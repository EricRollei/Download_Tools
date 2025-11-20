"""
500Px Handler

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
500px.com specific handler for the Web Image Scraper
"""

from site_handlers.base_handler import BaseSiteHandler
from urllib.parse import urljoin, urlparse, parse_qs
import os
import re
import json
import time
from typing import List, Dict, Any, Optional, Union

# Try importing Playwright types safely
try:
    from playwright.async_api import Page as AsyncPage
    from scrapling.fetchers import PlayWrightFetcher
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    AsyncPage = None
    PlayWrightFetcher = None
    PLAYWRIGHT_AVAILABLE = False

class Px500Handler(BaseSiteHandler):
    """
    Handler for 500px.com.
    Focuses on extracting high-quality photos from user profiles, photo pages, and galleries.
    
    Features:
    - DOM-based extraction with auto-scrolling
    - Support for various page types (photo, profile, gallery)
    - Extracts highest available resolution photos
    - Captures photo titles, descriptions, and photographer information
    """

    @classmethod
    def can_handle(cls, url):
        """Check if this handler can process the URL"""
        return "500px.com" in url.lower()

    def __init__(self, url, scraper=None):
        """Initialize with 500px-specific properties"""
        super().__init__(url, scraper)
        self.username = None
        self.photo_id = None
        self.gallery_id = None
        self.page_type = self._determine_page_type(url)
        self.debug_mode = getattr(scraper, 'debug_mode', False)
        
        # Extract key identifiers from URL
        self._extract_identifiers_from_url()
        
        # Set site-specific defaults from config or fallback values
        self.timeout_ms = getattr(self, 'timeout', 5000)
        self.scroll_delay_ms = getattr(self, 'scroll_delay_ms', 1500)
        self.max_scroll_count = getattr(self, 'max_scroll_count', 5)
        self.max_resolution = getattr(self, 'max_resolution', '6000')

    def _determine_page_type(self, url):
        """Determine what type of 500px page we're dealing with"""
        parsed_url = urlparse(url)
        path = parsed_url.path.strip('/')
        
        if not path:
            return "home"
            
        path_parts = path.split('/')
        
        if path.startswith('photo/'):
            return "photo"
        elif path.startswith('p/'):
            return "profile"
        elif path.startswith('discover') or path.startswith('search'):
            return "search"
        elif len(path_parts) > 1 and path_parts[1] == 'galleries':
            return "gallery"
        else:
            return "other"
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
            {"type": "wait_for_selector", "selector": "button:has-text('Accept All')", "timeout": 3000},
            {"type": "click", "selector": "button:has-text('Accept All')"},
            # Dismiss login/signup popup if present
            {"type": "wait_for_selector", "selector": "button[aria-label='Close']", "timeout": 3000},
            {"type": "click", "selector": "button[aria-label='Close']"},
            # Click "Load More" if present (repeat as needed)
            {"type": "wait_for_selector", "selector": "button:has-text('Load More')", "timeout": 3000},
            {"type": "click", "selector": "button:has-text('Load More')"},
            # Click "Load More" if present (repeat as needed)
            {"type": "wait_for_selector", "selector": "button:has-text('Load More')", "timeout": 3000},
            {"type": "click", "selector": "button:has-text('Load More')"},
            # Click "Load More" if present (repeat as needed)
            {"type": "wait_for_selector", "selector": "button:has-text('Load More')", "timeout": 3000},
            {"type": "click", "selector": "button:has-text('Load More')"},
            # Click "Load More" if present (repeat as needed)
            {"type": "wait_for_selector", "selector": "button:has-text('Load More')", "timeout": 3000},
            {"type": "click", "selector": "button:has-text('Load More')"},           
            # Click "Load More" if present (repeat as needed)
            {"type": "wait_for_selector", "selector": "button:has-text('Load More')", "timeout": 3000},
            {"type": "click", "selector": "button:has-text('Load More')"},
            # Click "Load More" if present (repeat as needed)
            {"type": "wait_for_selector", "selector": "button:has-text('Load More')", "timeout": 3000},
            {"type": "click", "selector": "button:has-text('Load More')"},
        ]


    def _extract_identifiers_from_url(self):
        """Extract username, photo ID, etc. from the URL"""
        parsed_url = urlparse(self.url)
        path = parsed_url.path.strip('/')
        path_parts = path.split('/')
        
        if self.page_type == "profile" and len(path_parts) > 1:
            self.username = path_parts[1]
            if self.debug_mode:
                print(f"Extracted username: {self.username}")
                
        elif self.page_type == "photo" and len(path_parts) > 1:
            try:
                self.photo_id = path_parts[1]
                if self.debug_mode:
                    print(f"Extracted photo ID: {self.photo_id}")
            except Exception:
                pass
                
        elif self.page_type == "gallery" and len(path_parts) > 2:
            self.username = path_parts[0]
            self.gallery_id = path_parts[2]
            if self.debug_mode:
                print(f"Extracted gallery ID: {self.gallery_id} for user: {self.username}")

    def get_content_directory(self):
        """
        Generate 500px-specific directory structure.
        Returns (base_dir, content_specific_dir) tuple.
        """
        # Base directory is always '500px'
        base_dir = "500px"
        
        # Content directory based on page type
        content_parts = []
        
        if self.page_type == "profile" and self.username:
            content_parts.append("user")
            content_parts.append(self._sanitize_directory_name(self.username))
        elif self.page_type == "photo" and self.photo_id:
            content_parts.append("photo")
            content_parts.append(self.photo_id)
        elif self.page_type == "gallery" and self.username and self.gallery_id:
            content_parts.append("user")
            content_parts.append(self._sanitize_directory_name(self.username))
            content_parts.append("gallery")
            content_parts.append(self._sanitize_directory_name(self.gallery_id))
        elif self.page_type == "search":
            content_parts.append("search")
            # Extract search query if present
            parsed_url = urlparse(self.url)
            query = parse_qs(parsed_url.query).get('q', ['general'])[0]
            content_parts.append(self._sanitize_directory_name(query))
        else:
            # Fallback: use path components from URL
            parsed_url = urlparse(self.url)
            path = parsed_url.path.strip('/')
            path_components = [self._sanitize_directory_name(p) for p in path.split('/') if p]
            if path_components:
                content_parts.extend(path_components[:2])  # Limit depth to 2
            else:
                content_parts.append("general")
        
        # Join all parts to form the path
        content_specific_dir = os.path.join(*content_parts)
        
        return (base_dir, content_specific_dir)

    async def extract_with_direct_playwright_async(self, page: AsyncPage, **kwargs) -> list:
        print(f"500pxHandler: Extracting via Direct Playwright Async for page type: {self.page_type}")

        # Run interaction sequence (from UI, kwargs, or default)
        interaction_sequence = kwargs.get("interaction_sequence") or getattr(self, "interaction_sequence", None)
        if not interaction_sequence:
            interaction_sequence = self.get_default_interaction_sequence()
        await self._run_interaction_sequence(page, interaction_sequence)
        
        # Use site-specific or kwargs-provided settings
        timeout = kwargs.get('timeout', self.timeout_ms)
        scroll_count = kwargs.get('max_auto_scrolls', self.max_scroll_count)
        scroll_delay = kwargs.get('scroll_delay_ms', self.scroll_delay_ms)
        
        # Extract additional identifiers if needed
        if not self.username or (self.page_type == "photo" and not self.photo_id):
            await self._extract_identifiers_from_page_async(page)
        
        # Get raw media items based on page type
        if self.page_type == "photo":
            # Single photo page - extract the main photo
            raw_items = await self._extract_single_photo_async(page)
        elif self.page_type in ["profile", "gallery", "search"]:
            # Pages with multiple photos - scroll and extract all
            raw_items = await self._extract_multiple_photos_async(page)
        else:
            # Generic extraction for other page types
            raw_items = await self._extract_generic_async(page)
        
        # Apply post-processing before returning
        return self.post_process(raw_items)

    async def _extract_identifiers_from_page_async(self, page: AsyncPage):
        """Extract additional identifiers from page content"""
        html_content = await page.content()
        if not html_content:
            return
            
        # Try to find username in various patterns
        if not self.username:
            # Look for canonical profile URL
            profile_match = re.search(r'<link rel="canonical" href="https://500px.com/p/([^"/]+)"', html_content)
            if profile_match:
                self.username = profile_match.group(1)
                if self.debug_mode:
                    print(f"Found username in canonical link: {self.username}")
                    
            # Look in JSON data
            json_data_match = re.search(r'window\.__RELAY_STATE__\s*=\s*(\{.*?\});', html_content, re.DOTALL)
            if json_data_match:
                try:
                    json_text = json_data_match.group(1)
                    # Remove any invalid escape sequences that might cause JSON parsing to fail
                    json_text = re.sub(r'\\(?!["\\/bfnrt]|u[0-9a-fA-F]{4})', r'\\\\', json_text)
                    json_data = json.loads(json_text)
                    
                    # Navigate through the JSON structure to find user info
                    # Structure might vary, so we're being cautious with gets
                    if isinstance(json_data, dict):
                        for key, value in json_data.items():
                            if isinstance(value, dict) and 'username' in value:
                                self.username = value['username']
                                if self.debug_mode:
                                    print(f"Found username in JSON: {self.username}")
                                break
                except Exception as e:
                    if self.debug_mode:
                        print(f"Error parsing JSON data: {e}")
        
        # Try to extract photo ID if needed
        if self.page_type == "photo" and not self.photo_id:
            # Look for photo ID in various patterns
            photo_id_match = re.search(r'data-photo-id="(\d+)"', html_content)
            if photo_id_match:
                self.photo_id = photo_id_match.group(1)
                if self.debug_mode:
                    print(f"Found photo ID in HTML: {self.photo_id}")

    async def _extract_single_photo_async(self, page: AsyncPage) -> list:
        """Extract a single photo from a photo detail page"""
        media_items = []
        
        try:
            # Wait for the main image to load
            await page.wait_for_selector('img.photo-show__img, .photo-detail img, .photo-viewer img', timeout=self.timeout_ms)
            
            # Extract photo details
            photo_url = await page.evaluate("""() => {
                // Try different selectors for the main photo
                const selectors = [
                    'img.photo-show__img',
                    '.photo-detail img',
                    '.photo-viewer img',
                    '.photo-page__image img',
                    '.photo-show__image-container img'
                ];
                
                for (const selector of selectors) {
                    const img = document.querySelector(selector);
                    if (img && img.src) {
                        return img.src;
                    }
                }
                
                return null;
            }""")
            
            photo_title = await page.evaluate("""() => {
                const selectors = [
                    'h1.photo-show__top-info-title',
                    '.photo-detail__title',
                    '.photo-title',
                    '.photo-header__title'
                ];
                
                for (const selector of selectors) {
                    const title = document.querySelector(selector);
                    if (title) {
                        return title.textContent.trim();
                    }
                }
                
                return "500px Photo";
            }""")
            
            photographer = await page.evaluate("""() => {
                const selectors = [
                    'a.photo-show__top-info-photographer-name',
                    '.photo-detail__photographer',
                    '.photographer-name',
                    '.username'
                ];
                
                for (const selector of selectors) {
                    const author = document.querySelector(selector);
                    if (author) {
                        return author.textContent.trim();
                    }
                }
                
                return "";
            }""")
            
            description = await page.evaluate("""() => {
                const selectors = [
                    'div.photo-show__description',
                    '.photo-description',
                    '.photo-info__description'
                ];
                
                for (const selector of selectors) {
                    const desc = document.querySelector(selector);
                    if (desc) {
                        return desc.textContent.trim();
                    }
                }
                
                return "";
            }""")
            
            if photo_url:
                # Try to get the highest resolution version
                high_res_url = self._get_highest_resolution_url(photo_url)
                
                # Add headers for the request
                headers = self._get_request_headers(high_res_url)
                
                media_items.append({
                    'url': high_res_url or photo_url,
                    'alt': description or photo_title,
                    'title': photo_title,
                    'source_url': self.url,
                    'credits': photographer,
                    'type': 'image',
                    'category': 'photo',
                    '_headers': headers  # Add the headers for download
                })
                
                print(f"Extracted single photo: {photo_title}")
        except Exception as e:
            print(f"Error extracting single photo with Playwright: {e}")
            import traceback
            traceback.print_exc()
        
        return media_items

    async def _extract_multiple_photos_async(self, page: AsyncPage) -> list:
        """Extract multiple photos from a profile, gallery, or search page"""
        media_items = []
        
        try:
            # First scroll the page to load all content
            await self._scroll_page_async(page, scroll_count=self.max_scroll_count)
            
            # Instead of waiting for specific selectors, extract all images directly
            print("Extracting images from 500px page using generic image detection...")
            
            # Use JavaScript to find all substantial images on the page
            photo_data = await page.evaluate('''() => {
                const photos = [];
                
                // Find all img elements that are likely to be photos
                const imgElements = Array.from(document.querySelectorAll('img'))
                    .filter(img => {
                        // Skip small images like icons
                        const rect = img.getBoundingClientRect();
                        return (rect.width > 100 && rect.height > 100);
                    });
                
                console.log(`Found ${imgElements.length} substantial images`);
                
                imgElements.forEach((img, index) => {
                    // IMPORTANT: Get the complete URL with signature
                    const src = img.src || ''; // This preserves the full URL including query params
                    const dataSrc = img.getAttribute('data-src') || '';
                    
                    // Skip icons, avatars, etc.
                    if (src.includes('avatar') || src.includes('icon') || 
                        src.includes('logo') || !src.includes('drscdn.500px.org')) {
                        return;
                    }
                    
                    // Take the full URL exactly as is
                    let bestUrl = src || dataSrc;
                    
                    // Get other metadata
                    let title = img.alt || img.title || '';
                    let photographer = '';
                    let href = '';
                    
                    // Get link to photo page if available
                    let parent = img.closest('a');
                    if (parent && parent.href) {
                        href = parent.href;
                    }
                    
                    // Find nearby title or photographer info if available
                    const container = img.closest('div') || img.parentElement;
                    if (container) {
                        // Look for photographer
                        const userElem = container.querySelector('[class*="user"], [class*="author"], [class*="photographer"]');
                        if (userElem) {
                            photographer = userElem.textContent.trim();
                        }
                    }
                    
                    if (bestUrl) {
                        console.log(`Found image: ${bestUrl}`);
                        photos.push({
                            url: bestUrl, // The complete URL with signature
                            title: title || `500px Photo ${index + 1}`,
                            photographer: photographer,
                            href: href
                        });
                    }
                });
                
                return photos;
            }''')
            
            print(f"Extracted {len(photo_data)} photos from 500px {self.page_type} page")
            
            # Process the extracted data
            for photo in photo_data:
                if photo.get('url'):
                    # Get highest resolution version - UPDATED VERSION THAT PRESERVES QUERY PARAMS
                    high_res_url = self._get_highest_resolution_url(photo['url'])
                    
                    # Create media item
                    media_items.append({
                        'url': high_res_url,
                        'alt': photo.get('title', ''),
                        'title': photo.get('title', ''),
                        'source_url': photo.get('href', self.url),
                        'credits': photo.get('photographer', ''),
                        'type': 'image',
                        'category': 'gallery_photo',
                        '_headers': self._get_request_headers()
                    })
            
            # If we still haven't found any images, try extracting from JSON data
            if not media_items:
                print("DOM extraction found no images, attempting to extract from page JSON data...")
                html_content = await page.content()
                
                # Look for JSON data in the page
                json_pattern = re.compile(r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\});', re.DOTALL)
                match = json_pattern.search(html_content)
                
                if match:
                    try:
                        json_text = match.group(1)
                        # Clean up the JSON text (replace undefined with null, etc.)
                        json_text = re.sub(r'undefined', 'null', json_text)
                        json_data = json.loads(json_text)
                        
                        # Look for photo data in the JSON
                        json_photos = self._extract_photos_from_json(json_data)
                        
                        print(f"Found {len(json_photos)} photos in JSON data")
                        
                        # Add JSON photos to media items
                        for photo in json_photos:
                            if photo.get('url'):
                                # Get highest resolution version
                                high_res_url = self._get_highest_resolution_url(photo['url'])
                                
                                media_items.append({
                                    'url': high_res_url,
                                    'alt': photo.get('title', ''),
                                    'title': photo.get('title', ''),
                                    'source_url': photo.get('href', self.url),
                                    'credits': photo.get('photographer', ''),
                                    'type': 'image',
                                    'category': 'gallery_photo',
                                    '_headers': self._get_request_headers()
                                })
                    except Exception as e:
                        print(f"Error extracting photos from JSON: {e}")
                
                # Final fallback: direct URL extraction from HTML
                if not media_items:
                    print("Looking for image URLs directly in HTML...")
                    # Find all URLs that match 500px image patterns
                    url_matches = re.findall(r'https://drscdn\.500px\.org/photo/[^"\'\s\)]+', html_content)
                    
                    seen = set()
                    for url in url_matches:
                        if url in seen:
                            continue
                        seen.add(url)
                        
                        # Get highest resolution version
                        high_res_url = self._get_highest_resolution_url(url)
                        
                        media_items.append({
                            'url': high_res_url,
                            'alt': "500px Photo",
                            'title': "500px Photo",
                            'source_url': self.url,
                            'type': 'image',
                            'category': 'search_result',
                            '_headers': self._get_request_headers()
                        })
        
        except Exception as e:
            print(f"Error extracting multiple photos: {e}")
            import traceback
            traceback.print_exc()
        
        print(f"500px extraction complete. Found {len(media_items)} media items")
        return media_items

    def _extract_photos_from_json(self, json_data):
        """Extract photo information from 500px JSON data"""
        photos = []
        
        # Helper function to recursively search JSON
        def search_json(obj, depth=0, max_depth=10):
            # Limit recursion depth to avoid stack overflow
            if depth > max_depth:
                return
                
            if isinstance(obj, dict):
                # Look for photo objects that contain image URLs
                has_photo_data = False
                photo_data = {'url': '', 'title': '', 'photographer': '', 'href': ''}
                
                # Check for common photo properties
                if 'url' in obj and isinstance(obj['url'], str) and 'drscdn.500px.org' in obj['url']:
                    photo_data['url'] = obj['url']
                    has_photo_data = True
                    
                # Check for URLs in 'urls' or 'images' object
                for key in ['urls', 'images']:
                    if key in obj and isinstance(obj[key], dict):
                        for size, url in obj[key].items():
                            if isinstance(url, str) and 'drscdn.500px.org' in url:
                                photo_data['url'] = url
                                has_photo_data = True
                                break
                
                # Look for title
                for key in ['name', 'title']:
                    if key in obj and isinstance(obj[key], str):
                        photo_data['title'] = obj[key]
                
                # Look for photographer info
                if 'user' in obj and isinstance(obj['user'], dict):
                    for key in ['fullname', 'username', 'name']:
                        if key in obj['user'] and isinstance(obj['user'][key], str):
                            photo_data['photographer'] = obj['user'][key]
                            break
                
                # Look for link to photo
                if 'url' in obj and isinstance(obj['url'], str) and '/photo/' in obj['url']:
                    photo_data['href'] = obj['url']
                
                # If we found photo data, add it to results
                if has_photo_data and photo_data['url']:
                    photos.append(photo_data)
                
                # Continue searching in all values
                for value in obj.values():
                    search_json(value, depth + 1, max_depth)
                    
            elif isinstance(obj, list):
                for item in obj:
                    search_json(item, depth + 1, max_depth)
        
        # Start recursive search
        search_json(json_data)
        return photos

        
    async def _extract_generic_async(self, page: AsyncPage) -> list:
        """Generic extraction for any 500px page type"""
        media_items = []
        
        try:
            # Extract all image URLs from the page
            html_content = await page.content()
            
            # Find all 500px CDN image URLs
            img_matches = re.findall(r'https://drscdn.500px.org[^"\'\s>]+', html_content)
            
            # Process unique URLs
            seen_urls = set()
            for img_url in img_matches:
                # Clean the URL
                clean_url = img_url.split('?')[0].split('#')[0].strip()
                
                # Skip duplicates
                if clean_url in seen_urls:
                    continue
                    
                seen_urls.add(clean_url)
                
                # Get highest resolution version
                high_res_url = self._get_highest_resolution_url(clean_url)
                
                media_items.append({
                    'url': high_res_url or clean_url,
                    'alt': "Photo from 500px",
                    'title': "500px Photo",
                    'source_url': self.url,
                    'type': 'image',
                    'category': 'photo',
                    '_headers': self._get_request_headers()  # Add the required headers
                })
        except Exception as e:
            if self.debug_mode:
                print(f"Error during generic extraction: {e}")
        
        return media_items

    async def _scroll_page_async(self, page: AsyncPage, scroll_count=5, scroll_delay_ms=1500):
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
                    # No new content loaded, try clicking "Load More" if it exists
                    try:
                        load_more = page.locator('button.load-more, button:has-text("Load More")').first
                        if await load_more.is_visible(timeout=500):
                            await load_more.click()
                            await page.wait_for_timeout(2000)  # Wait longer after clicking
                    except Exception:
                        # If clicking fails, just continue scrolling
                        pass
                
                initial_height = new_height
                
                # Break early if we've scrolled enough
                if i >= 2:  # After 3rd scroll
                    # Check if we have enough photo cards
                    photo_count = await page.evaluate('() => document.querySelectorAll("a.photo-card").length')
                    if photo_count >= 30:
                        if self.debug_mode:
                            print(f"Found {photo_count} photos, stopping scrolling early")
                        break
                        
        except Exception as e:
            if self.debug_mode:
                print(f"Error during page scrolling: {e}")

    def _get_highest_resolution_url(self, url):
        """Convert a 500px image URL to its highest available resolution while preserving signatures."""
        if not url or not isinstance(url, str) or 'drscdn.500px.org' not in url:
            return url
            
        # Split URL and query parameters
        url_parts = url.split('?', 1)
        base_url = url_parts[0]
        query_params = url_parts[1] if len(url_parts) > 1 else ''
        
        # Handle resolution patterns but preserve signatures
        if '/q%3D' in base_url and '/m%3D' in base_url:
            # Matches pattern like: q%3D80_m%3D600
            res_pattern = re.search(r'q%3D(\d+)_m%3D(\d+)', base_url)
            if res_pattern:
                old_pattern = res_pattern.group(0)
                quality = res_pattern.group(1)
                size = res_pattern.group(2)
                
                # Increase resolution but keep same quality
                new_pattern = f'q%3D{quality}_m%3D{self.max_resolution or "2048"}'
                new_base_url = base_url.replace(old_pattern, new_pattern)
                
                # Reassemble URL with original query parameters
                if query_params:
                    return f"{new_base_url}?{query_params}"
                return new_base_url
        
        # Don't modify URLs we can't parse properly - return original
        return url

    def _get_request_headers(self):
        """Generate appropriate headers for 500px requests to avoid 403 errors"""
        return {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Referer': 'https://500px.com/',
            'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Sec-Fetch-Dest': 'image',
            'Sec-Fetch-Mode': 'no-cors',
            'Sec-Fetch-Site': 'cross-site',
            'Connection': 'keep-alive',
            'Cache-Control': 'no-cache'
        }
    def post_process(self, media_items):
        """Post-process media items to ensure they have proper headers and URLs"""
        if not media_items:
            return media_items
            
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
                
            # Try once more to get highest resolution version
            high_res_url = self._get_highest_resolution_url(clean_url)
            
            # Make sure we have headers
            if '_headers' not in item:
                item['_headers'] = self._get_request_headers()
                
            # Update URL and add to processed items
            item['url'] = high_res_url
            seen_urls.add(high_res_url)
            processed_items.append(item)
            
        print(f"Post-processing: {len(media_items)} -> {len(processed_items)} unique items")
        return processed_items
