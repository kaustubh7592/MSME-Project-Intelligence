# Government MSME Project Intelligence Platform
## Learning Build Technical Specification and Codex Execution Playbook

**Version:** 2.0  
**Date:** 30 September 2026  
**Purpose:** Implementation contract for a local, free-to-run, evidence-backed business intelligence learning project built from Indian government MSME project documents.  
**Primary starting source:** PMEGP/KVIC project material.  
**Scale strategy:** 20 representative businesses -> 100 businesses -> all currently discovered businesses (approximately 1,024 at the time of planning; never hard-code this count).  
**Primary implementation principle:** extract once, normalize once, validate once, and answer future questions from the structured corpus instead of repeatedly asking an LLM to read every PDF.

---

# 1. Executive Summary

The project will build a local business-intelligence knowledge base from government-published MSME project profiles and related documents. The first implementation will focus on PMEGP/KVIC material and will deliberately start with a small sample of approximately 20 businesses. Once the pipeline is demonstrated to be correct and repeatable, the same code will be expanded to 100 businesses and finally to the complete dynamically discovered corpus.

The application is not primarily a PDF downloader and it is not a generic PDF chatbot. The PDFs are source artifacts. The useful product is the structured, queryable, evidence-backed business knowledge extracted from those documents.

A user should eventually be able to ask questions such as:

- Which manufacturing businesses have an estimated project cost below INR 10 lakh?
- Show businesses below INR 20 lakh that need fewer than 10 employees.
- Which food-processing projects have machinery cost below INR 8 lakh?
- Compare the capital requirement, manpower and working-capital requirement of three selected projects.
- What does the government project report say about the machinery, raw materials, production capacity and revenue assumptions for a specific business?
- Which projects are similar to PCB assembly or light engineering?

The first version must answer those questions using the stored corpus rather than by reading hundreds or thousands of PDF pages at question time.

The architecture is intentionally simple:

```text
PMEGP / government source
        |
        v
Discovery and manifest
        |
        v
Downloader + raw PDF store
        |
        v
PDF processing
(text + tables + OCR fallback)
        |
        v
Normalization
(rules + local LLM where useful)
        |
        v
Validation + evidence
        |
        v
PostgreSQL
(projects + facts + evidence)
        |
        v
Query assistant
(intent -> validated filters -> SQL -> result explanation)
```

No paid LLM API, proprietary extraction service, cloud runtime or commercial database is required. The runtime should be local and based on free/open-source software. Open-source software still has licenses, so the project must record and verify the license of each dependency and each model checkpoint.

---

# 2. Problem Definition

Government agencies publish business project profiles, model DPRs and bankable project documents that contain valuable structured information, but the information is buried in PDFs with inconsistent layouts. Important data commonly includes:

- project name and project category;
- estimated total project cost;
- fixed capital and working capital;
- machinery/equipment lists and costs;
- raw-material requirements;
- manpower and salary assumptions;
- infrastructure requirements;
- production capacity;
- sales/revenue assumptions;
- cost and profit assumptions;
- break-even or payback information when available;
- licenses or compliance references explicitly mentioned by the source;
- year/version/context of the source document.

A person can read a few project reports manually. A person cannot efficiently compare hundreds or thousands of reports with consistent criteria. The project therefore needs a corpus-building pipeline, not merely a summarizer.

The software problem can be stated as:

> Discover government MSME project records and their documents, preserve the original source files, extract useful business facts with evidence, normalize the facts into a common representation, validate internal consistency, store the result in a queryable local database, and expose the corpus to a local AI assistant that answers questions from retrieved structured data rather than inventing unsupported facts.

---

# 3. Goals

## 3.1 Functional goals

The system shall:

1. Dynamically discover project records from the PMEGP/KVIC source instead of assuming a permanent count of 1,024.
2. Associate one project with zero, one or many source documents.
3. Download source documents with retries and integrity checks.
4. Preserve the original PDF or other downloaded artifact unchanged.
5. Extract text and page metadata from text-based PDFs.
6. Detect pages that require OCR and OCR only those pages.
7. Extract useful tables when the normal PDF structure allows it.
8. Normalize important business facts into canonical fields and units.
9. Preserve page-level evidence for every important extracted value.
10. Store data in PostgreSQL in a form that supports deterministic filtering.
11. Validate arithmetic relationships without changing the source value.
12. Use a local LLM only where semantic interpretation is useful.
13. Use the local LLM to understand user questions and explain retrieved results.
14. Prevent the LLM from inventing project facts or treating old assumptions as current market truth.
15. Produce human-readable Markdown/JSON reports for individual projects.
16. Support repeatable reprocessing when extraction logic improves.

## 3.2 Learning goals

The project is also intended to teach practical skills in:

- Python application structure;
- web discovery and crawling;
- resilient HTTP downloading;
- PDF and OCR processing;
- data normalization;
- relational data modelling;
- deterministic validation;
- local LLM integration;
- structured LLM outputs;
- safe query generation;
- automated testing;
- incremental software delivery using Codex.

---

# 4. Explicit Non-Goals for the First Build

The first build will not attempt to:

- build a polished production dashboard;
- use microservices, Kubernetes, Kafka or distributed workers;
- deploy to AWS, Azure or another cloud;
- use paid AI APIs;
- use proprietary PDF extraction services;
- crawl every government repository in the first milestone;
- determine whether a business is objectively the "best" business;
- claim that a project is currently profitable merely because a historical DPR contains a profit estimate;
- claim that a business is "trending in 2026" using only old government DPRs;
- provide live machinery pricing, commodity prices or competitor intelligence in Version 1;
- build a sophisticated recommendation score before the corpus is trustworthy.

These capabilities can be added later. The first objective is a correct, evidence-backed corpus and a useful local query assistant.

---

# 5. Source Truth, Current Truth and the Meaning of "Trending"

A core design rule is that government project documents and current market conditions are different information classes.

## 5.1 Source truth

A source document can support statements such as:

- "The project report states a total project cost of INR 18.4 lakh."
- "The report lists six employees."
- "The report estimates annual sales of INR 42 lakh."
- "The report contains a machinery subtotal of INR 7.8 lakh."

These are document-backed facts or assumptions.

## 5.2 Current truth

A question such as "What businesses are trending in 2026?" cannot be answered accurately from historical DPRs alone. A future current-market layer would need dated external signals such as official production statistics, registrations, procurement demand, import/export changes, industry reports, scheme changes, search-interest data or other current evidence.

Therefore the application shall enforce this rule:

> Version 1 may compare government project profiles and their assumptions. It must not label a business as currently trending unless a later market-signal layer provides current, dated evidence for that conclusion.

When current-market data is not available, the assistant should say so and offer corpus-based alternatives such as "projects below INR 20 lakh in food processing" or "projects with low stated manpower requirements".

---

# 6. Progressive Scale Strategy: 20 -> 100 -> Full Corpus

The project will not begin by processing every currently visible business.

## 6.1 Stage A: 20-business learning corpus

Purpose:

- prove discovery;
- prove download and project-document association;
- identify real PDF layout patterns;
- establish the canonical data dictionary;
- create golden tests;
- prove evidence tracking;
- measure extraction accuracy;
- validate local LLM integration.

The 20 records should be deterministic and reasonably varied. The preferred mechanism is a repeatable sample manifest, not a random sample that changes every run.

Example:

```text
config/sample_20.json
```

The file can contain stable project identifiers or canonical URLs selected from discovery output.

## 6.2 Stage B: 100-business pilot corpus

Purpose:

- reveal layout and terminology variation not present in the first 20;
- test retry/resume behaviour;
- test performance and database indexes;
- measure failure rates;
- improve extraction fallbacks;
- verify that the schema does not overfit the initial sample.

## 6.3 Stage C: all currently discovered projects

The final Version 1 run processes every project currently discovered from the source. The count may be approximately 1,024 now, but the implementation must never use `1024` as a business rule.

Correct behaviour:

```text
source website -> discover N records -> process N records
```

Incorrect behaviour:

```text
for i in range(1024):
    ...
```

A changed site may contain 1,010, 1,024, 1,100 or another number later. Discovery determines the current count.

---

# 7. Architecture Principles

The following principles are non-negotiable unless deliberately changed in the project decision log.

1. **Original source artifacts are immutable.** Never rewrite a downloaded PDF.
2. **The document is the source of document facts.** An LLM is not the source of truth.
3. **Extract once, query many times.** User questions should query structured data, not re-read all PDFs.
4. **Evidence is first-class.** Important values must point back to the document and page where they were found.
5. **Missing means missing.** Return `NULL`/unknown instead of guessing.
6. **Contradictions remain visible.** Validation produces warnings; it does not silently repair source numbers.
7. **Deterministic logic first.** Use ordinary code for downloading, hashing, number parsing, unit conversion, arithmetic and query execution.
8. **AI is constrained.** Use the LLM for interpretation, classification, structured extraction and explanation, not unrestricted database mutation.
9. **One simple application first.** No microservices in Version 1.
10. **Every milestone must run.** Do not accumulate half-built components that only work after a distant future phase.
11. **Scale only after correctness.** Move from 20 to 100 to the full discovered corpus only after acceptance gates pass.
12. **No paid runtime dependency.** Local operation must remain possible without usage-based paid services.

---

# 8. High-Level Architecture

## 8.1 Component view

```text
+------------------------------------------------------------+
|                    LOCAL APPLICATION                       |
|                                                            |
|  +--------------+      +-------------------------------+   |
|  | Source       |----->| Discovery / Manifest          |   |
|  | Adapter      |      +---------------+---------------+   |
|  +--------------+                      |                   |
|                                        v                   |
|                              +--------------------+        |
|                              | Downloader         |        |
|                              | retry/hash/MIME    |        |
|                              +---------+----------+        |
|                                        |                   |
|                          +-------------+--------------+    |
|                          |                            |    |
|                          v                            v    |
|                    Raw PDF store                PostgreSQL  |
|                          |                            ^    |
|                          v                            |    |
|                   PDF Processor ---------------------+    |
|                 text/tables/OCR/evidence                  |
|                          |                                 |
|                          v                                 |
|                 Normalizer + Validator                    |
|                          |                                 |
|                          v                                 |
|                    Local LLM adapter                       |
|                                                            |
|  User -> Query Assistant -> validated filters -> SQL ------+|
|                  -> retrieved projects -> explanation       |
+------------------------------------------------------------+
```

## 8.2 Why this is intentionally simple

The application can be implemented as one Python repository and one PostgreSQL database. The local model server is a separate local process because model runtimes naturally run as a local service, but it is not a business microservice and does not require independent deployment logic.

There is no message broker, workflow engine, container orchestration platform or separate vector database in the first build.

---

# 9. End-to-End Data Flow

For each source project:

1. Source adapter discovers the project listing.
2. Discovery records a canonical project/source record and all discovered document links.
3. Downloader retrieves each document.
4. SHA-256 is calculated from the downloaded bytes.
5. The raw artifact is stored in a content-addressed path.
6. The document is classified as text, scanned, mixed or unsupported.
7. Text is extracted page by page.
8. Tables are extracted using the simple extraction strategy.
9. OCR is invoked only on pages that require it.
10. Deterministic parsers normalize obvious numeric values and units.
11. The local LLM receives only relevant extracted content and returns strict structured JSON.
12. The application validates the LLM response against a Pydantic schema.
13. Facts and evidence are persisted.
14. Deterministic validation checks arithmetic and cross-field relationships.
15. The project becomes queryable.
16. Reports can be generated from database data without reopening every PDF.

---

# 10. Repository and Source Adapter Design

Version 1 will define a source-adapter interface but implement only PMEGP/KVIC initially.

```python
from abc import ABC, abstractmethod
from collections.abc import Iterable

class SourceAdapter(ABC):
    @abstractmethod
    def discover_projects(self) -> Iterable["ProjectCandidate"]:
        ...

    @abstractmethod
    def discover_documents(self, project: "ProjectCandidate") -> Iterable["DocumentCandidate"]:
        ...

    @abstractmethod
    def canonicalize_url(self, url: str) -> str:
        ...
```

The processing core must not contain PMEGP-specific HTML selectors. PMEGP-specific selectors belong in `sources/pmegp.py`.

A project candidate should contain only discovery metadata, for example:

```python
class ProjectCandidate(BaseModel):
    source_key: str
    external_project_id: str | None
    title: str
    page_url: str
    category_hint: str | None = None
```

A document candidate should contain:

```python
class DocumentCandidate(BaseModel):
    source_key: str
    project_source_key: str
    url: str
    title: str | None = None
    declared_type: str | None = None
```

---

# 11. Discovery and Manifest

Discovery is separated from downloading.

The output of discovery is a persistent manifest. This allows the project to answer basic questions before downloading anything:

- how many project records were found;
- how many document links were found;
- which project has multiple documents;
- which URLs are new since the previous run;
- which source records disappeared or changed.

Recommended command:

```bash
python -m msmeintel discover --source pmegp
```

Useful options:

```bash
python -m msmeintel discover --source pmegp --limit 20
python -m msmeintel discover --source pmegp --sample config/sample_20.json
```

The manifest should include at least:

```text
source_key
external_project_id
project_title
project_page_url
canonical_project_page_url
document_url
document_title
first_seen_at
last_seen_at
```

The source adapter should use conservative request rates and must not bypass authentication, CAPTCHA or access controls.

---

# 12. Download and Raw Artifact Storage

## 12.1 Download requirements

The downloader shall:

- use a finite connect/read timeout;
- use retry with exponential backoff for transient errors;
- use a stable descriptive User-Agent;
- respect conservative concurrency;
- validate HTTP status;
- validate MIME type and/or file signature;
- compute SHA-256 after download;
- write through a temporary file and atomically move the completed file;
- record the failure reason when a document cannot be downloaded;
- skip an already downloaded identical artifact unless re-download is explicitly requested.

## 12.2 Storage layout

```text
data/
  raw/
    aa/
      <sha256>.pdf
    ab/
      <sha256>.pdf
  work/
  reports/
```

The two-character prefix prevents one directory from containing every file.

## 12.3 Project-to-document relationship

The schema must allow:

```text
Project A -> PDF 1
Project A -> PDF 2
Project A -> PDF 3
```

and also:

```text
Project A -> shared PDF X
Project B -> shared PDF X
```

Therefore `projects` must not have a single `source_document_id` column as its only document relationship. Use a `project_documents` association table.

---

# 13. Document Classification

Each document should be classified before extraction.

Recommended document states:

```text
TEXT_PDF
SCANNED_PDF
MIXED_PDF
CORRUPTED
UNSUPPORTED
```

Page-level detection is more useful than document-level detection. A mixed PDF may contain normal text pages and scanned annexures.

A simple page classification rule can consider:

- extracted character count;
- extracted word count;
- ratio of visible page area covered by text boxes;
- presence of embedded images;
- extraction exceptions.

Do not make the classifier overly sophisticated initially. The 20-document sample should determine whether the simple rule is sufficient.

---

# 14. PDF Text and Layout Extraction

Primary tools:

- `pypdf` for lightweight PDF operations and metadata;
- `pdfplumber` for text, words, bounding boxes and basic table extraction.

Per page, persist or make available to downstream processing:

```text
page_number
text
word_count
extraction_method
ocr_used
ocr_confidence (nullable)
page_width
page_height
```

Word-level coordinates may be retained in JSON only when required for evidence or table reconstruction. Version 1 does not need to normalize every word into a separate database row.

---

# 15. OCR Strategy

OCR is a fallback, not the default.

Recommended flow:

```text
extract normal text
      |
      v
sufficient text?
  | yes           | no
  v               v
continue      render page image
                  |
                  v
             Tesseract OCR
                  |
                  v
           extracted OCR text
```

Requirements:

- OCR only the pages that need it.
- Store whether text came from native extraction or OCR.
- Store OCR confidence when available.
- Do not overwrite the native extracted text; preserve both when comparison is useful.
- Allow an OCR page to be reprocessed when OCR settings change.

---

# 16. Table Extraction Strategy

The first implementation should avoid an elaborate cascade of table engines.

## 16.1 Initial strategy

1. Attempt `pdfplumber` table extraction.
2. Apply basic quality checks.
3. If a clearly important table fails, optionally attempt Camelot for text PDFs.
4. For scanned pages, use OCR text/coordinates and either a basic reconstruction method or mark the table for review.
5. Do not introduce Docling or another large parsing framework until real samples demonstrate that it is necessary.

## 16.2 Quality checks

A candidate table can be evaluated using:

- stable column count;
- low excessive-empty-cell ratio;
- header detection;
- numeric parsing ratio for financial tables;
- repeated-cell anomalies;
- agreement between extracted subtotal and visible total where applicable.

## 16.3 Storage

Do not create one database row per table cell in the first build unless the need becomes clear. A simpler design is:

```text
extracted_tables
  id
  document_id
  page_number
  table_index
  extraction_method
  confidence
  title
  data_jsonb
  raw_text
```

Important values extracted from the table are still stored as individual project facts with evidence references.

---

# 17. Canonical Business Data Dictionary

The first 20 businesses will be used to refine this dictionary. The implementation must support unknown fields without forcing the system to invent values.

## 17.1 Identity and classification

Canonical fields:

```text
project_name
project_alias
project_type
sector
subsector
business_description
source_document_year
location_context
```

`project_type` should use a controlled value where possible:

```text
manufacturing
service
processing
agriculture_linked
mixed
unknown
```

## 17.2 Capital and financial facts

```text
total_project_cost_inr
fixed_capital_inr
land_cost_inr
building_cost_inr
machinery_cost_inr
other_fixed_assets_inr
working_capital_inr
annual_revenue_inr
annual_expense_inr
annual_profit_inr
break_even_percent
payback_years
irr_percent
npv_inr
```

The system must not derive IRR, NPV or payback if the source does not provide enough information unless a later analysis feature explicitly computes a separate derived value and clearly labels it as derived.

## 17.3 Operations

```text
working_days_per_year
shifts_per_day
hours_per_shift
capacity_utilization_percent
annual_capacity_value
annual_capacity_unit
power_requirement_kw
water_requirement
fuel_requirement
land_area_sqft
built_up_area_sqft
```

## 17.4 Human resources

```text
employee_count_total
managerial_count
skilled_worker_count
unskilled_worker_count
monthly_payroll_inr
annual_payroll_inr
```

Role-level details may be stored in a structured JSON list.

## 17.5 Products

Each product record may contain:

```text
name
specification
unit
annual_capacity
selling_price_inr
annual_sales_inr
```

## 17.6 Machinery

Each machinery item may contain:

```text
name
quantity
unit_cost_inr
total_cost_inr
power_kw
supplier_text_if_explicit
```

The system must never invent a supplier.

## 17.7 Raw materials

Each raw-material item may contain:

```text
name
quantity
unit
unit_price_inr
monthly_cost_inr
annual_cost_inr
```

## 17.8 Compliance

Store only compliance or certification requirements explicitly present in the source unless a later current-regulation module is added.

---

# 18. Numeric and Unit Normalization

Normalization should be deterministic whenever possible.

Examples:

```text
"10 lakh"       -> 1000000 INR
"Rs. 2.5 Lacs"  -> 250000 INR
"1.2 crore"     -> 12000000 INR
"15 %"          -> 15.0 percent
"2,50,000"      -> 250000
```

Store both raw and normalized values.

Example fact:

```json
{
  "field_name": "total_project_cost_inr",
  "raw_value": "Rs. 18.50 Lakh",
  "numeric_value": 1850000,
  "unit": "INR"
}
```

Rules should handle:

- Indian comma formatting;
- lakh/lac/lacs/lakhs variants;
- crore/crores;
- rupee/Rs/INR symbols;
- percentages;
- ranges such as "8-10 lakh" without silently choosing one endpoint;
- monthly vs annual amounts;
- tonnes/kg/units/pieces where meaningful.

If a range is present, store explicit range semantics rather than replacing it with an arbitrary single value.

---

# 19. Evidence and Provenance Model

Evidence is mandatory for important facts.

Each fact should be traceable to:

```text
source document
page number
source element/table identifier when available
raw quoted/snippet text
raw value
extraction method
confidence
```

Example:

```json
{
  "field": "total_project_cost_inr",
  "value": 1850000,
  "evidence": {
    "document_sha256": "...",
    "page": 8,
    "table_index": 2,
    "raw_text": "Total Project Cost 18.50",
    "method": "pdfplumber_table",
    "confidence": 0.97
  }
}
```

Evidence snippets should be short and sufficient to verify the value. The database is not intended to duplicate the complete PDF content as evidence strings.

---

# 20. Database Design

Version 1 should remain small and understandable.

Recommended tables:

1. `sources`
2. `projects`
3. `source_project_records`
4. `documents`
5. `project_documents`
6. `document_pages`
7. `extracted_tables`
8. `facts`
9. `evidence`
10. `validation_results`
11. `processing_runs`
12. `processing_errors`

This is sufficient for the learning project. Do not add separate normalized tables for every possible domain until real data proves the need.

## 20.1 `sources`

Stores source configuration and identity.

```text
id
key
name
base_url
active
created_at
updated_at
```

## 20.2 `projects`

Represents the canonical business concept inside the local corpus.

```text
id
project_name
project_type
sector
subsector
description
canonical_key
created_at
updated_at
```

## 20.3 `source_project_records`

Represents the project as observed at a particular source.

```text
id
source_id
external_project_id
source_title
source_page_url
canonical_page_url
first_seen_at
last_seen_at
project_id nullable
```

This keeps source identity separate from canonical project identity.

## 20.4 `documents`

Represents a physical downloaded artifact.

```text
id
sha256
file_path
filename
mime_type
file_size
created_at
```

`sha256` may be unique here because this table represents the physical content artifact, not every URL observation.

## 20.5 `project_documents`

Maps projects/source records to documents.

```text
id
project_id
source_project_record_id
document_id
source_url
document_role
downloaded_at
```

## 20.6 `document_pages`

```text
id
document_id
page_number
native_text
ocr_text
text_method
ocr_used
ocr_confidence
page_width
page_height
```

## 20.7 `facts`

The `facts` table is the queryable center of the normalized corpus.

```text
id
project_id
field_name
raw_value
normalized_text
numeric_value
unit
currency
value_jsonb
confidence
extraction_method
model_name
prompt_version
created_at
```

Recommended indexes:

```text
(project_id, field_name)
(field_name, numeric_value)
(field_name, normalized_text)
```

## 20.8 `evidence`

```text
id
fact_id
document_id
page_number
table_id nullable
snippet
bbox_jsonb nullable
created_at
```

## 20.9 `validation_results`

```text
id
project_id
rule_key
status
message
expected_value nullable
observed_value nullable
details_jsonb
created_at
```

## 20.10 `processing_runs`

```text
id
run_type
started_at
finished_at
status
code_version
parser_version
schema_version
model_name
prompt_version
metrics_jsonb
```

---

# 21. Database DDL Sketch

```sql
CREATE TABLE sources (
    id BIGSERIAL PRIMARY KEY,
    key TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    base_url TEXT,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE projects (
    id BIGSERIAL PRIMARY KEY,
    project_name TEXT NOT NULL,
    project_type TEXT,
    sector TEXT,
    subsector TEXT,
    description TEXT,
    canonical_key TEXT UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE source_project_records (
    id BIGSERIAL PRIMARY KEY,
    source_id BIGINT NOT NULL REFERENCES sources(id),
    external_project_id TEXT,
    source_title TEXT NOT NULL,
    source_page_url TEXT NOT NULL,
    canonical_page_url TEXT NOT NULL,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    project_id BIGINT REFERENCES projects(id),
    UNIQUE(source_id, canonical_page_url)
);

CREATE TABLE documents (
    id BIGSERIAL PRIMARY KEY,
    sha256 TEXT NOT NULL UNIQUE,
    file_path TEXT NOT NULL,
    filename TEXT,
    mime_type TEXT,
    file_size BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE project_documents (
    id BIGSERIAL PRIMARY KEY,
    project_id BIGINT REFERENCES projects(id),
    source_project_record_id BIGINT NOT NULL REFERENCES source_project_records(id),
    document_id BIGINT NOT NULL REFERENCES documents(id),
    source_url TEXT NOT NULL,
    document_role TEXT,
    downloaded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(source_project_record_id, source_url, document_id)
);

CREATE TABLE document_pages (
    id BIGSERIAL PRIMARY KEY,
    document_id BIGINT NOT NULL REFERENCES documents(id),
    page_number INTEGER NOT NULL,
    native_text TEXT,
    ocr_text TEXT,
    text_method TEXT NOT NULL,
    ocr_used BOOLEAN NOT NULL DEFAULT FALSE,
    ocr_confidence NUMERIC,
    page_width NUMERIC,
    page_height NUMERIC,
    UNIQUE(document_id, page_number)
);

CREATE TABLE extracted_tables (
    id BIGSERIAL PRIMARY KEY,
    document_id BIGINT NOT NULL REFERENCES documents(id),
    page_number INTEGER NOT NULL,
    table_index INTEGER NOT NULL,
    extraction_method TEXT NOT NULL,
    confidence NUMERIC,
    title TEXT,
    data_jsonb JSONB,
    raw_text TEXT,
    UNIQUE(document_id, page_number, table_index, extraction_method)
);

CREATE TABLE facts (
    id BIGSERIAL PRIMARY KEY,
    project_id BIGINT NOT NULL REFERENCES projects(id),
    field_name TEXT NOT NULL,
    raw_value TEXT,
    normalized_text TEXT,
    numeric_value NUMERIC,
    unit TEXT,
    currency TEXT,
    value_jsonb JSONB,
    confidence NUMERIC,
    extraction_method TEXT NOT NULL,
    model_name TEXT,
    prompt_version TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_facts_project_field ON facts(project_id, field_name);
CREATE INDEX idx_facts_numeric_query ON facts(field_name, numeric_value);

CREATE TABLE evidence (
    id BIGSERIAL PRIMARY KEY,
    fact_id BIGINT NOT NULL REFERENCES facts(id) ON DELETE CASCADE,
    document_id BIGINT NOT NULL REFERENCES documents(id),
    page_number INTEGER NOT NULL,
    table_id BIGINT REFERENCES extracted_tables(id),
    snippet TEXT,
    bbox_jsonb JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

This DDL is a starting contract, not a command to pre-design every future field.

---

# 22. Processing State Model

Processing status should be explicit and resumable.

Recommended states:

```text
DISCOVERED
DOWNLOAD_PENDING
DOWNLOADED
DOWNLOAD_FAILED
CLASSIFIED
TEXT_EXTRACTED
OCR_REQUIRED
OCR_COMPLETE
TABLES_EXTRACTED
NORMALIZED
VALIDATED
READY
REVIEW_REQUIRED
FAILED
```

A failed document must not stop the entire corpus run.

If 3 documents fail and 97 succeed, the run should finish and report the three failures.

A retry command should target failed items:

```bash
python -m msmeintel retry-failed
```

---

# 23. Local AI Architecture

The LLM is not the primary parser and does not receive every PDF at question time.

The AI has two distinct jobs.

## 23.1 Job A: semantic extraction during ingestion

Input:

- extracted page text;
- extracted tables;
- project/source identifier;
- page numbers and table identifiers;
- canonical field schema;
- extraction instructions.

Output:

- strict JSON conforming to a Pydantic model;
- `null` for unavailable fields;
- evidence references for each important field.

The application validates the returned JSON before storing it.

## 23.2 Job B: query understanding and answer explanation

At question time the LLM should not generate arbitrary SQL directly.

Safer flow:

```text
User question
    |
    v
Local LLM -> QueryIntent JSON
    |
    v
Pydantic validation
    |
    v
Deterministic query builder
    |
    v
Parameterized SQL
    |
    v
PostgreSQL results
    |
    v
Local LLM explains ONLY retrieved results
```

This design sharply reduces hallucination risk and makes the query layer testable.

---

# 24. Query Intent Contract

Example Pydantic concept:

```python
class NumericFilter(BaseModel):
    field: Literal[
        "total_project_cost_inr",
        "machinery_cost_inr",
        "working_capital_inr",
        "employee_count_total",
        "annual_revenue_inr",
        "annual_profit_inr",
        "land_area_sqft",
    ]
    operator: Literal["lt", "lte", "eq", "gte", "gt", "between"]
    value: float | None = None
    min_value: float | None = None
    max_value: float | None = None

class QueryIntent(BaseModel):
    intent: Literal["find_projects", "compare_projects", "project_detail"]
    project_type: str | None = None
    sector: str | None = None
    text_terms: list[str] = []
    numeric_filters: list[NumericFilter] = []
    limit: int = 20
```

Example user question:

```text
I want manufacturing businesses under 20 lakh with fewer than 10 employees.
```

Expected LLM output:

```json
{
  "intent": "find_projects",
  "project_type": "manufacturing",
  "sector": null,
  "text_terms": [],
  "numeric_filters": [
    {
      "field": "total_project_cost_inr",
      "operator": "lte",
      "value": 2000000
    },
    {
      "field": "employee_count_total",
      "operator": "lt",
      "value": 10
    }
  ],
  "limit": 20
}
```

The database query is generated by application code, not copied from free-form LLM SQL.

---

# 25. Query Builder Rules

The query builder shall:

- accept only allow-listed fields;
- accept only allow-listed operators;
- use bound SQL parameters;
- reject unsupported fields;
- cap result count;
- record the interpreted query intent for debugging;
- never allow the LLM to send raw database mutation statements;
- keep query execution read-only in the user-assistant path.

Example conceptual SQL for a budget filter:

```sql
SELECT p.id, p.project_name
FROM projects p
WHERE EXISTS (
    SELECT 1
    FROM facts f
    WHERE f.project_id = p.id
      AND f.field_name = 'total_project_cost_inr'
      AND f.numeric_value <= :max_cost
)
ORDER BY p.project_name
LIMIT :limit;
```

---

# 26. Answer Generation Rules

The final answer generator receives only the retrieved project records and selected supporting facts/evidence.

The final answer must distinguish:

- source-reported values;
- calculated validation differences;
- missing values;
- current-market claims, which are unavailable in Version 1 unless a dated market-signal source exists.

Example wording:

```text
The PMEGP project profile reports an estimated total project cost of INR 18.5 lakh.
The stored corpus does not establish whether that cost is current in 2026.
```

Do not transform a source assumption into a current fact.

---

# 27. Example Questions and How the System Should Answer

## 27.1 Budget query

Question:

```text
What businesses can I start below 10 lakh?
```

System behaviour:

1. Interpret 10 lakh as INR 1,000,000.
2. Query `total_project_cost_inr <= 1000000`.
3. Return matching projects.
4. Present source-reported project cost, sector and selected requirements.
5. Mention missing fields rather than inventing them.
6. State that source project costs may be historical.

## 27.2 Multi-constraint query

Question:

```text
Show manufacturing businesses under 20 lakh that need less than 10 people and low machinery investment.
```

`low machinery investment` is ambiguous. The assistant should either ask for a threshold or, if a documented application default exists, clearly apply that default. The first version should prefer asking for the missing numeric threshold rather than creating one silently.

## 27.3 Comparison query

Question:

```text
Compare spice grinding, paper bags and bakery.
```

The assistant retrieves only those projects, returns comparable known fields, and clearly marks unavailable values.

## 27.4 Current trend query

Question:

```text
What is trending in 2026?
```

Version 1 response should explain that the government corpus alone does not establish current trends and offer a corpus-based alternative. Phase 2 can answer this only after current market signals are integrated.

---

# 28. Deterministic Validation Engine

Validation is separate from extraction.

Recommended initial rules:

| Rule | Check | Behaviour |
|---|---|---|
| Project cost reconciliation | sum of declared capital components vs reported total | warning when outside tolerance |
| Machinery subtotal | sum of machinery line items vs reported machinery total | warning |
| Revenue consistency | capacity x selling price vs stated sales when dimensions permit | warning |
| Profit consistency | revenue - known expenses vs reported profit when comparable | warning |
| Working capital subtotal | component sum vs reported working capital | warning |
| Manpower total | role counts vs stated employee total | warning |

Statuses:

```text
PASS
WARNING
ERROR
NOT_CHECKABLE
```

`NOT_CHECKABLE` is important. Missing source information is not automatically an error.

The validator must never overwrite a source-reported value.

---

# 29. Confidence Model

Confidence is metadata, not truth.

Possible confidence sources:

- extraction method;
- OCR confidence;
- table quality score;
- deterministic parser certainty;
- LLM structured-output confidence if the model/runtime supports a useful signal;
- evidence completeness;
- agreement between two extraction paths.

A simple Version 1 policy is sufficient:

```text
HIGH    >= 0.90
MEDIUM  >= 0.70 and < 0.90
LOW     < 0.70
```

Do not spend early effort building a mathematically elaborate confidence model. The purpose is to route uncertain records to review and to make uncertainty visible.

---

# 30. Deduplication

Three identities must be kept separate:

1. source project record;
2. physical document artifact;
3. canonical project concept.

Version 1 deduplication priorities:

## 30.1 Exact document deduplication

Use SHA-256.

## 30.2 URL deduplication

Canonicalize query strings/fragments only where safe and source-specific.

## 30.3 Project concept deduplication

Do not make semantic project merging a blocking requirement for the 20-project milestone. Start with normalized names and manual review. More advanced similarity can be added after the corpus works.

---

# 31. Search Strategy

Version 1 search priority:

1. structured numeric filtering;
2. exact/normalized project-name lookup;
3. PostgreSQL full-text search over names/descriptions;
4. optional semantic search later.

Vector search is not required for the first usable milestone.

Questions such as "under INR 20 lakh" are structured filters, not embedding problems.

Semantic search becomes useful later for questions such as:

```text
projects similar to PCB assembly
small B2B engineering businesses
businesses related to packaging
```

---

# 32. Local Model Runtime

The simplest recommended runtime is Ollama because it is easy to install and exposes a local HTTP API. `llama.cpp` is a valid alternative if lower-level control is preferred.

Rules:

- no external paid API is required;
- model name is configuration, not hard-coded in business logic;
- the selected model checkpoint's license must be verified separately from the runtime license;
- store model name and prompt version with AI-generated facts;
- extraction prompts must use deterministic/low-variance settings where supported;
- model failure must not corrupt existing data.

Configuration example:

```yaml
llm:
  provider: ollama
  base_url: http://localhost:11434
  model: <verified-local-model>
  temperature: 0
  timeout_seconds: 120
```

The first model selection should be based on the user's available RAM/VRAM and the quality observed on the 20-document golden set. Do not design the entire architecture around one model family.

---

# 33. Technology Stack

| Concern | Initial choice | Reason |
|---|---|---|
| Runtime | Python 3.12+ | broad PDF/AI/data ecosystem |
| Dependency management | `uv` | fast local Python environment management |
| HTTP | `httpx` | modern sync/async client |
| HTML parsing | BeautifulSoup + lxml | simple source discovery |
| PDF text/layout | pypdf + pdfplumber | lightweight and proven |
| OCR | Tesseract | local open-source OCR |
| PDF rendering | pypdfium2 | page rendering for OCR |
| Table extraction | pdfplumber first; Camelot only if needed | avoid unnecessary complexity |
| Validation/schema | Pydantic | strict data contracts |
| Database | PostgreSQL | reliable local relational store and future growth path |
| ORM/migrations | SQLAlchemy + Alembic | controlled schema evolution |
| CLI | Typer | simple developer/operator interface |
| Local LLM | Ollama or llama.cpp | local inference |
| Tests | pytest | unit/integration/golden tests |
| Reports | Markdown + JSON | simple, diffable output |
| UI | none initially; optional Streamlit later | keep core pipeline first |

No Docker dependency is required for the first build. Docker/Podman can be added later if the user wants reproducible packaging.

---

# 34. License Policy

The requirement should be stated as:

> The project shall require no paid runtime service, no proprietary SaaS dependency and no commercial license purchase for the intended learning/local use. Every software dependency and model checkpoint must still have its actual license recorded and reviewed.

Maintain:

```text
THIRD_PARTY_LICENSES.md
```

For every runtime dependency record:

```text
name
version
license
source URL
purpose in project
```

Model checkpoints must be recorded separately because the model's license may differ from the model-serving runtime.

---

# 35. Repository Structure

Recommended repository:

```text
msme-project-intelligence/
|
|-- AGENTS.md
|-- README.md
|-- pyproject.toml
|-- uv.lock
|-- .env.example
|-- THIRD_PARTY_LICENSES.md
|
|-- .agent/
|   |-- PLANS.md
|   `-- plans/
|
|-- config/
|   |-- app.yaml
|   `-- sample_20.json
|
|-- docs/
|   |-- TECHNICAL_SPEC.md
|   |-- IMPLEMENTATION_ROADMAP.md
|   |-- DATA_DICTIONARY.md
|   |-- DECISIONS.md
|   `-- TEST_STRATEGY.md
|
|-- src/
|   `-- msmeintel/
|       |-- __init__.py
|       |-- cli.py
|       |-- config.py
|       |-- logging_config.py
|       |
|       |-- sources/
|       |   |-- base.py
|       |   `-- pmegp.py
|       |
|       |-- discovery/
|       |   `-- service.py
|       |
|       |-- download/
|       |   `-- service.py
|       |
|       |-- documents/
|       |   |-- classify.py
|       |   |-- text_extract.py
|       |   |-- tables.py
|       |   `-- ocr.py
|       |
|       |-- normalization/
|       |   |-- money.py
|       |   |-- units.py
|       |   `-- service.py
|       |
|       |-- ai/
|       |   |-- provider.py
|       |   |-- ollama_provider.py
|       |   |-- schemas.py
|       |   `-- prompts.py
|       |
|       |-- validation/
|       |   `-- rules.py
|       |
|       |-- query/
|       |   |-- intent.py
|       |   |-- builder.py
|       |   `-- answer.py
|       |
|       |-- db/
|       |   |-- models.py
|       |   |-- session.py
|       |   `-- repositories.py
|       |
|       `-- reports/
|           `-- markdown.py
|
|-- migrations/
|
|-- tests/
|   |-- unit/
|   |-- integration/
|   |-- golden/
|   `-- fixtures/
|
`-- data/
    |-- raw/
    |-- work/
    `-- reports/
```

The repository should remain understandable to one developer. Avoid introducing abstract layers that do not solve an observed problem.

---

# 36. Configuration

Configuration belongs outside business logic.

Example:

```yaml
app:
  data_dir: ./data
  log_level: INFO

source:
  pmegp:
    enabled: true
    request_delay_seconds: 1.0
    timeout_seconds: 30

processing:
  ocr_min_native_chars: 80
  max_pdf_mb: 50
  table_min_confidence: 0.60

llm:
  enabled: true
  provider: ollama
  base_url: http://localhost:11434
  model: <local-model>
  temperature: 0

database:
  url_env: DATABASE_URL
```

Secrets, if any, are stored in environment variables and are never committed.

---

# 37. Command-Line Interface

The CLI is the first operator interface.

Recommended commands:

```bash
python -m msmeintel source list
python -m msmeintel discover --source pmegp --limit 20
python -m msmeintel download --source pmegp --limit 20
python -m msmeintel process --limit 20
python -m msmeintel normalize --limit 20
python -m msmeintel validate --limit 20
python -m msmeintel query "manufacturing businesses under 20 lakh"
python -m msmeintel project show <project-id>
python -m msmeintel report <project-id>
python -m msmeintel retry-failed
python -m msmeintel run --sample config/sample_20.json
```

Commands should reuse service-layer functions rather than contain the business logic directly.

---

# 38. Logging and Observability

Do not build a monitoring platform. Use structured local logs and run summaries.

Each run should report:

```text
projects discovered
document URLs discovered
downloads attempted/succeeded/failed
documents classified
pages OCR'd
tables extracted
projects normalized
facts created
validation warnings
review-required items
elapsed time
```

Errors should include:

```text
run_id
project/source record ID
document ID or URL
pipeline stage
exception type
short message
retryable yes/no
```

---

# 39. Security and Safe Document Handling

Downloaded documents are untrusted input.

Requirements:

- do not execute embedded attachments or scripts;
- validate actual file type;
- enforce maximum file size;
- use safe temporary directories;
- prevent path traversal from filenames;
- do not use a source-provided filename as a filesystem path without sanitization;
- enforce processing timeouts where practical;
- do not bypass source authentication or access controls;
- preserve source URL and acquisition timestamp.

---

# 40. Testing Strategy

Testing is a required part of every milestone, not a final phase.

## 40.1 Unit tests

Initial unit-test targets:

- URL canonicalization;
- Indian currency parsing;
- lakh/crore normalization;
- percentage parsing;
- MIME/file-signature checks;
- SHA-256 storage path;
- page OCR decision rule;
- Pydantic extraction schemas;
- query-intent validation;
- safe query builder;
- financial reconciliation rules.

## 40.2 Golden corpus

Create a checked-in manifest describing approximately 10 representative documents from the 20-business sample. The actual source PDFs may remain outside Git if appropriate, but test fixtures/expected outputs must be reproducible.

For each golden document record expected values such as:

```text
project_name
total_project_cost_inr
machinery_cost_inr
working_capital_inr
employee_count_total
annual_capacity when available
annual_revenue when available
annual_profit when available
source page(s)
```

The golden set is the main defence against silent extraction regression.

## 40.3 Integration tests

Required flows:

```text
discovery -> manifest
download -> hash/store
PDF -> page text
OCR fallback -> page text
text/table -> structured facts
fact -> evidence
facts -> validation
query intent -> parameterized SQL
query results -> explanation context
```

## 40.4 Test data principle

Do not make tests depend on the live government website unless explicitly marked as live/integration tests. Most tests should use local saved fixtures so CI/local execution remains repeatable.

---

# 41. Acceptance Metrics for the 20-Business Milestone

The first corpus milestone is accepted only when:

1. 20 intended source project records are deterministically selected.
2. Every discovered document link is associated with the correct source project record.
3. At least 95% of reachable documents download successfully, with failures reported rather than hidden.
4. Every downloaded artifact has a SHA-256 hash and immutable file path.
5. All pages have extraction status.
6. Scanned pages trigger OCR instead of producing silently empty text.
7. At least the core fields below are attempted for every project:
   - project name;
   - project type/sector when present;
   - total project cost;
   - machinery cost;
   - working capital;
   - manpower;
   - annual revenue/profit when present.
8. Every stored core financial fact has a source page reference.
9. Missing values remain null/absent.
10. Validation warnings do not rewrite source values.
11. The query assistant can correctly answer a small fixed evaluation set.
12. Unit and integration tests pass.
13. Re-running the same sample does not create uncontrolled duplicate records.

Only after these conditions are met should the corpus be expanded to 100.

---

# 42. Evaluation Questions for the Assistant

Create a fixed set of evaluation questions such as:

```text
1. Which projects in the sample have total project cost below INR 20 lakh?
2. Which manufacturing projects have fewer than 10 employees?
3. Which projects have machinery cost below INR 5 lakh?
4. Compare the total project cost and manpower of project A and project B.
5. What source page supports the stored project cost for project C?
6. Which fields are missing for project D?
7. Does project E's machinery subtotal reconcile with its line items?
8. What businesses are trending in 2026?
```

Question 8 is intentionally included. The expected Version 1 behaviour is to decline to infer current trend from the corpus alone and explain the missing current-market evidence.

---

# 43. Implementation Roadmap

The roadmap is deliberately milestone-based. Codex should complete exactly one milestone at a time.

## Milestone 0 - Repository contract and executable skeleton

Deliverables:

- repository structure;
- `pyproject.toml`;
- application configuration loader;
- logging setup;
- Typer CLI with `--help`;
- PostgreSQL connection configuration;
- SQLAlchemy base and Alembic initialized;
- initial health/test command;
- test framework;
- `README.md` setup instructions;
- `THIRD_PARTY_LICENSES.md` initial entries.

Acceptance gate:

```text
uv run pytest
uv run python -m msmeintel --help
```

must work.

Do not implement the PMEGP crawler yet.

## Milestone 1 - PMEGP discovery and sample manifest

Deliverables:

- `SourceAdapter` interface;
- `PMEGPAdapter`;
- project discovery;
- document-link discovery;
- canonical URL logic;
- persistent source/project manifest;
- `--limit` and `--sample` support;
- discovery fixtures and tests.

Acceptance gate:

- deterministic discovery of the 20-business sample;
- project/document associations visible in a report;
- rerun updates timestamps without duplicating records.

## Milestone 2 - Downloader and immutable raw store

Deliverables:

- retry/backoff;
- MIME/signature checks;
- SHA-256;
- content-addressed storage;
- download status/error persistence;
- retry-failed behaviour.

Acceptance gate:

- all reachable sample documents stored;
- duplicate bytes stored once;
- repeated run is idempotent.

## Milestone 3 - PDF classification and text extraction

Deliverables:

- page enumeration;
- native text extraction;
- page metadata;
- text/scanned/mixed classification;
- persistence of page text;
- extraction tests.

Acceptance gate:

- every sample page gets an extraction status;
- normal text PDFs produce usable page text.

## Milestone 4 - OCR and basic tables

Deliverables:

- OCR decision rule;
- pypdfium2 page rendering;
- Tesseract OCR;
- pdfplumber table extraction;
- basic table quality score;
- optional Camelot fallback only if sample evidence justifies it.

Acceptance gate:

- scanned sample pages produce text;
- selected financial tables are extracted sufficiently to recover expected golden values.

## Milestone 5 - Canonical facts, evidence and validation

Deliverables:

- currency/unit normalization;
- facts/evidence persistence;
- project schema;
- deterministic validation rules;
- Markdown project report.

Acceptance gate:

- core fields extracted for golden sample;
- source page evidence displayed in report;
- validation warnings are correct and non-destructive.

## Milestone 6 - Local LLM structured extraction

Deliverables:

- LLM provider interface;
- Ollama adapter;
- strict Pydantic output schema;
- versioned extraction prompt;
- retry/error behaviour;
- LLM audit metadata;
- tests with mocked model responses plus selected real local-model evaluation.

Acceptance gate:

- invalid model JSON is rejected;
- missing values remain null;
- evidence references are required for core numeric fields;
- model does not write directly to the database.

## Milestone 7 - Query assistant

Deliverables:

- `QueryIntent` schema;
- local LLM intent parser;
- deterministic safe query builder;
- read-only SQL execution;
- result formatter;
- answer-generation prompt restricted to retrieved records;
- query CLI.

Acceptance gate:

- fixed evaluation questions pass;
- no arbitrary LLM SQL execution;
- current-trend question is handled with the required limitation.

## Milestone 8 - Scale from 20 to 100

Deliverables:

- run on 100 discovered projects;
- extraction failure report;
- schema/normalization updates driven by observed variation;
- performance metrics;
- golden-set regression.

Acceptance gate:

- no regression on 20-project golden set;
- known failures are classified and retryable/reviewable;
- pipeline remains resumable.

## Milestone 9 - Full dynamic corpus

Deliverables:

- process all currently discovered PMEGP projects;
- final run summary;
- searchable complete local corpus;
- corpus export/report;
- documented unresolved exceptions.

Acceptance gate:

- full run completes without one failed document aborting the job;
- query assistant operates on the full corpus;
- result claims remain evidence-backed.

---

# 44. What Codex Must Not Do

Codex should be explicitly instructed not to:

- implement multiple future milestones in one turn unless requested;
- replace the chosen architecture with a new framework without approval;
- add a cloud service because it is convenient;
- add paid APIs;
- add microservices, queues or distributed workers without a demonstrated need;
- remove evidence/provenance to simplify the code;
- let an LLM execute unrestricted SQL;
- silently repair inconsistent source financial values;
- hard-code the number 1,024 as the source count;
- hard-code a specific local model into business logic;
- swallow exceptions without recording the failed stage;
- mark a milestone complete before its acceptance commands/tests pass;
- perform an unrelated repository-wide refactor during a focused milestone;
- change database schema outside a migration;
- delete raw documents during reprocessing.

---

# 45. Codex Handoff Strategy

A long Word document should not be pasted into every Codex prompt. Keep the authoritative engineering information inside the repository as Markdown.

Recommended hierarchy:

```text
AGENTS.md
    -> short, always-applicable repository rules

docs/TECHNICAL_SPEC.md
    -> architecture and domain contract

docs/IMPLEMENTATION_ROADMAP.md
    -> milestone order and acceptance gates

docs/DATA_DICTIONARY.md
    -> canonical fields and normalization rules

docs/DECISIONS.md
    -> deliberate architecture decisions

.agent/PLANS.md
    -> rules for writing execution plans

.agent/plans/Mxx-*.md
    -> one concrete plan for the current milestone
```

This structure prevents two common failure modes:

1. Codex receives a giant one-off prompt and loses important constraints later.
2. `AGENTS.md` becomes so large that every small task consumes unnecessary context.

`AGENTS.md` should point Codex to the right document for the relevant type of change rather than requiring every document to be re-read for every edit.

---

# 46. Recommended `AGENTS.md`

The following should be placed at the repository root.

```markdown
# Repository Instructions

## Mission
Build the local Government MSME Project Intelligence Platform described in
`docs/TECHNICAL_SPEC.md`. The system builds an evidence-backed structured corpus
from government project documents and answers questions from retrieved data.

## Architecture boundaries
- Keep Version 1 as one Python application plus PostgreSQL and a local model runtime.
- Do not introduce cloud services, paid APIs, microservices, message brokers,
  Kubernetes, or a separate vector database unless the user explicitly approves it.
- PMEGP is the only source adapter required until the roadmap reaches additional sources.

## Data truth rules
- Raw downloaded artifacts are immutable.
- Never invent a missing value.
- Never silently rewrite contradictory source values.
- Important financial/operational facts require page-level evidence.
- Keep source-reported facts separate from validation findings and derived values.
- Never hard-code the total project count; discovery determines it dynamically.

## AI rules
- The LLM is an interpretation layer, not the source of truth.
- Validate model output with Pydantic before persistence.
- The model must not write directly to the database.
- The query assistant must not execute arbitrary LLM-generated SQL.
- Use a validated QueryIntent and deterministic parameterized query builder.
- Do not claim that a business is currently trending from historical DPR data alone.

## Development process
- Implement only the requested milestone or task.
- For complex milestones, create/update an ExecPlan in `.agent/plans/` using
  `.agent/PLANS.md` before implementation.
- Do not begin the next milestone automatically.
- Keep changes small and reviewable.
- Add or update tests with each behaviour change.
- Run the milestone acceptance commands before declaring completion.
- If a requirement is ambiguous and the choice would materially change architecture,
  stop and ask instead of guessing.

## Relevant documents
- Use `docs/TECHNICAL_SPEC.md` for architecture and pipeline behaviour.
- Use `docs/IMPLEMENTATION_ROADMAP.md` for milestone scope and acceptance gates.
- Use `docs/DATA_DICTIONARY.md` when changing extracted fields or normalization.
- Use `docs/DECISIONS.md` before changing a recorded architecture decision.
- Use `.agent/PLANS.md` for significant multi-step implementation work.

## Completion report
At the end of an implementation task, report:
1. files changed;
2. behaviour implemented;
3. tests/commands run and results;
4. acceptance criteria satisfied;
5. known limitations or blockers;
6. whether any dependency/schema/configuration changed.
```

---

# 47. Recommended `.agent/PLANS.md`

```markdown
# Execution Plans

Use an ExecPlan for each milestone or any change that spans multiple modules,
requires a database migration, or changes the ingestion/query architecture.

Each ExecPlan must be self-contained and stored in `.agent/plans/`.

Required sections:

## Goal
State the user-visible or pipeline behaviour to deliver.

## In scope
List exactly what this plan will implement.

## Out of scope
List adjacent work that must not be started.

## Existing code/context inspected
List the repository files that were actually inspected before planning.

## Design
Describe the minimal design and data flow. Reuse existing abstractions where possible.

## File changes
List files to create/change and the purpose of each.

## Database changes
Describe migrations, indexes and compatibility impact, or state "none".

## Implementation steps
Write ordered, independently checkable steps.

## Tests
List unit/integration/golden tests to add or update.

## Acceptance commands
List exact commands that must pass.

## Risks and open questions
Record uncertainty. Do not hide it.

## Progress
Update checkboxes as implementation proceeds.

## Outcome
After implementation, record what was completed, deviations from plan, test results
and unresolved follow-up work.
```

---

# 48. Codex Session Protocol

For every significant milestone, use this sequence.

## Step 1 - Start with planning only

Prompt Codex to inspect the relevant current repository state and produce the milestone ExecPlan. Do not ask it to code in the same first message.

## Step 2 - Review the plan

Check:

- Does it stay inside the milestone?
- Did it add unnecessary technologies?
- Does it preserve provenance?
- Does it contain tests and acceptance commands?
- Does it propose a schema migration when needed?
- Does it explicitly say what is out of scope?

If the plan is wrong, fix the plan before code exists.

## Step 3 - Implement only the approved plan

Tell Codex to execute the plan, update the plan's progress section and stop after the acceptance gate.

## Step 4 - Ask for verification, not more features

Have Codex review the diff, run tests, and identify any mismatch against the milestone acceptance criteria.

## Step 5 - Commit/checkpoint

After the milestone works, make a Git checkpoint before starting the next milestone.

## Step 6 - Start a fresh Codex task for the next milestone

A fresh task keeps the objective narrow. The repository files preserve the durable context.

---

# 49. Initial Codex Prompt: Planning Only

Use this after placing the handoff files in the repository.

```text
We are starting the Government MSME Project Intelligence Platform learning project.

Read the repository root AGENTS.md. For this task, also read:
- docs/TECHNICAL_SPEC.md
- docs/IMPLEMENTATION_ROADMAP.md
- .agent/PLANS.md

Work only on Milestone 0: Repository contract and executable skeleton.

This turn is PLANNING ONLY. Do not implement code yet.

Inspect the current repository first. Then create
`.agent/plans/M00-repository-skeleton.md` as a self-contained ExecPlan following
`.agent/PLANS.md`.

The plan must:
- stay strictly within Milestone 0;
- use the simplest architecture in the technical specification;
- identify exact files to create/change;
- include tests and exact acceptance commands;
- list anything intentionally deferred to later milestones;
- call out any ambiguity that requires my decision.

Do not start Milestone 1 and do not add future infrastructure.
When finished, summarize the proposed plan and stop for review.
```

---

# 50. Codex Prompt: Implement an Approved Milestone

```text
Read AGENTS.md and the approved ExecPlan:
`.agent/plans/M00-repository-skeleton.md`.

Implement ONLY that approved plan.

Rules:
- do not expand the scope;
- do not begin the next milestone;
- keep changes minimal and reviewable;
- add/update tests as described in the plan;
- update the plan progress/outcome sections while working;
- if a material architecture decision is missing, stop and ask instead of guessing;
- do not declare completion until all acceptance commands have been run.

At the end, provide:
1. changed files;
2. what was implemented;
3. commands/tests run and their results;
4. acceptance criteria status;
5. blockers/known limitations;
6. any dependency, migration or configuration changes.

Then stop.
```

---

# 51. Codex Prompt: Verification Pass

```text
Review the current implementation against:
- AGENTS.md
- the active milestone ExecPlan
- the milestone acceptance criteria in docs/IMPLEMENTATION_ROADMAP.md

Do not add new features.

Inspect the diff and run the required tests/acceptance commands. Look specifically for:
- scope creep;
- missing tests;
- silent exception handling;
- missing evidence/provenance;
- non-idempotent behaviour;
- hard-coded source counts;
- unsafe SQL construction;
- LLM output that is not schema-validated;
- source values being overwritten by derived/validated values.

Fix only defects that are clearly inside the current milestone. If a fix would require
an architecture change, report it instead of implementing it without approval.

Finish with a pass/fail checklist for every acceptance criterion.
```

---

# 52. Codex Prompt: Bug Fix Without Scope Drift

```text
We have a defect in the current implemented milestone.

Defect:
<describe observed behaviour>

Expected behaviour:
<describe expected behaviour>

Reproduction:
<commands/input>

Read AGENTS.md and only the documentation relevant to this subsystem.
First reproduce the defect and identify the smallest root cause.
Do not refactor unrelated modules.
Add a regression test that fails before the fix and passes after it.
Implement the smallest correct fix, run the relevant test suite, and report the result.
If the root cause conflicts with an architecture decision, stop and explain the conflict.
```

---

# 53. Codex Prompt for Milestone 1 and Later

Use the same two-turn pattern for every milestone:

## Planning turn

```text
Read AGENTS.md, .agent/PLANS.md, docs/TECHNICAL_SPEC.md and
`docs/IMPLEMENTATION_ROADMAP.md` sections relevant to Milestone <N>.
Also inspect the code produced by completed milestones that this work depends on.

Create `.agent/plans/M<N>-<short-name>.md`.
Planning only; do not code.
Keep scope strictly inside Milestone <N> and stop after presenting the plan.
```

## Implementation turn

```text
Implement only the approved `.agent/plans/M<N>-<short-name>.md`.
Update tests and the plan progress/outcome.
Run all acceptance commands.
Do not begin Milestone <N+1>.
Stop after the completion report.
```

This is intentionally repetitive. Repetition at milestone boundaries is cheaper than letting an agent drift across the entire system.

---

# 54. Decision Log

Create `docs/DECISIONS.md` and record decisions using a lightweight ADR format.

Example:

```markdown
## DEC-001 - PostgreSQL instead of a document-only store
Status: accepted

Context:
The main user questions are numeric/structured filters such as budget, manpower and
machinery cost.

Decision:
Use PostgreSQL as the local structured source of truth.

Reason:
SQL is simpler and more reliable for the dominant query types than vector retrieval.

Consequences:
A local PostgreSQL service is required. Vector search is deferred.
```

Other initial decisions:

```text
DEC-002 - PMEGP only for initial source adapter
DEC-003 - 20 -> 100 -> full dynamic corpus
DEC-004 - raw artifacts immutable
DEC-005 - evidence required for core facts
DEC-006 - OCR only as fallback
DEC-007 - no vector database in first build
DEC-008 - local LLM through provider interface
DEC-009 - QueryIntent + deterministic SQL builder, not arbitrary LLM SQL
DEC-010 - current trend analysis deferred to market-signal phase
```

Codex should not silently overturn accepted decisions.

---

# 55. Data Quality Review Queue

A full UI is unnecessary, but the system needs a way to identify uncertain records.

Version 1 can use a database flag/report rather than a dedicated review application.

Review reasons:

```text
LOW_OCR_CONFIDENCE
TABLE_EXTRACTION_FAILED
MISSING_CORE_EVIDENCE
FINANCIAL_RECONCILIATION_WARNING
AMBIGUOUS_PROJECT_NAME
LLM_SCHEMA_FAILURE
UNSUPPORTED_DOCUMENT
```

A CLI command can print review items:

```bash
python -m msmeintel review list
```

This keeps uncertainty visible without requiring a dashboard.

---

# 56. Idempotency and Reprocessing

The same input should not create uncontrolled duplicates.

Rules:

- discovery upserts by source + canonical source record URL/ID;
- document bytes are identified by SHA-256;
- project-document link creation is idempotent;
- page extraction can be replaced when parser version changes;
- AI facts record model/prompt version;
- reprocessing should be explicit when parser/schema/model versions change;
- raw files are retained across reprocessing.

Recommended version fields:

```text
code_version
parser_version
schema_version
prompt_version
model_name
```

---

# 57. Performance Expectations

The corpus is small enough that correctness is more important than distributed scale.

Approximately 1,024 project records, even with several documents per project, is well within the capability of a single local PostgreSQL instance and a single Python process.

Likely bottlenecks:

1. network download latency;
2. OCR;
3. local LLM inference;
4. difficult table extraction.

Do not optimize ordinary SQL or introduce concurrency before measurement demonstrates a problem.

Safe initial concurrency:

- source website: very low/conservative;
- PDF processing: sequential first;
- local LLM: sequential first.

Parallelism can be added after the pipeline is stable.

---

# 58. Failure Handling

Each pipeline stage must return/record a specific failure category.

Examples:

```text
DISCOVERY_PARSE_ERROR
HTTP_TIMEOUT
HTTP_STATUS_ERROR
INVALID_MIME
PDF_OPEN_ERROR
TEXT_EXTRACTION_ERROR
OCR_ERROR
TABLE_EXTRACTION_ERROR
LLM_TIMEOUT
LLM_INVALID_JSON
SCHEMA_VALIDATION_ERROR
DB_ERROR
VALIDATION_ERROR
```

The top-level run should catch per-document failures, record them, and continue where safe.

Do not use broad `except Exception: pass` patterns.

---

# 59. Project Report Output

For each project generate a Markdown report from database content.

Template:

```markdown
# <Project Name>

## Source documents
## Classification
## Project cost
## Machinery
## Working capital
## Products and capacity
## Raw materials
## Manpower
## Infrastructure
## Financial assumptions
## Compliance explicitly mentioned by source
## Validation warnings
## Missing important fields
## Evidence references
## Extraction metadata
```

The report is a debugging and learning artifact as much as a user-facing artifact.

---

# 60. Phase 2: Current Market Signal Layer

Only after the corpus is trustworthy should the project expand toward questions such as "What is trending in 2026?"

Possible architecture:

```text
Government project corpus
          |
          +--------------------+
                               |
Current dated market signals --+
                               |
                               v
                      Candidate comparison
                               |
                               v
                        AI explanation
```

Potential future signal categories:

```text
official production/growth statistics
public procurement/tender activity
new enterprise registrations
import/export changes
current scheme/incentive changes
current machinery/raw-material prices
regional industrial data
search-interest data if a suitable lawful source exists
```

Every signal must carry:

```text
source
observed_at
geography
metric
value
unit
method
```

A trend conclusion must be dated and evidence-backed.

---

# 61. Phase 2 Query Semantics

Once market signals exist, the assistant can distinguish:

```text
source suitability
current market momentum
capital fit
operational complexity
regional fit
```

Avoid collapsing everything into one opaque "best business" score. It is more useful to show trade-offs:

```text
Project A: lower capital, higher manpower
Project B: higher machinery cost, lower working-capital requirement
Project C: stronger current demand signal but older government cost assumptions
```

---

# 62. Full Definition of Done for Version 1

Version 1 is complete when:

1. PMEGP project records are discovered dynamically.
2. The implementation has successfully progressed through 20, 100 and the complete currently discovered corpus.
3. Multiple documents can be associated with one project/source record.
4. Original artifacts are preserved by content hash.
5. Text PDFs are parsed page-by-page.
6. Scanned pages receive OCR only when needed.
7. Important tables are extracted sufficiently for core business facts, with review flags for failures.
8. Core project facts are normalized in PostgreSQL.
9. Core numeric facts have evidence references.
10. Missing facts remain missing.
11. Deterministic validation warnings are stored separately from source values.
12. The local LLM uses strict structured extraction output.
13. The query assistant uses validated QueryIntent and deterministic parameterized SQL.
14. Users can filter by budget and other stored numeric criteria.
15. Users can compare selected project profiles.
16. The assistant clearly distinguishes historical DPR assumptions from current market facts.
17. The assistant does not claim current 2026 trends without a current market-signal layer.
18. Failed documents do not abort the entire run.
19. Re-running the pipeline is idempotent enough for normal development.
20. Golden regression tests pass.
21. The project runs locally without paid runtime services.
22. Dependency/model licenses are documented.
23. The repository documentation enables Codex to work one milestone at a time without needing the complete specification pasted into every prompt.

---

# 63. Appendix A - Example Canonical Project Record

```json
{
  "project": {
    "id": 123,
    "name": "Example Spice Grinding Unit",
    "project_type": "manufacturing",
    "sector": "food_processing",
    "description": "Example only"
  },
  "facts": {
    "total_project_cost_inr": 1850000,
    "machinery_cost_inr": 720000,
    "working_capital_inr": 350000,
    "employee_count_total": 8,
    "annual_revenue_inr": 3600000,
    "annual_profit_inr": null
  },
  "evidence": {
    "total_project_cost_inr": [
      {
        "document_id": 45,
        "page": 8,
        "table_index": 2,
        "raw_value": "18.50 Lakh"
      }
    ]
  },
  "validation": [
    {
      "rule": "PROJECT_COST_RECONCILIATION",
      "status": "WARNING",
      "message": "Declared component subtotal differs from reported total."
    }
  ]
}
```

---

# 64. Appendix B - Example Extraction Prompt Contract

The exact prompt should be versioned in source control. A concise contract is:

```text
You extract structured business facts from supplied government-document text and tables.
Use only the supplied source material.
Do not infer a missing value.
Do not estimate current prices.
Do not invent suppliers, licenses, profit, capacity or manpower.
Return null when a requested field is absent.
For every non-null core numeric field, include at least one evidence reference containing
the page number and source table/element identifier when available.
Return only JSON matching the provided schema.
```

The application, not the prompt alone, enforces correctness through schema validation and evidence checks.

---

# 65. Appendix C - Example Answer Prompt Contract

```text
Answer the user's question only from the supplied retrieved project records.
Do not add facts that are not present in the records.
Label values as source-reported assumptions when appropriate.
If a value is missing, say it is not available in the stored source evidence.
Do not describe a business as currently trending/profitable in 2026 unless the supplied
context contains dated current-market evidence supporting that statement.
When comparing projects, explain trade-offs rather than hiding uncertainty behind an
unsupported single score.
```

---

# 66. Appendix D - Recommended Development Loop

```text
1. Pick one milestone.
2. Ask Codex for planning only.
3. Review ExecPlan.
4. Correct plan if needed.
5. Ask Codex to implement approved plan only.
6. Run tests/acceptance commands.
7. Ask Codex for verification pass.
8. Manually inspect important output.
9. Commit/checkpoint.
10. Start next milestone in a new focused task.
```

Do not issue a prompt such as:

```text
Build the whole system in this 60-page spec.
```

The document is the contract; the milestone plan is the unit of execution.

---

# 67. Appendix E - Practical Review Checklist Before Scaling

Before moving from 20 to 100:

```text
[ ] Are all 20 project/document relationships correct?
[ ] Are raw files hash-addressed and immutable?
[ ] Are normal PDFs extracting correctly?
[ ] Are scanned pages actually detected?
[ ] Are important financial tables recoverable?
[ ] Are currency/lakh/crore rules tested?
[ ] Are source pages attached to core facts?
[ ] Are missing fields preserved as missing?
[ ] Are validation differences non-destructive?
[ ] Does rerunning avoid uncontrolled duplicates?
[ ] Do fixed assistant evaluation questions pass?
[ ] Does the assistant avoid claiming unsupported current trends?
```

Before moving from 100 to full corpus:

```text
[ ] No regression on the golden 20.
[ ] Failure reasons are categorized.
[ ] Retry-failed works.
[ ] Schema supports observed variation.
[ ] LLM failures are recoverable.
[ ] Processing can resume after interruption.
[ ] Run metrics are understandable.
[ ] Database query latency is acceptable.
```

---

# 68. Appendix F - Source and Tooling Notes

This specification is a simplified implementation evolution of the earlier Government MSME Project Intelligence Platform design. It intentionally preserves the earlier document's strongest principles - immutable source documents, evidence, deterministic validation, source adapters and AI as an interpretation layer - while reducing the initial number of infrastructure components and making the 20 -> 100 -> full-corpus path explicit.

For Codex usage, current OpenAI guidance supports repository-level `AGENTS.md` instructions and execution-plan files for complex work. Current guidance also recommends keeping persistent agent instructions focused rather than requiring every large design document to be read for every small edit. The repository handoff pack accompanying this specification follows that approach.

---

# 69. Final Implementation Rule

The project should be judged by a simple standard:

> Can the application take real government project documents, convert them into verified structured business facts with traceable evidence, and answer useful budget/operations/comparison questions locally and repeatably without rereading the entire corpus or inventing unsupported data?

If yes, the project has achieved its Version 1 learning objective. Additional repositories, embeddings, polished UI and current-market intelligence are later improvements, not prerequisites for proving the core idea.
