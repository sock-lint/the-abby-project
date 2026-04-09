"""Generic URL ingestor: JSON-LD HowTo > OpenGraph > heuristic lists."""
from __future__ import annotations

import json
from typing import Any, Iterable

from bs4 import BeautifulSoup

from .base import BaseIngestor, IngestionResult, MaterialDraft, MilestoneDraft
from .category import guess_category


MATERIAL_HEADING_KEYWORDS = ("materials", "supplies", "you'll need", "you will need", "what you need", "tools")


class GenericUrlIngestor(BaseIngestor):
    source_type = "url"

    def __init__(self, url: str) -> None:
        if not url:
            raise ValueError("URL required")
        self.url = url

    def ingest(self) -> IngestionResult:
        html = self.fetch_cached(self.url, "generic_url")
        soup = BeautifulSoup(html, "html.parser")

        result = IngestionResult(
            source_url=self.url,
            source_type=self.source_type,
            raw_html=html,
        )

        # 1) JSON-LD (preferred — exact HowTo schema)
        jsonld_used = self._apply_jsonld(soup, result)

        # 2) OpenGraph fallback for title/description/cover
        self._apply_opengraph(soup, result)

        # 3) Heuristic fallback when JSON-LD did not supply milestones/materials
        if not result.milestones:
            self._apply_heuristic_milestones(soup, result)
        if not result.materials:
            self._apply_heuristic_materials(soup, result)

        if not result.title:
            title_tag = soup.find("title")
            if title_tag:
                result.title = title_tag.get_text(strip=True)

        if not jsonld_used:
            result.warnings.append(
                "No structured HowTo data — parsed with best-effort heuristics."
            )
        if not result.milestones:
            result.warnings.append("No steps found — add milestones manually.")
        if not result.materials:
            result.warnings.append(
                "No materials list found — add materials manually."
            )

        result.category_hint = guess_category(result.title, result.description)
        return result

    # ---- JSON-LD --------------------------------------------------------

    def _apply_jsonld(self, soup: BeautifulSoup, result: IngestionResult) -> bool:
        for tag in soup.find_all("script", type="application/ld+json"):
            try:
                payload = json.loads(tag.string or "")
            except (ValueError, TypeError):
                continue
            for node in self._iter_nodes(payload):
                if not isinstance(node, dict):
                    continue
                t = node.get("@type")
                if isinstance(t, list):
                    types = {x.lower() for x in t if isinstance(x, str)}
                else:
                    types = {t.lower()} if isinstance(t, str) else set()
                if "howto" in types or "recipe" in types:
                    self._ingest_howto_node(node, result)
                    return True
                if "article" in types and not result.title:
                    result.title = node.get("headline") or result.title
                    result.description = node.get("description") or result.description
        return False

    @staticmethod
    def _iter_nodes(payload: Any) -> Iterable[Any]:
        if isinstance(payload, list):
            for item in payload:
                yield from GenericUrlIngestor._iter_nodes(item)
        elif isinstance(payload, dict):
            yield payload
            if "@graph" in payload:
                yield from GenericUrlIngestor._iter_nodes(payload["@graph"])

    def _ingest_howto_node(self, node: dict, result: IngestionResult) -> None:
        result.title = result.title or node.get("name") or node.get("headline") or ""
        result.description = result.description or node.get("description") or ""
        image = node.get("image")
        if isinstance(image, dict):
            image = image.get("url")
        if isinstance(image, list) and image:
            image = image[0] if isinstance(image[0], str) else image[0].get("url")
        if isinstance(image, str):
            result.cover_photo_url = image

        # steps
        steps = node.get("step") or []
        if isinstance(steps, dict):
            steps = [steps]
        order = 0
        for s in steps:
            if not isinstance(s, dict):
                continue
            # HowToSection contains nested HowToStep children
            if (s.get("@type") or "").lower() == "howtosection":
                for child in s.get("itemListElement", []) or []:
                    if isinstance(child, dict):
                        self._append_howto_step(child, result, order)
                        order += 1
            else:
                self._append_howto_step(s, result, order)
                order += 1

        # supplies + tools -> materials
        for key in ("supply", "tool"):
            items = node.get(key) or []
            if isinstance(items, dict):
                items = [items]
            for item in items:
                name = item.get("name") if isinstance(item, dict) else str(item)
                if name:
                    result.materials.append(MaterialDraft(name=name[:200]))

    @staticmethod
    def _append_howto_step(
        step: dict, result: IngestionResult, order: int
    ) -> None:
        title = step.get("name") or f"Step {order + 1}"
        desc = step.get("text") or ""
        if isinstance(desc, list):
            desc = " ".join(str(x) for x in desc)
        result.milestones.append(
            MilestoneDraft(title=str(title)[:200], description=str(desc)[:500], order=order)
        )

    # ---- OpenGraph fallbacks -------------------------------------------

    @staticmethod
    def _apply_opengraph(soup: BeautifulSoup, result: IngestionResult) -> None:
        if not result.title:
            og_title = soup.find("meta", property="og:title")
            if og_title and og_title.get("content"):
                result.title = og_title["content"].strip()
        if not result.description:
            og_desc = soup.find("meta", property="og:description")
            if og_desc and og_desc.get("content"):
                result.description = og_desc["content"].strip()
        if not result.cover_photo_url:
            og_image = soup.find("meta", property="og:image")
            if og_image and og_image.get("content"):
                result.cover_photo_url = og_image["content"].strip()

    # ---- Heuristic fallbacks --------------------------------------------

    @staticmethod
    def _apply_heuristic_milestones(
        soup: BeautifulSoup, result: IngestionResult
    ) -> None:
        # First <ol> with 3+ items inside <article>/<main>/body counts as steps.
        container = soup.find("article") or soup.find("main") or soup.body
        if container is None:
            return
        for ol in container.find_all("ol"):
            items = ol.find_all("li", recursive=False)
            if len(items) >= 3:
                for i, li in enumerate(items):
                    text = li.get_text(" ", strip=True)
                    if not text:
                        continue
                    # First sentence as title, rest as description.
                    head, _, rest = text.partition(". ")
                    result.milestones.append(
                        MilestoneDraft(
                            title=head[:200] or f"Step {i + 1}",
                            description=rest[:500],
                            order=i,
                        )
                    )
                return

    @staticmethod
    def _apply_heuristic_materials(
        soup: BeautifulSoup, result: IngestionResult
    ) -> None:
        for heading in soup.find_all(["h2", "h3", "h4"]):
            text = heading.get_text(" ", strip=True).lower()
            if any(kw in text for kw in MATERIAL_HEADING_KEYWORDS):
                lst = heading.find_next(["ul", "ol"])
                if lst is None:
                    continue
                for li in lst.find_all("li"):
                    name = li.get_text(" ", strip=True)
                    if name:
                        result.materials.append(MaterialDraft(name=name[:200]))
                if result.materials:
                    return
