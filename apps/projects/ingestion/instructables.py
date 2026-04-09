"""Instructables ingestor — pulls title, steps, and supplies list."""
from __future__ import annotations

from bs4 import BeautifulSoup

from .base import BaseIngestor, IngestionResult, MaterialDraft, MilestoneDraft
from .category import guess_category


class InstructablesIngestor(BaseIngestor):
    source_type = "instructables"

    def __init__(self, url: str) -> None:
        if not url or "instructables.com" not in url:
            raise ValueError("Invalid Instructables URL")
        self.url = url

    def ingest(self) -> IngestionResult:
        html = self.fetch_cached(self.url, "instructables")
        soup = BeautifulSoup(html, "html.parser")

        result = IngestionResult(
            source_url=self.url,
            source_type=self.source_type,
            raw_html=html,
        )

        # Title
        title_tag = soup.find("h1")
        if title_tag:
            result.title = title_tag.get_text(strip=True)

        # Cover photo (og:image)
        og_image = soup.find("meta", property="og:image")
        if og_image and og_image.get("content"):
            result.cover_photo_url = og_image.get("content")

        # Description — og:description falls back to first intro paragraph
        og_desc = soup.find("meta", property="og:description")
        if og_desc and og_desc.get("content"):
            result.description = og_desc.get("content", "").strip()

        # Steps -> milestones. Instructables step sections have class names
        # containing "step" (the exact markup has changed over time).
        steps = soup.find_all(
            "section", class_=lambda c: bool(c) and "step" in " ".join(
                c if isinstance(c, list) else [c]
            ).lower()
        )
        if not steps:
            # Fallback: heading tags starting with "Step"
            steps = [
                h for h in soup.find_all(["h2", "h3"])
                if h.get_text(strip=True).lower().startswith("step")
            ]

        for i, step in enumerate(steps):
            title_el = step.find(["h2", "h3"]) if hasattr(step, "find") else None
            step_title = (title_el.get_text(strip=True) if title_el else "") or f"Step {i + 1}"
            # Grab first paragraph as description, truncated.
            desc_el = step.find("p") if hasattr(step, "find") else None
            step_desc = desc_el.get_text(" ", strip=True)[:500] if desc_el else ""
            result.milestones.append(
                MilestoneDraft(title=step_title, description=step_desc, order=i)
            )

        if not result.milestones:
            result.warnings.append("No steps found — add milestones manually.")

        # Supplies list -> materials
        supplies_section = (
            soup.find(id="supplies")
            or soup.find("section", attrs={"data-section": "supplies"})
            or self._find_by_heading(soup, ("supplies", "materials", "you'll need"))
        )
        if supplies_section is not None:
            for li in supplies_section.find_all("li"):
                text = li.get_text(" ", strip=True)
                if text:
                    result.materials.append(MaterialDraft(name=text[:200]))
        if not result.materials:
            result.warnings.append(
                "No supplies list found — add materials manually."
            )

        # Category hint
        og_section = soup.find("meta", property="article:section")
        source_cat = og_section.get("content") if og_section else None
        result.category_hint = guess_category(
            result.title, result.description, source_cat
        )

        return result

    @staticmethod
    def _find_by_heading(soup: BeautifulSoup, needles: tuple[str, ...]):
        """Return the element following a heading whose text matches any needle."""
        for heading in soup.find_all(["h2", "h3", "h4"]):
            text = heading.get_text(" ", strip=True).lower()
            if any(n in text for n in needles):
                # The list is usually the next sibling that contains <li> items.
                sib = heading.find_next(["ul", "ol", "div", "section"])
                if sib is not None:
                    return sib
        return None
