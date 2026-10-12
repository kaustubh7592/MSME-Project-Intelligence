"""Mandatory OFFLINE real-Tesseract acceptance; missing runtime is a failure, never a skip."""

import hashlib
import io
import json
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from msmeintel import extraction, ocr, page_processing


def synthetic_pdf(*, scanned=False, mixed=False) -> bytes:
    """Deliberately synthetic ruled table and/or raster text, not PMEGP material."""
    writer = PdfWriter()
    if not scanned or mixed:
        page = writer.add_blank_page(width=612, height=792)
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})}
        )
        commands = [
            "BT /F1 12 Tf 50 750 Td "
            "(Synthetic native project table for offline testing only.) Tj ET",
            "BT /F1 12 Tf 50 730 Td "
            "(Financial cell text must remain exactly as printed in this test.) Tj ET",
        ]
        for x in (50, 300, 500):
            commands.append(f"{x} 500 m {x} 650 l S")
        for y in (500, 550, 600, 650):
            commands.append(f"50 {y} m 500 {y} l S")
        for x, y, text in [
            (60, 625, "Particulars"),
            (310, 625, "Amount"),
            (60, 575, "Machine"),
            (310, 575, "1,23,456.00"),
            (60, 525, "Missing amount"),
        ]:
            commands.append(f"BT /F1 12 Tf {x} {y} Td ({text}) Tj ET")
        stream = DecodedStreamObject()
        stream.set_data("\n".join(commands).encode())
        page[NameObject("/Contents")] = writer._add_object(stream)
    if scanned:
        image = Image.new("RGB", (1600, 2000), "white")
        draw = ImageDraw.Draw(image)
        font = ImageFont.load_default(size=44)
        for index, text in enumerate(
            (
                "SYNTHETIC SCANNED PROJECT",
                "Investment 12345 rupees",
                "Employment 7 people",
                "This is an offline OCR test.",
            )
        ):
            draw.text((120, 180 + index * 110), text, fill="black", font=font)
        encoded = io.BytesIO()
        image.save(encoded, format="PDF", resolution=200)
        image.close()
        encoded.seek(0)
        reader = PdfReader(encoded)
        writer.add_page(reader.pages[0])
    output = io.BytesIO()
    writer.write(output)
    writer.close()
    return output.getvalue()


def main() -> int:
    try:
        engine = ocr.runtime("eng")
        reports = []
        with tempfile.TemporaryDirectory(prefix="msmeintel-m04-check-") as directory:
            for name, scanned, mixed in (
                ("native", False, False),
                ("scanned", True, False),
                ("mixed", True, True),
            ):
                raw = Path(directory) / f"{name}.pdf"
                body = synthetic_pdf(scanned=scanned, mixed=mixed)
                raw.write_bytes(body)
                digest = hashlib.sha256(body).hexdigest()
                document = {
                    "sha256": digest,
                    "storage_path": f"raw/{digest[:2]}/{digest}.pdf",
                    "byte_count": len(body),
                }
                native = extraction.extract_document(raw, document, extraction.parser_identity())
                if native["status"] not in extraction.COMPLETE_STATUSES:
                    raise ValueError("Synthetic native parsing failed")
                result = page_processing.process_document(
                    raw, native, {}, page_processing.Options(), engine
                )
                expected = int(scanned)
                if (
                    result["status"] != "COMPLETE"
                    or result["counts"]["pages_ocr_processed"] != expected
                ):
                    raise ValueError("Selective real OCR did not complete")
                for page in result["pages"]:
                    if page["ocr"] is not None:
                        text = " ".join(page["ocr"]["text"].split())
                        if not all(
                            word in text for word in ("SYNTHETIC", "12345", "Employment", "7")
                        ):
                            raise ValueError("Real OCR did not recover the printed reference text")
                if raw.read_bytes() != body:
                    raise ValueError("Synthetic source was modified")
                reports.append({"fixture": name, **result["counts"]})
        print(json.dumps({"status": "PASSED", "engine": engine, "fixtures": reports}, indent=2))
        return 0
    except (ocr.OCRError, ValueError, OSError) as error:
        print(
            json.dumps(
                {
                    "status": "BLOCKED" if isinstance(error, ocr.OCRError) else "FAILED",
                    "error": str(error),
                },
                indent=2,
            )
        )
        return 2 if isinstance(error, ocr.OCRError) else 1


if __name__ == "__main__":
    sys.exit(main())
