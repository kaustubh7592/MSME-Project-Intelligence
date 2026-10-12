"""Synthetic, offline acquisition tests; never download a government document."""

import copy
import hashlib
import re
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

from msmeintel import cli, discovery, downloads, raw_storage
from msmeintel.raw_storage import ArtifactError
from msmeintel.sources.base import DiscoveryError, DocumentCandidate, ProjectCandidate

SOURCE = "https://example.test/list"
PDF = (Path(__file__).parent / "fixtures/downloads/minimal.pdf").read_bytes()
SECOND_PDF = PDF.replace(b"300 144", b"301 144")
runner = CliRunner()


class Body(httpx.SyncByteStream):
    def __init__(self, chunks):
        self.chunks = chunks
        self.closed = False

    def __iter__(self):
        for item in self.chunks:
            if isinstance(item, BaseException):
                raise item
            yield item

    def close(self):
        self.closed = True


class Unread(httpx.SyncByteStream):
    def __iter__(self):
        raise AssertionError("Forbidden body was read")


def response(body=PDF, *, status=200, headers=None):
    return httpx.Response(
        status,
        headers=headers
        if headers is not None
        else {"Content-Type": "application/pdf", "Content-Length": str(len(body))},
        stream=Body([body]),
    )


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    current, sleeps = [0.0], []

    def sleep(seconds):
        sleeps.append(seconds)
        current[0] += seconds

    monkeypatch.setattr(downloads.time, "sleep", sleep)
    monkeypatch.setattr(downloads.time, "monotonic", lambda: current[0])
    return current, sleeps


@pytest.fixture
def work(tmp_path):
    def factory(links=None):
        links = links if links is not None else [["/a.pdf"], ["/b.pdf"]]
        projects = [
            ProjectCandidate(
                title=f"Synthetic project {i}",
                listing_url=SOURCE,
                external_project_id=str(i),
                documents=tuple(
                    DocumentCandidate(href, SOURCE, title="Synthetic") for href in group
                ),
            )
            for i, group in enumerate(links, 1)
        ]
        full, _ = discovery.build_manifest(projects, source_key="synthetic", source_url=SOURCE)
        sample = discovery.select_sample(full, len(projects))
        full_path, sample_path = tmp_path / "full.json", tmp_path / "sample.json"
        output, data_dir = tmp_path / "downloads.json", tmp_path / "data"
        discovery.write_manifest(full_path, full)
        discovery.write_sample(sample_path, sample, replace=True)
        manifest = downloads.prepare(sample_path, full_path, output, data_dir)
        return manifest, output, data_dir, sample_path, full_path

    return factory


def execute(workflow, handler=None, *, robots=None, retry=False):
    value, output, data_dir, _, _ = workflow
    opened = []

    def route(request):
        opened.append(str(request.url))
        assert request.headers["user-agent"] == downloads.USER_AGENT
        assert request.headers["accept-encoding"] == "identity"
        assert request.extensions["timeout"]["connect"] == 10
        assert "cookie" not in request.headers
        if request.url.path == "/robots.txt":
            return robots(request) if robots else httpx.Response(404, stream=Unread())
        return handler(request) if handler else response()

    result = downloads.execute(
        value, output, data_dir, retry_failed=retry, transport=httpx.MockTransport(route)
    )
    return result, opened


def test_synthetic_fixture_has_valid_xref_and_no_active_content():
    assert PDF.startswith(b"%PDF-1.4\n")
    start = int(re.search(rb"startxref\n(\d+)", PDF)[1])
    assert PDF[start:].startswith(b"xref\n")
    offsets = re.findall(rb"(\d{10}) 00000 n", PDF)
    for number, offset in enumerate(offsets, 1):
        assert PDF[int(offset) :].startswith(f"{number} 0 obj\n".encode())
    assert b"/JavaScript" not in PDF and b"/EmbeddedFiles" not in PDF


def test_shared_urls_content_and_all_associations(work):
    workflow = work([["/a.pdf", "/b.pdf", "/a.pdf#different"], ["/a.pdf"]])
    result, opened = execute(workflow)
    summary = result["last_run"]["summary"]
    assert summary == {
        "projects": 2,
        "associations": 3,
        "unique_urls": 2,
        "duplicate_url_associations": 1,
        "successful_urls": 2,
        "unique_hashes": 1,
        "storage_bytes": len(PDF),
        "content_duplicate_urls": 1,
        "failed": 0,
        "unfinished": 0,
        "urls_attempted": 2,
        "http_attempts": 2,
        "downloaded": 2,
        "skipped": 0,
        "recovered": 0,
        "new_files": 1,
        "content_deduplicated": 1,
    }
    assert len(opened) == 3
    assert len(result["documents"][0]["associations"]) == 2
    assert any(a["document"]["original_variants"] for a in result["documents"][0]["associations"])
    files = list((workflow[2] / "raw").glob("*/*.pdf"))
    assert len(files) == 1 and files[0].read_bytes() == PDF
    assert files[0].stem == hashlib.sha256(PDF).hexdigest()
    assert not list((workflow[2] / "raw/.tmp").glob("*.part"))
    assert downloads.read_manifest(workflow[1]) == result
    assert downloads.verify(result, workflow[2])["problems"] == []


@pytest.mark.parametrize("count", [1, 3, 7])
def test_dynamic_count_case_sensitive_urls(work, count):
    workflow = work([[f"/{i}.pdf", f"/{i}.PDF"] for i in range(count)])
    result, opened = execute(workflow)
    assert result["last_run"]["summary"]["projects"] == count
    assert result["last_run"]["summary"]["urls_attempted"] == count * 2
    assert len(opened) == count * 2 + 1


def test_second_run_no_http_preserves_bytes_mtime_and_time(work, monkeypatch):
    workflow = work()
    result, _ = execute(workflow)
    before = [
        (d["downloaded_at"], (workflow[2] / d["storage_path"]).stat().st_mtime_ns)
        for d in result["documents"]
    ]

    def no_http(*args, **kwargs):
        raise AssertionError("Verified rerun must not call HTTP, even robots")

    monkeypatch.setattr(httpx.Client, "send", no_http)
    again, opened = execute(workflow)
    assert opened == []
    assert again["last_run"]["summary"]["skipped"] == 2
    assert all(
        again["last_run"]["summary"][k] == 0 for k in ("urls_attempted", "downloaded", "new_files")
    )
    assert before == [
        (d["downloaded_at"], (workflow[2] / d["storage_path"]).stat().st_mtime_ns)
        for d in again["documents"]
    ]
    assert downloads.verify(again, workflow[2])["verified_hashes"] == 1


@pytest.mark.parametrize(
    "mime", [None, "application/octet-stream", "application/pdf; charset=binary"]
)
def test_mime_with_valid_signature(work, mime):
    result, _ = execute(
        work([["/a.pdf"]]), lambda r: response(headers={"Content-Type": mime} if mime else {})
    )
    document = result["documents"][0]
    assert document["status"] == "DOWNLOADED"
    assert bool(document["warnings"]) == (mime != "application/pdf; charset=binary")


@pytest.mark.parametrize("mime", ["text/html", "application/json", "image/png", "text/plain"])
def test_explicit_non_pdf_mime_never_reads_body(work, mime):
    result, _ = execute(
        work([["/a.pdf"]]),
        lambda r: httpx.Response(200, headers={"Content-Type": mime}, stream=Unread()),
    )
    assert result["documents"][0]["error"]["category"] == "INVALID_MIME"


@pytest.mark.parametrize(
    ("body", "category"),
    [
        (b"", "INVALID_PDF"),
        (b"<html>challenge</html>", "INVALID_PDF"),
        (b"PK\x03\x04synthetic ZIP-like non-PDF bytes", "INVALID_PDF"),
        (PDF[:-7], "INVALID_PDF"),
        (b"%PDF-garbage\n%%EOF", "INVALID_PDF"),
    ],
)
def test_bad_pdf_bodies(work, body, category):
    workflow = work([["/a.pdf"]])
    result, _ = execute(workflow, lambda r: response(body))
    assert result["documents"][0]["error"]["category"] == category
    assert result["documents"][0]["sha256"] is None
    assert not list(workflow[2].rglob("*.pdf"))
    assert not list(workflow[2].rglob("*.part"))


@pytest.mark.parametrize(
    ("headers", "category"),
    [
        ({"content-length": "1"}, "LENGTH_MISMATCH"),
        ({"content-length": "-1"}, "LENGTH_MISMATCH"),
        ({"content-length": "4, 4"}, "LENGTH_MISMATCH"),
        ({"content-length": str(50 * 1024 * 1024 + 1)}, "SIZE_LIMIT"),
        ({"content-encoding": "gzip"}, "CONTENT_ENCODING"),
    ],
)
def test_header_checks(work, headers, category):
    result, _ = execute(work([["/a.pdf"]]), lambda r: response(headers=headers))
    assert result["documents"][0]["error"]["category"] == category


def test_streamed_size_limit(work, monkeypatch):
    monkeypatch.setattr(raw_storage, "MAX_PDF_BYTES", 100)
    result, _ = execute(work([["/a.pdf"]]), lambda r: response(headers={}))
    assert result["documents"][0]["error"]["category"] == "SIZE_LIMIT"


@pytest.mark.parametrize("status", [204, 206, 401, 403, 404, 410])
def test_http_terminal_failure_does_not_lose_success(work, status):
    workflow = work()
    result, opened = execute(
        workflow,
        lambda r: httpx.Response(status, stream=Unread()) if r.url.path == "/a.pdf" else response(),
    )
    assert result["last_run"]["summary"]["failed"] == 1
    assert result["last_run"]["summary"]["successful_urls"] == 1
    assert len(opened) == 3
    assert downloads.verify(result, workflow[2])["problems"] == []
    assert downloads.report(result)["failures"][0]["source_project_ids"] == ["1"]


@pytest.mark.parametrize("status", sorted(downloads.RETRY_STATUSES))
def test_transient_retry_then_success(work, status, clock):
    attempts = []

    def handler(request):
        attempts.append(request)
        return response() if len(attempts) == 3 else httpx.Response(status, stream=Unread())

    result, _ = execute(work([["/a.pdf"]]), handler)
    assert len(attempts) == 3
    assert result["last_run"]["summary"]["urls_attempted"] == 1
    assert result["last_run"]["summary"]["http_attempts"] == 3
    assert result["last_run"]["summary"]["failed"] == 0
    assert 1 in clock[1] and 2 in clock[1]


@pytest.mark.parametrize(
    "error_class",
    [httpx.ConnectTimeout, httpx.ReadTimeout, httpx.ConnectError, httpx.RemoteProtocolError],
)
def test_transport_retry_exhaustion_is_sanitized(work, error_class):
    def handler(request):
        raise error_class("secret proxy password/body", request=request)

    result, opened = execute(work([["/a.pdf"]]), handler)
    assert len(opened) == 4
    assert result["documents"][0]["error"]["retryable"]
    assert "secret" not in discovery.json_text(result)


def test_midstream_timeout_removes_partial_before_retry(work):
    attempts, bodies = [], []

    def handler(request):
        attempts.append(request)
        stream = (
            Body([PDF[:40], httpx.ReadTimeout("private")]) if len(attempts) == 1 else Body([PDF])
        )
        bodies.append(stream)
        return httpx.Response(200, headers={"content-type": "application/pdf"}, stream=stream)

    workflow = work([["/a.pdf"]])
    result, _ = execute(workflow, handler)
    assert result["last_run"]["summary"]["downloaded"] == 1
    assert all(b.closed for b in bodies)
    assert (workflow[2] / result["documents"][0]["storage_path"]).read_bytes() == PDF


def test_slow_stream_elapsed_cap(work, clock):
    class Slow(Body):
        def __iter__(self):
            clock[0][0] += 121
            yield PDF

    result, _ = execute(work([["/a.pdf"]]), lambda r: httpx.Response(200, stream=Slow([])))
    assert result["documents"][0]["error"]["category"] == "HTTP_TIMEOUT"
    assert result["documents"][0]["attempts"] == 3


@pytest.mark.parametrize("retry_after", ["120", "Fri, 01 Jan 2100 00:00:00 GMT"])
def test_retry_after_defers_origin_and_survives_rerun(work, retry_after):
    workflow = work()
    result, opened = execute(
        workflow,
        lambda r: httpx.Response(429, headers={"retry-after": retry_after}, stream=Unread()),
    )
    assert len(opened) == 2 and result["last_run"]["summary"]["failed"] == 2
    assert all(d["retry_not_before"] for d in result["documents"])
    workflow = (downloads.read_manifest(workflow[1]), *workflow[1:])
    result, opened = execute(workflow, retry=True)
    assert opened == [] and result["last_run"]["summary"]["urls_attempted"] == 0


def test_short_retry_after_and_exhausted_rate_limit(work, clock):
    result, opened = execute(
        work(), lambda r: httpx.Response(429, headers={"retry-after": "3"}, stream=Unread())
    )
    assert len(opened) == 4
    assert result["last_run"]["summary"]["urls_attempted"] == 1
    assert sum(clock[1]) >= 5.9


@pytest.mark.parametrize(
    "policy",
    [
        "User-agent: *\nDisallow: /",
        "User-agent: *\nDisallow: /*secret",
        "User-agent: *\nAllow: /\nDisallow: /a",
        "Disallow: /",
        "User-agent: *\nAllow: /\n\nUser-agent: *\nDisallow: /",
        "User-agent: *\nCrawl-delay: 1.5",
        "<html>captcha</html>",
        "User-agent: *\nRequest-rate: 0/10",
        "User-agent: *\nUnknown: value",
    ],
)
def test_robots_restrictions(work, policy):
    result, opened = execute(
        work(),
        robots=lambda r: httpx.Response(200, headers={"content-type": "text/plain"}, text=policy),
    )
    assert opened == ["https://example.test/robots.txt"]
    assert result["last_run"]["summary"]["failed"] == 2


@pytest.mark.parametrize("status", [301, 401, 403, 429, 500])
def test_robots_http_fail_closed(work, status):
    result, opened = execute(work(), robots=lambda r: httpx.Response(status, stream=Unread()))
    assert len(opened) == 1 and result["last_run"]["summary"]["urls_attempted"] == 0


@pytest.mark.parametrize("status", [404, 410])
def test_absent_robots_not_a_download_prohibition(work, status):
    result, _ = execute(
        work([["/a.pdf"]]), robots=lambda r: httpx.Response(status, stream=Unread())
    )
    assert result["last_run"]["summary"]["downloaded"] == 1


def test_robots_pacing_cookies_and_same_origin_redirect(work, clock):
    def handler(request):
        if request.url.path == "/a.pdf":
            return httpx.Response(
                302, headers={"location": "/final.pdf", "set-cookie": "secret=1"}, stream=Unread()
            )
        return response()

    result, opened = execute(
        work([["/a.pdf"]]),
        handler,
        robots=lambda r: httpx.Response(
            200,
            headers={"content-type": "text/plain"},
            text="User-agent: *\nAllow: /\nCrawl-delay: 2\nRequest-rate: 1/3",
        ),
    )
    assert len(opened) == 3
    assert clock[1] == [3, 3]
    assert result["documents"][0]["final_url"] == "https://example.test/final.pdf"


@pytest.mark.parametrize(
    "target",
    [
        "https://evil.test/x",
        "http://example.test/x",
        "file:///tmp/a",
        "http://localhost/x",
        "/a.pdf",
    ],
)
def test_unsafe_redirect_not_requested(work, target):
    result, opened = execute(
        work([["/a.pdf"]]),
        lambda r: httpx.Response(302, headers={"location": target}, stream=Unread()),
    )
    assert len(opened) == 2 and result["last_run"]["summary"]["failed"] == 1


def test_redirect_hop_cap_and_robots_destination(work):
    result, opened = execute(
        work([["/a.pdf"]]),
        lambda r: httpx.Response(302, headers={"location": str(r.url) + "x"}, stream=Unread()),
    )
    assert len(opened) == 5
    assert result["documents"][0]["error"]["category"] == "REDIRECT"


@pytest.mark.parametrize(
    "url",
    [
        "https://127.0.0.1/a",
        "https://127.1/a",
        "https://224.0.0.1/a",
        "https://[::1]/a",
        "https://10.0.0.2/a",
        "https://localhost/a",
        "https://box.local/a",
        "https://u:p@example.test/a",
    ],
)
def test_unsafe_origin(url):
    with pytest.raises((downloads.DownloadError, DiscoveryError)):
        downloads.checked_url(url, url)


def test_retry_failed_only_and_normal_run_leaves_failures(work):
    workflow = work()
    result, _ = execute(
        workflow,
        lambda r: response() if r.url.path == "/b.pdf" else httpx.Response(404, stream=Unread()),
    )
    receipt = copy.deepcopy(result["documents"][1])
    result, opened = execute(workflow)
    assert opened == [] and result["last_run"]["summary"]["failed"] == 1
    result, opened = execute(workflow, retry=True)
    assert opened == ["https://example.test/robots.txt", "https://example.test/a.pdf"]
    assert result["last_run"]["summary"]["successful_urls"] == 2
    assert result["documents"][1]["downloaded_at"] == receipt["downloaded_at"]


@pytest.mark.parametrize("point", ["partial", "staged", "published", "receipt"])
def test_interrupted_download_recovers(work, monkeypatch, point):
    workflow = work([["/a.pdf"]])
    real_publish, real_checkpoint = raw_storage.publish, downloads.checkpoint

    def interrupted_publish(*args):
        if point == "published":
            real_publish(*args)
        raise KeyboardInterrupt

    def interrupted_checkpoint(path, value):
        if point == "receipt" and value["documents"][0]["status"] == "DOWNLOADED":
            raise KeyboardInterrupt
        real_checkpoint(path, value)

    def handler(request):
        return (
            httpx.Response(200, stream=Body([PDF[:20], KeyboardInterrupt()]))
            if point == "partial"
            else response()
        )

    with monkeypatch.context() as patch:
        if point in {"staged", "published"}:
            patch.setattr(raw_storage, "publish", interrupted_publish)
        patch.setattr(downloads, "checkpoint", interrupted_checkpoint)
        with pytest.raises(KeyboardInterrupt):
            execute(workflow, handler)
    saved = downloads.read_manifest(workflow[1])
    assert saved["documents"][0]["status"] == (
        "DOWNLOAD_PENDING" if point == "partial" else "STAGED"
    )
    assert downloads.verify(saved, workflow[2])["problems"]
    result, opened = execute((saved, *workflow[1:]))
    assert result["documents"][0]["status"] == "DOWNLOADED"
    assert bool(opened) == (point == "partial")
    assert len(list(workflow[2].rglob("*.pdf"))) == 1
    assert not list(workflow[2].rglob("*.part"))


def test_manifest_replacement_failure_retains_previous_receipt(work, monkeypatch):
    workflow = work()
    execute(workflow)
    previous = workflow[1].read_bytes()

    def fail(*args):
        raise OSError("private path")

    monkeypatch.setattr(downloads.os, "replace", fail)
    with pytest.raises(OSError):
        execute(workflow)
    assert workflow[1].read_bytes() == previous
    assert not list(workflow[1].parent.glob("*.tmp"))
    assert downloads.verify(downloads.read_manifest(workflow[1]), workflow[2])["problems"] == []


def test_transient_windows_receipt_lock_retries_without_data_loss(work, monkeypatch):
    workflow = work([["/a.pdf"]])
    replace = downloads.os.replace
    calls, sleeps = [], []

    def temporarily_locked(*args):
        calls.append(args)
        if len(calls) == 1:
            raise PermissionError("transient receipt lock")
        return replace(*args)

    monkeypatch.setattr(downloads.os, "replace", temporarily_locked)
    monkeypatch.setattr(downloads, "storage_retry_sleep", sleeps.append)
    result, _ = execute(workflow)
    assert sleeps == [0.05]
    assert downloads.verify(result, workflow[2])["verified_hashes"] == 1


def test_permanent_receipt_lock_is_bounded(work, monkeypatch):
    workflow = work([["/a.pdf"]])
    execute(workflow)
    before = workflow[1].read_bytes()
    calls = []

    def locked(*args):
        calls.append(args)
        raise PermissionError("locked")

    monkeypatch.setattr(downloads.os, "replace", locked)
    monkeypatch.setattr(downloads, "storage_retry_sleep", lambda seconds: None)
    with pytest.raises(PermissionError):
        execute(workflow)
    assert len(calls) == 5 and workflow[1].read_bytes() == before


def test_storage_publication_failure_remains_recoverable(work, monkeypatch):
    workflow = work([["/a.pdf"]])
    with monkeypatch.context() as patch:
        patch.setattr(
            raw_storage.os, "link", lambda *a: (_ for _ in ()).throw(OSError("unsupported"))
        )
        with pytest.raises(OSError):
            execute(workflow)
    saved = downloads.read_manifest(workflow[1])
    assert saved["documents"][0]["status"] == "STAGED"
    result, opened = execute((saved, *workflow[1:]))
    assert opened == [] and result["last_run"]["summary"]["recovered"] == 1


def test_corrupt_file_never_skipped_overwritten_or_retried(work):
    workflow = work([["/a.pdf"]])
    result, _ = execute(workflow)
    path = workflow[2] / result["documents"][0]["storage_path"]
    path.write_bytes(b"corrupted evidence")
    assert downloads.verify(result, workflow[2])["problems"]
    result, opened = execute(workflow)
    assert opened == [] and result["last_run"]["summary"]["skipped"] == 0
    assert result["documents"][0]["error"]["category"] == "CORRUPT_FILE"
    result, opened = execute(workflow, retry=True)
    assert opened == [] and path.read_bytes() == b"corrupted evidence"


@pytest.mark.parametrize("changed", [False, True])
def test_missing_file_refetch_requires_saved_hash(work, changed):
    workflow = work([["/a.pdf"]])
    result, _ = execute(workflow)
    path = workflow[2] / result["documents"][0]["storage_path"]
    digest = result["documents"][0]["sha256"]
    path.unlink()
    result, opened = execute(workflow, lambda r: response(SECOND_PDF if changed else PDF))
    assert len(opened) == 2
    assert result["documents"][0]["sha256"] == digest
    assert path.exists() is not changed
    if changed:
        assert result["documents"][0]["error"]["category"] == "HASH_CHANGED"


def test_existing_corrupt_hash_collision_is_not_clobbered(work):
    workflow = work([["/a.pdf"]])
    digest = hashlib.sha256(PDF).hexdigest()
    destination = workflow[2] / raw_storage.storage_path(digest)
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"do not overwrite")
    result, _ = execute(workflow)
    assert result["documents"][0]["status"] == "DOWNLOAD_FAILED"
    assert destination.read_bytes() == b"do not overwrite"


@pytest.mark.parametrize(
    "relative",
    [
        "../escape.pdf",
        "raw/aa/" + "b" * 64 + ".pdf",
        "raw/.tmp/foreign.part",
        "C:/evil.pdf",
        "raw/aa/../../x",
    ],
)
def test_unsafe_storage_paths(tmp_path, relative):
    with pytest.raises(ArtifactError):
        raw_storage.safe_path(tmp_path, relative)


def test_linked_raw_directory_rejected(tmp_path, monkeypatch):
    original = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink", lambda p: p.name == "raw" or original(p))
    with pytest.raises(ArtifactError):
        raw_storage.safe_path(tmp_path, raw_storage.storage_path("a" * 64))


@pytest.mark.parametrize(
    "damage",
    [
        lambda m: m.update(schema_version=2),
        lambda m: m["documents"].append(copy.deepcopy(m["documents"][0])),
        lambda m: m["documents"][0].update(storage_path="../escape", sha256="a" * 64),
        lambda m: m["documents"][0].update(status="DOWNLOADED"),
        lambda m: m["documents"][0].update(staging_path="raw/.tmp/foreign.part"),
        lambda m: m["documents"][0]["associations"][0]["document"].update(
            url="https://evil.test/a"
        ),
        lambda m: m["last_run"]["summary"].update(projects=10000),
        lambda m: m["documents"][0].update(attempts=True),
    ],
)
def test_invalid_receipts_rejected(work, damage):
    value = work()[0]
    damage(value)
    with pytest.raises(downloads.DownloadError):
        downloads.validate_manifest(value)


def test_invalid_json_and_input_alias_preserved(work):
    workflow = work()
    _, output, data_dir, sample, full = workflow
    for target in (sample, full):
        before = target.read_bytes()
        with pytest.raises(downloads.DownloadError):
            downloads.prepare(sample, full, target, data_dir)
        assert target.read_bytes() == before
    output.write_text('{"schema_version": 1, "schema_version": 1}', encoding="utf-8")
    before = output.read_bytes()
    with pytest.raises(downloads.DownloadError):
        downloads.prepare(sample, full, output, data_dir)
    assert output.read_bytes() == before


def test_changed_selection_stale_sample_and_raw_output(work):
    workflow = work()
    execute(workflow)
    _, output, data_dir, sample_path, full_path = workflow
    sample = discovery.read_sample(sample_path)
    sample["projects"] = sample["projects"][:1]
    sample["count"] = 1
    discovery.write_sample(sample_path, sample, replace=True)
    with pytest.raises(downloads.DownloadError, match="selection"):
        downloads.prepare(sample_path, full_path, output, data_dir)
    with pytest.raises(downloads.DownloadError, match="raw store"):
        downloads.prepare(sample_path, full_path, data_dir / "raw/receipt.json", data_dir)
    sample["projects"][0]["raw_title"] = "changed title"
    sample["projects"][0]["title"] = "changed title"
    discovery.write_sample(sample_path, sample, replace=True)
    with pytest.raises(downloads.DownloadError, match="differ"):
        downloads.prepare(sample_path, full_path, output, data_dir)


def test_cli_complete_offline_transport_workflow(work, monkeypatch):
    workflow = work()
    _, output, data_dir, sample, full = workflow
    monkeypatch.setenv("MSMEINTEL_DATA_DIR", str(data_dir))
    original = downloads.DownloadHTTP.__init__
    monkeypatch.setattr(
        downloads.DownloadHTTP,
        "__init__",
        lambda self, source, counts, transport=None: original(
            self,
            source,
            counts,
            httpx.MockTransport(
                lambda r: httpx.Response(404) if r.url.path == "/robots.txt" else response()
            ),
        ),
    )
    for command in (
        ["download", "--help"],
        [
            "download",
            "run",
            "--sample",
            str(sample),
            "--discovery",
            str(full),
            "--manifest",
            str(output),
        ],
        ["download", "list", "--manifest", str(output)],
        ["download", "verify", "--manifest", str(output)],
        ["download", "retry-failed", "--manifest", str(output)],
    ):
        result = runner.invoke(cli.app, command)
        assert result.exit_code == 0, result.output
    data = downloads.read_manifest(output)
    path = data_dir / data["documents"][0]["storage_path"]
    path.write_bytes(b"corruption")
    assert runner.invoke(cli.app, ["download", "verify", "--manifest", str(output)]).exit_code == 1


def test_cli_failure_exit_and_secret_redaction(work, monkeypatch):
    workflow = work()
    _, output, data_dir, sample, full = workflow
    monkeypatch.setenv("MSMEINTEL_DATA_DIR", str(data_dir))
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://private:supersecret@localhost/db")
    original = downloads.DownloadHTTP.__init__
    monkeypatch.setattr(
        downloads.DownloadHTTP,
        "__init__",
        lambda self, source, counts, transport=None: original(
            self, source, counts, httpx.MockTransport(lambda r: httpx.Response(404))
        ),
    )
    command = [
        "download",
        "run",
        "--sample",
        str(sample),
        "--discovery",
        str(full),
        "--manifest",
        str(output),
    ]
    result = runner.invoke(cli.app, command)
    assert result.exit_code == 1 and "HTTP_STATUS" in result.output
    assert "supersecret" not in result.output and "private" not in result.output
    monkeypatch.setenv("MSMEINTEL_LOG_LEVEL", "invalid")
    result = runner.invoke(cli.app, command)
    assert result.exit_code == 2 and "supersecret" not in result.output


def test_list_verify_never_http(work, monkeypatch):
    workflow = work()
    execute(workflow)
    monkeypatch.setenv("MSMEINTEL_DATA_DIR", str(workflow[2]))
    monkeypatch.setattr(httpx.Client, "send", lambda *a, **k: pytest.fail("Unexpected HTTP"))
    for command in ("list", "verify"):
        assert (
            runner.invoke(cli.app, ["download", command, "--manifest", str(workflow[1])]).exit_code
            == 0
        )


def test_distinct_valid_bytes_store_distinct_hashes(work):
    workflow = work()
    result, _ = execute(workflow, lambda r: response(PDF if r.url.path == "/a.pdf" else SECOND_PDF))
    assert result["last_run"]["summary"]["unique_hashes"] == 2
    assert result["last_run"]["summary"]["storage_bytes"] == len(PDF) + len(SECOND_PDF)
    assert downloads.verify(result, workflow[2])["verified_hashes"] == 2


def test_huge_declared_length_fails_without_int_conversion_or_body(work):
    result, _ = execute(
        work([["/a.pdf"]]),
        lambda r: httpx.Response(200, headers={"content-length": "9" * 5000}, stream=Unread()),
    )
    assert result["documents"][0]["error"]["category"] == "SIZE_LIMIT"


@pytest.mark.parametrize(
    "policy",
    [
        "User-agent: *\nCrawl-delay: 9999999999999999999999999",
        "User-agent: *\nCrawl-delay: 120",
        "User-agent: *\nRequest-rate: 1/9999999999999999999999999",
    ],
)
def test_unbounded_robots_wait_fails_closed(work, policy):
    result, opened = execute(
        work(),
        robots=lambda r: httpx.Response(200, headers={"content-type": "text/plain"}, text=policy),
    )
    assert len(opened) == 1 and result["last_run"]["summary"]["failed"] == 2


def test_invalid_retry_after_defers_origin(work):
    result, opened = execute(
        work(),
        lambda r: httpx.Response(503, headers={"retry-after": "unrecognized"}, stream=Unread()),
    )
    assert len(opened) == 2
    assert result["last_run"]["summary"]["failed"] == 2


def test_robots_destination_denial_before_redirect_request(work):
    result, opened = execute(
        work([["/a.pdf"]]),
        lambda r: httpx.Response(302, headers={"location": "/private/report"}, stream=Unread()),
        robots=lambda r: httpx.Response(
            200, headers={"content-type": "text/plain"}, text="User-agent: *\nDisallow: /private"
        ),
    )
    assert len(opened) == 2 and result["documents"][0]["error"]["category"] == "ACCESS_DENIED"


def test_robots_wrong_mime_oversize_and_transport_error(work, monkeypatch):
    workflow = work()
    for handler in (
        lambda r: httpx.Response(200, headers={"content-type": "text/html"}, stream=Unread()),
        lambda r: httpx.Response(200, headers={"content-type": "text/plain"}, text="x" * 10),
        lambda r: (_ for _ in ()).throw(httpx.ConnectTimeout("secret")),
    ):
        monkeypatch.setattr(downloads, "MAX_ROBOTS_BYTES", 5)
        result, opened = execute(workflow, robots=handler, retry=True)
        # Initial pending work is intentionally not eligible for retry-failed.
        if not opened:
            result, opened = execute(workflow, robots=handler)
        assert len(opened) == 1
        assert result["last_run"]["summary"]["failed"] == 2
        assert "secret" not in discovery.json_text(result)


def test_late_publication_failure_retains_earlier_success(work, monkeypatch):
    workflow = work()
    original = raw_storage.publish
    calls = []

    def fail_second(*args):
        calls.append(args)
        if len(calls) == 2:
            raise OSError("disk failure")
        return original(*args)

    with monkeypatch.context() as patch:
        patch.setattr(raw_storage, "publish", fail_second)
        with pytest.raises(OSError):
            execute(workflow, lambda r: response(PDF if r.url.path == "/a.pdf" else SECOND_PDF))
    saved = downloads.read_manifest(workflow[1])
    assert [d["status"] for d in saved["documents"]] == ["DOWNLOADED", "STAGED"]
    result, opened = execute((saved, *workflow[1:]))
    assert opened == [] and result["last_run"]["summary"]["recovered"] == 1
    assert result["last_run"]["summary"]["skipped"] == 1


def test_missing_staged_file_restarts_and_foreign_temporary_is_untouched(work, monkeypatch):
    workflow = work([["/a.pdf"]])
    with monkeypatch.context() as patch:
        patch.setattr(raw_storage, "publish", lambda *a: (_ for _ in ()).throw(KeyboardInterrupt()))
        with pytest.raises(KeyboardInterrupt):
            execute(workflow)
    saved = downloads.read_manifest(workflow[1])
    (workflow[2] / saved["documents"][0]["staging_path"]).unlink()
    foreign = workflow[2] / "raw/.tmp/user-notes.part"
    foreign.write_bytes(b"not application-owned")
    result, opened = execute((saved, *workflow[1:]))
    assert len(opened) == 2 and result["last_run"]["summary"]["downloaded"] == 1
    assert foreign.read_bytes() == b"not application-owned"


def test_store_symlink_rejected_before_http_and_checkpoint(work, monkeypatch):
    workflow = work()
    original = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink", lambda p: p.name == "raw" or original(p))
    with pytest.raises(ArtifactError):
        execute(workflow, lambda r: pytest.fail("Must not call HTTP"))
    assert not workflow[1].exists()


def test_invalid_manifest_cli_exits_two(work):
    workflow = work()
    workflow[1].write_text("not JSON", encoding="utf-8")
    result = runner.invoke(cli.app, ["download", "list", "--manifest", str(workflow[1])])
    assert result.exit_code == 2


def test_robots_retry_after_persists_across_runs(work):
    workflow = work()
    result, opened = execute(
        workflow,
        robots=lambda r: httpx.Response(503, headers={"retry-after": "120"}, stream=Unread()),
    )
    assert len(opened) == 1 and all(d["retry_not_before"] for d in result["documents"])
    saved = downloads.read_manifest(workflow[1])
    result, opened = execute((saved, *workflow[1:]), retry=True)
    assert opened == [] and result["last_run"]["summary"]["failed"] == 2


def test_encoded_robots_unread(work):
    result, opened = execute(
        work(),
        robots=lambda r: httpx.Response(
            200, headers={"content-type": "text/plain", "content-encoding": "gzip"}, stream=Unread()
        ),
    )
    assert len(opened) == 1 and result["last_run"]["summary"]["failed"] == 2


def test_http_client_invalid_url_is_safe_failure(work):
    result, _ = execute(
        work([["/a.pdf"]]), lambda r: (_ for _ in ()).throw(httpx.InvalidURL("secret"))
    )
    assert result["documents"][0]["error"]["category"] == "UNSAFE_URL"
    assert "secret" not in discovery.json_text(result)
