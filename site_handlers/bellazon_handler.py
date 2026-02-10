"""
Bellazon / Invision Community (IPS) Forum Handler

Description: Handler for Invision Power Board (IPS Community Suite) forums
             such as bellazon.com. Extracts full-resolution images from
             gallery card thumbnails that link to high-res originals.
Author: Eric Hiss (GitHub: EricRollei)
Contact: eric@historic.camera, eric@rollei.us
License: Dual License (Non-Commercial and Commercial Use)
Copyright (c) 2025 Eric Hiss. All rights reserved.

Dual License:
1. Non-Commercial Use: This software is licensed under the terms of the
   Creative Commons Attribution-NonCommercial 4.0 International License.
   To view a copy of this license, visit http://creativecommons.org/licenses/by-nc/4.0/
   
2. Commercial Use: For commercial use, a separate license is required.
   Please contact Eric Hiss at eric@historic.camera or eric@rollei.us for licensing options.

Dependencies:
This code depends on several third-party libraries, each with its own license.
See CREDITS.md for a comprehensive list of dependencies and their licenses.

Third-party code:
- See CREDITS.md for complete list of dependencies
"""

"""
Bellazon / IPS Community handler for the Web Image Scraper.

Invision Community (IPS) forums use a specific pattern for image galleries:
  - Thumbnail <img> tags have class "ipsImage_thumbnailed" and src URLs
    containing ".thumb.jpg.<hash>.jpg"
  - These thumbnails are wrapped in <a> tags whose href points to the
    full-resolution image (without ".thumb" in the path)
  - Posts are contained in article elements with class "ipsComment"
  - Forums support pagination via /page/N/ URL patterns

This handler:
  1. Detects IPS Community forums (bellazon.com and similar)
  2. Opens spoiler / hidden-content blocks before extraction
  3. Extracts full-resolution image URLs from the <a> wrappers around thumbnails
     and from the data-full-image attribute on <img> tags
  4. Collects YouTube / Vimeo video links found in post content
  5. Optionally crawls multiple pages of a topic
"""

from site_handlers.base_handler import BaseSiteHandler
from urllib.parse import urlparse, urljoin, unquote, urlencode, parse_qs
import re
import time
import asyncio
import traceback

# Safe import for Playwright types
try:
    from playwright.async_api import Page as AsyncPage
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    AsyncPage = None
    PLAYWRIGHT_AVAILABLE = False


class BellazonHandler(BaseSiteHandler):
    """
    Handler for Bellazon.com and other Invision Community (IPS/IPB) forums.

    Targets the common IPS gallery-card pattern where small thumbnails
    (.thumb.jpg) link to full-resolution originals.
    """

    # Known IPS Community forum domains
    IPS_DOMAINS = [
        "bellazon.com",
        # Add more IPS-powered fashion/model forums here as discovered
    ]

    # Regex to detect IPS-style paginated topic URLs
    IPS_TOPIC_PATTERN = re.compile(
        r"https?://(?:www\.)?[^/]+/(?:main/)?(?:topic|forum)/\d+",
        re.IGNORECASE,
    )

    # Regex to strip ".thumb" from an IPS upload URL to get the full-res version
    # e.g.  …/filename.thumb.jpg.hash.jpg  →  …/filename.jpg.hash.jpg
    THUMB_STRIP_RE = re.compile(r"\.thumb\.(jpe?g|png|gif|webp)", re.IGNORECASE)

    # Regex to match YouTube / Vimeo video URLs found in post content
    VIDEO_LINK_RE = re.compile(
        r"https?://(?:www\.)?(?:"
        r"youtube\.com/watch\?[^\s\"'<>]+"
        r"|youtu\.be/[\w-]+"
        r"|youtube\.com/embed/[\w-]+"
        r"|youtube\.com/shorts/[\w-]+"
        r"|vimeo\.com/\d+"
        r"|player\.vimeo\.com/video/\d+"
        r")",
        re.IGNORECASE,
    )

    def __init__(self, url, scraper=None):
        super().__init__(url, scraper)
        self.debug_mode = getattr(scraper, "debug_mode", False)
        self.start_time = time.time()
        # Normalise the URL: strip /page/N/ so we have a clean base for pagination
        self.base_topic_url = self._strip_page_number(url)
        self.start_page = self._get_page_number(url)
        print(f"[BellazonHandler] Initialized for {url}")
        print(f"[BellazonHandler] Base topic URL: {self.base_topic_url}, start page: {self.start_page}")

    # ------------------------------------------------------------------
    # Detection
    # ------------------------------------------------------------------
    @classmethod
    def can_handle(cls, url):
        """Return True for URLs on known IPS Community forums."""
        url_lower = url.lower()
        for domain in cls.IPS_DOMAINS:
            if domain in url_lower:
                return True
        # Also match generic IPS topic URL patterns with /uploads/ evidence
        if cls.IPS_TOPIC_PATTERN.search(url):
            # Only claim if the domain looks like a forum
            parsed = urlparse(url)
            path = parsed.path.lower()
            if "/topic/" in path or "/forum/" in path:
                # Heuristic: could be IPS, but only claim known domains
                # to avoid false positives with other forum software
                pass
        return False

    # ------------------------------------------------------------------
    # Trusted domains
    # ------------------------------------------------------------------
    def get_trusted_domains(self) -> list:
        """IPS forums host uploads on the same domain."""
        return [self.domain, f"www.{self.domain}"]

    # ------------------------------------------------------------------
    # Content directory
    # ------------------------------------------------------------------
    def get_content_directory(self):
        """Generate a meaningful output directory based on the topic."""
        parsed = urlparse(self.url)
        path_parts = [p for p in parsed.path.strip("/").split("/") if p]

        base_dir = self._sanitize_directory_name(self.domain.split(".")[0])

        # Try to extract topic slug  (e.g. "88521-clémence-navarro")
        topic_dir = "general"
        for i, part in enumerate(path_parts):
            if part == "topic" and i + 1 < len(path_parts):
                topic_dir = self._sanitize_directory_name(
                    unquote(path_parts[i + 1])
                )
                break

        return (base_dir, topic_dir)

    # ------------------------------------------------------------------
    # Main Playwright extraction (async)
    # ------------------------------------------------------------------
    async def extract_with_direct_playwright(self, page, **kwargs) -> list:
        """
        Extract full-resolution images from ALL pages of an IPS forum topic.

        Workflow:
          1. Detect total page count from the pagination controls
          2. Extract images from the current (or first) page
          3. Navigate to each subsequent page and extract images
          4. Respect the scraper's max_pages setting to cap how far we go
        """
        print(f"[BellazonHandler] Starting multi-page extraction …")

        # Determine how many pages to visit
        # The scraper passes max_pages via kwargs from the UI "Max Pages to Visit" control
        max_pages = kwargs.get("max_pages", 500)
        # Also check the scraper instance for max_pages if not in kwargs
        if max_pages <= 1 and hasattr(self, "scraper") and self.scraper:
            max_pages = getattr(self.scraper, "max_pages", 500)

        # Detect total number of pages from IPS pagination
        total_pages = await self._detect_total_pages(page)
        print(f"[BellazonHandler] Detected {total_pages} total page(s) in topic")

        # Determine page range
        pages_to_visit = min(total_pages, max_pages)
        start = self.start_page
        end = min(start + pages_to_visit - 1, total_pages)
        print(f"[BellazonHandler] Will scrape pages {start} through {end} "
              f"(max_pages={max_pages})")

        all_media_items = []
        seen_urls = set()

        for page_num in range(start, end + 1):
            # Navigate to the correct page (skip navigation for the first page
            # since we're already on it)
            if page_num != self.start_page:
                page_url = self._build_page_url(page_num)
                print(f"[BellazonHandler] Navigating to page {page_num}/{end}: {page_url}")
                try:
                    await page.goto(page_url, timeout=30000, wait_until="load")
                    # Small delay to let IPS JS / lazy-loading settle
                    await page.wait_for_timeout(1500)
                except Exception as e:
                    print(f"[BellazonHandler] Failed to navigate to page {page_num}: {e}")
                    continue

            # Extract images from this page
            page_items = await self._extract_images_from_current_page(
                page, page_num, seen_urls
            )
            all_media_items.extend(page_items)
            print(f"[BellazonHandler] Page {page_num}: {len(page_items)} images "
                  f"(running total: {len(all_media_items)})")

            # Safety: don't hammer the server
            if page_num < end:
                await page.wait_for_timeout(500)

        # --- Fallback: use base handler if we found nothing ---
        if not all_media_items:
            print("[BellazonHandler] No items from IPS-specific extraction, "
                  "falling back to base handler")
            all_media_items = await super().extract_with_direct_playwright(
                page, **kwargs
            )

        print(f"[BellazonHandler] Total images extracted across all pages: "
              f"{len(all_media_items)}")

        # Final safety pass: strip any remaining .thumb. URLs and deduplicate
        all_media_items = await self.post_process(all_media_items)
        print(f"[BellazonHandler] After post-processing: {len(all_media_items)} images")

        return all_media_items

    # ------------------------------------------------------------------
    # Single-page image extraction (called per page)
    # ------------------------------------------------------------------
    async def _extract_images_from_current_page(
        self, page, page_num: int, seen_urls: set
    ) -> list:
        """Extract full-res images from the currently-loaded IPS page.

        IPS Community HTML structure (confirmed on bellazon.com):
        ─────────────────────────────────────────────────────────
        Every user-uploaded image appears as:

          <a class="ipsAttachLink ipsAttachLink_image"
             href="https://…/uploads/…/name.jpg.HASH_FULL.jpg"
             data-fileid="12345" data-fileext="jpg">
            <img class="ipsImage ipsImage_thumbnailed"
                 data-fileid="12345"
                 src="https://…/uploads/…/name.thumb.jpg.HASH_THUMB.jpg"
                 width="241" alt="…">
          </a>

        KEY INSIGHT: the hash in the thumb URL is DIFFERENT from the hash
        in the full-res URL.  You cannot derive full-res from the thumb
        src via regex – you MUST read the parent <a> href.

        Strategy:
          1. Grab every <a class*="ipsAttachLink_image"> href (full-res)
          2. For any remaining content <img> not already covered, accept
             it ONLY if its src does NOT contain ".thumb." (direct-linked
             full-res images that some users paste).
          3. NEVER add a URL that contains ".thumb." – it always points
             to a low-res thumbnail with a wrong hash.
        """
        media_items = []

        try:
            # Wait for post content to be present
            try:
                await page.wait_for_selector(
                    "article.ipsComment, div.ipsComment, div.cPost",
                    timeout=15000,
                )
            except Exception:
                print(f"[BellazonHandler] Page {page_num}: could not find IPS "
                      "post containers, proceeding with full-page extraction")

            # --- Reveal spoiler / hidden content blocks ---
            await self._open_spoilers(page, page_num)

            # --- JavaScript extraction ---
            extracted_items = await page.evaluate("""
                () => {
                    const results = [];
                    const seen = new Set();       // full-res URLs already added
                    const seenThumbs = new Set();  // thumb srcs we've resolved via <a>

                    // Helper: is this a content image URL (not UI junk)?
                    const isContentUrl = (url) => {
                        if (!url) return false;
                        const lower = url.toLowerCase();
                        // Must be an image
                        if (!/\\.(jpe?g|png|gif|webp)/i.test(lower)) return false;
                        // Reject common UI images
                        if (/\\/emoticons\\/|default_photo|\\/avatars?\\/|\\/core_|\\/emoji\\/|favicon|logo/i.test(lower)) return false;
                        return true;
                    };

                    // Helper: add to results if the full URL is not yet seen
                    const addIfNew = (fullUrl, thumbSrc, img) => {
                        if (!fullUrl || seen.has(fullUrl)) return;
                        if (!isContentUrl(fullUrl)) return;
                        // REJECT any URL that still contains .thumb.
                        if (fullUrl.includes('.thumb.')) return;
                        seen.add(fullUrl);
                        if (thumbSrc) seenThumbs.add(thumbSrc);
                        results.push({
                            url: fullUrl,
                            thumb_url: thumbSrc || '',
                            alt: img ? (img.alt || '') : '',
                            width: img ? (img.naturalWidth || 0) : 0,
                            height: img ? (img.naturalHeight || 0) : 0,
                            data_fileid: img ? (img.getAttribute('data-fileid') || '') : '',
                        });
                    };

                    // ── Strategy 1 (PRIMARY): <a> links around thumbnails ──
                    // The <a href> IS the authoritative full-res URL.
                    // Also handles lightbox links (data-ipslightbox).
                    document.querySelectorAll(
                        'a.ipsAttachLink_image[href], ' +
                        'a.ipsAttachLink[href], ' +
                        'a[data-ipslightbox][href]'
                    ).forEach(link => {
                        const href = link.href;
                        if (!href) return;
                        const img = link.querySelector('img');
                        const thumbSrc = img ? img.src : '';
                        if (thumbSrc) seenThumbs.add(thumbSrc);
                        addIfNew(href, thumbSrc, img);
                    });

                    // Also catch thumbnails with data-fileid whose parent
                    // <a> might not have the ipsAttachLink class
                    document.querySelectorAll(
                        'a[href] img.ipsImage_thumbnailed, ' +
                        'a[href] img[data-fileid]'
                    ).forEach(img => {
                        const link = img.closest('a');
                        if (!link) return;
                        const href = link.href;
                        if (!href) return;
                        const thumbSrc = img.src || '';
                        if (thumbSrc) seenThumbs.add(thumbSrc);
                        addIfNew(href, thumbSrc, img);
                    });

                    // ── Strategy 2: data-full-image attribute ──
                    // IPS sometimes puts the full-res URL in a data
                    // attribute on the <img> itself.
                    document.querySelectorAll('img[data-full-image]').forEach(img => {
                        const fullUrl = img.getAttribute('data-full-image');
                        const thumbSrc = img.src || '';
                        if (thumbSrc) seenThumbs.add(thumbSrc);
                        addIfNew(fullUrl, thumbSrc, img);
                    });

                    // ── Strategy 3: Non-thumbnail content images ──
                    // Some users paste direct full-res URLs into posts.
                    // These imgs will NOT have .thumb. in their src and
                    // will NOT have been caught by earlier strategies.
                    document.querySelectorAll(
                        'div[data-role="commentContent"] img, ' +
                        'div.ipsType_richText img, ' +
                        'div.cPost_contentWrap img'
                    ).forEach(img => {
                        const src = img.src;
                        if (!src || src.startsWith('data:')) return;
                        // Skip if we already resolved this thumb via <a> href
                        if (seenThumbs.has(src)) return;
                        if (seen.has(src)) return;
                        // REJECT any remaining .thumb. URL – we have no way
                        // to derive the correct full-res hash from it
                        if (src.includes('.thumb.')) return;
                        // Skip tiny UI images
                        if (img.naturalWidth && img.naturalWidth < 80) return;
                        if (img.naturalHeight && img.naturalHeight < 80) return;
                        // Skip avatars and profile photos
                        if (img.closest('.ipsUserPhoto, .ipsPhotoPanel, .cAuthorPane')) return;
                        // Skip quoted content to avoid duplicates
                        if (img.closest('blockquote, .ipsQuote')) return;
                        addIfNew(src, '', img);
                    });

                    return results;
                }
            """)

            if extracted_items:
                print(f"[BellazonHandler] Page {page_num}: JS extracted "
                      f"{len(extracted_items)} full-res image URLs")

            for item in extracted_items:
                url = item.get("url", "")
                if not url:
                    continue

                # ABSOLUTE SAFETY: reject any URL still containing .thumb.
                # (The JS already filters these, but belt-and-suspenders)
                if ".thumb." in url.lower():
                    if self.debug_mode:
                        print(f"[BellazonHandler] REJECTED thumb URL: {url[:80]}…")
                    continue

                if url in seen_urls:
                    continue
                seen_urls.add(url)

                # Ensure absolute URL
                if not url.startswith("http"):
                    url = urljoin(self.url, url)

                # Determine title from alt text or filename
                alt = item.get("alt", "")
                title = self._clean_title(alt) if alt else self._title_from_url(url)

                media_items.append({
                    "url": url,
                    "type": "image",
                    "title": title,
                    "alt": alt,
                    "width": item.get("width", 0),
                    "height": item.get("height", 0),
                    "source_url": self.url,
                    "trusted_cdn": True,
                    "data_fileid": item.get("data_fileid", ""),
                    "thumb_url": item.get("thumb_url", ""),
                })

            # --- Collect video links (YouTube / Vimeo) ---
            video_items = await self._extract_video_links(page, page_num, seen_urls)
            if video_items:
                media_items.extend(video_items)

        except Exception as e:
            print(f"[BellazonHandler] Error during extraction: {e}")
            traceback.print_exc()

        return media_items

    # ------------------------------------------------------------------
    # Spoiler / hidden-content handling
    # ------------------------------------------------------------------
    async def _open_spoilers(self, page, page_num: int) -> int:
        """
        Open all spoiler / hidden-content blocks on the current page so
        that their images become visible in the DOM.

        IPS Community uses HTML5 <details> elements for spoilers:
          <details class="ipsRichTextBox">
            <summary class="ipsRichTextBox__title">
              <p>Spoiler Nudity</p>        ← or "Spoiler", "Reveal hidden contents", etc.
            </summary>
            … hidden images / content …
          </details>

        Approach:
          1. Use JavaScript to programmatically set the `open` attribute on
             every <details> element – this is instantaneous and avoids
             click-timing issues.
          2. Fall back to clicking <summary> elements if JS approach fails.
          3. Wait briefly for any lazy-loaded images inside spoilers to load.

        Returns the number of spoiler blocks that were opened.
        """
        try:
            opened = await page.evaluate("""
                () => {
                    let count = 0;
                    // Open ALL <details> elements (IPS spoiler blocks)
                    document.querySelectorAll('details').forEach(d => {
                        if (!d.open) {
                            d.open = true;
                            count++;
                        }
                    });
                    // Also look for IPS-specific spoiler toggles that might
                    // not use <details> (older IPS versions)
                    document.querySelectorAll(
                        '.ipsSpoiler_header, ' +
                        '[data-action="toggleSpoiler"], ' +
                        '.ipsStyle_spoiler'
                    ).forEach(btn => {
                        const container = btn.closest('.ipsSpoiler, [data-ipsSpoiler]');
                        if (container) {
                            container.classList.add('ipsSpoiler_open');
                            container.style.display = '';
                            // Un-hide the content inside
                            const content = container.querySelector(
                                '.ipsSpoiler_contents, .ipsSpoiler_content'
                            );
                            if (content) {
                                content.style.display = '';
                                content.style.visibility = 'visible';
                                content.style.maxHeight = 'none';
                            }
                            count++;
                        }
                    });
                    return count;
                }
            """)

            if opened > 0:
                print(f"[BellazonHandler] Page {page_num}: opened {opened} "
                      f"spoiler/hidden-content block(s)")
                # Wait for any lazy-loaded images inside spoilers to start loading
                await page.wait_for_timeout(1000)

                # Trigger lazy loading by scrolling spoiler content into view
                await page.evaluate("""
                    () => {
                        document.querySelectorAll(
                            'details[open] img[loading="lazy"], ' +
                            '.ipsSpoiler_open img[loading="lazy"]'
                        ).forEach(img => {
                            img.scrollIntoView({ behavior: 'instant', block: 'center' });
                        });
                    }
                """)
                await page.wait_for_timeout(500)

            return opened

        except Exception as e:
            print(f"[BellazonHandler] Page {page_num}: error opening spoilers: {e}")
            # Fallback: try clicking <summary> elements directly
            try:
                summaries = page.locator("details:not([open]) > summary")
                count = await summaries.count()
                if count > 0:
                    print(f"[BellazonHandler] Page {page_num}: clicking "
                          f"{count} <summary> element(s) as fallback")
                    for i in range(count):
                        try:
                            await summaries.nth(i).click(timeout=2000)
                        except Exception:
                            pass
                    await page.wait_for_timeout(800)
                    return count
            except Exception:
                pass
            return 0

    # ------------------------------------------------------------------
    # Video link collection
    # ------------------------------------------------------------------
    async def _extract_video_links(
        self, page, page_num: int, seen_urls: set
    ) -> list:
        """
        Collect YouTube and Vimeo video URLs found in post content.

        These are returned as media items with type="video" so the
        scraper can log them.  They won't be downloaded by the image
        scraper but will appear in the results / metadata for the user
        to process with the yt-dlp node if desired.
        """
        video_items = []
        try:
            raw_links = await page.evaluate("""
                () => {
                    const links = new Set();
                    // 1. <a> tags linking to YouTube / Vimeo
                    document.querySelectorAll(
                        'div[data-role="commentContent"] a[href], ' +
                        'div.ipsType_richText a[href], ' +
                        'div.cPost_contentWrap a[href]'
                    ).forEach(a => {
                        const href = a.href || '';
                        if (/youtu\.?be|youtube\.com|vimeo\.com/i.test(href)) {
                            links.add(href);
                        }
                    });
                    // 2. Embedded iframes (YouTube / Vimeo embeds)
                    document.querySelectorAll(
                        'iframe[src]'
                    ).forEach(iframe => {
                        const src = iframe.src || '';
                        if (/youtube\.com\/embed|player\.vimeo\.com/i.test(src)) {
                            links.add(src);
                        }
                    });
                    // 3. IPS oembed containers
                    document.querySelectorAll(
                        '[data-embed-src]'
                    ).forEach(el => {
                        const src = el.getAttribute('data-embed-src') || '';
                        if (/youtu\.?be|youtube\.com|vimeo\.com/i.test(src)) {
                            links.add(src);
                        }
                    });
                    return Array.from(links);
                }
            """)

            for link in raw_links:
                if not link or link in seen_urls:
                    continue
                seen_urls.add(link)

                # Normalise embed URLs to standard watch URLs
                clean_url = self._normalise_video_url(link)

                video_items.append({
                    "url": clean_url,
                    "type": "video",
                    "title": f"Video: {clean_url}",
                    "alt": "",
                    "width": 0,
                    "height": 0,
                    "source_url": self.url,
                    "trusted_cdn": True,
                    "platform": "youtube" if "youtu" in clean_url.lower() else "vimeo",
                })

            if video_items:
                print(f"[BellazonHandler] Page {page_num}: collected "
                      f"{len(video_items)} video link(s)")

        except Exception as e:
            if self.debug_mode:
                print(f"[BellazonHandler] Page {page_num}: error collecting "
                      f"video links: {e}")

        return video_items

    @staticmethod
    def _normalise_video_url(url: str) -> str:
        """
        Convert embed / shortened video URLs to canonical watch URLs.

        Examples:
          https://www.youtube.com/embed/ABC123  →  https://www.youtube.com/watch?v=ABC123
          https://youtu.be/ABC123               →  https://www.youtube.com/watch?v=ABC123
          https://player.vimeo.com/video/12345  →  https://vimeo.com/12345
        """
        # YouTube embed → watch
        m = re.search(r"youtube\.com/embed/([\w-]+)", url)
        if m:
            return f"https://www.youtube.com/watch?v={m.group(1)}"
        # YouTube short URL
        m = re.search(r"youtu\.be/([\w-]+)", url)
        if m:
            return f"https://www.youtube.com/watch?v={m.group(1)}"
        # YouTube shorts
        m = re.search(r"youtube\.com/shorts/([\w-]+)", url)
        if m:
            return f"https://www.youtube.com/watch?v={m.group(1)}"
        # Vimeo player embed
        m = re.search(r"player\.vimeo\.com/video/(\d+)", url)
        if m:
            return f"https://vimeo.com/{m.group(1)}"
        return url

    # ------------------------------------------------------------------
    # Pagination helpers
    # ------------------------------------------------------------------
    async def _detect_total_pages(self, page) -> int:
        """
        Read the IPS pagination controls to determine the total number of
        pages in the current topic.

        IPS pagination HTML typically looks like:
          <li class="ipsPagination_last">
            <a href="…/page/16/" …>Last</a>
          </li>
        or the pagination bar contains numbered links like:
          <a …>16</a>
        We also look for the "PAGE X OF Y" text.
        """
        try:
            total = await page.evaluate("""
                () => {
                    // Strategy 1: "PAGE X OF Y" text  (e.g. "PAGE 2 OF 16")
                    const pageOfText = document.body.innerText.match(
                        /PAGE\\s+(\\d+)\\s+OF\\s+(\\d+)/i
                    );
                    if (pageOfText) return parseInt(pageOfText[2], 10);

                    // Strategy 2: Last-page link
                    const lastLink = document.querySelector(
                        'li.ipsPagination_last a[href], ' +
                        'a.ipsPagination_last[href]'
                    );
                    if (lastLink) {
                        const href = lastLink.href;
                        const m = href.match(/\\/page\\/(\\d+)/);
                        if (m) return parseInt(m[1], 10);
                    }

                    // Strategy 3: Highest numbered page link in the paginator
                    let maxPage = 1;
                    document.querySelectorAll(
                        'ul.ipsPagination li a, ' +
                        'div.ipsPagination a'
                    ).forEach(a => {
                        const href = a.href || '';
                        const m = href.match(/\\/page\\/(\\d+)/);
                        if (m) {
                            const n = parseInt(m[1], 10);
                            if (n > maxPage) maxPage = n;
                        }
                        // Also check link text for plain numbers
                        const txt = a.textContent.trim();
                        if (/^\\d+$/.test(txt)) {
                            const n = parseInt(txt, 10);
                            if (n > maxPage) maxPage = n;
                        }
                    });
                    return maxPage;
                }
            """)
            return max(1, total)
        except Exception as e:
            print(f"[BellazonHandler] Could not detect page count: {e}")
            return 1

    def _strip_page_number(self, url: str) -> str:
        """
        Remove /page/N/ from an IPS topic URL to get the base URL.
        e.g. …/topic/88521-name/page/2/  →  …/topic/88521-name/
        """
        return re.sub(r"/page/\d+/?", "/", url).rstrip("/") + "/"

    def _get_page_number(self, url: str) -> int:
        """Extract the page number from a URL, defaulting to 1."""
        m = re.search(r"/page/(\d+)", url)
        return int(m.group(1)) if m else 1

    def _build_page_url(self, page_num: int) -> str:
        """
        Build the URL for a specific page number of the topic.
        Page 1 uses the base URL (no /page/ suffix).
        """
        base = self.base_topic_url.rstrip("/")
        if page_num <= 1:
            return base + "/"
        return f"{base}/page/{page_num}/"

    # ------------------------------------------------------------------
    # Post-processing
    # ------------------------------------------------------------------
    async def post_process(self, media_items):
        """
        Final safety pass before items are sent to the download queue.

        Rules:
          1. REJECT any URL that still contains ".thumb." – these are
             low-res thumbnails and their hash is different from the
             full-res version, so stripping .thumb. would produce a 404.
          2. Deduplicate by URL.
          3. Remove common non-content images (emoticons, avatars, etc.).
        """
        upgraded = []
        seen = set()
        rejected_thumbs = 0

        for item in media_items:
            url = item.get("url", "")
            if not url:
                continue

            # HARD REJECT: any URL containing .thumb. is a thumbnail
            # with a wrong hash – do NOT try to "fix" it, just drop it
            if ".thumb." in url.lower():
                rejected_thumbs += 1
                continue

            # Deduplicate
            if url in seen:
                continue
            seen.add(url)

            # Filter out common non-content images
            url_lower = url.lower()
            if any(p in url_lower for p in [
                "/emoticons/", "/emoji/", "default_photo",
                "profile_photo", "/avatars/", "/reputation/",
                "/core_", "favicon",
            ]):
                continue

            upgraded.append(item)

        if rejected_thumbs:
            print(f"[BellazonHandler] post_process rejected {rejected_thumbs} "
                  f"remaining .thumb. URLs")

        return upgraded

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _clean_title(self, alt_text: str) -> str:
        """
        Clean an IPS image alt text to produce a readable title.
        IPS alt text often looks like:
          'filename.thumb.jpg.hash.jpg'
        """
        if not alt_text:
            return "Untitled"
        # Remove hash suffixes  (e.g. .bbef56b4...695b.jpg)
        cleaned = re.sub(r"\.[a-f0-9]{20,}\.(jpe?g|png|gif|webp)$", "", alt_text, flags=re.IGNORECASE)
        # Remove .thumb
        cleaned = re.sub(r"\.thumb", "", cleaned, flags=re.IGNORECASE)
        # Remove file extension
        cleaned = re.sub(r"\.(jpe?g|png|gif|webp)$", "", cleaned, flags=re.IGNORECASE)
        # Replace underscores/dashes with spaces
        cleaned = cleaned.replace("_", " ").replace("-", " ")
        # Collapse whitespace
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned if cleaned else "Untitled"

    def _title_from_url(self, url: str) -> str:
        """Extract a human-readable title from a URL path."""
        try:
            path = urlparse(url).path
            filename = path.rsplit("/", 1)[-1] if "/" in path else path
            return self._clean_title(unquote(filename))
        except Exception:
            return "Untitled"

    @staticmethod
    def _strip_thumb(url: str) -> str:
        """Remove .thumb from an IPS upload URL to get the full-res version."""
        return BellazonHandler.THUMB_STRIP_RE.sub(r".\1", url)
