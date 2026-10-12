"""Bounded local Tesseract invocation; never execute PDF scripts or attachments."""

import csv
import hashlib
import io
import math
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pypdfium2

MAX_RENDER_PIXELS = 40_000_000


class OCRError(ValueError):
    def __init__(self, category: str):
        super().__init__(category)
        self.category = category


def executable() -> Path:
    configured = os.environ.get("MSMEINTEL_TESSERACT")
    command = configured or shutil.which("tesseract")
    if not command and os.name == "nt":
        command = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    if not command or not Path(command).is_file():
        raise OCRError("OCR_RUNTIME_UNAVAILABLE")
    return Path(command).resolve()


def _run(arguments: list[str], timeout: float) -> str:
    try:
        result = subprocess.run(
            arguments,
            capture_output=True,
            timeout=timeout,
            check=False,
            encoding="utf-8",
            errors="replace",
            shell=False,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except subprocess.TimeoutExpired as error:
        raise OCRError("OCR_TIMEOUT") from error
    except OSError as error:
        raise OCRError("OCR_RUNTIME_UNAVAILABLE") from error
    if result.returncode:
        raise OCRError("OCR_PROCESS_FAILED")
    return result.stdout


def runtime(language: str) -> dict:
    if not re.fullmatch(r"[a-zA-Z0-9_]+", language):
        raise OCRError("INVALID_OCR_LANGUAGE")
    binary = executable()
    description = _run([str(binary), "--version"], 10).splitlines()
    languages = _run([str(binary), "--list-langs"], 10)
    match = re.search(r'"([^"\r\n]+)"', languages)
    if not description or not match or language not in languages.splitlines()[1:]:
        raise OCRError("OCR_LANGUAGE_UNAVAILABLE")
    traineddata = Path(match[1]) / f"{language}.traineddata"
    try:
        return {
            "executable": str(binary),
            "version": description[0],
            "executable_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
            "language": language,
            "traineddata_sha256": hashlib.sha256(traineddata.read_bytes()).hexdigest(),
        }
    except OSError as error:
        raise OCRError("OCR_LANGUAGE_UNAVAILABLE") from error


def parse_tsv(text: str, *, width: int, height: int, bbox: list[float]) -> dict:
    words, lines = [], {}
    try:
        reader = csv.DictReader(io.StringIO(text), delimiter="\t", quoting=csv.QUOTE_NONE)
        required = {
            "level",
            "page_num",
            "block_num",
            "par_num",
            "line_num",
            "word_num",
            "left",
            "top",
            "width",
            "height",
            "conf",
            "text",
        }
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise ValueError("Invalid TSV header")
        for row in reader:
            if row["level"] != "5":
                continue
            if not row["text"]:
                continue
            left, top, w, h = (int(row[k]) for k in ("left", "top", "width", "height"))
            confidence = float(row["conf"])
            if (
                not math.isfinite(confidence)
                or not 0 <= confidence <= 100
                or min(left, top, w, h) < 0
                or left + w > width
                or top + h > height
            ):
                raise ValueError("Invalid OCR coordinates/confidence")
            line = tuple(int(row[k]) for k in ("page_num", "block_num", "par_num", "line_num"))
            lines.setdefault(line, []).append(row["text"])
            sx, sy = (bbox[2] - bbox[0]) / width, (bbox[3] - bbox[1]) / height
            words.append(
                {
                    "text": row["text"],
                    "confidence": confidence,
                    "pixel_bbox": [left, top, left + w, top + h],
                    "bbox": [
                        bbox[0] + left * sx,
                        bbox[1] + top * sy,
                        bbox[0] + (left + w) * sx,
                        bbox[1] + (top + h) * sy,
                    ],
                    "line": list(line),
                }
            )
    except (ValueError, KeyError, TypeError, csv.Error) as error:
        raise OCRError("INVALID_OCR_OUTPUT") from error
    return {
        "text": "\n".join(" ".join(line) for line in lines.values()),
        "words": words,
        "mean_word_confidence": sum(w["confidence"] for w in words) / len(words) if words else None,
        "render_width": width,
        "render_height": height,
        "method": "tesseract_tsv",
        "status": "OCR_COMPLETE" if words else "OCR_EMPTY",
    }


def extract(
    path: Path,
    page_number: int,
    bbox: list[float],
    engine: dict,
    *,
    dpi: int = 300,
    timeout: float = 60,
) -> dict:
    if dpi < 72 or dpi > 600 or not math.isfinite(timeout) or timeout <= 0:
        raise OCRError("INVALID_OCR_SETTINGS")
    with tempfile.TemporaryDirectory(prefix="msmeintel-ocr-") as directory:
        target = Path(directory) / "page.png"
        try:
            with pypdfium2.PdfDocument(path) as pdf:
                page = pdf[page_number - 1]
                try:
                    w, h = page.get_size()
                    if math.ceil(w * dpi / 72) * math.ceil(h * dpi / 72) > MAX_RENDER_PIXELS:
                        raise OCRError("OCR_PIXEL_LIMIT")
                    bitmap = page.render(scale=dpi / 72)
                    try:
                        image = bitmap.to_pil()
                        width, height = image.size
                        try:
                            image.save(target)
                        finally:
                            image.close()
                    finally:
                        bitmap.close()
                finally:
                    page.close()
        except OCRError:
            raise
        except Exception as error:
            raise OCRError("OCR_RENDER_ERROR") from error
        # No shell, PDF-supplied arguments, downloaded executables or remote OCR service.
        output = _run(
            [
                engine["executable"],
                str(target),
                "stdout",
                "-l",
                engine["language"],
                "--dpi",
                str(dpi),
                "--psm",
                "3",
                "tsv",
            ],
            timeout,
        )
        return parse_tsv(output, width=width, height=height, bbox=bbox)
