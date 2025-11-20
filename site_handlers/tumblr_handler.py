"""
Tumblr Handler

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

# tumblr_handler.py

"""
TumblrHandler for the Web Image Scraper
- API-first approach using pytumblr if credentials are present
- Fallback to DOM-based or HTML-based scraping for images
"""

from site_handlers.base_handler import BaseSiteHandler
import traceback
import time
import re
import os
from urllib.parse import urlparse, urljoin

# Try importing pytumblr
try:
    import pytumblr
    PYTUMBLR_AVAILABLE = True
except ImportError:
    pytumblr = None
    PYTUMBLR_AVAILABLE = False

# Try importing Playwright types
try:
    from playwright.async_api import Page as AsyncPage
    from playwright.sync_api import Page as SyncPage
    from scrapling.fetchers import PlayWrightFetcher
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    AsyncPage = None
    SyncPage = None
    PlayWrightFetcher = None
    PLAYWRIGHT_AVAILABLE = False

class TumblrHandler(BaseSiteHandler):
    """
    A site-specific handler for tumblr.com or <blog>.tumblr.com.
    1) Attempts API-based scraping if we have Tumblr OAuth credentials.
    2) Falls back to DOM-based extraction if the API fails or returns no items.
    """

    PRIORITY = 10  # Medium priority for Tumblr

    @classmethod
    def can_handle(cls, url):
        return "tumblr.com" in url.lower()

    def get_trusted_domains(self):
        """Return list of trusted CDN domains for Tumblr"""
        return [
            "tumblr.com",           # Main domain
            "64.media.tumblr.com",  # Primary media CDN
            "va.media.tumblr.com",  # Video assets
            "static.tumblr.com",    # Static assets
            "assets.tumblr.com",    # General assets
            "media.tumblr.com",     # Legacy media
            "78.media.tumblr.com",  # Alternative media CDN
            "66.media.tumblr.com",  # Alternative media CDN 
            "vxtwitter.com",        # Video content
            "pbs.twimg.com"         # Twitter embeds (common on Tumblr)
        ]

    def __init__(self, url, scraper=None):
        super().__init__(url, scraper)
        self.debug_mode = True
        self.tumblr_client = None
        self.blog_name = None  # e.g. "staff.tumblr.com"
        self._parse_blog_name()
      
        # Set site-specific defaults from config or fallback values
        self.timeout_ms = getattr(self, 'timeout', 5000)
        self.scroll_delay_ms = getattr(self, 'scroll_delay_ms', 2000)
        self.max_scroll_count = getattr(self, 'max_scroll_count', 10)
        self.posts_per_page = getattr(self, 'posts_per_page', 20)

        # Load authentication credentials  
        self._load_api_credentials()

        print(f"[TumblrHandler] Initialized for URL: {url}")
        print(f"  Detected blog name: {self.blog_name}")
        if hasattr(self, 'auth_credentials') and self.auth_credentials:
            auth_type = self.auth_credentials.get('auth_type', 'unknown')
            print(f"  🔑 Authentication loaded: {auth_type}")
        else:
            print(f"  ⚠️ No authentication configured")

    def prefers_api(self) -> bool:
        """Returns True if we have Tumblr API credentials"""
        return (
            PYTUMBLR_AVAILABLE and 
            hasattr(self, 'consumer_key') and 
            hasattr(self, 'consumer_secret') and
            self.consumer_key and self.consumer_secret
        )

    async def extract_api_data_async(self, **kwargs) -> list:
        """Async API extraction method"""
        # Since pytumblr is not async, we'll run it in a thread pool executor
        import asyncio
        loop = asyncio.get_event_loop()
        
        return await loop.run_in_executor(None, self._extract_via_tumblr_api, **kwargs)

    async def extract_with_direct_playwright_async(self, page: AsyncPage, **kwargs) -> list:
        print("[TumblrHandler] Using async Playwright extraction")
        
        # Run interaction sequence (from UI, kwargs, or default)
        interaction_sequence = kwargs.get("interaction_sequence") or getattr(self, "interaction_sequence", None)
        if not interaction_sequence:
            interaction_sequence = self.get_default_interaction_sequence()
        await self._run_interaction_sequence(page, interaction_sequence)
        
        # Try API first if available
        if self.prefers_api():
            try:
                items = await self.extract_api_data_async(**kwargs)
                if items:
                    print(f"[TumblrHandler] Got {len(items)} items via API.")
                    return items
                else:
                    print("[TumblrHandler] API returned no items; using DOM fallback.")
            except Exception as e:
                print(f"[TumblrHandler] Error in API extraction: {e}")
                traceback.print_exc()
                print("[TumblrHandler] Fallback to DOM-based scraping.")

        # Fallback to DOM extraction
        return await self._dom_extract_async(page, **kwargs)



    def _init_tumblr_api(self):
        """Initialize pytumblr.Client if credentials are present in auth_config."""
        # Credentials should already be loaded by _load_api_credentials
        consumer_key = getattr(self, 'consumer_key', None)
        consumer_secret = getattr(self, 'consumer_secret', None)
        oauth_token = getattr(self, 'oauth_token', None)
        oauth_secret = getattr(self, 'oauth_secret', None)

        if not (consumer_key and consumer_secret):
            print("[TumblrHandler] Missing consumer_key or consumer_secret")
            return None

        if not PYTUMBLR_AVAILABLE:
            print("[TumblrHandler] pytumblr not installed")
            return None

        try:
            client = pytumblr.TumblrRestClient(
                consumer_key,
                consumer_secret,
                oauth_token,
                oauth_secret
            )
            print("[TumblrHandler] Successfully initialized pytumblr client.")
            return client
        except Exception as e:
            print(f"[TumblrHandler] Error initializing Tumblr API: {e}")
            traceback.print_exc()
            return None

    def _extract_via_tumblr_api(self, **kwargs):
        """
        Use the Tumblr API to fetch recent photo posts from the blog.
        """
        items = []
        
        # Initialize client if not already done
        if not self.tumblr_client:
            self.tumblr_client = self._init_tumblr_api()
            
        if not self.tumblr_client or not self.blog_name:
            return items

        try:
            # Get parameters from kwargs with defaults
            limit = kwargs.get('posts_per_page', self.posts_per_page)
            max_pages = kwargs.get('max_api_pages', 1)
            offset = 0
            
            for page in range(max_pages):
                # Fetch posts with pagination
                response = self.tumblr_client.posts(
                    self.blog_name, 
                    limit=limit, 
                    offset=offset,
                    filter="raw"
                )
                
                posts = response.get('posts', [])
                if not posts:
                    break  # No more posts
                
                for p in posts:
                    # Only interested in photo or text posts that contain photos
                    # Tumblr photo posts often have a "photos" field with multiple images
                    if 'photos' in p:
                        post_title = p.get('title') or p.get('slug') or f"Tumblr post {p.get('id')}"
                        post_url = p.get('post_url')
                        blog_name = p.get('blog_name') or self.blog_name

                        for photo_obj in p['photos']:
                            original = photo_obj.get('original_size')
                            if original:
                                image_url = original.get('url')
                                alt_text = photo_obj.get('caption') or post_title
                                if image_url:
                                    items.append({
                                        'url': image_url,
                                        'alt': alt_text,
                                        'title': post_title,
                                        'source_url': post_url,
                                        'credits': f"Tumblr blog: {blog_name}",
                                        'type': 'image',
                                        '_headers': {'Referer': post_url or self.url}
                                    })

                    # Some text posts also have an embedded "photos" array or inline <img>.
                    # If you want to parse inline <img>, you'd look at p.get('body') HTML, etc.
                    # For now we skip these for simplicity

                offset += limit
                
        except Exception as e:
            print(f"[TumblrHandler] API error fetching posts: {e}")
            traceback.print_exc()

        return items

    async def _dom_extract_async(self, page: AsyncPage, **kwargs) -> list:
        """
        Fallback approach: 
        1) if the page is an infinite scroll, we attempt to scroll.
        2) Then we parse <img> from DOM or raw HTML to gather media.
        """
        items = []
        
        if page:
            # Attempt infinite scroll 
            await self._scroll_until_no_more_async(page, max_scrolls=self.max_scroll_count)
            # Then gather images
            items.extend(await self._extract_images_from_dom_async(page))
        else:
            # If no Playwright, fallback to basic HTML approach
            html_items = self._extract_images_from_html(page)
            items.extend(html_items)

        return items

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
            except Exception as e:
                print(f"[TumblrHandler] Interaction step failed: {step} - {e}")

    def get_default_interaction_sequence(self):
        return [
            # Accept cookies if present
            {"type": "wait_for_selector", "selector": "button:has-text('Accept all')", "timeout": 4000},
            {"type": "click", "selector": "button:has-text('Accept all')"},
            # Dismiss login/signup popup if present
            {"type": "wait_for_selector", "selector": "button[aria-label='Close']", "timeout": 3000},
            {"type": "click", "selector": "button[aria-label='Close']"}
        ]


    async def _scroll_until_no_more_async(self, page: AsyncPage, max_scrolls=10):
        """Simple loop-based scrolling until page stops growing or we hit max_scrolls."""
        last_height = 0
        for i in range(max_scrolls):
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(self.scroll_delay_ms)
            new_height = await page.evaluate("document.body.scrollHeight")
            if new_height == last_height:
                print("No more content loaded, stopping scroll.")
                break
            last_height = new_height

    def parse_srcset(self, srcset: str) -> dict:
        """Parse srcset attribute to extract the LARGEST image URL.
        
        Example srcset:
        "image_100.jpg 100w, image_250.jpg 250w, image_500.jpg 500w"
        Returns the highest resolution image as a single dict.
        """
        if not srcset or not srcset.strip():
            return None
        
        best_image = None
        max_width = 0
        
        try:
            # Split by comma and parse each entry
            entries = [entry.strip() for entry in srcset.split(',')]
            
            for entry in entries:
                if not entry:
                    continue
                
                parts = entry.split()
                if len(parts) >= 2:
                    url = parts[0]
                    descriptor = parts[1]
                    
                    # Parse width descriptor (e.g., "640w")
                    width = None
                    height = None
                    
                    if descriptor.endswith('w'):
                        try:
                            width = int(descriptor[:-1])
                        except ValueError:
                            continue
                    elif descriptor.endswith('h'):
                        try:
                            height = int(descriptor[:-1])
                            # For height descriptors, estimate width (assume 3:4 ratio)
                            width = int(height * 0.75)
                        except ValueError:
                            continue
                    elif descriptor.endswith('x'):
                        try:
                            # Pixel density descriptor like "2x"
                            density = float(descriptor[:-1])
                            # Estimate width based on density
                            width = int(500 * density)
                        except ValueError:
                            continue
                    
                    # Update best image if this one is larger
                    if width and width > max_width:
                        max_width = width
                        best_image = {
                            'url': url,
                            'width': width,
                            'height': height,
                            'descriptor': descriptor
                        }
                        
                elif len(parts) == 1:
                    # Just a URL without descriptor - treat as fallback
                    if not best_image:
                        best_image = {
                            'url': parts[0],
                            'width': None,
                            'height': None,
                            'descriptor': None
                        }
        
        except Exception as e:
            print(f"Error parsing srcset '{srcset}': {e}")
            return None
        
        return best_image

    async def _extract_images_from_dom_async(self, page: AsyncPage) -> list:
        """Query the DOM for images in modern Tumblr posts, including srcset handling."""
        items = []
        try:
            # Modern Tumblr image selectors - includes new classes and srcset
            selectors = [
                "img[srcset]",  # Modern Tumblr images with srcset
                "img.RoN4R",    # Specific Tumblr image class
                "img.tPU70",    # Another Tumblr image class  
                "img.xhGbM",    # Another Tumblr image class
                "article img",  # Post images
                ".post img",    # Legacy post images
                ".post-media img",  # Media in posts
                "[data-testid*='image'] img",  # React component images
                ".NPRecommendationsContainer img",  # Recommended content
                "img[data-src]"  # Lazy-loaded images
            ]
            
            print(f"🔍 Searching for Tumblr images with enhanced selectors...")
            
            # Try each selector and collect unique images
            found_urls = set()
            
            for selector in selectors:
                try:
                    img_count = await page.locator(selector).count()
                    if img_count > 0:
                        print(f"  Found {img_count} images with selector: {selector}")
                        
                        for i in range(img_count):
                            img = page.locator(selector).nth(i)
                            
                            # Get srcset first (preferred for modern Tumblr)
                            srcset = await img.get_attribute("srcset")
                            if srcset and srcset.strip():
                                # Parse srcset to get the highest quality image
                                best_image = self.parse_srcset(srcset)
                                if best_image:
                                    url = best_image['url']
                                    width = best_image.get('width')
                                    height = best_image.get('height')
                                    print(f"    📸 Found srcset image: {width}w from {url[:50]}...")
                                else:
                                    continue
                            else:
                                # Fallback to src attribute
                                url = await img.get_attribute("src")
                                if not url:
                                    # Try data-src for lazy loading
                                    url = await img.get_attribute("data-src")
                                if not url:
                                    continue
                                width = None
                                height = None
                            
                            # Skip if not a valid HTTP URL
                            if not url or not url.startswith("http"):
                                continue
                                
                            # Skip if already found
                            if url in found_urls:
                                continue
                            found_urls.add(url)
                            
                            # Skip tracking/analytics images
                            if any(tracker in url.lower() for tracker in [
                                'google-analytics', 'doubleclick', 'googletagmanager', 
                                'facebook.com/tr', 'intentiq.com', 'adsystem',
                                'scorecardresearch', 'quantserve', 'outbrain'
                            ]):
                                continue
                            
                            # Skip very small images (likely icons/tracking pixels)
                            if width and height and (width < 50 or height < 50):
                                continue
                            
                            # Get additional attributes
                            alt = await img.get_attribute("alt") or "Tumblr image"
                            
                            # Check if it's from a trusted Tumblr CDN
                            trusted_cdn = self.is_trusted_domain(url)
                            
                            item = {
                                'url': url,
                                'alt': alt,
                                'title': alt,
                                'source_url': self.url,
                                'credits': "Tumblr (Enhanced DOM extraction)",
                                'type': 'image',
                                'trusted_cdn': trusted_cdn,
                                '_headers': {'Referer': self.url}
                            }
                            
                            # Add dimensions if available
                            if width:
                                item['width'] = width
                            if height:
                                item['height'] = height
                            
                            items.append(item)
                            
                except Exception as selector_e:
                    print(f"  Error with selector {selector}: {selector_e}")
                    continue
            
            print(f"✅ Found {len(items)} unique images from Tumblr page")
            
            # If we found very few images, try a more general approach
            if len(items) < 5:
                print(f"⚠️ Found few images ({len(items)}), trying general img selector...")
                try:
                    all_imgs = await page.locator("img").count()
                    print(f"  Total img elements on page: {all_imgs}")
                    
                    # Sample a few more images to see what we're missing
                    for i in range(min(10, all_imgs)):
                        img = page.locator("img").nth(i)
                        src = await img.get_attribute("src")
                        srcset = await img.get_attribute("srcset") 
                        classes = await img.get_attribute("class")
                        
                        if src and "tumblr.com" in src and src not in found_urls:
                            print(f"    Missed image: {src[:60]}... (class: {classes})")
                            
                except Exception as e:
                    print(f"  Error in general img check: {e}")
            
        except Exception as e:
            print(f"[TumblrHandler] Error in _extract_images_from_dom_async: {e}")
            import traceback
            traceback.print_exc()
            
        return items

    def _extract_images_from_html(self, page):
        """Last-resort approach if no Playwright page: parse raw HTML <img> with regex."""
        items = []
        html_content = ""
        if hasattr(page, 'html_content'):
            html_content = page.html_content
        elif hasattr(page, 'text'):
            html_content = page.text

        if not html_content:
            return items

        # Regex find <img src="...">
        img_urls = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', html_content, flags=re.IGNORECASE)
        for url in img_urls:
            if url.startswith("http"):
                items.append({
                    'url': url,
                    'alt': "Tumblr fallback image",
                    'title': "Tumblr fallback",
                    'source_url': self.url,
                    'credits': "Tumblr (HTML fallback)",
                    'type': 'image',
                    '_headers': {'Referer': self.url}
                })
        print(f"[TumblrHandler] Fallback HTML extraction found {len(items)} images.")
        return items

    def _parse_blog_name(self):
        """Extract <blog>.tumblr.com from the URL, e.g. staff.tumblr.com."""
        # e.g. https://staff.tumblr.com/ or https://someuser.tumblr.com/tagged/cats
        # or https://www.tumblr.com/blog/view/<user> 
        parsed = urlparse(self.url)
        host = parsed.netloc.lower()
        # If it's something like "staff.tumblr.com", blog_name = "staff"
        if host.endswith("tumblr.com"):
            self.blog_name = host
        else:
            # Possibly custom domain? (some users have custom domain mapping)
            # This can complicate the API approach, but let's keep it simple
            self.blog_name = host

        # We might refine further by removing "www." if present, etc.
        # Or handle the new forms of Tumblr URLs that might not have "tumblr.com" in them.

    def get_content_directory(self):
        """Generate Tumblr-specific directory structure"""
        # Base directory is always 'tumblr'
        base_dir = "tumblr"
        
        # Content directory based on blog name
        content_parts = []
        
        if self.blog_name:
            # Remove .tumblr.com suffix if present
            blog_name = self.blog_name.replace('.tumblr.com', '')
            content_parts.append(self._sanitize_directory_name(blog_name))
        else:
            # Fallback to URL path components
            parsed_url = urlparse(self.url)
            path = parsed_url.path.strip('/')
            path_components = [self._sanitize_directory_name(p) for p in path.split('/') if p]
            if path_components:
                content_parts.extend(path_components)
        
        # Ensure there's at least one part
        if not content_parts:
            content_parts.append("general")
        
        # Join all parts to form the path
        content_specific_dir = os.path.join(*content_parts)
        
        return (base_dir, content_specific_dir)

    # Legacy methods for compatibility
    def extract_media_items(self, page):
        """Legacy sync extraction method - not used in async version"""
        if self.debug_mode:
            print("WARNING: Sync extraction method called - this should not be used")
        return []

    async def extract_with_direct_playwright(self, page, **kwargs) -> list:
        """Async Playwright extraction method for Direct Playwright strategy.
        
        This method is called by the main scraper when using Direct Playwright strategy.
        It delegates to the actual async implementation.
        """
        if self.debug_mode:
            print("[TumblrHandler] Using async Playwright extraction")
        
        # Check if page is async or sync
        if hasattr(page, 'goto'):
            # Async page - use directly
            return await self.extract_with_direct_playwright_async(page, **kwargs)
        else:
            # Should not happen in Direct Playwright mode, but handle gracefully
            print("WARNING: Received sync page in async context")
            return []