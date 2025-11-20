"""
Flickr Handler

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

# flickr_handler.py

"""
Flickr specific handler for the Web Image Scraper
"""

from site_handlers.base_handler import BaseSiteHandler
from urllib.parse import urlparse, urljoin
import re
import time
import traceback
import os

# Safe import for flickr_api
try:
    import flickr_api
    from flickr_api.api import flickr
    FLICKR_API_AVAILABLE = True
except ImportError:
    flickr_api = None
    flickr = None
    FLICKR_API_AVAILABLE = False
    print("Warning: flickr_api library not found. Flickr handler will be limited.")

# Safe import for Playwright types
try:
    from playwright.async_api import Page as AsyncPage
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    AsyncPage = None
    PLAYWRIGHT_AVAILABLE = False


class FlickrHandler(BaseSiteHandler):
    """
    Handler for Flickr.com.
    Uses the flickr_api library if available and configured.
    Falls back to generic scraping otherwise.
    """
    # Regex to identify Flickr photo, album, or user URLs
    FLICKR_URL_PATTERN = re.compile(
        r"https?://(?:www\.)?flickr\.com/(?:photos/([^/]+)(?:/(\d+))?|people/([^/]+)|albums/(\d+)|groups/([^/]+))"
    )

    def __init__(self, url, scraper=None):
        super().__init__(url, scraper)
        self.api_key = None
        self.api_secret = None
        self.api_available = FLICKR_API_AVAILABLE # API library installed
        self.api_configured = False # API keys loaded
        self.user_id = None
        self.photo_id = None
        self.album_id = None
        self.group_id = None
        self.username = None # Flickr username from URL

        self.debug_mode = getattr(scraper, 'debug_mode', False)
        self.max_pages = 5 # Flickr API pages
        self.max_execution_time = 120.0
        self.start_time = time.time()

        self._parse_flickr_url()
        self._load_api_credentials()
        print(f"FlickrHandler initialized for URL: {url}. API Available: {self.api_available}, Configured: {self.api_configured}")

@staticmethod
def can_handle(url):
    """Check if this handler can process the URL"""
    return "flickr.com" in url.lower() or "staticflickr.com" in url.lower()

    def _parse_flickr_url(self):
        match = self.FLICKR_URL_PATTERN.match(self.url)
        if match:
            self.username = match.group(1) or match.group(3)
            self.photo_id = match.group(2)
            self.album_id = match.group(4)
            self.group_id = match.group(5)
            print(f"Parsed Flickr URL: User={self.username}, Photo={self.photo_id}, Album={self.album_id}, Group={self.group_id}")

    def _load_api_credentials(self):
        """Load Flickr API credentials from the scraper's auth config."""
        if not self.api_available: return

        auth_config = getattr(self.scraper, 'auth_config', None)
        site_auth_config = {}
        if auth_config and hasattr(self.scraper, 'get_site_auth_config'):
            site_auth_config = self.scraper.get_site_auth_config('flickr.com', auth_config) or {}

        self.api_key = site_auth_config.get('api_key')
        self.api_secret = site_auth_config.get('api_secret')

        if self.api_key and self.api_secret:
            try:
                flickr_api.set_keys(api_key=self.api_key, api_secret=self.api_secret)
                self.api_configured = True
                print("Flickr API keys loaded and set.")
            except Exception as e:
                print(f"Error setting Flickr API keys: {e}")
                self.api_configured = False
        else:
            print("Flickr API key or secret missing in auth config.")
            self.api_configured = False

    def prefers_api(self) -> bool:
        """Flickr handler prefers API if available and configured."""
        print(f"FlickrHandler prefers_api check. Available: {self.api_available}, Configured: {self.api_configured}")
        return self.api_available and self.api_configured

    def extract_api_data(self, **kwargs) -> list:
        """Extract media using the Flickr API."""
        print("FlickrHandler: Attempting API data extraction...")
        if not self.prefers_api():
            print("Flickr API not available or not configured.")
            return []

        self.start_time = time.time()
        self.max_pages = kwargs.get('max_api_pages', self.max_pages)
        self.max_execution_time = kwargs.get('timeout', self.max_execution_time)

        media_items = []
        try:
            # Resolve username to user_id if necessary
            if self.username and not self.user_id:
                try:
                    user = flickr_api.Person.findByUserName(self.username)
                    self.user_id = user.id
                    print(f"Resolved Flickr username '{self.username}' to user ID '{self.user_id}'")
                except Exception as e:
                    print(f"Could not find Flickr user ID for username '{self.username}': {e}")
                    return [] # Cannot proceed without user ID for user/album fetches

            if self.photo_id:
                print(f"Fetching single Flickr photo: {self.photo_id}")
                photo = flickr_api.Photo(id=self.photo_id)
                media_items.append(self._process_flickr_photo(photo))
            elif self.album_id:
                print(f"Fetching Flickr album/photoset: {self.album_id}")
                photoset = flickr_api.Photoset(id=self.album_id)
                photos = photoset.getPhotos(page=1, per_page=500) # Get first page
                for photo in photos:
                     if time.time() - self.start_time > self.max_execution_time: break
                     media_items.append(self._process_flickr_photo(photo))
            elif self.group_id:
                 print(f"Fetching Flickr group pool: {self.group_id}")
                 print("Flickr group fetching via API not fully implemented.")
                 pass
            elif self.user_id:
                print(f"Fetching Flickr user photostream: {self.user_id} (Username: {self.username})")
                user = flickr_api.Person(id=self.user_id)
                page_num = 1
                while page_num <= self.max_pages:
                    if time.time() - self.start_time > self.max_execution_time:
                         print("Flickr API extraction timeout reached.")
                         break
                    print(f"Fetching user photos page {page_num}...")
                    try:
                        photos = user.getPhotos(page=page_num, per_page=100) # Fetch 100 per page
                        if not photos:
                            print("No more photos found for user.")
                            break
                        for photo in photos:
                             media_items.append(self._process_flickr_photo(photo))
                        page_num += 1
                        time.sleep(0.5) # Small delay
                    except Exception as page_error:
                         print(f"Error fetching user photos page {page_num}: {page_error}")
                         break # Stop if a page fails
            else:
                print("Could not determine Flickr content type from URL for API call.")

        except Exception as e:
            print(f"Error during Flickr API extraction: {e}")
            traceback.print_exc()

        # Filter out None results from processing errors
        media_items = [item for item in media_items if item]
        print(f"Flickr API extraction found {len(media_items)} items.")
        return media_items

    def _process_flickr_photo(self, photo_obj) -> dict | None:
        """Extracts details from a Flickr Photo object."""
        try:
            photo_obj.load() # Ensure photo details are loaded
            # Try to get original size, fall back through sizes
            photo_url = photo_obj.getPhotoFileUrl(size_label='Original')
            if not photo_url: photo_url = photo_obj.getPhotoFileUrl(size_label='Large 2048')
            if not photo_url: photo_url = photo_obj.getPhotoFileUrl(size_label='Large 1600')
            if not photo_url: photo_url = photo_obj.getPhotoFileUrl(size_label='Large')
            if not photo_url: photo_url = photo_obj.getPhotoFileUrl() # Default (Medium)

            if not photo_url: return None # Skip if no URL found

            title = photo_obj.title or ""
            description = photo_obj.description or ""
            owner_name = photo_obj.owner.username if photo_obj.owner else "unknown"

            return {
                'url': photo_url,
                'alt': title or description, # Use title or description as alt
                'title': title,
                'source_url': photo_obj.getPageUrl(),
                'credits': owner_name,
                'type': 'image' # Assume image for now
            }
        except Exception as e:
            print(f"Error processing Flickr photo ID {getattr(photo_obj, 'id', 'N/A')}: {e}")
            return None

    # --- Implement extract_with_direct_playwright_async ---
    async def extract_with_direct_playwright_async(self, page: AsyncPage, **kwargs) -> list:
        """Fallback to generic Playwright extraction if API fails or isn't used (async version)."""
        print("FlickrHandler: Direct Playwright extraction")
        media_items = []
        
        try:
            # First try to extract from the photo page if we're on a single photo
            if "/photos/" in self.url and self.page_type == "photo":
                single_photo_items = await self._extract_single_photo_async(page)
                if single_photo_items:
                    return single_photo_items
            
            # Then try to extract from the search or photostream pages
            # Find all photo elements
            photo_elements = page.locator('.photo-list-photo-view, .search-photos-photo, .photo-container, .flickr-embed-frame img')
            count = await photo_elements.count()
            print(f"Found {count} potential photo elements")
            
            for i in range(count):
                try:
                    photo = photo_elements.nth(i)
                    
                    # Get image source
                    src = await photo.get_attribute('src') or await photo.get_attribute('data-src')
                    if not src:
                        # Try to get background image
                        style = await photo.get_attribute('style')
                        if style and 'background-image' in style:
                            bg_match = re.search(r'url\([\'"]?(.*?)[\'"]?\)', style)
                            if bg_match:
                                src = bg_match.group(1)
                    
                    if not src or 'staticflickr.com' not in src:
                        continue
                    
                    # Get link to photo page and other data
                    photo_page_url = self.url  # Default to current url
                    title = "Flickr Photo"
                    
                    # Try to find photo ID from parent elements
                    photo_id = ""
                    try:
                        parent = photo.locator('xpath=./ancestor::a').first
                        if await parent.count() > 0:
                            photo_page_url = await parent.get_attribute('href')
                            if photo_page_url and '/photos/' in photo_page_url:
                                photo_id_match = re.search(r'/(\d+)/?$', photo_page_url)
                                if photo_id_match:
                                    photo_id = photo_id_match.group(1)
                    except Exception:
                        pass
                    
                    # Try to get title
                    try:
                        title_elem = page.locator(f'a[href*="{photo_id}"] .title, a[href*="{photo_id}"] .meta .title, .title')
                        if await title_elem.count() > 0:
                            title = await title_elem.inner_text()
                    except Exception:
                        pass
                    
                    # Convert to highest resolution
                    high_res_url = self._get_highest_resolution_url(src)
                    
                    # Create item
                    media_items.append({
                        'url': high_res_url,
                        'alt': title,
                        'title': title,
                        'source_url': photo_page_url,
                        'credits': "Flickr",
                        'type': 'image',
                        'category': 'photo'
                    })
                except Exception as e:
                    print(f"Error processing photo element {i}: {e}")
                    continue
        
        except Exception as e:
            print(f"Error in FlickrHandler extraction: {e}")
            import traceback
            traceback.print_exc()
        
        print(f"FlickrHandler found {len(media_items)} photos")
        return media_items

    # --- Implement extract_with_scrapling_async ---
    async def extract_with_scrapling_async(self, response, **kwargs) -> list:
        """Fallback to generic Scrapling extraction if API fails or isn't used (async version)."""
        print("FlickrHandler: API preferred, falling back to Scrapling (generic HTML).")
        self.start_time = time.time()
        # Use the generic method from the scraper (inherited via BaseSiteHandler default)
        return self.scraper._extract_media_from_scrapling_page(response, self.url, **kwargs)

    def post_process(self, media_items):
        """Post-process the media items to ensure they're unique and have correct metadata"""
        if not media_items:
            return media_items
            
        # Ensure all URLs are absolute and clean
        processed_items = []
        seen_urls = set()
        
        for item in media_items:
            url = item.get('url')
            if not url:
                continue
                
            # Clean URL (remove query params and fragments)
            clean_url = url.split('?')[0].split('#')[0].strip()
            
            # Skip duplicates
            if clean_url in seen_urls:
                continue
                
            # Try one more time to convert to high-res
            high_res_url = self._get_highest_resolution_url(clean_url)
            
            # Update the URL and add to processed items
            item['url'] = high_res_url
            seen_urls.add(high_res_url)
            processed_items.append(item)
            
        return processed_items

    def get_content_directory(self):
        base_dir = "flickr"
        content_dir = "unknown"
        if self.username:
            content_dir = self._sanitize_directory_name(self.username)
            if self.album_id:
                content_dir = os.path.join(content_dir, f"album_{self.album_id}")
            elif self.group_id:
                 content_dir = os.path.join("groups", self._sanitize_directory_name(self.group_id))
        elif self.album_id: # Album ID without username? Unlikely but possible
             content_dir = f"album_{self.album_id}"
        elif self.group_id:
             content_dir = os.path.join("groups", self._sanitize_directory_name(self.group_id))

        return base_dir, content_dir

    async def _extract_single_photo_async(self, page: AsyncPage) -> list:
        """Extract image from a single photo page"""
        media_items = []
        
        try:
            # Wait for the photo to load
            await page.wait_for_selector('.main-photo img, .photo-container img, [data-track="photo-page-photo-img"]', 
                                        timeout=5000)
            
            # Try to find the image element
            photo_elem = page.locator('.main-photo img, .photo-container img, [data-track="photo-page-photo-img"]').first
            
            if await photo_elem.count() > 0:
                # Get image source
                src = await photo_elem.get_attribute('src')
                
                if src and 'staticflickr.com' in src:
                    # Get photo metadata
                    title = "Flickr Photo"
                    photographer = ""
                    
                    # Get title
                    title_elem = page.locator('.photo-title')
                    if await title_elem.count() > 0:
                        title = await title_elem.inner_text()
                    
                    # Get photographer
                    photographer_elem = page.locator('.owner-name, .photo-attribution-info .owner-name')
                    if await photographer_elem.count() > 0:
                        photographer = await photographer_elem.inner_text()
                    
                    # Convert to highest resolution
                    high_res_url = self._get_highest_resolution_url(src)
                    
                    # Add to media items
                    media_items.append({
                        'url': high_res_url,
                        'alt': title,
                        'title': title,
                        'source_url': self.url,
                        'credits': photographer if photographer else "Flickr",
                        'type': 'image',
                        'category': 'photo'
                    })
                    
                    print(f"Extracted single photo: {title}")
            
            # Look for the "View All Sizes" button to get the original size URL
            view_all_sizes = page.locator('a[data-track="photo-sizes"]')
            if await view_all_sizes.count() > 0:
                sizes_url = await view_all_sizes.get_attribute('href')
                if sizes_url:
                    # Navigate to the sizes page
                    print("Navigating to photo sizes page...")
                    full_sizes_url = urljoin(self.url, sizes_url)
                    await page.goto(full_sizes_url, wait_until="domcontentloaded")
                    
                    # Look for the original size link
                    original_link = page.locator('a[data-track="photo-sizes-orig"], .Download')
                    if await original_link.count() > 0:
                        original_url = await original_link.get_attribute('href')
                        if original_url and len(media_items) > 0:
                            # Update the URL to the original size
                            media_items[0]['url'] = original_url
                            print(f"Updated to original size URL: {original_url}")
        
        except Exception as e:
            print(f"Error extracting single photo: {e}")
            import traceback
            traceback.print_exc()
        
        return media_items

    def _get_highest_resolution_url(self, url):
        """
        Convert a Flickr thumbnail URL to its highest resolution version.
        
        Flickr image URLs follow a pattern like:
        https://live.staticflickr.com/{server-id}/{id}_{secret}_SIZE.jpg
        
        Where SIZE can be:
        - _s: small square 75x75
        - _q: large square 150x150
        - _t: thumbnail, 100px
        - _m: small, 240px
        - _n: small, 320px
        - (no suffix): medium, 500px
        - _z: medium 640px
        - _c: medium 800px
        - _b: large, 1024px
        - _h: large, 1600px
        - _k: large, 2048px
        - _o: original size
        
        This method attempts to modify the URL to get the highest resolution version.
        """
        if not url:
            return url
            
        # Skip non-Flickr URLs
        if "staticflickr.com" not in url:
            return url
            
        # If it's already an original size URL, return as is
        if "_o." in url:
            return url
        
        # Try to convert to highest available resolution
        # First attempt to get original size by replacing size suffix
        url_pattern = re.compile(r'(.*_[a-z0-9]+)(_[sqtnmzcbhk])?(\.jpg|\.png|\.gif)$')
        match = url_pattern.match(url)
        
        if match:
            base_url = match.group(1)
            extension = match.group(3)
            
            # Try these size suffixes in decreasing order of quality
            size_suffixes = ['_o', '_k', '_h', '_b', '_c', '_z', '']
            
            for suffix in size_suffixes:
                # We don't want to repeatedly try the original URL if it has a suffix we don't recognize
                if suffix == '' and match.group(2):
                    continue
                    
                high_res_url = f"{base_url}{suffix}{extension}"
                
                # For better performance, we're just returning a constructed URL 
                # without actually checking if it exists
                # A more robust solution would verify these URLs with HEAD requests
                if suffix == '_o':  # Original size typically needs verification
                    try:
                        response = requests.head(high_res_url, timeout=2)
                        if response.status_code == 200:
                            return high_res_url
                        # If original size failed, continue with other sizes
                    except Exception:
                        pass
                else:
                    # For standard sizes, just return the URL without verification
                    return high_res_url
        
        # If all attempts fail, return the original URL
        return url