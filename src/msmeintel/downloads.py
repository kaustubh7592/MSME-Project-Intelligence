"""Sequential source-independent acquisition and inspectable download receipts."""

import copy
import hashlib
import ipaddress
import json
import os
import tempfile
import time
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from time import sleep as storage_retry_sleep
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser
from uuid import UUID

import httpx

from . import discovery, raw_storage
from .raw_storage import ArtifactError
from .sources.base import DiscoveryError, canonicalize_url

USER_AGENT = "MSMEIntel/0.1 (local learning project; document acquisition)"
MAX_ROBOTS_BYTES = 512 * 1024
ATTEMPT_SECONDS = 120
MAX_ATTEMPTS = 3
RETRY_STATUSES = {408, 429, 500, 502, 503, 504}
RUN_COUNTS = (
    "urls_attempted",
    "http_attempts",
    "downloaded",
    "skipped",
    "recovered",
    "new_files",
    "content_deduplicated",
)
DOCUMENT_FIELDS = {
    "canonical_url",
    "associations",
    "status",
    "sha256",
    "storage_path",
    "byte_count",
    "downloaded_at",
    "verified_at",
    "final_url",
    "content_type",
    "http_status",
    "attempts",
    "warnings",
    "error",
    "staging_path",
    "retry_not_before",
}


class DownloadError(ValueError):
    def __init__(self, category: str, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.category, self.retryable = category, retryable


def now() -> str:
    return datetime.now(UTC).isoformat()


def timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.utcoffset() != timedelta(0):
        raise ValueError("Not a UTC timestamp")
    return parsed


def checked_url(url: str, source_url: str) -> str:
    result = canonicalize_url(url)
    parsed, source = urlsplit(result), urlsplit(canonicalize_url(source_url))
    host = parsed.hostname.rstrip(".")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        if (
            "." not in host
            or host.replace(".", "").isdigit()
            or host.endswith((".localhost", ".local", ".internal"))
        ):
            raise DownloadError("UNSAFE_URL", "Local host names are forbidden.") from None
    else:
        if not address.is_global or address.is_multicast:
            raise DownloadError("UNSAFE_URL", "Non-public literal hosts are forbidden.")
    if (parsed.scheme, parsed.netloc) != (source.scheme, source.netloc):
        raise DownloadError("UNSAFE_URL", "Cross-origin or downgraded document URL.")
    return result


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def summarize(manifest: dict) -> dict:
    documents = manifest["documents"]
    associations = [a for d in documents for a in d["associations"]]
    stored = [d for d in documents if d["status"] == "DOWNLOADED"]
    hashes = {d["sha256"]: d["byte_count"] for d in stored}
    return {
        "projects": len({a["record_key"] for a in associations}),
        "associations": len(associations),
        "unique_urls": len(documents),
        "duplicate_url_associations": len(associations) - len(documents),
        "successful_urls": len(stored),
        "unique_hashes": len(hashes),
        "storage_bytes": sum(hashes.values()),
        "content_duplicate_urls": len(stored) - len(hashes),
        "failed": sum(d["status"] == "DOWNLOAD_FAILED" for d in documents),
        "unfinished": sum(d["status"] in {"DOWNLOAD_PENDING", "STAGED"} for d in documents),
    }


def _validate_observation(observation: dict, canonical: str) -> None:
    if set(observation) != {
        "original_href",
        "url",
        "canonical_url",
        "found_on_url",
        "title",
        "declared_type",
    }:
        raise ValueError("Invalid observation fields")
    if observation["canonical_url"] != canonical:
        raise ValueError("Wrong observation identity")
    if canonicalize_url(observation["original_href"], observation["found_on_url"]) != canonical:
        raise ValueError("Wrong original link")
    if (
        urljoin(observation["found_on_url"], observation["original_href"].strip())
        != observation["url"]
    ):
        raise ValueError("Wrong absolute original link")
    canonicalize_url(observation["found_on_url"])
    for key in ("title", "declared_type"):
        if observation[key] is not None and (
            not isinstance(observation[key], str) or not observation[key].strip()
        ):
            raise ValueError("Invalid observation text")


def validate_manifest(value: dict) -> None:
    try:
        if (
            set(value)
            != {
                "schema_version",
                "source_key",
                "source_url",
                "inputs",
                "created_at",
                "updated_at",
                "documents",
                "last_run",
            }
            or type(value["schema_version"]) is not int
            or value["schema_version"] != 1
        ):
            raise ValueError("Unsupported receipt schema")
        if not isinstance(value["source_key"], str) or not value["source_key"].strip():
            raise ValueError("Missing source")
        checked_url(value["source_url"], value["source_url"])
        if timestamp(value["created_at"]) > timestamp(value["updated_at"]):
            raise ValueError("Invalid receipt times")
        inputs = value["inputs"]
        if set(inputs) != {
            "sample_path",
            "discovery_path",
            "sample_sha256",
            "discovery_sha256",
            "discovered_at",
        }:
            raise ValueError("Invalid input provenance")
        for field in ("sample_path", "discovery_path"):
            if not isinstance(inputs[field], str) or not inputs[field].strip():
                raise ValueError("Missing input path")
        for field in ("sample_sha256", "discovery_sha256"):
            raw_storage.storage_path(inputs[field])
        timestamp(inputs["discovered_at"])
        if not isinstance(value["documents"], list) or not value["documents"]:
            raise ValueError("Missing documents")
        seen_urls, seen_associations, identities = set(), set(), {}
        for document in value["documents"]:
            if set(document) != DOCUMENT_FIELDS:
                raise ValueError("Invalid document fields")
            url = document["canonical_url"]
            if checked_url(url, value["source_url"]) != url or url in seen_urls:
                raise ValueError("Duplicate or noncanonical URL")
            seen_urls.add(url)
            if not isinstance(document["associations"], list) or not document["associations"]:
                raise ValueError("Missing associations")
            for association in document["associations"]:
                if set(association) != {
                    "record_key",
                    "external_project_id",
                    "raw_title",
                    "document",
                }:
                    raise ValueError("Invalid association")
                key = association["record_key"]
                UUID(key)
                identity = association["external_project_id"], association["raw_title"]
                if (
                    not isinstance(identity[1], str)
                    or not identity[1].strip()
                    or (
                        identity[0] is not None
                        and (not isinstance(identity[0], str) or not identity[0].strip())
                    )
                ):
                    raise ValueError("Invalid project identity")
                if (
                    key in identities
                    and identities[key] != identity
                    or (key, url) in seen_associations
                ):
                    raise ValueError("Conflicting/duplicate association")
                identities[key] = identity
                seen_associations.add((key, url))
                original = dict(association["document"])
                variants = original.pop("original_variants")
                if not isinstance(variants, list):
                    raise ValueError("Invalid original variants")
                for observation in [original, *variants]:
                    _validate_observation(observation, url)
            if document["status"] not in {
                "DOWNLOAD_PENDING",
                "STAGED",
                "DOWNLOADED",
                "DOWNLOAD_FAILED",
            }:
                raise ValueError("Invalid status")
            if type(document["attempts"]) is not int or document["attempts"] < 0:
                raise ValueError("Invalid attempt count")
            if not isinstance(document["warnings"], list) or not all(
                isinstance(w, str) for w in document["warnings"]
            ):
                raise ValueError("Invalid warnings")
            if document["http_status"] is not None and (
                type(document["http_status"]) is not int
                or not 100 <= document["http_status"] <= 599
            ):
                raise ValueError("Invalid HTTP status")
            if document["content_type"] is not None and not isinstance(
                document["content_type"], str
            ):
                raise ValueError("Invalid MIME")
            for field in ("downloaded_at", "verified_at", "retry_not_before"):
                if document[field] is not None:
                    timestamp(document[field])
            if document["final_url"] is not None:
                checked_url(document["final_url"], value["source_url"])
            if document["sha256"] is None:
                if any(
                    document[k] is not None for k in ("storage_path", "byte_count", "downloaded_at")
                ):
                    raise ValueError("Incomplete artifact identity")
            else:
                if document["storage_path"] != raw_storage.storage_path(document["sha256"]):
                    raise ValueError("Path differs from hash")
                if (
                    type(document["byte_count"]) is not int
                    or not 0 < document["byte_count"] <= raw_storage.MAX_PDF_BYTES
                ):
                    raise ValueError("Invalid artifact size")
                timestamp(document["downloaded_at"])
            if document["status"] in {"STAGED", "DOWNLOADED"} and document["sha256"] is None:
                raise ValueError("Successful/staged receipt has no artifact")
            staging = document["staging_path"]
            if staging is not None and not raw_storage.STAGING_PATTERN.fullmatch(staging):
                raise ValueError("Invalid staging path")
            if document["status"] == "STAGED" and staging is None:
                raise ValueError("Missing staging path")
            if document["status"] == "DOWNLOADED" and (
                staging is not None
                or document["verified_at"] is None
                or document["error"] is not None
            ):
                raise ValueError("Unverified downloaded receipt")
            error = document["error"]
            if error is not None:
                if (
                    set(error) != {"category", "message", "at", "retryable"}
                    or not all(
                        isinstance(error[k], str) and error[k] for k in ("category", "message")
                    )
                    or type(error["retryable"]) is not bool
                ):
                    raise ValueError("Invalid error")
                timestamp(error["at"])
            if document["status"] == "DOWNLOAD_FAILED" and error is None:
                raise ValueError("Failure has no reason")
        run = value["last_run"]
        if set(run) != {"started_at", "ended_at", "complete", "summary"}:
            raise ValueError("Invalid run")
        timestamp(run["started_at"])
        if type(run["complete"]) is not bool or run["complete"] != (run["ended_at"] is not None):
            raise ValueError("Invalid run completion")
        if run["ended_at"] is not None and timestamp(run["ended_at"]) < timestamp(
            run["started_at"]
        ):
            raise ValueError("Invalid run times")
        expected = summarize(value)
        if set(run["summary"]) != set(expected) | set(RUN_COUNTS):
            raise ValueError("Invalid summary fields")
        if any(type(v) is not int or v < 0 for v in run["summary"].values()):
            raise ValueError("Invalid summary counts")
        if any(run["summary"][k] != v for k, v in expected.items()):
            raise ValueError("Summary contradicts receipts")
    except (ValueError, KeyError, TypeError, AttributeError, OverflowError) as error:
        raise DownloadError(
            "INVALID_MANIFEST", "Invalid download manifest; no data replaced."
        ) from error


def read_manifest(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    except (OSError, ValueError, RecursionError) as error:
        raise DownloadError(
            "INVALID_MANIFEST", "Cannot read an unambiguous download manifest."
        ) from error
    validate_manifest(value)
    return value


def _protect_output(path: Path, inputs: dict, data_dir: Path) -> None:
    if path.resolve().is_relative_to((data_dir / "raw").resolve()):
        raise DownloadError("INVALID_PATH", "A manifest cannot be placed in the raw store.")
    for field in ("sample_path", "discovery_path"):
        source = Path(inputs[field])
        if path.resolve() == source.resolve() or (
            path.exists() and source.exists() and path.samefile(source)
        ):
            raise DownloadError("INVALID_PATH", "Manifest must not overwrite an M01 input.")
    if path.is_symlink():
        raise DownloadError("INVALID_PATH", "Manifest symlinks are forbidden.")


def checkpoint(path: Path, manifest: dict) -> None:
    manifest["updated_at"] = now()
    manifest["last_run"]["summary"].update(summarize(manifest))
    validate_manifest(manifest)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n", dir=path.parent, suffix=".tmp", delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(discovery.json_text(manifest))
            stream.flush()
            os.fsync(stream.fileno())
        # Windows scanners may briefly hold the previous receipt without delete-sharing.
        for attempt in range(5):
            try:
                os.replace(temporary, path)
                break
            except PermissionError:
                if attempt == 4:
                    raise
                storage_retry_sleep(0.05 * 2**attempt)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def prepare(sample_path: Path, discovery_path: Path, output: Path, data_dir: Path) -> dict:
    sample = discovery.read_sample(sample_path)
    full = discovery.read_manifest(discovery_path)
    selected = discovery.filter_manifest(full, sample=sample)
    originals = {p["record_key"]: p for p in selected["projects"]}
    grouped = {}
    for project in sample["projects"]:
        old = originals[project["record_key"]]
        if any(old[k] != project[k] for k in ("external_project_id", "documents", "raw_title")):
            raise DownloadError("STALE_SAMPLE", "Sample observations differ from full discovery.")
        for document in project["documents"]:
            url = checked_url(document["canonical_url"], sample["source_url"])
            grouped.setdefault(url, []).append(
                {
                    "record_key": project["record_key"],
                    "external_project_id": project["external_project_id"],
                    "raw_title": project["raw_title"],
                    "document": copy.deepcopy(document),
                }
            )
    inputs = {
        "sample_path": str(sample_path.resolve()),
        "discovery_path": str(discovery_path.resolve()),
        "sample_sha256": hashlib.sha256(sample_path.read_bytes()).hexdigest(),
        "discovery_sha256": hashlib.sha256(discovery_path.read_bytes()).hexdigest(),
        "discovered_at": full["discovered_at"],
    }
    _protect_output(output, inputs, data_dir)
    if output.exists():
        existing = read_manifest(output)
        if (
            any(existing[k] != sample[k] for k in ("source_key", "source_url"))
            or {d["canonical_url"]: d["associations"] for d in existing["documents"]} != grouped
        ):
            raise DownloadError(
                "CHANGED_SELECTION", "Existing receipt belongs to another selection."
            )
        return existing
    created = now()
    documents = []
    for url in sorted(grouped):
        document = dict.fromkeys(DOCUMENT_FIELDS)
        document.update(
            canonical_url=url,
            associations=grouped[url],
            status="DOWNLOAD_PENDING",
            attempts=0,
            warnings=[],
        )
        documents.append(document)
    manifest = {
        "schema_version": 1,
        "source_key": sample["source_key"],
        "source_url": sample["source_url"],
        "inputs": inputs,
        "created_at": created,
        "updated_at": created,
        "documents": documents,
        "last_run": {
            "started_at": created,
            "ended_at": None,
            "complete": False,
            "summary": dict.fromkeys(RUN_COUNTS, 0),
        },
    }
    manifest["last_run"]["summary"].update(summarize(manifest))
    validate_manifest(manifest)
    return manifest


def parse_robots(text: str, robots_url: str) -> RobotFileParser:
    agents, permissions = set(), set()
    seen_agent = False
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        key, separator, value = line.partition(":")
        key, value = key.strip().lower(), value.strip()
        if not separator or key not in {
            "user-agent",
            "allow",
            "disallow",
            "crawl-delay",
            "request-rate",
            "sitemap",
        }:
            raise DownloadError("ROBOTS_POLICY", "Unrecognized robots policy.")
        if key == "user-agent":
            if not value or value.lower() in agents:
                raise DownloadError("ROBOTS_POLICY", "Ambiguous robots user-agent groups.")
            agents.add(value.lower())
            seen_agent = True
        elif key != "sitemap" and not seen_agent:
            raise DownloadError("ROBOTS_POLICY", "Robots restriction lacks a user-agent.")
        if key in {"allow", "disallow"}:
            if any(c in value for c in "*$"):
                raise DownloadError("ROBOTS_POLICY", "Unsupported robots wildcard restriction.")
            if value:
                permissions.add(key)
        if key == "crawl-delay" and (not value.isascii() or not value.isdigit() or len(value) > 9):
            raise DownloadError("ROBOTS_POLICY", "Unsupported robots delay.")
        if key == "request-rate":
            parts = value.split("/")
            if len(parts) != 2 or not all(
                p.isascii() and p.isdigit() and len(p) <= 9 and int(p) > 0 for p in parts
            ):
                raise DownloadError("ROBOTS_POLICY", "Unsupported robots request rate.")
    if (
        permissions == {"allow", "disallow"}
        or sum(a != "*" and a in "msmeintel" for a in agents) > 1
    ):
        raise DownloadError("ROBOTS_POLICY", "Ambiguous robots precedence.")
    parser = RobotFileParser(robots_url)
    parser.parse(text.splitlines())
    return parser


class DownloadHTTP:
    """One sequential client; policy/transport state is shared only for this run."""

    def __init__(self, source_url: str, counters: dict, transport=None):
        self.source_url = source_url
        parsed = urlsplit(source_url)
        self.robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        self.counters = counters
        self.policy = None
        self.blocked = None
        self.not_before = None
        self.last_request = None
        self.delay = 1.0
        self.client = httpx.Client(
            headers={"User-Agent": USER_AGENT, "Accept-Encoding": "identity"},
            timeout=httpx.Timeout(30, connect=10),
            follow_redirects=False,
            transport=transport,
        )

    def _request(self, url: str, *, document: dict | None = None):
        if self.last_request is not None:
            time.sleep(max(0, self.delay - (time.monotonic() - self.last_request)))
        self.last_request = time.monotonic()
        if document is not None:
            self.counters["http_attempts"] += 1
            document["attempts"] += 1
        self.client.cookies.clear()
        return self.client.stream("GET", url)

    def ensure_policy(self):
        if self.blocked:
            raise self.blocked
        if self.not_before is not None and timestamp(self.not_before) > datetime.now(UTC):
            raise DownloadError(
                "RETRY_DEFERRED", "Origin Retry-After has not elapsed.", retryable=True
            )
        if self.policy is not None:
            return
        try:
            with self._request(self.robots_url) as response:
                if response.status_code in {404, 410}:
                    text = ""
                elif response.status_code == 200:
                    if response.headers.get("content-encoding", "identity").lower().strip() not in {
                        "",
                        "identity",
                    }:
                        raise DownloadError("ROBOTS_POLICY", "Unexpected encoded robots body.")
                    if (
                        response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                        != "text/plain"
                    ):
                        raise DownloadError("ROBOTS_POLICY", "Robots response is not plain text.")
                    body = bytearray()
                    started = time.monotonic()
                    for chunk in response.iter_bytes(chunk_size=raw_storage.CHUNK_SIZE):
                        if (
                            len(body) + len(chunk) > MAX_ROBOTS_BYTES
                            or time.monotonic() - started > ATTEMPT_SECONDS
                        ):
                            raise DownloadError("ROBOTS_POLICY", "Robots response exceeds limits.")
                        body.extend(chunk)
                    text = body.decode("utf-8-sig")
                else:
                    if response.status_code in RETRY_STATUSES:
                        self._retry_after(response)
                    raise DownloadError(
                        "ROBOTS_HTTP",
                        f"Robots HTTP {response.status_code}; no documents requested.",
                        retryable=response.status_code in RETRY_STATUSES,
                    )
            self.policy = parse_robots(text, self.robots_url)
            rate = self.policy.request_rate(USER_AGENT)
            self.delay = max(
                self.delay,
                self.policy.crawl_delay(USER_AGENT) or 0,
                rate.seconds / rate.requests if rate else 0,
            )
            if self.delay > 60:
                raise DownloadError("ROBOTS_POLICY", "Robots pacing exceeds this run's wait limit.")
        except (httpx.HTTPError, UnicodeError) as error:
            self.blocked = DownloadError(
                "ROBOTS_HTTP", "Robots transport/encoding failure.", retryable=True
            )
            raise self.blocked from error
        except DownloadError as error:
            self.blocked = error
            raise

    def _retry_after(self, response: httpx.Response) -> float:
        value = response.headers.get("retry-after")
        if value is None:
            return 0
        try:
            if value.isascii() and value.isdigit():
                deadline = datetime.now(UTC) + timedelta(seconds=int(value))
            else:
                deadline = parsedate_to_datetime(value)
                if deadline.tzinfo is None:
                    raise ValueError
            seconds = max(0, (deadline - datetime.now(UTC)).total_seconds())
            self.not_before = deadline.astimezone(UTC).isoformat() if seconds else None
            return seconds
        except (ValueError, TypeError, OverflowError) as error:
            raise DownloadError(
                "RETRY_DEFERRED", "Invalid Retry-After; origin deferred.", retryable=True
            ) from error

    def fetch(self, document: dict, data_dir: Path) -> tuple[str, int]:
        self.ensure_policy()
        attempted = False
        for attempt in range(MAX_ATTEMPTS):
            delay = 2**attempt
            status = None
            try:
                started = time.monotonic()

                def check_time():
                    if time.monotonic() - started > ATTEMPT_SECONDS:
                        raise DownloadError(
                            "HTTP_TIMEOUT",
                            "Document attempt elapsed limit exceeded.",
                            retryable=True,
                        )

                url, visited = document["canonical_url"], set()
                for hop in range(4):
                    url = checked_url(url, self.source_url)
                    if url in visited or not self.policy.can_fetch(USER_AGENT, url):
                        raise DownloadError("ACCESS_DENIED", "Redirect loop or robots denial.")
                    visited.add(url)
                    if not attempted:
                        self.counters["urls_attempted"] += 1
                        attempted = True
                    with self._request(url, document=document) as response:
                        check_time()
                        status = document["http_status"] = response.status_code
                        if response.is_redirect:
                            if hop == 3 or not response.headers.get("location"):
                                raise DownloadError(
                                    "REDIRECT", "Missing redirect target or hop limit reached."
                                )
                            url = canonicalize_url(response.headers["location"], url)
                            continue
                        document["final_url"] = url
                        if status != 200:
                            if status in RETRY_STATUSES:
                                try:
                                    delay = max(delay, self._retry_after(response))
                                except DownloadError as error:
                                    self.blocked = error
                                    raise
                                if delay > 60:
                                    self.blocked = DownloadError(
                                        "RETRY_DEFERRED",
                                        "Origin Retry-After exceeds this run's wait limit.",
                                        retryable=True,
                                    )
                                    raise self.blocked
                            raise DownloadError(
                                "HTTP_STATUS",
                                f"Document HTTP {status}.",
                                retryable=status in RETRY_STATUSES,
                            )
                        encoding = (
                            response.headers.get("content-encoding", "identity").lower().strip()
                        )
                        if encoding not in {"", "identity"}:
                            raise DownloadError(
                                "CONTENT_ENCODING", "Unexpected encoded document body."
                            )
                        mime = (
                            response.headers.get("content-type", "")
                            .split(";", 1)[0]
                            .strip()
                            .lower()
                        )
                        document["content_type"] = mime or None
                        if mime not in {"", "application/pdf", "application/octet-stream"}:
                            raise DownloadError(
                                "INVALID_MIME", "Response explicitly declares a non-PDF MIME type."
                            )
                        document["warnings"] = (
                            []
                            if mime == "application/pdf"
                            else ["MIME absent/generic; PDF byte checks required."]
                        )
                        length = response.headers.get("content-length")
                        if length is not None:
                            if not length.isascii() or not length.isdigit():
                                raise DownloadError(
                                    "LENGTH_MISMATCH", "Invalid/conflicting Content-Length."
                                )
                            if len(length.lstrip("0")) > 9:
                                raise DownloadError(
                                    "SIZE_LIMIT", "Declared PDF exceeds the size limit."
                                )
                            length = int(length.lstrip("0") or "0")
                            if length > raw_storage.MAX_PDF_BYTES:
                                raise DownloadError(
                                    "SIZE_LIMIT", "Declared PDF exceeds the 50 MiB limit."
                                )
                        return raw_storage.write_pdf(
                            data_dir,
                            document["staging_path"],
                            response.iter_raw(chunk_size=raw_storage.CHUNK_SIZE),
                            length=length,
                            check_time=check_time,
                        )
                raise DownloadError("REDIRECT", "Redirect did not reach a document.")
            except httpx.TimeoutException:
                error = DownloadError("HTTP_TIMEOUT", "Document HTTP timeout.", retryable=True)
            except httpx.InvalidURL:
                error = DownloadError("UNSAFE_URL", "HTTP client rejected the document URL.")
            except httpx.TransportError:
                error = DownloadError(
                    "HTTP_TRANSPORT", "Document HTTP transport failure.", retryable=True
                )
            except DownloadError as caught:
                error = caught
            raw_storage.discard_staging(data_dir, document["staging_path"])
            document["retry_not_before"] = self.not_before
            if self.blocked or not error.retryable or attempt == MAX_ATTEMPTS - 1:
                if status == 429:
                    self.blocked = error
                raise error
            time.sleep(delay)
        raise AssertionError("Unreachable retry state")


def _failure(document: dict, error: ArtifactError | DownloadError) -> None:
    document["status"] = "DOWNLOAD_FAILED"
    document["error"] = {
        "category": error.category,
        "message": str(error),
        "at": now(),
        "retryable": getattr(error, "retryable", False),
    }


def execute(
    manifest: dict, path: Path, data_dir: Path, *, retry_failed=False, transport=None
) -> dict:
    validate_manifest(manifest)
    _protect_output(path, manifest["inputs"], data_dir)
    raw_storage.safe_path(data_dir, raw_storage.storage_path("0" * 64))
    raw_storage.safe_path(data_dir, "raw/.tmp/msmeintel-" + "0" * 32 + ".part")
    for document in manifest["documents"]:
        for field in ("storage_path", "staging_path"):
            if document[field] is not None:
                raw_storage.safe_path(data_dir, document[field])
    # ponytail: one local writer, matching M01; add locking only if concurrent runs are required.
    counts = dict.fromkeys(RUN_COUNTS, 0)
    manifest["last_run"] = {
        "started_at": now(),
        "ended_at": None,
        "complete": False,
        "summary": counts,
    }
    checkpoint(path, manifest)
    http = DownloadHTTP(manifest["source_url"], counts, transport)
    deadlines = [d["retry_not_before"] for d in manifest["documents"] if d["retry_not_before"]]
    http.not_before = max(deadlines, key=timestamp) if deadlines else None
    try:
        for document in manifest["documents"]:
            try:
                if document["status"] == "DOWNLOADED":
                    try:
                        raw_storage.verify_file(
                            data_dir,
                            document["storage_path"],
                            document["sha256"],
                            document["byte_count"],
                        )
                    except FileNotFoundError:
                        document["status"] = "DOWNLOAD_PENDING"
                    else:
                        document["verified_at"] = now()
                        counts["skipped"] += 1
                        checkpoint(path, manifest)
                        continue
                if document["status"] == "STAGED":
                    target = raw_storage.safe_path(data_dir, document["storage_path"])
                    staging = raw_storage.safe_path(data_dir, document["staging_path"])
                    if target.exists():
                        raw_storage.verify_file(
                            data_dir,
                            document["storage_path"],
                            document["sha256"],
                            document["byte_count"],
                        )
                        raw_storage.discard_staging(data_dir, document["staging_path"])
                    elif staging.exists():
                        counts["new_files"] += raw_storage.publish(
                            data_dir,
                            document["staging_path"],
                            document["sha256"],
                            document["byte_count"],
                        )
                    else:
                        document["status"] = "DOWNLOAD_PENDING"
                    if document["status"] == "STAGED":
                        document.update(
                            status="DOWNLOADED", staging_path=None, verified_at=now(), error=None
                        )
                        counts["recovered"] += 1
                        checkpoint(path, manifest)
                        continue
                if document["status"] == "DOWNLOAD_FAILED":
                    if not retry_failed or document["error"]["category"] in {
                        "CORRUPT_FILE",
                        "HASH_CHANGED",
                        "INVALID_PATH",
                    }:
                        continue
                elif retry_failed:
                    continue
                raw_storage.discard_staging(data_dir, document["staging_path"])
                document.update(
                    status="DOWNLOAD_PENDING",
                    error=None,
                    staging_path=raw_storage.new_staging_path(),
                )
                checkpoint(path, manifest)
                expected_hash = document["sha256"]
                digest, size = http.fetch(document, data_dir)
                if expected_hash is not None and digest != expected_hash:
                    raise ArtifactError(
                        "HASH_CHANGED", "Refetched bytes differ from the saved immutable identity."
                    )
                document.update(
                    status="STAGED",
                    sha256=digest,
                    byte_count=size,
                    storage_path=raw_storage.storage_path(digest),
                    downloaded_at=document["downloaded_at"] or now(),
                    retry_not_before=None,
                )
                checkpoint(path, manifest)
                created = raw_storage.publish(data_dir, document["staging_path"], digest, size)
                counts["new_files"] += created
                counts["content_deduplicated"] += not created
                counts["downloaded"] += 1
                document.update(
                    status="DOWNLOADED", staging_path=None, verified_at=now(), error=None
                )
            except (ArtifactError, DownloadError, DiscoveryError) as error:
                raw_storage.discard_staging(data_dir, document["staging_path"])
                document["staging_path"] = None
                document["retry_not_before"] = http.not_before
                if isinstance(error, DiscoveryError):
                    error = DownloadError("UNSAFE_URL", "Invalid redirect/source URL.")
                _failure(document, error)
            checkpoint(path, manifest)
        manifest["last_run"].update(complete=True, ended_at=now())
        checkpoint(path, manifest)
    finally:
        http.client.close()
    return manifest


def verify(manifest: dict, data_dir: Path) -> dict:
    validate_manifest(manifest)
    problems = []
    verified = set()
    for document in manifest["documents"]:
        if document["status"] in {"DOWNLOAD_PENDING", "STAGED"}:
            problems.append({"url": document["canonical_url"], "reason": "Unfinished acquisition."})
        if document["sha256"] is not None:
            try:
                raw_storage.verify_file(
                    data_dir, document["storage_path"], document["sha256"], document["byte_count"]
                )
                verified.add(document["sha256"])
            except (ArtifactError, OSError):
                problems.append(
                    {"url": document["canonical_url"], "reason": "Missing/corrupt/unsafe artifact."}
                )
    return {"verified_hashes": len(verified), "problems": problems, **summarize(manifest)}


def report(manifest: dict) -> dict:
    return {
        "summary": manifest["last_run"]["summary"],
        "failures": [
            {
                "url": d["canonical_url"],
                "source_project_ids": [a["external_project_id"] for a in d["associations"]],
                "error": d["error"],
            }
            for d in manifest["documents"]
            if d["status"] == "DOWNLOAD_FAILED"
        ],
    }
