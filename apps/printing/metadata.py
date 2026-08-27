"""Pull a title + thumbnail out of a model-host link.

Used for the request card, so a submission reads as "Articulated Dragon" with
a picture rather than as a bare URL. MakerWorld, Printables and Thingiverse
all server-render OpenGraph tags, so a single OG scrape covers every host we
care about plus most of the long tail.

Safety: every fetch goes through :func:`config.url_safety.safe_get`, which
rejects private/loopback/link-local targets and re-validates each redirect
hop. This is a **child-supplied URL** reaching server-side HTTP — exactly the
SSRF shape that guard exists for. Never swap this for a bare
``requests.get``.

Failure is always soft. A model host that is slow, down, or has changed its
markup must not stop a kid from submitting a request; we fall back to the
URL's own slug for a title and no thumbnail, and the parent sees the link.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from urllib.parse import unquote, urlparse

from bs4 import BeautifulSoup

from config.url_safety import UnsafeURLError, safe_get

from .models import PrintRequest

logger = logging.getLogger(__name__)

#: Model hosts get a real browser UA — several 403 an obvious bot string.
_USER_AGENT = (
    "Mozilla/5.0 (compatible; AbbyProject/1.0; +https://github.com/sock-lint/the-abby-project)"
)
_TIMEOUT_SECONDS = 8
#: Stop reading after this much HTML. OG tags live in <head>; anything past
#: a megabyte is a page we don't want to parse anyway.
_MAX_BYTES = 1_000_000

_HOST_KINDS = (
    ("makerworld.com", PrintRequest.SourceKind.MAKERWORLD),
    ("printables.com", PrintRequest.SourceKind.PRINTABLES),
    ("thingiverse.com", PrintRequest.SourceKind.THINGIVERSE),
)

#: ``/model/12345-articulated-dragon`` → ``articulated dragon``
_SLUG_TITLE_RE = re.compile(r"[-_]+")


@dataclass
class LinkMetadata:
    title: str = ""
    thumbnail_url: str = ""
    author: str = ""
    source_kind: str = PrintRequest.SourceKind.OTHER_URL
    #: Populated when the fetch failed; the caller decides whether to surface it.
    error: str = ""


def classify_url(url: str) -> str:
    """Map a URL to a ``PrintRequest.SourceKind``."""
    host = (urlparse(url or "").hostname or "").lower()
    for needle, kind in _HOST_KINDS:
        if host == needle or host.endswith("." + needle):
            return kind
    return PrintRequest.SourceKind.OTHER_URL


def title_from_url(url: str) -> str:
    """Best-effort title from the URL path, for when scraping fails.

    ``https://www.printables.com/model/12345-articulated-dragon`` →
    ``Articulated Dragon``. Leading numeric ids are dropped; if nothing
    usable remains we return ``""`` and the caller supplies a placeholder.
    """
    path = urlparse(url or "").path.rstrip("/")
    if not path:
        return ""
    last = unquote(path.rsplit("/", 1)[-1])
    last = re.sub(r"^\d+[-_]", "", last)
    words = [w for w in _SLUG_TITLE_RE.split(last) if w and not w.isdigit()]
    return " ".join(words).strip().title()[:160]


def _meta_content(soup: BeautifulSoup, *, prop=None, name=None) -> str:
    if prop:
        tag = soup.find("meta", property=prop)
        if tag and tag.get("content"):
            return tag["content"].strip()
    if name:
        tag = soup.find("meta", attrs={"name": name})
        if tag and tag.get("content"):
            return tag["content"].strip()
    return ""


def fetch_link_metadata(url: str) -> LinkMetadata:
    """Scrape OpenGraph metadata from a model page. Never raises."""
    kind = classify_url(url)
    fallback = LinkMetadata(
        title=title_from_url(url),
        source_kind=kind,
    )
    if not url:
        return fallback

    try:
        response = safe_get(
            url,
            timeout=_TIMEOUT_SECONDS,
            headers={"User-Agent": _USER_AGENT, "Accept": "text/html,*/*"},
        )
    except UnsafeURLError as exc:
        # A child pasting an internal address is far more likely to be a typo
        # than an attack, so this reads as a normal validation failure.
        fallback.error = f"That link doesn't point at a public website ({exc})."
        return fallback
    except Exception as exc:  # noqa: BLE001 - any transport failure is soft
        logger.info("printing: metadata fetch failed for %s: %s", url, exc)
        fallback.error = "Couldn't reach that page — the link was saved as-is."
        return fallback

    if response.status_code >= 400:
        fallback.error = f"That page returned HTTP {response.status_code}."
        return fallback

    content_type = (response.headers.get("Content-Type") or "").lower()
    if "html" not in content_type:
        fallback.error = "That link isn't a web page."
        return fallback

    try:
        soup = BeautifulSoup(response.content[:_MAX_BYTES], "html.parser")
    except Exception as exc:  # noqa: BLE001 - malformed markup is not our problem
        logger.info("printing: could not parse %s: %s", url, exc)
        fallback.error = "Couldn't read that page."
        return fallback

    title = _meta_content(soup, prop="og:title", name="title")
    if not title and soup.title and soup.title.string:
        title = soup.title.string.strip()
    image = _meta_content(soup, prop="og:image", name="twitter:image")
    author = _meta_content(soup, prop="og:site_name", name="author")

    return LinkMetadata(
        title=(title or fallback.title)[:160],
        thumbnail_url=image[:500],
        author=author[:120],
        source_kind=kind,
    )
