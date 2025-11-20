"""
Artsy Handler

Description: ComfyUI custom node for downloading and scraping media from websites
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

# artsy_handler.py
"""
Artsy.net specific handler for the Web Image Scraper - Enhanced Version
With API-first approach and fallback to DOM scraping
"""

import re
import time
import json
import traceback

from site_handlers.base_handler import BaseSiteHandler
from urllib.parse import urljoin, urlparse
import os

# We'll use requests for Artsy API calls
try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    requests = None
    REQUESTS_AVAILABLE = False

# Try importing Playwright types safely
try:
    from playwright.async_api import Page as AsyncPage
    from scrapling.fetchers import PlayWrightFetcher
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    AsyncPage = None
    PlayWrightFetcher = None
    PLAYWRIGHT_AVAILABLE = False

class ArtsyHandler(BaseSiteHandler):
    """
    Handler for Artsy.net with API-first approach.
    1) Attempt to fetch artworks from the Artsy API if XAPP token/credentials are available.
    2) Fallback to DOM-based scraping if the API approach fails or returns nothing.
    """

    @classmethod
    def can_handle(cls, url):
        """Check if this handler can process the URL"""
        return "artsy.net" in url.lower()

    def __init__(self, url, scraper=None):
        """Initialize with Artsy-specific properties"""
        super().__init__(url, scraper)
        self.debug_mode = True  # Set True for detailed logging
        self.page_type = self._determine_page_type(url)

        # New: Artsy API usage flags
        self.use_api = REQUESTS_AVAILABLE
        self.artsy_token = None

        print(f"ArtsyHandler initialized for URL: {url} (page type: {self.page_type})")

    def _determine_page_type(self, url):
        """Determine the type of Artsy page we're dealing with"""
        url_lower = url.lower()
        if "/artwork/" in url_lower:
            return "artwork"
        elif "/artist/" in url_lower:
            return "artist"
        elif "/show/" in url_lower:
            return "show"
        elif "/collection/" in url_lower:
            return "collection"
        elif "/auction/" in url_lower:
            return "auction"
        else:
            return "general"

    def get_default_interaction_sequence(self):
        return [
            # Accept cookies if present
            {"type": "wait_for_selector", "selector": "button:has-text('Agree'), button:has-text('Accept')", "timeout": 4000},
            {"type": "click", "selector": "button:has-text('Agree'), button:has-text('Accept')"},
            # Dismiss login/signup popup if present
            {"type": "wait_for_selector", "selector": "button[aria-label='Close']", "timeout": 3000},
            {"type": "click", "selector": "button[aria-label='Close']"},
            # Scroll to load more artworks
            {"type": "scroll", "scroll_count": 10, "scroll_delay": 1000}
        ]

    async def _auto_scroll(self, page, scroll_count=10, scroll_delay=1000):
        for _ in range(scroll_count):
            await page.mouse.wheel(0, 1000)
            await page.wait_for_timeout(scroll_delay)

    async def extract_with_direct_playwright_async(self, page, **kwargs):
        print(f"[ArtsyHandler] extract_with_direct_playwright_async() for {self.page_type} page")

        # Use pagination for collection pages
        if self.page_type == "collection":
            max_pages = kwargs.get("max_pages", 10)
            return await self.extract_collection_with_pagination(page, max_pages=max_pages, **kwargs)

        interaction_sequence = kwargs.get("interaction_sequence") or getattr(self, "interaction_sequence", None)
        if not interaction_sequence:
            interaction_sequence = self.get_default_interaction_sequence()
        await self._run_interaction_sequence(page, interaction_sequence)

        # --- Optional scroll ---
        do_scroll = kwargs.get("do_scroll", True)
        scroll_count = kwargs.get("scroll_count", 10)
        scroll_delay = kwargs.get("scroll_delay", 1000)
        if do_scroll:
            print(f"[ArtsyHandler] Performing auto-scroll: {scroll_count} times, {scroll_delay}ms delay")
            await self._auto_scroll(page, scroll_count=scroll_count, scroll_delay=scroll_delay)

        # 1) If we have an Artsy token, attempt API-based extraction
        if self.artsy_token:
            try:
                api_items = self._extract_via_artsy_api()
                if api_items:
                    print(f"[ArtsyHandler] Got {len(api_items)} items from the Artsy API")
                    return api_items
                else:
                    print("[ArtsyHandler] API returned no items, using DOM-based fallback.")
            except Exception as e:
                print(f"[ArtsyHandler] Error in API extraction: {e}")
                traceback.print_exc()
                print("[ArtsyHandler] Using DOM-based fallback...")

        # 2) Try Canvas-Based Extraction for high-resolution images first
        canvas_items = await self._extract_canvas_images_async(page)
        if canvas_items:
            print(f"[ArtsyHandler] Canvas extraction found {len(canvas_items)} high-resolution images")
            return canvas_items

        # 3) Fallback: async DOM/HTML-based scraping
        dom_items = await self._dom_extract_async(page)
        print(f"[ArtsyHandler] DOM-based extraction returned {len(dom_items)} items")
        return dom_items

    def _init_artsy_api(self):
        """
        Attempt to retrieve an Artsy XAPP token from credentials.
        Expects self.scraper.auth_config and site-specific 'client_id'/'client_secret'.
        """
        # Keep this method as-is since it's non-async API calls with requests
        # ... (existing implementation)

    async def _run_interaction_sequence(self, page, sequence):
        for step in sequence:
            try:
                timeout = step.get("timeout", 5000)
                if step["type"] == "wait_for_selector":
                    await page.wait_for_selector(step["selector"], timeout=timeout)
                elif step["type"] == "click":
                    await page.click(step["selector"])
                elif step["type"] == "fill":
                    await page.fill(step["selector"], step["value"])
                elif step["type"] == "press":
                    await page.press(step["selector"], step["key"])
                elif step["type"] == "wait_for_timeout":
                    await page.wait_for_timeout(step["timeout"])
                elif step["type"] == "scroll":
                    for _ in range(step.get("scroll_count", 5)):
                        await page.mouse.wheel(0, 1000)
                        await page.wait_for_timeout(step.get("scroll_delay", 1000))
            except Exception as e:
                print(f"Interaction step failed: {step} - {e}")

    def _extract_via_artsy_api(self):
        """
        Perform an API-based extraction:
          - Figure out what we are scraping (artist page vs. single artwork, etc.)
          - Query the relevant Artsy API endpoints
          - Return a list of media items in the standard format
        """
        # Keep this method as-is since it's non-async API calls with requests
        # ... (existing implementation)

    async def _dom_extract_async(self, page):
        """
        The async version of DOM extraction.
        1) If it's an 'artwork' page, run _extract_artwork_page_async()
        2) Else if it's an 'artist/collection/etc.' page, run _extract_grid_page_async()
        3) If still nothing, use the general approach
        """
        media_items = []
        if self.page_type == "artwork":
            print("Extracting from an individual artwork page (fallback)...")
            items = await self._extract_artwork_page_async(page)
            media_items.extend(items)
        else:
            print("Extracting from a grid-based page (fallback)...")
            items = await self._extract_grid_page_async(page)
            media_items.extend(items)

        if not media_items:
            print("No items from the specialized fallback, using general approach")
            general_items = await self._extract_general_images_async(page)
            media_items.extend(general_items)

            if not media_items:
                print("Still no items, trying direct HTML extraction as a last resort")
                html_items = await self._extract_media_from_html_async(page)
                media_items.extend(html_items)

        print(f"[ArtsyHandler fallback] Extracted {len(media_items)} items total (DOM approach)")
        return media_items

    async def _extract_highres_from_artwork_page(self, page, artwork_url, click_count=3):
        """Open artwork page, click image multiple times, extract high-res image URL."""
        await page.goto(artwork_url, timeout=60000)
        await page.wait_for_timeout(2000)

        # Click the main image multiple times
        img_selector = 'img[data-test="artworkImage"], [class*="Artwork"] img'
        for _ in range(click_count):
            img = page.locator(img_selector).first
            try:
                await img.wait_for(timeout=3000)
                await img.click()
                await page.wait_for_timeout(1000)
            except Exception as e:
                print(f"Could not click image: {e}")
                break

        # After clicks, try to get the highest-res image URL
        try:
            img = page.locator(img_selector).first
            await img.wait_for(timeout=3000)
            src = await img.get_attribute('src')
            srcset = await img.get_attribute('srcset')
            best_url = src
            if srcset:
                best_url = self._get_best_image_from_srcset(srcset) or src
            if best_url and not best_url.startswith('data:'):
                return best_url
        except Exception as e:
            print(f"Could not extract high-res image: {e}")
        return None

    async def extract_collection_with_pagination(self, page, max_pages=10, **kwargs):
        """
        Extract images from paginated Artsy collection pages by modifying the ?page=N parameter.
        """
        from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

        all_items = []
        base_url = self.url.split('?')[0]
        for page_num in range(1, max_pages + 1):
            # Build paginated URL
            url_parts = list(urlparse(base_url))
            query = dict(parse_qs(urlparse(self.url).query))
            query['page'] = str(page_num)
            url_parts[4] = urlencode(query, doseq=True)
            paged_url = urlunparse(url_parts)

            print(f"[ArtsyHandler] Visiting page {page_num}: {paged_url}")
            await page.goto(paged_url, timeout=60000)
            await page.wait_for_timeout(2000)

            # Run interaction sequence if needed (e.g., cookie banners)
            interaction_sequence = kwargs.get("interaction_sequence") or getattr(self, "interaction_sequence", None)
            if not interaction_sequence:
                interaction_sequence = self.get_default_interaction_sequence()
            await self._run_interaction_sequence(page, interaction_sequence)

            # --- Use high-res extraction here ---
            items = await self._extract_grid_page_highres_async(page)
            print(f"[ArtsyHandler] Extracted {len(items)} high-res items from page {page_num}")
            if not items:
                print("[ArtsyHandler] No more items found, stopping pagination.")
                break
            all_items.extend(items)

        return all_items

    async def _extract_and_follow_links(self, page, base_url, max_depth=1, current_depth=0, 
                                    visited_urls=None, same_domain_only=True, max_pages=10, **kwargs):
        """Extract content from the current page and follow links (async version)."""
        # Define wait_until_strategy at the beginning
        wait_until_strategy = "networkidle" if kwargs.get('wait_for_network_idle', False) else "load"
        
        if visited_urls is None:
            visited_urls = set()
        
        # Extract media from current page
        media_items = await self._dom_extract_async(page)
        
        # If we've reached max depth or max pages, stop here
        if current_depth >= max_depth or len(visited_urls) >= max_pages:
            return media_items
        
        # Find links to follow
        links = []
        try:
            # Find all links on the page that contain '/artwork/' or '/artist/'
            link_elems = page.locator('a[href*="/artwork/"], a[href*="/artist/"]')
            count = await link_elems.count()
            
            for i in range(count):
                try:
                    link = link_elems.nth(i)
                    href = await link.get_attribute('href')
                    if href:
                        full_url = urljoin(base_url, href)
                        # Only add if in same domain & not already visited
                        parsed_url = urlparse(full_url)
                        parsed_base = urlparse(base_url)
                        
                        if (not same_domain_only or parsed_url.netloc == parsed_base.netloc) and \
                        full_url not in visited_urls:
                            links.append(full_url)
                except Exception as e:
                    if self.debug_mode:
                        print(f"Error extracting link {i}: {e}")
        except Exception as e:
            print(f"Error finding links on page: {e}")
        
        # Visit each link up to max_pages
        links_to_visit = links[:max_pages - len(visited_urls)]
        for link in links_to_visit:
            if link in visited_urls:
                continue
                
            try:
                print(f"Following link: {link} (depth {current_depth+1}/{max_depth})")
                visited_urls.add(link)
                
                # Navigate to link
                await page.goto(link, timeout=60000, wait_until=wait_until_strategy)
                
                # Wait for content to load
                await page.wait_for_timeout(2000)
                
                # Extract from the new page and follow its links recursively
                new_items = await self._extract_and_follow_links(
                    page, link, max_depth, current_depth+1, visited_urls, 
                    same_domain_only, max_pages, **kwargs
                )
                
                media_items.extend(new_items)
                
                if len(visited_urls) >= max_pages:
                    break
                    
            except Exception as e:
                print(f"Error following link {link}: {e}")
        
        return media_items
    async def _extract_artwork_page_async(self, page):
        """Extract image from an individual artwork page (async version)."""
        media_items = []
        html_content = await self._get_page_content_async(page)
        
        try:
            # 1) Attempt JSON data approach
            json_data = self._extract_json_data(html_content)
            if json_data:
                json_items = self._process_json_data(json_data)
                if json_items:
                    print(f"Extracted {len(json_items)} items from JSON data on artwork page")
                    return json_items
            else:
                print("No JSON data found, using direct DOM extraction")

            # 2) Fallback DOM extraction with Playwright
            main_img = page.locator('img[data-test="artworkImage"], [class*="Artwork"] img').first
            try:
                await main_img.wait_for(timeout=2000)
                
                image_url = await main_img.get_attribute('src')
                srcset = await main_img.get_attribute('srcset')
                alt_text = await main_img.get_attribute('alt') or "Artwork image"
                
                if srcset:
                    best_url = self._get_best_image_from_srcset(srcset)
                    if best_url:
                        image_url = best_url
                        
                if image_url:
                    image_url = self._optimize_cloudfront_url(image_url)
                    title = await self._extract_artwork_title_async(page) or alt_text
                    artist = await self._extract_artwork_artist_async(page) or "Unknown Artist"
                    
                    media_items.append({
                        'url': image_url,
                        'alt': alt_text,
                        'title': title,
                        'source_url': self.url,
                        'credits': f"Artwork by {artist}",
                        'type': 'image',
                        '_headers': {'Referer': self.url}
                    })
            except Exception as e:
                print(f"Main image not found: {e}")
                
        except Exception as e:
            print(f"Error extracting artwork page: {e}")
            traceback.print_exc()

        return media_items

    async def _extract_grid_page_highres_async(self, page):
        """Extract high-res images by visiting each artwork page and clicking through."""
        media_items = []
        grid_items = page.locator(
            '[data-test="artworkGridItem"], [class*="ArtworkGrid"] a, '
            '[class*="ArtworkBrick"] a, [class*="Artwork"] a, '
            'a[href*="/artwork/"], .GridItem a[href*="/artwork/"], .MasonryGrid a[href*="/artwork/"]'
        )
        count = await grid_items.count()
        print(f"Found {count} artwork links on grid for high-res extraction")

        for i in range(count):
            try:
                item = grid_items.nth(i)
                artwork_href = await item.get_attribute('href')
                if not artwork_href or '/artwork/' not in artwork_href:
                    continue
                artwork_url = urljoin(self.url, artwork_href)
                print(f"Opening artwork page: {artwork_url}")

                # Open in the same page (or use context.new_page() for parallelism)
                await page.goto(artwork_url, timeout=60000)
                await page.wait_for_timeout(2000)

                # Click image multiple times to reveal high-res
                highres_url = await self._extract_highres_from_artwork_page(page, artwork_url, click_count=3)
                if highres_url:
                    media_items.append({
                        'url': self._optimize_cloudfront_url(highres_url),
                        'alt': 'High-res artwork',
                        'title': 'High-res artwork',
                        'source_url': artwork_url,
                        'credits': 'Artsy (high-res)',
                        'type': 'image',
                        '_headers': {'Referer': artwork_url}
                    })

                # Go back to the grid page
                await page.go_back(timeout=60000)
                await page.wait_for_timeout(2000)
            except Exception as e:
                print(f"Error processing artwork {i+1}: {e}")
                continue

        print(f"Extracted {len(media_items)} high-res images from grid")
        return media_items

    async def _extract_grid_page_async(self, page):
        """Extract images from grid-based pages (artist, collection, etc.) (async version)."""
        media_items = []

        try:
            # 1) Attempt to accept cookie banner
            consent_button = page.locator('button:has-text("Agree"), button:has-text("Accept")').first
            try:
                await consent_button.wait_for(timeout=5000)
                await consent_button.click()
                await page.wait_for_timeout(1000)
            except:
                pass

            # 2) Locate grid items
            grid_items = page.locator(
                '[data-test="artworkGridItem"], [class*="ArtworkGrid"] a, '
                '[class*="ArtworkBrick"] a, [class*="Artwork"] a, '
                'a[href*="/artwork/"], .GridItem a[href*="/artwork/"], .MasonryGrid a[href*="/artwork/"]'
            )
            count = await grid_items.count()
            print(f"Found {count} potential grid items on Artsy")

            # Use a 10-second timeout for each item
            for i in range(count):
                try:
                    item = grid_items.nth(i)
                    artwork_href = await item.get_attribute('href')
                    if not artwork_href or '/artwork/' not in artwork_href:
                        continue

                    await item.hover(timeout=10000)  # reveal lazy-thumbnails if needed
                    img = item.locator('img').first
                    await img.wait_for(timeout=10000)

                    # Evaluate possible image attributes
                    image_url = await img.evaluate("""
                        (el) => el.getAttribute('src') 
                            || el.getAttribute('data-src') 
                            || el.getAttribute('data-lazyload-src') 
                            || ''
                    """)

                    # Fallback to srcset
                    if not image_url:
                        srcset = await img.get_attribute('srcset')
                        if srcset:
                            best_url = self._get_best_image_from_srcset(srcset)
                            if best_url:
                                image_url = best_url

                    # Skip empty data
                    if not image_url or image_url.startswith('data:'):
                        continue

                    alt_text = await img.get_attribute('alt') or "Artwork image"
                    image_url = self._optimize_cloudfront_url(image_url)

                    # Attempt to get a title
                    title_elem = item.locator('[class*="Title"], [class*="title"]').first
                    title_text = alt_text
                    try:
                        await title_elem.wait_for(timeout=2000)
                        full_title = await title_elem.inner_text()
                        title_text = full_title.strip() if full_title else alt_text
                    except:
                        pass

                    # Attempt to get artist info
                    artist_elem = item.locator('[class*="Artist"], [class*="artist"]').first
                    artist_text = "Unknown Artist"
                    try:
                        await artist_elem.wait_for(timeout=2000)
                        full_artist = await artist_elem.inner_text()
                        artist_text = full_artist.strip() if full_artist else artist_text
                    except:
                        pass

                    absolute_href = urljoin(self.url, artwork_href)
                    media_items.append({
                        'url': image_url,
                        'alt': alt_text,
                        'title': title_text,
                        'source_url': absolute_href,
                        'credits': f"Artwork by {artist_text}",
                        'type': 'image',
                        '_headers': {'Referer': absolute_href}
                    })

                except Exception as img_err:
                    if self.debug_mode:
                        print(f"Error processing Artsy grid item {i+1}: {img_err}")
                    continue

        except Exception as e:
            print(f"Error extracting grid page on Artsy: {e}")
            traceback.print_exc()

        return media_items

    async def _extract_canvas_images_async(self, page):
        """Extract high resolution images that are rendered using canvas elements."""
        media_items = []
        
        try:
            print("Attempting to extract canvas-based high-resolution images...")
            
            # 1. Find all grid items with artwork links
            grid_items = page.locator('a[href*="/artwork/"]')
            count = await grid_items.count()
            print(f"Found {count} potential artwork links")
            
            # Process a reasonable number of items
            max_items = min(count, 20)  # Limit to 20 to avoid excessive processing
            
            for i in range(max_items):
                try:
                    # Get the link URL before clicking (we'll need it later)
                    item = grid_items.nth(i)
                    href = await item.get_attribute('href')
                    if not href or '/artwork/' not in href:
                        continue
                    
                    absolute_href = urljoin(self.url, href)
                    print(f"Processing artwork {i+1}/{max_items}: {absolute_href}")
                    
                    # Extract image ID from the URL if possible
                    artwork_id = href.split('/artwork/')[1] if '/artwork/' in href else None
                    
                    # Attempt to extract from source data without clicking
                    try:
                        # Extract the high-res image URL from data attributes if available
                        artwork_data = await page.evaluate(f"""() => {{
                            try {{
                                // Look for data in the page that contains image URLs
                                window.__RELAY_STORE__ = window.__RELAY_STORE__ || {{}};
                                const keys = Object.keys(window.__RELAY_STORE__);
                                
                                // First look for the specific artwork by ID
                                const artworkId = "{artwork_id}";
                                if (artworkId) {{
                                    const matchingKeys = keys.filter(k => k.includes(artworkId));
                                    
                                    for (const key of matchingKeys) {{
                                        const data = window.__RELAY_STORE__[key];
                                        if (data && data.image) {{
                                            return {{
                                                imageUrl: data.image.url,
                                                imageVersions: data.image.imageVersions,
                                                title: data.title,
                                                artist: data.artist ? data.artist.name : "Unknown Artist"
                                            }};
                                        }}
                                    }}
                                }}
                                
                                // If not found by ID, try to find any artwork data
                                for (const key of keys) {{
                                    const data = window.__RELAY_STORE__[key];
                                    
                                    if (data && key.includes('Artwork') && data.image) {{
                                        const imgUrl = data.image.url || 
                                                    (data.image.imageVersions && data.image.imageVersions.larger) ||
                                                    null;
                                        
                                        if (imgUrl) {{
                                            return {{
                                                imageUrl: imgUrl,
                                                imageVersions: data.image.imageVersions,
                                                title: data.title,
                                                artist: data.artist ? data.artist.name : "Unknown Artist"
                                            }};
                                        }}
                                    }}
                                }}
                                
                                return null;
                            }} catch(e) {{
                                console.error("Error looking for artwork data:", e);
                                return null;
                            }}
                        }}""")
                    except Exception as e:
                        print(f"Error extracting artwork data: {e}")
                        artwork_data = None  # Set to None so the next check fails gracefully

                    if artwork_data and artwork_data.get('imageUrl'):
                        print(f"Found image data without clicking: {artwork_data.get('imageUrl')}")
                        url = artwork_data.get('imageUrl')
                        
                        # Make sure we get the highest resolution version
                        if '/larger.jpg' not in url and '/normalized.' not in url:
                            url = url.replace('.jpg', '/larger.jpg')
                        
                        # Some images are served through the resize proxy - extract the source URL
                        if 'resize_to=fit&src=' in url:
                            src_part = url.split('src=')[1].split('&')[0]
                            import urllib.parse
                            original_url = urllib.parse.unquote(src_part)
                            if original_url:
                                url = original_url
                        
                        media_items.append({
                            'url': url,
                            'alt': artwork_data.get('title', 'Artwork'),
                            'title': artwork_data.get('title', 'Artwork'),
                            'source_url': absolute_href,
                            'credits': f"Artwork by {artwork_data.get('artist', 'Unknown Artist')}",
                            'type': 'image',
                            '_headers': {'Referer': absolute_href}
                        })
                        
                        # Skip clicking if we found the data
                        continue
                    
                    # If we couldn't extract data passively, try clicking to open artwork detail
                    try:
                        # First make sure the element is visible and scrolled into view
                        await item.scroll_into_view_if_needed()
                        await page.wait_for_timeout(500)  # Brief pause to let positioning stabilize
                        
                        # Check if element is clickable
                        is_visible = await item.is_visible()
                        if not is_visible:
                            print(f"Artwork link not visible, skipping click interaction")
                            continue
                            
                        # Try to click with a timeout and retry logic
                        try:
                            await item.click(timeout=5000)
                            await page.wait_for_timeout(3000)  # Wait for modal to open
                        except Exception as click_err:
                            print(f"Standard click failed: {click_err}. Trying alternate click methods...")
                            
                            # Fallback 1: Try JavaScript click
                            try:
                                await page.evaluate("(el) => el.click()", item)
                                await page.wait_for_timeout(3000)
                                print("Used JavaScript click as fallback")
                            except Exception as js_click_err:
                                print(f"JavaScript click also failed: {js_click_err}")
                                
                                # Fallback 2: Try direct navigation instead of clicking
                                try:
                                    href = await item.get_attribute('href')
                                    if href:
                                        full_href = urljoin(self.url, href)
                                        print(f"Navigating directly to {full_href} instead of clicking")
                                        await page.goto(full_href, timeout=30000, wait_until='domcontentloaded')
                                        await page.wait_for_timeout(3000)
                                    else:
                                        print("No href attribute found for direct navigation")
                                        continue
                                except Exception as nav_err:
                                    print(f"Direct navigation failed too: {nav_err}")
                                    continue
                    
                        # After successfully opening the modal/page, process the content
                        try:
                            # If a OpenSeadragon container is visible, we have a high-res image
                            oed_container = page.locator('.openseadragon-container').first
                            is_visible = await oed_container.is_visible(timeout=2000)
                            
                            if is_visible:
                                # Try to extract the image URL using OSD API
                                try:
                                    image_url = await page.evaluate("""() => {
                                        try {
                                            // Find OpenSeadragon instance
                                            let osd_instance = null;
                                            for (const key in window) {
                                                if (window[key] && 
                                                    window[key].hasOwnProperty('viewer') && 
                                                    window[key].viewer && 
                                                    window[key].viewer.hasOwnProperty('_tileSources')) {
                                                    osd_instance = window[key].viewer;
                                                    break;
                                                }
                                            }
                                            
                                            // Get the tile source (original image)
                                            if (osd_instance && osd_instance._tileSources && osd_instance._tileSources.length) {
                                                const source = osd_instance._tileSources[0];
                                                
                                                // Different tile source formats
                                                if (typeof source === 'string') {
                                                    return source;  // Direct URL
                                                } else if (source.url) {
                                                    return source.url;  // Object with URL property
                                                } else if (source.Image && source.Image.Url) {
                                                    return source.Image.Url;  // DZI format
                                                }
                                            }
                                            
                                            // Alternative approach: check network requests
                                            const highResLinks = [];
                                            document.querySelectorAll('a[href*="cloudfront"], a[href*="artsy"], a[href*="d32dm0rphc51dk"]')
                                                .forEach(a => {
                                                    if (a.href.includes('larger.jpg')) highResLinks.push(a.href);
                                                });
                                            
                                            if (highResLinks.length) return highResLinks[0];
                                            
                                            // Look for OpenSeadragon config in the page source
                                            const scripts = document.querySelectorAll('script');
                                            for (const script of scripts) {
                                                if (script.textContent.includes('OpenSeadragon') && 
                                                    script.textContent.includes('tileSources')) {
                                                    const match = script.textContent.match(/tileSources[^"]*"([^"]+)"/);
                                                    if (match && match[1]) return match[1];
                                                }
                                            }
                                            
                                            // As a last resort, try to find data-src attributes
                                            const dataSrcs = [];
                                            document.querySelectorAll('[data-src]').forEach(el => {
                                                if (el.dataset.src.includes('cloudfront') || 
                                                    el.dataset.src.includes('larger.jpg')) {
                                                    dataSrcs.push(el.dataset.src);
                                                }
                                            });
                                            
                                            if (dataSrcs.length) return dataSrcs[0];
                                            
                                            return null;
                                        } catch(e) {
                                            console.error("Error extracting image from OpenSeadragon:", e);
                                            return null;
                                        }
                                    }""")
                                except Exception as js_error:
                                    print(f"Error evaluating JavaScript for OpenSeadragon: {js_error}")
                                    image_url = None
                                
                                # Check if image URL was found
                                if image_url:
                                    print(f"Found OpenSeadragon image URL: {image_url}")
                                    
                                    # Try to get artwork title and artist
                                    artwork_info = {
                                        'title': 'Artwork', 
                                        'artist': 'Unknown Artist'
                                    }
                                    
                                    try:
                                        title_elem = page.locator('[data-test="artworkTitle"], h1').first
                                        artist_elem = page.locator('[data-test="artworkArtist"], [class*="ArtistName"]').first
                                        
                                        artwork_info['title'] = await title_elem.text_content() or 'Artwork'
                                        artwork_info['artist'] = await artist_elem.text_content() or 'Unknown Artist'
                                    except Exception as e:
                                        print(f"Error getting artwork info: {e}")
                                    
                                    media_items.append({
                                        'url': image_url,
                                        'alt': artwork_info['title'],
                                        'title': artwork_info['title'],
                                        'source_url': absolute_href,
                                        'credits': f"Artwork by {artwork_info['artist']}",
                                        'type': 'image',
                                        '_headers': {'Referer': absolute_href}
                                    })
                                else:
                                    print("No OpenSeadragon image URL found")
                                    # If we couldn't get the image URL, try to take a screenshot of the canvas
                                    if self.debug_mode:
                                        try:
                                            # Take a screenshot of the canvas for debugging
                                            canvas = page.locator('.openseadragon-canvas canvas').first
                                            if await canvas.is_visible():
                                                title = await page.title()
                                                screenshot_path = f"artsy_canvas_{i}.png"
                                                await canvas.screenshot(path=screenshot_path)
                                                print(f"Took screenshot of canvas: {screenshot_path}")
                                        except Exception as ss_error:
                                            print(f"Error taking canvas screenshot: {ss_error}")
                            else:
                                print("OpenSeadragon container not visible")
                        
                        except Exception as osd_error:
                            print(f"Error checking for OpenSeadragon container: {osd_error}")

                        # Try to find high-res image in standard img elements
                        try:
                            artwork_images = await page.locator('img[srcset], img[src*="larger.jpg"], img[src*="normalized"]').all()
                            for img in artwork_images:
                                try:
                                    src = await img.get_attribute('src')
                                    srcset = await img.get_attribute('srcset')
                                    
                                    img_url = src
                                    if srcset:
                                        best_url = self._get_best_image_from_srcset(srcset)
                                        if best_url:
                                            img_url = best_url
                                            
                                    if img_url and ('larger.jpg' in img_url or 'normalized' in img_url):
                                        title_elem = page.locator('[data-test="artworkTitle"], h1').first
                                        title = await title_elem.inner_text() if await title_elem.count() > 0 else 'Artwork'
                                        
                                        artist_elem = page.locator('[data-test="artworkArtist"], [class*="ArtistName"]').first
                                        artist = await artist_elem.inner_text() if await artist_elem.count() > 0 else 'Unknown Artist'
                                        
                                        media_items.append({
                                            'url': self._optimize_cloudfront_url(img_url),
                                            'alt': title,
                                            'title': title,
                                            'source_url': absolute_href,
                                            'credits': f"Artwork by {artist}",
                                            'type': 'image',
                                            '_headers': {'Referer': absolute_href}
                                        })
                                except Exception as img_err:
                                    print(f"Error processing artwork image: {img_err}")
                        except Exception as img_list_err:
                            print(f"Error getting artwork images: {img_list_err}")
                    
                    except Exception as click_error:
                        print(f"Error during click operation: {click_error}")
                    
                    finally:
                        # Close the modal by pressing ESC
                        try:
                            await page.keyboard.press('Escape')
                            await page.wait_for_timeout(1000)  # Wait for modal to close
                        except Exception as esc_error:
                            print(f"Error closing modal: {esc_error}")
                
                except Exception as e:
                    print(f"Error processing artwork {i+1}: {e}")
                    # Try to close any open modal
                    try:
                        await page.keyboard.press('Escape')
                        await page.wait_for_timeout(1000)
                    except:
                        pass
        
        except Exception as e:
            print(f"Error in canvas extraction setup: {e}")
            traceback.print_exc()
        
        # Clean up results - filter to high-res only
        filtered_items = []
        seen_urls = set()
        
        for item in media_items:
            url = item.get('url')
            if not url or url in seen_urls:
                continue
                
            # Focus on high resolution images
            if ('larger.jpg' in url or 
                'normalized' in url or 
                'd32dm0rphc51dk.cloudfront.net' in url or
                url.endswith('.tif') or
                '/large.' in url):
                
                # Make sure it's a direct image URL
                if '?' in url and 'src=' in url:
                    # Extract the source image from the resize parameters
                    src_part = url.split('src=')[1].split('&')[0] if 'src=' in url else ""
                    if src_part:
                        import urllib.parse
                        direct_url = urllib.parse.unquote(src_part)
                        item['url'] = direct_url
                
                seen_urls.add(url)
                filtered_items.append(item)
        
        print(f"Canvas extraction found {len(filtered_items)} high-resolution images after filtering")
        return filtered_items

    def _sanitize_directory_name(self, name):
        """Convert a name into a safe directory name"""
        # Replace special characters with underscores
        sanitized = re.sub(r'[\\/:*?"<>|]', '_', name)
        # Replace spaces with underscores
        sanitized = sanitized.replace(' ', '_')
        # Replace multiple underscores with a single one
        sanitized = re.sub(r'_+', '_', sanitized)
        # Limit length to avoid issues with too long paths
        if len(sanitized) > 50:
            sanitized = sanitized[:50]
        return sanitized.lower()
    
    def _scroll_page(self, page):
        """Scroll the page to load lazy-loaded images"""
        try:
            # Simple auto-scroll to load lazy content
            page.evaluate("""
                (() => {
                    let totalHeight = 0;
                    let distance = 500;
                    let scrollDelay = 500;
                    let timer = setInterval(() => {
                        let scrollHeight = document.body.scrollHeight;
                        window.scrollBy(0, distance);
                        totalHeight += distance;
                        
                        if(totalHeight >= scrollHeight || totalHeight > 15000){
                            clearInterval(timer);
                        }
                    }, scrollDelay);
                })()
            """)
            time.sleep(5)  # Give some time for everything to load
        except Exception as e:
            print(f"Error during scrolling: {e}")

    def _get_playwright_page(self, page):
        """Try to get a playwright page from various page objects"""
        if page and hasattr(page, 'goto'):
            return page  # Already a playwright page
        
        # Handled when passed a scrapling fetcher or a fetcher with playwright page
        if page and hasattr(page, 'page'):
            return page.page
        
        # When passed a ScraplingFetcher
        if page and hasattr(page, 'fetcher') and hasattr(page.fetcher, 'page'):
            return page.fetcher.page
            
        # When using a PlaywrightFetcher directly
        if page and isinstance(page, PlayWrightFetcher) and hasattr(page, 'page'):
            return page.page
            
        return None
    async def _get_page_content_async(self, page):
        """Extract HTML content from the page (async version)."""
        try:
            await page.wait_for_timeout(1500)  # small wait
            return await page.content()
        except:
            return ""

    async def _extract_artwork_title_async(self, page):
        """Try to find an artwork title in the page for a single artwork view (async version)."""
        title_elem = page.locator('[data-test="artworkTitle"], [class*="ArtworkMetadata"] h1').first
        try:
            await title_elem.wait_for(timeout=1000)
            text = await title_elem.inner_text()
            return text.strip()
        except:
            return None

    async def _extract_artwork_artist_async(self, page):
        """Try to find the artist name in the page for a single artwork view (async version)."""
        artist_elem = page.locator('[data-test="artworkArtist"], [class*="ArtistName"]').first
        try:
            await artist_elem.wait_for(timeout=1000)
            text = await artist_elem.inner_text()
            return text.strip()
        except:
            return None

    async def _extract_general_images_async(self, page):
        """A simpler fallback that queries all <img> elements from the DOM (async version)."""
        items = []
        try:
            img_elements = page.locator('img')
            count = await img_elements.count()
            
            for i in range(count):
                img = img_elements.nth(i)
                src = await img.get_attribute('src')
                
                if src and src.startswith('http'):
                    alt = await img.get_attribute('alt') or 'Artsy image'
                    
                    items.append({
                        'url': self._optimize_cloudfront_url(src),
                        'alt': alt,
                        'title': 'Artsy Image',
                        'source_url': self.url,
                        'credits': 'Artsy (general fallback)',
                        'type': 'image',
                        '_headers': {'Referer': self.url}
                    })
        except Exception as e:
            print(f"Error in _extract_general_images_async: {e}")
        return items

    async def _extract_media_from_html_async(self, page):
        """Last-resort raw HTML parse if we can't use the DOM or didn't find anything (async version)."""
        media_items = []
        html = await self._get_page_content_async(page)
        
        # Simple regex for <img src=...> as a fallback
        img_urls = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', html)
        for url in img_urls:
            if url.startswith('http'):
                media_items.append({
                    'url': self._optimize_cloudfront_url(url),
                    'alt': 'Artsy fallback image',
                    'title': 'Artsy fallback image',
                    'source_url': self.url,
                    'credits': 'Artsy (raw HTML fallback)',
                    'type': 'image',
                    '_headers': {'Referer': self.url}
                })
        return media_items

    def pre_process(self, page):
        """Prepare the page for extraction (and try to init the Artsy API)"""
        print(f"[ArtsyHandler] Pre-processing {self.url} (page type: {self.page_type})")

        # Attempt to init the API if credentials exist
        if self.use_api:
            self._init_artsy_api()

        # Proceed with normal DOM pre-processing (scroll, etc.) as fallback
        pw_page = self._get_playwright_page(page)
        if pw_page:
            print("Found Playwright page for pre-processing")
            try:
                # Wait for key content to load
                if self.page_type == "artwork":
                    print("Waiting for main artwork image to load (DOM approach)")
                    pw_page.wait_for_selector('img[data-test="artworkImage"], img[srcset]', timeout=10000)
                else:
                    print("Waiting for images to load on grid/other pages")
                    pw_page.wait_for_selector('img[srcset], img[src*="cloudfront"]', timeout=10000)

                # Scroll down to load more content if it's a grid page
                if self.page_type in ["artist", "collection", "show", "auction", "general"]:
                    print("Scrolling page to load more content (DOM approach)")
                    self._scroll_page(pw_page)
            except Exception as e:
                print(f"Error during Artsy pre-processing: {e}")
                traceback.print_exc()
        else:
            print("No Playwright page available for DOM pre-processing")

        return page

    def _init_artsy_api(self):
        """
        Attempt to retrieve an Artsy XAPP token from credentials.
        Expects self.scraper.auth_config and site-specific 'client_id'/'client_secret'.
        """
        if not self.scraper or not hasattr(self.scraper, 'auth_config'):
            print("[ArtsyHandler] No scraper or auth_config, API usage disabled.")
            self.use_api = False
            return

        site_auth = {}
        if hasattr(self.scraper, 'get_site_auth_config'):
            site_auth = self.scraper.get_site_auth_config(self.scraper.auth_config, self.url)
        else:
            # fallback if get_site_auth_config not defined
            site_auth = self.scraper.auth_config.get('artsy.net', {})

        client_id = site_auth.get('client_id')
        client_secret = site_auth.get('client_secret')
        if not client_id or not client_secret:
            print("[ArtsyHandler] Artsy API credentials missing (client_id/client_secret).")
            self.use_api = False
            return

        if not REQUESTS_AVAILABLE:
            print("[ArtsyHandler] 'requests' is not available. Cannot call the API.")
            self.use_api = False
            return

        try:
            # get XAPP token
            print("[ArtsyHandler] Fetching XAPP token from Artsy API...")
            r = requests.post(
                "https://api.artsy.net/api/tokens/xapp_token",
                data={"client_id": client_id, "client_secret": client_secret},
                timeout=15
            )
            data = r.json()
            token = data.get('token')
            if token:
                self.artsy_token = token
                print("[ArtsyHandler] Successfully retrieved Artsy XAPP token.")
            else:
                print(f"[ArtsyHandler] No 'token' in response: {data}")
                self.use_api = False
        except Exception as e:
            print(f"[ArtsyHandler] Error fetching XAPP token: {e}")
            traceback.print_exc()
            self.use_api = False

    def _extract_via_artsy_api(self):
        """
        Perform an API-based extraction:
          - Figure out what we are scraping (artist page vs. single artwork, etc.)
          - Query the relevant Artsy API endpoints
          - Return a list of media items in the standard format
        """
        media_items = []

        if not self.artsy_token:
            print("[ArtsyHandler] Missing artsy_token, cannot use the API.")
            return media_items

        # For demonstration, we’ll do some simple logic:
        # if self.page_type == "artist", we fetch a few artworks for that artist
        # if self.page_type == "artwork", we fetch that single artwork
        # etc. In a real project, you'd parse the URL to get the actual slug/ID.

        # 1) parse an 'artist slug' or 'artwork slug' from the URL
        slug = self._extract_slug_from_url(self.url)
        if not slug:
            print("[ArtsyHandler] Could not parse a slug from the URL, skipping API approach.")
            return media_items

        headers = {"X-Xapp-Token": self.artsy_token, "Accept": "application/vnd.artsy-v2+json"}

        if self.page_type == "artist":
            # Example: GET https://api.artsy.net/api/artworks?artist_id=<some-artist-id>
            # But we first have to find the artist_id from the slug
            artist_id = self._find_artist_id_by_slug(slug, headers)
            if not artist_id:
                print(f"[ArtsyHandler] Could not find artist ID for slug '{slug}'")
                return media_items

            print(f"[ArtsyHandler] Found artist ID: {artist_id}, now fetching artworks...")
            url_artworks = f"https://api.artsy.net/api/artworks?artist_id={artist_id}&size=20"
            resp = requests.get(url_artworks, headers=headers, timeout=15)
            data = resp.json()
            if "_embedded" in data and "artworks" in data["_embedded"]:
                for aw in data["_embedded"]["artworks"]:
                    item = self._convert_artwork_to_media_item(aw)
                    if item:
                        media_items.append(item)

        elif self.page_type == "artwork":
            # Example: GET https://api.artsy.net/api/artworks/<id-or-slug>
            # Usually, the 'id' is different from the slug, but we can try the slug first
            print(f"[ArtsyHandler] Getting single artwork by slug: {slug}")
            single_url = f"https://api.artsy.net/api/artworks/{slug}"
            resp = requests.get(single_url, headers=headers, timeout=15)
            aw = resp.json()
            if "id" in aw and "title" in aw:
                item = self._convert_artwork_to_media_item(aw)
                if item:
                    media_items.append(item)
            else:
                print(f"[ArtsyHandler] Did not get valid artwork data for slug '{slug}'")

        else:
            # For other page types, you’d implement additional logic or skip
            print("[ArtsyHandler] No specialized API approach for this page type. Returning empty.")
            # You could add code for 'collection', 'show', etc.

        print(f"[ArtsyHandler] API extraction found {len(media_items)} items.")
        return media_items

    def _extract_slug_from_url(self, url):
        """
        For an Artsy URL like https://www.artsy.net/artist/banksy, 
        returns 'banksy'. For https://www.artsy.net/artwork/banksy-love-rat, returns 'banksy-love-rat'.
        """
        # This is a simplistic approach. A robust one might parse the path segments carefully.
        parts = url.lower().split('/')
        # find where "artist" or "artwork" occurs and take the next part as slug
        # for example: /artist/banksy => parts might be [..., 'artist', 'banksy']
        # for /artwork/banksy-love-rat => parts might be [..., 'artwork', 'banksy-love-rat']
        # We already know self.page_type from _determine_page_type
        for i, seg in enumerate(parts):
            if seg in ["artist", "artwork"]:
                if i + 1 < len(parts):
                    return parts[i+1]
        return None

    def _find_artist_id_by_slug(self, slug, headers):
        """
        Helper to get the numeric (or internal) ID for an artist from the slug
        using the endpoint: GET /api/artists/:slug
        """
        try:
            url = f"https://api.artsy.net/api/artists/{slug}"
            resp = requests.get(url, headers=headers, timeout=15)
            data = resp.json()
            # If successful, data should have an 'id' field
            if "id" in data:
                return data["id"]
        except Exception as e:
            print(f"[ArtsyHandler] _find_artist_id_by_slug error: {e}")
        return None

    def _convert_artwork_to_media_item(self, aw_json):
        """
        Convert an Artsy artwork JSON object to a standard media item
        e.g. aw_json might have: 'title', 'artist', 'image_versions', '_links'
        """
        try:
            # Some examples from the Artsy API:
            # aw_json['title'], aw_json['date'], aw_json['collecting_institution'], etc.
            # Large image URL might come from aw_json['_links']['thumbnail']['href'] (or 'image')
            links = aw_json.get('_links', {})
            img_link = links.get('thumbnail', {}).get('href') or links.get('image', {}).get('href')
            if not img_link:
                return None

            # Replace "{image_version}" in the URL with "large" or "larger" if available
            # Because the Artsy API uses templated URLs sometimes, e.g.:
            # "thumbnail": {"href": "https://d32dm0rphc51dk.cloudfront.net/abcdefgh/large.jpg"}
            # or "https://api.artsy.net/api/images/ID/{image_version}.jpg"
            if "{image_version}" in img_link:
                img_link = img_link.replace("{image_version}", "large")

            # Artwork title and artist
            title = aw_json.get('title', 'Untitled Artwork')
            artist_names = aw_json.get('artist', {}).get('name')
            if not artist_names:
                # sometimes there's "collecting_institution" or multiple artists
                artist_names = aw_json.get('multiple_artists', 'Unknown Artist')

            # Construct media dict
            return {
                'url': img_link,
                'alt': title,
                'title': title,
                'source_url': self.url,  # reference the original page
                'credits': f"Artsy - {artist_names}" if artist_names else "Artsy",
                'type': 'image',
                '_headers': {
                    'Referer': self.url
                }
            }
        except Exception as e:
            print(f"[ArtsyHandler] Error converting artwork JSON: {e}")
        return None


    def _optimize_cloudfront_url(self, url):
        """Optimize Artsy's CloudFront URLs to get the highest resolution."""
        if not url:
            return url
            
        # Handle proxied URLs that have the actual image URL in the 'src' parameter
        if '?' in url and 'src=' in url:
            src_param = url.split('src=')[1].split('&')[0] if 'src=' in url else None
            if src_param:
                import urllib.parse
                src_url = urllib.parse.unquote(src_param)
                url = src_url  # Use the actual source URL
        
        # Make sure it's a high resolution version
        if 'd32dm0rphc51dk.cloudfront.net' in url:
            if not url.endswith('/larger.jpg') and not url.endswith('/normalized.jpg'):
                url = url.replace('.jpg', '/larger.jpg')
        
        # Strip unnecessary resize parameters
        if 'quality=' in url and 'resize_to=' in url:
            base_url = url.split('?')[0]
            return base_url
            
        return url


    def _get_best_image_from_srcset(self, srcset):
        """Return the largest URL from a srcset string."""
        best_url = None
        best_width = 0
        for entry in srcset.split(','):
            entry = entry.strip()
            parts = entry.split(' ')
            if len(parts) == 2 and parts[1].endswith('w'):
                try:
                    width = int(parts[1].replace('w', ''))
                    if width > best_width:
                        best_width = width
                        best_url = parts[0]
                except:
                    pass
        return best_url


    def _extract_json_data(self, html):
        """
        Attempt to find JSON data in the HTML that might contain artwork info.
        For example, some pages embed a JSON blob with Redux/Relay data.
        """
        # This is just a placeholder example that tries to find something like
        # <script>window.__INITIAL_STATE__ = {...}</script>
        match = re.search(r'window\.__INITIAL_STATE__\s*=\s*({.*?});?\s*</script>', html, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except:
                pass
        return None

    def _process_json_data(self, json_data):
        """Custom logic to parse the JSON data structure for images."""
        # This is a placeholder that depends heavily on how Artsy structures data.
        # You’d rummage through the JSON for image URLs, artist, etc.
        # Return a list of media items in the usual format.
        items = []
        # Example: if there's something like json_data['artwork']['images']
        # you loop over them. This is purely hypothetical:
        try:
            if 'artwork' in json_data and 'images' in json_data['artwork']:
                for img in json_data['artwork']['images']:
                    url = img.get('url')
                    if url:
                        items.append({
                            'url': self._optimize_cloudfront_url(url),
                            'alt': img.get('title', 'Artwork image'),
                            'title': img.get('title', 'Untitled Artwork'),
                            'source_url': self.url,
                            'credits': 'Artsy (JSON fallback)',
                            'type': 'image',
                            '_headers': {'Referer': self.url}
                        })
        except:
            pass
        return items

    def get_content_directory(self):
        """Generate Artsy-specific directory structure"""
        # Base directory is always 'artsy'
        base_dir = "artsy"
        
        # Content directory based on page type
        content_parts = []
        
        if self.page_type == 'artist':
            content_parts.append("artist")
            # Extract artist name from URL
            parsed_url = urlparse(self.url)
            path = parsed_url.path.strip('/')
            path_parts = path.split('/')
            if len(path_parts) > 1:
                artist_name = path_parts[-1]
                content_parts.append(self._sanitize_directory_name(artist_name))
        elif self.page_type == 'artwork':
            content_parts.append("artwork")
            # Extract artwork name from URL
            parsed_url = urlparse(self.url)
            path = parsed_url.path.strip('/')
            path_parts = path.split('/')
            if len(path_parts) > 1:
                artwork_name = path_parts[-1]
                content_parts.append(self._sanitize_directory_name(artwork_name))
        elif self.page_type == 'collection':
            content_parts.append("collection")
            # Extract collection name from URL
            parsed_url = urlparse(self.url)
            path = parsed_url.path.strip('/')
            path_parts = path.split('/')
            if len(path_parts) > 1:
                collection_name = path_parts[-1]
                content_parts.append(self._sanitize_directory_name(collection_name))
        else:
            # Fallback to URL path
            parsed_url = urlparse(self.url)
            path = parsed_url.path.strip('/')
            path_parts = path.split('/')
            for part in path_parts[:2]:  # Limit depth to 2
                if part:
                    content_parts.append(self._sanitize_directory_name(part))
        
        # Ensure there's at least one part
        if not content_parts:
            content_parts.append("general")
        
        # Join all parts to form the path
        content_specific_dir = os.path.join(*content_parts)
        
        return (base_dir, content_specific_dir)
