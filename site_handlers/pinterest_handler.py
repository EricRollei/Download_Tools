"""
Pinterest Handler

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
Pinterest (pinterest.com) specific handler for the Web Image Scraper
"""

from site_handlers.base_handler import BaseSiteHandler 
from urllib.parse import urljoin, urlparse, parse_qs
import time
import traceback
import os
import re
import json
from typing import List, Dict, Any, Optional, Union

# Try importing Playwright types safely
try:
    from playwright.async_api import Page as AsyncPage
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    AsyncPage = None
    PLAYWRIGHT_AVAILABLE = False

class PinterestHandler(BaseSiteHandler):
    """
    Handler for pinterest.com.
    Focuses on extracting images from pins, boards, and user profiles.
    
    Features:
    - DOM-based extraction with scrolling
    - Support for various Pinterest page types (pins, boards, user profiles)
    - Extracts pin images at highest available resolution
    - Captures pin titles, descriptions, and creator information when available
    """

    @classmethod
    def can_handle(cls, url):
        """Check if this handler can process the URL"""
        return "pinterest.com" in url.lower() or "pin.it" in url.lower()

    def __init__(self, url, scraper=None):
        """Initialize with Pinterest-specific properties"""
        # Set instance variables BEFORE calling super().__init__
        self.debug_mode = True
        self.board_id = None
        self.pin_id = None 
        self.username = None
        self.is_search = False
        self.search_query = None
        self.captured_media_urls = set()  # For network monitoring
        self.scraper = scraper  # Save reference to scraper
        
        # Call parent initialization AFTER setting our properties
        super().__init__(url, scraper)
        
        # Parse the URL to determine what type of Pinterest page we're dealing with
        self._parse_pinterest_url()
        print(f"PinterestHandler initialized for URL: {url}")

    def _load_auth_config(self):
        """Load Pinterest authentication configuration from config file"""
        try:
            # Check multiple potential config locations
            script_dir = os.path.dirname(os.path.abspath(__file__))
            config_paths = [
                os.path.join(script_dir, "auth_config.json"),
                os.path.join(script_dir, "..", "auth_config.json"),
                os.path.join(os.path.dirname(script_dir), "auth_config.json"),
                os.path.join(os.path.expanduser("~"), ".comfyui", "auth_config.json")
            ]
            
            for config_path in config_paths:
                if os.path.exists(config_path):
                    print(f"Found auth config at: {config_path}")
                    with open(config_path, 'r') as f:
                        config = json.load(f)
                        if 'pinterest' in config:
                            return config['pinterest']
            
            print("No Pinterest auth configuration found")
            return None
        except Exception as e:
            print(f"Error loading auth config: {e}")
            return None

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
                print(f"Interaction step failed: {step} - {e}")
                
    def get_default_interaction_sequence(self):
        return [
            # Accept cookies if present
            {"type": "wait_for_selector", "selector": "button:has-text('Accept all')", "timeout": 3000},
            {"type": "click", "selector": "button:has-text('Accept all')"},
            # Dismiss login/signup popup if present
            {"type": "wait_for_selector", "selector": "button[aria-label='Close']", "timeout": 3000},
            {"type": "click", "selector": "button[aria-label='Close']"},
            # Click "See more" or "Load more" if present
            {"type": "wait_for_selector", "selector": "button:has-text('See more')", "timeout": 3000},
            {"type": "click", "selector": "button:has-text('See more')"}
        ]


    async def _rate_limit(self, operation_type="default"):
        """Apply rate limiting to prevent being blocked"""
        delays = {
            "default": 0.5,    # Default delay
            "api": 1.0,        # Longer delay for API calls
            "page_load": 2.0,  # Longer delay for page navigation
            "scroll": 0.5      # Delay for scrolling
        }
        
        delay = delays.get(operation_type, delays["default"])
        await asyncio.sleep(delay)

    async def _save_session(self, context):
        """Save session cookies for later use"""
        if not hasattr(self, 'scraper') or not self.scraper:
            return
            
        domain = "pinterest.com"
        cookies_path = os.path.join(self.scraper.output_path, f"pinterest_cookies.json")
        
        try:
            await context.storage_state(path=cookies_path)
            print(f"Saved Pinterest session to {cookies_path}")
        except Exception as e:
            print(f"Error saving session: {e}")

    def _get_mobile_user_agent(self):
        """Get a mobile user agent for Pinterest"""
        return "Mozilla/5.0 (iPhone; CPU iPhone OS 14_7_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.2 Mobile/15E148 Safari/604.1"


    async def _update_selectors(self, page):
        """Check and update selectors based on current Pinterest version"""
        selectors = {
            # Check for these class names in the page
            "hCL": "img.hCL",  # 2024 class
            "kVc": "img.kVc",  # Another 2024 class
            "GrowthUnauthPinImage": '[data-test-id="GrowthUnauthPinImage"]',
            "pinWrapper": '[data-test-id="pinWrapper"]'
        }
        
        # Test which selectors exist on the current page
        active_selectors = []
        for name, selector in selectors.items():
            try:
                count = await page.locator(selector).count()
                if count > 0:
                    active_selectors.append(name)
            except:
                pass
        
        print(f"Active Pinterest selectors: {', '.join(active_selectors)}")
        return active_selectors


    def get_trusted_domains(self) -> list:
        """
        Return a list of domains that should be considered 'trusted' and allowed
        even when same_domain_only is enabled.
        """
        return [
            "pinterest.com",
            "pinimg.com",      # Main image CDN
            "s-media-cache-ak.pinimg.com",  # Alternative CDN sometimes used
            "i.pinimg.com",    # Direct image subdomain
            "s.pinimg.com",    # Static assets subdomain
            "media-cdn.pinterest.com",  # Media CDN
            "pin.it",          # Short URL domain
            "pinterest.ca",    # International domains
            "pinterest.co.uk",
            "pinterest.fr",
            "pinterest.de",
            "pinterest.jp"
        ]
    def _setup_authentication(self):
        """Set up Pinterest authentication based on available credentials"""
        auth_config = self._load_auth_config()
        self.auth_method = "none"  # Default
        
        if not auth_config:
            print("No Pinterest auth config found, proceeding without authentication")
            return False
        
         # Auto-detect authentication method
        if auth_config.get("api_key") and auth_config.get("api_secret"):
            self.auth_method = "api"
            self.api_key = auth_config.get("api_key")
            self.api_secret = auth_config.get("api_secret")
            self.access_token = auth_config.get("access_token", "")
            print("Detected API credentials - using Pinterest Developer API authentication")
            return True
            
        elif auth_config.get("username") and auth_config.get("password"):
            self.auth_method = "login"
            self.username = auth_config.get("username")
            self.password = auth_config.get("password")
            print("Detected login credentials - using Pinterest username/password authentication")
            return True
        
        # If explicit method is set and matches credentials
        elif auth_config.get("auth_method") == "api" and auth_config.get("api_key"):
            self.auth_method = "api"
            self.api_key = auth_config.get("api_key")
            self.api_secret = auth_config.get("api_secret", "")
            self.access_token = auth_config.get("access_token", "")
            print("Using Pinterest Developer API authentication")
            return True
            
        elif auth_config.get("auth_method") == "login" and auth_config.get("username"):
            self.auth_method = "login"
            self.username = auth_config.get("username")
            self.password = auth_config.get("password", "")
            print("Using Pinterest username/password authentication")
            return True
            
        print("No valid Pinterest credentials found, proceeding without authentication")
        return False

    async def _perform_login(self, page):
        """Log in to Pinterest using username and password"""
        if self.auth_method != "login" or not self.username or not self.password:
            return False
            
        try:
            print(f"Attempting Pinterest login as {self.username}...")
            
            # Go to login page
            await page.goto("https://www.pinterest.com/login/", wait_until="networkidle")
            
            # Fill in credentials and submit
            await page.fill('input[name="id"]', self.username)
            await page.fill('input[name="password"]', self.password)
            await page.click('button[type="submit"]')
            
            # Wait for login to complete (look for typical elements on logged-in pages)
            try:
                await page.wait_for_selector('[data-test-id="header-profile"], [aria-label="Your profile"]', timeout=10000)
                print("Pinterest login successful!")
                return True
            except Exception as e:
                print(f"Login wait error: {e}")
                
            # Check if we're still on login page or got redirected to an error page
            if 'login' in page.url:
                print("Pinterest login failed - still on login page")
                return False
                
            # If we didn't find the profile element but are no longer on login page,
            # we might still be logged in
            print("Pinterest login may have succeeded, continuing...")
            return True
                
        except Exception as e:
            print(f"Error during Pinterest login: {e}")
            traceback.print_exc()
            return False

    def _setup_api_client(self):
        """Set up Pinterest API client if credentials are available"""
        if self.auth_method != "api":
            return None
            
        try:
            # Try to import Pinterest API client
            try:
                # Try official SDK first
                from pinterest.client import PinterestAPI
                client = PinterestAPI(
                    client_id=self.api_key,
                    client_secret=self.api_secret
                )
                
                # Try to authenticate
                if hasattr(self, 'access_token') and self.access_token:
                    client.set_access_token(self.access_token)
                else:
                    client.auth()
                    
                print("Pinterest API client initialized successfully")
                return client
            except ImportError:
                # Try alternate library
                try:
                    from python_pinterest_api import PinterestAPI
                    client = PinterestAPI(
                        api_key=self.api_key,
                        api_secret=self.api_secret,
                        access_token=self.access_token if hasattr(self, 'access_token') else None
                    )
                    print("Pinterest API client (alternate) initialized successfully")
                    return client
                except ImportError:
                    print("Pinterest API client libraries not available. Install with: pip install pinterest-python-sdk")
                    return None
        except Exception as e:
            print(f"Error setting up Pinterest API client: {e}")
            return None

    async def extract_with_api(self, count=50):
        """Extract pins using Pinterest API"""
        if self.auth_method != "api" or not hasattr(self, "api_client") or not self.api_client:
            print("API client not available for extraction")
            return []
            
        media_items = []
        try:
            # Different API calls based on URL type
            if self.is_search and self.search_query:
                # Search for pins
                response = self.api_client.search_pins(query=self.search_query, limit=count)
                pins = response.items if hasattr(response, 'items') else response
            elif self.board_id:
                # Get pins from a board
                board_parts = self.board_id.split('/')
                if len(board_parts) == 2:
                    username, board_slug = board_parts
                    response = self.api_client.get_board_pins(username=username, board_slug=board_slug, limit=count)
                    pins = response.items if hasattr(response, 'items') else response
                else:
                    print(f"Invalid board ID format: {self.board_id}")
                    return []
            elif self.pin_id:
                # Get a single pin
                response = self.api_client.get_pin(pin_id=self.pin_id)
                pins = [response] if response else []
            elif self.username:
                # Get user pins
                response = self.api_client.get_user_pins(username=self.username, limit=count)
                pins = response.items if hasattr(response, 'items') else response
            else:
                # Default to home feed
                response = self.api_client.get_home_feed(limit=count)
                pins = response.items if hasattr(response, 'items') else response
            
            # Process pins into media items
            for pin in pins:
                try:
                    # The structure depends on which API client we're using
                    image_url = None
                    title = "Pinterest Pin"
                    description = ""
                    pin_id = ""
                    creator = "Pinterest"
                    
                    # Handle different response structures based on API client
                    if hasattr(pin, 'image') and pin.image:
                        if hasattr(pin.image, 'original') and pin.image.original:
                            image_url = pin.image.original.url
                        else:
                            image_url = pin.image.url
                        
                        if hasattr(pin, 'id'):
                            pin_id = pin.id
                        
                        if hasattr(pin, 'title'):
                            title = pin.title
                        
                        if hasattr(pin, 'description'):
                            description = pin.description
                        
                        if hasattr(pin, 'creator') and pin.creator and hasattr(pin.creator, 'username'):
                            creator = f"Pinterest: {pin.creator.username}"
                    # Dictionary-like response
                    elif isinstance(pin, dict):
                        image_url = pin.get('image_url') or pin.get('url')
                        pin_id = pin.get('id', '')
                        title = pin.get('title', "Pinterest Pin")
                        description = pin.get('description', '')
                        if 'creator' in pin and 'username' in pin['creator']:
                            creator = f"Pinterest: {pin['creator']['username']}"
                            
                    if image_url:
                        media_items.append({
                            'url': image_url,
                            'alt': title or "Pinterest Image",
                            'title': title,
                            'description': description,
                            'source_url': f"https://www.pinterest.com/pin/{pin_id}/" if pin_id else self.url,
                            'credits': creator,
                            'type': 'image',
                            '_headers': {
                                'Referer': 'https://www.pinterest.com/',
                                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
                                'Accept': 'image/webp,image/avif,image/*,*/*;q=0.8',
                            }
                        })
                except Exception as e:
                    print(f"Error processing API pin: {e}")
                    
            print(f"Pinterest API extraction found {len(media_items)} pins")
            return media_items
            
        except Exception as e:
            print(f"Error during Pinterest API extraction: {e}")
            traceback.print_exc()
            return []

            
    async def extract_with_direct_playwright_async(self, page, **kwargs):
        print("PinterestHandler: Using specialized Pinterest extraction")

        # Run interaction sequence (from UI, kwargs, or default)
        interaction_sequence = kwargs.get("interaction_sequence") or getattr(self, "interaction_sequence", None)
        if not interaction_sequence:
            interaction_sequence = self.get_default_interaction_sequence()
        await self._run_interaction_sequence(page, interaction_sequence)
        
        media_items = []
        
        try:
            # First scroll to load more content
            await self._scroll_page_async(page)
            
            # Extract Pinterest pins using updated selectors
            pin_data = await page.evaluate("""() => {
                const pins = [];
                
                // Modern Pinterest selectors - 2024 structure
                const pinSelectors = [
                    'img.hCL', // Main search results 2024 class
                    'img.kVc', // Another 2024 Pinterest class
                    'img[class*="hCL"]', // Class contains pattern 
                    'img[srcset]', // Images with srcset attribute
                    'div[data-test-id="pin-closeup-image"] img', // Pin closeup
                    'div[data-test-id="pinWrapper"] img',
                    'div[data-test-id="pin"] img',
                    'div[data-test-id="pinCard"] img',
                    // Various fallback selectors
                    'div[class*="Pin"] img',
                    '.pinWrapper img',
                    '.pinHolder img',
                    // Very generic fallback
                    'img[src*="pinimg.com"]'
                ];
                
                // Check each selector
                for (const selector of pinSelectors) {
                    const images = document.querySelectorAll(selector);
                    
                    if (images.length > 0) {
                        console.log(`Found ${images.length} images with selector ${selector}`);
                        
                        images.forEach((img, index) => {
                            // Skip small thumbnails/icons
                            if (img.width < 100 || img.height < 100) {
                                return;
                            }
                            
                            // Get all possible image sources
                            const src = img.src || '';
                            const dataSrc = img.getAttribute('data-src') || '';
                            
                            // Handle srcset - critical for Pinterest
                            const srcset = img.getAttribute('srcset') || '';
                            
                            if (!src && !dataSrc && !srcset) {
                                return;
                            }
                            
                            // Skip non-Pinterest images
                            if (!src.includes('pinimg.com') && !dataSrc.includes('pinimg.com')) {
                                return;
                            }
                            
                            // Skip profile images, icons etc.
                            if (src.includes('avatar') || src.includes('icon') || 
                                src.includes('favicon') || src.includes('logo')) {
                                return;
                            }
                            
                            // Find the best image URL - prioritize high resolution
                            let imageUrl = src || dataSrc;
                            
                            // Process srcset to get highest res if available
                            if (srcset) {
                                // Pinterest specific format parsing: "url 1x, url 2x, url 3x, url 4x"
                                const srcsetParts = srcset.split(',');
                                
                                // Look specifically for originals or 4x
                                for (const part of srcsetParts) {
                                    if (part.includes('originals') || part.includes('4x')) {
                                        const url = part.trim().split(' ')[0];
                                        imageUrl = url;
                                        break;
                                    }
                                }
                                
                                // If no originals found, look for the highest number (3x, then 2x)
                                if (!imageUrl.includes('originals')) {
                                    for (const part of srcsetParts) {
                                        if (part.includes('3x')) {
                                            const url = part.trim().split(' ')[0];
                                            imageUrl = url;
                                            break;
                                        }
                                    }
                                }
                                
                                if (!imageUrl.includes('originals') && !imageUrl.includes('736x')) {
                                    for (const part of srcsetParts) {
                                        if (part.includes('2x')) {
                                            const url = part.trim().split(' ')[0];
                                            imageUrl = url;
                                            break;
                                        }
                                    }
                                }
                            }
                            
                            // Convert to higher resolution if possible
                            if (imageUrl.includes('236x')) {
                                imageUrl = imageUrl.replace('236x', '1200x');
                            } else if (imageUrl.includes('474x')) {
                                imageUrl = imageUrl.replace('474x', '1200x');
                            } else if (imageUrl.includes('736x')) {
                                imageUrl = imageUrl.replace('736x', '1200x');
                            }
                            
                            // Get pin details
                            let pinId = '';
                            let pinUrl = '';
                            let title = img.alt || '';
                            let description = '';
                            
                            // Find pin container to extract more data
                            const pinContainer = 
                                img.closest('[data-test-id="pinWrapper"]') || 
                                img.closest('[data-test-id="pin"]') || 
                                img.closest('[data-test-id="pinCard"]') ||
                                img.closest('div[class*="Pin"]') ||
                                img.closest('div[role="button"]');
                            
                            if (pinContainer) {
                                // Try to find pin ID from parent elements or links
                                const links = pinContainer.querySelectorAll('a[href*="/pin/"]');
                                if (links.length > 0) {
                                    pinUrl = links[0].href;
                                    const pinMatch = pinUrl.match(/\\/pin\\/(\\d+)/);
                                    if (pinMatch) {
                                        pinId = pinMatch[1];
                                    }
                                }
                            }
                            
                            pins.push({
                                url: imageUrl,
                                pinId: pinId,
                                pinUrl: pinUrl || (pinId ? `https://www.pinterest.com/pin/${pinId}/` : ''),
                                title: title || 'Pinterest Pin',
                                description: description
                            });
                        });
                        
                        // If we found pins with this selector, break out of the loop
                        if (pins.length > 0) {
                            break;
                        }
                    }
                }
                
                // Special case for the pin view/closeup
                if (pins.length === 0) {
                    const closeupImg = document.querySelector('div[data-test-id="pin-closeup-image"] img, div[role="dialog"] img[src*="pinimg.com"]');
                    if (closeupImg) {
                        console.log('Found pin closeup image');
                        const src = closeupImg.src;
                        if (src && src.includes('pinimg.com')) {
                            // Extract pin ID from URL if possible
                            let pinId = '';
                            const pinMatch = window.location.href.match(/\\/pin\\/(\\d+)/);
                            if (pinMatch) {
                                pinId = pinMatch[1];
                            }
                            
                            pins.push({
                                url: src.replace(/\/\d+x\//, '/1200x/'), // Try to get 1200x version
                                pinId: pinId,
                                pinUrl: window.location.href,
                                title: closeupImg.alt || 'Pinterest Pin',
                                description: ''
                            });
                        }
                    }
                }
                
                // Special case for full-page pin detail view (based on your HTML example)
                if (pins.length === 0) {
                    const fullViewImg = document.querySelector('img[alt="Full view"]');
                    if (fullViewImg && fullViewImg.src && fullViewImg.src.includes('pinimg.com')) {
                        console.log('Found full view image');
                        pins.push({
                            url: fullViewImg.src,
                            pinId: '',
                            pinUrl: window.location.href,
                            title: fullViewImg.alt || 'Pinterest Full View',
                            description: ''
                        });
                    }
                }
                
                // If still nothing found, try a more general approach
                if (pins.length === 0) {
                    // Find all images with pinimg.com in src
                    const allImages = Array.from(document.querySelectorAll('img'))
                        .filter(img => {
                            const src = img.src || '';
                            return src.includes('pinimg.com') && 
                                !src.includes('avatar') && 
                                !src.includes('icon') &&
                                (img.width >= 100 || img.height >= 100);
                        });
                    
                    console.log(`Found ${allImages.length} Pinterest images with generic approach`);
                    
                    allImages.forEach((img, index) => {
                        let imageUrl = img.src;
                        // Try to convert to higher resolution
                        if (imageUrl.includes('236x')) {
                            imageUrl = imageUrl.replace('236x', '1200x');
                        } else if (imageUrl.includes('474x')) {
                            imageUrl = imageUrl.replace('474x', '1200x');
                        } else if (imageUrl.includes('736x')) {
                            imageUrl = imageUrl.replace('736x', '1200x');
                        }
                        
                        pins.push({
                            url: imageUrl,
                            pinId: '',
                            pinUrl: '',
                            title: img.alt || `Pinterest Image ${index + 1}`,
                            description: ''
                        });
                    });
                }
                
                console.log(`Returning ${pins.length} pins`);
                return pins;
            }""")
            
            print(f"Extracted {len(pin_data)} Pinterest pins")
            
            # Add video extraction
            if not media_items or self.debug_mode:
                print("Extracting videos from Pinterest...")
                video_items = await self._extract_video_pins(page)
                if video_items:
                    print(f"Found {len(video_items)} videos")
                    media_items.extend(video_items)
                    
            # Process each pin
            for pin in pin_data:
                image_url = pin.get('url', '')
                
                if not image_url:
                    continue
                    
                # Convert to highest resolution
                high_res_url = self._convert_to_highest_res(image_url)
                
                # Create a descriptive title
                title = pin.get('title', '') or "Pinterest Pin"
                if pin.get('description'):
                    title += f" - {pin.get('description')}"
                
                # Add to media items
                media_items.append({
                    'url': high_res_url,
                    'alt': pin.get('title', ''),
                    'title': title,
                    'source_url': pin.get('pinUrl', self.url),
                    'credits': "Pinterest",
                    'type': 'image',
                    '_headers': {
                        'Referer': 'https://www.pinterest.com/',
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
                        'Accept': 'image/webp,image/avif,image/*,*/*;q=0.8',
                        'sec-ch-ua': '"Google Chrome";v="123", "Not:A-Brand";v="8", "Chromium";v="123"'
                    }
                })
            
            # If no pins found, try extracting from network requests
            if not media_items and hasattr(self, 'captured_media_urls') and self.captured_media_urls:
                print(f"No pins found in DOM, using {len(self.captured_media_urls)} captured network URLs")
                media_items.extend(self._process_captured_network_urls())
            
            # If still no pins found, try extracting from JSON data
            if not media_items:
                print("No pins found in DOM or network, trying JSON extraction...")
                html_content = await page.content()
                
                # Look for initial state JSON
                json_matches = [
                    re.search(r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\});', html_content, re.DOTALL),
                    re.search(r'window\.__REDUX_STATE__\s*=\s*(\{.*?\});', html_content, re.DOTALL),
                    re.search(r'"pins":\s*(\{.*?\}),', html_content, re.DOTALL)
                ]
                
                for json_match in json_matches:
                    if json_match:
                        try:
                            json_text = json_match.group(1)
                            # Clean up the JSON text
                            json_text = re.sub(r'undefined', 'null', json_text)
                            json_data = json.loads(json_text)
                            
                            # Use your existing method to extract pins from JSON
                            json_items = self._extract_pins_from_json(json_data)
                            
                            if json_items:
                                print(f"Found {len(json_items)} pins in JSON data")
                                media_items.extend(json_items)
                                break
                                
                        except Exception as e:
                            print(f"Error extracting from JSON: {e}")
        
        except Exception as e:
            print(f"Error extracting Pinterest pins: {e}")
            import traceback
            traceback.print_exc()
        
        # Extract enhanced metadata and apply to media items
        metadata_map = await self._extract_enhanced_metadata(page)
        if metadata_map:
            # Apply metadata to matching media items
            for item in media_items:
                # Try to find pin ID from URL
                pin_id = None
                if 'source_url' in item:
                    pin_match = re.search(r'/pin/(\d+)', item['source_url'])
                    if pin_match:
                        pin_id = pin_match.group(1)
                
                # If pin ID is found and metadata exists, apply it
                if pin_id and pin_id in metadata_map:
                    metadata = metadata_map[pin_id]
                    
                    # Apply metadata to item
                    if metadata.get('title'):
                        item['title'] = metadata['title']
                    
                    if metadata.get('description'):
                        item['description'] = metadata['description']
                    
                    if metadata.get('creator'):
                        item['credits'] = f"Pinterest: {metadata['creator']}"
                    
                    # If there's a board, add it to the title
                    if metadata.get('board') and metadata['board'].get('name'):
                        board_name = metadata['board']['name']
                        item['board'] = board_name
                        # Add to title if not already there
                        if board_name and board_name not in item['title']:
                            item['title'] = f"{item['title']} (Board: {board_name})"
                    
                    # Add source link if available
                    if metadata.get('source_link'):
                        item['original_source'] = metadata['source_link']
        
        print(f"Pinterest extraction complete. Found {len(media_items)} media items")
        return media_items

    async def _extract_enhanced_metadata(self, page):
        """Extract enhanced metadata for Pinterest pins"""
        metadata_map = {}  # Map of pin_id -> metadata
        
        try:
            print("Extracting enhanced metadata from Pinterest...")
            
            # First, try to extract from JSON data in the page
            html_content = await page.content()
            
            # Look for pin metadata in JSON structures
            json_patterns = [
                r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\});',
                r'window\.__REDUX_STATE__\s*=\s*(\{.*?\});',
                r'"pins":\s*(\{.*?\}),',
                r'<script id="__PWS_DATA__" type="application/json">(.*?)</script>'
            ]
            
            for pattern in json_patterns:
                matches = re.search(pattern, html_content, re.DOTALL)
                if matches:
                    try:
                        json_text = matches.group(1)
                        # Clean up JSON (replace JS functions, undefined, etc.)
                        json_text = re.sub(r'function\s*\([^)]*\)\s*\{[^}]*\}', '""', json_text)
                        json_text = json_text.replace('undefined', 'null')
                        # Parse the JSON
                        json_data = json.loads(json_text)
                        
                        # Process data to extract metadata
                        metadata_map.update(self._extract_metadata_from_json(json_data))
                        
                        if metadata_map:
                            print(f"Extracted metadata for {len(metadata_map)} pins from JSON")
                            break
                    except Exception as e:
                        print(f"Error extracting from JSON: {e}")
            
            # If needed, try to get metadata directly from DOM
            if not metadata_map:
                # For pin detail pages, extract from the current pin
                if self.pin_id:
                    try:
                        # Extract title
                        title_selector = '[data-test-id="pin-title"], h1, [role="dialog"] h1'
                        title_elem = page.locator(title_selector).first
                        if await title_elem.count() > 0:
                            title = await title_elem.inner_text()
                            
                            # Extract description
                            desc_selector = '[data-test-id="pin-description"], [role="dialog"] p'
                            desc_elem = page.locator(desc_selector).first
                            description = ""
                            if await desc_elem.count() > 0:
                                description = await desc_elem.inner_text()
                            
                            # Extract creator info
                            creator_selector = '[data-test-id="pinner-name"], [data-test-id="creator-name"], [rel="creator"]'
                            creator_elem = page.locator(creator_selector).first
                            creator = ""
                            if await creator_elem.count() > 0:
                                creator = await creator_elem.inner_text()
                            
                            # Extract link if any
                            link_selector = '[data-test-id="pin-link"], [data-test-id="pin-website-link"]'
                            link_elem = page.locator(link_selector).first
                            link = ""
                            if await link_elem.count() > 0:
                                link = await link_elem.get_attribute('href') or ""
                            
                            # Add to metadata map
                            metadata_map[self.pin_id] = {
                                'title': title,
                                'description': description,
                                'creator': creator,
                                'source_link': link,
                                'board': None  # Will be filled if found
                            }
                            
                            print(f"Extracted metadata for current pin: {self.pin_id}")
                    except Exception as e:
                        print(f"Error extracting metadata from DOM: {e}")
            
            return metadata_map
            
        except Exception as e:
            print(f"Error extracting enhanced metadata: {e}")
            traceback.print_exc()
            return {}

    def _extract_metadata_from_json(self, json_data):
        """Extract pin metadata from JSON data"""
        metadata = {}
        
        try:
            # Look for pins object first (common structure)
            if isinstance(json_data, dict) and 'pins' in json_data:
                pins = json_data['pins']
                if isinstance(pins, dict):
                    for pin_id, pin_data in pins.items():
                        if isinstance(pin_data, dict):
                            # Extract core metadata
                            title = pin_data.get('title', '')
                            description = pin_data.get('description', '')
                            
                            # Extract creator info
                            creator = ''
                            creator_data = pin_data.get('creator') or pin_data.get('pinner')
                            if creator_data and isinstance(creator_data, dict):
                                creator = creator_data.get('username', '')
                                if not creator and 'full_name' in creator_data:
                                    creator = creator_data.get('full_name', '')
                            
                            # Extract board info
                            board = None
                            board_data = pin_data.get('board')
                            if board_data and isinstance(board_data, dict):
                                board_name = board_data.get('name', '')
                                board_id = board_data.get('id', '')
                                board_owner = ''
                                if 'owner' in board_data and isinstance(board_data['owner'], dict):
                                    board_owner = board_data['owner'].get('username', '')
                                
                                if board_name:
                                    board = {
                                        'name': board_name,
                                        'id': board_id,
                                        'owner': board_owner
                                    }
                            
                            # Extract source link
                            source_link = ''
                            link_data = pin_data.get('link') or pin_data.get('source')
                            if isinstance(link_data, str):
                                source_link = link_data
                            elif isinstance(link_data, dict):
                                source_link = link_data.get('url', '')
                            
                            # Store all metadata
                            metadata[pin_id] = {
                                'title': title,
                                'description': description,
                                'creator': creator,
                                'source_link': source_link,
                                'board': board,
                                # Additional metadata
                                'created_at': pin_data.get('created_at', ''),
                                'likes': pin_data.get('like_count', 0),
                                'saves': pin_data.get('repin_count', 0)
                            }
            
            # Recursively search for nested pins
            if isinstance(json_data, dict):
                for key, value in json_data.items():
                    if isinstance(value, (dict, list)) and key != 'pins':  # Avoid re-processing 'pins'
                        nested_metadata = self._extract_metadata_from_json(value)
                        metadata.update(nested_metadata)
            elif isinstance(json_data, list):
                for item in json_data:
                    if isinstance(item, (dict, list)):
                        nested_metadata = self._extract_metadata_from_json(item)
                        metadata.update(nested_metadata)
            
            return metadata
            
        except Exception as e:
            print(f"Error extracting metadata from JSON: {e}")
            return metadata


    async def _extract_video_pins(self, page):
        """Extract video pins from Pinterest page"""
        video_items = []
        
        try:
            print("Extracting video pins from Pinterest...")
            
            # First try to find video elements in the DOM
            video_selectors = [
                'video[src*="pinimg.com"]',
                'video[poster*="pinimg.com"]',
                '[data-test-id="VideoPlayer"] video',
                '[data-test-id="StoryPin"] video',
                'div[class*="VideoPlayer"] video',
                'div[role="dialog"] video'
            ]
            
            for selector in video_selectors:
                videos = page.locator(selector)
                count = await videos.count()
                if count > 0:
                    print(f"Found {count} videos with selector {selector}")
                    
                    for i in range(count):
                        try:
                            video = videos.nth(i)
                            
                            # Get video source
                            src = await video.get_attribute('src')
                            if not src:
                                # Check for source elements
                                source_element = video.locator('source').first
                                if await source_element.count() > 0:
                                    src = await source_element.get_attribute('src')
                            
                            # Skip if no valid URL
                            if not src or not src.startswith('http'):
                                continue
                                
                            # Get poster image as thumbnail
                            poster = await video.get_attribute('poster') or ""
                            
                            # Get title or alt text if available
                            title = await video.get_attribute('title') or ""
                            alt = await video.get_attribute('alt') or ""
                            
                            # Try to find pin ID from container
                            pin_id = ""
                            video_container = video.locator("xpath=../..")  # Parent's parent
                            link = video_container.locator('a[href*="/pin/"]').first
                            try:
                                if await link.count() > 0:
                                    href = await link.get_attribute('href') or ""
                                    pin_match = re.search(r'/pin/(\d+)', href)
                                    if pin_match:
                                        pin_id = pin_match.group(1)
                            except:
                                pass
                            
                            # Add item to results
                            video_items.append({
                                'url': src,
                                'thumbnail': poster,
                                'type': 'video',
                                'title': title or alt or "Pinterest Video",
                                'alt': alt or title or "Pinterest Video",
                                'source_url': f"https://www.pinterest.com/pin/{pin_id}/" if pin_id else self.url,
                                'credits': "Pinterest",
                                '_headers': {
                                    'Referer': 'https://www.pinterest.com/',
                                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36'
                                }
                            })
                        except Exception as e:
                            if self.debug_mode:
                                print(f"Error extracting video: {e}")
            
            # If no videos found yet, try to extract from JSON data
            if not video_items:
                # Extract from page content
                html_content = await page.content()
                
                # Look for video URLs in the page
                video_patterns = [
                    r'(https?://v\.pinimg\.com/[^"\'<>\s]+\.mp4)',
                    r'(https?://[^"\'<>\s]*pinimg\.com[^"\'<>\s]*\.mp4)',
                    r'"video_url":"(https?:\\/\\/[^"]+?\.mp4)',
                    r'"url":"(https?:\\/\\/v\.pinimg\.com[^"]+?)"'
                ]
                
                # Extract using patterns
                for pattern in video_patterns:
                    matches = re.findall(pattern, html_content)
                    for url in matches:
                        # Clean up escaped slashes
                        clean_url = url.replace('\/', '/')
                        
                        # Skip duplicates
                        if any(item['url'] == clean_url for item in video_items):
                            continue
                        
                        # Add to results
                        video_items.append({
                            'url': clean_url,
                            'type': 'video',
                            'title': "Pinterest Video",
                            'alt': "Pinterest Video",
                            'source_url': self.url,
                            'credits': "Pinterest",
                            '_headers': {
                                'Referer': 'https://www.pinterest.com/',
                                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36'
                            }
                        })
                
                print(f"Found {len(video_items)} video URLs from page content")
            
            # Also try to extract from API responses and other network data
            if hasattr(self, 'captured_media_urls'):
                video_urls = [url for url in self.captured_media_urls 
                            if url.endswith('.mp4') or url.endswith('.mov') or '.mp4?' in url]
                
                for url in video_urls:
                    # Skip duplicates
                    if any(item['url'] == url for item in video_items):
                        continue
                    
                    video_items.append({
                        'url': url,
                        'type': 'video',
                        'title': "Pinterest Video (Network)",
                        'alt': "Pinterest Video",
                        'source_url': self.url,
                        'credits': "Pinterest",
                        '_headers': {
                            'Referer': 'https://www.pinterest.com/',
                            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36'
                        }
                    })
                
                print(f"Found {len(video_urls)} video URLs from network capture")
            
            return video_items
            
        except Exception as e:
            print(f"Error extracting video pins: {e}")
            traceback.print_exc()
            return []


    async def extract_media_items_async(self, page):
        """Extract media items using async Playwright."""
        print("PinterestHandler: Extracting media items")
        
        # Reset captured media URLs to prevent false duplicates
        self.captured_media_urls = set()
        
        media_items = []
        
        # Try API extraction first if configured
        if hasattr(self, "auth_method") and self.auth_method == "api" and hasattr(self, "api_client") and self.api_client:
            api_items = await self.extract_with_api(count=50)
            if api_items:
                print(f"API extraction successful, found {len(api_items)} items")
                media_items.extend(api_items)
                return media_items
            else:
                print("API extraction returned no results, falling back to scraping")

        # First extract media from JSON data in the page
        json_media_items = await self._extract_media_from_json_data_async(page)
        if json_media_items:
            print(f"JSON extraction found {len(json_media_items)} items")
            media_items.extend(json_media_items)
        
        # Then try DOM-based extraction
        if PLAYWRIGHT_AVAILABLE:
            dom_media_items = await self._extract_media_from_dom_async(page)
            if dom_media_items:
                print(f"DOM extraction found {len(dom_media_items)} items")
                media_items.extend(dom_media_items)
        
        # For search pages, use a more specific extraction method
        if self.is_search:
            search_media_items = await self._extract_media_from_search_page_async(page)
            if search_media_items:
                print(f"Search page extraction found {len(search_media_items)} items")
                media_items.extend(search_media_items)
        
        # Then try HTML parsing as a fallback
        html_media_items = await self._extract_media_from_html_async(page)
        if html_media_items:
            print(f"HTML extraction found {len(html_media_items)} items")
            media_items.extend(html_media_items)
        
        # Include any URLs captured by network monitoring
        network_items = self._process_captured_network_urls()
        if network_items:
            print(f"Network monitoring found {len(network_items)} additional items")
            media_items.extend(network_items)
        
        # Remove duplicates while preserving order
        unique_items = self._remove_duplicate_urls(media_items)
        
        print(f"Total Pinterest media items found: {len(unique_items)}")
        return unique_items

    async def _extract_media_from_json_data_async(self, page):
        """Extract media from JSON data embedded in the page (async version)"""
        media_items = []
        
        try:
            html_content = await page.content()
            if not html_content:
                return media_items
                
            # The rest of this function doesn't need to be async since it's processing the HTML locally
            # Look for Pinterest-specific JSON data
            # Pattern 1: __PWS_DATA__ script
            json_match = re.search(r'<script id="__PWS_DATA__" type="application/json">(.*?)</script>', html_content)
            if json_match:
                try:
                    json_data = json.loads(json_match.group(1))
                    pins = self._extract_pins_from_json(json_data)
                    if pins:
                        media_items.extend(pins)
                except Exception as e:
                    print(f"Error extracting from __PWS_DATA__: {e}")
                    
            # Pattern 2: Initial state JSON
            state_match = re.search(r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\});', html_content, re.DOTALL)
            if state_match:
                try:
                    json_text = state_match.group(1)
                    # Clean up the JSON string (remove JS functions, etc.)
                    json_text = re.sub(r'function\s*\([^)]*\)\s*\{[^}]*\}', '""', json_text)
                    # Replace undefined with null
                    json_text = json_text.replace('undefined', 'null')
                    json_data = json.loads(json_text)
                    pins = self._extract_pins_from_json(json_data)
                    if pins:
                        media_items.extend(pins)
                except Exception as e:
                    print(f"Error extracting from __INITIAL_STATE__: {e}")
                    
            # Pattern 3: Look for any JSON with image URLs
            img_matches = re.findall(r'"(https://i\.pinimg\.com/[^"]+)"', html_content)
            for url in img_matches:
                # Skip thumbnails, icons, etc.
                if any(x in url.lower() for x in ['favicon', 'icon', 'avatar', '16x16', '32x32', '64x64']):
                    continue
                    
                # Try to upgrade to highest quality
                image_url = re.sub(r'/\d+x/', '/originals/', url)
                
                # Skip if we already have this URL
                if image_url in [item['url'] for item in media_items]:
                    continue
                    
                media_items.append({
                    'url': image_url,
                    'alt': "Pinterest Image (JSON)",
                    'title': "Pinterest Image",
                    'source_url': self.url,
                    'credits': "Pinterest",
                    'type': 'image',
                    '_headers': {
                        'Referer': 'https://www.pinterest.com/',
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
                        'Accept': 'image/webp,image/avif,image/*,*/*;q=0.8',
                        'sec-ch-ua': '"Google Chrome";v="123", "Not:A-Brand";v="8", "Chromium";v="123"'
                    }
                })
        
        except Exception as e:
            print(f"Error extracting media from JSON data: {e}")
            traceback.print_exc()
            
        return media_items

    async def _extract_media_from_dom_async(self, page):
        """Extract media items using DOM queries (async version)."""
        media_items = []
        
        if not PLAYWRIGHT_AVAILABLE:
            return media_items
            
        try:
            # Simple DOM-based extraction focused on image elements
            img_elements = page.locator('img[src*="pinimg.com"]')
            count = await img_elements.count()
            print(f"Found {count} Pinterest images in DOM")
            
            for i in range(count):
                try:
                    img = img_elements.nth(i)
                    
                    # Get image attributes
                    src = await img.get_attribute('src') or ""
                    alt = await img.get_attribute('alt') or "Pinterest image"
                    
                    # Skip small images, icons, etc.
                    if any(x in src.lower() for x in ['favicon', 'icon', 'avatar', '16x16', '32x32', '64x64']):
                        continue
                    
                    # Try to upgrade to original quality
                    image_url = re.sub(r'/\d+x/', '/originals/', src)
                    
                    media_items.append({
                        'url': image_url,
                        'alt': alt,
                        'title': alt,
                        'source_url': self.url,
                        'credits': "Pinterest",
                        'type': 'image',
                        '_headers': {
                            'Referer': 'https://www.pinterest.com/',
                            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
                            'Accept': 'image/webp,image/avif,image/*,*/*;q=0.8',
                            'sec-ch-ua': '"Google Chrome";v="123", "Not:A-Brand";v="8", "Chromium";v="123"'
                        }
                    })
                except Exception as e:
                    print(f"Error extracting image: {e}")
        
        except Exception as e:
            print(f"Error extracting media from DOM: {e}")
            traceback.print_exc()
            
        return media_items

    async def _extract_media_from_search_page_async(self, page):
        """Extract media items specifically from Pinterest search results (async version)."""
        media_items = []
        
        if not PLAYWRIGHT_AVAILABLE:
            return media_items
            
        try:
            print("Extracting images from Pinterest search results...")
            
            # Most search result images are in grid items
            containers = page.locator('[data-grid-item], [data-test-id="pinWrapper"], [data-test-id="pinCard"]')
            count = await containers.count()
            print(f"Found {count} potential image containers")
            
            for i in range(count):
                try:
                    container = containers.nth(i)
                    
                    # Add special handling for 2024 Pinterest classes
                    special_img = container.locator('img.hCL, img.kVc, img[class*="hCL"]').first
                    if await special_img.count():
                        print(f"Found Pinterest image with 2024 class structure")
                        img = special_img
                    else:
                        # Original fallback
                        img = container.locator('img').first
                    
                    # First check if img exists
                    try:
                        await img.wait_for(timeout=500)
                    except:
                        continue
                        
                    # Get image source
                    src = await img.get_attribute('src') or ""
                    data_src = await img.get_attribute('data-src') or ""
                    srcset = await img.get_attribute('srcset') or ""
                    
                    # Use data-src if available
                    image_url = data_src if data_src else src
                    
                    # If srcset is available, extract highest quality
                    if srcset:
                        best_url = self._get_best_image_from_srcset(srcset)
                        if best_url:
                            image_url = best_url
                            
                    # Skip if no valid URL
                    if not image_url or not image_url.startswith('http'):
                        continue
                        
                    # Skip small thumbnails/icons
                    if any(x in image_url.lower() for x in ['favicon', 'icon', 'avatar', 'profile']):
                        continue
                    
                    # Check if this is a Pinterest image
                    if "pinimg.com" not in image_url:
                        continue
                        
                    # Try to upgrade to original size
                    if '/236x/' in image_url or '/474x/' in image_url or '/736x/' in image_url:
                        image_url = re.sub(r'/\d+x/', '/originals/', image_url)
                        
                    # Get alt text and link to pin
                    alt_text = await img.get_attribute('alt') or "Pinterest image"
                    
                    # Try to find pin ID from container
                    pin_id = ""
                    link = container.locator('a[href*="/pin/"]').first
                    try:
                        await link.wait_for(timeout=500)
                        href = await link.get_attribute('href') or ""
                        pin_match = re.search(r'/pin/(\d+)', href)
                        if pin_match:
                            pin_id = pin_match.group(1)
                    except:
                        pass
                            
                    # Create media item
                    media_items.append({
                        'url': image_url,
                        'alt': alt_text,
                        'title': alt_text,
                        'source_url': f"https://www.pinterest.com/pin/{pin_id}/" if pin_id else self.url,
                        'credits': f"Pinterest: {self.search_query}" if self.search_query else "Pinterest",
                        'type': 'image',
                        '_headers': {
                            'Referer': 'https://www.pinterest.com/',
                            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
                            'Accept': 'image/webp,image/avif,image/*,*/*;q=0.8',
                            'sec-ch-ua': '"Google Chrome";v="123", "Not:A-Brand";v="8", "Chromium";v="123"'
                        }
                    })
                    
                except Exception as e:
                    if self.debug_mode:
                        print(f"Error processing container: {e}")
                        
        except Exception as e:
            print(f"Error extracting from search page: {e}")
            traceback.print_exc()
            
        return media_items

    def _parse_pinterest_url(self):
        """Extract board ID, pin ID, username, or search query from the URL"""
        parsed_url = urlparse(self.url)
        url_path = parsed_url.path.strip('/')
        path_parts = url_path.split('/')
        query_params = parse_qs(parsed_url.query) # Moved query parsing here
        
        # Check if this is a search page
        if 'search' in url_path:
            self.is_search = True
            # Try to extract search query from query parameters
            if 'q' in query_params and query_params['q']:
                 self.search_query = query_params['q'][0] # Store the query
                 print(f"Detected search query: {self.search_query}")
            return
        
        if len(path_parts) < 1:
            return  # Homepage
            
        # Extract components based on URL structure
        if len(path_parts) >= 1:
            if path_parts[0] == 'pin':
                # Individual pin URL: pinterest.com/pin/123456789/
                if len(path_parts) >= 2:
                    self.pin_id = path_parts[1]
                    print(f"Detected pin ID: {self.pin_id}")
                    
            elif path_parts[0] == 'board':
                # Board URL: pinterest.com/board/username/boardname/
                if len(path_parts) >= 3:
                    self.username = path_parts[1]
                    board_name = path_parts[2]
                    self.board_id = f"{self.username}/{board_name}"
                    print(f"Detected board: {self.board_id}")
                    
            else:
                # Could be a user profile: pinterest.com/username/
                self.username = path_parts[0]
                
                if len(path_parts) >= 2:
                    # Could be board: pinterest.com/username/boardname/
                    board_name = path_parts[1]
                    if board_name not in ['pins', 'following', 'followers']:
                        self.board_id = f"{self.username}/{board_name}"
                        print(f"Detected board: {self.board_id}")

        # Check for short URLs (pin.it)
        if "pin.it" in self.url:
            print("Detected Pinterest short URL, will need to follow redirect")

    def get_content_directory(self):
        """
        Generate a Pinterest-specific directory structure based on the content type.
        Returns a tuple of (base_dir, content_specific_dir)
        Example: ('pinterest', 'search/man_ray') or ('pinterest', 'username/board_name')
        """
        # Base directory is always 'pinterest'
        base_dir = "pinterest"
        
        # Default subdirectory (fallback)
        content_parts = []
        
        # For search pages, use 'search' and the sanitized query
        if self.is_search and self.search_query:
            content_parts.append("search")
            content_parts.append(self._sanitize_directory_name(self.search_query))
            
        # For boards, use username/boardname (assuming board_id contains this structure)
        elif self.board_id:
             # Assuming board_id might be like 'username/board-name'
             parts = self.board_id.split('/')
             content_parts.extend(self._sanitize_directory_name(p) for p in parts)
            
        # For user profiles, use the username
        elif self.username:
            content_parts.append(self._sanitize_directory_name(self.username))
            
        # For individual pins, maybe use 'pin' and the ID
        elif self.pin_id:
            content_parts.append("pin")
            content_parts.append(self._sanitize_directory_name(self.pin_id))
            
        # Fallback using path components if specific parts weren't identified
        if not content_parts:
            parsed_url = urlparse(self.url)
            path_parts = parsed_url.path.strip('/').split('/')
            if path_parts:
                 content_parts.extend(self._sanitize_directory_name(p) for p in path_parts if p)

        # Ensure there's at least a default part
        if not content_parts:
            content_parts.append("default")
            
        # Join the parts to form the content-specific directory path
        content_specific_dir = os.path.join(*content_parts)
                
        print(f"Generated content directory: ('{base_dir}', '{content_specific_dir}')")
        return (base_dir, content_specific_dir)

    async def pre_process(self, page):
        """Perform pre-processing specific to Pinterest"""
        print(f"PinterestHandler: Pre-processing URL {self.url}")
        
        # Set up authentication
        self._setup_authentication()
    
        # First, try to get the Playwright page
        pw_page = await self.get_playwright_page(page)
        
        # Handle login if needed
        if self.auth_method == "login" and pw_page:
            login_success = await self._perform_login(pw_page)
            if not login_success:
                print("Warning: Pinterest login failed, continuing without authentication")
        
        # If using API, set up the client
        if self.auth_method == "api":
            self.api_client = self._setup_api_client()
        
        # If we have a pin ID, prioritize extracting that image first
        if self.pin_id and pw_page:
            print(f"Prioritizing extraction of pin ID: {self.pin_id}")
            try:
                # Wait for the main pin image to load
                await pw_page.wait_for_selector('div[data-test-id="pin-closeup-image"] img', timeout=5000)
                main_image = await pw_page.query_selector('div[data-test-id="pin-closeup-image"] img')
                if main_image:
                    src = await main_image.get_attribute('src')
                    if src and "pinimg.com" in src:
                        # Store this high-quality image URL immediately
                        high_res_url = re.sub(r'/\d+x/', '/originals/', src)
                        self.captured_media_urls.add(high_res_url)
                        print(f"Captured main pin image: {high_res_url}")
            except Exception as e:
                print(f"Error prioritizing pin image: {e}")
        
        # Set up network monitoring if we have a Playwright page
        if pw_page:
            await self._setup_network_monitoring_async(pw_page)
        
        # Then scroll the page to load more content
        if pw_page:
            print("Found Playwright page, scrolling to load content")
            await self._scroll_page_async(pw_page, scroll_count=8, scroll_delay_ms=1500)
        else:
            print("No Playwright page found, skipping scrolling")
                
        return page

    async def _setup_network_monitoring_async(self, pw_page):
        """Set up enhanced network monitoring to capture image URLs and API responses (async version)"""
        if not pw_page:
            print("No Playwright page available for network monitoring")
            return
                
        try:
            async def handle_response(response):
                if response.status == 200:
                    url = response.url
                    content_type = response.headers.get("content-type", "")
                    
                    # Prioritize Pinterest image content
                    if ("pinimg.com" in url and 
                        any(x in url for x in ['/originals/', '/736x/', '/564x/', '/474x/']) and
                        not any(x in url.lower() for x in ['/favicon', '/icon', '/avatar', '/16x16', '/32x32', '/64x64', '/30.png'])):
                        # This is likely a high-quality pin image
                        self.captured_media_urls.add(url)
                        print(f"Captured high-quality image URL via network: {url}")
                    
                    # Check for API responses containing image data
                    elif ("pinterest.com/resource/" in url or "api/v3" in url) and "application/json" in content_type:
                        try:
                            data = await response.json()
                            self._extract_urls_from_api_response(data)
                        except Exception as e:
                            if self.debug_mode:
                                print(f"Error extracting from API response: {e}")
                    
                    # Other image content types
                    elif content_type.startswith("image/") and "pinimg.com" in url:
                        self.captured_media_urls.add(url)
                            
            # Register the response handler
            pw_page.on("response", handle_response)
            print("Enhanced network monitoring set up for Pinterest media URLs")
                
        except Exception as e:
            print(f"Error setting up network monitoring: {e}")


    def _is_valid_pinterest_image(self, item):
        """This function doesn't use async operations, so it remains synchronous"""
        url = item.get('url', '')
        if not url or url.startswith("https://s.pinimg.com"):
            return False  # skip avatars and system icons
        if any(x in url for x in ["/user-avatar/", "profile_images", "/placeholder", "/static"]):
            return False
        if "&width=" in url:
            try:
                width = int(url.split("&width=")[1].split("&")[0])
                if width < 300:
                    return False
            except Exception:
                pass
        return True

    async def _scroll_page_async(self, page: AsyncPage, scroll_count=8, scroll_delay_ms=1500):
        """Scroll the page to load more content with improved reliability (async version)"""
        if not page:
            return
            
        try:
            # Get initial height
            initial_height = await page.evaluate('document.body.scrollHeight')
            
            for i in range(scroll_count):
                # Scroll with smoother increments
                await page.evaluate("""
                    window.scrollBy({
                        top: document.body.scrollHeight / 4,
                        behavior: 'smooth'
                    });
                """)
                print(f"Scrolling Pinterest page ({i+1}/{scroll_count})...")
                
                # Wait for content to load
                await page.wait_for_timeout(scroll_delay_ms)
                
                # Every second scroll, try to click "Load more" buttons
                if i % 2 == 0:
                    await self._click_load_more_async(page)
                
                # Get new height
                new_height = await page.evaluate('document.body.scrollHeight')
                
                # If height didn't change, we've reached the bottom or stuck
                if new_height == initial_height and i > 1:
                    print("Reached the end of scrollable content")
                    # Try one more explicit action to trigger more content
                    await page.keyboard.press("End")
                    await page.wait_for_timeout(scroll_delay_ms)
                    break
                    
                initial_height = new_height
            
        except Exception as e:
            print(f"Error during scrolling: {e}")


    def _convert_to_highest_res(self, url):
        """Convert Pinterest thumbnail URL to highest resolution version"""
        if not url or not isinstance(url, str):
            return url
            
        # Skip non-Pinterest URLs
        if 'pinimg.com' not in url:
            return url
        
        print(f"Converting URL: {url}")
        original_url = url
        
        # For 1200x images (already high-res), we can keep them
        if '/1200x/' in url:
            print(f"Already high-res (1200x): {url}")
            return url
            
        # Handle multi-dimension patterns (like 60x60)
        if re.search(r'/\d+x\d+/', url):
            url = re.sub(r'/\d+x\d+/', '/originals/', url)
            print(f"Multi-dimension pattern converted: {original_url} -> {url}")
            return url
            
        # Handle single dimension patterns (like 236x)
        size_pattern = re.compile(r'/(\d+x)/')
        match = size_pattern.search(url)
        
        if match:
            # Replace any size indicator with 'originals' or '1200x'
            high_res_url = size_pattern.sub('/1200x/', url)
            print(f"Single dimension pattern converted: {original_url} -> {high_res_url}")
            return high_res_url
        
        # For URLs without size pattern but still on pinimg.com
        for size in ['236x', '474x', '736x', 'pin-sm', 'pin-med', 'pin-small']:
            if f'/{size}/' in url:
                new_url = url.replace(f'/{size}/', '/originals/')
                print(f"Size pattern found and replaced: {original_url} -> {new_url}")
                return new_url
        
        print(f"No patterns matched, keeping original URL: {url}")
        return url

    async def _click_load_more_async(self, pw_page):
        """Try to find and click 'Load more' or similar buttons (async version)"""
        try:
            # Common selectors for load more buttons
            selectors = [
                'button:has-text("Load more")',
                'button:has-text("Show more")',
                'button:has-text("More")',
                'button:has-text("See more")',
                '[role="button"]:has-text("Load more")',
                '[role="button"]:has-text("Show more")',
                '[data-test-id="load-more"]',
                '[class*="loadMore"]',
                '[class*="load-more"]'
            ]
            
            for selector in selectors:
                try:
                    button = pw_page.locator(selector).first
                    is_visible = await button.is_visible()
                    if is_visible:
                        print(f"Clicking '{selector}' button")
                        await button.click()
                        await pw_page.wait_for_timeout(1500)  # Wait for new content to load
                        return True
                except Exception as e:
                    if self.debug_mode:
                        print(f"Error clicking '{selector}': {e}")
            
            return False
        except Exception as e:
            print(f"Error in click_load_more: {e}")
            return False

    async def _extract_media_from_html_async(self, page):
        """Extract media items from HTML content (async version)"""
        media_items = []
        
        try:
            html_content = await page.content()
            if not html_content:
                return media_items
                    
            print("Extracting images from Pinterest HTML content...")
            
            # Extract Pinterest image URLs - try multiple patterns
            # Pattern 1: Standard img tags with pinimg.com
            img_pattern = re.compile(r'<img[^>]+src=["\'](https?://[^"\']*pinimg\.com[^"\']*)["\']', re.IGNORECASE)
            img_matches = img_pattern.findall(html_content)
            
            # Add extracted URLs to media items
            for url in img_matches:
                # Skip small thumbnails, icons, avatars
                if any(x in url.lower() for x in ['favicon', 'icon', 'avatar', '16x16', '32x32', '64x64']):
                    continue
                
                # Try to upgrade to higher quality
                # If URL has a size like /236x/ or /736x/, try to get original
                image_url = re.sub(r'/\d+x/', '/originals/', url)
                
                media_items.append({
                    'url': image_url,
                    'alt': "Pinterest Image",
                    'title': "Pinterest Image",
                    'source_url': self.url,
                    'credits': "Pinterest",
                    'type': 'image',
                    '_headers': {
                        'Referer': 'https://www.pinterest.com/',
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
                        'Accept': 'image/webp,image/avif,image/*,*/*;q=0.8',
                        'sec-ch-ua': '"Google Chrome";v="123", "Not:A-Brand";v="8", "Chromium";v="123"'
                    }
                })
                
            # Pattern 2: Look for data-src attributes (lazy loading)
            data_src_pattern = re.compile(r'<img[^>]+data-src=["\'](https?://[^"\']*pinimg\.com[^"\']*)["\']', re.IGNORECASE)
            data_src_matches = data_src_pattern.findall(html_content)
            
            for url in data_src_matches:
                if any(x in url.lower() for x in ['favicon', 'icon', 'avatar', '16x16', '32x32', '64x64']):
                    continue
                
                # Try to upgrade to higher quality
                image_url = re.sub(r'/\d+x/', '/originals/', url)
                
                media_items.append({
                    'url': image_url,
                    'alt': "Pinterest Image (Lazy Loaded)",
                    'title': "Pinterest Image",
                    'source_url': self.url,
                    'credits': "Pinterest",
                    'type': 'image',
                    '_headers': {
                        'Referer': 'https://www.pinterest.com/',
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
                        'Accept': 'image/webp,image/avif,image/*,*/*;q=0.8',
                        'sec-ch-ua': '"Google Chrome";v="123", "Not:A-Brand";v="8", "Chromium";v="123"'
                    }
                })
                
            # Pattern 3: Search for background images with pinimg URLs
            bg_pattern = re.compile(r'background-image:\s*url\(["\']?(https?://[^"\'()]*pinimg\.com[^"\'()]*)["\']?\)', re.IGNORECASE)
            bg_matches = bg_pattern.findall(html_content)
            
            for url in bg_matches:
                if any(x in url.lower() for x in ['favicon', 'icon', 'avatar', '16x16', '32x32', '64x64']):
                    continue
                
                # Try to upgrade to higher quality
                image_url = re.sub(r'/\d+x/', '/originals/', url)
                
                media_items.append({
                    'url': image_url,
                    'alt': "Pinterest Background Image",
                    'title': "Pinterest Image",
                    'source_url': self.url,
                    'credits': "Pinterest",
                    'type': 'image',
                    '_headers': {
                        'Referer': 'https://www.pinterest.com/',
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
                        'Accept': 'image/webp,image/avif,image/*,*/*;q=0.8',
                        'sec-ch-ua': '"Google Chrome";v="123", "Not:A-Brand";v="8", "Chromium";v="123"'
                    }
                })
                
            # Pattern 4: Extract pin IDs and construct direct image URLs
            # Pinterest often has pin IDs in the HTML that can be used to construct image URLs
            pin_id_pattern = re.compile(r'pinterest\.com/pin/(\d+)', re.IGNORECASE)
            pin_id_matches = pin_id_pattern.findall(html_content)
            
            # Also look for PIN IDs in JSON data
            json_pin_pattern = re.compile(r'"id"\s*:\s*"(\d+)"', re.IGNORECASE)
            json_pin_matches = json_pin_pattern.findall(html_content)
            
            # Combine pin IDs from both sources
            all_pin_ids = set(pin_id_matches + json_pin_matches)
            
            for pin_id in all_pin_ids:
                # Construct original image URL from PIN ID
                media_items.append({
                    'url': f"https://i.pinimg.com/originals/pins/{pin_id}.jpg",
                    'alt': "Pinterest Pin",
                    'title': "Pinterest Pin",
                    'source_url': f"https://www.pinterest.com/pin/{pin_id}/",
                    'credits': "Pinterest",
                    'type': 'image',
                    '_headers': {
                        'Referer': 'https://www.pinterest.com/',
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
                        'Accept': 'image/webp,image/avif,image/*,*/*;q=0.8',
                        'sec-ch-ua': '"Google Chrome";v="123", "Not:A-Brand";v="8", "Chromium";v="123"'
                    }
                })
                
            # Pattern 5: Direct pinimg.com URLs from any HTML context
            pinimg_pattern = re.compile(r'(https?://[^"\'<>\s]*pinimg\.com[^"\'<>\s]*)', re.IGNORECASE)
            pinimg_matches = pinimg_pattern.findall(html_content)
            
            for url in pinimg_matches:
                if any(x in url.lower() for x in ['favicon', 'icon', 'avatar', '16x16', '32x32', '64x64']):
                    continue
                
                # Check if we already have this URL (might have found it with previous patterns)
                if url in [item['url'] for item in media_items]:
                    continue
                    
                # Try to upgrade to higher quality
                image_url = re.sub(r'/\d+x/', '/originals/', url)
                
                media_items.append({
                    'url': image_url,
                    'alt': "Pinterest Image (URL match)",
                    'title': "Pinterest Image",
                    'source_url': self.url,
                    'credits': "Pinterest",
                    'type': 'image',
                    '_headers': {
                        'Referer': 'https://www.pinterest.com/',
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
                        'Accept': 'image/webp,image/avif,image/*,*/*;q=0.8',
                        'sec-ch-ua': '"Google Chrome";v="123", "Not:A-Brand";v="8", "Chromium";v="123"'
                    }
                })
                
            print(f"HTML extraction found {len(media_items)} items")
                
        except Exception as e:
            print(f"Error extracting media from HTML: {e}")
            traceback.print_exc()
            
        return media_items

    def _get_best_image_from_srcset(self, srcset):
        """Parse srcset attribute to get highest quality image URL"""
        if not srcset:
            return None
            
        try:
            # Split the srcset string
            parts = srcset.split(',')
            highest_width = 0
            best_url = None
            
            # Find the highest resolution
            for part in parts:
                part = part.strip()
                if not part:
                    continue
                    
                # Extract width and URL
                match = re.search(r'(https?://[^ ]+) (\d+)w', part)
                if match:
                    url = match.group(1)
                    width = int(match.group(2))
                    
                    if width > highest_width:
                        highest_width = width
                        best_url = url
                        
            # Convert to highest resolution version if it's a Pinterest URL
            if best_url and 'pinimg.com' in best_url:
                best_url = self._convert_to_highest_res(best_url)
                
            return best_url
        except Exception as e:
            if self.debug_mode:
                print(f"Error parsing srcset: {e}")
            return None

    async def post_process(self, media_items, page=None):
        """Post-process media items to improve quality and remove duplicates"""
        if not media_items:
            return []
                    
        try:
            # Get a valid page object for URL verification if needed
            pw_page = None
            if page:
                pw_page = await self.get_playwright_page(page)
            
            # Improve image URLs where possible and verify they work
            verified_items = []
            for item in media_items:
                # Process by type
                if item['type'] == 'image' and 'pinimg.com' in item.get('url', ''):
                    # Convert to highest quality using our method
                    item['url'] = self._convert_to_highest_res(item['url'])
                    
                    # Fix headers for Pinterest images to avoid 403 errors
                    item['_headers'] = {
                        'Referer': 'https://www.pinterest.com/',
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
                        'Accept': 'image/webp,image/avif,image/*,*/*;q=0.8',
                        'sec-ch-ua': '"Google Chrome";v="123", "Not:A-Brand";v="8", "Chromium";v="123"'
                    }
                elif item['type'] == 'video':
                    # Make sure video URLs have proper headers
                    item['_headers'] = {
                        'Referer': 'https://www.pinterest.com/',
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
                        'Accept': 'video/mp4,video/webm,video/*,*/*;q=0.8',
                        'Range': 'bytes=0-'  # Important for video streaming
                    }
                
                # Additional processing for item titles
                if 'title' in item and 'credits' in item and item['credits'] not in item['title']:
                    # Add credits to title if relevant
                    if item['credits'] and item['credits'].startswith('Pinterest: '):
                        creator = item['credits'].replace('Pinterest: ', '')
                        if creator and creator not in item['title']:
                            item['title'] = f"{item['title']} by {creator}"
                
                # If we have a page object, verify the URL works
                if pw_page and 'url' in item:
                    if item['type'] == 'image':
                        verified_url = await self._verify_url_exists(pw_page, item['url'])
                        if verified_url:
                            item['url'] = verified_url
                            verified_items.append(item)
                        else:
                            print(f"Skipping invalid URL: {item['url']}")
                    else:
                        # For videos and other types, don't try to verify
                        verified_items.append(item)
                else:
                    verified_items.append(item)
                    
            # Remove duplicate URLs while preserving order
            unique_items = self._remove_duplicate_urls(verified_items)
                    
            print(f"Post-processing: {len(media_items)} → {len(unique_items)} unique items")
            return unique_items
                
        except Exception as e:
            print(f"Error during post-processing: {e}")
            traceback.print_exc()
            return media_items
            

    def _get_page_content(self, page):
        """Get HTML content from page object"""
        html_content = ""
        
        # Try different ways to get the content based on page type
        if PLAYWRIGHT_AVAILABLE:
            pw_page = self.get_playwright_page(page)
            if pw_page:
                try:
                    html_content = pw_page.content()
                    return html_content
                except Exception as e:
                    print(f"Error getting Playwright page content: {e}")
        
        # Try alternate methods to get content
        if hasattr(page, 'html_content'):
            return page.html_content
        elif hasattr(page, 'text'):
            return page.text
        else:
            return str(page)

    def _process_captured_network_urls(self):
        """Process URLs captured by network monitoring with better filtering"""
        media_items = []
        
        # Group by suspected pin ID to grab best versions
        pin_groups = {}
        
        for url in self.captured_media_urls:
            # Skip non-image URLs completely
            if not any(url.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']):
                continue
                
            # Skip JavaScript, CSS and other non-media files
            if any(ext in url.lower() for ext in ['.js', '.css', '.json', '.mjs', '.map', '.ico']):
                continue
                
            # Skip small assets and icons
            if any(x in url.lower() for ext in ['favicon', 'icon', 'avatar', 'profile', '16x16', '32x32', '64x64']):
                continue
                
            # Convert to highest resolution right away
            high_res_url = self._convert_to_highest_res(url)
                
            # Try to identify the pin ID from the URL for grouping
            path_parts = urlparse(high_res_url).path.split('/')
            
            # Group key can be filename or full URL
            if len(path_parts) >= 4:
                filename = path_parts[-1]
                group_key = os.path.splitext(filename)[0]  # Use filename without extension
            else:
                group_key = high_res_url
                
            if group_key not in pin_groups:
                pin_groups[group_key] = []
            pin_groups[group_key].append(high_res_url)
        
        # For each group, select the best quality URL
        for group_key, urls in pin_groups.items():
            best_url = None
            # Prioritize by known quality indicators
            for quality in ['originals', '736x', '564x', '474x', '236x']:
                for url in urls:
                    if f"/{quality}/" in url:
                        best_url = url
                        break
                if best_url:
                    break
                    
            # If no quality match found, just use the first URL
            if not best_url and urls:
                best_url = urls[0]
                
            if best_url:
                media_items.append({
                    'url': best_url,
                    'alt': f"Pinterest Image",
                    'title': f"Pinterest Image",
                    'source_url': self.url,
                    'credits': "Pinterest",
                    'type': 'image',
                    '_headers': {
                        'Referer': 'https://www.pinterest.com/',
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
                        'Accept': 'image/webp,image/avif,image/*,*/*;q=0.8',
                        'sec-ch-ua': '"Google Chrome";v="123", "Not:A-Brand";v="8", "Chromium";v="123"'
                    }
                })
                
        return media_items

    def _remove_duplicate_urls(self, media_items):
        """Remove duplicate URLs while preserving order"""
        seen_urls = set()
        unique_items = []
        
        for item in media_items:
            if item['url'] not in seen_urls:
                seen_urls.add(item['url'])
                unique_items.append(item)
                    
        return unique_items


    def _extract_pins_from_json(self, json_data):
        """Extract pin image URLs from JSON data"""
        media_items = []
        
        try:
            # This is a simplified version that looks for common patterns
            # in Pinterest's JSON structure
            
            # Check for 'pins' object (common in board/search pages)
            if isinstance(json_data, dict) and 'pins' in json_data:
                pins = json_data['pins']
                if isinstance(pins, dict):
                    for pin_id, pin_data in pins.items():
                        if isinstance(pin_data, dict) and 'images' in pin_data:
                            images = pin_data['images']
                            image_url = None
                            
                            # Try to get original size
                            if 'orig' in images:
                                image_url = images['orig'].get('url')
                            # Try other sizes in order of preference
                            elif '736x' in images:
                                image_url = images['736x'].get('url')
                            elif '474x' in images:
                                image_url = images['474x'].get('url')
                            elif '236x' in images:
                                image_url = images['236x'].get('url')
                                
                            if image_url:
                                # Try to get pin metadata
                                title = pin_data.get('title', "Pinterest Pin")
                                description = pin_data.get('description', "")
                                
                                media_items.append({
                                    'url': image_url,
                                    'alt': description or title,
                                    'title': title,
                                    'source_url': f"https://www.pinterest.com/pin/{pin_id}/",
                                    'credits': "Pinterest",
                                    'type': 'image',
                                    '_headers': {
                                        'Referer': 'https://www.pinterest.com/',
                                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
                                        'Accept': 'image/webp,image/avif,image/*,*/*;q=0.8',
                                        'sec-ch-ua': '"Google Chrome";v="123", "Not:A-Brand";v="8", "Chromium";v="123"'
                                    }
                                })
            
            # Recursively search any nested objects for pins
            if isinstance(json_data, dict):
                for key, value in json_data.items():
                    if isinstance(value, (dict, list)):
                        nested_items = self._extract_pins_from_json(value)
                        media_items.extend(nested_items)
            elif isinstance(json_data, list):
                for item in json_data:
                    if isinstance(item, (dict, list)):
                        nested_items = self._extract_pins_from_json(item)
                        media_items.extend(nested_items)
        
        except Exception as e:
            print(f"Error extracting pins from JSON: {e}")
            
        return media_items

    def _extract_urls_from_api_response(self, data):
        """Extract image URLs from Pinterest API responses"""
        if not data or not isinstance(data, (dict, list)):
            return
            
        try:
            # Look for image URLs in API response data
            if isinstance(data, dict):
                # Check for direct 'images' object
                if 'images' in data:
                    images = data['images']
                    if isinstance(images, dict):
                        # Try to get original image
                        if 'orig' in images and 'url' in images['orig']:
                            self.captured_media_urls.add(images['orig']['url'])
                        # Try other sizes
                        elif '736x' in images and 'url' in images['736x']:
                            self.captured_media_urls.add(images['736x']['url'])
                        elif '474x' in images and 'url' in images['474x']:
                            self.captured_media_urls.add(images['474x']['url'])
                
                # Check for 'pins' array
                if 'pins' in data and isinstance(data['pins'], list):
                    for pin in data['pins']:
                        if isinstance(pin, dict) and 'images' in pin:
                            images = pin['images']
                            if isinstance(images, dict):
                                # Try to get original image
                                if 'orig' in images and 'url' in images['orig']:
                                    self.captured_media_urls.add(images['orig']['url'])
                                # Try other sizes
                                elif '736x' in images and 'url' in images['736x']:
                                    self.captured_media_urls.add(images['736x']['url'])
                                elif '474x' in images and 'url' in images['474x']:
                                    self.captured_media_urls.add(images['474x']['url'])
                
                # Recursively check all nested objects
                for key, value in data.items():
                    if isinstance(value, (dict, list)):
                        self._extract_urls_from_api_response(value)
                        
            # If data is a list, check each item
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, (dict, list)):
                        self._extract_urls_from_api_response(item)
        
        except Exception as e:
            if self.debug_mode:
                print(f"Error extracting URLs from API response: {e}")

    async def get_playwright_page(self, page):
        """Get the Playwright page object from various possible input formats"""
        if hasattr(page, 'page'):
            # Adaptor object with page property
            return page.page
        elif AsyncPage and isinstance(page, AsyncPage):
            # Direct Playwright page
            return page
        elif hasattr(page, '_pw_page'):
            # Custom wrapper with _pw_page attribute
            return page._pw_page
        return None

    def _sanitize_directory_name(self, name):
        """Sanitize a string to be used as a directory name"""
        if not name:
            return "default"
            
        # Replace spaces and special characters
        sanitized = re.sub(r'[\\/*?:"<>|]', '_', name)
        sanitized = re.sub(r'\s+', '_', sanitized)
        
        # Truncate if too long
        if len(sanitized) > 64:
            sanitized = sanitized[:61] + "..."
            
        return sanitized

    async def _verify_url_exists(self, page, url):
        """Verify if a Pinterest image URL actually exists before attempting download"""
        try:
            response = await page.context.request.head(url, headers={
                'Referer': 'https://www.pinterest.com/',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
            })
            
            status = response.status
            print(f"URL verification: {url} - Status: {status}")
            
            # If 404 or other error, try with different resolutions
            if status >= 400 and '/originals/' in url:
                # Try 1200x as fallback
                fallback_url = url.replace('/originals/', '/1200x/')
                print(f"Original image not found, trying fallback: {fallback_url}")
                
                fallback_response = await page.context.request.head(fallback_url, headers={
                    'Referer': 'https://www.pinterest.com/',
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
                })
                
                if fallback_response.status < 400:
                    print(f"Fallback URL valid: {fallback_url}")
                    return fallback_url
                    
                # Try 736x as second fallback
                fallback_url = url.replace('/originals/', '/736x/')
                print(f"1200x not found, trying second fallback: {fallback_url}")
                
                fallback_response = await page.context.request.head(fallback_url, headers={
                    'Referer': 'https://www.pinterest.com/',
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
                })
                
                if fallback_response.status < 400:
                    print(f"Second fallback URL valid: {fallback_url}")
                    return fallback_url
                    
            return url if status < 400 else None
        except Exception as e:
            print(f"Error verifying URL {url}: {e}")
        return None