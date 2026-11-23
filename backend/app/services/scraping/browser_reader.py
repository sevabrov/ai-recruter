"""
Our own page reader for Instagram and Facebook: a headless browser on the server.

Why it exists, measured (November 2026):

* ScrapeGraphAI opened 8 of 145 Instagram profiles and 4 of 62 Facebook pages;
  every other attempt hung for about a minute and came back "504 timed out".
* The same profiles, opened anonymously by a headless Chromium — from a home
  connection *and* from a datacentre (Railway, US) — opened 104 of 104 and 20 of
  20, with the whole bio, in well under a second each. Facebook opened 7 of 10
  from the datacentre.

So the blocker was never "Instagram needs a login": it was the provider. Nothing
here logs in, and nothing here needs to — only pages anyone can see are read.

What a page gives is turned into a profile by the same code that reads a search
result (`snippet_extractor`): the page's title has the very shape of the search
result's title, and the bio is simply a much longer, current snippet. One
definition of "who is this" for both, and the judge then reads the whole bio.

LinkedIn is deliberately not routed here: anonymously it shows a sign-up wall to
a browser (0 of 40 from the datacentre), while ScrapeGraphAI reads it (83%).
"""

import asyncio
import re
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime
from typing import Any

from app.core.logging import get_logger
from app.models.common import Platform, SourceKind
from app.models.scrape import ScrapeOutcome
from app.models.source import DiscoveredUrl, ProviderResult, UrlKind
from app.services.scraping.base import PROFILE_GONE, ExtractionCost, PageRead, bills_for
from app.services.scraping.snippet_extractor import SnippetProfileExtractor
from app.services.search.url_tools import author_profile, canonicalize, discover

log = get_logger(__name__)

#: What this reader opens. Everything else goes to the other reader.
BROWSER_PLATFORMS = frozenset({Platform.INSTAGRAM, Platform.FACEBOOK})
#: …and the search sources whose pages that means: free per page.
BROWSER_SOURCES = frozenset({SourceKind.INSTAGRAM_PUBLIC, SourceKind.FACEBOOK_PUBLIC})

#: Pages are read in English, so the markers below are the platform's own words.
_GONE = re.compile(r"isn.t available|content isn.t available|page not found", re.IGNORECASE)
_LOGIN = re.compile(r"/accounts/login|/login|checkpoint", re.IGNORECASE)

#: Ready when the profile header has drawn, or the platform has said no.
_READY = """() => {
  const text = (document.querySelector('header')?.innerText || '');
  const meta = document.querySelector('meta[property="og:description"]');
  return /followers/i.test(text) || !!meta
    || /isn.t available|log in|not found/i.test(document.title)
    || /login|checkpoint/.test(location.pathname);
}"""

MAX_BIO = 1500
MAX_CAPTION = 600

#: How an Instagram post introduces itself to an anonymous visitor, in its
#: `og:description`: `32 likes, 2 comments - renata.kierszka on June 5, 2025: "…"`.
#: The counts are optional (a post with none omits them), the handle and the date
#: are not.
_POST_LINE = re.compile(
    r"(?:^|\s-\s)(?P<handle>[A-Za-z0-9._]{2,30}) on "
    r"(?P<date>(?:January|February|March|April|May|June|July|August|September|October"
    r"|November|December) \d{1,2}, \d{4})(?::\s*(?P<caption>.*))?",
    re.DOTALL,
)


class BrowserPool:
    """
    One headless Chromium for the whole process, started on first use.

    Shared by every search, like the HTTP client of the other reader: a browser
    costs a few hundred megabytes and a second to start, and keeping one context
    open keeps Instagram's own scripts cached — measured, the first profile moves
    3.7 MB and each next one about 0.6 MB.
    """

    def __init__(self, *, concurrency: int = 4) -> None:
        self._slots = asyncio.Semaphore(max(1, concurrency))
        self._lock = asyncio.Lock()
        self._playwright: Any = None
        self._browser: Any = None
        self._context: Any = None

    async def _ready(self) -> Any:
        async with self._lock:
            if self._browser is not None and self._browser.is_connected():
                return self._context
            await self._shutdown()
            # Imported here: the package is only needed where the reader is on.
            from playwright.async_api import async_playwright

            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=True, args=["--disable-dev-shm-usage", "--no-sandbox"]
            )
            self._context = await self._browser.new_context(
                locale="en-US", viewport={"width": 1280, "height": 900}
            )
            log.info("browser_started")
            return self._context

    @asynccontextmanager
    async def page(self):
        async with self._slots:
            context = await self._ready()
            page = await context.new_page()
            try:
                yield page
            finally:
                await page.close()

    async def _shutdown(self) -> None:
        for closer in (self._context, self._browser):
            if closer is not None:
                with suppress(Exception):  # already gone is fine
                    await closer.close()
        if self._playwright is not None:
            with suppress(Exception):
                await self._playwright.stop()
        self._playwright = self._browser = self._context = None

    async def aclose(self) -> None:
        async with self._lock:
            await self._shutdown()


class BrowserPageReader:
    """Reads public Instagram profiles and Facebook pages with `BrowserPool`."""

    name = "browser"

    def __init__(
        self,
        pool: BrowserPool,
        *,
        timeout_seconds: float = 15.0,
        cost: ExtractionCost | None = None,
    ) -> None:
        self.pool = pool
        self.timeout_ms = int(timeout_seconds * 1000)
        self.cost = cost or ExtractionCost()
        self._snippets = SnippetProfileExtractor()

    async def extract(self, url: DiscoveredUrl):
        return (await self.read(url)).profile

    async def read(self, url: DiscoveredUrl) -> PageRead:
        if url.platform not in BROWSER_PLATFORMS:
            return PageRead(ScrapeOutcome.FAILED, detail="Not a page this reader opens.")
        try:
            async with self.pool.page() as page:
                seen = await self._open(page, url.url)
        except Exception as error:
            log.warning(
                "browser_read_failed", extra={"url": url.canonical_url, "error": str(error)[:200]}
            )
            return PageRead(
                ScrapeOutcome.FAILED,
                detail=f"The browser could not open the page: {str(error)[:120]}",
            )
        return await self._verdict(url, seen)

    async def read_post(self, url: DiscoveredUrl) -> DiscoveredUrl | None:
        """
        Open an Instagram post that does not name its author anywhere else, and
        return it with the author's profile, the date and the caption filled in.

        Free, like every read here, and never raises: a post that would not open is
        simply a post whose author stays unknown — which is what it was before.
        """
        if url.platform not in BROWSER_PLATFORMS:
            return None
        try:
            async with self.pool.page() as page:
                seen = await self._open(page, url.url)
        except Exception as error:
            log.warning(
                "browser_post_failed", extra={"url": url.canonical_url, "error": str(error)[:200]}
            )
            return None
        if _LOGIN.search(seen["final_url"]):
            return None

        if url.platform is Platform.INSTAGRAM:
            found = parse_post(seen["description"]) or parse_post(seen["title"])
            if found is not None:
                handle, published, caption = found
                log.info("browser_post_author", extra={"url": url.canonical_url, "handle": handle})
                return url.model_copy(
                    update={
                        "author_url": f"https://instagram.com/{handle}",
                        "snippet": caption or url.snippet,
                        "page_age": published or url.page_age,
                        "age_label": None if published else url.age_label,
                    }
                )

        # Facebook (and an Instagram post that would not say): the visitor is sent
        # to the post's full address, which is `{account}/videos/…`, `{account}/posts/…`.
        for address in (seen["final_url"], seen["canonical"], seen["og_url"]):
            author = _author_at(address)
            if author:
                log.info("browser_post_author", extra={"url": url.canonical_url, "author": author})
                return url.model_copy(
                    update={"author_url": author, "snippet": seen["description"] or url.snippet}
                )
        return None

    async def _open(self, page: Any, address: str) -> dict[str, str]:
        await page.goto(address, wait_until="domcontentloaded", timeout=self.timeout_ms)
        with suppress(Exception):  # judged on whatever has drawn
            await page.wait_for_function(_READY, timeout=min(self.timeout_ms, 8000))
        header = ""
        if "instagram.com" in page.url:
            with suppress(Exception):  # a profile with no header drew nothing
                header = await page.locator("header").first.inner_text(timeout=2000)
        else:
            # Facebook has no profile header element; the page's own summary and
            # the opening of its main column say who it is and what it is.
            with suppress(Exception):
                main = await page.locator('[role="main"]').first.inner_text(timeout=2000)
                header = main[:800]
        return {
            "final_url": page.url,
            "title": await page.title(),
            "header": header or "",
            "description": await _attribute(page, 'meta[property="og:description"]', "content"),
            "og_url": await _attribute(page, 'meta[property="og:url"]', "content"),
            "canonical": await _attribute(page, 'link[rel="canonical"]', "href"),
        }

    async def _verdict(self, url: DiscoveredUrl, seen: dict[str, str]) -> PageRead:
        title, header = seen["title"].strip(), seen["header"].strip()
        if _LOGIN.search(seen["final_url"]):
            return PageRead(ScrapeOutcome.BLOCKED, detail="The platform asked to log in.")
        if _GONE.search(title) or (not header and _GONE.search(seen["description"])):
            self.cost.pages_read += 1
            return PageRead(ScrapeOutcome.NOT_A_PERSON, detail=PROFILE_GONE)
        bio = "\n".join(part for part in (header, seen["description"]) if part).strip()
        if not title and not bio:
            return PageRead(ScrapeOutcome.EMPTY, detail="The page came back empty.")

        self.cost.pages_read += 1
        # The page, in the shape of a search result: its own title, and its bio as
        # a very long snippet.
        page_as_result = url.model_copy(update={"title": title or url.title, "snippet": bio})
        profile = await self._snippets.extract(page_as_result)
        if profile is None:
            return PageRead(ScrapeOutcome.NOT_A_PERSON, detail="The page names no person.")

        # What the search engine said stays on record as the source; the bio is
        # what the page says now.
        sources = [
            source.model_copy(update={"title": url.title, "snippet": url.snippet})
            for source in profile.sources
        ]
        profile = profile.model_copy(
            update={
                "summary": bio[:MAX_BIO],
                "sources": sources,
                "extractor": self.name,
            }
        )
        log.info("browser_read", extra={"url": url.canonical_url, "person": profile.name})
        return PageRead(ScrapeOutcome.OK, profile=profile)


async def _attribute(page: Any, selector: str, name: str) -> str:
    """An element's attribute, or "" when the page has no such element."""
    with suppress(Exception):
        element = page.locator(selector)
        if await element.count():
            return await element.first.get_attribute(name, timeout=1000) or ""
    return ""


def _author_at(address: str) -> str | None:
    """The account an address belongs to: a post's author, or the profile itself."""
    if not address:
        return None
    found = discover(
        [ProviderResult(url=address, title="", snippet="", query="", provider="browser")]
    )[0]
    if found.platform not in BROWSER_PLATFORMS:
        return None
    if found.kind is UrlKind.CANDIDATE:
        return found.canonical_url
    author = author_profile(found)
    return canonicalize(author) if author else None


def parse_post(text: str) -> tuple[str, datetime | None, str] | None:
    """`(handle, published, caption)` from a post's own description, or None."""
    match = _POST_LINE.search(text or "")
    if match is None:
        return None
    handle = match.group("handle").strip(".")
    if handle.casefold() in {"instagram", "facebook"} or not re.search(r"[a-z]", handle, re.I):
        return None
    try:
        published = datetime.strptime(match.group("date"), "%B %d, %Y").replace(tzinfo=UTC)
    except ValueError:
        published = None
    caption = " ".join((match.group("caption") or "").split()).strip('"“” ')
    return handle, published, caption[:MAX_CAPTION]


class RoutingPageReader:
    """
    Instagram and Facebook to the browser, everything else to the other reader.

    The chain above it (`FallbackProfileExtractor`) still sees one reader: its name,
    budget and cost are the other reader's, because that is the one that bills.
    """

    def __init__(self, browser: Any, other: Any | None, *, cost: ExtractionCost) -> None:
        self.browser = browser
        self.other = other
        self.name = other.name if other is not None else browser.name
        self.cost = cost
        self.budget = getattr(other, "budget", None)

    def bills(self, url: DiscoveredUrl) -> bool:
        """The browser is free; only what goes to the other reader may cost money."""
        if url.platform in BROWSER_PLATFORMS:
            return False
        return self.other is not None and bills_for(self.other, url)

    async def extract(self, url: DiscoveredUrl):
        return (await self.read(url)).profile

    async def read(self, url: DiscoveredUrl) -> PageRead:
        if url.platform in BROWSER_PLATFORMS:
            return await self.browser.read(url)
        if self.other is None:
            return PageRead(ScrapeOutcome.SKIPPED, detail="No reader for this platform.")
        return await self.other.read(url)

    async def aclose(self) -> None:
        for reader in (self.other, self.browser):
            closer = getattr(reader, "aclose", None)
            if closer is not None:
                await closer()
