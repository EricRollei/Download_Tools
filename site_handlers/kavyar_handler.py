"""
Kavyar Handler

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
Kavyar-specific handler for the Web Image Scraper
Extracts images / video / audio from https://kavyar.com/mob-journal
"""

# -- Core base-class & typing
from site_handlers.base_handler import BaseSiteHandler           # core helper methods
from urllib.parse import urlparse, urljoin                       # URL ops
from typing import List, Dict, Any, Optional                     # type hints
import re, json, time, asyncio, random, os, traceback           # misc utilities

# -- Playwright (async) – load only if user enabled Playwright in the node UI
try:
    from playwright.async_api import Page as AsyncPage           # Playwright page type
    from playwright.async_api import Browser, BrowserContext     # Additional Playwright types
    PLAYWRIGHT_AVAILABLE = True
except ImportError:                                              # fallback when PW missing
    AsyncPage = None
    Browser = None
    BrowserContext = None
    PLAYWRIGHT_AVAILABLE = False


class KavyarHandler(BaseSiteHandler):
    """Handler for Kavyar.com (Mob Journal section)"""
    
    # Class attributes for configuration
    PRIORITY = 50  # Medium priority (lower number = higher priority)
    
    @classmethod
    def can_handle(cls, url: str) -> bool:
        # Use this handler for any Kavyar URL (not just Mob Journal)
        return "kavyar.com" in url.lower()
    
    def __init__(self, url, scraper=None):
        super().__init__(url, scraper)
        # Configuration defaults - ENHANCED for Kavyar's content discovery needs
        self.max_scroll_count = 25  # Increased from 10 - Kavyar needs more scrolling
        self.scroll_delay_ms = 1500  # Increased from 1000 - Allow more time for lazy loading
        self.use_stealth_mode = True
        self.retry_attempts = 2
        self.dynamic_content_wait_ms = 2000
        
        self.request_delay_ms = 1500  # Time between major actions
        self.last_request_time = 0
        # Track state
        self.is_logged_in = False
        self.extracted_media_cache = {}  # Cache to avoid duplicates

        # Add state persistence
        self.state_file = None
        if scraper and hasattr(scraper, 'output_path'):
            self.state_file = os.path.join(
                scraper.output_path, 
                "kavyar_state.json"
            )
    
    def get_trusted_domains(self):
        """Return list of trusted CDN domains for Kavyar"""
        return [
            "dfocupmdlnlkc.cloudfront.net",  # Kavyar's CloudFront CDN
            "kavyar.com",                    # Main domain
            "cloudfront.net"                 # General CloudFront (for safety)
        ]
        
    def _load_api_credentials(self):
        """Load credentials from the auth_config if available"""
        # Initialize defaults
        self.username = None
        self.password = None
        
        # Skip if no scraper or auth_config
        if not hasattr(self, 'scraper') or not self.scraper:
            return
            
        if not hasattr(self.scraper, 'auth_config') or not self.scraper.auth_config:
            return
            
        # Check both domain-specific and generic credentials
        auth_config = self.scraper.auth_config
        
        # Try to get domain-specific config
        domain = urlparse(self.url).netloc
        domain_config = None
        
        # Look in 'sites' section first (newer format)
        if 'sites' in auth_config and domain in auth_config['sites']:
            domain_config = auth_config['sites'][domain]
        # Then directly in the config (older format)
        elif domain in auth_config:
            domain_config = auth_config[domain]
            
        if domain_config:
            self.username = domain_config.get('username')
            self.password = domain_config.get('password')
            # Load additional config if available
            if 'max_scroll_count' in domain_config:
                self.max_scroll_count = domain_config.get('max_scroll_count')
            if 'scroll_delay_ms' in domain_config:
                self.scroll_delay_ms = domain_config.get('scroll_delay_ms')
            if 'use_stealth_mode' in domain_config:
                self.use_stealth_mode = domain_config.get('use_stealth_mode')
    
    async def _setup_stealth_context(self, browser: Browser) -> Optional[BrowserContext]:
        """Create a stealth browser context with random user agent and other anti-detection measures"""
        if not PLAYWRIGHT_AVAILABLE or not browser:
            return None
            
        try:
            # Generate a realistic user agent
            user_agents = [
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:94.0) Gecko/20100101 Firefox/94.0",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.1 Safari/605.1.15"
            ]
            user_agent = random.choice(user_agents)
            
            # Create a context with stealth settings
            context = await browser.new_context(
                user_agent=user_agent,
                viewport={"width": 1920, "height": 1080},
                device_scale_factor=1.0,
                locale="en-US",
                timezone_id="America/New_York",
                permissions=["geolocation", "notifications"]
            )
            
            # Add stealth script to mask automation
            await context.add_init_script("""
                () => {
                    // Override the navigator and window objects
                    Object.defineProperty(navigator, 'webdriver', { get: () => false });
                    
                    // Fake plugins to look more like a regular browser
                    Object.defineProperty(navigator, 'plugins', {
                        get: () => {
                            return {
                                length: 5,
                                item: (index) => { return {name: `Plugin ${index}`, filename: `plugin${index}.dll`}; },
                                namedItem: (name) => { return null; }
                            };
                        }
                    });
                    
                    // Fake languages
                    Object.defineProperty(navigator, 'languages', {
                        get: () => ['en-US', 'en']
                    });
                    
                    // Add Chrome-specific properties
                    window.chrome = {
                        runtime: {},
                        webstore: {}
                    };
                    
                    // Override permission query
                    if (navigator.permissions) {
                        const originalQuery = navigator.permissions.query;
                        navigator.permissions.query = (parameters) => (
                            parameters.name === 'notifications' || parameters.name === 'geolocation'
                                ? Promise.resolve({ state: Notification.permission })
                                : originalQuery(parameters)
                        );
                    }
                    
                    // Handle canvas fingerprinting
                    const originalGetContext = HTMLCanvasElement.prototype.getContext;
                    if (originalGetContext) {
                        HTMLCanvasElement.prototype.getContext = function() {
                            const context = originalGetContext.apply(this, arguments);
                            if (context && arguments[0] === '2d') {
                                const originalGetImageData = context.getImageData;
                                context.getImageData = function() {
                                    const imageData = originalGetImageData.apply(this, arguments);
                                    // Add minor noise to fingerprint
                                    for (let i = 0; i < imageData.data.length; i += 100) {
                                        imageData.data[i] = imageData.data[i] + (Math.random() < 0.5 ? 1 : -1);
                                    }
                                    return imageData;
                                };
                            }
                            return context;
                        };
                    }
                    
                    // Hide automation flags
                    delete navigator.__proto__.webdriver;
                }
            """)
            
            return context
        except Exception as e:
            print(f"Error setting up stealth context: {e}")
            return None
    
    async def extract_with_direct_playwright(self, page: AsyncPage, **kwargs) -> List[Dict]:
        """
        Enhanced extract method with stealth options, better page handling,
        and improved error recovery, focusing on Kavyar's specific structure.
        """
        # Apply configurations from kwargs if provided
        self.max_scroll_count = kwargs.get('max_auto_scrolls', self.max_scroll_count)
        self.scroll_delay_ms = kwargs.get('scroll_delay_ms', self.scroll_delay_ms)
        self.use_stealth_mode = kwargs.get('use_stealth_mode', self.use_stealth_mode)
        self.dynamic_content_wait_ms = kwargs.get('playwright_wait_ms', self.dynamic_content_wait_ms)
        self.retry_attempts = kwargs.get('retry_attempts', 2)
        self.debug_mode = kwargs.get('debug_mode', True)  # Enable debug by default for troubleshooting
        
        print(f"Kavyar handler starting extraction with scrolls={self.max_scroll_count}, delay={self.scroll_delay_ms}ms")
        
        all_media_items = []
        current_context = None
        
        # Load previous state if available
        previous_state = self._load_state() if hasattr(self, '_load_state') else {}
        processed_urls = set(previous_state.get('processed_urls', []))
        
        # Initialize URL tracking set
        if not hasattr(self, 'processed_urls'):
            self.processed_urls = set()
        
        # Implement retry logic for the entire extraction process
        for attempt in range(self.retry_attempts + 1):
            try:
                # Setup browser with stealth mode if needed
                if self.use_stealth_mode and hasattr(self, 'scraper') and hasattr(self.scraper, 'pw_resources'):
                    try:
                        pw, browser, old_context, old_page = self.scraper.pw_resources
                        
                        # Create stealth context - only do this on first attempt
                        if attempt == 0 or current_context is None:
                            new_context = await self._setup_stealth_context(browser)
                            if new_context:
                                current_context = new_context
                                # Create new page with stealth context
                                new_page = await new_context.new_page()
                                # Navigate to URL
                                await new_page.goto(self.url, wait_until="domcontentloaded", timeout=30000)
                                # Update page reference
                                page = new_page
                                if self.debug_mode:
                                    print("Using stealth mode for Kavyar")
                    except Exception as e:
                        if self.debug_mode:
                            print(f"Failed to setup stealth mode: {e}")
                        # Continue with existing page if stealth setup fails
                
                # Improved authentication with cookie support
                self._load_api_credentials()
                print(f"Credentials loaded - username exists: {hasattr(self, 'username') and bool(self.username)}")
                
                # Force cookie-based authentication for Kavyar
                auth_type = 'cookie'  # Force cookie auth for Kavyar since we have the cookies configured
                print(f"Authentication type: {auth_type} (forced for Kavyar)")
                
                # Apply cookies if using cookie-based auth (which we are forcing)
                if auth_type == 'cookie' and hasattr(self, 'auth_credentials'):
                    print("Using cookie-based authentication...")
                    await self._apply_cookies(page)
                    
                    # Navigate to the target profile after applying cookies
                    print(f"Navigating to profile with cookies: {self.url}")
                    await page.goto(self.url, wait_until="domcontentloaded", timeout=30000)
                    await page.wait_for_timeout(3000)
                    current_url = page.url
                    print(f"After cookie navigation, URL is: {current_url}")
                else:
                    # Check auth type from config if available
                    config_auth_type = getattr(self, 'auth_credentials', {}).get('auth_type', 'form')
                    print(f"Config authentication type: {config_auth_type}")
                    
                    # Check if we're on a login redirect page for form-based auth
                    current_url = page.url
                    print(f"Current URL after navigation: {current_url}")
                    
                    if 'start' in current_url or 'login' in current_url:
                        print(f"Detected login redirect. Current URL: {current_url}")
                        
                        # If we have credentials, attempt login
                        if hasattr(self, 'username') and hasattr(self, 'password') and self.username and self.password:
                            print("Attempting login to access the profile...")
                            login_success = await self._perform_improved_login(page)
                            if login_success:
                                print("Login successful, navigating to target profile...")
                                await page.goto(self.url, wait_until="domcontentloaded", timeout=30000)
                                await page.wait_for_timeout(3000)
                                current_url = page.url
                                print(f"After login navigation, URL is: {current_url}")
                            else:
                                print("Login failed, but continuing with extraction attempt...")
                        else:
                            print("No credentials available for login - content may be limited")
                    else:
                        print("Direct access successful - no login redirect detected")
                
                # Take a screenshot to see what we're working with
                if self.debug_mode:
                    try:
                        debug_dir = os.path.dirname(os.path.abspath(__file__))
                        os.makedirs(os.path.join(debug_dir, "debug"), exist_ok=True)
                        screenshot_path = os.path.join(debug_dir, "debug", "kavyar_current_page.png")
                        await page.screenshot(path=screenshot_path, full_page=True)
                        print(f"Current page screenshot saved to: {screenshot_path}")
                    except Exception as ss_err:
                        print(f"Failed to save debug screenshot: {ss_err}")
                        
                print(f"Final URL before extraction: {page.url}")
                
                # First, try to extract images directly from current page if it's a profile page
                print("Checking if current page has images to extract...")
                
                # Look for expand/gallery buttons that might reveal images
                expand_success = await self._click_expand_buttons(page)
                if expand_success:
                    print("Successfully clicked expand buttons, waiting for content to load...")
                    await page.wait_for_timeout(3000)
                
                await self._optimized_kavyar_scroll(page)  # Scroll to load all content
                
                # Initialize page_items list to collect all images
                page_items = []
                
                # Try to extract images directly from the current page first
                direct_page_items = []
                direct_cache = set()
                await self._extract_current_page_images(page, direct_page_items, direct_cache)
                
                if direct_page_items:
                    print(f"Found {len(direct_page_items)} images on current page")
                    page_items.extend(direct_page_items)
                
                # Also look for card links to individual works if this is a gallery page
                card_links = await page.evaluate("""
                    () => {
                        // Look for card links - try multiple patterns
                        const links = [];
                        // Pattern 1: Works links
                        document.querySelectorAll('a[href*="/works/"]').forEach(link => {
                            if (link.href && link.href.includes('/works/')) {
                                links.push(link.href);
                            }
                        });
                        // Pattern 2: Any internal links that might be image pages
                        document.querySelectorAll('a[href^="/"]').forEach(link => {
                            if (link.href && !link.href.includes('login') && !link.href.includes('register')) {
                                // Only add if it looks like it might contain images
                                const hasImg = link.querySelector('img');
                                if (hasImg) {
                                    links.push(window.location.origin + link.getAttribute('href'));
                                }
                            }
                        });
                        return [...new Set(links)];  // Remove duplicates
                    }
                """)
                
                print(f"Found {len(card_links)} card links to process")
                
                # Process each card link to extract high-res images (ADD to existing page_items, don't reset!)
                card_items = []  # Use separate list for card processing
                for idx, link in enumerate(card_links[:kwargs.get('max_cards', 50)]):  # Limit to prevent too many requests
                    try:
                        print(f"Processing card {idx+1}/{len(card_links)}: {link}")
                        
                        # Navigate to the detail page
                        await page.goto(link, wait_until="domcontentloaded", timeout=30000)
                        await page.wait_for_timeout(1000)  # Short wait for content
                        
                        # Extract images from this detail page
                        detail_items = []
                        detail_cache = set()
                        
                        # Extract detail page images
                        await self._extract_detail_page_images(page, detail_items, detail_cache)
                        
                        if detail_items:
                            print(f"  Found {len(detail_items)} images on detail page")
                            card_items.extend(detail_items)
                        else:
                            print("  No images found on detail page")
                            
                        # Rate limiting to be polite to the server
                        await page.wait_for_timeout(1000)  # 1-second delay between pages
                        
                    except Exception as e:
                        print(f"  Error processing card link {link}: {e}")
                        continue
                
                # Add any card items found to the main page_items list
                if card_items:
                    print(f"Found {len(card_items)} additional images from card links")
                    page_items.extend(card_items)
                
                print(f"Finished processing card links. Total media items found: {len(page_items)}")
                
                # Filter out already processed URLs and add to all_media_items
                for item in page_items:
                    url = item.get('url')
                    if url and url not in processed_urls and url not in self.processed_urls:
                        all_media_items.append(item)
                        processed_urls.add(url)
                        self.processed_urls.add(url)
                
                # Save state if method exists
                if hasattr(self, '_save_state'):
                    self._save_state({
                        'processed_urls': list(processed_urls),
                        'last_run': time.time(),
                        'url': self.url
                    })
                
                # Save session cookies if logged in successfully
                if hasattr(self, 'is_logged_in') and self.is_logged_in and hasattr(self, '_handle_session_persistence') and current_context:
                    await self._handle_session_persistence(current_context, page)
                
                # If we found items, break out of retry loop
                if all_media_items:
                    if self.debug_mode:
                        print(f"Successfully extracted {len(all_media_items)} items on attempt {attempt+1}")
                    break
                elif attempt < self.retry_attempts:
                    print(f"No media items found on attempt {attempt+1}, retrying...")
                    await page.reload()
                    await page.wait_for_timeout(self.dynamic_content_wait_ms)
                    
            except Exception as e:
                print(f"Error in Kavyar extraction (attempt {attempt+1}): {e}")
                if self.debug_mode:
                    traceback.print_exc()
                
                if attempt < self.retry_attempts:
                    print(f"Retrying extraction ({attempt+1}/{self.retry_attempts})...")
                    await page.wait_for_timeout(2000)
                    
                    # Try reloading the page for a fresh attempt
                    try:
                        await page.reload()
                        await page.wait_for_timeout(self.dynamic_content_wait_ms)
                    except Exception as reload_err:
                        print(f"Error reloading page: {reload_err}")
        
        # Clean up resources
        if current_context:
            try:
                await current_context.close()
            except Exception as e:
                print(f"Error closing stealth context: {e}")
        
        # If we found no items at all, take a debug screenshot
        if not all_media_items and self.debug_mode:
            try:
                debug_dir = os.path.dirname(os.path.abspath(__file__))
                os.makedirs(os.path.join(debug_dir, "debug"), exist_ok=True)
                ss_path = os.path.join(debug_dir, "debug", f"kavyar_extraction_failed_{int(time.time())}.png")
                await page.screenshot(path=ss_path, full_page=True)
                print(f"Debug screenshot saved to: {ss_path}")
                
                # Also save HTML for inspection
                html_path = os.path.join(debug_dir, "debug", f"kavyar_page_{int(time.time())}.html")
                html_content = await page.content()
                with open(html_path, 'w', encoding='utf-8') as f:
                    f.write(html_content)
                print(f"Debug HTML saved to: {html_path}")
            except Exception as ss_err:
                print(f"Failed to save debug files: {ss_err}")
        
        print(f"Kavyar extraction complete: {len(all_media_items)} items extracted")
        
        # Post-process to add trusted_cdn flag for CloudFront URLs
        for item in all_media_items:
            url = item.get('url', '')
            if 'cloudfront.net' in url:
                item['trusted_cdn'] = True
        
        return all_media_items

    async def _optimized_kavyar_scroll(self, page: AsyncPage) -> None:
        """Enhanced aggressive scrolling for Kavyar's image grid layout"""
        try:
            print("Starting enhanced aggressive scrolling for Kavyar...")
            
            # First, check how many images we can see initially
            initial_image_count = await page.evaluate("""
                () => {
                    const imgCount = document.querySelectorAll('picture img, picture source').length;
                    const cloudfront = document.querySelectorAll('[src*="cloudfront.net"], [srcset*="cloudfront.net"]').length;
                    return { imgCount, cloudfront };
                }
            """)
            
            print(f"Initially found {initial_image_count['imgCount']} images including {initial_image_count['cloudfront']} cloudfront images")
            
            # Enhanced scrolling strategy for Kavyar
            max_scrolls = max(self.max_scroll_count, 20)  # At least 20 scrolls
            scroll_delay = max(self.scroll_delay_ms, 1500)  # At least 1.5s delay
            last_image_count = initial_image_count['cloudfront']
            consecutive_unchanged = 0
            
            # Try multiple scrolling techniques
            for i in range(max_scrolls):
                # Technique 1: Smooth scroll (for lazy loading)
                await page.evaluate("""
                    () => {
                        const viewportHeight = window.innerHeight;
                        window.scrollBy({
                            top: viewportHeight * 0.8,
                            behavior: 'smooth'
                        });
                    }
                """)
                
                await page.wait_for_timeout(scroll_delay // 3)
                
                # Technique 2: Jump scroll (trigger different loading mechanisms)
                await page.evaluate("""
                    () => {
                        const documentHeight = document.documentElement.scrollHeight;
                        const currentPosition = window.pageYOffset;
                        const jumpTo = Math.min(currentPosition + window.innerHeight * 2, documentHeight);
                        window.scrollTo({ top: jumpTo, behavior: 'instant' });
                    }
                """)
                
                await page.wait_for_timeout(scroll_delay // 3)
                
                # Technique 3: Bottom scroll (trigger "load more" behavior)
                if i % 5 == 0:  # Every 5th scroll
                    await page.evaluate("""
                        () => {
                            window.scrollTo({ 
                                top: document.documentElement.scrollHeight, 
                                behavior: 'smooth' 
                            });
                        }
                    """)
                    await page.wait_for_timeout(scroll_delay)
                
                # Check if we've loaded new images
                current_counts = await page.evaluate("""
                    () => {
                        const imgCount = document.querySelectorAll('picture img, picture source').length;
                        const cloudfront = document.querySelectorAll('[src*="cloudfront.net"], [srcset*="cloudfront.net"]').length;
                        return { imgCount, cloudfront };
                    }
                """)
                
                # For Kavyar specifically, check the cloudfront count
                cloudfront_count = current_counts['cloudfront']
                
                if cloudfront_count > last_image_count:
                    print(f"Scroll {i+1}: Found {cloudfront_count - last_image_count} new images (total: {cloudfront_count})")
                    last_image_count = cloudfront_count
                    consecutive_unchanged = 0
                else:
                    consecutive_unchanged += 1
                    print(f"Scroll {i+1}: No new images found. Unchanged: {consecutive_unchanged}")
                    
                    # After consecutive unchanged scrolls, try clicking any "Load More" buttons
                    if consecutive_unchanged == 2:
                        load_more_clicked = await self._click_kavyar_load_buttons(page)
                        if load_more_clicked:
                            consecutive_unchanged = 0
                            await page.wait_for_timeout(scroll_delay * 2)
                    
                    # If no new content after multiple tries, try other interaction methods first
                    if consecutive_unchanged >= 3:
                        # Try clicking navigation arrows or gallery controls
                        nav_clicked = await self._click_navigation_controls(page)
                        if nav_clicked:
                            consecutive_unchanged = 0
                            await page.wait_for_timeout(scroll_delay * 2)
                            continue
                    
                    # If still no new content after multiple tries, we're done  
                    if consecutive_unchanged >= 8:  # Increased from 5 to be more persistent
                        print("No new content after multiple scrolls and interactions. Finishing scrolling.")
                        break
            
            # Final scroll to the bottom to ensure we've loaded everything
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(scroll_delay)
            
            # Give a moment for any final lazy loading
            await page.wait_for_timeout(1000)
            
            # Final count
            final_counts = await page.evaluate("""
                () => {
                    const imgCount = document.querySelectorAll('picture img, picture source').length;
                    const cloudfront = document.querySelectorAll('[src*="cloudfront.net"], [srcset*="cloudfront.net"]').length;
                    return { imgCount, cloudfront };
                }
            """)
            
            print(f"Finished scrolling. Found total of {final_counts['cloudfront']} cloudfront images")
            
        except Exception as e:
            print(f"Error during optimized scrolling: {e}")
            traceback.print_exc()


    async def _apply_cookies(self, page):
        """Apply Kavyar session cookies for authentication."""
        try:
            cookies = self.auth_credentials.get('cookies', [])
            if not cookies:
                print("No cookies to apply")
                return
                
            print(f"Applying {len(cookies)} Kavyar cookies...")
            
            # Convert cookies to Playwright format and apply them
            playwright_cookies = []
            for cookie in cookies:
                playwright_cookie = {
                    'name': cookie['name'],
                    'value': cookie['value'],
                    'domain': cookie['domain'],
                    'path': cookie.get('path', '/'),
                    'secure': cookie.get('secure', False),
                    'httpOnly': cookie.get('httpOnly', False)
                }
                
                # Add sameSite if present
                if 'sameSite' in cookie:
                    playwright_cookie['sameSite'] = cookie['sameSite']
                    
                playwright_cookies.append(playwright_cookie)
            
            # Apply cookies to the browser context
            context = page.context
            await context.add_cookies(playwright_cookies)
            print(f"Successfully applied {len(playwright_cookies)} cookies")
            
            # Navigate to Kavyar main page to activate cookies
            print("Navigating to Kavyar main page to activate cookies...")
            await page.goto("https://kavyar.com", timeout=30000)
            await page.wait_for_timeout(2000)
            
            # Check if logged in by looking for user profile indicators
            login_indicators = [
                '[data-user]', '.user-menu', '.profile-link', '.user-profile', 
                '.avatar', '.logged-in', '.user-nav', '[href*="profile"]'
            ]
            
            logged_in = False
            for indicator in login_indicators:
                if await page.query_selector(indicator):
                    logged_in = True
                    break
            
            if logged_in:
                print("✓ Successfully logged in with cookies")
            else:
                print("⚠ Cookies applied but login status unclear")
                
        except Exception as e:
            print(f"Error applying cookies: {e}")
            traceback.print_exc()

    async def _click_expand_buttons(self, page: AsyncPage) -> bool:
        """Try to click expand/gallery buttons to reveal images - ENHANCED VERSION"""
        try:
            print("Looking for expand/gallery buttons...")
            
            # Enhanced selectors for Kavyar-specific patterns
            expand_selectors = [
                # Standard buttons
                "button:has-text('Gallery')",
                "button:has-text('View Gallery')", 
                "button:has-text('Expand')",
                "button:has-text('Show More')",
                "button:has-text('Load More')",
                "button:has-text('View All')",
                "button:has-text('See All')",
                "button:has-text('More Photos')",
                
                # Class-based selectors
                ".gallery-expand", ".expand-gallery", ".view-gallery", ".show-gallery",
                ".gallery-trigger", ".expand-trigger", ".portfolio-expand",
                ".load-more", ".show-more", ".view-more",
                
                # Data attributes
                "[data-action='expand']", "[data-action='gallery']", "[data-action='load-more']",
                "[data-trigger='expand']", "[data-trigger='gallery']",
                
                # Aria labels
                "button[aria-label*='gallery']", "button[aria-label*='expand']",
                "button[aria-label*='more']", "button[aria-label*='load']",
                
                # Kavyar-specific patterns (observed from actual site)
                ".gallery-navigation button",
                ".image-navigation button", 
                ".portfolio-navigation button",
                ".work-navigation button",
                "button[class*='gallery']",
                "button[class*='expand']",
                "button[class*='load']",
                "button[class*='more']",
                
                # Generic clickable elements that might reveal content
                ".clickable", ".expandable", ".toggleable",
                "[role='button']", "a[href='#']",
                
                # Look for any button near images
                "img + button", "picture + button", ".image-container button"
            ]
            
            clicked_count = 0
            
            for selector in expand_selectors:
                try:
                    buttons = page.locator(selector)
                    button_count = await buttons.count()
                    
                    if button_count > 0:
                        print(f"Found {button_count} buttons with selector: {selector}")
                        
                        # Click all visible buttons with this selector
                        for i in range(button_count):
                            button = buttons.nth(i)
                            if await button.is_visible(timeout=1000):
                                await button.click()
                                clicked_count += 1
                                print(f"Clicked button {i+1} with selector: {selector}")
                                await page.wait_for_timeout(1000)  # Wait between clicks
                                
                except Exception as e:
                    # Continue if this selector fails
                    print(f"Error with selector {selector}: {e}")
                    continue
            
            # Also try clicking on any images that might be clickable to expand galleries
            try:
                clickable_images = page.locator("img[src*='thumb'], img[src*='preview'], img[src*='small']")
                img_count = await clickable_images.count()
                
                if img_count > 0:
                    print(f"Found {img_count} potentially clickable thumbnail images")
                    # Click first few thumbnail images (they might expand galleries)
                    for i in range(min(3, img_count)):
                        img = clickable_images.nth(i)
                        if await img.is_visible(timeout=1000):
                            await img.click()
                            clicked_count += 1
                            print(f"Clicked thumbnail image {i+1}")
                            await page.wait_for_timeout(1500)
                            
            except Exception as e:
                print(f"Error clicking thumbnail images: {e}")
            
            print(f"Total expand buttons/elements clicked: {clicked_count}")
            return clicked_count > 0
            
        except Exception as e:
            print(f"Error in _click_expand_buttons: {e}")
            traceback.print_exc()
            return False

    async def _click_navigation_controls(self, page: AsyncPage) -> bool:
        """Try to click navigation arrows, thumbnails, or other gallery controls to reveal more images"""
        try:
            print("Looking for navigation controls (arrows, thumbnails, etc.)...")
            
            # Kavyar-specific navigation selectors
            nav_selectors = [
                # Navigation arrows
                "button[aria-label*='next']", "button[aria-label*='previous']",
                "button[aria-label*='Next']", "button[aria-label*='Previous']", 
                ".next-button", ".prev-button", ".navigation-next", ".navigation-prev",
                "[class*='arrow']", "[class*='nav']", "[class*='slide']",
                
                # Gallery navigation
                ".gallery-nav button", ".image-nav button", ".work-nav button",
                ".thumbnail", ".thumb", "[class*='thumbnail']", "[class*='thumb']",
                
                # Pagination or carousel controls
                ".pagination button", ".carousel-control", ".slider-control",
                "[role='button'][aria-label*='image']", "[role='button'][aria-label*='photo']",
                
                # Generic clickable elements near images
                "img[role='button']", "img[onclick]", "img[data-click]",
                "figure[role='button']", "picture[role='button']",
                
                # Kavyar work page specific patterns (observed)
                ".work-images button", ".image-grid button", ".photo-nav button",
                "[data-action*='nav']", "[data-nav]", "[data-slide]"
            ]
            
            clicked_count = 0
            
            for selector in nav_selectors:
                try:
                    buttons = page.locator(selector)
                    button_count = await buttons.count()
                    
                    if button_count > 0:
                        print(f"Found {button_count} navigation elements with selector: {selector}")
                        
                        # Click up to 5 elements with this selector to avoid infinite loops
                        for i in range(min(button_count, 5)):
                            try:
                                await buttons.nth(i).click(timeout=2000)
                                clicked_count += 1
                                print(f"  Clicked navigation element {i+1}")
                                await page.wait_for_timeout(1000)  # Wait for content to load
                            except Exception as click_err:
                                print(f"  Failed to click navigation element {i+1}: {click_err}")
                                continue
                        
                        # Stop after first successful selector to avoid over-clicking
                        if clicked_count > 0:
                            break
                            
                except Exception as selector_err:
                    # Selector might be invalid, continue to next one
                    continue
            
            print(f"Total navigation elements clicked: {clicked_count}")
            return clicked_count > 0
        except Exception as e:
            print(f"Error clicking navigation controls: {e}")
            return False

    async def _click_kavyar_load_buttons(self, page: AsyncPage) -> bool:
        """Click Kavyar-specific load more buttons"""
        try:
            # Try multiple potential load more button selectors
            load_more_selectors = [
                "button:has-text('Load More')",
                "button:has-text('Show More')",
                "button.load-more",
                "[role='button']:has-text('more')",
                ".button:has-text('Load')",
                "[data-testid*='load-more']"
            ]
            
            for selector in load_more_selectors:
                try:
                    button = page.locator(selector).first
                    if await button.count() > 0 and await button.is_visible(timeout=1000):
                        print(f"Found load more button: {selector}")
                        await button.click()
                        print("Clicked load more button")
                        await page.wait_for_timeout(2000)
                        return True
                except Exception:
                    continue
            
            # Also try JavaScript click detection for buttons without clear selectors
            click_result = await page.evaluate("""
                () => {
                    // Look for button-like elements with text containing 'load' or 'more'
                    const buttonTexts = ['load more', 'show more', 'see more', 'view more', 'more'];
                    let clicked = false;
                    
                    // Try standard buttons first
                    document.querySelectorAll('button, [role="button"], .button, a.button').forEach(el => {
                        if (clicked) return;
                        
                        const text = (el.textContent || '').toLowerCase();
                        if (buttonTexts.some(btn => text.includes(btn))) {
                            el.click();
                            clicked = true;
                            console.log('Clicked button via JS:', text);
                        }
                    });
                    
                    return clicked;
                }
            """)
            
            if click_result:
                print("Clicked load more button via JavaScript")
                await page.wait_for_timeout(2000)
                return True
                
            return False
        except Exception as e:
            print(f"Error clicking load buttons: {e}")
            return False

    async def _perform_improved_login(self, page: AsyncPage) -> bool:
        """Improved login method that handles Kavyar's login flow better"""
        print("Attempting improved login to Kavyar...")
        try:
            # Wait a bit for any dynamic content
            await page.wait_for_timeout(2000)
            
            # Check if we're already logged in by looking for user indicators
            profile_selectors = [
                ".user-menu", ".profile-link", ".user-profile", ".avatar", 
                "[data-user]", ".logged-in", ".user-nav"
            ]
            
            for selector in profile_selectors:
                if await page.locator(selector).count() > 0:
                    print("Already logged in - user profile indicator found")
                    return True
            
            # Take a screenshot to see the current state
            try:
                debug_dir = os.path.dirname(os.path.abspath(__file__))
                os.makedirs(os.path.join(debug_dir, "debug"), exist_ok=True)
                screenshot_path = os.path.join(debug_dir, "debug", "kavyar_login_start.png")
                await page.screenshot(path=screenshot_path, full_page=True)
                print(f"Login start screenshot saved to: {screenshot_path}")
            except:
                pass
            
            # Look for email/username field with expanded selectors
            email_selectors = [
                "input[name='email']", "input[type='email']", "input[id*='email']",
                "input[placeholder*='email' i]", "input[placeholder*='Email']",
                "input[name='username']", "input[id*='username']",
                "input[placeholder*='username' i]", "input[placeholder*='Username']",
                "#email", "#username", ".email-input", ".username-input"
            ]
            
            email_field = None
            for selector in email_selectors:
                try:
                    field = page.locator(selector).first
                    if await field.count() > 0 and await field.is_visible(timeout=2000):
                        email_field = field
                        print(f"Found email field with selector: {selector}")
                        break
                except:
                    continue
            
            # Look for password field
            password_selectors = [
                "input[name='password']", "input[type='password']", "input[id*='password']",
                "input[placeholder*='password' i]", "input[placeholder*='Password']",
                "#password", ".password-input"
            ]
            
            password_field = None
            for selector in password_selectors:
                try:
                    field = page.locator(selector).first
                    if await field.count() > 0 and await field.is_visible(timeout=2000):
                        password_field = field
                        print(f"Found password field with selector: {selector}")
                        break
                except:
                    continue
            
            # If no fields found, try clicking login buttons to reveal them
            if not email_field or not password_field:
                print("Login fields not visible, trying to click login buttons...")
                login_buttons = [
                    "a:has-text('Log In')", "button:has-text('Log In')",
                    "a:has-text('Login')", "button:has-text('Login')",
                    "a:has-text('Sign In')", "button:has-text('Sign In')",
                    ".login-btn", ".login-button", "[href*='login']", "[data-action='login']"
                ]
                
                for selector in login_buttons:
                    try:
                        button = page.locator(selector).first
                        if await button.count() > 0 and await button.is_visible(timeout=1000):
                            print(f"Clicking login button: {selector}")
                            await button.click()
                            await page.wait_for_timeout(3000)  # Wait for form to appear
                            
                            # Try to find fields again
                            for email_sel in email_selectors:
                                try:
                                    field = page.locator(email_sel).first
                                    if await field.count() > 0 and await field.is_visible(timeout=1000):
                                        email_field = field
                                        print(f"Found email field after click: {email_sel}")
                                        break
                                except:
                                    continue
                            
                            for pass_sel in password_selectors:
                                try:
                                    field = page.locator(pass_sel).first
                                    if await field.count() > 0 and await field.is_visible(timeout=1000):
                                        password_field = field
                                        print(f"Found password field after click: {pass_sel}")
                                        break
                                except:
                                    continue
                            
                            if email_field and password_field:
                                break
                    except:
                        continue
            
            # Verify we have both fields
            if not email_field or not password_field:
                print(f"Login form incomplete - email field: {email_field is not None}, password field: {password_field is not None}")
                return False
            
            # Fill in credentials
            print(f"Filling login form with username: {self.username}")
            
            # Clear and fill email
            await email_field.click()
            await email_field.fill("")
            await page.wait_for_timeout(500)
            await email_field.type(self.username, delay=100)  # Type slowly
            
            await page.wait_for_timeout(1000)
            
            # Clear and fill password
            await password_field.click()
            await password_field.fill("")
            await page.wait_for_timeout(500)
            await password_field.type(self.password, delay=100)  # Type slowly
            
            await page.wait_for_timeout(1000)
            
            # Find submit button
            submit_selectors = [
                "button[type='submit']", "input[type='submit']",
                "button:has-text('Log In')", "button:has-text('Login')",
                "button:has-text('Sign In')", "button:has-text('Submit')",
                ".login-submit", ".submit-button", ".login-btn"
            ]
            
            submit_button = None
            for selector in submit_selectors:
                try:
                    button = page.locator(selector).first
                    if await button.count() > 0 and await button.is_visible(timeout=1000):
                        submit_button = button
                        print(f"Found submit button: {selector}")
                        break
                except:
                    continue
            
            if not submit_button:
                print("No submit button found, trying Enter key")
                await password_field.press("Enter")
            else:
                print("Clicking submit button")
                await submit_button.click()
            
            # Wait for login to process
            print("Waiting for login to process...")
            await page.wait_for_timeout(5000)
            
            # Check if login was successful
            current_url = page.url
            print(f"After login attempt, URL is: {current_url}")
            
            # Look for success indicators
            for selector in profile_selectors:
                if await page.locator(selector).count() > 0:
                    print("Login successful - user profile indicator found")
                    return True
            
            # Check if we're no longer on login page
            if 'login' not in current_url and 'start' not in current_url:
                print("Login appears successful - no longer on login page")
                return True
            
            print("Login status unclear - continuing anyway")
            return False
            
        except Exception as e:
            print(f"Error during improved login: {e}")
            traceback.print_exc()
            return False

    async def _perform_login(self, page: AsyncPage) -> bool:
        """Attempt to log in to Kavyar with improved error handling and detection"""
        print("Attempting to log in to Kavyar...")
        try:
            # First check if we're already logged in
            profile_indicator = page.locator(".profile-link, .user-profile, .avatar, .user-menu")
            profile_count = await profile_indicator.count()
            if profile_count > 0:
                print("Already logged in - profile indicator found")
                self.is_logged_in = True
                return True
                
            # Take screenshot for debugging if needed
            if self.debug_mode:
                try:
                    screenshot_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug_login.png")
                    await page.screenshot(path=screenshot_path, full_page=True)
                    print(f"Login page screenshot saved to: {screenshot_path}")
                except Exception as ss_err:
                    print(f"Failed to save debug screenshot: {ss_err}")
            
            # Look for login link/button
            login_selectors = [
                "a:has-text('Log In')", 
                "button:has-text('Log In')",
                "a:has-text('Login')",
                "button:has-text('Login')",
                ".login-link", 
                "[href*='login']"
            ]
            
            login_found = False
            for selector in login_selectors:
                login_button = page.locator(selector)
                login_count = await login_button.count()
                
                if login_count > 0 and await login_button.first.is_visible(timeout=1000):
                    print(f"Found login button with selector: {selector}")
                    # Click login to open the form
                    await login_button.first.click()
                    await page.wait_for_timeout(2000)  # Wait longer for form to appear
                    login_found = True
                    break
                    
            if not login_found:
                print("No login button found - checking if form is already visible")
                
            # Look for email/username field
            email_selectors = [
                "input[name='email']", 
                "input[type='email']",
                "input[placeholder*='Email']", 
                "input[id*='email']",
                "input[name='username']", 
                "input[id*='username']"
            ]
            
            email_field = None
            for selector in email_selectors:
                field = page.locator(selector)
                if await field.count() > 0 and await field.is_visible(timeout=1000):
                    email_field = field.first
                    print(f"Found email field with selector: {selector}")
                    break
                    
            # Look for password field
            password_selectors = [
                "input[name='password']", 
                "input[type='password']",
                "input[placeholder*='Password']"
            ]
            
            password_field = None
            for selector in password_selectors:
                field = page.locator(selector)
                if await field.count() > 0 and await field.is_visible(timeout=1000):
                    password_field = field.first
                    print(f"Found password field with selector: {selector}")
                    break
            
            # Verify we have both fields
            if not email_field or not password_field:
                print(f"Login form incomplete - email field: {email_field is not None}, password field: {password_field is not None}")
                return False
                
            # Get credentials
            if not hasattr(self, 'username') or not hasattr(self, 'password') or not self.username or not self.password:
                print("Missing credentials for login")
                return False
                
            # Clear and fill fields with humanlike delay
            print(f"Filling login form with username: {self.username}")
            await email_field.click()
            await email_field.fill("")
            await page.wait_for_timeout(random.randint(200, 400))
            await email_field.fill(self.username)
            
            await page.wait_for_timeout(random.randint(500, 800))
            
            await password_field.click()
            await password_field.fill("")
            await page.wait_for_timeout(random.randint(200, 400))
            await password_field.fill(self.password)
            
            # Find and click submit button
            submit_selectors = [
                "button[type='submit']", 
                "button:has-text('Log In')", 
                "button:has-text('Login')",
                "button:has-text('Sign In')", 
                "input[type='submit']",
                "button.login-button",
                "button.submit-button",
                ".login-form button"
            ]
            
            submit_button = None
            for selector in submit_selectors:
                button = page.locator(selector)
                if await button.count() > 0 and await button.first.is_visible(timeout=1000):
                    submit_button = button.first
                    print(f"Found submit button with selector: {selector}")
                    break
                    
            if not submit_button:
                print("Submit button not found")
                return False
                
            # Click the submit button
            await submit_button.click()
            print("Clicked submit button")
            
            # Wait for navigation or login success
            try:
                # Wait for either navigation or a profile indicator to appear
                print("Waiting for login to complete...")
                await page.wait_for_navigation(timeout=10000)
            except Exception as nav_error:
                print(f"Navigation wait failed: {nav_error}")
                # Check if we're still logging in anyway
            
            # Verify login success
            await page.wait_for_timeout(3000)  # Additional wait for page to settle
            
            # Check for profile indicators again
            profile_indicator = page.locator(".profile-link, .user-profile, .avatar, .user-menu")
            profile_count = await profile_indicator.count()
            
            self.is_logged_in = profile_count > 0
            
            # Check for login errors
            if not self.is_logged_in:
                error_message = page.locator(".error-message, .alert-danger, [role='alert']")
                if await error_message.count() > 0 and await error_message.first.is_visible():
                    error_text = await error_message.first.inner_text()
                    print(f"Login failed: {error_text}")
                else:
                    print("Login failed: No profile indicator found after login attempt")
            else:
                print("Login successful!")
                
            return self.is_logged_in
            
        except Exception as e:
            print(f"Login error: {e}")
            traceback.print_exc()
            return False
    
    async def _smart_scroll_page(self, page: AsyncPage) -> None:
        """Intelligently scroll the page to load all dynamic content"""
        try:
            print(f"Starting smart scrolling with {self.max_scroll_count} max scrolls")
            
            # Function to detect when page has stabilized
            async def is_page_stable():
                # Get metrics before and after a short wait
                content_count_before = await page.evaluate("""
                    () => document.querySelectorAll('img, video, audio').length
                """)
                await page.wait_for_timeout(500)
                content_count_after = await page.evaluate("""
                    () => document.querySelectorAll('img, video, audio').length
                """)
                return content_count_before == content_count_after
            
            # Main scrolling loop with dynamic detection
            prev_height = 0
            for i in range(self.max_scroll_count):
                # Get current scroll height
                curr_height = await page.evaluate("document.body.scrollHeight")
                
                # Break if height hasn't changed for 2 consecutive scrolls
                if curr_height == prev_height and await is_page_stable():
                    print(f"Page stabilized after {i} scrolls")
                    break
                
                # Remember current height
                prev_height = curr_height
                
                # Scroll with human-like behavior
                await page.evaluate("""
                    () => {
                        // Random scroll amount between 80-100% of viewport
                        const scrollAmount = window.innerHeight * (0.8 + Math.random() * 0.2);
                        window.scrollBy(0, scrollAmount);
                    }
                """)
                
                # Add small variation to scroll delay for human-like behavior
                delay_variation = random.randint(-200, 200)
                actual_delay = max(500, self.scroll_delay_ms + delay_variation)
                await page.wait_for_timeout(actual_delay)
                
                # Look for and click load more buttons
                await self._click_load_more_buttons(page)
            
            # Final scroll to bottom
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(self.scroll_delay_ms)
            
            # Final attempt to click load more buttons
            await self._click_load_more_buttons(page)
            
            print("Smart scrolling complete")
        except Exception as e:
            print(f"Error during smart scrolling: {e}")
    
    async def _click_load_more_buttons(self, page: AsyncPage) -> None:
        """Click various forms of 'load more' buttons"""
        load_more_selectors = [
            "button:has-text('Load More')",
            "a:has-text('Load More')",
            "button:has-text('Show More')",
            "a:has-text('Show More')",
            ".load-more",
            ".show-more",
            "[data-action='load-more']"
        ]
        
        for selector in load_more_selectors:
            load_more_button = page.locator(selector)
            if await load_more_button.count() > 0:
                try:
                    # Check if button is visible
                    if await load_more_button.first.is_visible():
                        await load_more_button.first.click()
                        await page.wait_for_timeout(self.scroll_delay_ms * 2)
                        # Wait for new content to load
                        await page.wait_for_function("""
                            () => !document.querySelector('.loading, .spinner, .loader, [aria-busy="true"]')
                        """, timeout=5000)
                except Exception as e:
                    print(f"Error clicking load more button: {e}")
    
    async def _extract_all_media(self, page: AsyncPage, **kwargs) -> List[Dict]:
        """Extract all media items with enhanced metadata and debugging"""
        media_items = []
        min_width = kwargs.get('min_width', 0)
        min_height = kwargs.get('min_height', 0)
        extract_metadata = kwargs.get('extract_metadata', True)
        
        # Create a cache to avoid duplicates
        url_cache = set()
        
        print(f"Starting comprehensive media extraction from {page.url}")
        
        # 1. Extract images with improved metadata
        await self._extract_images(page, media_items, url_cache, min_width, min_height, extract_metadata)
        
        # 2. Extract videos with improved metadata (if enabled)
        if kwargs.get('download_videos', True):
            await self._extract_videos(page, media_items, url_cache, extract_metadata)
        
        # 3. Extract audio with improved metadata (if enabled)
        if kwargs.get('download_audio', True):
            await self._extract_audio(page, media_items, url_cache, extract_metadata)
        
        # 4. Extract background images and CSS images
        await self._extract_css_images(page, media_items, url_cache)
        
        # 5. Extract publication metadata to enhance all media items
        publication_metadata = await self._extract_publication_metadata(page)
        
        # If we didn't find anything with standard methods, try deeper inspection
        if not media_items:
            print("No media found with standard methods. Trying deep inspection...")
            await self._extract_with_deep_inspection(page, media_items, url_cache, min_width, min_height)
        
        # Enhance all items with publication metadata
        if publication_metadata and extract_metadata:
            for item in media_items:
                if 'credits' not in item or not item['credits']:
                    item['credits'] = publication_metadata.get('credits', '')
                item['source_url'] = self.url
                item['publication'] = publication_metadata.get('title', '')
                item['publisher'] = publication_metadata.get('publisher', '')
        
        print(f"Extracted {len(media_items)} total media items from Kavyar")
        
        # If we found no items at all, take a debug screenshot
        if not media_items and self.debug_mode:
            try:
                debug_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug")
                os.makedirs(debug_dir, exist_ok=True)
                ss_path = os.path.join(debug_dir, f"kavyar_extraction_failed_{int(time.time())}.png")
                await page.screenshot(path=ss_path, full_page=True)
                print(f"Debug screenshot saved to: {ss_path}")
                
                # Also save HTML for inspection
                html_path = os.path.join(debug_dir, f"kavyar_page_{int(time.time())}.html")
                html_content = await page.content()
                with open(html_path, 'w', encoding='utf-8') as f:
                    f.write(html_content)
                print(f"Debug HTML saved to: {html_path}")
            except Exception as ss_err:
                print(f"Failed to save debug files: {ss_err}")
        
        return media_items

    async def _extract_current_page_images(self, page: AsyncPage, media_items: List[Dict], url_cache: set) -> None:
        """Extract images from the current page (for profile pages or main galleries) - AGGRESSIVE VERSION"""
        try:
            print("=== AGGRESSIVE IMAGE EXTRACTION ===")
            
            # First, get page info for debugging
            page_title = await page.title()
            page_url = page.url
            print(f"Page: {page_title} | URL: {page_url}")
            
            # Get ALL images on the page first
            all_page_images = await page.evaluate('''
                () => {
                    const images = [];
                    document.querySelectorAll('img').forEach(img => {
                        const rect = img.getBoundingClientRect();
                        images.push({
                            src: img.src,
                            alt: img.alt || '',
                            visible: rect.width > 0 && rect.height > 0,
                            width: img.naturalWidth || img.width || rect.width,
                            height: img.naturalHeight || img.height || rect.height,
                            dataset: Object.assign({}, img.dataset),
                            className: img.className
                        });
                    });
                    return images;
                }
            ''')
            
            print(f"Total images found on page: {len(all_page_images)}")
            
            # Show details about ALL images for debugging
            for i, img in enumerate(all_page_images):
                src_short = img['src'][:60] + '...' if len(img['src']) > 60 else img['src']
                print(f"  {i+1}. {src_short}")
                print(f"      visible: {img['visible']}, size: {img['width']}x{img['height']}")
                print(f"      class: {img['className']}")
                if 'cloudfront' in img['src']:
                    print(f"      *** CLOUDFRONT IMAGE FOUND! ***")
            
            # Look for CloudFront images (Kavyar's CDN) - MORE AGGRESSIVE
            cloudfront_images = await page.evaluate('''
                () => {
                    const images = [];
                    // Method 1: Direct img tags
                    document.querySelectorAll('img').forEach(img => {
                        if (img.src && img.src.includes('cloudfront')) {
                            const rect = img.getBoundingClientRect();
                            images.push({
                                src: img.src,
                                alt: img.alt || '',
                                width: img.naturalWidth || img.width || rect.width,
                                height: img.naturalHeight || img.height || rect.height,
                                visible: rect.width > 0 && rect.height > 0,
                                method: 'img_tag'
                            });
                        }
                    });
                    
                    // Method 2: Data attributes that might contain cloudfront URLs
                    document.querySelectorAll('*[data-src*="cloudfront"], *[data-original*="cloudfront"], *[data-lazy*="cloudfront"]').forEach(el => {
                        const src = el.dataset.src || el.dataset.original || el.dataset.lazy;
                        if (src) {
                            images.push({
                                src: src,
                                alt: el.alt || el.title || '',
                                width: 0,
                                height: 0,
                                visible: true,
                                method: 'data_attribute'
                            });
                        }
                    });
                    
                    // Method 3: Look in background images
                    const elementsWithBg = document.querySelectorAll('*');
                    elementsWithBg.forEach(el => {
                        const style = window.getComputedStyle(el);
                        const bgImage = style.backgroundImage;
                        if (bgImage && bgImage.includes('cloudfront')) {
                            const urlMatch = bgImage.match(/url\\(["']?([^"')]+)["']?\\)/);
                            if (urlMatch && urlMatch[1]) {
                                images.push({
                                    src: urlMatch[1],
                                    alt: el.alt || el.title || '',
                                    width: 0,
                                    height: 0,
                                    visible: true,
                                    method: 'background_image'
                                });
                            }
                        }
                    });
                    
                    // Method 4: Look in the page source/HTML for any cloudfront URLs
                    const pageHtml = document.documentElement.outerHTML;
                    const cloudFrontMatches = pageHtml.match(/https:\\/\\/[^\\s"']*cloudfront[^\\s"']*/g) || [];
                    cloudFrontMatches.forEach(url => {
                        // Only add image URLs (not CSS/JS)
                        if (url.match(/\\.(jpg|jpeg|png|webp|gif)([?#].*)?$/i)) {
                            images.push({
                                src: url,
                                alt: '',
                                width: 0,
                                height: 0,
                                visible: true,
                                method: 'html_parsing'
                            });
                        }
                    });
                    
                    return images;
                }
            ''')
            
            print(f"CloudFront images found: {len(cloudfront_images)}")
            
            # Process the CloudFront images
            for i, img_data in enumerate(cloudfront_images):
                url = img_data.get('src', '')
                if not url or url in url_cache:
                    continue
                    
                url_cache.add(url)
                
                print(f"Processing CloudFront image {i+1}: {url} (method: {img_data.get('method', 'unknown')})")
                
                # Try to get the highest resolution version
                high_res_url = self._get_highest_res_url(url)
                if high_res_url != url:
                    print(f"  Enhanced to: {high_res_url}")
                
                # Parse metadata from alt text
                alt_text = img_data.get('alt', '')
                title = alt_text
                credits = ""
                
                if "by" in alt_text and "," in alt_text:
                    parts = alt_text.split("by", 1)
                    if len(parts) == 2:
                        title = parts[0].strip()
                        credits = parts[1].strip()
                
                # Create media item
                media_item = {
                    'url': high_res_url or url,
                    'type': 'image',
                    'title': title or "Image from Kavyar",
                    'alt': alt_text,
                    'credits': credits,
                    'width': img_data.get('width', 0),
                    'height': img_data.get('height', 0),
                    'source_url': page.url,
                    'extraction_method': img_data.get('method', 'unknown')
                }
                
                media_items.append(media_item)
                print(f"  Added image: {title}")
            
            print(f"=== EXTRACTION COMPLETE: {len(media_items)} images added to collection ===")
            print(f"(Found {len(cloudfront_images)} CloudFront URLs, filtered to {len(media_items)} unique items)")
            
            # Debug: Show breakdown of image types found
            if media_items:
                large_images = [item for item in media_items if item.get('width', 0) > 512 or item.get('height', 0) > 512]
                small_images = [item for item in media_items if item.get('width', 0) <= 512 and item.get('height', 0) <= 512]
                
                print(f"📊 IMAGE BREAKDOWN:")
                print(f"  Large images (>512px): {len(large_images)}")
                print(f"  Small images (≤512px): {len(small_images)} (will be filtered out)")
                
                if large_images:
                    print(f"  🎯 Content images that should download successfully: {len(large_images)}")
                    for img in large_images[:3]:  # Show first 3
                        print(f"    - {img.get('title', 'Untitled')} ({img.get('width', '?')}x{img.get('height', '?')})")
                else:
                    print(f"  ⚠️  WARNING: No large content images found! May indicate navigation/discovery issue.")
                
        except Exception as e:
            print(f"Error extracting current page images: {e}")
            traceback.print_exc()

    async def _extract_detail_page_images(self, page: AsyncPage, media_items: List[Dict], url_cache: set) -> None:
        """Extract high-resolution images from a Kavyar detail page"""
        try:
            # First, look for the image stack/carousel that appears in detail view
            stack_images = await page.evaluate("""
                () => {
                    const images = [];
                    // Look for the main image container in detail view
                    document.querySelectorAll('img[src*="cloudfront.net"]').forEach(img => {
                        // Check if this is likely a full-size image (filter out thumbnails)
                        const rect = img.getBoundingClientRect();
                        if (rect.width > 300 || rect.height > 300) {  // Adjust threshold as needed
                            images.push({
                                src: img.src,
                                alt: img.alt || '',
                                width: img.naturalWidth || img.width || 0,
                                height: img.naturalHeight || img.height || 0
                            });
                        }
                    });
                    return images;
                }
            """)
            
            print(f"Found {len(stack_images)} stack images on detail page")
            
            # Process the stack images
            for img_data in stack_images:
                url = img_data.get('src', '')
                if not url or url in url_cache:
                    continue
                    
                url_cache.add(url)
                
                # Try to get the highest resolution version by modifying URL patterns
                # Kavyar might use URL patterns like _800x1200 to indicate size
                high_res_url = self._get_highest_res_url(url)
                
                # Parse metadata from alt text
                alt_text = img_data.get('alt', '')
                title = alt_text
                credits = ""
                
                if "by" in alt_text:
                    parts = alt_text.split("by", 1)
                    if len(parts) == 2:
                        title = parts[0].strip()
                        credits = parts[1].strip()
                
                # Create media item
                media_items.append({
                    'url': high_res_url or url,
                    'type': 'image',
                    'title': title or "Image from Kavyar",
                    'alt': alt_text,
                    'credits': credits,
                    'width': img_data.get('width', 0),
                    'height': img_data.get('height', 0),
                    'source_url': page.url
                })
                
            # Get the page title for metadata
            page_title = await page.title()
            
            # If no images found in stack, try other methods
            if not stack_images:
                print("No stack images found, trying fallback methods")
                # Add your fallback methods here
                
        except Exception as e:
            print(f"Error extracting detail page images: {e}")
            traceback.print_exc()

    def _get_highest_res_url(self, url: str) -> str:
        """
        Try to get the highest resolution version of a Kavyar image URL
        by modifying size parameters in the URL.
        
        Handles patterns like:
        - https://dfocupmdlnlkc.cloudfront.net/original/2dd3477d-5339-44bf-aea2-b5f1f484de99_800x1200q75.jpg
        - https://dfocupmdlnlkc.cloudfront.net/original/d09fa66e-c1d8-4246-ac56-5dbfd42ac6a3_800x1200q75_jpg.webp
        """
        try:
            # Pattern 1: _800x1200q75.jpg or similar size specifications
            size_match = re.search(r'_(\d+)x(\d+)q(\d+)', url)
            if size_match:
                # Extract the base URL without size and quality
                base_url = url[:size_match.start()]
                extension = url[url.rfind('.'):]
                
                # Check if this is a webp file with embedded format (common Kavyar pattern)
                if '_jpg.webp' in url:
                    # For _jpg.webp files, prefer fallback to .jpg which tends to work better
                    high_res_url = f"{base_url}_2000x3000q90.jpg"
                    return high_res_url
                elif '_png.webp' in url:
                    # For _png.webp files, prefer fallback to .png which tends to work better
                    high_res_url = f"{base_url}_2000x3000q90.png"
                    return high_res_url
                
                # Try different high resolution versions
                # First try without any size restrictions (original)
                original_url = f"{base_url}{extension}"
                
                # Also try common high-res sizes
                high_res_variants = [
                    f"{base_url}_2000x3000q90{extension}",
                    f"{base_url}_1600x2400q90{extension}", 
                    f"{base_url}_1200x1800q90{extension}",
                    original_url  # Original without size params
                ]
                
                # Return the first variant (highest res)
                return high_res_variants[0]
            
            # Pattern 2: _800x1200q75_jpg.webp (extension in filename)
            size_match2 = re.search(r'_(\d+)x(\d+)q(\d+)_([a-z]+)\.([a-z]+)$', url)
            if size_match2:
                base_url = url[:size_match2.start()]
                original_ext = size_match2.group(4)  # jpg
                current_ext = size_match2.group(5)   # webp
                
                # Try original format without size restrictions
                original_url = f"{base_url}.{original_ext}"
                high_res_url = f"{base_url}_2000x3000q95.{original_ext}"
                
                return high_res_url
            
            # If no size parameters found, try to get original by removing common suffixes
            if '_thumb' in url or '_small' in url or '_medium' in url:
                # Remove thumbnail indicators
                clean_url = re.sub(r'_(thumb|small|medium|preview)', '', url)
                return clean_url
            
            return url  # Return original if no modification needed
        except Exception as e:
            print(f"Error processing URL for higher resolution: {e}")
            return url  # Return original URL on any error

    async def _extract_images(self, page: AsyncPage, media_items: List[Dict], url_cache: set, 
                            min_width: int, min_height: int, extract_metadata: bool) -> None:
        """Extract image elements with focus on Kavyar's picture element structure"""
        try:
            print("Beginning image extraction from Kavyar page with focus on picture elements...")
            
            # First, let's target the specific picture structure we identified
            kavyar_picture_selector = "picture > img[src], picture > source[srcset]"
            
            # Count all picture elements first
            picture_count = await page.locator("picture").count()
            img_count = await page.locator(kavyar_picture_selector).count()
            
            print(f"Found {picture_count} picture elements and {img_count} img/source elements within them")
            
            # Extract both source and img elements from pictures
            elements = page.locator(kavyar_picture_selector)
            
            for i in range(await elements.count()):
                try:
                    element = elements.nth(i)
                    
                    # Check if we're dealing with source or img
                    tag_name = await element.evaluate("el => el.tagName.toLowerCase()")
                    
                    # Extract URL based on element type
                    if tag_name == "source":
                        src = await element.get_attribute("srcset")
                    else:  # img
                        src = await element.get_attribute("src")
                    
                    # Skip invalid URLs
                    if not src or src.startswith('data:'):
                        continue
                    
                    print(f"Processing {tag_name} element {i+1}: {src[:60]}...")
                    
                    # Skip already processed URLs
                    if src in url_cache:
                        print(f"  Skipping - already processed")
                        continue
                    
                    # Skip common non-content URLs
                    if any(x in src.lower() for x in ['placeholder', 'tracking', 'icon', 'logo', 'avatar']):
                        print(f"  Skipping - appears to be a placeholder or icon")
                        continue
                    
                    # Extract alt text from img or from parent img if we're on a source
                    alt_text = ""
                    if tag_name == "img":
                        alt_text = await element.get_attribute("alt") or ""
                    else:
                        # For source elements, look for sibling img
                        img_sibling = page.locator("picture > img").nth(i)
                        if await img_sibling.count() > 0:
                            alt_text = await img_sibling.get_attribute("alt") or ""
                    
                    # Get dimensions - for images
                    width = height = 0
                    try:
                        if tag_name == "img":
                            width = await element.evaluate("el => el.naturalWidth || el.width")
                            height = await element.evaluate("el => el.naturalHeight || el.height")
                        else:
                            # For source elements, we don't have direct width/height
                            # Try to parse from style if available or from srcset
                            srcset = await element.get_attribute("srcset")
                            if srcset and "x" in srcset:
                                # Extract dimensions from URL pattern like _800x1200
                                dimensions_match = re.search(r'_(\d+)x(\d+)', srcset)
                                if dimensions_match:
                                    width = int(dimensions_match.group(1))
                                    height = int(dimensions_match.group(2))
                    except Exception as dim_err:
                        print(f"  Error getting dimensions: {dim_err}")
                    
                    # Skip images that don't meet minimum dimension requirements
                    if (min_width > 0 and width > 0 and width < min_width) or \
                    (min_height > 0 and height > 0 and height < min_height):
                        print(f"  Skipping - below minimum dimensions ({width}x{height})")
                        continue
                    
                    # Add to URL cache
                    url_cache.add(src)
                    
                    # Parse title and credits from alt text (Kavyar specific format)
                    # Example: "Photo by Mob Journal, MICHAEL HIGGINS"
                    title = alt_text
                    credits = ""
                    
                    if alt_text and "by" in alt_text:
                        parts = alt_text.split("by", 1)
                        if len(parts) == 2:
                            title = parts[0].strip()
                            credits = parts[1].strip()
                    
                    # Create the media item
                    media_item = {
                        'url': src,
                        'type': 'image',
                        'title': title or "Image from Kavyar",
                        'alt': alt_text,
                        'credits': credits,
                        'width': width,
                        'height': height,
                        'source_url': page.url
                    }
                    
                    # Add to results
                    media_items.append(media_item)
                    print(f"  Added image: {title} ({width}x{height})")
                    
                except Exception as item_err:
                    print(f"  Error processing individual element: {item_err}")
            
            # Also gather any standalone images (without picture elements)
            standalone_img_selector = "img:not(picture > img)"
            standalone_count = await page.locator(standalone_img_selector).count()
            print(f"Checking {standalone_count} standalone img elements (outside picture tags)")
            
            if standalone_count > 0:
                standalone_imgs = page.locator(standalone_img_selector)
                for i in range(standalone_count):
                    try:
                        img = standalone_imgs.nth(i)
                        
                        # Get image URL
                        src = await img.get_attribute("src")
                        
                        # Skip invalid or already processed URLs
                        if not src or src.startswith('data:') or src in url_cache:
                            continue
                        
                        # Cloudfront detection - Kavyar images are often on cloudfront
                        if "cloudfront.net" in src:
                            print(f"Found cloudfront image: {src[:60]}...")
                            
                            alt_text = await img.get_attribute("alt") or ""
                            
                            # Get dimensions
                            width = height = 0
                            try:
                                width = await img.evaluate("el => el.naturalWidth || el.width")
                                height = await img.evaluate("el => el.naturalHeight || el.height")
                            except Exception:
                                pass
                            
                            # Skip small images and images below min dimensions
                            if (width > 0 and height > 0 and (width < 100 or height < 100)) or \
                            (min_width > 0 and width > 0 and width < min_width) or \
                            (min_height > 0 and height > 0 and height < min_height):
                                continue
                            
                            # Add to URL cache
                            url_cache.add(src)
                            
                            # Parse title and credits from alt text
                            title = alt_text
                            credits = ""
                            
                            if alt_text and "by" in alt_text:
                                parts = alt_text.split("by", 1)
                                if len(parts) == 2:
                                    title = parts[0].strip()
                                    credits = parts[1].strip()
                            
                            # Create the media item
                            media_item = {
                                'url': src,
                                'type': 'image',
                                'title': title or "Image from Kavyar",
                                'alt': alt_text,
                                'credits': credits,
                                'width': width,
                                'height': height,
                                'source_url': page.url
                            }
                            
                            # Add to results
                            media_items.append(media_item)
                    except Exception as standalone_err:
                        continue
                        
            # Look specifically for cloudfront URLs in any elements (direct targeting)
            cloudfront_js = """() => {
                const results = [];
                // Find any element with attributes containing cloudfront.net URLs
                document.querySelectorAll('*').forEach(el => {
                    if (el.tagName === 'SOURCE' || el.tagName === 'IMG') {
                        for (const attr of el.attributes) {
                            if (attr.value && 
                                typeof attr.value === 'string' && 
                                attr.value.includes('cloudfront.net') && 
                                (attr.value.includes('.jpg') || 
                                attr.value.includes('.webp') || 
                                attr.value.includes('.png'))) {
                                
                                // Get alt text from parent img if available
                                let altText = '';
                                if (el.tagName === 'SOURCE' && el.parentElement && 
                                    el.parentElement.tagName === 'PICTURE') {
                                    const img = el.parentElement.querySelector('img');
                                    if (img) {
                                        altText = img.alt || '';
                                    }
                                } else if (el.tagName === 'IMG') {
                                    altText = el.alt || '';
                                }
                                
                                results.push({
                                    url: attr.value,
                                    alt: altText,
                                    tag: el.tagName.toLowerCase(),
                                    attribute: attr.name
                                });
                            }
                        }
                    }
                });
                return results;
            }"""
            
            cloudfront_results = await page.evaluate(cloudfront_js)
            print(f"Direct cloudfront search found {len(cloudfront_results)} image URLs")
            
            # Process cloudfront results
            for item in cloudfront_results:
                url = item.get('url')
                if url and url not in url_cache:
                    url_cache.add(url)
                    
                    alt_text = item.get('alt', '')
                    title = alt_text
                    credits = ""
                    
                    if alt_text and "by" in alt_text:
                        parts = alt_text.split("by", 1)
                        if len(parts) == 2:
                            title = parts[0].strip()
                            credits = parts[1].strip()
                    
                    media_items.append({
                        'url': url,
                        'type': 'image',
                        'title': title or "Image from Kavyar",
                        'alt': alt_text,
                        'credits': credits,
                        'source_url': page.url
                    })
            
            print(f"Total images extracted: {len(media_items)}")
        except Exception as e:
            print(f"Error extracting images: {e}")
            traceback.print_exc()
    
    async def _extract_videos(self, page: AsyncPage, media_items: List[Dict], url_cache: set, extract_metadata: bool) -> None:
        """Extract video elements with enhanced metadata"""
        try:
            # Target both direct video elements and video containers
            video_selectors = [
                "video",
                ".video-container video",
                ".media-container video"
            ]
            
            for selector in video_selectors:
                video_elements = page.locator(selector)
                count = await video_elements.count()
                for i in range(count):
                    vid = video_elements.nth(i)
                    
                    # Get direct src attribute
                    src = await vid.get_attribute("src")
                    
                    # If no direct src, check for source elements
                    if not src:
                        source_elem = vid.locator("source")
                        if await source_elem.count() > 0:
                            src = await source_elem.first.get_attribute("src")
                    
                    if not src:
                        continue
                        
                    # Skip already processed URLs
                    if src in url_cache:
                        continue
                    url_cache.add(src)
                    
                    # Extract metadata
                    title_text = (await vid.get_attribute("title")) or ""
                    poster_url = await vid.get_attribute("poster") or ""
                    
                    # Get more context if metadata is enabled
                    caption = credits = ""
                    if extract_metadata:
                        # Look for parent container with metadata
                        try:
                            parent = page.locator(f".video-player, .video-container, .media-container >> video[src='{src}']").first
                            
                            if await parent.count() > 0:
                                # Try to get caption/title elements
                                caption_elem = parent.locator(".caption, .title, [class*='title'], [class*='caption']")
                                if await caption_elem.count() > 0:
                                    caption = await caption_elem.inner_text()
                                
                                # Look for credits
                                credits_elem = parent.locator(".credits, .author, [class*='credit'], [class*='author']")
                                if await credits_elem.count() > 0:
                                    credits = await credits_elem.inner_text()
                        except:
                            pass
                    
                    # Use best available text for title
                    title = caption.strip() or title_text.strip() or f"Video from Kavyar"
                    
                    # Create the media item
                    media_item = {
                        'url': src,
                        'type': 'video',
                        'title': title,
                        'credits': credits.strip(),
                        'poster': poster_url
                    }
                    
                    media_items.append(media_item)
        except Exception as e:
            print(f"Error extracting videos: {e}")
    
    async def _extract_audio(self, page: AsyncPage, media_items: List[Dict], url_cache: set, extract_metadata: bool) -> None:
        """Extract audio elements with enhanced metadata"""
        try:
            audio_elements = page.locator("audio")
            count = await audio_elements.count()
            for i in range(count):
                aud = audio_elements.nth(i)
                
                # Get direct src attribute
                src = await aud.get_attribute("src")
                
                # If no direct src, check for source elements
                if not src:
                    source_elem = aud.locator("source")
                    if await source_elem.count() > 0:
                        src = await source_elem.first.get_attribute("src")
                
                if not src:
                    continue
                    
                # Skip already processed URLs
                if src in url_cache:
                    continue
                url_cache.add(src)
                
                # Extract metadata
                title_text = (await aud.get_attribute("title")) or ""
                
                # Get more context if metadata is enabled
                caption = credits = ""
                if extract_metadata:
                    try:
                        parent = page.locator(f".audio-player, .audio-container >> audio[src='{src}']").first
                        
                        if await parent.count() > 0:
                            # Try to get caption/title elements
                            caption_elem = parent.locator(".caption, .title, [class*='title'], [class*='caption']")
                            if await caption_elem.count() > 0:
                                caption = await caption_elem.inner_text()
                            
                            # Look for credits
                            credits_elem = parent.locator(".credits, .author, [class*='credit'], [class*='author']")
                            if await credits_elem.count() > 0:
                                credits = await credits_elem.inner_text()
                    except:
                        pass
                
                # Use best available text for title
                title = caption.strip() or title_text.strip() or f"Audio from Kavyar"
                
                # Create the media item
                media_item = {
                    'url': src,
                    'type': 'audio',
                    'title': title,
                    'credits': credits.strip()
                }
                
                media_items.append(media_item)
        except Exception as e:
            print(f"Error extracting audio: {e}")
    
    async def _extract_css_images(self, page: AsyncPage, media_items: List[Dict], url_cache: set) -> None:
        """Extract images from CSS background-image properties and other sources"""
        try:
            # Get background images using JavaScript
            bg_urls = await page.evaluate("""
                () => {
                    const bgUrls = [];
                    const processedUrls = new Set();
                    
                    // Process background-image styles
                    document.querySelectorAll('[style*="background-image"]').forEach(el => {
                        // Skip tiny elements (likely icons)
                        if (el.offsetWidth < 60 || el.offsetHeight < 60) return;
                        
                        const style = window.getComputedStyle(el);
                        const bg = style.getPropertyValue('background-image');
                        if(bg && bg.startsWith('url(')) {
                            // Extract URL from background-image
                            let url = bg.slice(4, -1).replace(/["']/g, "");
                            
                            // Skip data URLs, small icons, and tracking pixels
                            if(!url || url.startsWith('data:') || 
                               url.includes('icon') || url.includes('logo') || 
                               url.includes('placeholder')) return;
                               
                            if (!processedUrls.has(url)) {
                                processedUrls.add(url);
                                
                                // Get any available caption from parent or sibling elements
                                let caption = '';
                                const captionElem = el.querySelector('.caption') || 
                                                   el.parentElement?.querySelector('.caption');
                                if (captionElem) {
                                    caption = captionElem.textContent.trim();
                                }
                                
                                bgUrls.push({
                                    url: url,
                                    width: el.offsetWidth,
                                    height: el.offsetHeight,
                                    caption: caption
                                });
                            }
                        }
                    });
                    
                    return bgUrls;
                }
            """)
            
            # Process the extracted background images
            for bg_item in bg_urls:
                url = bg_item.get('url')
                
                # Skip if already processed
                if url in url_cache:
                    continue
                url_cache.add(url)
                
                # Create the media item
                media_item = {
                    'url': url,
                    'type': 'image',
                    'title': bg_item.get('caption') or "Background image from Kavyar",
                    'width': bg_item.get('width', 0),
                    'height': bg_item.get('height', 0)
                }
                
                media_items.append(media_item)
        except Exception as e:
            print(f"Error extracting CSS images: {e}")
    
    async def _extract_publication_metadata(self, page: AsyncPage) -> Dict:
        """Extract metadata about the publication itself"""
        metadata = {
            'title': '',
            'publisher': 'Kavyar',
            'credits': '',
            'description': ''
        }
        
        try:
            # Get page title
            metadata['title'] = await page.title()
            
            # Try to extract more specific publication info
            try:
                # Publication title
                title_elem = page.locator("h1, .publication-title, .journal-title")
                if await title_elem.count() > 0:
                    metadata['title'] = await title_elem.first.inner_text()
                
                # Publisher/Editor
                publisher_elem = page.locator(".publisher, .editor, [class*='publisher'], [class*='editor']")
                if await publisher_elem.count() > 0:
                    metadata['publisher'] = await publisher_elem.first.inner_text()
                
# Credits
                credits_elem = page.locator(".credits, .team, [class*='credit'], [class*='team']")
                if await credits_elem.count() > 0:
                    metadata['credits'] = await credits_elem.first.inner_text()
                
                # Description
                desc_elem = page.locator(".description, .about, [class*='desc'], [class*='about']")
                if await desc_elem.count() > 0:
                    metadata['description'] = await desc_elem.first.inner_text()
            except Exception as inner_e:
                print(f"Error extracting detailed publication metadata: {inner_e}")
        except Exception as e:
            print(f"Error extracting publication metadata: {e}")
        
        return metadata
    
    def prefers_api(self) -> bool:
        """
        Indicates if this handler prefers API extraction over browser-based extraction.
        For Kavyar, browser extraction is more reliable.
        """
        return False
    
    def get_content_directory(self) -> tuple:
        """Returns the base directory and content-specific directory for organizing downloads"""
        parsed_url = urlparse(self.url)
        path_parts = parsed_url.path.strip('/').split('/')
        
        # Base is 'kavyar'
        base_dir = 'kavyar'
        
        # Content dir is based on the path components
        content_dir = '_'.join(path_parts) if path_parts else 'mob_journal'
        
        return base_dir, content_dir
    
    # Optional: API extraction for completeness (not implemented for Kavyar)
    async def extract_api_data_async(self, **kwargs):
        """
        Kavyar doesn't have a public API to extract data from.
        This is a placeholder for API-based extraction.
        """
        raise NotImplementedError("Kavyar doesn't support API extraction")

    async def _rate_limit(self):
        """Implement polite delay between actions to avoid overloading the server"""
        current_time = time.time() * 1000  # Convert to ms
        elapsed = current_time - self.last_request_time
        
        if elapsed < self.request_delay_ms:
            delay = self.request_delay_ms - elapsed
            await asyncio.sleep(delay / 1000)  # Convert back to seconds
        
        self.last_request_time = time.time() * 1000

    async def _is_high_quality_image(self, page, img_element, min_width, min_height):
        """Determine if an image is high quality based on various metrics"""
        try:
            # Check dimensions
            width = await img_element.evaluate("el => el.naturalWidth || el.width")
            height = await img_element.evaluate("el => el.naturalHeight || el.height")
            
            if width < min_width or height < min_height:
                return False
                
            # Check if image is likely a real photo vs icon/button
            aspect_ratio = width / height if height > 0 else 0
            if aspect_ratio > 0:
                # Extreme aspect ratios might be banners or UI elements
                if aspect_ratio > 5 or aspect_ratio < 0.2:
                    return False
                    
            # Check if image is in a prominent location (likely content vs. decoration)
            is_prominent = await img_element.evaluate("""
                el => {
                    const rect = el.getBoundingClientRect();
                    const viewportHeight = window.innerHeight;
                    const viewportWidth = window.innerWidth;
                    
                    // Check if image is reasonably sized relative to viewport
                    const imgArea = rect.width * rect.height;
                    const viewportArea = viewportWidth * viewportHeight;
                    
                    return imgArea > (viewportArea * 0.05); // At least 5% of viewport
                }
            """)
            
            return is_prominent
        except Exception as e:
            print(f"Error checking image quality: {e}")
            return True  # Default to accepting if we can't determine

    async def _handle_session_persistence(self, context, page):
        """Save and load session cookies for more efficient scraping across runs"""
        if not hasattr(self, 'scraper') or not self.scraper:
            return
            
        # Check if we should save cookies after successful login
        if self.is_logged_in and hasattr(self.scraper, 'session_manager'):
            domain = urlparse(self.url).netloc
            await self.scraper.session_manager.store_session(domain, context)
            print(f"Saved Kavyar session for {domain}")

    async def _handle_infinite_scroll_and_pagination(self, page):
        """Handle both infinite scroll and traditional pagination if present"""
        # First, try standard scrolling
        await self._smart_scroll_page(page)
        
        # Check for pagination links after scrolling
        pagination_selectors = [
            ".pagination a", 
            "nav.pagination",
            "[aria-label='pagination']",
            ".page-numbers",
            "a[rel='next']"
        ]
        
        for selector in pagination_selectors:
            next_page = page.locator(f"{selector}:has-text('Next'), {selector}[aria-label='Next']")
            if await next_page.count() > 0 and await next_page.first.is_visible():
                print("Found pagination element, will attempt to navigate")
                
                # Store current page media count to verify new content loads
                current_media_count = await page.evaluate("""
                    () => document.querySelectorAll('img, video, audio').length
                """)
                
                # Click next page
                await next_page.first.click()
                
                # Wait for navigation or new content
                try:
                    await page.wait_for_function(
                        """
                        (currentCount) => {
                            return document.querySelectorAll('img, video, audio').length > currentCount;
                        }
                        """,
                        arg=current_media_count,
                        timeout=10000
                    )
                    
                    # New content loaded, scroll through it
                    await self._smart_scroll_page(page)
                except Exception as e:
                    print(f"Error navigating to next page: {e}")
                
                break  # Only try one pagination method

    async def _detect_and_handle_mobile_version(self, page):
        """Detect if site is serving mobile version and handle accordingly"""
        # Check if we got redirected to mobile version
        current_url = page.url
        if "m." in current_url or "/mobile/" in current_url or "?mobile=1" in current_url:
            print("Detected mobile version of site")
            
            # Try to switch to desktop version if available
            desktop_link = page.locator("a:has-text('Desktop'), a:has-text('Switch to desktop'), [data-action='view-desktop']")
            if await desktop_link.count() > 0:
                await desktop_link.first.click()
                await page.wait_for_navigation()
                print("Switched to desktop version")
            else:
                # Adjust extraction selectors for mobile layout
                # (you would adapt your extraction methods to use mobile-specific selectors)
                print("Staying on mobile version, adapting selectors")

    async def _extract_from_interactive_galleries(self, page, media_items, url_cache):
        """Extract images from interactive galleries that require clicking through"""
        # Find gallery containers
        gallery_selectors = [
            ".gallery", 
            ".image-gallery", 
            ".slideshow", 
            ".carousel",
            "[data-gallery]"
        ]
        
        for selector in gallery_selectors:
            gallery = page.locator(selector)
            if await gallery.count() == 0:
                continue
                
            print(f"Found gallery with selector: {selector}")
            
            # Try to find gallery navigation buttons
            next_button = gallery.locator("button.next, .next, [aria-label='Next']")
            if await next_button.count() == 0:
                continue
                
            # Track images we've seen to detect when we've gone through the whole gallery
            seen_image_srcs = set()
            max_clicks = 20  # Safety limit
            
            # Click through gallery
            for _ in range(max_clicks):
                # Extract current image
                current_img = gallery.locator("img").first
                if await current_img.count() == 0:
                    break
                    
                src = await current_img.get_attribute("src")
                if not src or src in seen_image_srcs:
                    break  # We've seen this image already, we've looped through all
                    
                seen_image_srcs.add(src)
                
                # Skip if already in global cache
                if src in url_cache:
                    continue
                url_cache.add(src)
                    
                # Add to media items
                media_items.append({
                    'url': src,
                    'type': 'image',
                    'title': f"Gallery image from Kavyar",
                    'source_url': self.url
                })
                
                # Click next
                await next_button.click()
                await page.wait_for_timeout(500)  # Wait for animation

def _save_state(self, data):
    """Save extraction state for potential resuming"""
    if not self.state_file:
        return
        
    try:
        with open(self.state_file, 'w') as f:
            json.dump(data, f)
    except Exception as e:
        print(f"Error saving state: {e}")
        
def _load_state(self):
    """Load previous extraction state"""
    if not self.state_file or not os.path.exists(self.state_file):
        return {}
        
    try:
        with open(self.state_file, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading state: {e}")
        return {}

async def _extract_with_deep_inspection(self, page: AsyncPage, media_items: List[Dict], url_cache: set, 
                                       min_width: int, min_height: int) -> None:
    """Last-resort deep inspection to find media that other methods missed"""
    print("Performing deep inspection for media content...")
    
    try:
        # Use JavaScript to find ALL possible image sources on the page
        image_sources = await page.evaluate("""() => {
            const sources = [];
            
            // 1. Regular img tags
            document.querySelectorAll('img').forEach(img => {
                if (img.src && !img.src.startsWith('data:') && img.src.includes('://')) {
                    sources.push({
                        type: 'img',
                        url: img.src,
                        alt: img.alt || '',
                        width: img.naturalWidth || img.width || 0,
                        height: img.naturalHeight || img.height || 0,
                        visible: img.offsetParent !== null
                    });
                }
                
                // Check data attributes
                if (img.dataset) {
                    for (const [key, value] of Object.entries(img.dataset)) {
                        if (key.includes('src') && value && value.includes('://')) {
                            sources.push({
                                type: 'data-attribute',
                                url: value,
                                alt: img.alt || '',
                                width: img.naturalWidth || img.width || 0,
                                height: img.naturalHeight || img.height || 0,
                                visible: img.offsetParent !== null
                            });
                        }
                    }
                }
            });
            
            // 2. Background images
            const checkElements = document.querySelectorAll('*');
            checkElements.forEach(el => {
                const style = window.getComputedStyle(el);
                if (style.backgroundImage && style.backgroundImage !== 'none') {
                    const match = style.backgroundImage.match(/url\\(['"]?(.*?)['"]?\\)/);
                    if (match && match[1] && match[1].includes('://') && !match[1].startsWith('data:')) {
                        const rect = el.getBoundingClientRect();
                        sources.push({
                            type: 'background',
                            url: match[1],
                            alt: el.getAttribute('aria-label') || el.title || '',
                            width: rect.width || 0,
                            height: rect.height || 0,
                            visible: el.offsetParent !== null && rect.width > 0 && rect.height > 0
                        });
                    }
                }
            });
            
            // 3. Video poster images
            document.querySelectorAll('video[poster]').forEach(video => {
                if (video.poster && video.poster.includes('://')) {
                    const rect = video.getBoundingClientRect();
                    sources.push({
                        type: 'poster',
                        url: video.poster,
                        alt: video.getAttribute('aria-label') || video.title || '',
                        width: rect.width || 0,
                        height: rect.height || 0,
                        visible: video.offsetParent !== null
                    });
                }
            });
            
            // 4. Meta tags and link tags
            document.querySelectorAll('meta[property="og:image"], meta[name="twitter:image"], link[rel="image_src"]').forEach(meta => {
                const content = meta.getAttribute('content') || meta.getAttribute('href');
                if (content && content.includes('://')) {
                    sources.push({
                        type: 'meta',
                        url: content,
                        alt: '',
                        width: 0,
                        height: 0,
                        visible: true
                    });
                }
            });
            
            // 5. Source elements used with img/picture
            document.querySelectorAll('source[srcset]').forEach(source => {
                const srcset = source.getAttribute('srcset');
                if (srcset) {
                    // Parse srcset for the highest resolution
                    const srcsetParts = srcset.split(',');
                    for (const part of srcsetParts) {
                        const [url, descriptor] = part.trim().split(/\\s+/);
                        if (url && url.includes('://') && !url.startsWith('data:')) {
                            sources.push({
                                type: 'srcset',
                                url: url,
                                alt: '',
                                width: descriptor && descriptor.endsWith('w') ? parseInt(descriptor) : 0,
                                height: 0,
                                visible: source.parentElement && source.parentElement.offsetParent !== null
                            });
                        }
                    }
                }
            });
            
            // 6. Look for likely image URLs in all attributes
            document.querySelectorAll('[href*=".jpg"], [href*=".jpeg"], [href*=".png"], [href*=".webp"]').forEach(el => {
                const url = el.getAttribute('href');
                if (url && url.includes('://') && !url.startsWith('data:')) {
                    const rect = el.getBoundingClientRect();
                    sources.push({
                        type: 'href',
                        url: url,
                        alt: el.getAttribute('aria-label') || el.title || el.textContent || '',
                        width: rect.width || 0,
                        height: rect.height || 0,
                        visible: el.offsetParent !== null
                    });
                }
            });
            
            // 7. CSS custom properties that might contain image URLs
            const styleSheets = Array.from(document.styleSheets);
            try {
                for (const sheet of styleSheets) {
                    // Skip external sheets we can't access due to CORS
                    if (sheet.href && !sheet.href.startsWith(window.location.origin)) continue;
                    
                    try {
                        const rules = Array.from(sheet.cssRules || []);
                        for (const rule of rules) {
                            // Process only style rules
                            if (rule.style) {
                                const bgImage = rule.style.backgroundImage;
                                if (bgImage && bgImage !== 'none') {
                                    const matches = bgImage.match(/url\\(['"]?(.*?)['"]?\\)/g);
                                    if (matches) {
                                        for (const match of matches) {
                                            const urlMatch = match.match(/url\\(['"]?(.*?)['"]?\\)/);
                                            if (urlMatch && urlMatch[1] && urlMatch[1].includes('://') && !urlMatch[1].startsWith('data:')) {
                                                sources.push({
                                                    type: 'css',
                                                    url: urlMatch[1],
                                                    alt: '',
                                                    width: 0,
                                                    height: 0,
                                                    visible: true
                                                });
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    } catch (cssError) {
                        // Ignore CORS errors for external stylesheets
                        continue;
                    }
                }
            } catch (styleError) {
                // Ignore stylesheet access errors
            }
            
            return sources;
        }""")
        
        print(f"Deep inspection found {len(image_sources)} potential media sources")
        
        # Process and filter the results
        added_count = 0
        for source in image_sources:
            url = source.get('url', '')
            
            # Skip if already processed
            if url in url_cache:
                continue
                
            # Check if it's a media URL (simple pattern check)
            is_likely_media = (
                '.jpg' in url.lower() or
                '.jpeg' in url.lower() or
                '.png' in url.lower() or
                '.webp' in url.lower() or
                '.gif' in url.lower() or
                'image' in url.lower() or
                'img' in url.lower() or
                'photo' in url.lower() or
                '/media/' in url.lower()
            )
            
            if not is_likely_media:
                continue
                
            # Skip small images that are likely icons
            width = source.get('width', 0)
            height = source.get('height', 0)
            
            if width > 0 and height > 0:
                if width < 100 or height < 100:
                    continue
                    
                # Skip images that don't meet minimum dimensions
                if (min_width > 0 and width < min_width) or (min_height > 0 and height < min_height):
                    continue
            
            # Add to URL cache
            url_cache.add(url)
            
            # Create a title from available information
            alt_text = source.get('alt', '').strip()
            source_type = source.get('type', 'unknown')
            title = alt_text or f"Image from Kavyar ({source_type})"
            
            # Create the media item
            media_item = {
                'url': url,
                'type': 'image',
                'title': title,
                'alt': alt_text,
                'width': width,
                'height': height,
                'source_url': page.url,
                'extraction_type': f"deep_inspection_{source_type}"
            }
            
            # Add to results
            media_items.append(media_item)
            added_count += 1
            
            print(f"  Deep inspection added: {title} ({width}x{height})")
            
        print(f"Deep inspection added {added_count} new media items")
        
    except Exception as e:
        print(f"Error during deep inspection: {e}")
        traceback.print_exc()

async def _is_valid_image_url(self, url: str) -> bool:
    """Check if a URL appears to be a valid image URL"""
    try:
        # Skip empty URLs and data URLs
        if not url or url.startswith('data:'):
            return False
            
        # Must be an HTTP(S) URL
        if not url.startswith(('http://', 'https://')):
            return False
            
        # Check file extension for common image types
        url_lower = url.lower()
        has_image_extension = any(ext in url_lower for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg'])
        
        # If it has a file extension that's an image type, it's likely valid
        if has_image_extension:
            return True
            
        # Check for other signs of image URLs even without extensions
        image_indicators = ['image', 'photo', 'picture', 'img', 'media']
        has_image_indicator = any(indicator in url_lower for indicator in image_indicators)
        
        # Additional checks for CDN URLs without extensions
        is_likely_cdn = any(cdn in url_lower for cdn in [
            'cloudfront.net', 'cloudinary.com', 'imgix.net', 
            'cdn.', 'assets.', 'images.', 'static.'
        ])
        
        return has_image_indicator or is_likely_cdn
        
    except Exception:
        return False
