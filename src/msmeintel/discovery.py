"""Local discovery observations, safe snapshots, and deterministic sampling."""

import json
import math
import os
import tempfile
from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urljoin
from uuid import NAMESPACE_URL, uuid5

from .sources.base import DiscoveryError, DocumentCandidate, ProjectCandidate, canonicalize_url

SELECTION_METHOD = "category-pattern-round-robin-v1"


def json_text(value: dict) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"


def _text(value, *, nullable=False) -> None:
    if nullable and value is None:
        return
    if not isinstance(value, str) or not value.strip():
        raise DiscoveryError("Expected nonempty observation text.")


def _timestamp(value) -> datetime:
    _text(value)
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.utcoffset() != UTC.utcoffset(None):
            raise ValueError
        return parsed
    except ValueError as error:
        raise DiscoveryError("Observation timestamp must be UTC ISO-8601.") from error


def _documents(candidates: Iterable[DocumentCandidate]) -> list[dict]:
    grouped = defaultdict(dict)
    for candidate in candidates:
        _text(candidate.title, nullable=True)
        _text(candidate.declared_type, nullable=True)
        canonicalize_url(candidate.found_on_url)
        canonical = canonicalize_url(candidate.original_href, candidate.found_on_url)
        observation = {
            "original_href": candidate.original_href,
            "url": urljoin(candidate.found_on_url, candidate.original_href.strip()),
            "canonical_url": canonical,
            "title": candidate.title,
            "found_on_url": candidate.found_on_url,
            "declared_type": candidate.declared_type,
        }
        grouped[canonical][json_text(observation)] = observation
    result = []
    for canonical in sorted(grouped):
        variants = [grouped[canonical][key] for key in sorted(grouped[canonical])]
        result.append({**variants[0], "original_variants": variants[1:]})
    return result


def _document_candidates(documents: list[dict]) -> tuple[DocumentCandidate, ...]:
    return tuple(
        DocumentCandidate(
            original_href=item["original_href"],
            found_on_url=item["found_on_url"],
            title=item["title"],
            declared_type=item["declared_type"],
        )
        for document in documents
        for item in [document, *document["original_variants"]]
    )


def _record(candidate: ProjectCandidate, source_key: str, source_url: str) -> dict:
    _text(candidate.title)
    _text(candidate.external_project_id, nullable=True)
    _text(candidate.category_hint, nullable=True)
    if not isinstance(candidate.raw_metadata, dict) or not all(
        isinstance(key, str)
        and (value is None or isinstance(value, (str, int, float, bool)))
        and (not isinstance(value, float) or math.isfinite(value))
        for key, value in candidate.raw_metadata.items()
    ):
        raise DiscoveryError("Raw metadata must contain finite JSON scalar observations.")
    if not isinstance(candidate.normalized_metadata, dict) or not all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in candidate.normalized_metadata.items()
    ):
        raise DiscoveryError("Normalized metadata must contain explicitly derived text values.")
    documents = _documents(candidate.documents)
    page_url = canonicalize_url(candidate.page_url) if candidate.page_url is not None else None
    title = " ".join(candidate.title.split())
    if candidate.external_project_id is not None:
        identity = [source_key, "id", candidate.external_project_id]
    elif page_url is not None:
        identity = [source_key, "page", page_url]
    else:
        # Adapter must omit unstable display serials from raw_metadata.
        identity = [
            source_key,
            "observation",
            canonicalize_url(source_url),
            title,
            candidate.category_hint,
            candidate.raw_metadata,
            [document["canonical_url"] for document in documents],
        ]
    key = str(uuid5(NAMESPACE_URL, json.dumps(identity, sort_keys=True, ensure_ascii=False)))
    return {
        "record_key": key,
        "external_project_id": candidate.external_project_id,
        "title": title,
        "raw_title": candidate.title,
        "category_hint": candidate.category_hint,
        "listing_url": candidate.listing_url,
        "canonical_listing_url": canonicalize_url(candidate.listing_url),
        "page_url": candidate.page_url,
        "canonical_page_url": page_url,
        "raw_metadata": dict(candidate.raw_metadata),
        "normalized_metadata": dict(candidate.normalized_metadata),
        "documents": documents,
        "discovery_status": "DISCOVERED" if documents else "MISSING_DOCUMENT_LINK",
    }


def _stable(record: dict) -> dict:
    return {
        key: value for key, value in record.items() if key not in {"first_seen_at", "last_seen_at"}
    }


def _signature(record: dict) -> dict:
    """Canonical content, independent of original URL spellings and observation page."""
    return {
        key: record[key]
        for key in (
            "title",
            "category_hint",
            "raw_metadata",
            "normalized_metadata",
            "external_project_id",
            "canonical_page_url",
        )
    } | {"documents": [doc["canonical_url"] for doc in record["documents"]]}


def build_manifest(
    candidates: Iterable[ProjectCandidate],
    *,
    source_key: str,
    source_url: str,
    previous: dict | None = None,
    observed_at: str | None = None,
) -> tuple[dict, dict]:
    """Input must be a complete traversal; generators must finish before anything is written."""
    _text(source_key)
    canonicalize_url(source_url)
    now = observed_at or datetime.now(UTC).isoformat()
    _timestamp(now)
    if previous is not None:
        validate_manifest(previous)
        if not previous["complete"] or (previous["source_key"], previous["source_url"]) != (
            source_key,
            source_url,
        ):
            raise DiscoveryError("Previous manifest must be a full snapshot of this source.")
        if _timestamp(now) < _timestamp(previous["discovered_at"]):
            raise DiscoveryError("Observation time precedes the previous snapshot.")
    old = {record["record_key"]: record for record in (previous or {}).get("projects", [])}
    records = {}
    for candidate in candidates:
        record = _record(candidate, source_key, source_url)
        key = record["record_key"]
        if key in records:
            other = records[key]
            if _signature(other) != _signature(record):
                raise DiscoveryError(f"Conflicting source identity {key}; no snapshot written.")
            documents = _documents(_document_candidates(other["documents"] + record["documents"]))
            record = min(
                (other, record),
                key=lambda item: json_text({k: v for k, v in item.items() if k != "documents"}),
            )
            record["documents"] = documents
        records[key] = record
    if not records:
        raise DiscoveryError("No identifiable projects; empty discovery is not verified success.")
    issues = []
    for key, record in records.items():
        record["first_seen_at"] = old.get(key, {}).get("first_seen_at", now)
        record["last_seen_at"] = now
        if not record["documents"]:
            issues.append(
                {
                    "source_url": record["listing_url"],
                    "context": key,
                    "reason": "MISSING_DOCUMENT_LINK",
                    "raw_text": record["raw_title"],
                }
            )
    manifest = {
        "schema_version": 1,
        "source_key": source_key,
        "source_url": source_url,
        "discovered_at": now,
        "scope": "full",
        "complete": True,
        "discovered_total": len(records),
        "projects": [records[key] for key in sorted(records)],
        "issues": sorted(issues, key=json_text),
    }
    changes = {
        "added": sorted(records.keys() - old.keys()),
        "changed": sorted(
            key for key in records.keys() & old.keys() if _stable(records[key]) != _stable(old[key])
        ),
        "no_longer_seen": sorted(old.keys() - records.keys()),
    }
    validate_manifest(manifest)
    return manifest, changes


def _validate_projects(value: dict, *, timestamps: bool) -> None:
    _text(value["source_key"])
    canonicalize_url(value["source_url"])
    if not isinstance(value["projects"], list) or not value["projects"]:
        raise DiscoveryError("Snapshot must contain projects.")
    seen = set()
    for record in value["projects"]:
        candidate = ProjectCandidate(
            title=record["raw_title"],
            listing_url=record["listing_url"],
            external_project_id=record["external_project_id"],
            category_hint=record["category_hint"],
            page_url=record["page_url"],
            raw_metadata=record["raw_metadata"],
            normalized_metadata=record["normalized_metadata"],
            documents=_document_candidates(record["documents"]),
        )
        rebuilt = _record(candidate, value["source_key"], value["source_url"])
        if rebuilt != (_stable(record) if timestamps else record):
            raise DiscoveryError("Invalid project identity, fields, or canonical URL observations.")
        if timestamps:
            first, last = _timestamp(record["first_seen_at"]), _timestamp(record["last_seen_at"])
            if first > last or last != _timestamp(value["discovered_at"]):
                raise DiscoveryError("Inconsistent observation timestamps.")
        if record["record_key"] in seen:
            raise DiscoveryError("Duplicate project key in snapshot.")
        seen.add(record["record_key"])


def validate_manifest(value: dict) -> None:
    try:
        if set(value) != {
            "schema_version",
            "source_key",
            "source_url",
            "discovered_at",
            "scope",
            "complete",
            "discovered_total",
            "projects",
            "issues",
        }:
            raise DiscoveryError("Invalid manifest fields.")
        if value["schema_version"] != 1 or type(value["schema_version"]) is not int:
            raise DiscoveryError("Unsupported manifest schema.")
        _timestamp(value["discovered_at"])
        _validate_projects(value, timestamps=True)
        if value["scope"] not in {"full", "limit", "sample"} or type(value["complete"]) is not bool:
            raise DiscoveryError("Invalid snapshot scope/completeness.")
        total = value["discovered_total"]
        if type(total) is not int or total < len(value["projects"]):
            raise DiscoveryError("Invalid discovered population.")
        if value["complete"] != (value["scope"] == "full") or (
            value["complete"] and total != len(value["projects"])
        ):
            raise DiscoveryError("Incomplete manifest cannot represent a full population.")
        if not isinstance(value["issues"], list):
            raise DiscoveryError("Invalid discovery issues.")
        for issue in value["issues"]:
            if set(issue) != {"source_url", "context", "reason", "raw_text"}:
                raise DiscoveryError("Invalid issue fields.")
            for field in ("source_url", "context", "reason", "raw_text"):
                _text(issue[field])
            canonicalize_url(issue["source_url"])
    except (KeyError, TypeError, AttributeError) as error:
        raise DiscoveryError("Invalid discovery manifest structure.") from error


def _unique_object(pairs: list[tuple]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise DiscoveryError("Duplicate JSON field; snapshot is ambiguous.")
        result[key] = value
    return result


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    except (OSError, ValueError) as error:
        raise DiscoveryError(
            "Cannot read valid JSON snapshot; existing file left unchanged."
        ) from error


def read_manifest(path: Path) -> dict:
    value = _read_json(path)
    validate_manifest(value)
    return value


def _atomic_write(path: Path, value: dict) -> None:
    text = json_text(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n", dir=path.parent, suffix=".tmp", delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def write_manifest(path: Path, manifest: dict) -> None:
    validate_manifest(manifest)
    if path.exists():
        old = read_manifest(path)
        if any(old[field] != manifest[field] for field in ("source_key", "source_url", "scope")):
            raise DiscoveryError("Cannot overwrite a snapshot with a different source or scope.")
    _atomic_write(path, manifest)


def filter_manifest(
    manifest: dict, *, limit: int | None = None, sample: dict | None = None
) -> dict:
    validate_manifest(manifest)
    if not manifest["complete"] or (limit is None) == (sample is None):
        raise DiscoveryError("Choose exactly one output filter after full discovery.")
    if limit is not None:
        if limit <= 0:
            raise DiscoveryError("Limit must be positive.")
        selected = manifest["projects"][:limit]
    else:
        validate_sample(sample)
        if (sample["source_key"], sample["source_url"]) != (
            manifest["source_key"],
            manifest["source_url"],
        ):
            raise DiscoveryError("Sample belongs to a different source.")
        keys = {project["record_key"] for project in sample["projects"]}
        selected = [project for project in manifest["projects"] if project["record_key"] in keys]
        if len(selected) != len(keys):
            raise DiscoveryError("Selected keys are missing from current full discovery.")
    return manifest | {
        "scope": "limit" if limit is not None else "sample",
        "complete": False,
        "projects": selected,
    }


def link_pattern(project: dict) -> str:
    detail = any(
        canonicalize_url(observation["found_on_url"]) == project["canonical_page_url"]
        for document in project["documents"]
        for observation in [document, *document["original_variants"]]
    )
    location = "detail" if detail else "listing"
    multiplicity = "multiple" if len(project["documents"]) > 1 else "single"
    return f"{location}-{multiplicity}"


def _category_key(category: str | None) -> tuple:
    return category is not None, category or ""


def _spread(items: list, count: int) -> list:
    if count == 1:
        return [items[len(items) // 2]]
    return [items[i * (len(items) - 1) // (count - 1)] for i in range(count)]


def select_sample(manifest: dict, count: int = 20) -> dict:
    validate_manifest(manifest)
    if not manifest["complete"]:
        raise DiscoveryError("Sampling requires a complete, unfiltered manifest.")
    eligible = [record for record in manifest["projects"] if record["documents"]]
    if type(count) is not int or count <= 0 or len(eligible) < count:
        raise DiscoveryError("Sample count must be positive and no larger than eligible projects.")
    buckets = defaultdict(list)
    for record in eligible:
        buckets[(record["category_hint"], link_pattern(record))].append(record)
    categories = sorted({key[0] for key in buckets}, key=_category_key)
    if len(categories) > count:
        categories = _spread(categories, count)
    patterns = {
        category: sorted(key[1] for key in buckets if key[0] == category) for category in categories
    }
    cursors = dict.fromkeys(categories, 0)
    quotas = dict.fromkeys(buckets, 0)
    remaining = count
    while remaining:
        for category in categories:
            options = patterns[category]
            for _ in options:
                pattern = options[cursors[category] % len(options)]
                cursors[category] += 1
                key = category, pattern
                if quotas[key] < len(buckets[key]):
                    quotas[key] += 1
                    remaining -= 1
                    break
            if not remaining:
                break
    selected = []
    for key, quota in quotas.items():
        if quota:
            selected.extend(
                _spread(sorted(buckets[key], key=lambda item: item["record_key"]), quota)
            )
    return {
        "schema_version": 1,
        "source_key": manifest["source_key"],
        "source_url": manifest["source_url"],
        "selection_method": SELECTION_METHOD,
        "count": count,
        "projects": [
            _stable(record) for record in sorted(selected, key=lambda item: item["record_key"])
        ],
    }


def validate_sample(value: dict) -> None:
    try:
        if set(value) != {
            "schema_version",
            "source_key",
            "source_url",
            "selection_method",
            "count",
            "projects",
        }:
            raise DiscoveryError("Invalid sample fields.")
        if (
            type(value["schema_version"]) is not int
            or value["schema_version"] != 1
            or value["selection_method"] != SELECTION_METHOD
        ):
            raise DiscoveryError("Unsupported sample schema/method.")
        _validate_projects(value, timestamps=False)
        if (
            type(value["count"]) is not int
            or value["count"] != len(value["projects"])
            or not all(project["documents"] for project in value["projects"])
        ):
            raise DiscoveryError("Invalid sample population/document eligibility.")
    except (KeyError, TypeError, AttributeError) as error:
        raise DiscoveryError("Invalid sample structure.") from error


def read_sample(path: Path) -> dict:
    value = _read_json(path)
    validate_sample(value)
    return value


def write_sample(path: Path, sample: dict, *, replace: bool = False) -> bool:
    """Return false for unchanged samples; never silently regenerate a frozen selection."""
    validate_sample(sample)
    if path.exists():
        old = read_sample(path)
        if old == sample:
            return False
        if not replace:
            raise DiscoveryError("Sample content differs; choose another path or --replace.")
    _atomic_write(path, sample)
    return True


def summary(manifest: dict) -> str:
    documents = [document for record in manifest["projects"] for document in record["documents"]]
    return (
        f"discovered_total={manifest['discovered_total']} "
        f"saved_projects={len(manifest['projects'])} "
        f"document_associations={len(documents)} "
        f"unique_document_urls={len({doc['canonical_url'] for doc in documents})} "
        f"scope={manifest['scope']} complete={manifest['complete']}"
    )


def sample_coverage(manifest: dict, sample: dict) -> str:
    eligible = [record for record in manifest["projects"] if record["documents"]]
    categories = {record["category_hint"] for record in eligible}
    selected = {record["category_hint"] for record in sample["projects"]}
    patterns = {link_pattern(record) for record in eligible}
    covered = {link_pattern(record) for record in sample["projects"]}
    uncovered = sorted(categories - selected, key=_category_key)
    return (
        f"categories={len(selected)}/{len(categories)} "
        f"link_patterns={len(covered)}/{len(patterns)} "
        f"uncovered_categories={json.dumps(uncovered, ensure_ascii=False)} "
        f"missing_categories={sum(record['category_hint'] is None for record in eligible)}. "
        "Coverage uses observed labels/link patterns only; document contents are unverified."
        + (
            " No categories: deterministic link-pattern/even-spread coverage only."
            if categories == {None}
            else ""
        )
    )
