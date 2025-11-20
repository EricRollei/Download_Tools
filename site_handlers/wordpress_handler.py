"""
Wordpress Handler

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

# wordpress_handler.py

"""
WordPressHandler for the Web Image Scraper
- Attempts /wp-json/wp/v2/media or /wp-json/wp/v2/posts for images
- Falls back to DOM-based scraping if the REST API fails or is disabled
"""

from site_handlers.base_handler import BaseSiteHandler
import traceback
import re
import time
import requests
from urllib.parse import urljoin, urlparse
import os

try:
    from playwright.sync_api import Page as SyncPage
    from scrapling.fetchers import PlayWrightFetcher
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    SyncPage = None
    PlayWrightFetcher = None
    PLAYWRIGHT_AVAILABLE = False

class WordPressHandler(BaseSiteHandler):
    """
    A site-specific handler for WordPress blogs.
    Steps:
      1) Check if /wp-json/wp/v2/media is accessible. If so, fetch media items (images).
      2) If no luck, fallback to DOM-based extraction with infinite scroll or HTML parse.
    """

    @classmethod
    def can_handle(cls, url):
        # Basic check for 'wordpress.com' or if the site might be self-hosted WordPress
        # We'll do a stronger check in `_init_wp_api()`.
        return "wordpress.com" in url.lower() or "wp-json" in url.lower() or "wp-content" in url.lower()

    def __init__(self, url, scraper=None):
        super().__init__(url, scraper)
        self.debug_mode = True
        self.use_api = True  # We'll try the WP REST API if available
        self.api_base_url = None
        print(f"[WordPressHandler] Initialized for {url}")

    def pre_process(self, page):
        """Try to detect and init the WP REST API base if possible."""
        self._init_wp_api()
        return page

    def extract_media_items(self, page):
        if self.api_base_url:
            # Try the WP REST API approach
            try:
                items = self._extract_via_wp_api()
                if items:
                    print(f"[WordPressHandler] Got {len(items)} items via WP REST API.")
                    return items
                else:
                    print("[WordPressHandler] WP REST API returned no items. Fallback to DOM.")
            except Exception as e:
                print(f"[WordPressHandler] WP API extraction error: {e}")
                traceback.print_exc()
                print("[WordPressHandler] Fallback to DOM scraping.")

        # Fallback: DOM or HTML approach
        dom_items = self._dom_extract(page)
        print(f"[WordPressHandler] DOM-based extraction returned {len(dom_items)} items.")
        return dom_items

    # --------------------------------------------------
    #             WORDPRESS REST API
    # --------------------------------------------------
    def _init_wp_api(self):
        """
        Attempt to figure out if /wp-json/wp/v2/media is accessible for this domain.
        We'll store the base as self.api_base_url if it works.
        """
        parsed = urlparse(self.url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"

        # Test /wp-json endpoint
        possible_endpoints = [
            f"{base_url}/wp-json/wp/v2/media",
            f"{base_url}/wp-json/wp/v2/posts"
        ]

        for endpoint in possible_endpoints:
            try:
                resp = requests.head(endpoint, timeout=5)
                if resp.status_code in [200, 301, 302, 403, 401]:
                    # We'll assume it's a valid WP endpoint. We'll do a GET in extract_via_wp_api
                    self.api_base_url = base_url
                    print(f"[WordPressHandler] Found possible WP REST endpoint: {endpoint}")
                    return
            except Exception as e:
                if self.debug_mode:
                    print(f"Head request failed on {endpoint}: {e}")

        # If we never set self.api_base_url
        self.use_api = False
        print("[WordPressHandler] WP REST API not detected or not accessible.")

    def _extract_via_wp_api(self):
        """Try to retrieve media from /wp-json/wp/v2/media or posts content for images."""
        if not self.api_base_url:
            return []

        media_items = []
        # First attempt /wp-json/wp/v2/media
        media_url = f"{self.api_base_url}/wp-json/wp/v2/media?per_page=20"
        # You could paginate more if needed: per_page=100, etc.

        try:
            print(f"[WordPressHandler] Trying {media_url}")
            resp = requests.get(media_url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list):
                    # Each item is a media object with 'source_url' and 'title'
                    for m in data:
                        if m.get('media_type') == 'image':
                            img_url = m.get('source_url')
                            title = (m.get('title') or {}).get('rendered', 'WP image')
                            if img_url:
                                alt_text = m.get('alt_text', '')  # from WP metadata
                                media_items.append({
                                    'url': img_url,
                                    'alt': alt_text or title,
                                    'title': title,
                                    'source_url': self.url,
                                    'credits': "WordPress blog",
                                    'type': 'image',
                                    '_headers': {'Referer': self.url}
                                })
                # If data is empty, we might try posts next
                if media_items:
                    return media_items
                else:
                    print("[WordPressHandler] No media items found in /wp-json/wp/v2/media. Trying posts approach.")
            else:
                print(f"[WordPressHandler] WP media endpoint returned status {resp.status_code}")
        except Exception as e:
            print(f"[WordPressHandler] Error fetching media endpoint: {e}")
            # Fallback to posts approach

        # If we get here, try scanning posts content
        posts_url = f"{self.api_base_url}/wp-json/wp/v2/posts?per_page=10"
        try:
            print(f"[WordPressHandler] Trying {posts_url}")
            resp = requests.get(posts_url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                for p in data:
                    content = (p.get('content') or {}).get('rendered', '')
                    if not content:
                        continue
                    # Extract <img> from post content
                    post_id = p.get('id')
                    post_title = (p.get('title') or {}).get('rendered', 'WP Post')
                    img_matches = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', content, re.IGNORECASE)
                    for img_src in img_matches:
                        if img_src.startswith('http'):
                            media_items.append({
                                'url': img_src,
                                'alt': post_title,
                                'title': post_title,
                                'source_url': self.url,
                                'credits': "WordPress Post",
                                'type': 'image',
                                '_headers': {'Referer': self.url}
                            })
            else:
                print(f"[WordPressHandler] WP posts endpoint returned status {resp.status_code}")
        except Exception as e:
            print(f"[WordPressHandler] Error fetching posts endpoint: {e}")

        return media_items

    # --------------------------------------------------
    #               DOM / HTML FALLBACK
    # --------------------------------------------------
    def _dom_extract(self, page):
        """
        Typical infinite scroll or multi-page approach for WordPress themes.
        1) Try to scroll, then parse <img>.
        """
        items = []
        pw_page = self._get_playwright_page(page)
        if pw_page:
            # Basic attempt to scroll or click "Load more" to reveal images
            self._scroll_until_no_more(pw_page, max_scrolls=5)
            items.extend(self._extract_images_from_dom(pw_page))
        else:
            # If no playwright, fallback to raw HTML parse
            items.extend(self._extract_images_from_html(page))
        return items

    def _scroll_until_no_more(self, pw_page, max_scrolls=5):
        last_height = 0
        for i in range(max_scrolls):
            pw_page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            pw_page.wait_for_timeout(1500)
            new_height = pw_page.evaluate("document.body.scrollHeight")
            if new_height == last_height:
                print("[WordPressHandler] No more content loaded, stopping scroll.")
                break
            last_height = new_height

    def _extract_images_from_dom(self, pw_page):
        items = []
        try:
            img_elems = pw_page.query_selector_all("article img, .post img, .entry-content img, img")
            print(f"[WordPressHandler] Found {len(img_elems)} <img> in DOM.")
            for img in img_elems:
                src = img.get_attribute("src")
                if src and src.startswith("http"):
                    alt_text = img.get_attribute("alt") or "WP image"
                    items.append({
                        'url': src,
                        'alt': alt_text,
                        'title': alt_text,
                        'source_url': self.url,
                        'credits': "WordPress (DOM fallback)",
                        'type': 'image',
                        '_headers': {'Referer': self.url}
                    })
        except Exception as e:
            print(f"[WordPressHandler] Error extracting from DOM: {e}")
        return items

    def _extract_images_from_html(self, page):
        items = []
        html_content = ""
        if hasattr(page, 'html_content'):
            html_content = page.html_content
        elif hasattr(page, 'text'):
            html_content = page.text

        if not html_content:
            return items

        pattern = re.compile(r'<img[^>]+src=["\']([^"\']+)["\']', re.IGNORECASE)
        matches = pattern.findall(html_content)
        for m in matches:
            if m.startswith('http'):
                items.append({
                    'url': m,
                    'alt': "WP fallback image",
                    'title': "WordPress fallback",
                    'source_url': self.url,
                    'credits': "WordPress (HTML fallback)",
                    'type': 'image',
                    '_headers': {'Referer': self.url}
                })
        print(f"[WordPressHandler] HTML fallback found {len(items)} images.")
        return items

    def get_content_directory(self):
        """Generate WordPress-specific directory structure"""
        # Base directory is always 'wordpress'
        base_dir = "wordpress"
        
        # Content directory based on blog domain and path
        parsed_url = urlparse(self.url)
        domain = parsed_url.netloc
        if domain.startswith('www.'):
            domain = domain[4:]
        
        content_parts = [self._sanitize_directory_name(domain)]
        
        # Add path components if present
        path = parsed_url.path.strip('/')
        if path:
            path_components = [self._sanitize_directory_name(p) for p in path.split('/') if p]
            if path_components:
                content_parts.extend(path_components[:2])  # Limit depth to 2
        
        # Join all parts to form the path
        content_specific_dir = os.path.join(*content_parts)
        
        return (base_dir, content_specific_dir)
