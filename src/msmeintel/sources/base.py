"""Small discovery contract and source-independent observations."""

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Protocol
from urllib.parse import quote, urljoin, urlsplit, urlunsplit

type MetadataValue = str | int | float | bool | None


class DiscoveryError(ValueError):
    """Discovery could not produce a safe, complete observation."""


def canonicalize_url(href: str, base_url: str | None = None) -> str:
    """Normalize conservatively; do not reorder queries or decode reserved escapes."""
    if not isinstance(href, str) or not href.strip() or href.strip().startswith("#"):
        raise DiscoveryError("Missing or fragment-only URL.")
    if any(ord(char) < 32 or ord(char) == 127 for char in href) or "\\" in href:
        raise DiscoveryError("Control character or backslash in URL.")
    try:
        parsed = urlsplit(urljoin(base_url or "", href.strip()))
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
            raise ValueError
        if parsed.username is not None or parsed.password is not None:
            raise ValueError
        host = parsed.hostname.lower().encode("idna").decode("ascii")
        if any(char.isspace() for char in host):
            raise ValueError
        if ":" in host:
            host = f"[{host}]"
        port = parsed.port
        if port is not None and (parsed.scheme.lower(), port) not in {("http", 80), ("https", 443)}:
            host += f":{port}"
        return urlunsplit(
            (
                parsed.scheme.lower(),
                host,
                quote(parsed.path, safe="/%:@!$&'()*+,;=-._~"),
                parsed.query,
                "",
            )
        )
    except (ValueError, UnicodeError) as error:
        raise DiscoveryError("Invalid HTTP(S) URL (credentials are forbidden).") from error


@dataclass(frozen=True)
class DocumentCandidate:
    original_href: str
    found_on_url: str
    title: str | None = None
    declared_type: str | None = None


@dataclass(frozen=True)
class ProjectCandidate:
    title: str
    listing_url: str
    external_project_id: str | None = None
    category_hint: str | None = None
    page_url: str | None = None
    raw_metadata: dict[str, MetadataValue] = field(default_factory=dict)
    documents: tuple[DocumentCandidate, ...] = ()
    normalized_metadata: dict[str, str] = field(default_factory=dict)


class SourceAdapter(Protocol):
    source_key: str
    source_url: str

    def discover_projects(self) -> Iterable[ProjectCandidate]: ...

    def discover_documents(self, project: ProjectCandidate) -> Iterable[DocumentCandidate]: ...

    def canonicalize_url(self, url: str) -> str: ...
