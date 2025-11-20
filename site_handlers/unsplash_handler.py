"""
Unsplash Handler

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
Unsplash-specific handler for the Web Image Scraper
"""

from site_handlers.base_handler import BaseSiteHandler
from urllib.parse import urljoin, urlparse
import re
import os

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

class UnsplashHandler(BaseSiteHandler):
    """
    Handler for Unsplash.com, a popular free stock photo site.
    
    This handler optimizes extraction of high-quality images from Unsplash
    along with proper attribution metadata.
    """
    
    @classmethod
    def can_handle(cls, url):
        """Check if this handler can process the URL"""
        return "unsplash.com" in url.lower()
    
    def __init__(self, url, scraper=None):
        """Initialize with Unsplash-specific properties"""
        super().__init__(url, scraper)
        self.debug_mode = getattr(scraper, 'debug_mode', False)
        
        # Load site-specific auth configuration
        self._load_api_credentials()  # This is inherited from base_handler
        
        # Set site-specific defaults from config or fallback values
        self.timeout_ms = getattr(self, 'timeout', 5000)
        self.scroll_delay_ms = getattr(self, 'scroll_delay_ms', 1000)
        self.max_scroll_count = getattr(self, 'max_scroll_count', 5)
        self.default_width = getattr(self, 'default_width', 2400)
    
    async def extract_with_direct_playwright_async(self, page: AsyncPage, **kwargs) -> list:
        """Async extraction using Playwright - Main entry point"""
        print(f"UnsplashHandler: Extracting via Direct Playwright Async")
        
        # Use site-specific or kwargs-provided settings
        timeout = kwargs.get('timeout', self.timeout_ms)
        scroll_count = kwargs.get('max_auto_scrolls', self.max_scroll_count)
        scroll_delay = kwargs.get('scroll_delay_ms', self.scroll_delay_ms)
        
        # Scroll to load more images
        if scroll_count > 0:
            await self._scroll_page_async(page, scroll_count=scroll_count, scroll_delay_ms=scroll_delay)
        
        # Extract media items
        media_items = await self._extract_with_playwright_async(page)
        
        # Post-process the results
        return self.post_process(media_items)
    
    async def _extract_with_playwright_async(self, page: AsyncPage) -> list:
        """Extract images with proper metadata from Unsplash using Playwright"""
        media_items = []
        
        try:
            # Wait for photo elements to load
            await page.wait_for_selector('figure[itemprop="photograph"], figure.photo, figure img', timeout=self.timeout_ms)
            
            # Extract photo data using JavaScript for efficiency
            photo_data = await page.evaluate('''() => {
                const photos = [];
                // Try multiple selectors to find photos
                let photoElements = document.querySelectorAll('figure[itemprop="photograph"]');
                if (!photoElements.length) {
                    photoElements = document.querySelectorAll('figure.photo');
                }
                if (!photoElements.length) {
                    photoElements = document.querySelectorAll('figure:has(img)');
                }
                
                photoElements.forEach(figure => {
                    const img = figure.querySelector('img');
                    if (!img) return;
                    
                    // Parse srcset to find highest resolution URL
                    const srcset = img.getAttribute('srcset');
                    let highestRes = '';
                    if (srcset) {
                        const entries = srcset.split(',');
                        let maxWidth = 0;
                        
                        entries.forEach(entry => {
                            const parts = entry.trim().split(' ');
                            if (parts.length === 2) {
                                const width = parseInt(parts[1].replace('w', ''));
                                if (width > maxWidth) {
                                    maxWidth = width;
                                    highestRes = parts[0];
                                }
                            }
                        });
                    }
                    
                    // Extract photographer credits
                    let credits = '';
                    const authorLink = figure.querySelector('a[rel="author"], a.author');
                    if (authorLink) {
                        credits = authorLink.textContent.trim();
                    }
                    
                    photos.push({
                        url: highestRes || img.src,
                        alt: img.alt || '',
                        title: img.title || '',
                        credits: credits,
                        originalSrc: img.src
                    });
                });
                
                return photos;
            }''')
            
            # Convert extracted data to media items
            for data in photo_data:
                if not data.get('url'):
                    continue
                    
                # Make relative URLs absolute if needed
                image_url = data['url']
                if not image_url.startswith(('http://', 'https://')):
                    image_url = urljoin(self.url, image_url)
                
                media_items.append({
                    'url': image_url,
                    'alt': data.get('alt', ''),
                    'title': data.get('title', ''),
                    'source_url': self.url,
                    'credits': data.get('credits', ''),
                    'type': 'image'
                })
        except Exception as e:
            if self.debug_mode:
                print(f"Error extracting Unsplash images with Playwright: {e}")
            
            # Fallback to more basic extraction
            try:
                img_count = await page.locator("img").count()
                print(f"Found {img_count} images in fallback mode")
                
                for i in range(img_count):
                    img = page.locator("img").nth(i)
                    src = await img.get_attribute("src")
                    srcset = await img.get_attribute("srcset")
                    
                    # Parse srcset manually if available
                    image_url = src
                    if srcset:
                        entries = srcset.split(',')
                        highest_width = 0
                        for entry in entries:
                            parts = entry.strip().split(' ')
                            if len(parts) == 2 and 'w' in parts[1]:
                                try:
                                    width = int(parts[1].replace('w', ''))
                                    if width > highest_width:
                                        highest_width = width
                                        image_url = parts[0]
                                except ValueError:
                                    pass
                    
                    alt = await img.get_attribute("alt") or ""
                    title = await img.get_attribute("title") or ""
                    
                    if image_url:
                        if not image_url.startswith(('http://', 'https://')):
                            image_url = urljoin(self.url, image_url)
                        
                        media_items.append({
                            'url': image_url,
                            'alt': alt,
                            'title': title,
                            'source_url': self.url,
                            'credits': "Photo from Unsplash",
                            'type': 'image'
                        })
            except Exception as fallback_error:
                if self.debug_mode:
                    print(f"Error in fallback extraction: {fallback_error}")
        
        return media_items
    
    async def _scroll_page_async(self, page: AsyncPage, scroll_count=5, scroll_delay_ms=1000):
        """Scroll down the page to load more content"""
        if not page:
            return
        
        try:
            initial_height = await page.evaluate('() => document.body.scrollHeight')
            
            for i in range(scroll_count):
                if self.debug_mode:
                    print(f"Scrolling page ({i+1}/{scroll_count})...")
                
                # Scroll to bottom
                await page.evaluate('() => window.scrollTo(0, document.body.scrollHeight)')
                
                # Wait for content to load
                await page.wait_for_timeout(scroll_delay_ms)
                
                # Check if more content was loaded
                new_height = await page.evaluate('() => document.body.scrollHeight')
                if new_height == initial_height:
                    if self.debug_mode:
                        print("No more content loaded after scroll")
                    break
                
                initial_height = new_height
        except Exception as e:
            if self.debug_mode:
                print(f"Error during page scrolling: {e}")
    
    def post_process(self, media_items):
        """
        Post-process the extracted media items
        
        For Unsplash, ensure we have proper attribution and clean URLs
        """
        for item in media_items:
            # Ensure we have proper credits format for Unsplash
            if item.get('credits') and 'Photo by' not in item.get('credits', ''):
                item['credits'] = f"Photo by {item['credits']} on Unsplash"
            
            # If we didn't get credits but it's an Unsplash item, add a generic credit
            if not item.get('credits') and item.get('type') == 'image':
                item['credits'] = "Photo from Unsplash"
            
            # Fix Unsplash URLs to get full resolution if needed
            url = item.get('url', '')
            if url and '&w=' in url:
                # Replace with configured default width or fallback
                width_pattern = f'&w={self.default_width}'
                item['url'] = re.sub(r'&w=\d+', width_pattern, url)
        
        return media_items
    
    def get_content_directory(self):
        """
        Generate Unsplash-specific directory structure.
        Returns (base_dir, content_specific_dir) tuple.
        """
        # Base directory is always 'unsplash'
        base_dir = "unsplash"
        
        # Content-specific directory based on what we're scraping
        content_parts = []
        
        # Parse URL to extract meaningful information
        parsed_url = urlparse(self.url)
        path = parsed_url.path.strip('/')
        
        if not path:
            # Homepage
            content_parts.append("home")
        elif path.startswith('photos/'):
            # Single photo page: /photos/abc123
            photo_parts = path.split('/')
            if len(photo_parts) > 1:
                content_parts.append("photos")
                content_parts.append(self._sanitize_directory_name(photo_parts[1]))
        elif path.startswith('@'):
            # User profile: /@username
            username = path.lstrip('@')
            content_parts.append("user")
            content_parts.append(self._sanitize_directory_name(username))
        elif path.startswith('s/'):
            # Search results: /s/photos/search-term
            search_parts = path.split('/')
            if len(search_parts) > 2:
                content_parts.append("search")
                content_parts.append(self._sanitize_directory_name(search_parts[2]))
        elif path.startswith('collections/'):
            # Collection page: /collections/123456/collection-name
            collection_parts = path.split('/')
            if len(collection_parts) > 1:
                content_parts.append("collection")
                collection_id = collection_parts[1]
                if len(collection_parts) > 2:
                    collection_name = collection_parts[2]
                    content_parts.append(self._sanitize_directory_name(collection_name))
                else:
                    content_parts.append(collection_id)
        elif path.startswith('t/'):
            # Topic page: /t/architecture
            topic_parts = path.split('/')
            if len(topic_parts) > 1:
                content_parts.append("topic")
                content_parts.append(self._sanitize_directory_name(topic_parts[1]))
        else:
            # Generic path handling
            path_components = [self._sanitize_directory_name(p) for p in path.split('/') if p]
            if path_components:
                content_parts.extend(path_components[:2])  # Limit depth to 2
        
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
    
    def extract_with_direct_playwright(self, page: SyncPage, **kwargs) -> list:
        """Legacy sync extraction method - not used in async version"""
        if self.debug_mode:
            print("WARNING: Sync extraction method called - this should not be used")
        return []