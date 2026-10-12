# PMEGP fixture provenance

Captured at **2026-10-08T05:32:17.594477+00:00** from the corrected official
PMEGP source. These are authentic, pruned observations, not synthetic PMEGP HTML.

## Requests and source contract

- Listing: `GET https://pmegp.msme.gov.in/Home/ProjectDetailList` -> 200 HTML.
- Observed page script:
  `https://pmegp.msme.gov.in/TFL_Scripts/Home/ProjectDetailList.cshtml.js`.
  Its AJAX call uses GET, `/Home/GetAllProjectDocuments`, JSON content/data type,
  and no query/body parameters. No site JavaScript is vendored or executed by the app.
- Data: `GET https://pmegp.msme.gov.in/Home/GetAllProjectDocuments` -> 200,
  `application/json; charset=utf-8`, `{"success":true,"data":[...]}`.
  No login, session cookie, API key, server pagination, or separate total field is needed.
- Robots: `GET https://pmegp.msme.gov.in/robots.txt` -> 404, empty body.
  This is treated as no published policy, not a grant of copyright/reuse rights.
- Verified-TLS httpx requests succeeded. Windows curl reported an inability to
  check certificate revocation; no verification was disabled to work around it.
  The web reader could not fetch this site, but the browser and httpx could.

The browser showed an initially empty table populated with all fetched rows,
including hidden PSRID cells and Download buttons carrying `data-path`.
The row-loading script renders every array item, using index + 1 for Sr No.
It initializes DataTables with local searching/paging/ordering, not a server-side
AJAX paginator. Browser page 2 showed rows 11-20; the default display size was 10
with 10/25/50/100 choices. A separate inline initializer references a different
table ID and does not set the observed table's page size. Direct JSON retrieval
confirmed the full available array (1,024 rows/unique PSRIDs at capture, not a constant).

The browser control did not expose a raw network/HAR trace. Request method and
parameters were verified from the actual linked JavaScript and a successful
direct request, alongside observed rendered rows/paging. No endpoints were guessed.

## Included captures and pruning

- `listing.html`: the actual initial `#datatable-basic` table (five headers,
  empty `#ux_tablebody`) plus its actual row-loading script reference. Table
  text/attributes are retained; line endings are normalized. The script tag was
  serialized from the observed element. Other layout, scripts, navigation,
  graphics, cookies, and potential session material are omitted.
- `project_documents.json`: 12 unmodified row objects from the actual API,
  reassembled in its success/data envelope. Original numeric token text and JSON
  escapes are retained; only rows and outer whitespace were pruned. It is an
  **excerpt**, not the full live corpus. PSRIDs:
  1, 2, 3, 4, 5, 79, 83, 89, 354, 671, 705, 1024.
  Selection includes all nine published group annotations, inner parentheses,
  ampersand escaping, an inactive-but-listed record, a zero cost, null/non-null
  ModifyOn values, and the last returned row.
- Malformed/missing/duplicate/changed-population cases in `test_discovery.py`
  are explicitly synthetic mutations of these observations, never additional
  alleged real captures. No empty edge-case HTML or fabricated live sample exists.

The seven observed API fields are PSRID (integer), ProjectName (string),
ProjectCost (decimal JSON number), DocPath (string), IsActive (boolean),
CreatedOn (string), and ModifyOn (null/string). Source .NET date strings remain
verbatim. The header explicitly states rupees, enabling exact decimal-text
normalization separate from raw ProjectCost. Null/zero/false are not discarded.

There is no category column/filter or category JSON field. Names explicitly carry
trailing ` ( group label )` annotations. These literal labels become category
hints, not inferred canonical sectors; `Samadhan Projects` is a publisher-style
label. Unknown/missing annotations remain absent. The source script does not
filter IsActive, so the adapter does not drop publicly listed inactive records.

The observed button handler uses `/Home/DownloadDocument?fileName=` plus
`encodeURIComponent(DocPath)`. Python reproduces the same escaping; the original
DocPath is retained in raw metadata. None of these document URLs was requested,
including by HEAD. Shared document URLs do not merge separate PSRIDs.

## Attribution and reuse

Source: Ministry of Micro, Small and Medium Enterprises / PMEGP portal.
The page credits Indian Bank for its hosting/development/maintenance.

The linked [terms](https://pmegp.msme.gov.in/Home/TermsAndConditions), inspected
on 2026-10-08, assert rights in portal content and do not state an open-content
license. These fixtures retain minimal factual metadata/schema for this local
learning project's deterministic tests; no PDF, graphics, or site script source
is copied. **REVIEW REQUIRED before public redistribution/republication of source
material.** Public access and robots 404 are not license evidence.

The older KVIC listing was investigated in the prior checkpoint, but it is not
this adapter's primary source or a fallback.
