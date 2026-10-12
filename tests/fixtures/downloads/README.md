# Synthetic downloader fixture

`minimal.pdf` is an authored, ASCII, one-blank-page PDF 1.4 with a catalog,
page tree, page dictionary and correct byte-offset xref table (LF line endings).
It has no scripts, attachments, government content or external dependencies.
It is not an authentic PMEGP document and is never used to replace a failed live
download. Tests verify its offsets and derive malformed/truncated responses in
memory. A same-length MediaBox change produces a second distinct valid byte fixture.
