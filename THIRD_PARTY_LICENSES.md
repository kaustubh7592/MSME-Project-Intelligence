# Third-Party Licenses

This M00–M03 inventory covers the direct build/runtime/development dependencies and all
transitive packages installed in the locked environment. Versions come from `uv.lock`
and the M00 build output. Licenses and source links come from installed package metadata,
shipped license files, or the dependency's authoritative repository.

No entry below is based on a guessed license. Future unclear or conflicting entries must
be marked `REVIEW REQUIRED` before the dependency can become required core functionality.

Free/open-source dependencies are allowed. Proprietary paid runtime dependencies,
subscription-only components, and commercial-license-only components must not be
required for core functionality. Public availability is not license evidence.

## Build

| Package | Version | License | Source | Purpose |
|---|---:|---|---|---|
| uv_build | 0.12.22 | Apache-2.0 OR MIT | [Astral uv](https://github.com/astral-sh/uv) | Project build backend |

## Runtime

| Package | Version | License | Source | Purpose |
|---|---:|---|---|---|
| Alembic | 1.20.0 | MIT | [SQLAlchemy Alembic](https://github.com/sqlalchemy/alembic) | Database migrations |
| annotated-doc | 0.0.5 | MIT | [FastAPI annotated-doc](https://github.com/fastapi/annotated-doc) | Typer annotation metadata |
| colorama | 0.4.6 | BSD-3-Clause | [Colorama](https://github.com/tartley/colorama) | Windows terminal support for Typer |
| Mako | 1.4.3 | MIT | [Mako](https://github.com/sqlalchemy/mako) | Alembic revision templates |
| markdown-it-py | 4.2.0 | MIT | [markdown-it-py](https://github.com/executablebooks/markdown-it-py) | Rich Markdown rendering |
| MarkupSafe | 3.0.4 | BSD-3-Clause | [MarkupSafe](https://github.com/pallets/markupsafe) | Mako escaping support |
| mdurl | 0.1.2 | MIT | [mdurl](https://github.com/executablebooks/mdurl) | Markdown URL parsing |
| psycopg | 3.3.6 | LGPL-3.0-only | [Psycopg](https://github.com/psycopg/psycopg) | PostgreSQL driver |
| psycopg-binary | 3.3.6 | LGPL-3.0-only | [Psycopg](https://github.com/psycopg/psycopg) | Local binary PostgreSQL driver distribution |
| Pygments | 2.21.0 | BSD-2-Clause | [Pygments](https://github.com/pygments/pygments) | Rich syntax highlighting |
| Rich | 15.0.0 | MIT | [Rich](https://github.com/Textualize/rich) | Typer terminal output |
| shellingham | 1.5.4 | ISC | [Shellingham](https://github.com/sarugaku/shellingham) | Shell detection for Typer |
| SQLAlchemy | 2.1.3 | MIT | [SQLAlchemy](https://github.com/sqlalchemy/sqlalchemy) | Database toolkit and declarative metadata |
| Typer | 0.27.2 | MIT | [Typer](https://github.com/fastapi/typer) | Command-line interface |
| typing-extensions | 4.16.0 | PSF-2.0 | [typing_extensions](https://github.com/python/typing_extensions) | Compatibility typing APIs |
| tzdata | 2026.4 | Apache-2.0 | [Python tzdata](https://github.com/python/tzdata) | Time-zone data required by Psycopg on Windows |

### M01 additions (verified from the installed distributions, 2026-10-08)

| Package | Version | License | Source | Purpose |
|---|---:|---|---|---|
| beautifulsoup4 | 4.15.0 | MIT | [Beautiful Soup](https://www.crummy.com/software/BeautifulSoup/bs4/) | Verified PMEGP HTML-shell parsing |
| httpx | 0.28.1 | BSD-3-Clause | [HTTPX](https://github.com/encode/httpx) | Bounded synchronous HTML/JSON HTTP and mock transport |
| lxml | 6.1.3 | BSD-3-Clause core; bundled notices below | [lxml](https://github.com/lxml/lxml) | HTML parsing backend |
| anyio | 4.15.1 | MIT | [AnyIO](https://github.com/agronholm/anyio) | HTTPX transitive dependency |
| certifi | 2026.7.22 | MPL-2.0 | [certifi](https://github.com/certifi/python-certifi) | HTTP TLS certificate bundle |
| h11 | 0.16.0 | MIT | [h11](https://github.com/python-hyper/h11) | HTTP/1.1 protocol support |
| httpcore | 1.0.9 | BSD-3-Clause | [httpcore](https://github.com/encode/httpcore) | HTTPX transport |
| idna | 3.20 | BSD-3-Clause | [idna](https://github.com/kjd/idna) | HTTP host-name encoding |
| soupsieve | 2.10 | MIT | [Soup Sieve](https://github.com/facelessuser/soupsieve) | Beautiful Soup selectors |

Evidence: `License` or `License-Expression` in each installed distribution's
`METADATA`, with shipped files under its `.dist-info/licenses/` directory.
Existing runtime `typing-extensions` is also used by these additions. No M00
locked package version was upgraded; no extra quality/audit tools were added.

lxml's shipped `LICENSE.txt` identifies its core BSD-3-Clause license.
`LICENSES.txt` additionally identifies CPython-derived code (PSF-License v2),
ElementTree-derived code (separate upstream notice), and bundled wheel libraries:
zlib (zlib license), iconv (LGPL 2.1 as stated in the notice), and libxml2/libxslt/
libexslt (MIT). Those are included binary-library notices, not separately installed
Python packages; their versions have not been invented.

**REVIEW REQUIRED:** lxml's notice describes some Schematron extraction stylesheets
as unlicensed and points to separate ElementTree/resource-specific notices. These
resources are not used by M01's intended HTML parser or its current runtime.
Do not introduce Schematron/resource functionality or redistribute the bundle
without resolving its applicable notices. This is not a claim that every bundled
asset has the core BSD license.

### PMEGP source observations (not a software dependency)

The corrected PMEGP source's [terms](https://pmegp.msme.gov.in/Home/TermsAndConditions)
assert rights in the site's content and do not provide an open-content license.
No site JavaScript, graphics, or PDF document body is vendored or executed by the
application. The test fixtures contain only a minimal factual table schema and
12 factual JSON project observations, with attribution and pruning documented in
`tests/fixtures/pmegp/README.md`. The sample stores observed metadata and links.
**REVIEW REQUIRED** before public redistribution/republication of source material;
neither a robots 404 nor public access is a grant of a reuse license. No open
license for the government source is guessed. Local discovery/testing uses the
existing free/open-source stack; no new dependency was added for the corrected feed.

### M03 additions (installed distribution evidence, 2026-10-09)

| Package | Version | License | Source | Purpose |
|---|---:|---|---|---|
| pdfplumber | 0.11.10 | MIT | [pdfplumber](https://github.com/jsvine/pdfplumber) | Native page text, words and boxes |
| pypdf | 6.19.0 | BSD-3-Clause | [pypdf](https://github.com/py-pdf/pypdf) | Page enumeration/encryption preflight; synthetic test PDFs |
| pdfminer.six | 20260107 | MIT | [pdfminer.six](https://github.com/pdfminer/pdfminer.six) | pdfplumber native parsing engine |
| charset-normalizer | 3.5.2 | MIT | [charset-normalizer](https://github.com/jawah/charset_normalizer) | pdfminer encoding dependency |
| cryptography | 50.0.2 | Apache-2.0 OR BSD-3-Clause | [cryptography](https://github.com/pyca/cryptography) | pdfminer dependency; synthetic encrypted PDF tests |
| cffi | 2.1.1 | MIT-0 | [cffi](https://github.com/python-cffi/cffi) | cryptography dependency |
| pycparser | 3.1 | BSD-3-Clause | [pycparser](https://github.com/eliben/pycparser) | cffi dependency |
| Pillow | 12.3.0 | MIT-CMU; bundled notices below | [Pillow](https://github.com/python-pillow/Pillow) | Required pdfplumber dependency; manual acceptance images |
| pypdfium2 | 5.14.0 | Apache-2.0 / BSD-3-Clause; bundled notices below | [pypdfium2](https://github.com/pypdfium2-team/pypdfium2) | Required pdfplumber dependency; manual source-page inspection only |

Evidence: the installed versions' `METADATA` License/License-Expression fields,
pdfplumber's MIT classifier plus `.dist-info/licenses/LICENSE.txt`, cffi's shipped
MIT No Attribution text, and the shipped cryptography/Pillow license files.
No new development-quality dependency or optional crypto/image extra was added.
No previously locked M00/M01 package version changed.

pypdfium2's installed metadata explicitly separates its Apache-2.0/BSD-3-Clause
code from CC-BY-4.0 documentation/examples. Its Windows wheel supplies PDFium and
binary dependency notices under
`pypdfium2-5.14.0.dist-info/licenses/data/windows_x64/BUILD_LICENSES/`:
PDFium (BSD-style and Apache notices), Abseil (Apache-2.0), AGG 2.3
(permission notice), fast_float (MIT), FreeType (FreeType Project License), ICU
(Unicode License V3), LittleCMS (MIT-style notice), libjpeg-turbo (IJG/BSD-style
notices), OpenJPEG (BSD-2-Clause), libpng (PNG Reference Library License v2),
LLVM libc (Apache-2.0 with LLVM exceptions), pdfium-binaries (MIT), simdutf
(MIT-style notice) and zlib (zlib notice). Preserve the shipped notices on any
redistribution; do not relabel all bundled components with the wrapper license.
This local build uses FreeType. Pillow's `licenses/LICENSE` also contains its
binary-library notices (including FreeType); those remain with the installed
wheel. These are bundled native components, not additional installed Python
packages. Native rendering is not part of the M03 application pipeline and no
OCR engine was added. No paid/proprietary runtime component is required.

**REVIEW REQUIRED** before redistributing platform-specific binary bundles or
government PDFs/full extracted text: retain/check all applicable component and
source notices. This is not a guessed government-content reuse license.

## Development

### M04 runtime status (2026-10-09; gate not accepted)

The implementation uses already installed pdfplumber/pdfminer.six, pypdf,
pypdfium2 and Pillow with the M03 licenses above. No additional Python package
was installed. pypdfium2/Pillow now support selective page rendering for OCR,
not just manual inspection; they are already required by the locked pdfplumber
distribution. No OCR wrapper framework or paid service was added.

Tesseract engine licensing was checked against the upstream
[Apache-2.0 license](https://github.com/tesseract-ocr/tesseract/blob/main/LICENSE)
and [installation documentation](https://tesseract-ocr.github.io/tessdoc/Installation.html),
which links the UB Mannheim Windows distribution. `winget show` identified
UB-Mannheim.TesseractOCR 5.4.0.20240606, Apache-2.0, with an installer on that
publisher's GitHub release. **Installation did not succeed:** download timed out.
No installed engine/version or trained language data is claimed verified. Before
acceptance, verify the actual installed binary, its bundled notices and English
traineddata; unresolved bundle/data licensing is **REVIEW REQUIRED**, not guessed.
Real OCR functionality remains blocked, independently of passing mocked tests.

### Existing development packages

| Package | Version | License | Source | Purpose |
|---|---:|---|---|---|
| iniconfig | 2.3.0 | MIT | [iniconfig](https://github.com/pytest-dev/iniconfig) | pytest configuration parsing |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause | [PyPA packaging](https://github.com/pypa/packaging) | pytest version/specifier handling |
| pluggy | 1.6.0 | MIT | [pluggy](https://github.com/pytest-dev/pluggy) | pytest plugin system |
| pytest | 9.1.1 | MIT | [pytest](https://github.com/pytest-dev/pytest) | Test runner |
| Ruff | 0.16.10 | MIT | [Ruff](https://github.com/astral-sh/ruff) | Linting and formatting |
