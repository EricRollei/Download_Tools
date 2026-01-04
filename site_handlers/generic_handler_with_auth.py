"""
Generic Handler With Auth

Description: Generic handler for sites without specialized implementations
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
Generic website handler for the Web Image Scraper with Network Monitoring and Authentication
"""

from site_handlers.base_handler import BaseSiteHandler
from urllib.parse import urljoin, urlparse
import re
import time
import traceback
import os
import json
import asyncio
import random

# Try importing Playwright types safely
try:
    from playwright.async_api import Page as AsyncPage
    from scrapling.fetchers import PlayWrightFetcher
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    AsyncPage = None
    PlayWrightFetcher = None
    PLAYWRIGHT_AVAILABLE = False

class GenericWebsiteWithAuthHandler(BaseSiteHandler):
    """
    Generic handler for websites without a specific handler.
    Uses network monitoring to capture images as they load.
    Can also handle authentication for protected content.
    """

    @classmethod
    def can_handle(cls, url):
        """This handler can process any URL as a fallback"""
        # This should be the last handler to check, as it accepts any URL
        return True

    def __init__(self, url, scraper=None):
        """Initialize the generic handler"""
        super().__init__(url, scraper)
        self.debug_mode = True  # Enable debugging by default
        self.network_resources = []  # Store captured network resources
        self.seen_urls = set()  # Track unique URLs
        self.min_width = 100  # Minimum image width to consider
        self.min_height = 100  # Minimum image height to consider
        print(f"GenericWebsiteWithAuthHandler initialized for URL: {url}")
        
        # Configuration for different media types
        self.image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff', '.svg']
        self.video_extensions = ['.mp4', '.webm', '.mov', '.avi', '.mkv', '.mpg', '.mpeg', '.m4v']
        
        # Authentication state
        self.username = None
        self.password = None
        self.auth_loaded = False
        self.debug_auth = False  # Set to True for detailed auth logs
        self.is_logged_in = False
        self.last_auth_attempt_time = 0
        self.auth_retry_count = 0
        
        # Default auth settings (can be overridden by config)
        self.auth_type = 'basic'  # 'basic', 'form', 'api'
        self.auth_retry = 2
        self.auth_delay_ms = 1000
        self.auth_cooldown_sec = 300  # 5 minutes between retries

    async def pre_process_async(self, page):
        """Async version of pre_process"""
        print(f"GenericWebsiteWithAuthHandler: Pre-processing {self.url}")
        
        # Get any min dimensions from scraper if available
        if self.scraper:
            if hasattr(self.scraper, 'min_width'):
                self.min_width = self.scraper.min_width
            if hasattr(self.scraper, 'min_height'):
                self.min_height = self.scraper.min_height
        
        # Try to authenticate if credentials are available
        if PLAYWRIGHT_AVAILABLE:
            pw_page = await self._get_playwright_page_async(page)
            if pw_page:
                # First try to load session then authenticate if needed
                session_loaded = False
                if hasattr(self.scraper, 'session_manager'):
                    try:
                        session_loaded = await self.load_auth_session(pw_page)
                    except Exception as e:
                        print(f"Error loading session: {e}")
                
                if not session_loaded:
                    try:
                        auth_success = await self.authenticate(pw_page)
                        if auth_success:
                            # Save this new session for future use
                            await self.save_auth_session(pw_page)
                    except Exception as e:
                        print(f"Authentication attempt failed: {e}")
                
                # Handle cookie consent and popups
                await self._handle_cookie_consent(pw_page)
                await self._dismiss_popups(pw_page)
        
        # Additional async pre-processing if needed
        return page

    async def extract_media_items_async(self, page):
        """Async version of extract_media_items"""
        print(f"GenericWebsiteWithAuthHandler: Extracting media from {self.url}")
        start_time = time.time()
        media_items = []
        
        # Get the Playwright page
        pw_page = await self._get_playwright_page_async(page)
        if not pw_page:
            print("No Playwright page available, falling back to HTML extraction")
            html_items = await self._extract_media_from_html(page)
            return html_items
            
        print("Found Playwright page for network monitoring")
        
        # Reset resource tracking
        self.network_resources = []
        self.seen_urls = set()
        
        # Create resource event listeners
        try:
            # Set up network monitoring
            await self._setup_network_monitoring(pw_page)
            
            # Perform actions to trigger content loading
            await self._trigger_content_loading(pw_page)
            
            # Process captured resources
            print(f"Processing {len(self.network_resources)} captured network resources")
            media_items = await self._process_network_resources()
            
            # If we found enough items, return them
            if len(media_items) >= 5:
                print(f"Network monitoring found {len(media_items)} media items")
                print(f"Extraction completed in {time.time() - start_time:.2f} seconds")
                return media_items
                
            # Otherwise, try DOM-based extraction as fallback
            print("Network monitoring found few items, trying DOM extraction")
            dom_items = await self._extract_from_dom(pw_page)
            media_items.extend(dom_items)
            
            # If we still don't have enough, try HTML extraction
            if len(media_items) < 5:
                print("DOM extraction found few items, trying HTML extraction")
                html_items = await self._extract_media_from_html(page)
                media_items.extend(html_items)
                
        except Exception as e:
            print(f"Error during network monitoring: {e}")
            traceback.print_exc()
            
            # Fall back to HTML extraction on error
            print("Error occurred, falling back to HTML extraction")
            html_items = await self._extract_media_from_html(page)
            media_items.extend(html_items)
            
        print(f"GenericWebsiteWithAuthHandler: Extracted {len(media_items)} media items")
        print(f"Extraction completed in {time.time() - start_time:.2f} seconds")
        return media_items


    async def _extract_from_browser_cache(self, pw_page):
        """Extract media directly from the browser's cache"""
        media_items = []
        
        try:
            print("Extracting media from browser cache...")
            
            # Execute JavaScript to access the browser cache
            cache_data = await pw_page.evaluate('''
                async () => {
                    const items = [];
                    
                    // Function to get cache keys
                    async function getCacheItems() {
                        try {
                            // Get all cache storage names
                            const cacheNames = await caches.keys();
                            
                            for (const cacheName of cacheNames) {
                                // Open each cache
                                const cache = await caches.open(cacheName);
                                const requests = await cache.keys();
                                
                                // Process each cached request
                                for (const request of requests) {
                                    // Only process image/video requests
                                    const url = request.url;
                                    const isMedia = url.match(/\\.(jpe?g|png|gif|webp|mp4|webm)($|\\?)/i);
                                    
                                    if (isMedia) {
                                        // Try to get response
                                        const response = await cache.match(request);
                                        if (response) {
                                            const headers = {};
                                            response.headers.forEach((value, key) => {
                                                headers[key] = value;
                                            });
                                            
                                            items.push({
                                                url: url,
                                                type: url.match(/\\.(mp4|webm)($|\\?)/i) ? 'video' : 'image',
                                                content_type: response.headers.get('content-type') || '',
                                                size: response.headers.get('content-length') || 0
                                            });
                                        }
                                    }
                                }
                            }
                        } catch (e) {
                            console.error("Cache access error:", e);
                        }
                        return items;
                    }
                    
                    return await getCacheItems();
                }
            ''')
            
            print(f"Browser cache extraction found {len(cache_data)} media items")
            
            # Process and return cache data as media items
            domain = self._get_url_domain_name(self.url)
            page_title = self._extract_title_from_url(self.url) or f"Content from {domain}"
            
            for item in cache_data:
                url = item['url']
                
                # Skip tiny images and UI elements
                if self._is_likely_ui_element_url(url):
                    continue
                    
                media_items.append({
                    'url': url,
                    'alt': page_title,
                    'title': page_title,
                    'source_url': self.url,
                    'credits': f"From {domain}",
                    'type': item['type'],
                    'category': 'browser_cache',
                    '_headers': {
                        'Referer': self.url
                    }
                })
                
            return media_items
            
        except Exception as e:
            print(f"Error extracting from browser cache: {e}")
            return []
                

    async def _extract_from_card_gallery(self, pw_page):
        """Robust extraction by clicking gallery cards, handling modals, overlays, and multi-click for high-res."""
        media_items = []
        try:
            print("Looking for clickable gallery cards...")

            gallery_card_selectors = [
                "[data-testid='ElementTileLink__a']",
                "[aria-label='Go to element']",
                "[data-element-id]",
                ".gallery-item",
                ".card-image",
                "[class*='tile']",
                "[class*='card']",
                "[class*='thumb']",
                ".products .product a",
                ".gallery-item a",
                ".card a",
                ".product-card a",
            ]
            image_selectors = [
                "img.css-1y1og61",
                "img[data-testid='ElementImage_Image']",
                "img[class*='fullscreen']",
                "img[class*='full']",
                "img[class*='large']",
                ".fullscreen-image img",
                ".modal img",
                ".lightbox img",
                ".woocommerce-product-gallery__image a img",
                ".pswp__img",
                ".modal img",
                ".lightbox img",
                "img.full-size",
            ]
            modal_close_selectors = [
                "button.close",
                ".modal button.close",
                ".modal-close",
                ".popup-close",
                ".close-popup",
                ".modal .close",
                "[aria-label='Close']",
                ".dialog-close",
                "[class*='close-button']",
                ".dismiss",
                "button:has-text('Close')",
                "button:has-text('Cancel')",
                "button:has-text('No Thanks')",
                "button:has-text('Not Now')"
            ]

            # Find all gallery cards
            found_cards = False
            card_selector = None
            for selector in gallery_card_selectors:
                try:
                    cards = await pw_page.locator(selector).all()
                    if len(cards) > 0:
                        print(f"Found {len(cards)} gallery cards with selector: {selector}")
                        card_selector = selector
                        found_cards = True
                        break
                except Exception as e:
                    if self.debug_mode:
                        print(f"Selector {selector} not found: {e}")
                    continue

            if not found_cards:
                print("No gallery cards found")
                return media_items

            original_url = pw_page.url
            max_cards = 100
            max_image_clicks = 3

            cards = await pw_page.locator(card_selector).all()
            for i, card in enumerate(cards[:max_cards]):
                try:
                    print(f"Processing card {i+1}/{min(len(cards), max_cards)}...")
                    try:
                        await card.scroll_into_view_if_needed(timeout=2000)
                    except Exception:
                        pass
                    await card.click()
                    try:
                        await pw_page.wait_for_load_state("networkidle", timeout=5000)
                    except:
                        await pw_page.wait_for_timeout(2000)

                    # Wait for modal/image to appear
                    modal_found = False
                    for img_selector in image_selectors:
                        try:
                            img = pw_page.locator(img_selector).first
                            if await img.count() > 0:
                                modal_found = True
                                break
                        except Exception:
                            continue
                    if not modal_found:
                        print("No modal/image found after card click, skipping.")
                        # Try to close any modal just in case
                        for close_sel in modal_close_selectors:
                            try:
                                close_btn = pw_page.locator(close_sel).first
                                if await close_btn.count() > 0 and await close_btn.is_visible(timeout=1000):
                                    await close_btn.click()
                                    await pw_page.wait_for_timeout(500)
                                    break
                            except Exception:
                                continue
                        await pw_page.goto(original_url)
                        await pw_page.wait_for_timeout(1000)
                        continue

                    # Try to click the image up to max_image_clicks times
                    for click_num in range(max_image_clicks):
                        found_image = False
                        for img_selector in image_selectors:
                            try:
                                image = pw_page.locator(img_selector).first
                                if await image.count() > 0:
                                    found_image = True
                                    await image.scroll_into_view_if_needed(timeout=2000)
                                    src = await image.get_attribute("src")
                                    width = await image.get_attribute("width") or "0"
                                    height = await image.get_attribute("height") or "0"
                                    alt = await image.get_attribute("alt") or ""
                                    if src and src.startswith(("http", "https", "//")):
                                        if src.startswith("//"):
                                            src = "https:" + src
                                        media_item = {
                                            'url': src,
                                            'alt': alt,
                                            'title': alt or f"Image {i+1}",
                                            'source_url': pw_page.url,
                                            'credits': f"From {self._get_url_domain_name(self.url)}",
                                            'type': 'image',
                                            'category': 'gallery_card',
                                            'metadata': {
                                                'width': int(width) if width.isdigit() else 0,
                                                'height': int(height) if height.isdigit() else 0,
                                                'extraction_method': f'card_gallery_click_{click_num+1}'
                                            },
                                            '_headers': {
                                                'Referer': pw_page.url
                                            }
                                        }
                                        if not any(item['url'] == src for item in media_items):
                                            print(f"Extracted image (click {click_num+1}): {src}")
                                            media_items.append(media_item)
                                    # Click the image to try to reveal higher-res
                                    await image.click()
                                    await pw_page.wait_for_timeout(1200)
                                    break
                            except Exception as e:
                                continue
                        if not found_image:
                            print(f"No image found to click on click {click_num+1}")
                            break

                    # Try to close modal/overlay after extraction
                    for close_sel in modal_close_selectors:
                        try:
                            close_btn = pw_page.locator(close_sel).first
                            if await close_btn.count() > 0 and await close_btn.is_visible(timeout=1000):
                                await close_btn.click()
                                await pw_page.wait_for_timeout(500)
                                break
                        except Exception:
                            continue

                    # Go back to the gallery page
                    await pw_page.goto(original_url)
                    await pw_page.wait_for_timeout(1000)
                except Exception as e:
                    print(f"Error processing card {i+1}: {e}")
                    try:
                        await pw_page.goto(original_url)
                    except:
                        pass

            print(f"Extracted {len(media_items)} images from gallery cards (robust multi-click logic)")
            return media_items

        except Exception as e:
            print(f"Error in _extract_from_card_gallery: {e}")
            return media_items
            

    async def extract_with_direct_playwright_async(self, page, **kwargs):
        """
        Enhanced async extraction using direct Playwright with browser cache access
        """
        print(f"GenericWebsiteWithAuthHandler: Extracting media from {self.url}")
        start_time = time.time()
        media_items = []
        
        # Get important parameters
        self.min_width = kwargs.get('min_width', 100)
        self.min_height = kwargs.get('min_height', 100)
        self.debug_mode = kwargs.get('debug_mode', True)
        
        # First try to load an existing session
        session_loaded = False
        if kwargs.get('try_auth', True) and hasattr(self.scraper, 'session_manager'):
            try:
                session_loaded = await self.load_auth_session(page)
            except Exception as e:
                print(f"Error loading session: {e}")
        
        # If no valid session and auth is enabled, try to authenticate
        if not session_loaded and kwargs.get('try_auth', True):
            try:
                auth_success = await self.authenticate(page)
                if auth_success:
                    # Save this new session for future use
                    await self.save_auth_session(page)
            except Exception as e:
                print(f"Authentication attempt failed: {e}")
        
        # Reset resource tracking
        self.network_resources = []
        self.seen_urls = set()
        
        try:
            # Set up network monitoring first to catch all resources
            await self._setup_network_monitoring(page)
            
            # Perform actions to trigger content loading
            await self._trigger_content_loading(page)
            
            # Try to extract from browser cache first
            cache_items = await self._extract_from_browser_cache(page)
            if cache_items:
                print(f"Found {len(cache_items)} items in browser cache")
                media_items.extend(cache_items)
            
            # Process network resources
            if self.network_resources:
                network_items = await self._process_network_resources()
                print(f"Found {len(network_items)} items from network monitoring")
                media_items.extend(network_items)
            
            # If we don't have enough items, use DOM extraction
            if len(media_items) < 10:
                dom_items = await self._extract_from_dom(page)
                if dom_items:
                    print(f"Found {len(dom_items)} items from DOM extraction")
                    media_items.extend(dom_items)
            
            if 'cosmos.so' in self.url or 'gallery' in self.url.lower() or len(media_items) < 5:
                try:
                    gallery_items = await self._extract_from_card_gallery(page)
                    if gallery_items:
                        print(f"Found {len(gallery_items)} items from card gallery")
                        media_items.extend(gallery_items)
                except Exception as gallery_err:
                    print(f"Error accessing gallery: {gallery_err}")
                    
            # Last resort: try DevTools cache if available
            if len(media_items) < 5 and self.debug_mode:
                try:
                    devtools_items = await self._extract_from_chrome_cache(page)
                    if devtools_items:
                        print(f"Found {len(devtools_items)} items from DevTools cache")
                        media_items.extend(devtools_items)
                except Exception as cache_err:
                    print(f"Error accessing DevTools cache: {cache_err}")
            
            # Process and deduplicate the combined results
            final_items = await self.post_process(media_items)
            print(f"Extraction completed in {time.time() - start_time:.2f} seconds")
            
            # After successful extraction with logged-in state, save the session again to refresh
            if self.is_logged_in and hasattr(self.scraper, 'session_manager'):
                await self.save_auth_session(page)
                
            return final_items
            
        except Exception as e:
            print(f"Error during extraction: {e}")
            traceback.print_exc()
            return media_items

    def add_resource_url(self, url, resource_type='image'):
        """Add a resource URL to the tracking list"""
        if url not in self.seen_urls:
            self.network_resources.append({
                'url': url,
                'type': resource_type,
                'content_type': f"{resource_type}/*",
                'category': 'direct_addition'
            })
            self.seen_urls.add(url)
            return True
        return False


    async def _get_playwright_page_async(self, page_adaptor):
        """Safely attempts to retrieve the underlying Playwright Page object (async version)."""
        if not PLAYWRIGHT_AVAILABLE:
            print("Playwright not available")
            return None
            
        try:
            # Check different possible locations of the page object
            if hasattr(PlayWrightFetcher, '_last_page'):
                print("Found Playwright page via PlayWrightFetcher._last_page")
                return PlayWrightFetcher._last_page
                
            if hasattr(page_adaptor, '_response') and hasattr(page_adaptor._response, 'page'):
                print("Found Playwright page via _response.page")
                return page_adaptor._response.page
                
            if hasattr(page_adaptor, 'page'):
                print("Found Playwright page via .page")
                return page_adaptor.page
                
            # For async Playwright objects, try to handle the context
            if hasattr(page_adaptor, 'context'):
                # This might be a Playwright Page already
                print("Input appears to be a Playwright Page already")
                return page_adaptor
                
            # Try to get pages from context if available
            if hasattr(page_adaptor, 'browser_context') and hasattr(page_adaptor.browser_context, 'pages'):
                pages = await page_adaptor.browser_context.pages()
                if pages:
                    print("Found Playwright page via browser context")
                    return pages[0]
            
            print("Could not find Playwright page")
        except Exception as e:
            print(f"Error accessing Playwright page: {e}")
        return None

    def _extract_title_from_url(self, url):
        """Extract a title from the URL for metadata purposes"""
        try:
            # Parse the URL
            parsed = urlparse(url)
            
            # Extract the last path component
            path = parsed.path.strip('/')
            if not path:
                return None
                
            # Split by slashes and get the last part
            parts = path.split('/')
            last_part = parts[-1]
            
            # Clean up the title
            title = last_part.replace('-', ' ').replace('_', ' ').capitalize()
            
            return title
        except:
            return None

    def _is_likely_ui_element_url(self, url):
        """Check if URL patterns suggest a UI element"""
        # Check URL patterns common for UI elements
        lower_url = url.lower()
        for ui_pattern in ['/icon/', '/logo/', '/ui/', '/button/', '/static/', 
                          'avatar', 'badge', 'emoji', 'thumb']:
            if ui_pattern in lower_url:
                return True
            
        # Check common UI filenames
        ui_filenames = ['icon', 'logo', 'button', 'avatar', 'badge', 'menu', 'arrow', 'close', 'favicon']
        for filename in ui_filenames:
            if f"/{filename}." in lower_url or f"-{filename}." in lower_url or f"_{filename}." in lower_url:
                return True
                
        # Check if URL contains dimensions suggesting small icon
        size_patterns = re.findall(r'(\d+)x(\d+)', lower_url)
        for width, height in size_patterns:
            if int(width) < 100 and int(height) < 100:
                return True
                
        return False

    def _get_url_domain_name(self, url):
        """Extract domain name from URL for credits"""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc
            
            # Remove www. prefix if present
            if domain.startswith('www.'):
                domain = domain[4:]
                
            return domain
        except:
            return "website"

    async def _handle_response(self, response):
        """Handle network responses for monitoring"""
        try:
            url = response.url
            status = response.status
            
            # Get regex patterns from class
            ui_pattern = getattr(self, '_ui_pattern', None)
            small_image_pattern = getattr(self, '_small_image_pattern', None)
            
            if not ui_pattern or not small_image_pattern:
                # Initialize patterns if not done yet
                import re
                self._ui_pattern = re.compile(r'/(icon|logo|avatar|badge|thumb|button)/')
                self._small_image_pattern = re.compile(r'(\d+)x(\d+)')
                ui_pattern = self._ui_pattern
                small_image_pattern = self._small_image_pattern
            
            # Quick initial filtering
            if (status < 200 or status >= 300 or 
                url in self.seen_urls or 
                not url.startswith(('http://', 'https://')) or
                ui_pattern.search(url.lower())):
                return
                
            # Extract content type efficiently
            content_type = response.headers.get('content-type', '').lower()
            
            # Check for image responses (faster checks first)
            is_image = False
            if 'image/' in content_type:  # Quick string check before more specific
                is_image = any(img_type in content_type for img_type in 
                            ['jpeg', 'png', 'gif', 'webp', 'jpg'])
            
            # If not identified by content type, check extension
            if not is_image:
                path = urlparse(url).path.lower()
                is_image = any(path.endswith(ext) for ext in self.image_extensions)
            
            if is_image:
                # Skip likely UI elements with compiled regex (faster)
                if ui_pattern.search(url.lower()):
                    return
                    
                # Skip tiny images by size in URL
                size_matches = small_image_pattern.findall(url.lower())
                if size_matches and any(int(w) < 100 and int(h) < 100 
                                    for w, h in size_matches):
                    return
                    
                # Skip tiny images by content length
                content_length = response.headers.get('content-length')
                if content_length and int(content_length) < 8000:  # Increased threshold
                    return
                
                # Add the resource with minimal processing
                self.network_resources.append({
                    'url': url,
                    'type': 'image',
                    'content_type': content_type
                })
                self.seen_urls.add(url)
            
            # Check for video responses
            is_video = False
            if 'video/' in content_type:  # Quick string check before more specific
                is_video = any(vid_type in content_type for vid_type in 
                            ['mp4', 'webm', 'quicktime', 'x-msvideo', 'mpeg'])

            # If not identified by content type, check extension
            if not is_video:
                path = urlparse(url).path.lower()
                is_video = any(path.endswith(ext) for ext in self.video_extensions)

            if is_video:
                # Skip tiny videos by content length - videos should be substantial
                content_length = response.headers.get('content-length')
                if content_length and int(content_length) < 50000:  # At least 50KB for videos
                    return
                
                # Add the resource with minimal processing
                self.network_resources.append({
                    'url': url,
                    'type': 'video',
                    'content_type': content_type,
                    'size': content_length
                })
                self.seen_urls.add(url)
                if self.debug_mode:
                    print(f"Captured video resource: {url}")
                
        except Exception as e:
            if self.debug_mode:
                print(f"Error in response handler: {e}")

    async def _setup_network_monitoring(self, pw_page):
        """Configure network monitoring with improved filtering"""
        # Create a concurrent-safe collection
        from collections import deque
        import re
        
        # Use a deque with a maximum size to prevent memory issues
        self.network_resources = deque(maxlen=1000)
        
        # Precompile regular expressions for faster matching
        self._ui_pattern = re.compile(r'/(icon|logo|avatar|badge|thumb|button)/')
        self._small_image_pattern = re.compile(r'(\d+)x(\d+)')
        
        # Register the event listener with a lambda that calls our class method
        pw_page.on('response', lambda response: asyncio.create_task(self._handle_response(response)))
        print("Optimized network monitoring set up")

    async def _verify_url(self, item):
        """Verify if a URL contains valid media content"""
        try:
            url = item['url']
            
            # Quick checks for obviously valid media URLs
            path = urlparse(url).path.lower()
            if any(path.endswith(ext) for ext in self.image_extensions + self.video_extensions):
                return item
                
            # For uncertain URLs, do a HEAD request to verify
            import aiohttp
            async with aiohttp.ClientSession() as session:
                # Set a short timeout to avoid waiting for slow responses
                async with session.head(url, timeout=3, 
                                    headers={'User-Agent': 'Mozilla/5.0'}) as response:
                    if response.status == 200:
                        content_type = response.headers.get('content-type', '')
                        if ('image/' in content_type or 'video/' in content_type):
                            # Update item with real content type
                            item['verified_content_type'] = content_type
                            return item
            return None
        except Exception:
            return None

    async def post_process(self, media_items):
        """Improved post-processing with concurrent URL verification"""
        print(f"GenericWebsiteWithAuthHandler: Post-processing {len(media_items)} media items")
        
        if not media_items:
            return []
            
        import asyncio
        from urllib.parse import urlparse
        
        # Deduplicate by URL first (fast operation)
        seen_urls = set()
        unique_items = []
        
        for item in media_items:
            url = item.get('url')
            if not url:
                continue
                
            # Clean and normalize URL
            if url.startswith('//'):
                url = 'https:' + url
            elif not url.startswith(('http://', 'https://')):
                continue
                
            # Fix URL encoding
            url = url.replace('&amp;', '&')
            
            # Simple deduplication
            clean_url = url.split('?')[0].split('#')[0]
            if clean_url in seen_urls:
                continue
                
            # Skip tiny thumbnails and UI elements
            if self._is_likely_ui_element_url(clean_url):
                continue
                
            # Update the URL in the item
            item['url'] = url
            
            # Mark CDN domains as trusted to allow cross-domain downloads
            # This is critical for sites like Tilda that serve images from tildacdn.com
            if self.is_trusted_domain(url):
                item['trusted_cdn'] = True
            
            unique_items.append(item)
            seen_urls.add(clean_url)
        
        print(f"Found {len(unique_items)} unique items after deduplication")
        
        # Run verification concurrently with a limit on concurrency
        max_concurrent = 20  # Limit concurrent requests
        verified_items = []
        
        # Process in batches to control memory usage
        for i in range(0, len(unique_items), max_concurrent):
            batch = unique_items[i:i+max_concurrent]
            results = await asyncio.gather(*[self._verify_url(item) for item in batch], 
                                        return_exceptions=False)
            verified_items.extend([item for item in results if item])
        
        print(f"Returning {len(verified_items)} verified media items")
        return verified_items

    async def _trigger_content_loading(self, pw_page, **kwargs):
        """
        Perform actions to trigger content loading (async version).
        Supports scrolling the main page or a specific container, using UI-provided settings.
        """
        try:
            # Get scroll settings from kwargs or fallback to defaults
            max_scrolls = kwargs.get('max_scrolls', getattr(self, 'max_scrolls', 10))
            scroll_delay_ms = kwargs.get('scroll_delay_ms', getattr(self, 'scroll_delay_ms', 1000))
            scroll_container_selector = kwargs.get('scroll_container_selector', getattr(self, 'scroll_container_selector', None))

            print(f"Waiting for page to load...")
            await pw_page.wait_for_load_state("networkidle", timeout=5000)

            if scroll_container_selector:
                print(f"Scrolling container '{scroll_container_selector}' for content loading...")
                for i in range(max_scrolls):
                    await pw_page.evaluate(f'''
                        () => {{
                            const el = document.querySelector("{scroll_container_selector}");
                            if (el) el.scrollTop = el.scrollHeight;
                        }}
                    ''')
                    print(f"Scrolled container {i+1}/{max_scrolls}")
                    await pw_page.wait_for_timeout(scroll_delay_ms)
                    await self._find_and_click_load_buttons(pw_page)
                    try:
                        await pw_page.wait_for_load_state("networkidle", timeout=2000)
                    except Exception:
                        pass
            else:
                print(f"Scrolling main page for content loading...")
                for i in range(max_scrolls):
                    await pw_page.evaluate(f"window.scrollTo(0, document.body.scrollHeight * {i}/{max_scrolls})")
                    print(f"Scrolled main page {i+1}/{max_scrolls}")
                    await pw_page.wait_for_timeout(scroll_delay_ms)
                    await self._find_and_click_load_buttons(pw_page)
                    try:
                        await pw_page.wait_for_load_state("networkidle", timeout=2000)
                    except Exception:
                        pass

            print("Waiting for final resources to load...")
            try:
                await pw_page.wait_for_load_state("networkidle", timeout=2000)
            except Exception:
                pass

        except Exception as e:
            print(f"Error triggering content loading: {e}")

    async def _find_and_click_load_buttons(self, pw_page):
        """Find and click buttons that load more content (async version)"""
        try:
            # Common selectors for "load more" buttons
            load_button_selectors = [
                'button:has-text("Load more")',
                'button:has-text("Show more")',
                'button:has-text("View more")',
                'a:has-text("Load more")',
                'a:has-text("Show more")',
                'a:has-text("View more")',
                'a:has-text("Next")',
                '[class*="load-more"]',
                '[class*="show-more"]',
                '[class*="view-more"]'
            ]
            
            for selector in load_button_selectors:
                try:
                    # Check if button exists and is visible
                    button = await pw_page.query_selector(selector)
                    if button and await button.is_visible():
                        print(f"Clicking '{selector}' button")
                        await button.click()
                        # Wait for content to load
                        await pw_page.wait_for_timeout(2000)
                        try:
                            await pw_page.wait_for_load_state("networkidle", timeout=3000)
                        except Exception:
                            pass  # Continue if timeout
                        return True  # Stop after first successful click
                except Exception as e:
                    if self.debug_mode:
                        print(f"Error clicking {selector}: {e}")
                        
            return False
            
        except Exception as e:
            print(f"Error finding load buttons: {e}")
            return False

    async def _extract_from_dom(self, pw_page):
        """Extract media directly from DOM using JavaScript (async version)"""
        media_items = []
        
        try:
            print("Extracting media from DOM using JavaScript...")
            
            # Execute JavaScript to find all images in the DOM
            img_data = await pw_page.evaluate('''
                () => {
                    const items = [];
                    
                    // Get all image elements
                    const imgElements = document.querySelectorAll('img');
                    imgElements.forEach(img => {
                        // Check for data-src first (lazy-loaded images like Tilda CDN)
                        // These often contain the full-resolution original
                        // Tilda uses data-img-zoom-url and data-original for full-res zoomable images
                        const dataSrc = img.getAttribute('data-img-zoom-url') ||
                                        img.getAttribute('data-original') || 
                                        img.getAttribute('data-src') || 
                                        img.getAttribute('data-lazy-src') ||
                                        img.getAttribute('data-full-src') ||
                                        img.getAttribute('data-image');
                        
                        if (dataSrc && dataSrc.startsWith('http')) {
                            items.push({
                                url: dataSrc,
                                alt: img.alt || '',
                                title: img.title || '',
                                width: img.naturalWidth || img.width || 0,
                                height: img.naturalHeight || img.height || 0,
                                type: 'image',
                                isFullRes: true  // Mark as likely full-res from data attribute
                            });
                        }
                        
                        // Check src attribute
                        if (img.src && img.src.startsWith('http')) {
                            // Skip if it's a placeholder/thumbnail URL from known CDNs with resize markers
                            const isResized = img.src.includes('/resize/') || 
                                              img.src.includes('/-/empty/') ||
                                              img.src.includes('/thb.') ||
                                              img.src.includes('_thumb') ||
                                              img.src.includes('_small');
                            
                            // If we already have a data-src for this image, prefer that
                            // Only add src if it looks like a full-res version or no data-src exists
                            if (!dataSrc || !isResized) {
                                items.push({
                                    url: img.src,
                                    alt: img.alt || '',
                                    title: img.title || '',
                                    width: img.naturalWidth || img.width || 0,
                                    height: img.naturalHeight || img.height || 0,
                                    type: 'image',
                                    isFullRes: !isResized
                                });
                            }
                        }
                        
                        // Check srcset attribute
                        if (img.srcset) {
                            const srcsetParts = img.srcset.split(',');
                            for (const part of srcsetParts) {
                                const [url, size] = part.trim().split(' ');
                                if (url && url.startsWith('http')) {
                                    items.push({
                                        url: url,
                                        alt: img.alt || '',
                                        title: img.title || '',
                                        width: 0,  // Width unknown from srcset
                                        height: 0,  // Height unknown from srcset
                                        type: 'image'
                                    });
                                }
                            }
                        }
                    });
                    
                    // Find background images
                    const allElements = document.querySelectorAll('*');
                    allElements.forEach(el => {
                        try {
                            const style = window.getComputedStyle(el);
                            const bgImage = style.backgroundImage;
                            if (bgImage && bgImage !== 'none') {
                                const urlMatch = bgImage.match(/url\\(['"]?(http[^'"\\)]+)['"]?\\)/);
                                if (urlMatch && urlMatch[1]) {
                                    items.push({
                                        url: urlMatch[1],
                                        alt: el.getAttribute('aria-label') || el.textContent.trim().substring(0, 50) || '',
                                        title: '',
                                        width: el.offsetWidth || 0,
                                        height: el.offsetHeight || 0,
                                        type: 'image'
                                    });
                                }
                            }
                        } catch (e) {
                            // Ignore errors for individual elements
                        }
                    });
                    
                    // Find video elements
                    const videoElements = document.querySelectorAll('video');
                    videoElements.forEach(video => {
                        // Check direct src
                        if (video.src && video.src.startsWith('http')) {
                            items.push({
                                url: video.src,
                                alt: video.getAttribute('aria-label') || '',
                                title: '',
                                width: video.videoWidth || 0,
                                height: video.videoHeight || 0,
                                type: 'video'
                            });
                        }
                        
                        // Check source elements
                        const sources = video.querySelectorAll('source');
                        sources.forEach(source => {
                            if (source.src && source.src.startsWith('http')) {
                                items.push({
                                    url: source.src,
                                    alt: video.getAttribute('aria-label') || '',
                                    title: '',
                                    width: video.videoWidth || 0,
                                    height: video.videoHeight || 0,
                                    type: 'video'
                                });
                            }
                        });
                    });
                    
                    return items;
                }
            ''')
            
            print(f"DOM extraction found {len(img_data)} potential media items")
            
            # Process the JavaScript results
            domain = self._get_url_domain_name(self.url)
            page_title = self._extract_title_from_url(self.url) or f"Content from {domain}"
            seen_urls = set()
            
            for item in img_data:
                url = item.get('url', '')
                
                # Skip duplicates and UI elements
                if not url or url in seen_urls or self._is_likely_ui_element_url(url):
                    continue
                    
                # Use item metadata or fallback to page info
                alt_text = item.get('alt', '') or page_title
                title = item.get('title', '') or alt_text or page_title
                
                # Filter by size if available - but skip for items marked as full-res from data attributes
                # (lazy-loaded images report thumbnail dimensions, not actual full-res dimensions)
                is_full_res = item.get('isFullRes', False)
                width = item.get('width', 0)
                height = item.get('height', 0)
                if width > 0 and height > 0 and not is_full_res:
                    if width < self.min_width or height < self.min_height:
                        continue
                
                # Create media item
                media_items.append({
                    'url': url,
                    'alt': alt_text,
                    'title': title,
                    'source_url': self.url,
                    'credits': f"From {domain}",
                    'type': item.get('type', 'image'),
                    'category': 'dom_js_extracted',
                    '_headers': {
                        'Referer': self.url
                    }
                })
                
                seen_urls.add(url)
                
        except Exception as e:
            print(f"Error extracting from DOM: {e}")
            traceback.print_exc()
            
        return media_items


    async def _extract_from_chrome_cache(self, pw_page):
        """Extract media from Chrome cache using the DevTools Protocol"""
        media_items = []
        
        try:
            # Get the Chrome DevTools Protocol session
            cdp_session = await pw_page.context.new_cdp_session(pw_page)
            
            # Enable the necessary domains
            await cdp_session.send('Network.enable')
            await cdp_session.send('Page.enable')
            
            # Get all resources in the page
            resources_response = await cdp_session.send('Page.getResourceTree')
            resources = resources_response.get('frameTree', {}).get('resources', [])
            
            print(f"Found {len(resources)} resources via DevTools Protocol")
            
            # Process each resource
            for resource in resources:
                url = resource.get('url', '')
                mime_type = resource.get('mimeType', '')
                
                # Skip if not media or if UI element
                if not (mime_type.startswith('image/') or mime_type.startswith('video/')):
                    continue
                    
                if self._is_likely_ui_element_url(url):
                    continue
                    
                # Get resource content
                try:
                    content_response = await cdp_session.send('Page.getResourceContent', {
                        'frameId': resources_response['frameTree']['frame']['id'],
                        'url': url
                    })
                    
                    # If we have content and it's substantial
                    if content_response.get('content') and len(content_response.get('content', '')) > 1000:
                        media_type = 'image' if mime_type.startswith('image/') else 'video'
                        
                        media_items.append({
                            'url': url,
                            'alt': f"Content from {self._get_url_domain_name(self.url)}",
                            'title': self._extract_title_from_url(url) or "Media content",
                            'source_url': self.url,
                            'type': media_type,
                            'category': 'devtools_cache',
                            'content_available': True
                        })
                except Exception as content_err:
                    if self.debug_mode:
                        print(f"Error getting content for {url}: {content_err}")
            
            return media_items
            
        except Exception as e:
            print(f"Error accessing Chrome cache: {e}")
            return []

    async def _process_network_resources(self):
        """Process captured network resources into media items (async version)"""
        media_items = []
        unique_urls = set()
        
        # Get the domain and page title for metadata
        domain = self._get_url_domain_name(self.url)
        page_title = self._extract_title_from_url(self.url) or f"Content from {domain}"
        
        for resource in self.network_resources:
            url = resource.get('url', '')
            
            # Skip duplicates
            if not url or url in unique_urls:
                continue
                
            # Skip likely UI elements
            if self._is_likely_ui_element_url(url):
                continue
                
            # Create media item
            item = {
                'url': url,
                'alt': page_title,
                'title': page_title,
                'source_url': self.url,
                'credits': f"From {domain}",
                'type': resource.get('type', 'image'),
                'category': 'network_captured',
                '_headers': {
                    'Referer': self.url
                }
            }
            
            media_items.append(item)
            unique_urls.add(url)
            
        return media_items

    async def _extract_media_from_html(self, page):
        """Extract media directly from HTML when other methods fail (async version)"""
        media_items = []
        html_content = await self._get_page_content(page)
        
        if not html_content:
            print("No HTML content to extract from")
            return media_items
            
        print("Extracting media directly from HTML content")
        
        try:
            # Extract page title for metadata
            title_match = re.search(r'<title>([^<]+)</title>', html_content)
            page_title = title_match.group(1) if title_match else self._get_url_domain_name(self.url)
            print(f"Page title: {page_title}")
            
            # Different patterns for finding images
            img_patterns = [
                r'<img[^>]+src=["\'](https?://[^"\']+)["\']',  # Image src
                r'url\(["\']?(https?://[^"\')\s]+)["\']?\)',  # CSS background-image
                r'content=["\'](https?://[^"\']+\.(jpg|jpeg|png|gif|webp))["\']',  # Meta content
                r'<source[^>]+srcset=["\'](https?://[^"\']+)[^\'"]*["\']'  # Source srcset
            ]
            
            # Process image patterns
            all_img_urls = []
            for pattern in img_patterns:
                matches = re.findall(pattern, html_content)
                if matches:
                    if isinstance(matches[0], tuple):
                        # Some patterns return tuples
                        all_img_urls.extend([match[0] for match in matches])
                    else:
                        all_img_urls.extend(matches)
            
            # Remove duplicates
            all_img_urls = list(set(all_img_urls))
                
            print(f"Found {len(all_img_urls)} image URLs in HTML")
            
            # Look for video URLs in the HTML
            video_patterns = [
                r'<source[^>]+src=["\'](https?://[^"\']+\.(mp4|webm|mov))["\']',
                r'<video[^>]+src=["\'](https?://[^"\']+\.(mp4|webm|mov))["\']',
                r'<iframe[^>]+src=["\'](https?://[^"\']+(?:youtube\.com/embed/|vimeo\.com/video/)[^"\']+)["\']'
            ]
            
            # Process video patterns
            all_video_urls = []
            for pattern in video_patterns:
                matches = re.findall(pattern, html_content)
                if matches:
                    if isinstance(matches[0], tuple):
                        # Some patterns return tuples
                        all_video_urls.extend([match[0] for match in matches])
                    else:
                        all_video_urls.extend(matches)
                        
            # Remove duplicates
            all_video_urls = list(set(all_video_urls))
                
            print(f"Found {len(all_video_urls)} video URLs in HTML")
            
            # Process unique image URLs
            domain = self._get_url_domain_name(self.url)
            seen_urls = set()
            
            # Add images
            for url in all_img_urls:
                # Clean URL and skip duplicates
                clean_url = url.split('?')[0].split('#')[0]
                if not clean_url or clean_url in seen_urls:
                    continue
                    
                # Skip likely UI elements and small icons
                if self._is_likely_ui_element_url(clean_url):
                    continue
                    
                # Make relative URLs absolute
                if not clean_url.startswith(('http://', 'https://')):
                    clean_url = urljoin(self.url, clean_url)
                    
                print(f"Adding HTML-extracted image: {clean_url}")
                
                media_items.append({
                    'url': clean_url,
                    'alt': page_title,
                    'title': page_title,
                    'source_url': self.url,
                    'credits': f"From {domain}",
                    'type': 'image',
                    'category': 'html_extracted',
                    '_headers': {
                        'Referer': self.url
                    }
                })
                seen_urls.add(clean_url)
                
            # Add videos
            for url in all_video_urls:
                # Clean URL and skip duplicates
                clean_url = url.split('?')[0].split('#')[0]
                if not clean_url or clean_url in seen_urls:
                    continue
                    
                # Make relative URLs absolute
                if not clean_url.startswith(('http://', 'https://')):
                    clean_url = urljoin(self.url, clean_url)
                    
                print(f"Adding HTML-extracted video: {clean_url}")
                
                media_items.append({
                    'url': clean_url,
                    'alt': page_title,
                    'title': page_title,
                    'source_url': self.url,
                    'credits': f"From {domain}",
                    'type': 'video',
                    'category': 'html_extracted',
                    '_headers': {
                        'Referer': self.url
                    }
                })
                seen_urls.add(clean_url)
                
        except Exception as e:
            print(f"Error extracting media from HTML: {e}")
            traceback.print_exc()
            
        return media_items

    async def _get_page_content(self, page) -> str:
        """Get HTML content from page object (async version)"""
        html_content = ""
        
        # Try different ways to get the content based on page type
        if PLAYWRIGHT_AVAILABLE:
            pw_page = await self._get_playwright_page_async(page)
            if pw_page:
                try:
                    html_content = await pw_page.content()
                    print("Got HTML content via Playwright")
                    return html_content
                except Exception as e:
                    print(f"Error getting Playwright page content: {e}")
        
        # Try alternate methods to get content
        if hasattr(page, 'html_content'):
            print("Got HTML content via html_content attribute")
            return page.html_content
        elif hasattr(page, 'text'):
            print("Got HTML content via text attribute")
            return page.text
        else:
            print("Got HTML content via string conversion")
            return str(page)
            
    # Authentication methods from the prototype
    
    async def load_auth_credentials(self):
        """
        Load authentication credentials from auth_config for the current domain
        """
        # Initialize defaults
        self.username = None
        self.password = None
        self.auth_loaded = False
        
        # Skip if no scraper or auth_config
        if not hasattr(self, 'scraper') or not self.scraper:
            return False
            
        if not hasattr(self.scraper, 'auth_config') or not self.scraper.auth_config:
            return False
            
        # Get the domain from the URL
        domain = urlparse(self.url).netloc
        auth_config = self.scraper.auth_config
        domain_config = None
        
        # First try the site-specific config in 'sites' section (newer format)
        if 'sites' in auth_config and domain in auth_config['sites']:
            domain_config = auth_config['sites'][domain]
            if self.debug_auth:
                print(f"Found domain config in 'sites' section for {domain}")
        
        # Then try directly in the config (older format)
        elif domain in auth_config:
            domain_config = auth_config[domain]
            if self.debug_auth:
                print(f"Found direct domain config for {domain}")
        
        # If no exact domain match, try subdomain matching
        elif not domain_config:
            base_domain = '.'.join(domain.split('.')[-2:])  # Get base domain like 'example.com'
            for config_domain, config in auth_config.get('sites', {}).items():
                if base_domain in config_domain:
                    domain_config = config
                    if self.debug_auth:
                        print(f"Using {config_domain} config for {domain} (subdomain match)")
                    break
                    
        if domain_config:
            self.username = domain_config.get('username')
            self.password = domain_config.get('password')
            # Load additional config if available
            self.auth_type = domain_config.get('auth_type', 'basic')  # 'basic', 'form', 'api'
            self.auth_retry = domain_config.get('auth_retry', 2)
            self.auth_delay_ms = domain_config.get('auth_delay_ms', 1000)
            self.auth_loaded = True
            
            if self.debug_auth:
                print(f"Loaded auth for {domain}: username={self.username is not None}, auth_type={self.auth_type}")
        
        return domain_config is not None

    async def perform_login(self, page):
        """
        Generic login implementation that tries to handle most common login flows
        
        Args:
            page: Playwright page object
            
        Returns:
            bool: True if login appears successful, False otherwise
        """
        if not hasattr(self, 'username') or not self.username or not hasattr(self, 'password') or not self.password:
            if hasattr(self, 'debug_auth') and self.debug_auth:
                print("Missing login credentials")
            return False
        
        print(f"Attempting generic login for {urlparse(self.url).netloc} with username: {self.username}")
        
        try:
            # First check if we're already logged in
            already_logged_in = await self._check_if_logged_in(page)
            if already_logged_in:
                print("Already logged in")
                self.is_logged_in = True
                return True
                
            # Find and click login button if needed
            login_page_loaded = await self._navigate_to_login(page)
            if not login_page_loaded:
                print("Could not locate login page/form")
                return False
                
            # Find login form fields
            email_field = await self._find_username_field(page)
            password_field = await self._find_password_field(page)
            
            # Verify we have both fields
            if not email_field or not password_field:
                print(f"Login form incomplete - email field: {email_field is not None}, password field: {password_field is not None}")
                return False
                
            # Fill credentials with humanlike delays
            await email_field.click()
            await email_field.fill("")
            await page.wait_for_timeout(random.randint(200, 400))
            await email_field.fill(self.username)
            
            await page.wait_for_timeout(random.randint(500, 800))
            
            await password_field.click()
            await password_field.fill("")
            await page.wait_for_timeout(random.randint(200, 400))
            await password_field.fill(self.password)
            
            await page.wait_for_timeout(random.randint(300, 600))
            
            # Find and click submit button
            submit_button = await self._find_submit_button(page)
            if not submit_button:
                print("Submit button not found")
                return False
                
            # Take a screenshot before submitting if debug enabled
            if self.debug_auth and hasattr(self.scraper, 'output_path'):
                debug_dir = os.path.join(self.scraper.output_path, "debug")
                os.makedirs(debug_dir, exist_ok=True)
                await page.screenshot(path=os.path.join(debug_dir, "login_before_submit.png"))
            
            # Click the submit button
            await submit_button.click()
            print("Clicked submit button")
            
            # Wait for navigation or login completion
            try:
                # Wait for either navigation or a profile indicator to appear
                print("Waiting for login to complete...")
                # First try to wait for navigation
                try:
                    await page.wait_for_navigation(timeout=10000)
                except Exception:
                    # If navigation didn't happen, that's OK - many sites use AJAX for login
                    pass
                    
                # Give time for the page to settle
                await page.wait_for_timeout(3000)
                
                # Take a screenshot after login attempt if debug enabled
                if self.debug_auth and hasattr(self.scraper, 'output_path'):
                    debug_dir = os.path.join(self.scraper.output_path, "debug")
                    os.makedirs(debug_dir, exist_ok=True)
                    await page.screenshot(path=os.path.join(debug_dir, "login_after_submit.png"))
                
                # Verify login success
                login_success = await self._check_if_logged_in(page)
                
                if login_success:
                    print("Login successful!")
                    self.is_logged_in = True
                else:
                    # Check for common error messages
                    errors = await self._check_for_login_errors(page)
                    if errors:
                        print(f"Login failed: {errors}")
                    else:
                        print("Login may have failed - no success indicators found")
                
                return login_success
                
            except Exception as e:
                print(f"Error during login completion: {e}")
                return False
                
        except Exception as e:
            print(f"Login error: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def _navigate_to_login(self, page):
        """Find and navigate to login page if needed"""
        try:
            # First check if we're already on a login page
            login_form_visible = await self._is_login_form_visible(page)
            if login_form_visible:
                print("Already on login page")
                return True
                
            # Try common login button/link selectors
            login_selectors = [
                "a:has-text('Log In')", 
                "button:has-text('Log In')",
                "a:has-text('Login')",
                "button:has-text('Login')",
                "a:has-text('Sign In')",
                "button:has-text('Sign In')",
                ".login-link", 
                "[href*='login']",
                "[href*='signin']",
                "[data-testid='login']",
                "[data-testid='signin']"
            ]
            
            for selector in login_selectors:
                try:
                    login_element = page.locator(selector).first
                    if await login_element.count() > 0 and await login_element.is_visible(timeout=1000):
                        print(f"Found login button: {selector}")
                        await login_element.click()
                        await page.wait_for_timeout(2000)  # Wait for form to appear
                        
                        # Check if login form is now visible
                        if await self._is_login_form_visible(page):
                            return True
                except Exception as e:
                    if hasattr(self, 'debug_auth') and self.debug_auth:
                        print(f"Error with selector {selector}: {e}")
                    continue
                    
            # If we couldn't find a login button, try common login URLs
            current_url = page.url
            domain = urlparse(current_url).netloc
            scheme = urlparse(current_url).scheme
            
            login_paths = [
                "/login", 
                "/signin", 
                "/sign-in",
                "/user/login", 
                "/auth/login",
                "/account/login"
            ]
            
            for path in login_paths:
                try:
                    login_url = f"{scheme}://{domain}{path}"
                    print(f"Trying login URL: {login_url}")
                    await page.goto(login_url, timeout=10000)
                    await page.wait_for_timeout(2000)
                    
                    # Check if this looks like a login page
                    if await self._is_login_form_visible(page):
                        return True
                except Exception as e:
                    if hasattr(self, 'debug_auth') and self.debug_auth:
                        print(f"Error navigating to {path}: {e}")
                    continue
                    
            return False
        except Exception as e:
            print(f"Error navigating to login: {e}")
            return False

    async def _is_login_form_visible(self, page):
        """Check if there's a visible login form on the page"""
        try:
            # Check for password field as the most reliable indicator of login form
            password_field = await self._find_password_field(page)
            if password_field:
                return True
                
            # Look for common login form containers
            form_selectors = [
                "form[action*='login']",
                "form[action*='signin']",
                "form[id*='login']",
                "form[id*='signin']",
                "form.login-form",
                "form.signin-form",
                ".login-form",
                ".signin-form",
                "[id*='login-form']",
                "[id*='signin-form']"
            ]
            
            for selector in form_selectors:
                form = page.locator(selector).first
                if await form.count() > 0 and await form.is_visible(timeout=1000):
                    return True
                    
            return False
        except Exception as e:
            if hasattr(self, 'debug_auth') and self.debug_auth:
                print(f"Error checking login form visibility: {e}")
            return False

    async def _find_username_field(self, page):
        """Find the username/email input field"""
        username_selectors = [
            "input[name='email']", 
            "input[type='email']",
            "input[placeholder*='Email']", 
            "input[id*='email']",
            "input[name='username']", 
            "input[id*='username']",
            "input[placeholder*='Username']",
            "input[autocomplete='username']",
            "input[autocomplete='email']",
            "input[name='user']",
            "input[id*='login']",
            "input[name*='login']"
        ]
        
        for selector in username_selectors:
            try:
                field = page.locator(selector).first
                if await field.count() > 0 and await field.is_visible(timeout=1000):
                    return field
            except Exception:
                continue
                
        return None

    async def _find_password_field(self, page):
        """Find the password input field"""
        password_selectors = [
            "input[name='password']", 
            "input[type='password']",
            "input[placeholder*='Password']",
            "input[autocomplete='current-password']",
            "input[id*='password']"
        ]
        
        for selector in password_selectors:
            try:
                field = page.locator(selector).first
                if await field.count() > 0 and await field.is_visible(timeout=1000):
                    return field
            except Exception:
                continue
                
        return None

    async def _find_submit_button(self, page):
        """Find the form submit button"""
        submit_selectors = [
            "button[type='submit']", 
            "button:has-text('Log In')", 
            "button:has-text('Login')",
            "button:has-text('Sign In')", 
            "input[type='submit']",
            "button.login-button",
            "button.signin-button",
            "button.submit-button",
            "[type='submit']",
            "form button"  # Last resort: any button within a form
        ]
        
        for selector in submit_selectors:
            try:
                button = page.locator(selector).first
                if await button.count() > 0 and await button.is_visible(timeout=1000):
                    return button
            except Exception:
                continue
                
        return None

    async def _check_if_logged_in(self, page):
        """Check if user appears to be logged in"""
        try:
            # Common indicators of being logged in
            logged_in_selectors = [
                ".profile-link", 
                ".user-profile", 
                ".avatar", 
                ".user-menu",
                "[aria-label*='account']",
                "[aria-label*='profile']",
                "a[href*='/account']",
                "a[href*='/profile']",
                ".logged-in",
                ".logout-button",
                "a:has-text('Logout')",
                "a:has-text('Sign Out')",
                "button:has-text('Logout')",
                "button:has-text('Sign Out')"
            ]
            
            for selector in logged_in_selectors:
                try:
                    element = page.locator(selector).first
                    if await element.count() > 0 and await element.is_visible(timeout=1000):
                        return True
                except Exception:
                    continue
                    
            # Check if login-related elements are NOT visible (negative check)
            login_elements = [
                "a:has-text('Log In')",
                "a:has-text('Login')",
                "a:has-text('Sign In')",
                "button:has-text('Log In')",
                "button:has-text('Login')",
                "button:has-text('Sign In')"
            ]
            
            login_visible = False
            for selector in login_elements:
                try:
                    element = page.locator(selector).first
                    if await element.count() > 0 and await element.is_visible(timeout=1000):
                        login_visible = True
                        break
                except Exception:
                    continue
                    
            # If no login elements are visible, that's a good sign
            if not login_visible:
                # Check if we have any authenticated-only content
                # This is site-specific, but some common patterns
                account_elements = [
                    ".dashboard", 
                    ".account-info", 
                    ".subscription", 
                    ".my-account",
                    "[data-authenticated='true']"
                ]
                
                for selector in account_elements:
                    try:
                        element = page.locator(selector).first
                        if await element.count() > 0 and await element.is_visible(timeout=1000):
                            return True
                    except Exception:
                        continue
                        
            return False
        except Exception as e:
            print(f"Error checking login status: {e}")
            return False

    async def _check_for_login_errors(self, page):
        """Check for common login error messages"""
        try:
            error_selectors = [
                ".error-message", 
                ".login-error", 
                ".alert-danger", 
                "[role='alert']",
                ".error",
                ".form-error"
            ]
            
            for selector in error_selectors:
                try:
                    error = page.locator(selector).first
                    if await error.count() > 0 and await error.is_visible(timeout=1000):
                        return await error.inner_text()
                except Exception:
                    continue
                    
            return None
        except Exception as e:
            print(f"Error checking for login errors: {e}")
            return None

    async def authenticate(self, page):
        """
        Main authentication method to be called from extraction flows.
        Loads credentials and performs login if needed.
        
        Args:
            page: Playwright page object
            
        Returns:
            bool: True if authenticated, False otherwise
        """
        # Check if we recently tried and failed to authenticate
        current_time = time.time()
        if (self.auth_retry_count > 0 and 
            current_time - self.last_auth_attempt_time < self.auth_cooldown_sec):
            print(f"Skipping auth - cooling down after previous attempts. Try again in {self.auth_cooldown_sec - (current_time - self.last_auth_attempt_time):.0f}s")
            return False
            
        # Load credentials from config
        credentials_loaded = await self.load_auth_credentials()
        if not credentials_loaded:
            print("No authentication credentials found for this site")
            return False
            
        # Check if we need to authenticate
        already_logged_in = await self._check_if_logged_in(page)
        if already_logged_in:
            print("Already authenticated")
            self.is_logged_in = True
            return True
            
        # Try to authenticate
        login_attempts = getattr(self, 'auth_retry', 2) + 1
        
        for attempt in range(login_attempts):
            try:
                if attempt > 0:
                    print(f"Login attempt {attempt+1}/{login_attempts}")
                    
                self.last_auth_attempt_time = time.time()
                login_success = await self.perform_login(page)
                
                if login_success:
                    self.auth_retry_count = 0  # Reset retry counter on success
                    return True
                    
                # Wait before retry
                if attempt < login_attempts - 1:
                    await page.wait_for_timeout(getattr(self, 'auth_delay_ms', 2000))
                    
            except Exception as e:
                print(f"Authentication error on attempt {attempt+1}: {e}")
                if attempt < login_attempts - 1:
                    await page.wait_for_timeout(getattr(self, 'auth_delay_ms', 2000))
                    
        # Update retry counter after all attempts failed
        self.auth_retry_count += 1
        print("Authentication failed after all attempts")
        return False

    async def save_auth_session(self, page):
        """
        Save authentication cookies/storage for future use
        """
        if not hasattr(self, 'scraper') or not self.scraper:
            return False
            
        # Check if we have a session manager
        if not hasattr(self.scraper, 'session_manager'):
            return False
            
        try:
            domain = urlparse(self.url).netloc
            
            # Check if page is a Playwright page
            if not hasattr(page, 'context'):
                return False
                
            # Get browser context and save
            context = page.context
            await self.scraper.session_manager.store_session(domain, context)
            print(f"Saved authentication session for {domain}")
            return True
                
        except Exception as e:
            print(f"Error saving authentication session: {e}")
            return False

    async def load_auth_session(self, page):
        """
        Load saved authentication session if available
        """
        if not hasattr(self, 'scraper') or not self.scraper:
            return False
            
        # Check if we have a session manager
        if not hasattr(self.scraper, 'session_manager'):
            return False
            
        try:
            domain = urlparse(self.url).netloc
            
            # Check if page is a Playwright page
            if not hasattr(page, 'context'):
                return False
                
            # Get browser context and load
            context = page.context
            session_loaded = await self.scraper.session_manager.load_session(domain, context)
            
            if session_loaded:
                print(f"Loaded authentication session for {domain}")
                # Verify the session is still valid
                await page.reload()
                is_logged_in = await self._check_if_logged_in(page)
                if is_logged_in:
                    print("Session login confirmed")
                    self.is_logged_in = True
                    return True
                else:
                    print("Session expired, will need to log in again")
                    return False
            return False
                
        except Exception as e:
            print(f"Error loading authentication session: {e}")
            return False

    async def _handle_cookie_consent(self, page):
        """Handle common cookie consent dialogs"""
        try:
            # Common cookie accept button selectors
            cookie_button_selectors = [
                "button:has-text('Accept')",
                "button:has-text('Accept All')",
                "button:has-text('Allow')",
                "button:has-text('Allow All')",
                "button:has-text('I Agree')",
                "button:has-text('Agree')",
                "button:has-text('Continue')",
                ".cookie-accept",
                ".accept-cookies",
                ".cookie-consent button",
                "[id*='cookie'] button",
                "[class*='cookie'] button",
                "[id*='consent'] button",
                "[class*='consent'] button",
                "[id*='gdpr'] button",
                "[class*='gdpr'] button"
            ]
            
            for selector in cookie_button_selectors:
                try:
                    button = page.locator(selector).first
                    if await button.is_visible(timeout=1000):
                        print(f"Found cookie consent button: {selector}")
                        await button.click()
                        await page.wait_for_timeout(500)
                        return True
                except Exception:
                    continue
            
            return False
        except Exception as e:
            print(f"Error handling cookie consent: {e}")
            return False

    async def _dismiss_popups(self, page):
        """Dismiss common popups and modals"""
        try:
            # Common popup close button selectors
            popup_close_selectors = [
                "button.close",
                ".modal button.close",
                ".modal-close",
                ".popup-close",
                ".close-popup",
                ".modal .close",
                "[aria-label='Close']",
                ".dialog-close",
                "[class*='close-button']",
                ".dismiss",
                "button:has-text('Close')",
                "button:has-text('Cancel')",
                "button:has-text('No Thanks')",
                "button:has-text('Not Now')"
            ]
            
            for selector in popup_close_selectors:
                try:
                    close_button = page.locator(selector).first
                    if await close_button.is_visible(timeout=1000):
                        print(f"Found popup close button: {selector}")
                        await close_button.click()
                        await page.wait_for_timeout(500)
                except Exception:
                    continue
            
            return True
        except Exception as e:
            print(f"Error dismissing popups: {e}")
            return False