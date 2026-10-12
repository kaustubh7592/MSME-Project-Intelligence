"""Authentic PMEGP excerpts plus explicitly synthetic mutations/algorithm inputs; all offline."""

import copy
import json
import socket
from dataclasses import replace
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from typer.testing import CliRunner

from msmeintel import cli, discovery
from msmeintel.sources import pmegp
from msmeintel.sources.base import (
    DiscoveryError,
    DocumentCandidate,
    ProjectCandidate,
    canonicalize_url,
)

NOW = "2026-10-08T00:00:00+00:00"
LATER = "2026-10-09T00:00:00+00:00"
SYNTHETIC_URL = "https://example.test/listing"
runner = CliRunner()


def projects(count=32):
    """Entirely synthetic algorithm inputs, never a real-source corpus/sample."""
    return [
        ProjectCandidate(
            title=f" Synthetic project {index} ",
            listing_url=SYNTHETIC_URL,
            external_project_id=str(index),
            category_hint=f"Category {index % 4}",
            raw_metadata={"Total Project Cost": f"synthetic {index}.00"},
            documents=(DocumentCandidate(f"/docs/{index}.pdf", SYNTHETIC_URL, "Profile", "PDF"),),
        )
        for index in range(count)
    ]


def manifest(items=None, **kwargs):
    return discovery.build_manifest(
        projects() if items is None else items,
        source_key="pmegp",
        source_url=SYNTHETIC_URL,
        observed_at=kwargs.pop("observed_at", NOW),
        **kwargs,
    )[0]


@pytest.mark.parametrize(
    ("href", "base", "expected"),
    [
        (
            "../Some File.pdf#page=2",
            "https://EXAMPLE.test:443/a/list",
            "https://example.test/Some%20File.pdf",
        ),
        (
            "HTTP://EXAMPLE.test:80/A%2FB/?z=2&a=1&a=3#x",
            None,
            "http://example.test/A%2FB/?z=2&a=1&a=3",
        ),
        ("https://EXAMPLE.test:8443/Case/", None, "https://example.test:8443/Case/"),
        ("/already%20encoded.pdf", SYNTHETIC_URL, "https://example.test/already%20encoded.pdf"),
    ],
)
def test_canonical_urls(href, base, expected):
    assert canonicalize_url(href, base) == expected
    assert canonicalize_url(expected) == expected


@pytest.mark.parametrize(
    "href",
    [
        "",
        " ",
        "#x",
        "javascript:go()",
        "mailto:x@y",
        "ftp://x/file",
        "https://u:password@example.test/a",
        "https://x:bad/a",
        "https://bad host/a",
        "https://x/\nfile",
        "https://x\\y/a",
    ],
)
def test_unsafe_or_missing_links(href):
    with pytest.raises(DiscoveryError):
        canonicalize_url(href, SYNTHETIC_URL)


def test_original_links_raw_cost_and_missing_metadata():
    item = replace(
        projects(1)[0],
        category_hint=None,
        external_project_id=None,
        documents=(
            DocumentCandidate("/docs/a file.pdf#one", SYNTHETIC_URL),
            DocumentCandidate("https://EXAMPLE.test:443/docs/a%20file.pdf#two", SYNTHETIC_URL),
        ),
    )
    record = manifest([item])["projects"][0]
    assert record["raw_title"] == item.title
    assert record["title"] == "Synthetic project 0"
    assert record["raw_metadata"] == item.raw_metadata
    assert record["category_hint"] is None and record["external_project_id"] is None
    assert record["page_url"] is None
    assert len(record["documents"]) == 1
    doc = record["documents"][0]
    assert len(doc["original_variants"]) == 1
    assert {value["original_href"] for value in [doc, *doc["original_variants"]]} == {
        link.original_href for link in item.documents
    }


def test_missing_document_retained_missing_name_fails():
    result = manifest([replace(projects(1)[0], documents=())])
    assert result["discovered_total"] == 1
    assert result["projects"][0]["discovery_status"] == "MISSING_DOCUMENT_LINK"
    assert result["issues"][0]["reason"] == "MISSING_DOCUMENT_LINK"
    with pytest.raises(DiscoveryError, match="nonempty"):
        manifest([replace(projects(1)[0], title=" ")])
    with pytest.raises(DiscoveryError):
        manifest(
            [replace(projects(1)[0], documents=(DocumentCandidate("javascript:x", SYNTHETIC_URL),))]
        )


def test_identity_duplicates_conflicts_and_shared_document():
    items = projects(2)
    items[1] = replace(items[1], title=items[0].title, documents=items[0].documents)
    result = manifest(items * 2)
    assert result["discovered_total"] == 2
    assert "document_associations=2 unique_document_urls=1" in discovery.summary(result)
    with pytest.raises(DiscoveryError, match="Conflicting"):
        manifest([items[0], replace(items[0], title="Different")])
    fallback = [replace(item, external_project_id=None) for item in projects(2)]
    fallback[1] = replace(fallback[1], title=fallback[0].title)
    assert manifest(fallback)["discovered_total"] == 2
    with pytest.raises(DiscoveryError, match="Conflicting"):
        manifest(
            [
                replace(item, external_project_id=None, page_url="https://example.test/detail")
                for item in items
            ]
        )


def test_dynamic_counts_rerun_and_temporal_changes():
    before = manifest(projects(3))
    items = projects(5)[1:]
    items[0] = replace(items[0], raw_metadata={"Total Project Cost": "synthetic changed"})
    after, changes = discovery.build_manifest(
        items + items,
        source_key="pmegp",
        source_url=SYNTHETIC_URL,
        previous=before,
        observed_at=LATER,
    )
    assert before["discovered_total"] == 3
    assert after["discovered_total"] == 4
    assert {key: len(value) for key, value in changes.items()} == {
        "added": 2,
        "changed": 1,
        "no_longer_seen": 1,
    }
    old_keys = {item["record_key"] for item in before["projects"]}
    for record in after["projects"]:
        assert record["first_seen_at"] == (NOW if record["record_key"] in old_keys else LATER)
        assert record["last_seen_at"] == LATER
    with pytest.raises(DiscoveryError, match="empty discovery"):
        manifest([])


def test_duplicate_original_variants_merge_independently_of_order():
    item = projects(1)[0]
    variants = [
        replace(item, listing_url=listing, documents=(DocumentCandidate(href, listing),))
        for listing, href in (
            (SYNTHETIC_URL, "/docs/0.pdf#one"),
            (SYNTHETIC_URL + "?page=2", "https://EXAMPLE.test:443/docs/0.pdf#two"),
            (SYNTHETIC_URL + "?page=3", "/docs/0.pdf#three"),
        )
    ]
    first = manifest(variants)
    assert discovery.json_text(first) == discovery.json_text(manifest(list(reversed(variants))))
    record = first["projects"][0]
    assert len(record["documents"][0]["original_variants"]) == 2
    assert discovery.link_pattern(record) == "listing-single"


def test_atomic_roundtrip_failure_and_invalid_old_json(tmp_path, monkeypatch):
    path = tmp_path / "snapshot.json"
    before = manifest(projects(3))
    discovery.write_manifest(path, before)
    original = path.read_bytes()
    assert discovery.read_manifest(path) == before
    after = manifest(projects(4), previous=before, observed_at=LATER)

    def failed_replace(*args):
        raise OSError("simulated interrupted replace")

    monkeypatch.setattr(discovery.os, "replace", failed_replace)
    with pytest.raises(OSError):
        discovery.write_manifest(path, after)
    assert path.read_bytes() == original
    assert not list(tmp_path.glob("*.tmp"))
    path.write_text("invalid JSON", encoding="utf-8")
    with pytest.raises(DiscoveryError):
        discovery.write_manifest(path, after)
    assert path.read_text(encoding="utf-8") == "invalid JSON"


@pytest.mark.parametrize(
    "damage",
    [
        lambda value: value.update(discovered_total=999),
        lambda value: value.update(complete=False),
        lambda value: value["projects"].append(value["projects"][0]),
        lambda value: value["projects"][0].update(record_key="invented"),
        lambda value: value["projects"][0]["documents"][0].update(
            canonical_url="https://elsewhere.test/a"
        ),
        lambda value: value["projects"][0].update(first_seen_at=LATER),
        lambda value: value.update(projects=None),
    ],
)
def test_manifest_validation(damage):
    value = manifest(projects(2))
    damage(value)
    with pytest.raises(DiscoveryError):
        discovery.validate_manifest(value)


def test_ambiguous_json_rejected(tmp_path):
    path = tmp_path / "ambiguous.json"
    path.write_text('{"schema_version":1,"schema_version":2}', encoding="utf-8")
    with pytest.raises(DiscoveryError):
        discovery.read_manifest(path)


def test_filters_cannot_replace_full_or_lose_selected_keys(tmp_path):
    full = manifest()
    path = tmp_path / "full.json"
    discovery.write_manifest(path, full)
    limited = discovery.filter_manifest(full, limit=3)
    assert limited["discovered_total"] == len(full["projects"])
    assert len(limited["projects"]) == 3 and not limited["complete"]
    with pytest.raises(DiscoveryError, match="scope"):
        discovery.write_manifest(path, limited)
    with pytest.raises(DiscoveryError, match="unfiltered"):
        discovery.select_sample(limited, 2)
    sample = discovery.select_sample(full, 20)
    filtered = discovery.filter_manifest(full, sample=sample)
    assert len(filtered["projects"]) == 20 and filtered["scope"] == "sample"
    with pytest.raises(DiscoveryError, match="missing"):
        discovery.filter_manifest(manifest(projects(2)), sample=sample)


def test_representative_twenty_is_stable_not_prefix():
    items = projects(48)
    for index in range(0, len(items), 3):
        items[index] = replace(
            items[index],
            page_url="https://example.test/detail",
            documents=items[index].documents
            + (DocumentCandidate(f"/extra/{index}.pdf", "https://example.test/detail"),),
        )
    full = manifest(items)
    sample = discovery.select_sample(full, 20)
    assert len(sample["projects"]) == len({item["record_key"] for item in sample["projects"]}) == 20
    assert len({item["category_hint"] for item in sample["projects"]}) == 4
    assert len({discovery.link_pattern(item) for item in sample["projects"]}) == 2
    assert sample["projects"] != [discovery._stable(item) for item in full["projects"][:20]]
    assert discovery.json_text(sample) == discovery.json_text(
        discovery.select_sample(manifest(list(reversed(items)) * 2, observed_at=LATER), 20)
    )
    assert "first_seen_at" not in discovery.json_text(sample)
    for category in {item.category_hint for item in items}:
        assert sum(item["category_hint"] == category for item in sample["projects"]) == 5


def test_sampling_uniform_missing_categories_small_buckets_and_many_categories():
    uniform = manifest([replace(item, category_hint=None) for item in projects(40)])
    sample = discovery.select_sample(uniform, 20)
    assert sample["projects"][0]["record_key"] == uniform["projects"][0]["record_key"]
    assert sample["projects"][-1]["record_key"] == uniform["projects"][-1]["record_key"]
    assert "No categories" in discovery.sample_coverage(uniform, sample)
    items = projects(30)
    items = [
        replace(item, category_hint="Singleton" if i == 0 else "Rest")
        for i, item in enumerate(items)
    ]
    sample = discovery.select_sample(manifest(items), 20)
    assert sum(item["category_hint"] == "Singleton" for item in sample["projects"]) == 1
    many = manifest(
        [replace(item, category_hint=f"C{i:02}") for i, item in enumerate(projects(40))]
    )
    sample = discovery.select_sample(many, 20)
    assert len({item["category_hint"] for item in sample["projects"]}) == 20
    assert {"C00", "C39"} <= {item["category_hint"] for item in sample["projects"]}
    assert "categories=20/40" in discovery.sample_coverage(many, sample)
    assert len(discovery.select_sample(uniform, 1)["projects"]) == 1
    for count in (0, -1, 41):
        with pytest.raises(DiscoveryError):
            discovery.select_sample(uniform, count)


def test_sample_write_requires_explicit_replacement(tmp_path):
    path = tmp_path / "sample.json"
    first = discovery.select_sample(manifest(), 20)
    assert discovery.write_sample(path, first)
    before = path.read_bytes()
    assert not discovery.write_sample(path, copy.deepcopy(first))
    assert path.read_bytes() == before
    changed = discovery.select_sample(manifest(projects(40)), 20)
    with pytest.raises(DiscoveryError, match="--replace"):
        discovery.write_sample(path, changed)
    assert path.read_bytes() == before
    assert discovery.write_sample(path, changed, replace=True)
    assert discovery.read_sample(path) == changed


class UnreadBody(httpx.SyncByteStream):
    def __iter__(self):
        raise AssertionError("Forbidden response body was consumed")


@pytest.fixture
def http_adapter(monkeypatch):
    """Controlled transport/clock; no PMEGP page structure is represented here."""
    monkeypatch.setattr(pmegp.time, "monotonic", lambda: 0.0)
    sleeps = []
    monkeypatch.setattr(pmegp.time, "sleep", sleeps.append)
    opened = []

    def factory(handler):
        def record(request):
            opened.append(str(request.url))
            assert request.headers["user-agent"] == pmegp.USER_AGENT
            assert request.extensions["timeout"]["connect"] == 10
            return handler(request)

        return pmegp.PMEGPAdapter(transport=httpx.MockTransport(record))

    return factory, opened, sleeps


def test_robots_allow_pacing_and_cached_policy(http_adapter):
    factory, opened, sleeps = http_adapter

    def response(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(
                200,
                headers={"content-type": "text/plain"},
                text="User-agent: *\nAllow: /\nCrawl-delay: 2\nRequest-rate: 1/3",
            )
        return httpx.Response(
            200, headers={"content-type": "text/html"}, text="synthetic transport body"
        )

    with factory(response) as adapter:
        assert adapter.fetch_listing() == "synthetic transport body"
        adapter.fetch_listing()
    assert opened == [pmegp.ROBOTS_URL, pmegp.SOURCE_URL, pmegp.SOURCE_URL]
    assert sleeps == [3, 3]


@pytest.mark.parametrize("status", [404, 410])
def test_missing_robots_and_unrecognized_page(http_adapter, status):
    factory, opened, sleeps = http_adapter

    def response(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(status, stream=UnreadBody())
        return httpx.Response(200, headers={"content-type": "text/html"}, text="not authentic HTML")

    with factory(response) as adapter, pytest.raises(DiscoveryError, match="listing structure"):
        adapter.discover_projects()
    assert opened == [pmegp.ROBOTS_URL, pmegp.SOURCE_URL]
    assert sleeps == [1]


@pytest.mark.parametrize(
    "policy",
    [
        "User-agent: *\nDisallow: /",
        "User-agent: *\nDisallow: /*secret",
        "User-agent: *\nDisallow: /secret$",
        "User-agent: *\nCrawl-delay: 1.5",
        "User-agent: *\nRequest-rate: 0/10",
        "Disallow: /",
        "<html>challenge</html>",
        "User-agent: *\nVisit-time: 0000-0100",
        "User-agent: *\nAllow: /\nDisallow: /pmegp/",
        "User-agent: MSMEIntel\nAllow: /\n\nUser-agent: MSMEIntel\nDisallow: /",
        "User-agent: *\nAllow: /\n\nUser-agent: *\nDisallow: /",
    ],
)
def test_robots_denial_or_unsupported_policy(http_adapter, policy):
    factory, opened, _ = http_adapter
    with factory(
        lambda request: httpx.Response(200, headers={"content-type": "text/plain"}, text=policy)
    ) as adapter:
        with pytest.raises(DiscoveryError):
            adapter.fetch_listing()
    assert opened == [pmegp.ROBOTS_URL]


@pytest.mark.parametrize("stage", ["robots", "listing"])
@pytest.mark.parametrize("status", [401, 403, 429, 500, 503])
def test_http_errors_fail_closed(http_adapter, stage, status):
    factory, opened, _ = http_adapter

    def response(request):
        if stage == "listing" and request.url.path == "/robots.txt":
            return httpx.Response(404, stream=UnreadBody())
        return httpx.Response(status, stream=UnreadBody())

    with factory(response) as adapter, pytest.raises(DiscoveryError, match=f"HTTP {status}"):
        adapter.fetch_listing()
    assert len(opened) == (1 if stage == "robots" else 2)


@pytest.mark.parametrize(
    "error_class", [httpx.ConnectTimeout, httpx.ReadTimeout, httpx.ConnectError]
)
def test_transport_failures_are_categorized(http_adapter, error_class):
    factory, _, _ = http_adapter

    def response(request):
        raise error_class("secret proxy details", request=request)

    with factory(response) as adapter, pytest.raises(DiscoveryError) as error:
        adapter.fetch_listing()
    assert "secret" not in str(error.value)
    assert "timeout" in str(error.value) or "transport failure" in str(error.value)


@pytest.mark.parametrize(
    "destination", ["https://other.test/list", "/document.pdf", "http://pmegp.msme.gov.in/"]
)
def test_redirects_are_not_followed(http_adapter, destination):
    factory, opened, _ = http_adapter
    with factory(
        lambda request: httpx.Response(302, headers={"location": destination}, stream=UnreadBody())
    ) as adapter:
        with pytest.raises(DiscoveryError, match="redirect"):
            adapter.fetch_listing()
    assert opened == [pmegp.ROBOTS_URL]


@pytest.mark.parametrize("content_type", ["application/pdf", "application/octet-stream", ""])
def test_unexpected_mime_body_is_unread_and_no_pdf_request(http_adapter, content_type):
    factory, opened, _ = http_adapter

    def response(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404, stream=UnreadBody())
        return httpx.Response(200, headers={"content-type": content_type}, stream=UnreadBody())

    with factory(response) as adapter:
        with pytest.raises(DiscoveryError, match="MIME"):
            adapter.fetch_listing()
        for url in (
            "https://other.test/",
            "https://pmegp.msme.gov.in/Home/DownloadDocument?fileName=document.pdf",
            pmegp.SOURCE_URL + "?unverified=1",
        ):
            with pytest.raises(DiscoveryError, match="origin/route"):
                adapter._get(url)
    assert opened == [pmegp.ROBOTS_URL, pmegp.SOURCE_URL]


def test_html_size_cap(http_adapter, monkeypatch):
    factory, _, _ = http_adapter
    monkeypatch.setattr(pmegp, "MAX_HTML_BYTES", 10)

    def response(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404, stream=UnreadBody())
        return httpx.Response(200, headers={"content-type": "text/html"}, content=b"x" * 11)

    with factory(response) as adapter, pytest.raises(DiscoveryError, match="limit"):
        adapter.fetch_listing()


@pytest.mark.parametrize("option", [0, -1, float("nan"), float("inf")])
def test_invalid_http_limits(option):
    for kwargs in ({"timeout": option}, {"request_delay": option}):
        with pytest.raises(DiscoveryError, match="positive"):
            pmegp.PMEGPAdapter(**kwargs)


def test_socket_and_dns_guard():
    with pytest.raises(AssertionError, match="forbidden"):
        socket.getaddrinfo("example.test", 443)
    with socket.socket() as connection, pytest.raises(AssertionError, match="forbidden"):
        connection.connect(("127.0.0.1", 1))


def test_cli_offline_workflow_and_protected_outputs(tmp_path, monkeypatch):
    monkeypatch.setenv("MSMEINTEL_DATA_DIR", str(tmp_path))
    # Explicitly mock the adapter boundary, NOT a fabricated PMEGP parser.
    monkeypatch.setattr(pmegp.PMEGPAdapter, "source_url", SYNTHETIC_URL)
    monkeypatch.setattr(pmegp.PMEGPAdapter, "discover_projects", lambda self: projects())

    def no_http(*args, **kwargs):
        raise AssertionError("Unexpected HTTP request")

    monkeypatch.setattr(httpx.Client, "send", no_http)
    full = tmp_path / "discovery" / "pmegp.json"
    sample_path = tmp_path / "synthetic-sample.json"
    assert "not discovered" in runner.invoke(cli.app, ["source", "list"]).stdout
    for command in (["--help"], ["source", "--help"], ["source", "discover"]):
        result = runner.invoke(cli.app, command)
        assert result.exit_code == 0, result.output
    first = discovery.read_manifest(full)
    result = runner.invoke(cli.app, ["source", "list", "--limit", "1"])
    assert result.exit_code == 0 and "saved_projects=32" in result.stdout
    assert "Total Project Cost" in result.stdout
    for _ in range(2):
        result = runner.invoke(
            cli.app, ["source", "sample", "--count", "20", "--output", str(sample_path)]
        )
        assert result.exit_code == 0, result.output
    assert "Unchanged" in result.stdout
    result = runner.invoke(cli.app, ["source", "discover"])
    assert result.exit_code == 0 and "added=0 changed=0 no_longer_seen=0" in result.stdout
    second = discovery.read_manifest(full)
    assert [p["first_seen_at"] for p in first["projects"]] == [
        p["first_seen_at"] for p in second["projects"]
    ]
    original = full.read_bytes()
    for args in (
        ["--limit", "3"],
        ["--limit", "3", "--output", str(full)],
        ["--limit", "3", "--sample", str(sample_path)],
    ):
        assert runner.invoke(cli.app, ["source", "discover", *args]).exit_code == 2
        assert full.read_bytes() == original
    for args, expected in ((["--limit", "3"], 3), (["--sample", str(sample_path)], 20)):
        path = tmp_path / f"filtered-{expected}.json"
        result = runner.invoke(cli.app, ["source", "discover", *args, "--output", str(path)])
        assert result.exit_code == 0, result.output
        assert len(discovery.read_manifest(path)["projects"]) == expected

    def failing(self):
        yield projects(1)[0]
        raise DiscoveryError("source failure after partial results")

    monkeypatch.setattr(pmegp.PMEGPAdapter, "discover_projects", failing)
    assert runner.invoke(cli.app, ["source", "discover"]).exit_code == 2
    assert full.read_bytes() == original
    assert runner.invoke(cli.app, ["source", "list", "--source", "../x"]).exit_code == 2


def test_cli_http_failure_preserves_manifest(tmp_path, monkeypatch):
    monkeypatch.setenv("MSMEINTEL_DATA_DIR", str(tmp_path))
    path = tmp_path / "discovery" / "pmegp.json"
    value = discovery.build_manifest(projects(2), source_key="pmegp", source_url=pmegp.SOURCE_URL)[
        0
    ]
    discovery.write_manifest(path, value)
    original = path.read_bytes()

    def failure(self):
        raise DiscoveryError("Source HTTP timeout")

    monkeypatch.setattr(pmegp.PMEGPAdapter, "fetch_listing", failure)
    for command in ("discover", "smoke"):
        result = runner.invoke(cli.app, ["source", command])
        assert result.exit_code == 2 and "timeout" in result.stderr
        assert path.read_bytes() == original


def test_unrecognized_page_is_not_an_empty_success():
    with pytest.raises(DiscoveryError, match="listing structure"):
        pmegp.parse_listing("<html>synthetic transport envelope</html>", pmegp.SOURCE_URL)


@pytest.fixture
def captured_responses():
    folder = Path(__file__).parent / "fixtures" / "pmegp"
    return (
        (folder / "listing.html").read_text(encoding="utf-8"),
        (folder / "project_documents.json").read_text(encoding="utf-8"),
    )


def test_authentic_shell_and_project_observations(captured_responses):
    html, body = captured_responses
    assert pmegp.parse_listing(html, pmegp.SOURCE_URL) is None  # no server-rendered rows
    records = pmegp.parse_projects(body)
    assert len(records) == len(json.loads(body)["data"])
    by_id = {record.external_project_id: record for record in records}
    first = by_id["1"]
    assert first.title == "3 Ply Mask ( Samadhan Projects )"
    assert first.category_hint == "Samadhan Projects"
    assert first.raw_metadata["ProjectCost"] == "180500.0000"
    assert first.normalized_metadata == {"project_cost_inr": "180500"}
    assert first.raw_metadata["IsActive"] is False  # present in the public list: do not filter
    assert first.raw_metadata["ModifyOn"] == "/Date(1738674106220)/"
    assert by_id["2"].raw_metadata["ModifyOn"] is None
    assert by_id["4"].category_hint == "RURAL ENGG. AND BIO-TECH INDUSTRY"
    assert by_id["354"].raw_metadata["ProjectCost"] == "0.0000"
    assert by_id["354"].normalized_metadata["project_cost_inr"] == "0"
    assert (
        len({record.category_hint for record in records}) == 9
    )  # captured excerpt, not a live total
    for record in records:
        doc = record.documents[0]
        query = parse_qs(urlsplit(doc.original_href).query)
        assert query == {"fileName": [record.raw_metadata["DocPath"]]}
        assert urlsplit(doc.original_href).path == "/Home/DownloadDocument"
        assert doc.found_on_url == pmegp.SOURCE_URL
        assert record.page_url is None
    assert "%26" in by_id["354"].documents[0].original_href


@pytest.mark.parametrize("count", [1, 5, 12])
def test_public_endpoint_is_one_dynamic_unpaginated_get(captured_responses, http_adapter, count):
    html, body = captured_responses
    value = json.loads(body)
    value["data"] = value["data"][:count]  # explicit synthetic population mutation
    factory, opened, sleeps = http_adapter

    def respond(request):
        assert request.method == "GET" and request.content == b"" and not request.url.query
        if str(request.url) == pmegp.ROBOTS_URL:
            return httpx.Response(404, stream=UnreadBody())
        if str(request.url) == pmegp.SOURCE_URL:
            return httpx.Response(200, headers={"content-type": "text/html"}, text=html)
        assert str(request.url) == pmegp.PROJECTS_URL
        assert request.headers["content-type"] == "application/json; charset=utf-8"
        return httpx.Response(200, json=value)

    with factory(respond) as adapter:
        result, _ = discovery.build_manifest(
            adapter.discover_projects(), source_key="pmegp", source_url=pmegp.SOURCE_URL
        )
    assert result["discovered_total"] == count
    assert opened == [pmegp.ROBOTS_URL, pmegp.SOURCE_URL, pmegp.PROJECTS_URL]
    assert sleeps == [1, 1]


@pytest.mark.parametrize(
    "body",
    [
        "not JSON",
        "[]",
        '{"success":false,"data":[]}',
        '{"success":true,"data":[]}',
        '{"success":1,"data":[{}]}',
        '{"success":true,"data":{}}',
        '{"success":true,"data":[{}],"nextPage":2}',
        '{"success":true,"success":true,"data":[]}',
        '{"success":true,"data":[{"PSRID":1,"ProjectName":"x","ProjectCost":NaN}]}',
    ],
)
def test_api_error_or_changed_envelope_is_not_complete(body):
    with pytest.raises(DiscoveryError):
        pmegp.parse_projects(body)


@pytest.mark.parametrize(
    "changes",
    [
        {"PSRID": None},
        {"PSRID": True},
        {"PSRID": "1"},
        {"PSRID": 0},
        {"ProjectName": None},
        {"ProjectName": "  "},
        {"Extra": {}},
        {"DocPath": "javascript:alert(1)"},
        {"DocPath": "Documents/ProjectSampleReport/../secret"},
    ],
)
def test_malformed_api_row_does_not_silently_reduce_total(captured_responses, changes):
    value = json.loads(captured_responses[1])
    value["data"][0].update(changes)
    with pytest.raises(DiscoveryError):
        pmegp.parse_projects(json.dumps(value))


def test_optional_metadata_and_unambiguous_cost_only(captured_responses):
    value = json.loads(captured_responses[1])
    value["data"] = [value["data"][0]]
    row = value["data"][0]
    row.update(
        ProjectName="  Exact  Name (product detail)  ",
        ProjectCost=None,
        DocPath=None,
        AdditionalLabel="observed additional value",
        AdditionalMissing=None,
    )
    project = pmegp.parse_projects(json.dumps(value))[0]
    assert project.title == row["ProjectName"] and project.category_hint is None
    assert project.normalized_metadata == {} and project.raw_metadata["ProjectCost"] is None
    assert project.raw_metadata["AdditionalLabel"] == "observed additional value"
    assert project.raw_metadata["AdditionalMissing"] is None
    result = manifest([project])
    assert result["projects"][0]["raw_title"] == row["ProjectName"]
    assert result["projects"][0]["discovery_status"] == "MISSING_DOCUMENT_LINK"
    for cost in ("unknown", "1,80,500", True):
        row["ProjectCost"] = cost
        project = pmegp.parse_projects(json.dumps(value))[0]
        assert project.raw_metadata["ProjectCost"] == cost
        assert project.normalized_metadata == {}
    row["ProjectName"] = "Synthetic name (   )"
    assert pmegp.parse_projects(json.dumps(value))[0].category_hint is None


def test_decimal_cost_no_rounding_and_bounded_expansion():
    prefix = '{"success":true,"data":[{"PSRID":1,"ProjectName":"Synthetic","ProjectCost":'
    exact = pmegp.parse_projects(prefix + "9007199254740993.123400}]}")[0]
    assert exact.raw_metadata["ProjectCost"] == "9007199254740993.123400"
    assert exact.normalized_metadata["project_cost_inr"] == "9007199254740993.1234"
    extreme = pmegp.parse_projects(prefix + "1e1000000}]}")[0]
    assert extreme.raw_metadata["ProjectCost"] == "1E+1000000"
    assert extreme.normalized_metadata == {}


def test_api_duplicate_psrid_and_conflict(captured_responses):
    value = json.loads(captured_responses[1])
    original = value["data"][0]
    value["data"] = [original, copy.deepcopy(original)]
    assert manifest(pmegp.parse_projects(json.dumps(value)))["discovered_total"] == 1
    value["data"][1]["ProjectCost"] += 1
    with pytest.raises(DiscoveryError, match="Conflicting"):
        manifest(pmegp.parse_projects(json.dumps(value)))


@pytest.mark.parametrize("failure", ["denial", "pdf", "timeout", "http", "invalid-json"])
def test_api_failures_preserve_prior_snapshot(
    captured_responses, http_adapter, tmp_path, monkeypatch, failure
):
    html, body = captured_responses
    factory, opened, _ = http_adapter
    monkeypatch.setenv("MSMEINTEL_DATA_DIR", str(tmp_path))
    path = tmp_path / "discovery" / "pmegp.json"
    previous, _ = discovery.build_manifest(
        pmegp.parse_projects(body), source_key="pmegp", source_url=pmegp.SOURCE_URL, observed_at=NOW
    )
    discovery.write_manifest(path, previous)
    saved = path.read_bytes()

    def respond(request):
        if str(request.url) == pmegp.ROBOTS_URL:
            if failure == "denial":
                return httpx.Response(
                    200,
                    headers={"content-type": "text/plain"},
                    text="User-agent: *\nDisallow: /Home/GetAllProjectDocuments",
                )
            return httpx.Response(404, stream=UnreadBody())
        if str(request.url) == pmegp.SOURCE_URL:
            return httpx.Response(200, headers={"content-type": "text/html"}, text=html)
        assert str(request.url) == pmegp.PROJECTS_URL
        if failure == "timeout":
            raise httpx.ReadTimeout("private proxy details", request=request)
        if failure == "http":
            return httpx.Response(503, stream=UnreadBody())
        if failure == "pdf":
            return httpx.Response(
                200, headers={"content-type": "application/pdf"}, stream=UnreadBody()
            )
        return httpx.Response(200, headers={"content-type": "application/json"}, text="not JSON")

    monkeypatch.setattr(cli, "PMEGPAdapter", lambda **kwargs: factory(respond))
    result = runner.invoke(cli.app, ["source", "discover"])
    assert result.exit_code == 2 and "private" not in result.output
    assert path.read_bytes() == saved
    assert opened == [pmegp.ROBOTS_URL, pmegp.SOURCE_URL] + (
        [] if failure == "denial" else [pmegp.PROJECTS_URL]
    )


def test_authentic_fixture_cli_roundtrip(captured_responses, http_adapter, tmp_path, monkeypatch):
    html, body = captured_responses
    factory, opened, _ = http_adapter
    monkeypatch.setenv("MSMEINTEL_DATA_DIR", str(tmp_path))

    def respond(request):
        if str(request.url) == pmegp.ROBOTS_URL:
            return httpx.Response(404, stream=UnreadBody())
        if str(request.url) == pmegp.SOURCE_URL:
            return httpx.Response(200, headers={"content-type": "text/html"}, text=html)
        assert str(request.url) == pmegp.PROJECTS_URL
        return httpx.Response(200, headers={"content-type": "application/json"}, text=body)

    monkeypatch.setattr(cli, "PMEGPAdapter", lambda **kwargs: factory(respond))
    for command in (["source", "smoke"], ["source", "discover"], ["source", "discover"]):
        result = runner.invoke(cli.app, command)
        assert result.exit_code == 0, result.output
    requests_before_offline = len(opened)
    for command in (
        ["source", "list", "--limit", "1"],
        ["source", "sample", "--count", "10", "--output", str(tmp_path / "subset.json")],
    ):
        result = runner.invoke(cli.app, command)
        assert result.exit_code == 0, result.output
    assert "categories=9/9" in result.output
    assert len(opened) == requests_before_offline


def test_corrected_source_never_falls_back_to_kvic(http_adapter):
    factory, opened, _ = http_adapter
    assert pmegp.SOURCE_URL == "https://pmegp.msme.gov.in/Home/ProjectDetailList"
    with factory(lambda request: pytest.fail("No request permitted")) as adapter:
        with pytest.raises(DiscoveryError, match="origin/route"):
            adapter._get(
                "https://www.kviconline.gov.in/pmegp/pmegpweb/docs/jsp/newprojectReports.jsp"
            )
    assert opened == []
