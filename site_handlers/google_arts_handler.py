"""
Google Arts Handler

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

"""
Google Arts & Culture-specific handler for the Web Image Scraper
Handles artwork pages, exhibits, collections, artist pages and cultural institution pages.
"""

from site_handlers.base_handler import BaseSiteHandler 
from urllib.parse import urljoin, urlparse, parse_qs
from typing import List, Dict, Any, Optional, Union
import os
import json
import re
import time
import traceback
import requests
import random

# Try importing Playwright types safely
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

class GoogleArtsHandler(BaseSiteHandler):
    """
    Handler for Google Arts & Culture (artsandculture.google.com), a platform for high-quality artwork from museums.
    
    Features:
    - Extract high-resolution artwork from museum collections
    - Support for artwork pages, exhibits, collections, and artist profiles
    - Captures artwork titles, descriptions and detailed attribution information
    - Proper cultural institution and artist metadata
    - High-resolution image extraction
    """
    
    @classmethod
    def can_handle(cls, url):
        """Check if this handler can process the URL"""
        return "artsandculture.google.com" in url.lower()
    
    def __init__(self, url, scraper=None):
        """Initialize with Google Arts & Culture-specific properties"""
        super().__init__(url, scraper)
        self.asset_id = None
        self.entity_id = None  # For artists, museums, etc.
        self.exhibit_id = None
        self.page_type = self._determine_page_type(url)
        self.debug_mode = getattr(scraper, 'debug_mode', False)
        
        # Extract identifiers from URL
        self._extract_identifiers_from_url()
        
        # Load site-specific auth configuration
        self._load_api_credentials()  # This is inherited from base_handler
        
        # Set site-specific defaults from config or fallback values
        self.timeout_ms = getattr(self, 'timeout', 10000)
        self.wait_for_network_idle = getattr(self, 'wait_for_network_idle', True)
        self.scroll_delay_ms = getattr(self, 'scroll_delay_ms', 2000)
        self.max_scroll_count = getattr(self, 'max_scroll_count', 10)
    
    # Keep _determine_page_type() method exactly as is
    def _determine_page_type(self, url):
        """Determine what type of Google Arts & Culture page we're dealing with"""
        parsed_url = urlparse(url)
        path = parsed_url.path.strip('/')
        
        if not path:
            return "home"
            
        path_parts = path.split('/')
        
        # Determine page type based on URL structure
        if path.startswith('asset/'):
            return "artwork"
        elif path.startswith('entity/'):
            return "entity"  # Artist, movement, medium, etc.
        elif path.startswith('exhibit/'):
            return "exhibit"
        elif path.startswith('partner/'):
            return "partner"  # Museum or institution
        elif path.startswith('project/'):
            return "project"
        elif path.startswith('story/'):
            return "story"
        elif path.startswith('category/'):
            return "category"
        elif path.startswith('explore'):
            return "explore"
        elif path.startswith('theme/'):
            return "theme"
        elif path.startswith('color/'):
            return "color"
        else:
            return "other"

    # Keep _extract_identifiers_from_url() method exactly as is
    def _extract_identifiers_from_url(self):
        """Extract asset ID, entity ID, etc. from the URL"""
        parsed_url = urlparse(self.url)
        path = parsed_url.path.strip('/')
        path_parts = path.split('/')
        
        # Extract IDs based on page type
        if self.page_type == "artwork" and len(path_parts) >= 2:
            self.asset_id = path_parts[1]
            if self.debug_mode:
                print(f"Extracted asset ID: {self.asset_id}")
                
        elif self.page_type == "entity" and len(path_parts) >= 2:
            self.entity_id = path_parts[1]
            if self.debug_mode:
                print(f"Extracted entity ID: {self.entity_id}")
                
        elif self.page_type == "partner" and len(path_parts) >= 2:
            self.entity_id = path_parts[1]
            if self.debug_mode:
                print(f"Extracted partner ID: {self.entity_id}")
                
        elif self.page_type == "exhibit" and len(path_parts) >= 2:
            self.exhibit_id = path_parts[1]
            if self.debug_mode:
                print(f"Extracted exhibit ID: {self.exhibit_id}")
    
    # Keep get_content_directory() method exactly as is
    def get_content_directory(self):
        """
        Generate Google Arts & Culture-specific directory structure.
        Returns (base_dir, content_specific_dir) tuple.
        """
        # Base directory is always 'google_arts'
        base_dir = "google_arts"
        
        # Content directory based on page type
        content_parts = []
        
        if self.page_type == "artwork":
            content_parts.append("artwork")
            if self.asset_id:
                content_parts.append(self._sanitize_directory_name(self.asset_id))
                
        elif self.page_type == "entity":
            content_parts.append("entity")
            if self.entity_id:
                content_parts.append(self._sanitize_directory_name(self.entity_id))
                
        elif self.page_type == "partner":
            content_parts.append("partner")
            if self.entity_id:
                content_parts.append(self._sanitize_directory_name(self.entity_id))
                
        elif self.page_type == "exhibit":
            content_parts.append("exhibit")
            if self.exhibit_id:
                content_parts.append(self._sanitize_directory_name(self.exhibit_id))
                
        elif self.page_type == "project":
            content_parts.append("project")
            parsed_url = urlparse(self.url)
            path = parsed_url.path.strip('/')
            path_parts = path.split('/')
            if len(path_parts) >= 2:
                content_parts.append(self._sanitize_directory_name(path_parts[1]))
                
        elif self.page_type == "story":
            content_parts.append("story")
            parsed_url = urlparse(self.url)
            path = parsed_url.path.strip('/')
            path_parts = path.split('/')
            if len(path_parts) >= 2:
                content_parts.append(self._sanitize_directory_name(path_parts[1]))
                
        elif self.page_type == "category" or self.page_type == "explore":
            if self.page_type == "category":
                content_parts.append("category")
            else:
                content_parts.append("explore")
                
            parsed_url = urlparse(self.url)
            path = parsed_url.path.strip('/')
            path_parts = path.split('/')
            if len(path_parts) >= 2:
                content_parts.append(self._sanitize_directory_name(path_parts[1]))
                
        else:
            # Generic path handling for other page types
            parsed_url = urlparse(self.url)
            path = parsed_url.path.strip('/')
            path_components = [self._sanitize_directory_name(p) for p in path.split('/') if p]
            if path_components:
                content_parts.extend(path_components[:2])  # Limit depth to 2
            else:
                content_parts.append("general")
        
        # Ensure there's at least one part
        if not content_parts:
            content_parts.append("general")
        
        # Join all parts to form the path
        content_specific_dir = os.path.join(*content_parts)
        
        return (base_dir, content_specific_dir)

    async def _init_stealth_playwright(self):
        """Initializes Playwright with enhanced stealth options for Google Arts"""
        if not PLAYWRIGHT_AVAILABLE:
            print("Playwright library not available")
            return None
            
        try:
            print("Initializing stealth Playwright for Google Arts & Culture...")
            
            # Start Playwright
            playwright_instance = await async_playwright().start()
            
            # Choose a random user agent from a pool
            user_agents = [
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.3 Safari/605.1.15",
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/109.0"
            ]
            user_agent = random.choice(user_agents)
            
            # Advanced stealth arguments
            browser_args = [
                '--disable-blink-features=AutomationControlled',
                '--disable-features=IsolateOrigins,site-per-process,SitePerProcess',
                '--disable-site-isolation-trials',
                '--disable-web-security',
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-accelerated-2d-canvas',
                '--disable-gpu',
                '--no-first-run',
                '--no-service-autorun',
                '--password-store=basic',
                '--use-mock-keychain',
                '--disable-extensions'
            ]
            
            # Launch with stealth arguments
            browser = await playwright_instance.chromium.launch(
                headless=True,
                args=browser_args
            )
            
            # Set up a more realistic browser context
            context = await browser.new_context(
                user_agent=user_agent,
                viewport={"width": 1920, "height": 1080},
                device_scale_factor=1.0,
                locale="en-US",
                timezone_id="America/New_York",
                has_touch=False,
                is_mobile=False,
                color_scheme="light",
                accept_downloads=True
            )
            
            # Add stealth script to evade detection
            await context.add_init_script("""
            () => {
                // Override the navigator.webdriver property
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => false,
                    configurable: true
                });
                
                // Add language and plugins
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['en-US', 'en'],
                    configurable: true
                });
                
                // Spoof plugins
                const originalPlugins = Object.getOwnPropertyDescriptor(Navigator.prototype, 'plugins');
                if (originalPlugins) {
                    Object.defineProperty(navigator, 'plugins', {
                        get: () => {
                            const plugins = {
                                length: 5,
                                item: () => null,
                                namedItem: () => null,
                                refresh: () => {}
                            };
                            for (let i = 0; i < 5; i++) {
                                plugins[i] = { name: `Plugin ${i}`, description: `Description ${i}` };
                            }
                            return plugins;
                        },
                        configurable: true
                    });
                }
                
                // Override permissions API
                const originalPermissions = navigator.permissions;
                if (originalPermissions) {
                    navigator.permissions.query = (function(originalQuery) {
                        return function(queryOptions) {
                            if (queryOptions.name === 'notifications' || 
                                queryOptions.name === 'clipboard-read' || 
                                queryOptions.name === 'clipboard-write') {
                                return Promise.resolve({ state: "prompt", onchange: null });
                            }
                            return originalQuery.call(this, queryOptions);
                        };
                    })(navigator.permissions.query);
                }
                
                // Add touch points for hardware concurrency
                Object.defineProperty(navigator, 'hardwareConcurrency', {
                    get: () => 8,
                    configurable: true
                });
                
                // Override User Agent string in case first method fails
                window.navigator.userAgent = "${user_agent}";
            }
            """)
            
            # Add cookie consent auto-clicker
            await context.add_init_script("""
            () => {
                // Auto-click cookie consent buttons after page loads
                setTimeout(() => {
                    const cookieSelectors = [
                        'button[aria-label*="Accept"]',
                        'button[aria-label*="Agree"]',
                        'button[aria-label*="consent"]',
                        'button:has-text("Accept all")',
                        'button:has-text("Accept cookies")',
                        'button:has-text("I agree")',
                        '.cookie-banner button',
                        '#consent-modal button'
                    ];
                    
                    cookieSelectors.forEach(selector => {
                        const button = document.querySelector(selector);
                        if (button && button.offsetParent !== null) {
                            console.log('Auto-clicking cookie consent button');
                            button.click();
                        }
                    });
                }, 3000);
            }
            """)
            
            # Set default navigation timeout
            context.set_default_timeout(30000)
            
            # Create a new page
            page = await context.new_page()
            
            # Auto-dismiss dialogs
            page.on("dialog", lambda dialog: dialog.dismiss())
            
            print(f"Stealth Playwright initialized with user agent: {user_agent[:30]}...")
            return (playwright_instance, browser, context, page)
        
        except Exception as e:
            print(f"Error initializing stealth Playwright: {e}")
            traceback.print_exc()
            
            # Clean up any resources that were created
            if 'playwright_instance' in locals() and playwright_instance:
                await playwright_instance.stop()
            
            return None

    async def _handle_dynamic_content(self, page: AsyncPage, **kwargs):
        """Comprehensive approach to handling dynamically loaded content"""
        print("Preparing to handle dynamic content...")
        
        try:
            # 1. Initial wait to let JavaScript initialize
            initial_wait_ms = kwargs.get('initial_wait_ms', 2000)
            await page.wait_for_timeout(initial_wait_ms)
            
            # 2. Scroll with intelligent detection of new content
            await self._intelligent_scroll(page, **kwargs)
            
            # 3. Click any "Load More"/"Show More" buttons
            await self._click_load_more_buttons(page)
            
            # 4. Force load any lazy images
            await self._force_lazy_image_loading(page)
            
            # 5. Wait for network idle to ensure everything is loaded
            try:
                await page.wait_for_load_state("networkidle", timeout=5000)
            except Exception:
                # Just a timeout, not critical
                pass
                
            print("Dynamic content handling complete")
            
        except Exception as e:
            print(f"Error handling dynamic content: {e}")
            traceback.print_exc()

    async def _intelligent_scroll(self, page: AsyncPage, **kwargs):
        """Smart scrolling that adapts to page content loading patterns"""
        max_scrolls = kwargs.get('max_auto_scrolls', 10)
        scroll_delay_ms = kwargs.get('scroll_delay_ms', 1500)
        
        print(f"Starting intelligent scrolling: max={max_scrolls}, delay={scroll_delay_ms}ms")
        
        try:
            content_counters = {
                'images': await page.evaluate('() => document.querySelectorAll("img").length'),
                'links': await page.evaluate('() => document.querySelectorAll("a").length')
            }
            
            unchanged_count = 0
            last_height = await page.evaluate('() => document.documentElement.scrollHeight')
            
            for i in range(max_scrolls):
                # Scroll to bottom
                await page.evaluate('window.scrollTo({top: document.documentElement.scrollHeight, behavior: "smooth"})')
                
                # Wait for content to load
                await page.wait_for_timeout(scroll_delay_ms)
                
                # Check current stats
                current_height = await page.evaluate('() => document.documentElement.scrollHeight')
                current_counters = {
                    'images': await page.evaluate('() => document.querySelectorAll("img").length'),
                    'links': await page.evaluate('() => document.querySelectorAll("a").length')
                }
                
                # Detect if any content changed
                has_changes = (current_height > last_height) or \
                            (current_counters['images'] > content_counters['images']) or \
                            (current_counters['links'] > content_counters['links'])
                
                if has_changes:
                    unchanged_count = 0
                    print(f"Scroll {i+1}: New content detected. Images: {current_counters['images']}")
                    
                    # Update our tracking variables
                    content_counters = current_counters
                    last_height = current_height
                else:
                    unchanged_count += 1
                    print(f"Scroll {i+1}: No new content. Unchanged scrolls: {unchanged_count}")
                    
                    # Try clicking "Load More" after first unchanged scroll
                    if unchanged_count == 1:
                        clicked = await self._click_load_more_buttons(page)
                        if clicked:
                            await page.wait_for_timeout(scroll_delay_ms * 1.5)
                            unchanged_count = 0  # Reset counter if we clicked something
                            
                    # Exit after consecutive unchanged scrolls
                    elif unchanged_count >= 3:
                        print("No new content after multiple scrolls, stopping")
                        break
            
            print(f"Finished scrolling. Final count: {content_counters['images']} images")
            
        except Exception as e:
            print(f"Error during intelligent scrolling: {e}")

    async def _click_load_more_buttons(self, page: AsyncPage) -> bool:
        """Click on any 'Load More' or similar buttons"""
        try:
            # First try using Playwright's locator API
            try:
                locator = page.locator('text="Load More"').first
                if await locator.is_visible(timeout=500):
                    await locator.click()
                    await page.wait_for_timeout(2000)
                    print("Clicked 'Load More' button using locator")
                    return True
            except Exception:
                pass
            
            # Try other common locators
            common_selectors = [
                '[aria-label*="more"]',
                '.load-more',
                '.show-more',
                '[data-test-id*="load-more"]'
            ]
            
            for selector in common_selectors:
                try:
                    locator = page.locator(selector).first
                    if await locator.is_visible(timeout=500):
                        await locator.click()
                        await page.wait_for_timeout(2000)
                        print(f"Clicked button with selector: {selector}")
                        return True
                except Exception:
                    continue
            
            # Fall back to pure JavaScript
            clicked = await page.evaluate("""() => {
                // Common text patterns for load more buttons
                const loadMoreTexts = ['load more', 'show more', 'see more', 'view more', 'more results'];
                
                // Find buttons by their text content
                const buttons = Array.from(document.querySelectorAll('button, [role="button"], a.button, .button'));
                const loadMoreButtons = buttons.filter(btn => {
                    const text = (btn.textContent || '').toLowerCase();
                    return loadMoreTexts.some(pattern => text.includes(pattern));
                });
                
                if (loadMoreButtons.length > 0) {
                    loadMoreButtons[0].click();
                    return true;
                }
                
                // Try standard selectors
                const buttonSelectors = [
                    '.load-more', 
                    '.show-more',
                    '[aria-label*="more"]',
                    '[data-test-id*="load-more"]',
                    '.more-button',
                    '.see-more'
                ];
                
                for (const selector of buttonSelectors) {
                    const elements = document.querySelectorAll(selector);
                    for (const el of elements) {
                        if (el.offsetParent !== null) { // Check if visible
                            el.click();
                            return true;
                        }
                    }
                }
                
                return false;
            }""")
            
            if clicked:
                print("Clicked a 'Load More' button via JavaScript")
                await page.wait_for_timeout(2000)
                return True
            
            return False
            
        except Exception as e:
            print(f"Error clicking load more buttons: {e}")
            return False

# Add this new method to the GoogleArtsHandler class

    async def direct_download_media(self, page, output_path, stats, **kwargs):
        """
        Extract and immediately download media items from a page.
        This bypasses any issues with the link crawler pipeline.
        """
        try:
            # First extract media items using our normal extraction methods
            media_items = await self.extract_with_direct_playwright_async(page, **kwargs)
            
            if not media_items:
                print("No media items found for direct download")
                return 0
                
            print(f"Found {len(media_items)} items for direct download")
            
            # Download each item directly
            downloaded_count = 0
            for idx, item in enumerate(media_items):
                try:
                    image_url = item.get('url')
                    if not image_url:
                        continue
                        
                    # Create a filename
                    extension = os.path.splitext(image_url)[1]
                    if not extension:
                        extension = '.jpg'  # Default to jpg
                    
                    filename = f"ga_{self.page_type}_{idx:03d}{extension}"
                    filepath = os.path.join(output_path, filename)
                    
                    # Download the file with special Google Arts headers
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                        'Referer': 'https://artsandculture.google.com/',
                        'Accept': 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8',
                        'Accept-Language': 'en-US,en;q=0.9',
                        'Sec-Fetch-Dest': 'image',
                        'Sec-Fetch-Mode': 'no-cors',
                        'Sec-Fetch-Site': 'cross-site'
                    }
                    
                    # Get cookies from the page
                    cookies = await page.context.cookies()
                    cookie_str = '; '.join([f"{cookie['name']}={cookie['value']}" for cookie in cookies])
                    if cookie_str:
                        headers['Cookie'] = cookie_str
                    
                    # Make request with proper headers
                    response = requests.get(image_url, stream=True, timeout=30, headers=headers)
                    response.raise_for_status()
                    
                    # Save the file
                    with open(filepath, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            f.write(chunk)
                    
                    print(f"  Directly downloaded: {filename}")
                    downloaded_count += 1
                    
                    # Update stats
                    if stats is not None:
                        stats["downloads_succeeded_image"] = stats.get("downloads_succeeded_image", 0) + 1
                        stats["files_downloaded"] = stats.get("files_downloaded", 0) + 1
                    
                    # Save metadata
                    metadata = {
                        'filename': filename,
                        'url': image_url,
                        'title': item.get('title', ''),
                        'alt': item.get('alt', ''),
                        'credits': item.get('credits', ''),
                        'source_url': item.get('source_url', ''),
                        'type': 'image'
                    }
                    
                    # Save metadata file
                    meta_filepath = os.path.splitext(filepath)[0] + '.json'
                    with open(meta_filepath, 'w', encoding='utf-8') as f:
                        json.dump(metadata, f, indent=4)
                    
                except Exception as e:
                    print(f"  Error downloading item {idx}: {e}")
                    if stats is not None:
                        stats["failed_download"] = stats.get("failed_download", 0) + 1
            
            return downloaded_count
            
        except Exception as e:
            print(f"Error in direct download: {e}")
            traceback.print_exc()
            return 0

    async def _force_lazy_image_loading(self, page: AsyncPage):
        """Force lazy-loaded images to load"""
        try:
            await page.evaluate("""() => {
                // Approach 1: Convert data-src attributes to src
                document.querySelectorAll('img[data-src]:not([src]), [data-src]').forEach(img => {
                    if (img.dataset.src && (!img.src || img.src.includes('data:') || img.src.includes('placeholder'))) {
                        console.log(`Converting data-src to src: ${img.dataset.src.substring(0, 30)}...`);
                        img.src = img.dataset.src;
                    }
                });
                
                // Approach 2: Look for other data attributes
                const dataAttrs = ['data-delayed-src', 'data-lazy', 'data-original', 'data-url', 'data-img'];
                dataAttrs.forEach(attr => {
                    const selector = `img[${attr}], [${attr}]`;
                    document.querySelectorAll(selector).forEach(img => {
                        const dataSrc = img.getAttribute(attr);
                        if (dataSrc && (!img.src || img.src.includes('data:') || img.src.includes('placeholder'))) {
                            console.log(`Converting ${attr} to src: ${dataSrc.substring(0, 30)}...`);
                            img.src = dataSrc;
                        }
                    });
                });
                
                // Approach 3: Trigger IntersectionObserver callbacks
                const observer = new IntersectionObserver((entries) => {
                    entries.forEach(entry => {
                        if (entry.target.tagName === 'IMG') {
                            // Force load the image if it has data attributes
                            const img = entry.target;
                            if (img.dataset.src && !img.src) {
                                img.src = img.dataset.src;
                            }
                            
                            // Also dispatch intersection event
                            const event = new CustomEvent('lazyloaded');
                            img.dispatchEvent(event);
                        }
                    });
                });
                
                // Observe all images
                document.querySelectorAll('img').forEach(img => {
                    observer.observe(img);
                });
                
                // Approach 4: Trigger scroll events which often trigger lazy loading
                for (let i = 0; i < 3; i++) {
                    window.dispatchEvent(new Event('scroll'));
                    window.dispatchEvent(new Event('resize'));
                    window.dispatchEvent(new Event('mousemove'));
                }
                
                return true;
            }""")
            
            # Wait for images to load
            await page.wait_for_timeout(2000)
            
        except Exception as e:
            print(f"Error forcing lazy image loading: {e}")

    async def extract_with_direct_playwright_async(self, page: AsyncPage, **kwargs) -> list:
        """Async extraction using Playwright - Main entry point"""
        print(f"GoogleArtsHandler: Extracting via Direct Playwright Async for page type: {self.page_type}")
        
        # Initialize tracking to avoid duplicate processing
        if not hasattr(self, 'processed_image_urls'):
            self.processed_image_urls = set()

        # Initialize media items list
        media_items = []
        
        # Handle dynamic content loading before attempting extraction
        await self._handle_dynamic_content(page, **kwargs)
        
        # Start with specialized extraction based on page type
        try:
            if self.page_type == "artwork":
                media_items = await self._extract_artwork_image_async(page)
            elif self.page_type in ["entity", "partner"]:
                media_items = await self._extract_entity_images_async(page)
            elif self.page_type == "exhibit":
                media_items = await self._extract_exhibit_images_async(page)
            elif self.page_type in ["story", "project"]:
                media_items = await self._extract_story_images_async(page)
            else:
                media_items = await self._extract_generic_images_async(page)
        except Exception as e:
            print(f"Error in specialized extraction: {e}")
            traceback.print_exc()
        
        # If we didn't find anything with specialized extraction, try generic extraction
        if not media_items:
            print("No items found with specialized extraction, trying generic approach")
            try:
                media_items = await self._extract_generic_images_async(page)
            except Exception as e:
                print(f"Error in generic extraction: {e}")
                traceback.print_exc()
        
        # Filter out duplicates before post-processing
        unique_items = []
        for item in media_items:
            item_url = item.get('url', '')
            if item_url and item_url not in self.processed_image_urls:
                self.processed_image_urls.add(item_url)
                unique_items.append(item)

        # Process the media items
        processed_items = await self.post_process(media_items)
        print(f"Final processed items count: {len(processed_items)}")
        
        # Try direct download if items were found
        if processed_items and self.scraper and hasattr(self.scraper, 'output_path'):
            try:
                output_path = self.scraper.output_path
                stats = getattr(self.scraper, 'stats', None)
                direct_count = await self.direct_download_media(page, output_path, stats, **kwargs)
                if direct_count > 0:
                    print(f"Successfully directly downloaded {direct_count} items")
            except Exception as direct_err:
                print(f"Error during direct download attempt: {direct_err}")
        
        return processed_items

        
    
    async def _extract_artwork_image_async(self, page: AsyncPage) -> list:
        """Extract high-resolution image from a single artwork page"""
        media_items = []
        
        try:
            # Don't wait for specific selectors that might time out
            # Get artwork metadata using JavaScript detection
            artwork_data = await page.evaluate("""() => {
                // Function to safely query and extract text
                function getText(selector) {
                    const elem = document.querySelector(selector);
                    return elem ? elem.textContent.trim() : '';
                }
                
                // Get the title (try multiple selectors)
                const title = getText('h1') || 
                            getText('[data-test-id="title"]') || 
                            getText('[role="heading"]') ||
                            document.title;
                
                // Get artist (try multiple patterns)
                const artist = getText('[data-test-id="creator"]') || 
                            getText('.entity-link') ||
                            getText('a[href*="/entity/"]');
                
                // Get institution
                const institution = getText('[data-test-id="partner"]') ||
                                getText('.partner-name') ||
                                getText('a[href*="/partner/"]');
                
                // Get description
                const description = getText('[data-test-id="description"]') ||
                                getText('.artefact-description') ||
                                getText('article p');
                
                // Find the most likely main image
                let imgSrc = null;
                
                // First try the standard selectors
                const mainImgElement = document.querySelector('img[src*="googleusercontent.com"]');
                if (mainImgElement) {
                    imgSrc = mainImgElement.src;
                }
                
                // If no image found yet, check special structures
                if (!imgSrc) {
                    // Look for image containers with background images
                    document.querySelectorAll('div[style*="background-image"]').forEach(div => {
                        if (!imgSrc) {
                            const style = window.getComputedStyle(div);
                            if (style.backgroundImage && style.backgroundImage !== 'none') {
                                const match = style.backgroundImage.match(/url\\(['"]?(.*?)['"]?\\)/);
                                if (match && match[1] && match[1].includes('googleusercontent.com')) {
                                    imgSrc = match[1];
                                }
                            }
                        }
                    });
                }
                
                // Build and return the data
                return {
                    title,
                    artist,
                    institution,
                    description,
                    imgSrc
                };
            }""")
            
            if artwork_data.get('imgSrc'):
                # Get high-resolution version of the image
                high_res_url = self._convert_to_highest_res(artwork_data.get('imgSrc'))
                
                # Create a detailed attribution string
                attribution = artwork_data.get('artist', '')
                if artwork_data.get('institution'):
                    if attribution:
                        attribution += f", {artwork_data.get('institution')}"
                    else:
                        attribution = artwork_data.get('institution')
                
                media_items.append({
                    'url': high_res_url or artwork_data.get('imgSrc'),
                    'alt': artwork_data.get('title', ''),
                    'title': artwork_data.get('title', ''),
                    'description': artwork_data.get('description', ''),
                    'source_url': page.url,
                    'credits': attribution,
                    'type': 'image',
                    'category': 'artwork'
                })
            
        except Exception as e:
            print(f"Error extracting artwork with Playwright: {e}")
            traceback.print_exc()
            
            # Fallback: Try a more direct image search
            try:
                # Look for any Google-hosted images
                image_urls = await page.evaluate("""() => {
                    const images = [];
                    document.querySelectorAll('img').forEach(img => {
                        if (img.src && (img.src.includes('googleusercontent.com') || img.src.includes('ggpht.com'))) {
                            images.push({
                                src: img.src,
                                alt: img.alt || '',
                                width: img.naturalWidth || img.width || 0,
                                height: img.naturalHeight || img.height || 0
                            });
                        }
                    });
                    return images;
                }""")
                
                # Get the page title as fallback title
                page_title = await page.title()
                
                for img_data in image_urls:
                    high_res_url = self._convert_to_highest_res(img_data.get('src', ''))
                    
                    media_items.append({
                        'url': high_res_url,
                        'alt': img_data.get('alt', page_title),
                        'title': page_title or "Artwork from Google Arts & Culture",
                        'source_url': page.url,
                        'type': 'image',
                        'category': 'artwork_direct'
                    })
                    
            except Exception as fallback_err:
                print(f"Fallback extraction also failed: {fallback_err}")
        
        return media_items

    
    async def _extract_entity_images_async(self, page: AsyncPage) -> list:
        """Extract images from entity pages (artist, museum, etc.)"""
        media_items = []
        
        try:
            # Get entity name
            entity_name = await page.evaluate("""() => {
                const nameElem = document.querySelector('h1, h1.title, .entity-title, [data-test="entity-title"], .VFACy');
                return nameElem ? nameElem.textContent.trim() : '';
            }""")
            
            print(f"Extracting images for entity: {entity_name}")
            
            # Add a tracking set within this method to avoid duplicates
            extracted_image_urls = set()

            # IMPORTANT: Extract Gallery Items (Search Results) - This was missing!
            gallery_items = await page.evaluate("""() => {
                const results = [];
                
                // APPROACH 1: Gallery Items with PJLMUc class (most gallery images)
                document.querySelectorAll('.PJLMUc[data-bgsrc]').forEach(item => {
                    // Get data-bgsrc attribute which contains the original image URL
                    const bgsrc = item.getAttribute('data-bgsrc');
                    if (!bgsrc) return;
                    
                    // Create full URL if needed
                    const imgUrl = bgsrc.startsWith('//') ? 'https:' + bgsrc : bgsrc;
                    
                    // Get additional metadata
                    const title = item.getAttribute('title') || '';
                    const href = item.getAttribute('href') || '';
                    let fullHref = href;
                    if (href && href.startsWith('/')) {
                        fullHref = 'https://artsandculture.google.com' + href;
                    }
                    
                    // Add to results
                    results.push({
                        src: imgUrl,
                        title: title,
                        link: fullHref,
                        width: item.offsetWidth || 0,
                        height: item.offsetHeight || 0,
                        approach: 'gallery-item'
                    });
                    
                    // Also check if there's an inline style with background-image
                    const style = window.getComputedStyle(item);
                    if (style.backgroundImage && style.backgroundImage !== 'none') {
                        const match = style.backgroundImage.match(/url\\(['"]?(.*?)['"]?\\)/);
                        if (match && match[1]) {
                            results.push({
                                src: match[1],
                                title: title,
                                link: fullHref,
                                width: item.offsetWidth || 0,
                                height: item.offsetHeight || 0,
                                approach: 'inline-style'
                            });
                        }
                    }
                });
                
                // APPROACH 2: Specifically target gallery card items
                document.querySelectorAll('.e0WtYb, .kdYEFe, .ZEnmnd, .lXkFp, a[data-bgsrc]').forEach(item => {
                    const bgsrc = item.getAttribute('data-bgsrc');
                    if (!bgsrc) return;
                    
                    const imgUrl = bgsrc.startsWith('//') ? 'https:' + bgsrc : bgsrc;
                    const title = item.getAttribute('title') || '';
                    const href = item.getAttribute('href') || '';
                    let fullHref = href;
                    if (href && href.startsWith('/')) {
                        fullHref = 'https://artsandculture.google.com' + href;
                    }
                    
                    results.push({
                        src: imgUrl,
                        title: title,
                        link: fullHref,
                        width: item.offsetWidth || 0,
                        height: item.offsetHeight || 0,
                        approach: 'gallery-card'
                    });
                    
                    // Also get inline background image if available
                    const style = window.getComputedStyle(item);
                    if (style.backgroundImage && style.backgroundImage !== 'none') {
                        const match = style.backgroundImage.match(/url\\(['"]?(.*?)['"]?\\)/);
                        if (match && match[1]) {
                            results.push({
                                src: match[1],
                                title: title,
                                link: fullHref,
                                width: item.offsetWidth || 0,
                                height: item.offsetHeight || 0,
                                approach: 'card-inline-style'
                            });
                        }
                    }
                });
                
                // APPROACH 3: Target any element with background image and title attribute
                document.querySelectorAll('[style*="background-image"][title]').forEach(item => {
                    const style = window.getComputedStyle(item);
                    if (!style.backgroundImage || style.backgroundImage === 'none') return;
                    
                    const match = style.backgroundImage.match(/url\\(['"]?(.*?)['"]?\\)/);
                    if (match && match[1]) {
                        const imgUrl = match[1];
                        const title = item.getAttribute('title') || '';
                        const href = item.getAttribute('href') || '';
                        let fullHref = href;
                        if (href && href.startsWith('/')) {
                            fullHref = 'https://artsandculture.google.com' + href;
                        }
                        
                        results.push({
                            src: imgUrl,
                            title: title,
                            link: fullHref,
                            width: item.offsetWidth || 0,
                            height: item.offsetHeight || 0,
                            approach: 'bg-image-with-title'
                        });
                    }
                });
                
                return results;
            }""")
            
            if gallery_items:
                print(f"Found {len(gallery_items)} gallery items")
                
                # Process gallery items
                for item in gallery_items:
                    image_url = item.get('src', '')
                    if not image_url or image_url in extracted_image_urls:
                        continue
                    
                    # Add URL to tracking
                    extracted_image_urls.add(image_url)
                    
                    # Convert to high-res if it's a Google URL
                    if 'googleusercontent.com' in image_url or 'ggpht.com' in image_url:
                        high_res_url = self._convert_to_highest_res(image_url)
                    else:
                        high_res_url = image_url
                    
                    # Get title and URL
                    title = item.get('title', '') or f"Artwork from {entity_name}" if entity_name else "Google Arts & Culture"
                    source_url = item.get('link', '') or self.url
                    
                    media_items.append({
                        'url': high_res_url or image_url,
                        'alt': title,
                        'title': title,
                        'source_url': source_url,
                        'credits': entity_name or "Google Arts & Culture",
                        'type': 'image',
                        'category': 'entity_gallery_item',
                        'extraction_approach': item.get('approach', 'gallery')
                    })

            # Continue with the original image extraction logic for other types of images
            # (keeping existing code for standard images)
            
            # DEBUGGING: Take screenshot to see the page state
            if self.debug_mode:
                debug_dir = os.path.dirname(os.path.abspath(__file__))
                os.makedirs(os.path.join(debug_dir, "debug"), exist_ok=True)
                screenshot_path = os.path.join(debug_dir, "debug", "entity_page.png")
                await page.screenshot(path=screenshot_path, full_page=True)
                print(f"Debug screenshot saved to: {screenshot_path}")
                
                # Save HTML for inspection
                html_path = os.path.join(debug_dir, "debug", "entity_page.html")
                html_content = await page.content()
                with open(html_path, "w", encoding="utf-8") as f:
                    f.write(html_content)
                print(f"Debug HTML saved to: {html_path}")
            
            # More direct approach to find images in Google Arts pages
            image_data = await page.evaluate("""() => {
                const results = [];
                
                // Function to extract image URL and check if it's from Google
                function processImgElement(img) {
                    // Get image source with fallback to data-src
                    const src = img.src || img.getAttribute('data-src') || '';
                    
                    // Skip placeholder/tiny images
                    if (!src || 
                        src.includes('data:') || 
                        src.includes('placeholder') || 
                        src.includes('transparent.gif') ||
                        (img.width < 100 && img.height < 100)) {
                        return null;
                    }
                    
                    // Look for metadata in parent elements
                    let title = img.alt || '';
                    let caption = '';
                    let link = '';
                    
                    // Find a parent link
                    const parentLink = img.closest('a');
                    if (parentLink) {
                        link = parentLink.href;
                    }
                    
                    // Find parent container for metadata
                    const container = img.closest('div') || img.parentElement;
                    if (container) {
                        // Look for title/caption in siblings or children
                        const titleElem = container.querySelector('h1, h2, h3, h4, [role="heading"]') || 
                                        container.nextElementSibling?.querySelector('h1, h2, h3, h4, [role="heading"]');
                        if (titleElem) {
                            title = titleElem.textContent.trim();
                        }
                        
                        // Look for captions/subtitles
                        const captionElem = container.querySelector('p, .caption, .subtitle') ||
                                        container.nextElementSibling?.querySelector('p, .caption, .subtitle');
                        if (captionElem) {
                            caption = captionElem.textContent.trim();
                        }
                    }
                    
                    // Create result object
                    return {
                        src: src,
                        title: title || 'Untitled',
                        caption: caption,
                        link: link || window.location.href,
                        width: img.naturalWidth || img.width || 0,
                        height: img.naturalHeight || img.height || 0
                    };
                }
                
                // APPROACH 1: Find all substantial img elements
                document.querySelectorAll('img').forEach(img => {
                    const result = processImgElement(img);
                    if (result) {
                        results.push({...result, approach: 'direct-img'});
                    }
                });
                
                // APPROACH 2: Look for div elements with background-image style
                document.querySelectorAll('div[style*="background-image"], span[style*="background-image"]').forEach(div => {
                    const style = window.getComputedStyle(div);
                    const bgImage = style.backgroundImage;
                    
                    if (bgImage && bgImage !== 'none') {
                        // Extract URL from the background-image CSS
                        const urlMatch = bgImage.match(/url\\(['"]?(.*?)['"]?\\)/);
                        if (urlMatch && urlMatch[1] && !urlMatch[1].startsWith('data:')) {
                            // Create a result object with available info
                            const result = {
                                src: urlMatch[1],
                                title: div.getAttribute('aria-label') || div.textContent.trim() || 'Background Image',
                                caption: '',
                                link: window.location.href,
                                width: div.offsetWidth || 0,
                                height: div.offsetHeight || 0,
                                approach: 'background-image'
                            };
                            
                            results.push(result);
                        }
                    }
                });
                
                // APPROACH 3: Look for Google Arts specific structures
                const galleryItems = document.querySelectorAll('.gallery-item, [data-test-id="gallery-item"]');
                if (galleryItems.length > 0) {
                    galleryItems.forEach(item => {
                        // Look for image inside gallery item
                        const img = item.querySelector('img');
                        if (img) {
                            const result = processImgElement(img);
                            if (result) {
                                results.push({...result, approach: 'gallery-item'});
                            }
                        } else {
                            // Check for background image style
                            const style = window.getComputedStyle(item);
                            const bgImage = style.backgroundImage;
                            
                            if (bgImage && bgImage !== 'none') {
                                const urlMatch = bgImage.match(/url\\(['"]?(.*?)['"]?\\)/);
                                if (urlMatch && urlMatch[1] && !urlMatch[1].startsWith('data:')) {
                                    results.push({
                                        src: urlMatch[1],
                                        title: item.getAttribute('aria-label') || item.textContent.trim() || 'Gallery Item',
                                        caption: '',
                                        link: window.location.href,
                                        width: item.offsetWidth || 0,
                                        height: item.offsetHeight || 0,
                                        approach: 'gallery-background'
                                    });
                                }
                            }
                        }
                    });
                }
                
                // Additional specific checks for Google Arts & Culture structure
                document.querySelectorAll('[data-test-id="grid-item"]').forEach(item => {
                    // Look for image inside grid item
                    const img = item.querySelector('img');
                    if (img) {
                        const result = processImgElement(img);
                        if (result) {
                            results.push({...result, approach: 'grid-item'});
                        }
                    }
                });
                
                // Look through all divs for possible containers
                document.querySelectorAll('div').forEach(div => {
                    // Check if this div might be an image container
                    const children = div.children;
                    if (children.length >= 1 && children.length <= 5) {
                        const img = div.querySelector('img');
                        if (img) {
                            // This might be an item card - process it
                            const result = processImgElement(img);
                            if (result) {
                                results.push({...result, approach: 'possible-card'});
                            }
                        }
                    }
                });
                
                return results;
            }""")
            
            print(f"Found {len(image_data)} image items")
            
            # Process all found images
            for img in image_data:
                image_url = img.get('src', '')
                if not image_url:
                    continue
                    
                # Convert to high-res if it's a Google image
                if 'googleusercontent.com' in image_url or 'ggpht.com' in image_url:
                    high_res_url = self._convert_to_highest_res(image_url)
                else:
                    high_res_url = image_url
                    
                # Create title
                title = img.get('title', '') or (f"Artwork by {entity_name}" if entity_name else "Google Arts & Culture Artwork")
                
                # Create attribution
                attribution = img.get('caption', '')
                if entity_name and not attribution:
                    attribution = entity_name
                    
                media_items.append({
                    'url': high_res_url or image_url,
                    'alt': title,
                    'title': title,
                    'subtitle': img.get('caption', ''),
                    'source_url': img.get('link', self.url),
                    'credits': attribution,
                    'type': 'image',
                    'category': 'entity_artwork',
                    'extraction_approach': img.get('approach', 'unknown')
                })
        
        except Exception as e:
            print(f"Error extracting entity images with Playwright: {e}")
            traceback.print_exc()
        
        print(f"Entity extraction found {len(media_items)} images")
        return media_items
    
    async def _extract_exhibit_images_async(self, page: AsyncPage) -> list:
        """Extract images from exhibit pages"""
        media_items = []
        
        try:
            # Wait for content to load
            await page.wait_for_selector('.exhibit-content, .curated-content', timeout=self.timeout_ms)
            
            # Scroll through the exhibit to load all content
            await self._scroll_page_async(page, scroll_count=8, scroll_delay_ms=2000)
            
            # Get exhibit title
            exhibit_title = await page.evaluate("""() => {
                const titleElem = document.querySelector('h1.title, .exhibit-title');
                return titleElem ? titleElem.textContent.trim() : '';
            }""")
            
            # Get institution
            institution = await page.evaluate("""() => {
                const institutionElem = document.querySelector('.partner-name, .exhibit-partner');
                return institutionElem ? institutionElem.textContent.trim() : '';
            }""")
            
            # Extract all images from the exhibit
            image_data = await page.evaluate("""() => {
                const images = [];
                // First look for main exhibit images
                document.querySelectorAll('.exhibit-content img, .single-item-view img, .item-viewer img').forEach(img => {
                    const caption = img.closest('.single-item-view')?.querySelector('.title-text')?.textContent || '';
                    const credit = img.closest('.single-item-view')?.querySelector('.subtitle-text')?.textContent || '';
                    
                    images.push({
                        src: img.src,
                        dataSrc: img.getAttribute('data-src') || '',
                        caption: caption.trim(),
                        credit: credit.trim(),
                        type: 'main'
                    });
                });
                
                // Then look for thumbnails/cards
                document.querySelectorAll('.asset-card, .curated-content-card').forEach(card => {
                    const link = card.querySelector('a');
                    const img = card.querySelector('img');
                    const title = card.querySelector('.title-text, .asset-card-title');
                    const subtitle = card.querySelector('.subtitle-text, .asset-card-subtitle');
                    
                    if (img) {
                        images.push({
                            src: img.src,
                            dataSrc: img.getAttribute('data-src') || '',
                            caption: title ? title.textContent.trim() : '',
                            credit: subtitle ? subtitle.textContent.trim() : '',
                            href: link ? link.href : '',
                            type: 'thumbnail'
                        });
                    }
                });
                
                return images;
            }""")
            
            # Process each image
            for idx, img in enumerate(image_data):
                image_url = img.get('dataSrc') or img.get('src')
                if not image_url:
                    continue
                
                # Convert to high-res
                high_res_url = self._convert_to_highest_res(image_url)
                
                # Create a title
                title = img.get('caption', '')
                if not title:
                    title = f"{exhibit_title} - Item {idx+1}" if exhibit_title else f"Exhibit Item {idx+1}"
                
                # Create attribution
                attribution = img.get('credit', '')
                if institution and not attribution:
                    attribution = institution
                
                # Use the specific item link if available, otherwise the exhibit URL
                source_url = img.get('href', '') or self.url
                
                media_items.append({
                    'url': high_res_url or image_url,
                    'alt': title,
                    'title': title,
                    'source_url': source_url,
                    'credits': attribution,
                    'type': 'image',
                    'category': 'exhibit_item' if img.get('type') == 'main' else 'exhibit_thumbnail'
                })
        except Exception as e:
            if self.debug_mode:
                print(f"Error extracting exhibit images with Playwright: {e}")
        
        return media_items
    
    async def _extract_story_images_async(self, page: AsyncPage) -> list:
        """Extract images from story/project pages"""
        media_items = []
        
        try:
            # Wait for content to load
            await page.wait_for_selector('.story-content, .project-content', timeout=self.timeout_ms)
            
            # Scroll through the story to load all content
            await self._scroll_page_async(page, scroll_count=10, scroll_delay_ms=1500)
            
            # Get story title
            story_title = await page.evaluate("""() => {
                const titleElem = document.querySelector('h1.title, .story-title');
                return titleElem ? titleElem.textContent.trim() : '';
            }""")
            
            # Extract all images from the story
            image_data = await page.evaluate("""() => {
                const images = [];
                // Look for all images in the story content
                document.querySelectorAll('.story-content img, .project-content img, .story-image').forEach((img, index) => {
                    // Try to find caption
                    let caption = '';
                    const captionElem = img.closest('figure')?.querySelector('figcaption') || 
                                       img.parentElement?.nextElementSibling?.querySelector('.caption') ||
                                       img.closest('.item-view')?.querySelector('.caption');
                    
                    if (captionElem) {
                        caption = captionElem.textContent.trim();
                    }
                    
                    images.push({
                        src: img.src,
                        dataSrc: img.getAttribute('data-src') || '',
                        caption: caption,
                        index: index
                    });
                });
                
                return images;
            }""")
            
            # Process each image
            for img in image_data:
                image_url = img.get('dataSrc') or img.get('src')
                if not image_url:
                    continue
                
                # Convert to high-res
                high_res_url = self._convert_to_highest_res(image_url)
                
                # Create a title
                title = img.get('caption', '')
                if not title:
                    idx = img.get('index', 0) + 1
                    title = f"{story_title} - Image {idx}" if story_title else f"Story Image {idx}"
                
                media_items.append({
                    'url': high_res_url or image_url,
                    'alt': title,
                    'title': title,
                    'source_url': self.url,
                    'type': 'image',
                    'category': 'story_image'
                })
        except Exception as e:
            if self.debug_mode:
                print(f"Error extracting story images with Playwright: {e}")
        
        return media_items

    async def _extract_last_resort_async(self, page: AsyncPage) -> list:
        """Last resort extraction method that tries to find any images on the page"""
        print("Attempting last resort extraction...")
        media_items = []
        
        try:
            # Save debug files first
            if self.debug_mode:
                debug_dir = os.path.dirname(os.path.abspath(__file__))
                os.makedirs(os.path.join(debug_dir, "debug"), exist_ok=True)
                
                screenshot_path = os.path.join(debug_dir, "debug", f"last_resort_{int(time.time())}.png")
                await page.screenshot(path=screenshot_path, full_page=True)
                print(f"Debug screenshot saved to: {screenshot_path}")
                
                html_path = os.path.join(debug_dir, "debug", f"last_resort_{int(time.time())}.html")
                with open(html_path, "w", encoding="utf-8") as f:
                    f.write(await page.content())
                print(f"Debug HTML saved to: {html_path}")
            
            # Use a very broad JavaScript approach to find anything that might be an image
            all_images = await page.evaluate("""() => {
                const allSources = [];
                
                // 1. Get all standard image elements
                document.querySelectorAll('img').forEach(img => {
                    if (img.src && img.src !== 'data:' && !img.src.startsWith('data:')) {
                        allSources.push({
                            type: 'standard',
                            url: img.src,
                            alt: img.alt || '',
                            width: img.naturalWidth || img.width || 0,
                            height: img.naturalHeight || img.height || 0
                        });
                    }
                    
                    // Check data-src attributes
                    if (img.dataset && img.dataset.src) {
                        allSources.push({
                            type: 'data-src',
                            url: img.dataset.src,
                            alt: img.alt || '',
                            width: img.naturalWidth || img.width || 0,
                            height: img.naturalHeight || img.height || 0
                        });
                    }
                });
                
                // 2. Get background images from divs
                document.querySelectorAll('div[style*="background-image"], span[style*="background-image"]').forEach(el => {
                    const style = window.getComputedStyle(el);
                    const bgImage = style.backgroundImage;
                    
                    if (bgImage && bgImage !== 'none') {
                        // Extract URL from the background-image CSS
                        const urlMatch = bgImage.match(/url\\(['"]?(.*?)['"]?\\)/);
                        if (urlMatch && urlMatch[1] && !urlMatch[1].startsWith('data:')) {
                            allSources.push({
                                type: 'background',
                                url: urlMatch[1],
                                alt: el.getAttribute('aria-label') || '',
                                width: el.offsetWidth || 0,
                                height: el.offsetHeight || 0
                            });
                        }
                    }
                });
                
                // 3. Check for image URLs in data attributes
                document.querySelectorAll('[data-image-url], [data-url], [data-img]').forEach(el => {
                    const dataUrl = el.dataset.imageUrl || el.dataset.url || el.dataset.img;
                    if (dataUrl && !dataUrl.startsWith('data:')) {
                        allSources.push({
                            type: 'data-attribute',
                            url: dataUrl,
                            alt: el.getAttribute('aria-label') || el.textContent || '',
                            width: 0,
                            height: 0
                        });
                    }
                });
                
                // 4. Look for Google Arts specific structures
                // Sometimes image URLs are in JSON strings within data attributes
                document.querySelectorAll('[data-values], [data-json], [data-initial-data]').forEach(el => {
                    const attrs = el.attributes;
                    for (let i = 0; i < attrs.length; i++) {
                        const attr = attrs[i];
                        if (attr.name.startsWith('data-') && attr.value.includes('"url"')) {
                            try {
                                // Try to parse JSON or extract URL
                                let jsonStr = attr.value;
                                
                                // Extract URLs from the attribute value
                                const urlMatches = jsonStr.match(/"url"\\s*:\\s*"([^"]+)"/g);
                                if (urlMatches) {
                                    urlMatches.forEach(match => {
                                        const url = match.split(':"')[1].replace('"', '');
                                        if (url && !url.startsWith('data:')) {
                                            allSources.push({
                                                type: 'json-data',
                                                url: url,
                                                alt: '',
                                                width: 0,
                                                height: 0
                                            });
                                        }
                                    });
                                }
                            } catch (e) {
                                // Skip parsing errors
                                console.error("Error parsing JSON in data attribute:", e);
                            }
                        }
                    }
                });
                
                // Filter to likely Google Arts image URLs and remove duplicates
                const googleDomains = ['googleusercontent.com', 'gstatic.com', 'ggpht.com'];
                const uniqueUrls = new Map();
                
                allSources.forEach(source => {
                    // Only keep Google domains or .jpg/png URLs
                    const isGoogleUrl = googleDomains.some(domain => source.url.includes(domain));
                    const isImageUrl = /\\.(jpg|jpeg|png|gif|webp)\\b/i.test(source.url);
                    
                    if (isGoogleUrl || isImageUrl) {
                        // Use URL as key to prevent duplicates
                        if (!uniqueUrls.has(source.url)) {
                            uniqueUrls.set(source.url, source);
                        }
                    }
                });
                
                return Array.from(uniqueUrls.values());
            }""")
            
            print(f"Last resort extraction found {len(all_images)} image sources")
            
            # Current page URL for source
            page_url = page.url
            
            # Get entity name if available
            entity_name = await page.evaluate("""() => {
                const nameElem = document.querySelector('h1, h1.title, .entity-title, [data-test="entity-title"], .VFACy');
                return nameElem ? nameElem.textContent.trim() : '';
            }""")
            
            # Process each found image
            for idx, img in enumerate(all_images):
                image_url = img.get('url', '')
                if not image_url:
                    continue
                
                # Convert to high-res
                high_res_url = self._convert_to_highest_res(image_url)
                
                # Create a title based on available information
                title = img.get('alt', '') or f"Google Arts Image {idx+1}"
                if entity_name:
                    title = f"{entity_name} - {title}"
                
                media_items.append({
                    'url': high_res_url or image_url,
                    'alt': img.get('alt', ''),
                    'title': title,
                    'source_url': page_url,
                    'credits': entity_name or "Google Arts & Culture",
                    'type': 'image',
                    'category': 'direct_scan',
                    'width': img.get('width', 0),
                    'height': img.get('height', 0),
                    'extraction_type': img.get('type', 'unknown')
                })
        
        except Exception as e:
            print(f"Error during last resort extraction: {e}")
            traceback.print_exc()
        
        return media_items

    async def _extract_generic_images_async(self, page: AsyncPage) -> list:
        """Generic extraction for any Google Arts & Culture page type"""
        media_items = []
        
        try:
            # Load images that might be lazy-loaded by scrolling
            await self._scroll_page_async(page, scroll_count=5, scroll_delay_ms=1000)
            
            # Try specialized selectors for Google Arts & Culture
            image_selectors = [
                'img.hero-image',
                'img.item-image',
                '.asset img',
                '.item-content img',
                '.item-viewer img',
                '.story-content img',
                '.exhibit-content img',
                'img[src*="googleusercontent.com"]',
                'img[data-src*="googleusercontent.com"]'
            ]
            
            # Process each selector
            for selector in image_selectors:
                try:
                    # Count images matching this selector
                    count = await page.locator(selector).count()
                    if count > 0:
                        print(f"Found {count} images with selector: {selector}")
                        
                        # Process each image
                        for i in range(count):
                            try:
                                # Get specific image
                                img = page.locator(selector).nth(i)
                                is_visible = await img.is_visible(timeout=300)
                                if not is_visible:
                                    continue
                                
                                # Extract image URL
                                src = await img.get_attribute('src')
                                if not src or not ('googleusercontent.com' in src):
                                    continue
                                
                                # Convert to high-res
                                high_res_url = self._convert_to_highest_res(src)
                                
                                # Get metadata 
                                alt = await img.get_attribute('alt') or ""
                                
                                # Add to media items
                                media_items.append({
                                    'url': high_res_url,
                                    'alt': alt,
                                    'title': alt or "Google Arts & Culture Image",
                                    'source_url': page.url,
                                    'type': 'image',
                                    'platform': 'google_arts_culture'
                                })
                            except Exception as img_error:
                                print(f"Error processing image {i}: {img_error}")
                                continue
                except Exception as selector_error:
                    print(f"Error with selector '{selector}': {selector_error}")
                    continue
                
                # If we found items with this selector, we can stop
                if media_items:
                    break
            
            # If we still don't have images, use JavaScript to extract them
            if not media_items:
                print("Trying JavaScript-based image extraction")
                
                # Run JavaScript to extract all substantial images
                js_images = await page.evaluate("""() => {
                    const images = [];
                    document.querySelectorAll('img').forEach(img => {
                        // Only get substantial images
                        if ((img.width >= 200 || img.height >= 200) && 
                            (img.src && (img.src.includes('googleusercontent.com') || img.src.includes('ggpht.com')))) {
                            
                            // Try to get any text context
                            const parent = img.closest('.item-content') || img.closest('figure') || 
                                        img.closest('.asset') || img.parentElement;
                            
                            let title = '';
                            let caption = '';
                            
                            if (parent) {
                                // Look for title/caption nearby
                                const titleElem = parent.querySelector('.title, h2, h3');
                                if (titleElem) title = titleElem.textContent.trim();
                                
                                const captionElem = parent.querySelector('.caption, .description');
                                if (captionElem) caption = captionElem.textContent.trim();
                            }
                            
                            images.push({
                                src: img.src,
                                width: img.width,
                                height: img.height,
                                alt: img.alt || '',
                                title: title,
                                caption: caption
                            });
                        }
                    });
                    return images;
                }""")
                
                for img_data in js_images:
                    src = img_data.get('src')
                    if not src:
                        continue
                    
                    high_res_url = self._convert_to_highest_res(src)
                    
                    # Build title from available info
                    title = img_data.get('title') or img_data.get('alt') or "Google Arts & Culture Image"
                    
                    media_items.append({
                        'url': high_res_url,
                        'alt': img_data.get('alt', ''),
                        'title': title,
                        'description': img_data.get('caption', ''),
                        'source_url': page.url,
                        'width': img_data.get('width', 0),
                        'height': img_data.get('height', 0),
                        'type': 'image',
                        'platform': 'google_arts_culture'
                    })
        except Exception as e:
            print(f"Error during generic extraction: {e}")
            import traceback
            traceback.print_exc()
        
        # If in debug mode and we found nothing, take a screenshot
        if not media_items and self.debug_mode:
            try:
                debug_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug")
                os.makedirs(debug_dir, exist_ok=True)
                screen_path = os.path.join(debug_dir, f"google_arts_{self.page_type}_{int(time.time())}.png")
                await page.screenshot(path=screen_path, full_page=True)
                print(f"Saved debug screenshot to {screen_path}")
                
                # Also save page HTML for further debugging
                html_path = os.path.join(debug_dir, f"google_arts_{self.page_type}_{int(time.time())}.html") 
                with open(html_path, 'w', encoding='utf-8') as f:
                    f.write(await page.content())
                print(f"Saved debug HTML to {html_path}")
            except Exception as e:
                print(f"Failed to save debug files: {e}")
        
        return media_items

    async def _scroll_page_async(self, page: AsyncPage, scroll_count=6, scroll_delay_ms=1500):
        """Scroll down the page to load more content - async version"""
        if not page:
            return
        
        try:
            print(f"Scrolling page ({scroll_count} times, {scroll_delay_ms}ms delay)...")
            initial_height = await page.evaluate('() => document.body.scrollHeight')
            initial_image_count = await page.evaluate('() => document.querySelectorAll("img").length')
            consecutive_unchanged = 0
            
            for i in range(scroll_count):
                # Scroll to bottom
                await page.evaluate('() => window.scrollTo(0, document.body.scrollHeight)')
                
                # Wait for content to load
                await page.wait_for_timeout(scroll_delay_ms)
                
                # Check if more content was loaded
                new_height = await page.evaluate('() => document.body.scrollHeight')
                new_image_count = await page.evaluate('() => document.querySelectorAll("img").length')
                
                if new_height == initial_height and new_image_count == initial_image_count:
                    consecutive_unchanged += 1
                    
                    # Stop if nothing changed for 2 consecutive scrolls
                    if consecutive_unchanged >= 2:
                        # Try clicking "Load More" if it exists
                        try:
                            load_more_button = await page.evaluate("""() => {
                                // Common load more button selectors
                                const selectors = [
                                    'button:has-text("Load More")', 
                                    '.load-more', 
                                    'button:has-text("Show more")',
                                    '[aria-label="Show more"]',
                                    'button.show-more'
                                ];
                                
                                for (const selector of selectors) {
                                    const el = document.querySelector(selector);
                                    if (el && el.offsetParent !== null) {  // Check if visible
                                        el.click();
                                        return true;
                                    }
                                }
                                return false;
                            }""")
                            
                            if load_more_button:
                                print("Clicked 'Load More' button")
                                await page.wait_for_timeout(scroll_delay_ms * 2)
                                consecutive_unchanged = 0  # Reset counter after clicking
                            else:
                                print(f"No more content loaded after {consecutive_unchanged} scrolls, stopping")
                                break
                        except Exception as click_err:
                            print(f"Error clicking load more: {click_err}")
                            break
                else:
                    # Content changed, reset counter
                    consecutive_unchanged = 0
                    initial_height = new_height
                    initial_image_count = new_image_count
                    print(f"Scroll {i+1}: Found {new_image_count} images")
            
            # Final content check
            final_image_count = await page.evaluate('() => document.querySelectorAll("img").length')
            print(f"Finished scrolling: Found {final_image_count} image elements")
            
            # Help load lazy images
            await page.evaluate("""() => {
                const observer = new IntersectionObserver((entries) => {
                    entries.forEach(entry => {
                        if (entry.isIntersecting) {
                            const img = entry.target;
                            if (img.dataset.src && !img.src) {
                                img.src = img.dataset.src;
                            }
                        }
                    });
                });
                
                document.querySelectorAll('img[data-src]').forEach(img => {
                    observer.observe(img);
                });
            }""")
            
            # Wait a moment for lazy loading to finish
            await page.wait_for_timeout(1000)
            
        except Exception as e:
            print(f"Error during page scrolling: {e}")
            traceback.print_exc()

    # Keep helper methods exactly as is, as they don't need async conversion
    def _convert_to_highest_res(self, url):
        """Convert a Google Arts & Culture image URL to highest resolution version"""
        if not url:
            return url
            
        # Check if this is a Google image URL
        google_domains = ['googleusercontent.com', 'gstatic.com', 'ggpht.com']
        is_google_url = any(domain in url for domain in google_domains)
        
        if not is_google_url:
            return url
            
        # Decode any Unicode escape sequences (like \u003d which is =)
        url = url.replace('\\u003d', '=').replace('\u003d', '=')
        
        # Skip encrypted thumbnail URLs as they can't be converted to high-res
        if 'encrypted-tbn' in url:
            return None  # Skip these thumbnails
        
        # Check if there's already a size parameter
        if '=s' in url or '=w' in url:
            # Remove existing size parameters
            base_url = re.sub(r'=[swh]\d+.*$', '', url)
        else:
            # Remove any existing parameters after the first =
            parts = url.split('=', 1)
            base_url = parts[0]
        
        # Handle the case where the URL might already have query parameters
        if '?' in base_url:
            parts = base_url.split('?')
            base_url = parts[0]
            
        # Add parameters for high resolution
        high_res_url = f"{base_url}=w3000-h3000"
        
        # Debug
        if self.debug_mode:
            print(f"Converted URL: {url} -> {high_res_url}")
        
        return high_res_url

    def _get_page_content(self, page) -> str:
        """Get HTML content from page object - async compatible"""
        html_content = ""
        
        # Try alternate methods to get content
        if hasattr(page, 'html_content'):
            return page.html_content
        elif hasattr(page, 'text'):
            return page.text
        else:
            return str(page)

    async def post_process(self, media_items):
        """Clean and enhance the extracted media items - async version"""
        if not media_items:
            return media_items
        
        processed_items = []

        seen_urls = set()
        # Track normalized versions of URLs
        seen_normalized_urls = set()

        for item in media_items:
            url = item.get('url')
            if not url:
                continue
            
            # Clean URL
            clean_url = url.split('?')[0].split('#')[0].strip()

            # Create a normalized version for better deduplication
            # For Google Arts, the key is often in the base part before any size parameters
            base_url = clean_url.split('=')[0] if '=' in clean_url else clean_url
            
            # Skip duplicates by comparing the base URL
            if base_url in seen_normalized_urls:
                continue
            
            # Update URL and add to processed items
            item['url'] = clean_url
            seen_urls.add(clean_url)
            seen_normalized_urls.add(base_url)
            
            # Ensure proper credits format
            if item.get('credits') and 'google arts' not in item.get('credits', '').lower():
                if 'via' not in item.get('credits', '').lower() and 'from' not in item.get('credits', '').lower():
                    item['credits'] = f"{item['credits']} via Google Arts & Culture"
            
            # Ensure title is present
            if not item.get('title'):
                item['title'] = "Artwork from Google Arts & Culture"
            
            # Ensure source URL is present
            if not item.get('source_url'):
                item['source_url'] = self.url
                
            # Add debug info
            if self.debug_mode:
                print(f"Processing item: {item['url'][:50]}...")
            
            processed_items.append(item)
        
        print(f"Post-process: input={len(media_items)}, output={len(processed_items)} items")
        return processed_items


    def prefers_api(self) -> bool:
        """
        This handler could use API extraction if credentials are available.
        """
        return hasattr(self, 'api_available') and self.api_available
