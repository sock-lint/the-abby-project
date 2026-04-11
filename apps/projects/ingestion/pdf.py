"""PDF ingestor — extracts steps + materials from uploaded PDF tutorials."""
from __future__ import annotations

import re

from .base import BaseIngestor, IngestionResult, MaterialDraft, StepDraft
from .category import guess_category


STEP_PATTERN = re.compile(r"^\s*(?:step\s*\d+|\d+[.)])\s*[:\-]?\s*(.*)$", re.IGNORECASE)
MATERIAL_HEADING_PATTERN = re.compile(
    r"^\s*(materials|supplies|you'?ll need|what you need|tools)\s*[:\-]?\s*$",
    re.IGNORECASE,
)
SECTION_BREAK = re.compile(r"^\s*(instructions|steps|directions|method)\s*[:\-]?\s*$", re.IGNORECASE)


class PdfIngestor(BaseIngestor):
    source_type = "pdf"

    def __init__(self, file_field) -> None:
        """`file_field` is a Django FieldFile (e.g. ``job.source_file``)."""
        self.file_field = file_field

    def ingest(self) -> IngestionResult:
        try:
            import pdfplumber  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise ValueError(
                "PDF ingestion requires pdfplumber — install it with `pip install pdfplumber`."
            ) from exc

        result = IngestionResult(source_type=self.source_type)

        # pdfplumber accepts a file path or a file-like object
        with self.file_field.open("rb") as fh:
            with pdfplumber.open(fh) as pdf:
                title = None
                if pdf.metadata and pdf.metadata.get("Title"):
                    title = str(pdf.metadata["Title"]).strip()
                text_pages = [page.extract_text() or "" for page in pdf.pages]

        full_text = "\n".join(text_pages)
        lines = [line.rstrip() for line in full_text.splitlines()]

        # Stash the full extracted text so the MarkdownStage has substantive
        # content to feed Claude. We wrap it in a <pre> so downstream HTML
        # converters treat it as literal text.
        if full_text.strip():
            result.raw_html = f"<pre>{full_text}</pre>"

        # Title: PDF metadata > first non-empty line
        if not title:
            for line in lines:
                stripped = line.strip()
                if stripped:
                    title = stripped
                    break
        result.title = (title or "")[:200]

        self._extract_steps(lines, result)
        self._extract_materials(lines, result)

        # Description: first paragraph that isn't the title and isn't a heading
        for line in lines:
            stripped = line.strip()
            if (
                stripped
                and stripped != result.title
                and len(stripped) > 30
                and not STEP_PATTERN.match(stripped)
                and not MATERIAL_HEADING_PATTERN.match(stripped)
            ):
                result.description = stripped[:500]
                break

        self.add_missing_section_warnings(result, source_label="in PDF")

        result.category_hint = guess_category(result.title, result.description, full_text[:2000])
        return result

    @staticmethod
    def _extract_steps(lines: list[str], result: IngestionResult) -> None:
        current: StepDraft | None = None
        order = 0
        for line in lines:
            match = STEP_PATTERN.match(line)
            if match:
                if current is not None:
                    result.steps.append(current)
                head = match.group(1).strip() or f"Step {order + 1}"
                current = StepDraft(
                    title=head[:200], description="", order=order
                )
                order += 1
            elif current is not None:
                stripped = line.strip()
                if not stripped:
                    # blank line closes the step
                    result.steps.append(current)
                    current = None
                else:
                    # append continuation text, capped at 2000 chars
                    if len(current.description) < 2000:
                        current.description = (current.description + " " + stripped).strip()[:2000]
        if current is not None:
            result.steps.append(current)

    @staticmethod
    def _extract_materials(lines: list[str], result: IngestionResult) -> None:
        in_block = False
        for line in lines:
            stripped = line.strip()
            if not stripped:
                if in_block:
                    break
                continue
            if MATERIAL_HEADING_PATTERN.match(stripped):
                in_block = True
                continue
            if in_block:
                # Stop if we hit the instructions/steps section
                if SECTION_BREAK.match(stripped) or STEP_PATTERN.match(stripped):
                    break
                # Accept bullets or plain lines
                name = re.sub(r"^[\-\*•·\u2022]+\s*", "", stripped)
                if name:
                    result.materials.append(MaterialDraft(name=name[:200]))
