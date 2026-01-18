"""
ModelMayhem Handler

Description: Handler for ModelMayhem.com portfolio/photo galleries
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
ModelMayhem-specific handler for the Web Image Scraper
Extracts full-resolution images from ModelMayhem portfolios

URL patterns:
- Profile: https://www.modelmayhem.com/4554791
- Portfolio (all): https://www.modelmayhem.com/portfolio/4554791/viewall
- Single photo: https://www.modelmayhem.com/portfolio/pic/48745727
- Photo CDN: https://photos.modelmayhem.com/photos/251111/17/6913e94c8f27f.jpg
"""

from site_handlers.base_handler import BaseSiteHandler
from urllib.parse import urlparse, urljoin
from typing import List, Dict, Any, Optional
import re
import json
import time
import asyncio
import traceback

# Playwright (async) – load only if available
try:
    from playwright.async_api import Page as AsyncPage
    from playwright.async_api import Browser, BrowserContext
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    AsyncPage = None
    Browser = None
    BrowserContext = None
    PLAYWRIGHT_AVAILABLE = False


class ModelMayhemHandler(BaseSiteHandler):
    """Handler for ModelMayhem.com portfolio sites"""
    
    # Class attributes for configuration
    PRIORITY = 40  # Higher priority for this specific handler
    
    # Domains associated with ModelMayhem
    DOMAINS = [
        "modelmayhem.com",
        "www.modelmayhem.com",
        "m.modelmayhem.com",
        "secure.modelmayhem.com",
        "m.secure.modelmayhem.com",
        "photos.modelmayhem.com"
    ]
    
    @classmethod
    def can_handle(cls, url: str) -> bool:
        """Check if this handler can process the URL"""
        url_lower = url.lower()
        for domain in cls.DOMAINS:
            if domain in url_lower:
                return True
        return False
    
    def __init__(self, url, scraper=None):
        super().__init__(url, scraper)
        # Configuration defaults
        self.max_scroll_count = 15
        self.scroll_delay_ms = 1500
        self.use_stealth_mode = True
        self.retry_attempts = 2
        self.dynamic_content_wait_ms = 2000
        self.request_delay_ms = 1000
        self.last_request_time = 0
        
        # Track state
        self.is_logged_in = False
        self.extracted_media_cache = {}
        self.seen_urls = set()
        self._username_to_resolve = None  # For username-based URLs that need numeric ID resolution
        
        # Load credentials from auth config
        self._load_api_credentials()
        
        print(f"ModelMayhemHandler initialized for URL: {url}")
    
    def get_trusted_domains(self) -> List[str]:
        """Return list of trusted CDN domains for ModelMayhem"""
        return [
            "photos.modelmayhem.com",      # Main photo CDN
            "assets.modelmayhem.com",       # Assets CDN
            "modelmayhem.com",              # Main domain
            "cloudfront.net"                # Potential CDN
        ]
    
    def _load_api_credentials(self):
        """Load credentials from the auth_config if available"""
        self.username = None
        self.password = None
        
        if not hasattr(self, 'scraper') or not self.scraper:
            return
            
        if not hasattr(self.scraper, 'auth_config') or not self.scraper.auth_config:
            return
            
        auth_config = self.scraper.auth_config
        
        # Try multiple domain variations
        domains_to_try = [
            "modelmayhem.com",
            "www.modelmayhem.com",
            "secure.modelmayhem.com"
        ]
        
        domain_config = None
        
        # Look in 'sites' section first
        if 'sites' in auth_config:
            for domain in domains_to_try:
                if domain in auth_config['sites']:
                    domain_config = auth_config['sites'][domain]
                    print(f"ModelMayhemHandler: Found auth config for {domain}")
                    break
        
        # Also try directly in the config (older format)
        if not domain_config:
            for domain in domains_to_try:
                if domain in auth_config:
                    domain_config = auth_config[domain]
                    print(f"ModelMayhemHandler: Found auth config (legacy) for {domain}")
                    break
        
        if domain_config:
            self.username = domain_config.get('username')
            self.password = domain_config.get('password')
            # Load additional config if available
            if 'max_scroll_count' in domain_config:
                self.max_scroll_count = domain_config.get('max_scroll_count')
            if 'scroll_delay_ms' in domain_config:
                self.scroll_delay_ms = domain_config.get('scroll_delay_ms')
            if self.username:
                print(f"ModelMayhemHandler: Loaded credentials for user {self.username}")
    
    def prefers_api(self) -> bool:
        """This handler doesn't use APIs, it scrapes the web pages"""
        return False
    
    def requires_api(self) -> bool:
        """This handler doesn't require API access"""
        return False
    
    async def _perform_login(self, page) -> bool:
        """Perform login to ModelMayhem if credentials are available"""
        if not self.username or not self.password:
            print("ModelMayhemHandler: No credentials available, continuing without login")
            return False
        
        if self.is_logged_in:
            return True
        
        try:
            print(f"ModelMayhemHandler: Attempting login as {self.username}")
            
            # Navigate to login page - use domcontentloaded for faster loading
            await page.goto("https://www.modelmayhem.com/login", wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(3)
            
            # Check if already logged in by looking for user menu or login form
            is_logged_in_already = await page.evaluate('''
                () => {
                    // Check for signs of being logged in
                    const userMenu = document.querySelector('.user-menu, .logged-in, [data-user], .account-menu');
                    const loginForm = document.querySelector('form[action*="login"], #login-form, .login-form');
                    return userMenu !== null || loginForm === null;
                }
            ''')
            
            if is_logged_in_already:
                print("ModelMayhemHandler: Already logged in")
                self.is_logged_in = True
                return True
            
            # Fill in login form
            # Try multiple selector patterns for username field
            username_selectors = [
                'input[name="username"]',
                'input[name="email"]',
                'input[type="email"]',
                '#username',
                '#email',
                'input[placeholder*="mail"]',
                'input[placeholder*="user"]'
            ]
            
            for selector in username_selectors:
                try:
                    username_field = await page.query_selector(selector)
                    if username_field:
                        await username_field.fill(self.username)
                        print(f"ModelMayhemHandler: Filled username field using selector: {selector}")
                        break
                except:
                    continue
            
            # Try multiple selector patterns for password field
            password_selectors = [
                'input[name="password"]',
                'input[type="password"]',
                '#password'
            ]
            
            for selector in password_selectors:
                try:
                    password_field = await page.query_selector(selector)
                    if password_field:
                        await password_field.fill(self.password)
                        print(f"ModelMayhemHandler: Filled password field using selector: {selector}")
                        break
                except:
                    continue
            
            # Submit login form
            submit_selectors = [
                'button[type="submit"]',
                'input[type="submit"]',
                'button:has-text("Log In")',
                'button:has-text("Sign In")',
                '.login-button',
                '#login-submit'
            ]
            
            for selector in submit_selectors:
                try:
                    submit_button = await page.query_selector(selector)
                    if submit_button:
                        await submit_button.click()
                        print(f"ModelMayhemHandler: Clicked submit using selector: {selector}")
                        break
                except:
                    continue
            
            # Wait for navigation/login to complete
            await asyncio.sleep(3)
            
            # Verify login succeeded
            current_url = page.url
            if "login" not in current_url.lower():
                print("ModelMayhemHandler: Login successful")
                self.is_logged_in = True
                return True
            else:
                print("ModelMayhemHandler: Login may have failed, continuing anyway")
                return False
                
        except Exception as e:
            print(f"ModelMayhemHandler: Login error: {e}")
            traceback.print_exc()
            return False
    
    def _normalize_portfolio_url(self, url: str) -> str:
        """Convert any ModelMayhem URL to the portfolio viewall URL"""
        # Extract user ID or username from various URL patterns
        patterns = [
            # Numeric ID patterns
            (r'modelmayhem\.com/portfolio/(\d+)/viewall', r'\1', True),  # Already viewall: /portfolio/4554791/viewall
            (r'modelmayhem\.com/portfolio/(\d+)', r'\1', True),  # Portfolio URL: /portfolio/4554791
            (r'modelmayhem\.com/(\d+)', r'\1', True),  # Profile URL with ID: /4554791
            # Username patterns (alphanumeric, may include underscores)
            (r'modelmayhem\.com/portfolio/([a-zA-Z][a-zA-Z0-9_]+)/viewall', r'\1', False),  # Already viewall with username
            (r'modelmayhem\.com/portfolio/([a-zA-Z][a-zA-Z0-9_]+)', r'\1', False),  # Portfolio with username
            (r'modelmayhem\.com/([a-zA-Z][a-zA-Z0-9_]+)(?:/|$)', r'\1', False),  # Profile URL with username: /albertobevacqua
        ]
        
        for pattern, group, is_numeric in patterns:
            match = re.search(pattern, url)
            if match:
                user_id = match.group(1)
                # Skip if it matches a reserved path
                if user_id.lower() in ['portfolio', 'login', 'signup', 'search', 'browse', 'help', 'about', 'contact', 'terms', 'privacy', 'pic']:
                    continue
                    
                # For username-based URLs, we need to visit the profile page first to get the numeric ID
                # Store the username for later resolution
                if not is_numeric:
                    self._username_to_resolve = user_id
                    # Return profile URL - we'll resolve to numeric ID in extract_with_direct_playwright
                    result_url = f"https://www.modelmayhem.com/{user_id}"
                    print(f"ModelMayhemHandler: Username URL detected, will resolve numeric ID from profile: {result_url}")
                    return result_url
                    
                result_url = f"https://www.modelmayhem.com/portfolio/{user_id}/viewall"
                print(f"ModelMayhemHandler: Normalized URL to {result_url}")
                return result_url
        
        # If it's already a pic URL, just return it
        if '/portfolio/pic/' in url:
            return url
        
        # Last resort: return the URL with /viewall appended if it looks like a profile
        print(f"ModelMayhemHandler: Could not normalize URL, using as-is: {url}")
        return url
    
    def _upgrade_thumbnail_to_full_res(self, url: str) -> str:
        """
        Convert a ModelMayhem thumbnail URL to full resolution.
        
        ModelMayhem URL patterns:
        - Thumbnail: https://photos.modelmayhem.com/photos/251111/17/6913e94c8f27f_m.jpg
        - Full res:  https://photos.modelmayhem.com/photos/251111/17/6913e94c8f27f.jpg
        
        The _m suffix indicates medium thumbnail. Remove it for full resolution.
        """
        if not url:
            return url
        
        # Remove thumbnail suffixes (_m, _s, _t) before the extension
        # Pattern: filename_X.ext -> filename.ext where X is m, s, or t
        upgraded = re.sub(r'_[mst]\.([a-zA-Z]+)$', r'.\1', url)
        
        if upgraded != url:
            print(f"ModelMayhemHandler: Upgraded URL: {url} -> {upgraded}")
        
        return upgraded
    
    async def _verify_and_get_best_url(self, page, thumbnail_url: str, verbose: bool = False) -> tuple[str, str]:
        """
        Verify if the full-res URL exists, fall back to thumbnail if not.
        
        Returns:
            tuple: (best_url, original_thumbnail_or_none)
            - best_url: The URL that should be used for download
            - original_thumbnail_or_none: The thumbnail URL if different from best_url, else None
        """
        full_res_url = self._upgrade_thumbnail_to_full_res(thumbnail_url)
        
        # If no upgrade happened (URL stayed the same), just use it
        if full_res_url == thumbnail_url:
            return (thumbnail_url, None)
        
        # Verify the full-res URL exists
        try:
            response = await page.context.request.head(full_res_url, headers={
                'Referer': 'https://www.modelmayhem.com/',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
            })
            
            if response.status < 400:
                # Full-res URL exists, use it with thumbnail as fallback
                if verbose:
                    print(f"ModelMayhemHandler: Full-res URL verified: {full_res_url}")
                return (full_res_url, thumbnail_url)
            else:
                # Full-res URL doesn't exist, use thumbnail instead
                if verbose:
                    print(f"ModelMayhemHandler: Full-res URL returned {response.status}, falling back to thumbnail: {thumbnail_url}")
                return (thumbnail_url, None)
                
        except Exception as e:
            # On error, use thumbnail as safe fallback
            if verbose:
                print(f"ModelMayhemHandler: Error verifying full-res URL ({e}), using thumbnail: {thumbnail_url}")
            return (thumbnail_url, None)
    
    async def extract_with_direct_playwright(self, page, **kwargs) -> List[Dict[str, Any]]:
        """Main extraction method using Playwright"""
        print(f"ModelMayhemHandler: Starting extraction from {self.url}")
        start_time = time.time()
        media_items = []
        
        try:
            # First, normalize the URL and check if we need to resolve a username
            target_url = self._normalize_portfolio_url(self.url)
            
            # Attempt login first if we have credentials
            await self._perform_login(page)
            
            # If we have a username to resolve, go to profile page first to get numeric ID
            if self._username_to_resolve:
                print(f"ModelMayhemHandler: Navigating to profile page to resolve username: {target_url}")
                try:
                    # Use domcontentloaded instead of networkidle for faster loading
                    await page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
                    await asyncio.sleep(3)  # Give extra time for dynamic content
                except Exception as e:
                    print(f"ModelMayhemHandler: Navigation timeout, retrying with load event: {e}")
                    await page.goto(target_url, wait_until="load", timeout=60000)
                    await asyncio.sleep(3)
                
                numeric_id = await self._resolve_numeric_id_from_profile(page)
                if numeric_id:
                    target_url = f"https://www.modelmayhem.com/portfolio/{numeric_id}/viewall"
                    print(f"ModelMayhemHandler: Resolved username '{self._username_to_resolve}' to numeric ID {numeric_id}")
                else:
                    print(f"ModelMayhemHandler: Could not resolve numeric ID for username '{self._username_to_resolve}'")
                    return media_items
            
            # Navigate to the portfolio page
            print(f"ModelMayhemHandler: Navigating to portfolio: {target_url}")
            try:
                await page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
                await asyncio.sleep(3)
            except Exception as e:
                print(f"ModelMayhemHandler: Navigation timeout, retrying with load event: {e}")
                await page.goto(target_url, wait_until="load", timeout=60000)
                await asyncio.sleep(3)
            
            # Disable worksafe mode if it's enabled (critical for seeing actual images)
            await self._disable_worksafe_mode(page)
            
            # Scroll to load all images (lazy loading)
            await self._scroll_to_load_all(page)
            
            # Check if this is a single pic page or portfolio page
            if '/portfolio/pic/' in self.url:
                # Single photo page - extract that one image
                media_items = await self._extract_single_photo(page)
            else:
                # Portfolio page - extract all photo links then get full-res images
                media_items = await self._extract_portfolio_images(page)
            
            print(f"ModelMayhemHandler: Extracted {len(media_items)} images in {time.time() - start_time:.2f}s")
            
        except Exception as e:
            print(f"ModelMayhemHandler: Error during extraction: {e}")
            traceback.print_exc()
        
        return media_items
    
    async def _resolve_numeric_id_from_profile(self, page) -> Optional[str]:
        """
        Extract the numeric Model Mayhem ID from a profile page.
        The ID is shown in "Model Mayhem #: XXXXXX" or in portfolio link URLs.
        """
        try:
            numeric_id = await page.evaluate('''
                () => {
                    // Method 1: Look for "Model Mayhem #:" text
                    const textContent = document.body.innerText;
                    const mmMatch = textContent.match(/Model Mayhem #:\\s*(\\d+)/);
                    if (mmMatch) return mmMatch[1];
                    
                    // Method 2: Look for portfolio link with numeric ID
                    const portfolioLink = document.querySelector('a[href*="/portfolio/"][href*="/viewall"]');
                    if (portfolioLink) {
                        const match = portfolioLink.href.match(/\\/portfolio\\/(\\d+)/);
                        if (match) return match[1];
                    }
                    
                    // Method 3: Look for any link with /portfolio/NUMBER pattern
                    const allLinks = document.querySelectorAll('a[href*="/portfolio/"]');
                    for (const link of allLinks) {
                        const match = link.href.match(/\\/portfolio\\/(\\d+)/);
                        if (match) return match[1];
                    }
                    
                    // Method 4: Look for profile link in navigation  
                    const profileLinks = document.querySelectorAll('a[href^="/"]');
                    for (const link of profileLinks) {
                        const match = link.href.match(/modelmayhem\\.com\\/(\\d+)$/);
                        if (match) return match[1];
                    }
                    
                    return null;
                }
            ''')
            
            if numeric_id:
                print(f"ModelMayhemHandler: Found numeric ID: {numeric_id}")
                return numeric_id
            else:
                print("ModelMayhemHandler: Could not find numeric ID on profile page")
                return None
                
        except Exception as e:
            print(f"ModelMayhemHandler: Error resolving numeric ID: {e}")
            return None
    
    async def _disable_worksafe_mode(self, page):
        """
        Disable worksafe mode to show actual images instead of placeholders.
        ModelMayhem defaults to worksafe mode which shows 'nopic_worksafe-on.gif' placeholders.
        """
        try:
            # Check if worksafe mode is currently ON (link to turn it OFF is visible)
            worksafe_off_link = await page.query_selector('a[href="/worksafe/0"], a[href*="worksafe/0"]')
            
            if worksafe_off_link:
                print("ModelMayhemHandler: Worksafe mode is ON, disabling it...")
                await worksafe_off_link.click()
                await asyncio.sleep(2)  # Wait for page to reload/update
                print("ModelMayhemHandler: Worksafe mode disabled")
            else:
                # Check the toggle text to see current state
                page_text = await page.evaluate('() => document.body.innerText')
                if 'Toggle Worksafe Mode: Off' in page_text:
                    print("ModelMayhemHandler: Worksafe mode already OFF")
                elif 'Toggle Worksafe Mode:' in page_text and 'On' in page_text:
                    # Try clicking via JavaScript
                    clicked = await page.evaluate('''
                        () => {
                            const links = document.querySelectorAll('a');
                            for (const link of links) {
                                if (link.textContent.trim() === 'Off' && 
                                    link.closest && 
                                    link.closest('[class*="worksafe"], [id*="worksafe"]') ||
                                    link.previousSibling?.textContent?.includes('Worksafe')) {
                                    link.click();
                                    return true;
                                }
                            }
                            // Alternative: find by href pattern
                            const wsLink = document.querySelector('a[href*="worksafe"]');
                            if (wsLink && wsLink.textContent.trim() === 'Off') {
                                wsLink.click();
                                return true;
                            }
                            return false;
                        }
                    ''')
                    if clicked:
                        await asyncio.sleep(2)
                        print("ModelMayhemHandler: Worksafe mode disabled via JS click")
                else:
                    print("ModelMayhemHandler: Could not determine worksafe mode state")
                    
        except Exception as e:
            print(f"ModelMayhemHandler: Error disabling worksafe mode: {e}")
    
    async def _scroll_to_load_all(self, page):
        """Scroll down the page to trigger lazy loading of images"""
        print("ModelMayhemHandler: Scrolling to load all images...")
        
        try:
            previous_height = 0
            scroll_count = 0
            
            while scroll_count < self.max_scroll_count:
                # Get current scroll height
                current_height = await page.evaluate("document.body.scrollHeight")
                
                if current_height == previous_height:
                    # No new content loaded, we're done
                    break
                
                previous_height = current_height
                
                # Scroll down
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await asyncio.sleep(self.scroll_delay_ms / 1000)
                
                scroll_count += 1
                print(f"ModelMayhemHandler: Scroll {scroll_count}/{self.max_scroll_count}")
            
            # Scroll back to top
            await page.evaluate("window.scrollTo(0, 0)")
            await asyncio.sleep(0.5)
            
        except Exception as e:
            print(f"ModelMayhemHandler: Scroll error: {e}")
    
    async def _extract_single_photo(self, page) -> List[Dict[str, Any]]:
        """Extract the full-resolution image from a single photo page"""
        media_items = []
        
        try:
            # Look for the main photo on the page
            photo_data = await page.evaluate('''
                () => {
                    const results = [];
                    
                    // Look for images from photos.modelmayhem.com
                    const imgs = document.querySelectorAll('img');
                    for (const img of imgs) {
                        const src = img.src || img.dataset.src || '';
                        if (src.includes('photos.modelmayhem.com')) {
                            results.push({
                                url: src,
                                width: img.naturalWidth || 0,
                                height: img.naturalHeight || 0,
                                alt: img.alt || ''
                            });
                        }
                    }
                    
                    // Also look for og:image meta tag (often has full-res URL)
                    const ogImage = document.querySelector('meta[property="og:image"]');
                    if (ogImage && ogImage.content) {
                        results.push({
                            url: ogImage.content,
                            width: 0,
                            height: 0,
                            alt: 'og:image'
                        });
                    }
                    
                    return results;
                }
            ''')
            
            for item in photo_data:
                url = item.get('url', '')
                if not url:
                    continue
                
                # Upgrade thumbnail to full resolution
                full_res_url = self._upgrade_thumbnail_to_full_res(url)
                
                if full_res_url not in self.seen_urls:
                    self.seen_urls.add(full_res_url)
                    self.seen_urls.add(url)  # Also mark original as seen
                    media_items.append({
                        'url': full_res_url,
                        'type': 'image',
                        'width': item.get('width', 0),
                        'height': item.get('height', 0),
                        'source_page': self.url,
                        'trusted_cdn': True
                    })
            
        except Exception as e:
            print(f"ModelMayhemHandler: Error extracting single photo: {e}")
        
        return media_items
    
    async def _extract_portfolio_images(self, page) -> List[Dict[str, Any]]:
        """
        Extract all images from a portfolio page.
        
        Strategy: Extract thumbnail URLs from the portfolio grid page and upgrade them
        to full resolution URLs. This is much faster than visiting each individual
        pic page, and works because ModelMayhem uses predictable URL patterns:
        - Thumbnail: /photos/.../filename_m.jpg
        - Full res:  /photos/.../filename.jpg
        """
        media_items = []
        
        try:
            # Debug: Log current URL and page title
            current_url = page.url
            page_title = await page.title()
            print(f"ModelMayhemHandler: Current page URL: {current_url}")
            print(f"ModelMayhemHandler: Page title: {page_title}")
            
            # Debug: Count all images on page
            all_img_count = await page.evaluate('() => document.querySelectorAll("img").length')
            print(f"ModelMayhemHandler: Total img elements on page: {all_img_count}")
            
            # Extract all images directly from the portfolio page
            # These are thumbnails but we'll upgrade them to full resolution
            page_images = await page.evaluate('''
                () => {
                    const images = [];
                    const debugInfo = { total: 0, modelmayhem: 0, worksafe: 0, other: [] };
                    const imgs = document.querySelectorAll('img');
                    debugInfo.total = imgs.length;
                    
                    for (const img of imgs) {
                        const src = img.src || img.dataset.src || img.getAttribute('data-src') || '';
                        
                        // Skip worksafe placeholder images
                        if (src.includes('nopic_worksafe') || src.includes('worksafe')) {
                            debugInfo.worksafe++;
                            continue;
                        }
                        
                        // Only include photos.modelmayhem.com images (the actual photos)
                        if (src.includes('photos.modelmayhem.com/photos/') || 
                            src.includes('photos.modelmayhem.com/covers/')) {
                            debugInfo.modelmayhem++;
                            images.push({
                                url: src,
                                width: img.naturalWidth || 0,
                                height: img.naturalHeight || 0
                            });
                        } else if (src && src.length > 10 && debugInfo.other.length < 5) {
                            // Log first few non-matching URLs for debugging
                            debugInfo.other.push(src.substring(0, 100));
                        }
                    }
                    
                    // Also check for background images in divs (some galleries use this)
                    const divs = document.querySelectorAll('[style*="background-image"]');
                    for (const div of divs) {
                        const style = div.getAttribute('style') || '';
                        const match = style.match(/url\\(['"]?(https?:\\/\\/photos\\.modelmayhem\\.com[^'")\s]+)['"]?\\)/);
                        if (match && match[1]) {
                            debugInfo.modelmayhem++;
                            images.push({
                                url: match[1],
                                width: 0,
                                height: 0
                            });
                        }
                    }
                    
                    // Check data attributes for lazy-loaded images
                    const lazyImgs = document.querySelectorAll('[data-src*="photos.modelmayhem.com"], [data-lazy-src*="photos.modelmayhem.com"]');
                    for (const img of lazyImgs) {
                        const src = img.dataset.src || img.dataset.lazySrc || '';
                        if (src && src.includes('photos.modelmayhem.com')) {
                            debugInfo.modelmayhem++;
                            images.push({
                                url: src,
                                width: 0,
                                height: 0
                            });
                        }
                    }
                    
                    // Return both images and debug info
                    return { images: images, debug: debugInfo };
                }
            ''')
            
            # Extract debug info and images
            debug_info = page_images.get('debug', {})
            actual_images = page_images.get('images', [])
            
            print(f"ModelMayhemHandler: Debug - Total imgs: {debug_info.get('total', 0)}, ModelMayhem imgs: {debug_info.get('modelmayhem', 0)}, Worksafe placeholders: {debug_info.get('worksafe', 0)}")
            if debug_info.get('other'):
                print(f"ModelMayhemHandler: Sample other image URLs: {debug_info.get('other', [])[:3]}")
            
            print(f"ModelMayhemHandler: Found {len(actual_images)} ModelMayhem images on portfolio page")
            
            # Upgrade each thumbnail URL to full resolution (with verification) and deduplicate
            print(f"ModelMayhemHandler: Verifying {len(actual_images)} image URLs...")
            verified_count = 0
            fallback_count = 0
            
            for img in actual_images:
                thumb_url = img.get('url', '')
                if not thumb_url:
                    continue
                
                # Skip if we've already seen this thumbnail URL
                if thumb_url in self.seen_urls:
                    continue
                
                # Verify and get the best URL (full-res if it exists, else thumbnail)
                best_url, original_thumbnail = await self._verify_and_get_best_url(page, thumb_url)
                
                # Skip if we've already seen the best URL
                if best_url in self.seen_urls:
                    continue
                
                self.seen_urls.add(best_url)
                self.seen_urls.add(thumb_url)  # Also mark thumbnail as seen
                
                # Track verification stats
                if original_thumbnail:
                    verified_count += 1
                else:
                    fallback_count += 1
                
                media_items.append({
                    'url': best_url,
                    'type': 'image',
                    'width': img.get('width', 0),
                    'height': img.get('height', 0),
                    'source_page': self.url,
                    'trusted_cdn': True,
                    'original_thumbnail': original_thumbnail
                })
            
            print(f"ModelMayhemHandler: Extracted {len(media_items)} unique image URLs ({verified_count} full-res verified, {fallback_count} using thumbnail)")
            
            # If we didn't find many images, fall back to visiting individual pic pages
            # This handles edge cases where the portfolio page doesn't show all thumbnails
            if len(media_items) < 10:
                print("ModelMayhemHandler: Few images found, trying pic page extraction as fallback...")
                fallback_items = await self._extract_via_pic_pages(page)
                
                # Add any new URLs from fallback
                for item in fallback_items:
                    url = item.get('url', '')
                    if url and url not in self.seen_urls:
                        self.seen_urls.add(url)
                        media_items.append(item)
                
                print(f"ModelMayhemHandler: After fallback, total {len(media_items)} images")
            
        except Exception as e:
            print(f"ModelMayhemHandler: Error extracting portfolio images: {e}")
            traceback.print_exc()
        
        return media_items
    
    async def _extract_via_pic_pages(self, page) -> List[Dict[str, Any]]:
        """
        Fallback method: Visit individual pic pages to extract full-res images.
        Used when the portfolio page doesn't have all thumbnails visible.
        """
        media_items = []
        
        try:
            # Collect all portfolio pic links
            pic_links = await page.evaluate('''
                () => {
                    const links = [];
                    const anchors = document.querySelectorAll('a[href*="/portfolio/pic/"]');
                    for (const a of anchors) {
                        if (a.href && !links.includes(a.href)) {
                            links.push(a.href);
                        }
                    }
                    return links;
                }
            ''')
            
            print(f"ModelMayhemHandler: Found {len(pic_links)} pic page links for fallback extraction")
            
            # Visit each pic page (no artificial limit - get all images)
            for i, pic_link in enumerate(pic_links):
                try:
                    if self.request_delay_ms > 0:
                        await asyncio.sleep(self.request_delay_ms / 1000)
                    
                    if (i + 1) % 10 == 0:
                        print(f"ModelMayhemHandler: Processing pic {i+1}/{len(pic_links)}")
                    
                    # Navigate to the pic page
                    await page.goto(pic_link, wait_until="domcontentloaded", timeout=15000)
                    await asyncio.sleep(0.5)
                    
                    # Extract the full-res image from this page
                    pic_images = await self._extract_single_photo(page)
                    
                    for item in pic_images:
                        url = item.get('url', '')
                        if url and url not in self.seen_urls:
                            self.seen_urls.add(url)
                            media_items.append(item)
                    
                except Exception as e:
                    print(f"ModelMayhemHandler: Error processing pic {i+1}: {e}")
                    continue
            
        except Exception as e:
            print(f"ModelMayhemHandler: Error in pic page extraction: {e}")
        
        return media_items
    
    async def extract_media_items_async(self, page_adaptor) -> List[Dict[str, Any]]:
        """
        Async extraction method - wrapper that gets Playwright page from adaptor
        """
        print(f"ModelMayhemHandler: extract_media_items_async called")
        
        # Try to get the underlying Playwright page
        pw_page = None
        if hasattr(page_adaptor, 'page'):
            pw_page = page_adaptor.page
        elif hasattr(self, 'get_playwright_page'):
            pw_page = await self.get_playwright_page(page_adaptor)
        
        if pw_page:
            return await self.extract_with_direct_playwright(pw_page)
        else:
            print("ModelMayhemHandler: No Playwright page available")
            return []
