"""PMEGP's public all-projects JSON feed; no document bodies are requested."""

import json
import math
import re
import time
from decimal import Decimal
from urllib.parse import quote
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup

from .base import DiscoveryError, DocumentCandidate, ProjectCandidate, canonicalize_url

SOURCE_URL = "https://pmegp.msme.gov.in/Home/ProjectDetailList"
ROBOTS_URL = "https://pmegp.msme.gov.in/robots.txt"
PROJECTS_URL = "https://pmegp.msme.gov.in/Home/GetAllProjectDocuments"
SCRIPT_PATH = "/TFL_Scripts/Home/ProjectDetailList.cshtml.js"
USER_AGENT = "MSMEIntel/0.1 (local learning project; metadata discovery only)"
MAX_HTML_BYTES = 5 * 1024 * 1024


def parse_listing(html: str, page_url: str) -> None:
    """Validate the observed table shell, NOT an empty HTML project population."""
    if canonicalize_url(page_url) != SOURCE_URL:
        raise DiscoveryError("Unexpected PMEGP listing URL.")
    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table", id="datatable-basic")
    expected = ["Sr No", "PSRID", "Project Name", "Total Project Cost (in ₹)", "View/Download"]
    if (
        table is None
        or [heading.get_text(" ", strip=True) for heading in table.select("thead th")] != expected
        or table.find("tbody", id="ux_tablebody") is None
        or soup.find("script", src=SCRIPT_PATH) is None
    ):
        raise DiscoveryError("Unrecognized PMEGP listing structure; discovery stopped.")


def _json_object(pairs: list[tuple]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise DiscoveryError("Duplicate JSON field in PMEGP response.")
        result[key] = value
    return result


def _reject_constant(value: str):
    raise DiscoveryError("Non-finite number in PMEGP JSON response.")


def parse_projects(text: str) -> list[ProjectCandidate]:
    """Parse the observed success/data response without network or floating-point rounding."""
    try:
        response = json.loads(
            text,
            parse_float=Decimal,
            parse_constant=_reject_constant,
            object_pairs_hook=_json_object,
        )
    except (ValueError, RecursionError) as error:
        raise DiscoveryError("Invalid PMEGP JSON response.") from error
    if (
        not isinstance(response, dict)
        or set(response) != {"success", "data"}
        or response["success"] is not True
        or not isinstance(response["data"], list)
        or not response["data"]
    ):
        raise DiscoveryError("PMEGP all-projects response is empty, unsuccessful, or changed.")
    projects = []
    for row in response["data"]:
        if (
            not isinstance(row, dict)
            or type(row.get("PSRID")) is not int
            or row["PSRID"] <= 0
            or not isinstance(row.get("ProjectName"), str)
            or not row["ProjectName"].strip()
        ):
            raise DiscoveryError("PMEGP row lacks a valid PSRID/name; incomplete discovery.")
        if not all(
            value is None or isinstance(value, (str, int, bool, Decimal)) for value in row.values()
        ):
            raise DiscoveryError("Unrecognized PMEGP metadata structure; discovery stopped.")
        raw = {
            key: str(value) if isinstance(value, Decimal) else value for key, value in row.items()
        }
        normalized = {}
        cost = row.get("ProjectCost")
        # The observed HTML header states rupees. Preserve exact raw decimal text separately.
        if type(cost) is int or isinstance(cost, Decimal):
            amount = Decimal(cost)
            if not amount.is_finite():
                raise DiscoveryError("Non-finite PMEGP project cost.")
            # Bound expansion of hostile exponents without discarding the source value.
            if len(amount.as_tuple().digits) <= 1000 and abs(amount.as_tuple().exponent) <= 1000:
                value = format(amount, "f")
                normalized["project_cost_inr"] = (
                    value.rstrip("0").rstrip(".") if "." in value else value
                )
        path = row.get("DocPath")
        documents = ()
        if path not in (None, ""):
            if (
                not isinstance(path, str)
                or not path.startswith("Documents/ProjectSampleReport/")
                or any(part in {".", "..", ""} for part in path.split("/"))
                or "\\" in path
                or any(ord(char) < 32 or ord(char) == 127 for char in path)
            ):
                raise DiscoveryError(f"Unsafe/unrecognized document path for PSRID {row['PSRID']}.")
            # Exact URL construction observed in the site's click handler (encodeURIComponent).
            href = "/Home/DownloadDocument?fileName=" + quote(path, safe="-_.!~*'()")
            documents = (DocumentCandidate(href, SOURCE_URL, title="Download"),)
        # Literal published grouping annotation, not a sector inferred from the business name.
        group = re.search(r" \( ([^()]+) \)$", row["ProjectName"])
        projects.append(
            ProjectCandidate(
                title=row["ProjectName"],
                listing_url=SOURCE_URL,
                external_project_id=str(row["PSRID"]),
                category_hint=group.group(1) if group and group.group(1).strip() else None,
                raw_metadata=raw,
                normalized_metadata=normalized,
                documents=documents,
            )
        )
    return projects


def parse_robots(text: str) -> RobotFileParser:
    """Fail closed on restrictions that stdlib robotparser cannot enforce."""
    seen_agent = False
    agents = set()
    permission_directives = set()
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
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
            raise DiscoveryError("Robots policy is ambiguous or uses unsupported directives.")
        if key == "user-agent":
            if not value:
                raise DiscoveryError("Empty robots user-agent.")
            if value.lower() in agents:
                raise DiscoveryError(
                    "Repeated robots user-agent groups need review; access stopped."
                )
            agents.add(value.lower())
            seen_agent = True
        elif key != "sitemap" and not seen_agent:
            raise DiscoveryError("Robots restrictions without a user-agent.")
        if key in {"allow", "disallow"} and any(char in value for char in "*$"):
            raise DiscoveryError("Unsupported robots wildcard/end-anchor rule; access stopped.")
        if key in {"allow", "disallow"} and value:
            permission_directives.add(key)
        if key == "crawl-delay" and not value.isdigit():
            raise DiscoveryError("Unsupported robots crawl-delay; access stopped.")
        if key == "request-rate":
            rate = value.split("/")
            if len(rate) != 2 or not all(part.isdigit() and int(part) > 0 for part in rate):
                raise DiscoveryError("Unsupported robots request-rate; access stopped.")
    # Be conservative across supported Python versions without relying on private parser state.
    product = USER_AGENT.split("/", 1)[0].lower()
    if sum(agent != "*" and agent in product for agent in agents) > 1:
        raise DiscoveryError("Ambiguous robots user-agent groups; access stopped.")
    if permission_directives == {"allow", "disallow"}:
        raise DiscoveryError("Mixed robots allow/disallow precedence needs review; access stopped.")
    policy = RobotFileParser(ROBOTS_URL)
    policy.parse(text.splitlines())
    return policy


class PMEGPAdapter:
    source_key = "pmegp"
    source_url = SOURCE_URL

    def __init__(
        self,
        *,
        timeout: float = 30,
        request_delay: float = 1,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not all(math.isfinite(value) and value > 0 for value in (timeout, request_delay)):
            raise DiscoveryError("Timeout and request delay must be finite and positive.")
        self.delay = max(1.0, request_delay)
        self.last_request: float | None = None
        self.policy: RobotFileParser | None = None
        self.client = httpx.Client(
            headers={"User-Agent": USER_AGENT},
            timeout=httpx.Timeout(timeout, connect=min(10, timeout)),
            follow_redirects=False,
            transport=transport,
        )

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.client.close()

    def canonicalize_url(self, url: str) -> str:
        return canonicalize_url(url, SOURCE_URL)

    def discover_documents(self, project: ProjectCandidate):
        return project.documents

    def _get(self, url: str, *, robots: bool = False) -> str:
        allowed_urls = {ROBOTS_URL} if robots else {SOURCE_URL, PROJECTS_URL}
        if canonicalize_url(url) not in allowed_urls:
            raise DiscoveryError("Unverified PMEGP origin/route; no request made.")
        if not robots and (self.policy is None or not self.policy.can_fetch(USER_AGENT, url)):
            raise DiscoveryError("Robots permission absent or denied; no listing request made.")
        if self.last_request is not None:
            time.sleep(max(0, self.delay - (time.monotonic() - self.last_request)))
        self.last_request = time.monotonic()
        phase = "robots" if robots else "projects JSON" if url == PROJECTS_URL else "listing"
        try:
            headers = (
                {"Accept": "application/json", "Content-Type": "application/json; charset=utf-8"}
                if url == PROJECTS_URL
                else {}
            )
            with self.client.stream("GET", url, headers=headers) as response:
                if robots and response.status_code in {404, 410}:
                    return ""
                if response.is_redirect:
                    # No redirect destinations have been observed/verified. Fail without following.
                    raise DiscoveryError("Unverified redirect; access stopped without following.")
                if response.status_code != 200:
                    raise DiscoveryError(f"Source HTTP {response.status_code}; access stopped.")
                media_type = (
                    response.headers.get("content-type", "").split(";", 1)[0].lower().strip()
                )
                allowed = (
                    {"text/plain"}
                    if robots
                    else {"application/json"}
                    if url == PROJECTS_URL
                    else {"text/html", "application/xhtml+xml"}
                )
                if media_type not in allowed:
                    raise DiscoveryError("Unexpected source MIME type; body was not consumed.")
                body = bytearray()
                for chunk in response.iter_bytes(chunk_size=65536):
                    if len(body) + len(chunk) > MAX_HTML_BYTES:
                        raise DiscoveryError("Source response exceeds the 5 MiB limit.")
                    body.extend(chunk)
                return body.decode(response.encoding or "utf-8")
        except httpx.TimeoutException as error:
            raise DiscoveryError(
                f"Source HTTP timeout ({phase}); previous manifest unchanged."
            ) from error
        except httpx.HTTPError as error:
            raise DiscoveryError(
                f"Source HTTP transport failure ({phase}); previous manifest unchanged."
            ) from error
        except (UnicodeError, LookupError) as error:
            raise DiscoveryError("Source response has invalid text encoding.") from error

    def fetch_listing(self) -> str:
        if self.policy is None:
            self.policy = parse_robots(self._get(ROBOTS_URL, robots=True))
            crawl_delay = self.policy.crawl_delay(USER_AGENT) or 0
            rate = self.policy.request_rate(USER_AGENT)
            self.delay = max(self.delay, crawl_delay, rate.seconds / rate.requests if rate else 0)
        return self._get(SOURCE_URL)

    def discover_projects(self) -> list[ProjectCandidate]:
        parse_listing(self.fetch_listing(), SOURCE_URL)
        return parse_projects(self._get(PROJECTS_URL))

    def smoke(self) -> list[ProjectCandidate]:
        """LIVE robots + HTML shell + one all-projects response; no writes/documents."""
        return self.discover_projects()
