from pathlib import Path

import typer

from . import discovery, downloads, extraction, page_processing
from .config import ConfigurationError, load_settings
from .database import create_engine_from_settings
from .logging_config import configure_logging
from .raw_storage import ArtifactError
from .sources.base import DiscoveryError
from .sources.pmegp import PROJECTS_URL, PMEGPAdapter

app = typer.Typer(
    help="Local Government MSME project intelligence tools.",
    no_args_is_help=True,
)
source_app = typer.Typer(
    help="Source metadata/link discovery; list and sample are offline.", no_args_is_help=True
)
app.add_typer(source_app, name="source")
download_app = typer.Typer(help="Raw acquisition; list/verify are offline.", no_args_is_help=True)
app.add_typer(download_app, name="download")
extract_app = typer.Typer(help="OFFLINE native PDF text/layout extraction.", no_args_is_help=True)
app.add_typer(extract_app, name="extract")
pages_app = typer.Typer(
    help="OFFLINE table extraction and selective local OCR.", no_args_is_help=True
)
app.add_typer(pages_app, name="pages")


@app.callback()
def main() -> None:
    """Run local Government MSME project intelligence tools."""


@app.command()
def health() -> None:
    """Validate local configuration without contacting PostgreSQL."""
    try:
        settings = load_settings()
        configure_logging(settings.log_level)
        create_engine_from_settings(settings).dispose()
    except ConfigurationError as error:
        typer.echo(f"Configuration error: {error}", err=True)
        raise typer.Exit(code=2) from None

    typer.echo("Configuration OK; database connectivity was not checked.")


def _manifest_path(source: str) -> Path:
    if source != "pmegp":
        raise DiscoveryError("Only source pmegp is supported.")
    settings = load_settings()
    configure_logging(settings.log_level)
    return settings.data_dir / "discovery" / "pmegp.json"


def _fail(error: Exception) -> None:
    # OS/transport exception messages can contain credentials, proxy URLs, or response bodies.
    message = (
        "Local file operation failed; existing snapshot was not replaced."
        if isinstance(error, OSError)
        else str(error)
    )
    typer.echo(f"Discovery error: {message}", err=True)
    raise typer.Exit(code=2) from None


@source_app.command("discover")
def source_discover(
    source: str = typer.Option("pmegp"),
    output: Path | None = typer.Option(None),
    limit: int | None = typer.Option(None, min=1),
    sample: Path | None = typer.Option(None),
    timeout: float = typer.Option(30.0, help="LIVE HTTP operation timeout, in seconds."),
    request_delay: float = typer.Option(
        1.0, help="Seconds between requests; minimum 1 plus robots policy."
    ),
) -> None:
    """LIVE: enumerate the full source before applying optional output filters. Never fetch PDFs."""
    try:
        full_path = _manifest_path(source)
        if limit is not None and sample is not None:
            raise DiscoveryError("--limit and --sample are mutually exclusive.")
        filtered = limit is not None or sample is not None
        destination = output or full_path
        if filtered and (output is None or destination.resolve() == full_path.resolve()):
            raise DiscoveryError(
                "Filtered discovery requires --output different from the full snapshot."
            )
        selector = discovery.read_sample(sample) if sample is not None else None
        previous = discovery.read_manifest(full_path) if filtered and full_path.exists() else None
        if destination.exists():
            existing = discovery.read_manifest(destination)
            expected_scope = "sample" if sample else "limit" if limit is not None else "full"
            if existing["scope"] != expected_scope or existing["source_key"] != source:
                raise DiscoveryError("Output already holds a different source/scope.")
            if not filtered:
                previous = existing
        typer.echo("LIVE: checking robots, official HTML and JSON; no document bodies requested.")
        with PMEGPAdapter(timeout=timeout, request_delay=request_delay) as adapter:
            manifest, changes = discovery.build_manifest(
                adapter.discover_projects(),
                source_key=adapter.source_key,
                source_url=adapter.source_url,
                previous=previous,
            )
        if filtered:
            manifest = discovery.filter_manifest(manifest, limit=limit, sample=selector)
        discovery.write_manifest(destination, manifest)
        typer.echo(discovery.summary(manifest))
        typer.echo(
            f"added={len(changes['added'])} changed={len(changes['changed'])} "
            f"no_longer_seen={len(changes['no_longer_seen'])}; written {destination}"
        )
    except (DiscoveryError, ConfigurationError, OSError) as error:
        _fail(error)


@source_app.command("list")
def source_list(
    source: str = typer.Option("pmegp"),
    manifest: Path | None = typer.Option(None),
    limit: int | None = typer.Option(None, min=1),
) -> None:
    """OFFLINE: inspect saved project metadata and original/canonical document links."""
    try:
        default = _manifest_path(source)
        path = manifest or default
        if manifest is None and not path.exists():
            typer.echo(f"{source}: not discovered (no local manifest).")
            return
        snapshot = discovery.read_manifest(path)
        if snapshot["source_key"] != source:
            raise DiscoveryError("Manifest belongs to a different source.")
        typer.echo(
            f"{source} observed_at={snapshot['discovered_at']} {discovery.summary(snapshot)}"
        )
        for record in snapshot["projects"][:limit]:
            typer.echo(discovery.json_text(record).rstrip())
        if snapshot["issues"]:
            typer.echo(discovery.json_text({"issues": snapshot["issues"]}).rstrip())
    except (DiscoveryError, ConfigurationError, OSError) as error:
        _fail(error)


@source_app.command("sample")
def source_sample(
    source: str = typer.Option("pmegp"),
    count: int = typer.Option(20, min=1),
    manifest: Path | None = typer.Option(None),
    output: Path = typer.Option(Path("config/sample_20.json")),
    replace: bool = typer.Option(False, help="Explicitly replace a changed fixed sample."),
) -> None:
    """OFFLINE: choose a deterministic category/link-pattern sample from a full manifest."""
    try:
        default = _manifest_path(source)
        path = manifest or default
        if output.resolve() == path.resolve():
            raise DiscoveryError("Sample output must not overwrite its source manifest.")
        snapshot = discovery.read_manifest(path)
        if snapshot["source_key"] != source:
            raise DiscoveryError("Manifest belongs to a different source.")
        sample = discovery.select_sample(snapshot, count)
        changed = discovery.write_sample(output, sample, replace=replace)
        typer.echo(f"{'Written' if changed else 'Unchanged'} {output}: {sample['count']} projects.")
        typer.echo(discovery.sample_coverage(snapshot, sample))
    except (DiscoveryError, ConfigurationError, OSError) as error:
        _fail(error)


@source_app.command("smoke")
def source_smoke(
    source: str = typer.Option("pmegp"),
    timeout: float = typer.Option(30.0),
    request_delay: float = typer.Option(1.0),
) -> None:
    """LIVE: check robots, HTML shell and one JSON response; no writes or PDFs."""
    try:
        _manifest_path(source)
        typer.echo(
            "LIVE: robots + HTML shell + one all-projects JSON response; no artifact writes."
        )
        with PMEGPAdapter(timeout=timeout, request_delay=request_delay) as adapter:
            records = adapter.smoke()
            typer.echo(
                f"url={adapter.source_url} parsed_entries={len(records)} "
                f"api_url={PROJECTS_URL} server_pagination=none "
                f"links={sum(len(record.documents) for record in records)} "
                f"explicit_categories={sum(record.category_hint is not None for record in records)}"
            )
    except (DiscoveryError, ConfigurationError, OSError) as error:
        _fail(error)


def _download_fail(error: Exception) -> None:
    message = (
        "Local storage operation failed; durable receipts/raw files retained."
        if isinstance(error, OSError)
        else str(error)
    )
    typer.echo(f"Download error: {message}", err=True)
    raise typer.Exit(code=2) from None


def _download_run(
    manifest: Path, sample: Path | None = None, discovery_path: Path | None = None
) -> None:
    try:
        settings = load_settings()
        configure_logging(settings.log_level)
        value = (
            downloads.prepare(sample, discovery_path, manifest, settings.data_dir)
            if sample is not None
            else downloads.read_manifest(manifest)
        )
        typer.echo("LIVE when needed: policy-checked downloads; verified local bytes are reused.")
        result = downloads.execute(value, manifest, settings.data_dir, retry_failed=sample is None)
        typer.echo(discovery.json_text(downloads.report(result)))
        if downloads.summarize(result)["failed"] or downloads.summarize(result)["unfinished"]:
            raise typer.Exit(code=1)
    except (
        downloads.DownloadError,
        ArtifactError,
        DiscoveryError,
        ConfigurationError,
        OSError,
    ) as error:
        _download_fail(error)


@download_app.command("run")
def download_run(
    sample: Path = typer.Option(...),
    discovery_path: Path = typer.Option(..., "--discovery"),
    manifest: Path = typer.Option(...),
) -> None:
    """LIVE when needed: acquire/resume the actual selected document candidates."""
    _download_run(manifest, sample, discovery_path)


@download_app.command("retry-failed")
def download_retry_failed(manifest: Path = typer.Option(...)) -> None:
    """LIVE when needed: retry failed URLs, never silently repair corrupt raw files."""
    _download_run(manifest)


@download_app.command("list")
def download_list(manifest: Path = typer.Option(...)) -> None:
    """OFFLINE: inspect counts and failed URLs/source project IDs."""
    try:
        typer.echo(discovery.json_text(downloads.report(downloads.read_manifest(manifest))))
    except (downloads.DownloadError, OSError) as error:
        _download_fail(error)


@download_app.command("verify")
def download_verify(manifest: Path = typer.Option(...)) -> None:
    """OFFLINE: verify stored hashes/paths/bytes; unavailable URLs stay explicit."""
    try:
        value = downloads.read_manifest(manifest)
        result = downloads.verify(value, load_settings().data_dir)
        typer.echo(discovery.json_text(result))
        typer.echo(discovery.json_text({"failures": downloads.report(value)["failures"]}))
        if result["problems"]:
            raise typer.Exit(code=1)
    except (downloads.DownloadError, ArtifactError, ConfigurationError, OSError) as error:
        _download_fail(error)


def _extract(manifest: Path, *, verify: bool) -> None:
    try:
        settings = load_settings()
        configure_logging(settings.log_level)
        if verify:
            result = extraction.verify(manifest, settings.data_dir)
            failed = bool(result["problems"])
        else:
            result = extraction.report(extraction.execute(manifest, settings.data_dir))
            failed = bool(result["failures"] or result["summary"]["pdfs_pending"])
        typer.echo(discovery.json_text(result))
        if failed:
            raise typer.Exit(code=1)
    except (
        extraction.ExtractionError,
        downloads.DownloadError,
        ArtifactError,
        ConfigurationError,
        OSError,
    ) as error:
        message = (
            "Local extraction storage operation failed."
            if isinstance(error, OSError)
            else str(error)
        )
        typer.echo(f"Extraction error: {message}", err=True)
        raise typer.Exit(code=2) from None


@extract_app.command("run")
def extract_run(manifest: Path = typer.Option(..., help="Existing M02 download manifest.")) -> None:
    """OFFLINE: verify raw files, extract native pages, or reuse verified versioned outputs."""
    _extract(manifest, verify=False)


@extract_app.command("verify")
def extract_verify(
    manifest: Path = typer.Option(..., help="Existing M02 download manifest."),
) -> None:
    """OFFLINE: check raw/output hashes, parser version, page coverage and associations."""
    _extract(manifest, verify=True)


@pages_app.command("run")
def pages_run(
    manifest: Path = typer.Option(..., help="Existing M02 manifest; M03 must be verified."),
    min_native_chars: int = typer.Option(80, min=0),
    min_native_words: int = typer.Option(10, min=0),
    min_printable_ratio: float = typer.Option(0.95, min=0, max=1),
    language: str = typer.Option("eng"),
) -> None:
    """OFFLINE: retain native artifacts and produce versioned tables/OCR JSON."""
    try:
        options = page_processing.Options(
            min_native_chars, min_native_words, min_printable_ratio, language
        )
        result = page_processing.execute(manifest, load_settings().data_dir, options)
        typer.echo(discovery.json_text(page_processing.summary(result)))
        if any(d["status"] == "FAILED" for d in result["documents"]):
            raise typer.Exit(1)
    except (
        extraction.ExtractionError,
        downloads.DownloadError,
        ArtifactError,
        ConfigurationError,
        OSError,
    ) as error:
        message = (
            "Local page-processing storage error." if isinstance(error, OSError) else str(error)
        )
        typer.echo(f"Page processing error: {message}", err=True)
        raise typer.Exit(2) from None


@pages_app.command("verify")
def pages_verify(manifest: Path = typer.Option(...)) -> None:
    """OFFLINE: verify native/raw identities, output hashes and project associations."""
    try:
        result = page_processing.verify(manifest, load_settings().data_dir)
        typer.echo(discovery.json_text(result))
        if result["problems"]:
            raise typer.Exit(1)
    except (
        extraction.ExtractionError,
        downloads.DownloadError,
        ArtifactError,
        ConfigurationError,
        OSError,
    ) as error:
        message = (
            "Local page-processing storage error." if isinstance(error, OSError) else str(error)
        )
        typer.echo(f"Page processing error: {message}", err=True)
        raise typer.Exit(2) from None
