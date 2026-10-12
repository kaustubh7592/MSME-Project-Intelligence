# M03 offline PDF fixtures

`tests/test_extraction.py::pdf_bytes` builds explicitly synthetic PDF bytes with
pypdf in memory. Helvetica text, blank pages, a one-pixel image painted on a page,
mixed text/image pages, rotation and password encryption exercise native parsing.
These are not authentic PMEGP documents or replacement downloads. Malformed PDFs
and failures are deliberate test inputs. The existing global socket/DNS guard
applies to all extraction tests.

`golden.json` records only small factual page snippets verified by manually viewing
three authentic source PDFs from the local M02 corpus. The government files and
complete extracted text remain under ignored `data/`; do not redistribute them
without resolving source-content rights. The optional authentic-corpus test reads
local raw files only, checks every available PDF, and skips explicitly when they
are absent. It never downloads files or changes M02 artifacts.
