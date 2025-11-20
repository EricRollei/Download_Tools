"""
Cosmos Handler

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
Cosmos.so-specific handler for the Web Image Scraper
Handles multi-level gallery navigation and authentication.
"""

from site_handlers.base_handler import BaseSiteHandler
from urllib.parse import urljoin, urlparse, parse_qs
from typing import List, Dict, Any, Optional, Union
import os
import json
import re
import time
import traceback
import asyncio

# Try importing Playwright types safely
try:
    from playwright.async_api import Page as AsyncPage
    from playwright.async_api import TimeoutError as PlaywrightTimeoutError
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    AsyncPage = None
    PlaywrightTimeoutError = Exception
    PLAYWRIGHT_AVAILABLE = False

class CosmosHandler(BaseSiteHandler):
    """
    Handler for Cosmos.so, a platform for visual discovery and curation.
    Supports multi-level gallery navigation and authentication.
    """

    @classmethod
    def can_handle(cls, url):
        """Check if this handler can process the URL"""
        return "cosmos.so" in url.lower()

    def __init__(self, url, scraper=None):
        """Initialize with Cosmos-specific properties"""
        super().__init__(url, scraper)
        
        # Set debug mode early
        self.debug_mode = getattr(scraper, 'debug_mode', True)  # Enable debug by default for Cosmos
        
        # Now determine page type and other properties
        self.page_type = self._determine_page_type(url)
        self.collection_id = None
        self.username = None
        self._extract_identifiers_from_url()
        
        # Set authentication flag
        self.requires_authentication = True
        self.auth_loaded = False
        self.auth_cookies = []
        
        # Load authentication configuration and cookies
        self._load_auth_config()
        
        # Track visited element IDs to avoid duplicates
        self.visited_element_ids = set()
        
        # Debug counters
        self.debug_stats = {
            'cards_found': 0,
            'cards_processed': 0,
            'images_extracted': 0,
            'errors_encountered': 0,
            'navigation_failures': 0,
            'authentication_attempts': 0
        }
        
        if self.debug_mode:
            print(f"🔍 [COSMOS DEBUG] Handler initialized for URL: {url}")
            print(f"🔍 [COSMOS DEBUG] Page Type: {self.page_type}")
            print(f"🔍 [COSMOS DEBUG] Authentication Required: {self.requires_authentication}")
            print(f"🔍 [COSMOS DEBUG] Collection ID: {self.collection_id}")
            print(f"🔍 [COSMOS DEBUG] Username: {self.username}")

    def _determine_page_type(self, url):
        """Determine what type of Cosmos page we're dealing with - enhanced detection"""
        parsed_url = urlparse(url)
        path = parsed_url.path.strip('/')
        query = parsed_url.query
        
        if not path: 
            return "home"
            
        path_parts = path.split('/')
        
        # Enhanced pattern matching for Cosmos URLs
        if path.startswith('collection/'):
            return "collection"
        elif path.startswith('element/'):
            return "element"
        elif path.startswith('element-group/'):
            return "element_group"
        elif path.startswith('board/'):
            return "board"
        elif path.startswith('user/'):
            return "profile"
        elif path.startswith('search'):
            # Check if it's a keyword search
            if 'elements/' in path or query:
                if self.debug_mode:
                    print(f"🔍 [COSMOS DEBUG] Detected search gallery pattern: {path}")
                return "search_gallery"
            return "search"
        elif path.startswith('e/') and len(path_parts) == 2:
            # Handle shortcut URLs like /e/1721224338 (element shortcut)
            if self.debug_mode:
                print(f"🔍 [COSMOS DEBUG] Detected element shortcut pattern: {path}")
            return "element"
        elif path.startswith('c/') and len(path_parts) == 2:
            # Handle shortcut URLs like /c/collection_id (collection shortcut)
            if self.debug_mode:
                print(f"🔍 [COSMOS DEBUG] Detected collection shortcut pattern: {path}")
            return "collection"
        elif path.startswith('b/') and len(path_parts) == 2:
            # Handle shortcut URLs like /b/board_id (board shortcut)
            if self.debug_mode:
                print(f"🔍 [COSMOS DEBUG] Detected board shortcut pattern: {path}")
            return "board"
        elif len(path_parts) >= 2:
            # Check for user gallery patterns like "carororo/collection-name"
            # These are typically user galleries or collections
            if self.debug_mode:
                print(f"🔍 [COSMOS DEBUG] Detected user gallery pattern: {path_parts[0]}/{path_parts[1]}")
            return "user_gallery"  # More specific than just "profile"
        elif len(path_parts) == 1:
            # Single path component, likely a user profile like "carororo"
            if self.debug_mode:
                print(f"🔍 [COSMOS DEBUG] Detected single user profile: {path_parts[0]}")
            return "profile"
        
        return "other"

    def _extract_identifiers_from_url(self):
        """Extract collection ID, username, etc. from the URL - enhanced for various patterns"""
        parsed_url = urlparse(self.url)
        path = parsed_url.path.strip('/')
        path_parts = path.split('/')
        
        try:
            if self.page_type == "collection" and len(path_parts) > 1:
                self.collection_id = path_parts[1]
            elif self.page_type == "element":
                if len(path_parts) > 1:
                    # Handle both /element/ID and /e/ID patterns
                    if path_parts[0] == 'e':
                        self.element_id = path_parts[1]
                    elif path_parts[0] == 'element':
                        self.element_id = path_parts[1]
            elif self.page_type == "profile":
                if len(path_parts) >= 1:
                    # For URLs like "carororo"
                    self.username = path_parts[0]
            elif self.page_type == "user_gallery":
                if len(path_parts) >= 2:
                    # For URLs like "jha/au-naturel-nude-human"
                    self.username = path_parts[0]
                    self.collection_id = path_parts[1]
                    if self.debug_mode:
                        print(f"🔍 [COSMOS DEBUG] Detected user gallery: {self.username}/{self.collection_id}")
            elif self.page_type == "board" and len(path_parts) > 1:
                # Handle both /board/ID and /b/ID patterns
                if path_parts[0] == 'b':
                    self.collection_id = path_parts[1]
                elif path_parts[0] == 'board':
                    self.collection_id = path_parts[1]
            elif self.page_type == "element_group" and len(path_parts) > 1:
                self.element_group_id = path_parts[1]
        except IndexError:
            if self.debug_mode: 
                print("IndexError during identifier extraction from URL path.")
        
        if self.debug_mode:
            print(f"  Extracted Identifiers: username={self.username}, collection_id={self.collection_id}")
            if hasattr(self, 'element_id'):
                print(f"    Element ID: {self.element_id}")
            if hasattr(self, 'element_group_id'):
                print(f"    Element Group ID: {self.element_group_id}")

    def _load_auth_config(self):
        """Load authentication configuration including cookies from auth_config.json"""
        try:
            # Get the directory containing this file
            current_dir = os.path.dirname(os.path.abspath(__file__))
            # Navigate to the configs directory 
            config_path = os.path.join(os.path.dirname(current_dir), 'configs', 'auth_config.json')
            
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    auth_config = json.load(f)
                
                cosmos_config = auth_config.get('sites', {}).get('cosmos.so', {})
                
                if cosmos_config:
                    self.auth_cookies = cosmos_config.get('cookies', [])
                    self.auth_loaded = True
                    
                    if self.debug_mode:
                        print(f"🔍 [COSMOS DEBUG] Loaded {len(self.auth_cookies)} authentication cookies")
                        print(f"🔍 [COSMOS DEBUG] Auth config includes user: {cosmos_config.get('username', 'unknown')}")
                        
                        # Show key cookies for debugging
                        key_cookies = ['cosmos_accessToken', 'cosmos_refreshToken', 'cookie_notice_accepted']
                        for cookie in self.auth_cookies:
                            if cookie.get('name') in key_cookies:
                                masked_value = cookie.get('value', '')[:20] + '...' if len(cookie.get('value', '')) > 20 else cookie.get('value', '')
                                print(f"🔍 [COSMOS DEBUG] Key cookie {cookie.get('name')}: {masked_value}")
                else:
                    if self.debug_mode:
                        print("🔍 [COSMOS DEBUG] No cosmos.so configuration found in auth_config.json")
            else:
                if self.debug_mode:
                    print(f"🔍 [COSMOS DEBUG] Auth config file not found at: {config_path}")
                    
        except Exception as e:
            if self.debug_mode:
                print(f"🔍 [COSMOS DEBUG] Error loading auth config: {e}")
                traceback.print_exc()

    async def _apply_cookies_to_page(self, page):
        """Apply stored cookies to the Playwright page for authentication"""
        if not self.auth_cookies:
            if self.debug_mode:
                print("🔍 [COSMOS DEBUG] No cookies available to apply")
            return False
            
        try:
            # Convert our cookies to Playwright format
            playwright_cookies = []
            for cookie in self.auth_cookies:
                pw_cookie = {
                    'name': cookie.get('name', ''),
                    'value': cookie.get('value', ''),
                    'domain': cookie.get('domain', ''),
                    'path': cookie.get('path', '/'),
                }
                
                # Add optional fields if they exist
                if 'secure' in cookie:
                    pw_cookie['secure'] = cookie['secure']
                if 'httpOnly' in cookie:
                    pw_cookie['httpOnly'] = cookie['httpOnly']
                if 'sameSite' in cookie and cookie['sameSite'] not in ['unspecified', None, '']:
                    # Map sameSite values to what Playwright expects
                    same_site = cookie['sameSite'].lower()
                    if same_site in ['strict', 'lax', 'none']:
                        pw_cookie['sameSite'] = same_site.capitalize()
                    # Skip invalid sameSite values like 'unspecified'
                
                # Handle domain formatting - ensure it starts with dot for proper domain cookies
                domain = cookie.get('domain', '')
                if domain and not domain.startswith('.') and 'cosmos.so' in domain:
                    # For cosmos.so domains, ensure proper domain cookie format
                    if domain == 'www.cosmos.so':
                        pw_cookie['domain'] = '.cosmos.so'  # Make it work for both www and main domain
                    elif domain == 'cosmos.so':
                        pw_cookie['domain'] = '.cosmos.so'
                else:
                    pw_cookie['domain'] = domain
                    
                playwright_cookies.append(pw_cookie)
            
            # Apply cookies to the page context
            await page.context.add_cookies(playwright_cookies)
            
            if self.debug_mode:
                print(f"🔍 [COSMOS DEBUG] Applied {len(playwright_cookies)} cookies to page context")
                # Print key authentication cookies for debugging
                for cookie in playwright_cookies:
                    if cookie['name'] in ['cosmos_accessToken', 'cosmos_refreshToken']:
                        masked_value = cookie['value'][:20] + '...' if len(cookie['value']) > 20 else cookie['value']
                        print(f"🔍 [COSMOS DEBUG] Applied key cookie {cookie['name']}: {masked_value}")
                        print(f"    Domain: {cookie['domain']}, Secure: {cookie.get('secure', False)}")
                self.debug_stats['authentication_attempts'] += 1
            
            return True
            
        except Exception as e:
            if self.debug_mode:
                print(f"🔍 [COSMOS DEBUG] Error applying cookies: {e}")
                traceback.print_exc()
                self.debug_stats['errors_encountered'] += 1
            return False

    def prefers_api(self) -> bool:
        """Cosmos handler does not use a public API."""
        return False

    def get_content_directory(self):
        """Generate Cosmos-specific directory structure."""
        base_dir = "cosmos"
        content_parts = []
        
        if self.page_type == "collection":
            content_parts.extend(["collection", self.collection_id or "unknown_collection"])
        elif self.page_type == "profile":
            username_sanitized = self._sanitize_directory_name(self.username) if self.username else "unknown_user"
            content_parts.extend(["user", username_sanitized])
        elif self.page_type == "user_gallery":
            username_sanitized = self._sanitize_directory_name(self.username) if self.username else "unknown_user"
            collection_sanitized = self._sanitize_directory_name(self.collection_id) if self.collection_id else "unknown_collection"
            content_parts.extend(["user", username_sanitized, collection_sanitized])
        elif self.page_type == "element":
            # Extract element ID from URL if available
            path_parts = urlparse(self.url).path.strip('/').split('/')
            element_id = path_parts[1] if len(path_parts) > 1 else "unknown_element"
            content_parts.extend(["element", element_id])
        elif self.page_type == "search" or self.page_type == "search_gallery":
            # Extract search query from URL
            parsed_url = urlparse(self.url)
            if '/search/elements/' in parsed_url.path:
                # Extract search term from path like '/search/elements/naked%20yoga'
                search_term = parsed_url.path.split('/search/elements/')[-1]
                search_term = self._sanitize_directory_name(search_term.replace('%20', '_').replace('%', ''))
            else:
                # Try to get from query parameters
                query_params = parse_qs(parsed_url.query)
                search_term = query_params.get('q', ['general_search'])[0]
                search_term = self._sanitize_directory_name(search_term)
            content_parts.extend(["search", search_term])
        elif self.page_type == "board":
            content_parts.extend(["board", self.collection_id or "unknown_board"])
        elif self.page_type == "element_group":
            path_parts = urlparse(self.url).path.strip('/').split('/')
            group_id = path_parts[1] if len(path_parts) > 1 else "unknown_group"
            content_parts.extend(["element_group", group_id])
        else:
            path_components = [self._sanitize_directory_name(p) for p in urlparse(self.url).path.strip('/').split('/') if p]
            content_parts.extend(path_components[:2] if path_components else ["general"])

        content_specific_dir = os.path.join(*[p for p in content_parts if p])
        if not content_specific_dir: 
            content_specific_dir = "general"

        return (base_dir, content_specific_dir)

    def _sanitize_directory_name(self, name):
        """Sanitize a string to be safe for directory names"""
        if not name:
            return "unknown"
        
        # Replace URL encoding and special characters
        name = name.replace('%20', '_').replace('%', '')
        
        # Remove or replace unsafe characters
        import re
        name = re.sub(r'[<>:"/\\|?*]', '_', name)
        name = re.sub(r'[^\w\-_.]', '_', name)
        
        # Remove multiple underscores and clean up
        name = re.sub(r'_+', '_', name).strip('_')
        
        # Limit length
        return name[:50] if len(name) > 50 else name

    def get_trusted_domains(self) -> list:
        """Return trusted domains for Cosmos content"""
        return ["cdn.cosmos.so", "cosmos.so", "www.cosmos.so", "cosmos-images.s3.amazonaws.com"]

    def _load_api_credentials(self):
        """
        Loads API credentials from the scraper's auth_data based on the site's domain.
        Dynamically sets attributes on the handler instance for all found key-value pairs.
        """
        print(f"Loading credentials for {self.__class__.__name__}")
        self.api_available = False # Default to False

        if not hasattr(self, 'scraper') or self.scraper is None:
            print("No scraper instance available")
            return False
            
        if not hasattr(self.scraper, 'auth_config') or not self.scraper.auth_config:
            print("No auth_config found in scraper")
            return False

        # Get auth configuration and check for valid structure
        auth_config = self.scraper.auth_config
        if not isinstance(auth_config, dict):
            print("Invalid auth_config structure")
            return False
            
        # Check if sites field exists and extract credentials
        if 'sites' in auth_config:
            auth_data = auth_config.get('sites', {})
        else:
            auth_data = auth_config  # Assume the auth_config itself is the sites dictionary
            
        if not auth_data:
            print("Empty auth data")
            return False

        # Try to find credentials for this domain
        domain_key = self._get_domain_key()
        if not domain_key or domain_key not in auth_data:
            print(f"No credentials found for domain: {domain_key}")
            return False
            
        # Get credentials and set as attributes
        credentials = auth_data[domain_key]
        print(f"Found credentials for {domain_key}: {list(credentials.keys())}")
        
        for key, value in credentials.items():
            # Fix for key issue in cosmos.so credentials where "password " has a space
            clean_key = key.strip()
            print(f"Setting attribute {clean_key} from auth config")
            setattr(self, clean_key, value)
            
        # Add a special check for the space in "password " key
        if "password " in credentials:
            self.password = credentials["password "]
            print("Fixed password attribute with space in key")
        
        # Verify we have the necessary auth info - support both cookie and password auth
        if hasattr(self, 'auth_type') and getattr(self, 'auth_type') == 'cookie':
            # For cookie-based auth, check if we have cookies
            if hasattr(self, 'cookies') and self.cookies:
                print(f"Successfully loaded cookie-based auth credentials for cosmos.so")
                self.auth_loaded = True
                # Load cookies into our format
                if not self.auth_cookies:  # Only load if not already loaded
                    self.auth_cookies = self.cookies
                return True
            else:
                print("Missing required cookies for cookie-based authentication")
                return False
        elif hasattr(self, 'username') and hasattr(self, 'password'):
            print(f"Successfully loaded auth credentials for {self.username}")
            self.auth_loaded = True
            return True
        else:
            print("Missing required username or password fields")
            return False

    async def _run_interaction_sequence(self, page, sequence):
        for step in sequence:
            try:
                if step["type"] == "goto":
                    await page.goto(step["url"])
                elif step["type"] == "wait_for_selector":
                    await page.wait_for_selector(step["selector"])
                elif step["type"] == "fill":
                    await page.fill(step["selector"], step["value"])
                elif step["type"] == "click":
                    await page.click(step["selector"])
                elif step["type"] == "press":
                    await page.press(step["selector"], step["key"])
                elif step["type"] == "wait_for_timeout":
                    await page.wait_for_timeout(step["timeout"])
            except Exception as e:
                print(f"Interaction step failed: {step} - {e}")
                
    async def authenticate_with_cosmos(self, page: AsyncPage, interaction_sequence=None) -> bool:
        """
        Perform authentication with Cosmos.so, using cookies first, then fallback to login form.
        """
        if not page:
            print("Cannot authenticate: Page object is None")
            return False

        # Try cookie-based authentication first
        if self.auth_loaded and self.auth_cookies:
            if self.debug_mode:
                print("🔍 [COSMOS DEBUG] Attempting cookie-based authentication...")
            
            try:
                # Apply cookies to the page
                cookie_success = await self._apply_cookies_to_page(page)
                
                if cookie_success:
                    # Navigate to the target URL with cookies
                    if self.debug_mode:
                        print(f"🔍 [COSMOS DEBUG] Navigating to target URL with cookies: {self.url}")
                    
                    try:
                        await page.goto(self.url, timeout=30000, wait_until="networkidle")
                    except Exception as nav_error:
                        if self.debug_mode:
                            print(f"⚠️ [COSMOS DEBUG] Navigation with networkidle failed, trying domcontentloaded: {nav_error}")
                        await page.goto(self.url, timeout=30000, wait_until="domcontentloaded")
                    
                    await page.wait_for_timeout(3000)  # Give time for auth to take effect
                    
                    # Check if we're logged in by looking for user-specific elements
                    is_logged_in = await self._check_if_logged_in(page)
                    
                    if is_logged_in:
                        if self.debug_mode:
                            print("✅ [COSMOS DEBUG] Cookie authentication successful!")
                        return True
                    else:
                        if self.debug_mode:
                            print("⚠️ [COSMOS DEBUG] Cookies applied but login check failed")
                            print("🔍 [COSMOS DEBUG] Proceeding anyway - might still work for content access")
                        # For cookie-based auth, proceed even if login check is unclear
                        return True
                
            except Exception as e:
                if self.debug_mode:
                    print(f"⚠️ [COSMOS DEBUG] Cookie authentication failed: {e}")
                    traceback.print_exc()
                self.debug_stats['errors_encountered'] += 1

        # Fall back to form-based authentication if we have username/password
        if hasattr(self, 'auth_type') and getattr(self, 'auth_type') == 'cookie':
            # For cookie-only configurations, return success if cookies were applied
            if self.auth_loaded and self.auth_cookies:
                if self.debug_mode:
                    print("✅ [COSMOS DEBUG] Cookie-only auth configuration - assuming success")
                return True
            else:
                if self.debug_mode:
                    print("⚠️ [COSMOS DEBUG] Cookie-only auth but no cookies loaded")
                return False
            
        if self.debug_mode:
            print("🔍 [COSMOS DEBUG] Falling back to form-based authentication...")

        # Load credentials directly (only for non-cookie auth)
        auth_success = self._load_api_credentials()
        if not auth_success:
            print("Failed to load Cosmos auth credentials")
            return False

        # Get interaction_sequence from scraper if not passed
        if interaction_sequence is None and hasattr(self.scraper, "interaction_sequence"):
            interaction_sequence = getattr(self.scraper, "interaction_sequence", None)

        if interaction_sequence:
            # Substitute credentials
            for step in interaction_sequence:
                if "value" in step:
                    if step["value"] == "<USERNAME>":
                        step["value"] = self.username
                    if step["value"] == "<PASSWORD>":
                        step["value"] = self.password
            await self._run_interaction_sequence(page, interaction_sequence)
            # Optionally check if logged in
            return await self._check_if_logged_in(page)
        else:
            # --- Hardcoded login logic as fallback ---
            try:
                await page.goto("https://cosmos.so/login", timeout=30000)
                await page.wait_for_timeout(2000)  # Wait for page to stabilize

                # Wait for login form
                try:
                    email_input = page.locator('input[type="email"]')
                    await email_input.wait_for(timeout=10000)
                    print("Login form found")
                except Exception as e:
                    print(f"Login form not found: {e}")
                    return False

                # Fill email
                await email_input.fill(self.username)
                print(f"Filled email: {self.username}")

                # Find and click continue button
                try:
                    continue_button = page.locator('button[type="submit"]')
                    await continue_button.click()
                    print("Clicked continue button")
                    await page.wait_for_timeout(2000)
                except Exception as e:
                    print(f"Error clicking continue: {e}")
                    # Try to continue anyway

                # Fill password
                try:
                    password_input = page.locator('input[type="password"]')
                    await password_input.wait_for(timeout=10000)
                    await password_input.fill(self.password)
                    print("Filled password")
                except Exception as e:
                    print(f"Password field error: {e}")
                    return False

                # Click login button
                try:
                    login_button = page.locator('button[type="submit"]')
                    await login_button.click()
                    print("Clicked login button")
                except Exception as e:
                    print(f"Error clicking login button: {e}")
                    return False

                # Wait for navigation
                await page.wait_for_timeout(5000)

                # Verify login
                try:
                    logged_in = await self._check_if_logged_in(page)
                    if logged_in:
                        print("Successfully logged in to Cosmos")
                        return True
                    else:
                        print("Login attempt failed")
                        return False
                except Exception as e:
                    print(f"Error verifying login: {e}")
                    return False

            except Exception as e:
                print(f"Authentication error: {e}")
                traceback.print_exc()
                return False

    async def _check_if_logged_in(self, page) -> bool:
        """
        Check if we're logged in to Cosmos with enhanced debugging
        """
        try:
            if self.debug_mode:
                print("🔍 [COSMOS DEBUG] Checking authentication status...")
            
            # Check for authentication cookies first (most reliable)
            if self.auth_cookies:
                try:
                    cookies = await page.context.cookies()
                    cosmos_cookies = [c for c in cookies if 'cosmos' in c['name'].lower()]
                    
                    if cosmos_cookies:
                        if self.debug_mode:
                            print(f"🔍 [COSMOS DEBUG] Found {len(cosmos_cookies)} cosmos-related cookies")
                        
                        # Look specifically for access token
                        access_token_cookies = [c for c in cosmos_cookies if 'accesstoken' in c['name'].lower()]
                        if access_token_cookies:
                            if self.debug_mode:
                                print(f"✅ [COSMOS DEBUG] Found access token cookie - assuming authenticated")
                            return True
                        
                        # If we have cosmos cookies but no access token, still might be authenticated
                        if len(cosmos_cookies) >= 2:  # Multiple cosmos cookies usually means auth
                            if self.debug_mode:
                                print(f"✅ [COSMOS DEBUG] Multiple cosmos cookies present - likely authenticated")
                            return True
                            
                except Exception as e:
                    if self.debug_mode:
                        print(f"⚠️ [COSMOS DEBUG] Error checking cookies: {e}")
            
            # Look for elements that would indicate a logged-in state
            logged_in_selectors = [
                'button[data-testid="HeaderUserMenu__button"]',
                'button[aria-label="User menu"]',
                'img[alt*="profile picture"]',
                '[data-testid="header-user-menu"]',
                '.user-avatar',
                'button:has-text("Profile")',
                '[aria-label*="user menu"]',
                '[data-testid="user-menu"]',
                'button[aria-label*="User"]',
                '.header-user-menu',
                'nav button[data-testid*="user"]'
            ]
            
            for selector in logged_in_selectors:
                try:
                    element = page.locator(selector)
                    is_visible = await element.is_visible(timeout=2000)  # Reduced timeout
                    if is_visible:
                        if self.debug_mode:
                            print(f"✅ [COSMOS DEBUG] Found logged-in indicator: {selector}")
                        return True
                except Exception as e:
                    if self.debug_mode:
                        print(f"🔍 [COSMOS DEBUG] Selector {selector} not found: {e}")
                    continue
            
            # Check for login button which indicates not logged in
            logout_selectors = [
                'button:has-text("Log In")', 
                'a:has-text("Log In")',
                'button:has-text("Sign In")',
                'a:has-text("Sign In")',
                '[data-testid="login-button"]',
                'button:has-text("Login")',
                'a[href*="login"]'
            ]
            
            for selector in logout_selectors:
                try:
                    element = page.locator(selector)
                    is_visible = await element.is_visible(timeout=2000)  # Reduced timeout
                    if is_visible:
                        if self.debug_mode:
                            print(f"❌ [COSMOS DEBUG] Found login button, not authenticated: {selector}")
                        return False
                except Exception as e:
                    if self.debug_mode:
                        print(f"🔍 [COSMOS DEBUG] Login selector {selector} not found: {e}")
                    continue
            
            # If we have auth cookies loaded, assume we're authenticated even if we can't verify via UI
            if self.auth_loaded and self.auth_cookies:
                if self.debug_mode:
                    print(f"✅ [COSMOS DEBUG] Auth cookies loaded, assuming authenticated")
                return True
            
            # Default to not authenticated if we can't determine
            if self.debug_mode:
                print(f"⚠️ [COSMOS DEBUG] Could not determine authentication status, defaulting to not authenticated")
            return False
            
        except Exception as e:
            if self.debug_mode:
                print(f"❌ [COSMOS DEBUG] Error checking login status: {e}")
                traceback.print_exc()
            # If error and we have cookies, assume authenticated
            return self.auth_loaded and bool(self.auth_cookies)

    async def extract_with_direct_playwright(self, page, **kwargs) -> list:
        """Extract media using direct Playwright browsing."""
        if self.debug_mode:
            print(f"🔍 [COSMOS DEBUG] Starting extraction for page type: {self.page_type}")
            print(f"🔍 [COSMOS DEBUG] Current URL: {page.url}")
            print(f"🔍 [COSMOS DEBUG] Target URL: {self.url}")
        
        # Verify page object
        if not page:
            print("❌ [COSMOS ERROR] Page object is None, cannot extract content")
            return []
            
        # Save initial page state for debugging
        if self.debug_mode:
            try:
                page_title = await page.title()
                print(f"🔍 [COSMOS DEBUG] Page title: {page_title}")
            except Exception as e:
                print(f"⚠️ [COSMOS DEBUG] Could not get page title: {e}")
                
        # Authenticate if needed
        if self.requires_authentication:
            self.debug_stats['authentication_attempts'] += 1
            if self.debug_mode:
                print("🔐 [COSMOS DEBUG] Attempting authentication...")
            
            auth_success = await self.authenticate_with_cosmos(page)
            if not auth_success:
                print("⚠️ [COSMOS WARNING] Not authenticated, some content may be unavailable")
            else:
                if self.debug_mode:
                    print("✅ [COSMOS DEBUG] Successfully authenticated")
                # Navigate back to original URL after login
                await page.goto(self.url, timeout=30000)
        
        # Add delay for page to fully load
        if self.debug_mode:
            print("🔍 [COSMOS DEBUG] Waiting for page to load...")
        await page.wait_for_timeout(3000)
        
        # Check page content after load
        if self.debug_mode:
            try:
                body_text = await page.locator('body').text_content()
                print(f"🔍 [COSMOS DEBUG] Page body length: {len(body_text) if body_text else 0} characters")
                
                # Check for common Cosmos elements
                cards = await page.locator('button[data-testid="ElementTileLink__a"]').count()
                elements = await page.locator('button[data-element-id]').count()
                images = await page.locator('img').count()
                
                print(f"🔍 [COSMOS DEBUG] Found on page:")
                print(f"    - ElementTileLink cards: {cards}")
                print(f"    - Data-element-id buttons: {elements}")
                print(f"    - Total images: {images}")
                
            except Exception as e:
                print(f"⚠️ [COSMOS DEBUG] Error analyzing page content: {e}")
        
        # Extract media based on page type
        media_items = []
        
        try:
            # First perform extensive auto-scroll to load more content  
            if self.debug_mode:
                print("🔍 [COSMOS DEBUG] Starting extensive auto-scroll to load content...")
            await self._auto_scroll_cosmos_page(page, max_scrolls=50, delay_ms=1200)
            
            if self.page_type in ["element", "element_group"]:
                if self.debug_mode:
                    print("🔍 [COSMOS DEBUG] Extracting single element/group images...")
                # We're on a single element page or element group page
                items = await self._extract_single_element_images(page)
                media_items.extend(items)
                self.debug_stats['images_extracted'] += len(items)
                
            elif self.page_type in ["collection", "board", "profile", "search", "home", "search_gallery", "user_gallery"]:
                if self.debug_mode:
                    print("🔍 [COSMOS DEBUG] Extracting gallery elements...")
                
                # Different approach based on specific page type
                if self.page_type == "search_gallery":
                    # Search results with elements like "naked yoga"
                    if self.debug_mode:
                        print("🔍 [COSMOS DEBUG] Handling search gallery page...")
                    thumbnail_items = await self._extract_search_gallery_images(page)
                elif self.page_type == "user_gallery":
                    # User galleries like "carororo/collection-name"
                    if self.debug_mode:
                        print("🔍 [COSMOS DEBUG] Handling user gallery page...")
                    thumbnail_items = await self._extract_user_gallery_images(page)
                elif self.page_type == "profile":
                    # User profile main page like "carororo"
                    if self.debug_mode:
                        print("🔍 [COSMOS DEBUG] Handling user profile page...")
                    thumbnail_items = await self._extract_profile_gallery_images(page)
                else:
                    # Generic gallery handling
                    thumbnail_items = await self._extract_thumbnail_gallery_images(page)
                
                if thumbnail_items:
                    if self.debug_mode:
                        print(f"✅ [COSMOS DEBUG] Found {len(thumbnail_items)} thumbnail images")
                    media_items.extend(thumbnail_items)
                    self.debug_stats['images_extracted'] += len(thumbnail_items)
                else:
                    # Fallback to click-through navigation if thumbnails fail
                    if self.debug_mode:
                        print("🔍 [COSMOS DEBUG] Thumbnails not found, falling back to click-through navigation...")
                    items = await self._extract_gallery_elements(page, max_elements=kwargs.get('max_files', 100))
                    media_items.extend(items)
                    self.debug_stats['images_extracted'] += len(items)
                
            else:
                if self.debug_mode:
                    print("🔍 [COSMOS DEBUG] Using generic extraction fallback...")
                # Fall back to generic extraction for other page types
                items = await self._extract_generic_cosmos_images(page)
                media_items.extend(items)
                self.debug_stats['images_extracted'] += len(items)
            
            # Add any direct high-res images from the page that we might have missed
            if self.debug_mode:
                print("🔍 [COSMOS DEBUG] Extracting direct CDN images...")
            direct_images = await self._extract_direct_cdn_images(page)
            media_items.extend(direct_images)
            
            # Remove duplicates based on URL
            seen_urls = set()
            unique_items = []
            
            for item in media_items:
                url = item.get('url')
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    unique_items.append(item)
            
            # Final debug summary
            if self.debug_mode:
                print("📊 [COSMOS DEBUG] Extraction Summary:")
                print(f"    - Total items found: {len(media_items)}")
                print(f"    - Unique items: {len(unique_items)}")
                print(f"    - Duplicates removed: {len(media_items) - len(unique_items)}")
                print(f"    - Debug stats: {self.debug_stats}")
            
            print(f"✅ [COSMOS] Extracted {len(unique_items)} unique media items from Cosmos")
            return unique_items
            
        except Exception as e:
            self.debug_stats['errors_encountered'] += 1
            print(f"❌ [COSMOS ERROR] Error during Playwright extraction: {e}")
            if self.debug_mode:
                traceback.print_exc()
            return []

    async def _extract_single_element_images(self, page: AsyncPage) -> list:
        """Extract high-res images from a single element or element group page"""
        media_items = []
        
        if self.debug_mode:
            print(f"🔍 [COSMOS DEBUG] Extracting single element images from: {page.url}")
        
        try:
            # Look for main image element - try multiple selectors for different layouts
            image_selectors = [
                'img[data-testid="ElementImage_Image"]',
                'img.css-1y1og61',
                'img[src*="cdn.cosmos.so"]',  # Direct CDN images
                'img[src*="cosmos"]',
                'img[src*="cdn"]',
                '.element-image img',
                'main img',
                'article img',
                'div[data-element-id] img',  # Images within element containers
                '[class*="carousel"] img',   # Carousel images
                '[class*="gallery"] img',   # Gallery images
                'div[style*="background-image"] img'  # Background images
            ]
            
            found_images = False
            total_images_found = 0
            processed_urls = set()
            
            for selector in image_selectors:
                try:
                    count = await page.locator(selector).count()
                    total_images_found += count
                    if self.debug_mode:
                        print(f"🔍 [COSMOS DEBUG] Selector '{selector}': {count} images")
                    
                    if count > 0:
                        found_images = True
                        
                        if self.debug_mode:
                            print(f"✅ [COSMOS DEBUG] Processing images with selector: {selector}")
                        
                        for i in range(count):
                            img = page.locator(selector).nth(i)
                            
                            # Get image attributes
                            try:
                                src = await img.get_attribute('src')
                                if self.debug_mode:
                                    print(f"🔍 [COSMOS DEBUG] Image {i+1} src: {src}")
                                
                                if not src or src.startswith('data:'):
                                    if self.debug_mode:
                                        print(f"⚠️ [COSMOS DEBUG] Skipping image {i+1} (no src or data URL)")
                                    continue
                                
                                # Skip if we've already processed this URL
                                if src in processed_urls:
                                    if self.debug_mode:
                                        print(f"⚠️ [COSMOS DEBUG] Skipping duplicate image: {src}")
                                    continue
                                processed_urls.add(src)
                                
                                # Only process Cosmos CDN images, skip avatars and other small images
                                if not ('cdn.cosmos.so' in src or 'cosmos-images' in src):
                                    if self.debug_mode:
                                        print(f"⚠️ [COSMOS DEBUG] Skipping non-CDN image: {src}")
                                    continue
                                
                                # Skip default avatars (they're too small)
                                if 'default-avatars' in src:
                                    if self.debug_mode:
                                        print(f"⚠️ [COSMOS DEBUG] Skipping avatar image: {src}")
                                    continue
                                    
                                # Get image dimensions if available
                                width = await img.get_attribute('width')
                                height = await img.get_attribute('height')
                                
                                # Try to get natural dimensions
                                try:
                                    natural_width = await img.evaluate('img => img.naturalWidth')
                                    natural_height = await img.evaluate('img => img.naturalHeight')
                                    if self.debug_mode:
                                        print(f"🔍 [COSMOS DEBUG] Natural dimensions: {natural_width}x{natural_height}")
                                except:
                                    natural_width = natural_height = None
                                
                                # Get alt text for metadata
                                alt = await img.get_attribute('alt') or ''
                                
                                # Try to get element ID
                                element_id = None
                                try:
                                    # Check URL for element ID
                                    url_path = urlparse(page.url).path
                                    if '/element/' in url_path:
                                        element_id = url_path.split('/element/')[1].split('/')[0]
                                    elif '/element-group/' in url_path:
                                        element_id = url_path.split('/element-group/')[1].split('/')[0]
                                    elif '/e/' in url_path:
                                        element_id = url_path.split('/e/')[1].split('/')[0]
                                except Exception as e:
                                    if self.debug_mode:
                                        print(f"⚠️ [COSMOS DEBUG] Error extracting element ID: {e}")
                                
                                # Convert to high-resolution URL
                                high_res_url = self._get_highest_res_cosmos_url(src)
                                
                                # Create media item
                                media_item = {
                                    'url': high_res_url,
                                    'title': alt or f'Cosmos Element {element_id or "Unknown"}',
                                    'width': natural_width or (int(width) if width and width.isdigit() else None),
                                    'height': natural_height or (int(height) if height and height.isdigit() else None),
                                    'source': 'cosmos.so',
                                    'page_url': page.url,
                                    'element_id': element_id,
                                    'alt_text': alt,
                                    'original_src': src,
                                    'extraction_method': 'single_element'
                                }
                                
                                media_items.append(media_item)
                                
                                if self.debug_mode:
                                    print(f"✅ [COSMOS DEBUG] Added image: {high_res_url}")
                                    print(f"    - Original: {src}")
                                    print(f"    - Dimensions: {media_item.get('width')}x{media_item.get('height')}")
                                    print(f"    - Element ID: {element_id}")
                                    
                            except Exception as e:
                                if self.debug_mode:
                                    print(f"❌ [COSMOS DEBUG] Error processing image {i+1}: {e}")
                                continue
                        
                        # Don't break - continue with other selectors to get all images
                        
                except Exception as e:
                    if self.debug_mode:
                        print(f"⚠️ [COSMOS DEBUG] Error with selector '{selector}': {e}")
                    continue
            
            if not found_images:
                if self.debug_mode:
                    print(f"❌ [COSMOS DEBUG] No images found with any selector")
            
            # Try to extract any additional images from related content or connections
            if len(media_items) < 10:  # If we didn't find many images, look for connections
                if self.debug_mode:
                    print("🔍 [COSMOS DEBUG] Few images found, checking for connections/related content...")
                
                try:
                    # Look for connection links that might lead to galleries
                    connection_links = page.locator('a[href*="/"]')
                    connection_count = await connection_links.count()
                    
                    if self.debug_mode:
                        print(f"🔍 [COSMOS DEBUG] Found {connection_count} potential connection links")
                    
                    # Look for any additional CDN images we might have missed
                    all_images = page.locator('img')
                    all_count = await all_images.count()
                    
                    if self.debug_mode:
                        print(f"🔍 [COSMOS DEBUG] Total images on page: {all_count}")
                        
                    # Check for lazy-loaded images that might not be visible yet
                    for i in range(min(all_count, 100)):  # Limit to avoid too many
                        try:
                            img = all_images.nth(i)
                            src = await img.get_attribute('src')
                            data_src = await img.get_attribute('data-src')
                            
                            # Check both src and data-src for lazy loading
                            image_url = src or data_src
                            
                            if (image_url and 
                                ('cdn.cosmos.so' in image_url or 'cosmos-images' in image_url) and
                                'default-avatars' not in image_url and
                                image_url not in processed_urls):
                                
                                processed_urls.add(image_url)
                                high_res_url = self._get_highest_res_cosmos_url(image_url)
                                
                                media_item = {
                                    'url': high_res_url,
                                    'title': f'Cosmos Additional Image {len(media_items) + 1}',
                                    'source': 'cosmos.so',
                                    'page_url': page.url,
                                    'original_src': image_url,
                                    'extraction_method': 'additional_scan'
                                }
                                
                                media_items.append(media_item)
                                
                                if self.debug_mode:
                                    print(f"✅ [COSMOS DEBUG] Added additional image: {high_res_url}")
                        
                        except Exception as e:
                            continue
                
                except Exception as e:
                    if self.debug_mode:
                        print(f"❌ [COSMOS DEBUG] Error scanning for additional images: {e}")
            
            if self.debug_mode:
                print(f"📊 [COSMOS DEBUG] Single element extraction complete:")
                print(f"    - Total images found: {total_images_found}")
                print(f"    - Media items extracted: {len(media_items)}")
                print(f"    - Unique URLs processed: {len(processed_urls)}")
                
        except Exception as e:
            print(f"❌ [COSMOS ERROR] Error in single element extraction: {e}")
            if self.debug_mode:
                traceback.print_exc()
        
        return media_items

    async def _extract_search_gallery_images(self, page) -> list:
        """Extract images from search gallery pages like '/search/elements/naked%20yoga'"""
        media_items = []
        
        if self.debug_mode:
            print(f"🔍 [COSMOS DEBUG] Extracting search gallery images from: {page.url}")
        
        try:
            # Search galleries typically show element cards/tiles that can be clicked
            card_selectors = [
                'button[data-testid="ElementTileLink__a"]',  # Common element tile
                'button[data-element-id]',                  # Element buttons with IDs
                'a[href*="/e/"]',                          # Links to elements
                'div[data-element-id]',                    # Element containers
                '[class*="ElementTile"]',                  # Element tile components
                '[class*="element-card"]',                 # Element cards
                'button:has(img[src*="cdn.cosmos.so"])'    # Buttons containing cosmos images
            ]
            
            # First, just extract thumbnails without navigation
            for selector in card_selectors:
                try:
                    count = await page.locator(selector).count()
                    if self.debug_mode:
                        print(f"🔍 [COSMOS DEBUG] Found {count} elements with selector: {selector}")
                    
                    if count > 0:
                        for i in range(min(count, 100)):  # Limit to avoid too many
                            try:
                                element = page.locator(selector).nth(i)
                                
                                # Try to find image within the element
                                img = element.locator('img').first
                                img_count = await element.locator('img').count()
                                
                                if img_count > 0:
                                    src = await img.get_attribute('src')
                                    if src and 'cdn.cosmos.so' in src:
                                        high_res_url = self._get_highest_res_cosmos_url(src)
                                        
                                        # Try to get element ID
                                        element_id = await element.get_attribute('data-element-id')
                                        if not element_id:
                                            # Try to extract from href
                                            href = await element.get_attribute('href')
                                            if href and '/e/' in href:
                                                element_id = href.split('/e/')[1].split('/')[0]
                                        
                                        alt = await img.get_attribute('alt') or ''
                                        
                                        media_item = {
                                            'url': high_res_url,
                                            'title': alt or f'Search Result {len(media_items) + 1}',
                                            'source': 'cosmos.so',
                                            'page_url': page.url,
                                            'element_id': element_id,
                                            'alt_text': alt,
                                            'original_src': src,
                                            'extraction_method': 'search_gallery_thumbnail'
                                        }
                                        
                                        media_items.append(media_item)
                                        
                                        if self.debug_mode:
                                            print(f"✅ [COSMOS DEBUG] Added search result: {high_res_url}")
                                
                            except Exception as e:
                                if self.debug_mode:
                                    print(f"⚠️ [COSMOS DEBUG] Error processing search element {i}: {e}")
                                continue
                        
                        break  # Found results with this selector, no need to try others
                        
                except Exception as e:
                    if self.debug_mode:
                        print(f"⚠️ [COSMOS DEBUG] Error with search selector '{selector}': {e}")
                    continue
                    
        except Exception as e:
            if self.debug_mode:
                print(f"❌ [COSMOS DEBUG] Error extracting search gallery: {e}")
                traceback.print_exc()
        
        return media_items

    async def _extract_user_gallery_images(self, page) -> list:
        """Extract images from user gallery pages like '/carororo/collection-name'"""
        media_items = []
        
        if self.debug_mode:
            print(f"🔍 [COSMOS DEBUG] Extracting user gallery images from: {page.url}")
        
        try:
            # User galleries may have different layouts than search
            gallery_selectors = [
                'button[data-testid="ElementTileLink__a"]',
                'div[data-element-id] img',
                'a[href*="/e/"] img',
                '[class*="gallery"] img',
                '[class*="collection"] img',
                'img[src*="cdn.cosmos.so"]'
            ]
            
            processed_urls = set()
            
            for selector in gallery_selectors:
                try:
                    count = await page.locator(selector).count()
                    if self.debug_mode:
                        print(f"🔍 [COSMOS DEBUG] Found {count} items with selector: {selector}")
                    
                    if count > 0:
                        for i in range(min(count, 100)):
                            try:
                                if 'img' in selector:
                                    # Direct image selector
                                    img = page.locator(selector).nth(i)
                                else:
                                    # Container selector, find image inside
                                    container = page.locator(selector).nth(i)
                                    img = container.locator('img').first
                                    img_count = await container.locator('img').count()
                                    if img_count == 0:
                                        continue
                                
                                src = await img.get_attribute('src')
                                if (src and 'cdn.cosmos.so' in src and 
                                    src not in processed_urls and 
                                    'default-avatars' not in src):
                                    
                                    processed_urls.add(src)
                                    high_res_url = self._get_highest_res_cosmos_url(src)
                                    alt = await img.get_attribute('alt') or ''
                                    
                                    media_item = {
                                        'url': high_res_url,
                                        'title': alt or f'User Gallery {len(media_items) + 1}',
                                        'source': 'cosmos.so',
                                        'page_url': page.url,
                                        'alt_text': alt,
                                        'original_src': src,
                                        'extraction_method': 'user_gallery_thumbnail'
                                    }
                                    
                                    media_items.append(media_item)
                                    
                                    if self.debug_mode:
                                        print(f"✅ [COSMOS DEBUG] Added user gallery image: {high_res_url}")
                                
                            except Exception as e:
                                if self.debug_mode:
                                    print(f"⚠️ [COSMOS DEBUG] Error processing gallery item {i}: {e}")
                                continue
                                
                except Exception as e:
                    if self.debug_mode:
                        print(f"⚠️ [COSMOS DEBUG] Error with gallery selector '{selector}': {e}")
                    continue
                    
        except Exception as e:
            if self.debug_mode:
                print(f"❌ [COSMOS DEBUG] Error extracting user gallery: {e}")
                traceback.print_exc()
        
        return media_items

    async def _extract_profile_gallery_images(self, page) -> list:
        """Extract images from profile pages like '/carororo' which show collection buttons"""
        media_items = []
        
        if self.debug_mode:
            print(f"🔍 [COSMOS DEBUG] Extracting profile gallery images from: {page.url}")
        
        try:
            # Profile pages might show collection previews or featured content
            profile_selectors = [
                'button[data-testid*="Collection"]',     # Collection buttons
                'a[href*="/"]',                          # Collection/gallery links
                'img[src*="cdn.cosmos.so"]',            # Direct cosmos images
                '[class*="collection-preview"] img',    # Collection preview images
                '[class*="featured"] img',              # Featured content images
                'div[role="button"] img'                # Clickable image containers
            ]
            
            processed_urls = set()
            
            # First try to get any direct images on the profile
            for selector in profile_selectors:
                try:
                    count = await page.locator(selector).count()
                    if self.debug_mode:
                        print(f"🔍 [COSMOS DEBUG] Found {count} items with selector: {selector}")
                    
                    if count > 0 and 'img' in selector:
                        # Process direct images
                        for i in range(min(count, 50)):
                            try:
                                img = page.locator(selector).nth(i)
                                src = await img.get_attribute('src')
                                
                                if (src and 'cdn.cosmos.so' in src and 
                                    src not in processed_urls and
                                    'default-avatars' not in src):
                                    
                                    processed_urls.add(src)
                                    high_res_url = self._get_highest_res_cosmos_url(src)
                                    alt = await img.get_attribute('alt') or ''
                                    
                                    media_item = {
                                        'url': high_res_url,
                                        'title': alt or f'Profile Image {len(media_items) + 1}',
                                        'source': 'cosmos.so',
                                        'page_url': page.url,
                                        'alt_text': alt,
                                        'original_src': src,
                                        'extraction_method': 'profile_direct'
                                    }
                                    
                                    media_items.append(media_item)
                                    
                                    if self.debug_mode:
                                        print(f"✅ [COSMOS DEBUG] Added profile image: {high_res_url}")
                                
                            except Exception as e:
                                if self.debug_mode:
                                    print(f"⚠️ [COSMOS DEBUG] Error processing profile image {i}: {e}")
                                continue
                                
                except Exception as e:
                    if self.debug_mode:
                        print(f"⚠️ [COSMOS DEBUG] Error with profile selector '{selector}': {e}")
                    continue
            
            # If we found few images, this might be a profile with collections to navigate
            if len(media_items) < 5:
                if self.debug_mode:
                    print("🔍 [COSMOS DEBUG] Few direct images found, this might be a collection hub")
                # Could potentially navigate to collections here in future
                
        except Exception as e:
            if self.debug_mode:
                print(f"❌ [COSMOS DEBUG] Error extracting profile gallery: {e}")
                traceback.print_exc()
        
        return media_items

    async def _extract_gallery_elements(self, page, max_elements=50) -> list:
        """Extract images from a gallery page with multiple elements"""
        start_time = time.time()
        media_items = []
        elements_processed = 0
        
        if self.debug_mode:
            print(f"🔍 [COSMOS DEBUG] Starting gallery extraction, max_elements: {max_elements}")
        
        try:
            # Look for element cards - try multiple selectors
            selectors_to_try = [
                'button[data-testid="ElementTileLink__a"]',
                'button[data-element-id]',
                'a[data-testid="ElementTileLink__a"]',
                'div[data-element-id]',
                '.element-card',
                '.tile-link'
            ]
            
            card_count = 0
            element_card_selector = None
            
            # Find the selector that returns the most results
            for selector in selectors_to_try:
                try:
                    count = await page.locator(selector).count()
                    if self.debug_mode:
                        print(f"🔍 [COSMOS DEBUG] Selector '{selector}': {count} elements")
                    if count > card_count:
                        card_count = count
                        element_card_selector = selector
                except Exception as e:
                    if self.debug_mode:
                        print(f"⚠️ [COSMOS DEBUG] Selector '{selector}' failed: {e}")
            
            if not element_card_selector or card_count == 0:
                if self.debug_mode:
                    print("❌ [COSMOS DEBUG] No element cards found with any selector")
                    # Try to debug what's actually on the page
                    try:
                        all_buttons = await page.locator('button').count()
                        all_divs = await page.locator('div').count()
                        all_links = await page.locator('a').count()
                        print(f"🔍 [COSMOS DEBUG] Page contains: {all_buttons} buttons, {all_divs} divs, {all_links} links")
                        
                        # Get first few button attributes for debugging
                        for i in range(min(5, all_buttons)):
                            try:
                                button = page.locator('button').nth(i)
                                classes = await button.get_attribute('class')
                                testid = await button.get_attribute('data-testid')
                                element_id = await button.get_attribute('data-element-id')
                                print(f"🔍 [COSMOS DEBUG] Button {i}: class='{classes}', testid='{testid}', element-id='{element_id}'")
                            except:
                                pass
                    except Exception as e:
                        print(f"⚠️ [COSMOS DEBUG] Error analyzing page structure: {e}")
                return []
            
            self.debug_stats['cards_found'] = card_count
            print(f"✅ [COSMOS DEBUG] Found {card_count} element cards using selector: {element_card_selector}")
            
            # Process each card (up to max_elements)
            for i in range(min(card_count, max_elements)):
                if elements_processed >= max_elements:
                    if self.debug_mode:
                        print(f"🔍 [COSMOS DEBUG] Reached max_elements limit: {max_elements}")
                    break
                    
                if self.debug_mode:
                    print(f"🔍 [COSMOS DEBUG] Processing card {i+1}/{min(card_count, max_elements)}")
                    
                # Get the current card
                card = page.locator(element_card_selector).nth(i)
                
                # Get element ID (try multiple attributes)
                element_id = None
                for attr in ['data-element-id', 'data-testid', 'id']:
                    try:
                        element_id = await card.get_attribute(attr)
                        if element_id:
                            break
                    except:
                        pass
                
                if not element_id:
                    element_id = f"card_{i}"  # Fallback ID
                    
                if element_id in self.visited_element_ids:
                    if self.debug_mode:
                        print(f"⚠️ [COSMOS DEBUG] Skipping already visited element: {element_id}")
                    continue
                    
                self.visited_element_ids.add(element_id)
                
                # Store current URL to return to
                current_url = page.url
                
                try:
                    if self.debug_mode:
                        print(f"🔍 [COSMOS DEBUG] Clicking on card with element_id: {element_id}")
                    
                    # Try to get card info before clicking
                    try:
                        card_text = await card.text_content()
                        card_href = await card.get_attribute('href')
                        if self.debug_mode:
                            print(f"🔍 [COSMOS DEBUG] Card text: {card_text[:100] if card_text else 'None'}")
                            print(f"🔍 [COSMOS DEBUG] Card href: {card_href}")
                    except:
                        pass
                    
                    # Click on card to open element detail
                    await card.click(timeout=5000)
                    
                    # Wait for new page to load
                    await page.wait_for_load_state("domcontentloaded", timeout=10000)
                    
                    if self.debug_mode:
                        new_url = page.url
                        print(f"🔍 [COSMOS DEBUG] Navigated to: {new_url}")
                    
                    # Wait for image to appear - try multiple selectors
                    image_selectors = [
                        'img[data-testid="ElementImage_Image"]',
                        'img.css-1y1og61',
                        'img[src*="cosmos"]',
                        '.element-image img',
                        'main img'
                    ]
                    
                    image_found = False
                    for img_selector in image_selectors:
                        try:
                            await page.wait_for_selector(img_selector, timeout=5000)
                            image_found = True
                            if self.debug_mode:
                                print(f"✅ [COSMOS DEBUG] Found image with selector: {img_selector}")
                            break
                        except:
                            continue
                    
                    if not image_found:
                        if self.debug_mode:
                            print("⚠️ [COSMOS DEBUG] No images found on element page")
                            # Debug what images are actually there
                            img_count = await page.locator('img').count()
                            print(f"🔍 [COSMOS DEBUG] Total images on page: {img_count}")
                    
                    # Extract image from detail page
                    element_images = await self._extract_single_element_images(page)
                    
                    if element_images:
                        media_items.extend(element_images)
                        elements_processed += 1
                        self.debug_stats['cards_processed'] += 1
                        if self.debug_mode:
                            print(f"✅ [COSMOS DEBUG] Extracted {len(element_images)} images from element {element_id}")
                    else:
                        if self.debug_mode:
                            print(f"⚠️ [COSMOS DEBUG] No images extracted from element {element_id}")
                    
                    # Go back to gallery using ESC key
                    if self.debug_mode:
                        print("🔍 [COSMOS DEBUG] Attempting to return to gallery with ESC")
                    await page.keyboard.press('Escape')
                    await page.wait_for_timeout(1000)
                    
                    # If ESC didn't work, navigate back
                    if page.url != current_url:
                        if self.debug_mode:
                            print("🔍 [COSMOS DEBUG] ESC didn't work, navigating back manually")
                        await page.goto(current_url, timeout=10000)
                        await page.wait_for_load_state("domcontentloaded", timeout=5000)
                    
                except PlaywrightTimeoutError:
                    self.debug_stats['navigation_failures'] += 1
                    print(f"⚠️ [COSMOS WARNING] Timeout navigating to/from element {element_id}")
                    # Try to go back to the main gallery
                    try:
                        await page.goto(current_url, timeout=10000)
                        await page.wait_for_load_state("domcontentloaded", timeout=5000)
                    except:
                        print("❌ [COSMOS ERROR] Failed to return to gallery page, extraction may be incomplete")
                        break
                except Exception as e:
                    self.debug_stats['errors_encountered'] += 1
                    print(f"❌ [COSMOS ERROR] Error processing element card {i}: {e}")
                    if self.debug_mode:
                        traceback.print_exc()
                    # Try to continue with the next card
                    try:
                        await page.goto(current_url, timeout=10000)
                        await page.wait_for_load_state("domcontentloaded", timeout=5000)
                    except:
                        pass
                    
                # Check if we've spent too much time (over 2 minutes)
                if time.time() - start_time > 120:
                    print("⏰ [COSMOS WARNING] Time limit reached for gallery extraction, stopping")
                    break
        
        except Exception as e:
            self.debug_stats['errors_encountered'] += 1
            print(f"❌ [COSMOS ERROR] Error extracting gallery elements: {e}")
            if self.debug_mode:
                traceback.print_exc()
            
        if self.debug_mode:
            print(f"📊 [COSMOS DEBUG] Gallery extraction complete:")
            print(f"    - Cards found: {self.debug_stats['cards_found']}")
            print(f"    - Cards processed: {self.debug_stats['cards_processed']}")
            print(f"    - Media items extracted: {len(media_items)}")
            print(f"    - Time taken: {time.time() - start_time:.2f} seconds")
            
        return media_items

    async def _extract_thumbnail_gallery_images(self, page: AsyncPage) -> list:
        """Extract images from thumbnail gallery without navigation - faster approach"""
        media_items = []
        
        if self.debug_mode:
            print("🔍 [COSMOS DEBUG] Starting thumbnail gallery extraction...")
        
        try:
            # Look for thumbnail images in the gallery containers
            # These are the actual images displayed in the grid, not just buttons
            thumbnail_selectors = [
                'img[src*="cdn.cosmos.so"]',  # Direct CDN images
                'div[data-element-id] img',  # Images within element containers
                'button[data-element-id] img',  # Images within buttons
                'div[class*="tile"] img',  # Images in tile containers
                '.gallery img',  # Images in gallery containers
                '.grid img',  # Images in grid containers
                'div[class*="element"] img'  # Images in element containers
            ]
            
            found_thumbnails = 0
            processed_urls = set()
            
            for selector in thumbnail_selectors:
                try:
                    images = page.locator(selector)
                    count = await images.count()
                    
                    if self.debug_mode:
                        print(f"🔍 [COSMOS DEBUG] Selector '{selector}': {count} images")
                    
                    if count > 0:
                        found_thumbnails += count
                        
                        for i in range(count):
                            try:
                                img = images.nth(i)
                                
                                # Get image source
                                src = await img.get_attribute('src')
                                if not src or src.startswith('data:'):
                                    continue
                                
                                # Skip if we've already processed this URL
                                if src in processed_urls:
                                    continue
                                processed_urls.add(src)
                                
                                # Only process Cosmos CDN images
                                if not ('cdn.cosmos.so' in src or 'cosmos-images' in src):
                                    continue
                                
                                if self.debug_mode:
                                    print(f"🔍 [COSMOS DEBUG] Processing thumbnail {i+1}: {src}")
                                
                                # Get image dimensions if available
                                try:
                                    width = await img.get_attribute('width')
                                    height = await img.get_attribute('height')
                                    
                                    # Try to get natural dimensions
                                    natural_width = await img.evaluate('img => img.naturalWidth')
                                    natural_height = await img.evaluate('img => img.naturalHeight')
                                    
                                    if self.debug_mode:
                                        print(f"    - Dimensions: {natural_width}x{natural_height} (natural), {width}x{height} (attr)")
                                    
                                except Exception as e:
                                    natural_width = natural_height = None
                                    if self.debug_mode:
                                        print(f"    - Could not get dimensions: {e}")
                                
                                # Get alt text for metadata
                                alt = await img.get_attribute('alt') or ''
                                
                                # Try to get element ID from parent containers
                                element_id = None
                                try:
                                    # Check parent elements for data-element-id
                                    parent_locator = img.locator('xpath=..')
                                    while parent_locator and not element_id:
                                        try:
                                            element_id = await parent_locator.get_attribute('data-element-id')
                                            if element_id:
                                                break
                                            # Move to next parent
                                            parent_locator = parent_locator.locator('xpath=..')
                                        except:
                                            break
                                except:
                                    pass
                                
                                # Convert thumbnail URL to high-resolution version
                                high_res_url = self._get_highest_res_cosmos_url(src)
                                
                                # Try to get even higher resolution by removing format parameters
                                if '?format=' in high_res_url:
                                    base_url = high_res_url.split('?')[0]
                                    # Try different format parameters for highest quality
                                    high_res_url = f"{base_url}?format=jpeg&quality=100"
                                
                                if self.debug_mode:
                                    print(f"    - Original: {src}")
                                    print(f"    - High-res: {high_res_url}")
                                    print(f"    - Element ID: {element_id}")
                                
                                # Create media item
                                media_item = {
                                    'url': high_res_url,
                                    'title': alt or f'Cosmos Image {element_id or len(media_items) + 1}',
                                    'width': natural_width or (int(width) if width and width.isdigit() else None),
                                    'height': natural_height or (int(height) if height and height.isdigit() else None),
                                    'source': 'cosmos.so',
                                    'page_url': page.url,
                                    'element_id': element_id,
                                    'alt_text': alt,
                                    'original_thumbnail_url': src,
                                    'extraction_method': 'thumbnail_gallery'
                                }
                                
                                media_items.append(media_item)
                                
                                if self.debug_mode:
                                    print(f"✅ [COSMOS DEBUG] Added thumbnail image #{len(media_items)}")
                                    
                            except Exception as e:
                                if self.debug_mode:
                                    print(f"❌ [COSMOS DEBUG] Error processing thumbnail {i+1}: {e}")
                                continue
                        
                        # If we found a good number of images with this selector, we can stop
                        if len(media_items) >= 20:
                            if self.debug_mode:
                                print(f"✅ [COSMOS DEBUG] Found sufficient images ({len(media_items)}) with selector: {selector}")
                            break
                            
                except Exception as e:
                    if self.debug_mode:
                        print(f"⚠️ [COSMOS DEBUG] Error with thumbnail selector '{selector}': {e}")
                    continue
            
            # If we didn't find many thumbnails, try looking for background images in CSS
            if len(media_items) < 10:
                if self.debug_mode:
                    print("🔍 [COSMOS DEBUG] Few thumbnails found, checking for CSS background images...")
                
                try:
                    # Look for elements with background images
                    bg_elements = page.locator('div[style*="background-image"], div[data-element-id]')
                    bg_count = await bg_elements.count()
                    
                    if self.debug_mode:
                        print(f"🔍 [COSMOS DEBUG] Found {bg_count} potential background image elements")
                    
                    for i in range(min(bg_count, 50)):  # Limit to avoid too many
                        try:
                            element = bg_elements.nth(i)
                            
                            # Get element ID
                            element_id = await element.get_attribute('data-element-id')
                            
                            # Get computed style for background image
                            bg_style = await element.evaluate('''
                                element => {
                                    const style = window.getComputedStyle(element);
                                    const bgImage = style.backgroundImage;
                                    return bgImage && bgImage !== 'none' ? bgImage : null;
                                }
                            ''')
                            
                            if bg_style and 'url(' in bg_style:
                                # Extract URL from CSS url() function
                                import re
                                url_match = re.search(r'url\(["\']?([^"\']+)["\']?\)', bg_style)
                                if url_match:
                                    bg_url = url_match.group(1)
                                    
                                    if 'cdn.cosmos.so' in bg_url and bg_url not in processed_urls:
                                        processed_urls.add(bg_url)
                                        high_res_url = self._get_highest_res_cosmos_url(bg_url)
                                        
                                        media_item = {
                                            'url': high_res_url,
                                            'title': f'Cosmos Background Image {element_id or len(media_items) + 1}',
                                            'source': 'cosmos.so',
                                            'page_url': page.url,
                                            'element_id': element_id,
                                            'original_thumbnail_url': bg_url,
                                            'extraction_method': 'background_image'
                                        }
                                        
                                        media_items.append(media_item)
                                        
                                        if self.debug_mode:
                                            print(f"✅ [COSMOS DEBUG] Added background image: {high_res_url}")
                            
                        except Exception as e:
                            if self.debug_mode:
                                print(f"⚠️ [COSMOS DEBUG] Error processing background element {i+1}: {e}")
                            continue
                
                except Exception as e:
                    if self.debug_mode:
                        print(f"❌ [COSMOS DEBUG] Error extracting background images: {e}")
            
            if self.debug_mode:
                print(f"📊 [COSMOS DEBUG] Thumbnail extraction complete:")
                print(f"    - Total thumbnails found: {found_thumbnails}")
                print(f"    - Media items extracted: {len(media_items)}")
                print(f"    - Unique URLs processed: {len(processed_urls)}")
                
        except Exception as e:
            print(f"❌ [COSMOS ERROR] Error in thumbnail gallery extraction: {e}")
            if self.debug_mode:
                traceback.print_exc()
        
        return media_items

    async def _extract_direct_cdn_images(self, page: AsyncPage) -> list:
        """Extract direct CDN images from the page"""
        media_items = []
        
        if self.debug_mode:
            print("🔍 [COSMOS DEBUG] Extracting direct CDN images...")
        
        try:
            # Look for all images from Cosmos CDN
            cdn_selectors = [
                'img[src*="cdn.cosmos.so"]',
                'img[src*="cosmos-images.s3.amazonaws.com"]',
                'img[src*="cosmos.so"]'
            ]
            
            total_found = 0
            seen_urls = set()
            
            for selector in cdn_selectors:
                try:
                    cdn_images = page.locator(selector)
                    count = await cdn_images.count()
                    total_found += count
                    
                    if self.debug_mode:
                        print(f"🔍 [COSMOS DEBUG] Found {count} images with selector: {selector}")
                    
                    for i in range(count):
                        img = cdn_images.nth(i)
                        
                        src = await img.get_attribute('src')
                        if not src or src.startswith('data:') or src in seen_urls:
                            continue
                            
                        seen_urls.add(src)
                        
                        if self.debug_mode:
                            print(f"🔍 [COSMOS DEBUG] Processing CDN image: {src}")
                        
                        # Check if this is likely a small thumbnail or icon
                        width = await img.get_attribute('width')
                        height = await img.get_attribute('height')
                        
                        # Try to get natural dimensions
                        try:
                            natural_width = await img.evaluate('img => img.naturalWidth')
                            natural_height = await img.evaluate('img => img.naturalHeight')
                        except:
                            natural_width = natural_height = None
                        
                        # Skip very small images (likely thumbnails)
                        if natural_width and natural_height:
                            if natural_width < 100 or natural_height < 100:
                                if self.debug_mode:
                                    print(f"⚠️ [COSMOS DEBUG] Skipping small image: {natural_width}x{natural_height}")
                                continue
                        
                        # Get alt text for metadata
                        alt = await img.get_attribute('alt') or ''
                        
                        # Try to get highest resolution version
                        high_res_url = self._get_highest_res_cosmos_url(src)
                        
                        media_item = {
                            'url': high_res_url,
                            'title': alt or 'Cosmos CDN Image',
                            'width': natural_width or width,
                            'height': natural_height or height,
                            'source': 'cosmos.so',
                            'page_url': page.url,
                            'alt_text': alt,
                            'original_url': src
                        }
                        
                        media_items.append(media_item)
                        
                        if self.debug_mode:
                            print(f"✅ [COSMOS DEBUG] Added CDN image: {high_res_url}")
                            print(f"    - Original: {src}")
                            print(f"    - Dimensions: {media_item.get('width')}x{media_item.get('height')}")
                            
                except Exception as e:
                    if self.debug_mode:
                        print(f"⚠️ [COSMOS DEBUG] Error with CDN selector '{selector}': {e}")
            
            if self.debug_mode:
                print(f"📊 [COSMOS DEBUG] CDN extraction complete: {len(media_items)} images from {total_found} total found")
                
        except Exception as e:
            print(f"❌ [COSMOS ERROR] Error extracting direct CDN images: {e}")
            if self.debug_mode:
                traceback.print_exc()
            
        return media_items

    async def _extract_generic_cosmos_images(self, page: AsyncPage) -> list:
        """Generic fallback extraction for any Cosmos page"""
        media_items = []
        
        try:
            # Look for all images from Cosmos CDN
            images = page.locator('img')
            count = await images.count()
            
            seen_urls = set()
            
            for i in range(count):
                img = images.nth(i)
                
                src = await img.get_attribute('src')
                if not src or src.startswith('data:') or src in seen_urls:
                    continue
                    
                # Only keep Cosmos domain images
                if not ('cosmos.so' in src or 'cosmos-images' in src):
                    continue
                    
                seen_urls.add(src)
                
                # Skip likely UI elements
                width = await img.get_attribute('width')
                height = await img.get_attribute('height')
                
                if width and height and (int(width) < 100 or int(height) < 100):
                    continue
                
                # Use original URL when possible
                image_url = self._get_highest_res_cosmos_url(src)
                
                # Get alt text for metadata
                alt = await img.get_attribute('alt') or 'Cosmos Image'
                
                media_items.append({
                    'url': image_url,
                    'alt': alt,
                    'title': alt[:50] + ('...' if len(alt) > 50 else ''),
                    'source_url': page.url,
                    'credits': "Cosmos",
                    'type': 'image',
                    'width': int(width) if width and width.isdigit() else 0,
                    'height': int(height) if height and height.isdigit() else 0
                })
        
        except Exception as e:
            print(f"Error in generic extraction: {e}")
            
        return media_items

    async def _auto_scroll_cosmos_page(self, page: AsyncPage, max_scrolls=50, delay_ms=1200):
        """Scroll down the page to load more content - enhanced for Cosmos galleries"""
        try:
            if self.debug_mode:
                print(f"🔍 [COSMOS DEBUG] Starting enhanced auto-scroll (max: {max_scrolls}, delay: {delay_ms}ms)")
            
            scroll_count = 0
            last_height = await page.evaluate('document.body.scrollHeight')
            no_change_count = 0  # Track consecutive scrolls with no change
            
            if self.debug_mode:
                print(f"🔍 [COSMOS DEBUG] Initial page height: {last_height}")
            
            while scroll_count < max_scrolls:
                # Scroll down in increments for better loading
                await page.evaluate('window.scrollBy(0, window.innerHeight * 0.8)')
                await page.wait_for_timeout(delay_ms // 2)
                
                # Scroll to bottom
                await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                await page.wait_for_timeout(delay_ms)
                
                # Get new scroll height
                new_height = await page.evaluate('document.body.scrollHeight')
                
                if self.debug_mode:
                    print(f"🔍 [COSMOS DEBUG] Scroll {scroll_count + 1}: height {last_height} → {new_height}")
                
                # If no change in height, increment no-change counter
                if new_height == last_height:
                    no_change_count += 1
                    if self.debug_mode:
                        print(f"🔍 [COSMOS DEBUG] No height change (count: {no_change_count})")
                    
                    # Try to trigger loading by scrolling up slightly then back down
                    await page.evaluate('window.scrollBy(0, -100)')
                    await page.wait_for_timeout(500)
                    await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                    await page.wait_for_timeout(delay_ms)
                    
                    # Check for "Load More" or "Show More" buttons more frequently
                    try:
                        load_more_selectors = [
                            'button:has-text("Load More")',
                            'button:has-text("Show More")',
                            'button:has-text("Load more")',
                            'button:has-text("See more")',
                            'a:has-text("Load More")',
                            'a:has-text("Show More")',
                            '[data-testid*="load"], [data-testid*="more"]',
                            'button[class*="load"], button[class*="more"]'
                        ]
                        
                        for selector in load_more_selectors:
                            try:
                                load_more = page.locator(selector)
                                is_visible = await load_more.is_visible(timeout=1000)
                                if is_visible:
                                    if self.debug_mode:
                                        print(f"🔍 [COSMOS DEBUG] Found and clicking load more button: {selector}")
                                    await load_more.click()
                                    await page.wait_for_timeout(2000)
                                    no_change_count = 0  # Reset counter after successful click
                                    break
                            except:
                                continue
                    except Exception as e:
                        if self.debug_mode:
                            print(f"⚠️ [COSMOS DEBUG] Error checking load more buttons: {e}")
                    
                    # If we've had no changes for multiple scrolls, we might be done
                    if no_change_count >= 5:
                        if self.debug_mode:
                            print(f"✅ [COSMOS DEBUG] No content changes for {no_change_count} scrolls, assuming end reached")
                        break
                else:
                    no_change_count = 0  # Reset counter when height changes
                    
                last_height = new_height
                scroll_count += 1
                
                # Check element count every few scrolls for progress indication
                if scroll_count % 5 == 0:
                    try:
                        element_count = await page.locator('button[data-element-id], div[data-element-id]').count()
                        image_count = await page.locator('img[src*="cdn.cosmos.so"]').count()
                        if self.debug_mode:
                            print(f"🔍 [COSMOS DEBUG] Progress check - Elements: {element_count}, Images: {image_count}")
                    except:
                        pass
            
            # Final check for infinite scroll or lazy loading
            if scroll_count >= max_scrolls:
                if self.debug_mode:
                    print(f"⏰ [COSMOS DEBUG] Reached max scrolls ({max_scrolls}), checking for remaining content...")
                
                # Try one more aggressive scroll to the very bottom
                try:
                    await page.evaluate('''
                        window.scrollTo(0, document.documentElement.scrollHeight);
                        // Also try scrolling any scrollable containers
                        document.querySelectorAll('div').forEach(div => {
                            if (div.scrollHeight > div.clientHeight) {
                                div.scrollTop = div.scrollHeight;
                            }
                        });
                    ''')
                    await page.wait_for_timeout(3000)
                except Exception as e:
                    if self.debug_mode:
                        print(f"⚠️ [COSMOS DEBUG] Error in final scroll attempt: {e}")
            
            # Final element count
            try:
                final_element_count = await page.locator('button[data-element-id], div[data-element-id]').count()
                final_image_count = await page.locator('img[src*="cdn.cosmos.so"]').count()
                if self.debug_mode:
                    print(f"📊 [COSMOS DEBUG] Final counts - Elements: {final_element_count}, Images: {final_image_count}")
            except:
                pass
            
            print(f"Completed {scroll_count} scrolls")
        
        except Exception as e:
            print(f"Error during auto-scroll: {e}")
            if self.debug_mode:
                traceback.print_exc()

    def _get_highest_res_cosmos_url(self, url):
        """Modify URL to get highest resolution version - enhanced for Cosmos CDN"""
        if not url:
            return url
            
        # Keep original URL for comparison
        original_url = url
        
        try:
            # Remove existing format parameters to get original image
            if "?format=" in url:
                url = url.split("?format=")[0]
            
            # Remove other common parameters that might limit quality
            params_to_remove = ['w=', 'width=', 'h=', 'height=', 'q=', 'quality=', 'fit=', 'crop=']
            for param in params_to_remove:
                url = re.sub(f'[?&]{param}\\d+', '', url)
            
            # Remove any remaining query parameters except essential ones
            if '?' in url:
                base_url, query = url.split('?', 1)
                # Keep only essential parameters if any
                essential_params = []
                if 'token=' in query:
                    # Keep authentication tokens
                    token_match = re.search(r'token=[^&]+', query)
                    if token_match:
                        essential_params.append(token_match.group(0))
                
                if essential_params:
                    url = f"{base_url}?{'&'.join(essential_params)}"
                else:
                    url = base_url
            
            # Look for common size indicators in path and replace with high-res versions
            size_patterns = [
                (r'/\d+x\d+/', '/original/'),
                (r'/thumb/', '/original/'),
                (r'/thumbnail/', '/original/'),
                (r'/small/', '/large/'),
                (r'/medium/', '/large/'),
                (r'_thumb\b', '_large'),
                (r'_small\b', '_large'),
                (r'_medium\b', '_large'),
                (r'_\d+x\d+\b', '_original')
            ]
            
            for pattern, replacement in size_patterns:
                if re.search(pattern, url):
                    url = re.sub(pattern, replacement, url)
                    if self.debug_mode:
                        print(f"🔍 [COSMOS DEBUG] Applied size pattern {pattern} → {replacement}")
                    break
            
            # For Cosmos CDN specifically, we can try appending high-quality parameters
            if 'cdn.cosmos.so' in url and '?' not in url:
                # Add high-quality JPEG parameters
                url += '?format=jpeg&quality=95'
            
            if self.debug_mode and url != original_url:
                print(f"🔍 [COSMOS DEBUG] URL enhancement:")
                print(f"    Original: {original_url}")
                print(f"    Enhanced: {url}")
            
            return url
            
        except Exception as e:
            if self.debug_mode:
                print(f"⚠️ [COSMOS DEBUG] Error enhancing URL {original_url}: {e}")
            return original_url

    async def extract_with_scrapling(self, response, **kwargs) -> list:
        """Extract media using Scrapling response (HTML fallback)."""
        print("CosmosHandler: Attempting extraction via Scrapling (HTML Fallback)...")
        
        if hasattr(self.scraper, '_get_page_content_from_response'):
            html_content = self.scraper._get_page_content_from_response(response)
        else:
            html_content = getattr(response, 'text', None) or getattr(response, 'content', b'').decode('utf-8', errors='ignore')
            
        if not html_content:
            print("CosmosHandler: No HTML content found in Scrapling response.")
            return []
            
        media_items = []
        
        # Extract image URLs using regex patterns
        cdn_pattern = r'https://cdn\.cosmos\.so/[^"\'\s\)>]+'
        
        for match in re.finditer(cdn_pattern, html_content):
            url = match.group(0)
            
            # Clean up URL
            url = url.split('"')[0].split("'")[0].split('?')[0].split('#')[0]
            
            # Skip if not an image URL
            if not url.endswith(('.jpg', '.jpeg', '.png', '.webp', '.gif')) and "?format=" not in url:
                # Try to detect if it's an image URL without extension
                if not re.search(r'[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}', url):
                    continue
            
            # Use highest res version
            image_url = self._get_highest_res_cosmos_url(url)
            
            # Create media item
            media_items.append({
                'url': image_url,
                'alt': "Image from Cosmos",
                'title': "Cosmos Image",
                'source_url': self.url,
                'credits': "Cosmos",
                'type': 'image'
            })
        
        print(f"CosmosHandler: Scrapling extraction found {len(media_items)} items.")
        return await self.post_process(media_items)

    async def post_process(self, media_items):
        """Clean and enhance the extracted media items."""
        processed_items = []
        seen_urls = set()
        
        for item in media_items:
            url = item.get('url')
            if not url:
                continue
                
            # Clean up URL
            clean_url = url.split('?')[0].split('#')[0].strip()
            if not clean_url or clean_url in seen_urls:
                continue
                
            # Upgrade to high-res version
            upgraded_url = self._get_highest_res_cosmos_url(clean_url)
            if upgraded_url in seen_urls:
                continue
                
            # Update the item with cleaned URL
            item['url'] = upgraded_url
            seen_urls.add(upgraded_url)
            
            # Add CDN indicator
            item['trusted_cdn'] = True
            
            # Process credits
            credits = item.get('credits', '').strip()
            if credits and 'cosmos' not in credits.lower():
                item['credits'] = f"{credits} on Cosmos"
            elif not credits:
                item['credits'] = "Cosmos"
                
            processed_items.append(item)
            
        if self.debug_mode:
            print(f"Post-processing finished. Kept {len(processed_items)} unique items.")
            
        return processed_items