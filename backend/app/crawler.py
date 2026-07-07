"""
Playwright-driven crawler for vignaniit.edu.in (or any single-domain site).
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse, urldefrag

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, Page, Browser

logger = logging.getLogger("crawler")

SKIP_EXTENSIONS = (
    ".pdf", ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp",
    ".zip", ".rar", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".mp4", ".mp3", ".avi", ".css", ".js", ".ico", ".xml", ".json",
)

SKIP_PREFIXES = ("mailto:", "tel:", "javascript:", "whatsapp:")


@dataclass
class CrawledPage:
    url: str
    title: str
    text: str


def _same_domain(base: str, candidate: str) -> bool:
    return urlparse(base).netloc.lower() == urlparse(candidate).netloc.lower()


def _normalize_url(url: str) -> str:
    url, _frag = urldefrag(url)
    if url.endswith("/") and len(urlparse(url).path) > 1:
        url = url[:-1]
    return url


def _is_crawlable(url: str, base_url: str) -> bool:
    lower = url.lower()
    if any(lower.startswith(p) for p in SKIP_PREFIXES):
        return False
    if any(lower.split("?")[0].endswith(ext) for ext in SKIP_EXTENSIONS):
        return False
    if not _same_domain(base_url, url):
        return False
    return True


def _extract_text_and_links(html: str, page_url: str) -> tuple[str, str, list[str]]:
    soup = BeautifulSoup(html, "lxml")
    title = (soup.title.string or "").strip() if soup.title else ""

    # Remove script/style etc. first -- these never contain useful links or text.
    for tag in soup(["script", "style", "noscript", "svg", "iframe"]):
        tag.decompose()

    # Collect links BEFORE stripping nav/header/footer -- site navigation
    # links live inside <nav>, so link discovery must happen first.
    links = []
    for a in soup.find_all("a", href=True):
        abs_url = _normalize_url(urljoin(page_url, a["href"].strip()))
        links.append(abs_url)

    # Now strip nav/header/footer before extracting text. On this site they
    # contain the full site menu and footer links, repeated verbatim on
    # every page, which otherwise dominates each chunk's embedding and
    # drowns out the actual unique page content.
    for tag in soup(["nav", "header", "footer"]):
        tag.decompose()

    # Some frameworks wrap navigation/menu/footer content in generic <div>s
    # instead of semantic tags. Catch those too via ARIA roles and common
    # class-name patterns (case-insensitive substring match).
    for tag in soup.find_all(attrs={"role": True}):
        if tag.get("role", "").lower() in ("navigation", "banner", "contentinfo"):
            tag.decompose()
    for tag in soup.find_all(class_=True):
        classes = " ".join(tag.get("class", [])).lower()
        if any(kw in classes for kw in ("navbar", "nav-menu", "site-header", "site-footer",
                                          "topbar", "quick-access", "quickaccess")):
            tag.decompose()

    text = soup.get_text(separator=" ", strip=True)
    text = " ".join(text.split())
    return title, text, links


class SiteCrawler:
    def __init__(
        self,
        base_url: str,
        max_pages: int = 300,
        max_depth: int = 6,
        request_timeout_ms: int = 20000,
        delay_seconds: float = 0.3,
    ):
        self.base_url = _normalize_url(base_url)
        self.max_pages = max_pages
        self.max_depth = max_depth
        self.request_timeout_ms = request_timeout_ms
        self.delay_seconds = delay_seconds

    async def _wait_for_content_settle(
        self,
        page: Page,
        min_chars: int = 200,
        max_wait_ms: int = 6000,
        poll_interval_ms: int = 300,
        stable_checks_required: int = 2,
    ) -> None:
        elapsed = 0
        last_len = -1
        stable_count = 0
        while elapsed < max_wait_ms:
            try:
                text = await page.inner_text("body")
                cur_len = len(text)
            except Exception:
                cur_len = 0
            if cur_len >= min_chars and cur_len == last_len:
                stable_count += 1
                if stable_count >= stable_checks_required:
                    return
            else:
                stable_count = 0
            last_len = cur_len
            await page.wait_for_timeout(poll_interval_ms)
            elapsed += poll_interval_ms

    async def _fetch_page(self, page: Page, url: str) -> str | None:
        try:
            await page.goto(url, timeout=self.request_timeout_ms, wait_until="load")
        except Exception:
            try:
                await page.goto(url, timeout=self.request_timeout_ms, wait_until="domcontentloaded")
            except Exception as e:
                logger.warning("Failed to load %s: %s", url, e)
                return None

        try:
            await self._wait_for_content_settle(page)
        except Exception:
            try:
                await page.wait_for_timeout(1500)
            except Exception:
                pass

        try:
            return await page.content()
        except Exception as e:
            logger.warning("Failed to read content for %s: %s", url, e)
            return None

    async def crawl(self) -> list[CrawledPage]:
        visited: set[str] = set()
        queue: list[tuple[str, int]] = [(self.base_url, 0)]
        results: list[CrawledPage] = []
        seen_content_hashes: set[str] = set()

        async with async_playwright() as pw:
            browser: Browser = await pw.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (compatible; VignanRAGBot/1.0; "
                    "+https://vignaniit.edu.in)"
                )
            )
            page = await context.new_page()

            while queue and len(results) < self.max_pages:
                url, depth = queue.pop(0)
                if url in visited:
                    continue
                visited.add(url)

                html = await self._fetch_page(page, url)
                await asyncio.sleep(self.delay_seconds)
                if html is None:
                    continue

                title, text, links = _extract_text_and_links(html, url)
                if text:
                    if len(text) < 200:
                        logger.warning(
                            "Page content unusually short (%d chars) -- may be a "
                            "client-rendered page that needs more settle time: %s",
                            len(text), url,
                        )

                    content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
                    if content_hash in seen_content_hashes:
                        logger.warning(
                            "Skipping page -- content is identical to an already-captured "
                            "page (likely a route that falls back to serving another page, "
                            "e.g. the homepage): %s",
                            url,
                        )
                    else:
                        seen_content_hashes.add(content_hash)
                        results.append(CrawledPage(url=url, title=title or url, text=text))
                        logger.info("Indexed [%d/%d] %s (%d chars)",
                                    len(results), self.max_pages, url, len(text))

                if depth < self.max_depth:
                    for link in links:
                        if (
                            link not in visited
                            and _is_crawlable(link, self.base_url)
                            and len(visited) + len(queue) < self.max_pages * 3
                        ):
                            queue.append((link, depth + 1))

            await context.close()
            await browser.close()

        return results


async def crawl_site(
    base_url: str,
    max_pages: int = 300,
    max_depth: int = 6,
    request_timeout_ms: int = 20000,
) -> list[CrawledPage]:
    crawler = SiteCrawler(
        base_url=base_url,
        max_pages=max_pages,
        max_depth=max_depth,
        request_timeout_ms=request_timeout_ms,
    )
    return await crawler.crawl()
