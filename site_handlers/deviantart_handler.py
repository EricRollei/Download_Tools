"""
Deviantart Handler

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
DeviantArt-specific handler for the Web Image Scraper
Handles deviation (artwork) pages, user galleries, collections, and search results.
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

class DeviantArtHandler(BaseSiteHandler):
    """
    Handler for DeviantArt.com, the largest online art community.
    
    Features:
    - Extract high-resolution artwork (deviations) from pages
    - Support for user galleries, deviation pages, collections and search results
    - Captures artwork titles, descriptions and artist information
    - Proper attribution metadata
    - Special handling for mature content settings
    """
    
    @classmethod
    def can_handle(cls, url):
        """Check if this handler can process the URL"""
        return "deviantart.com" in url.lower() or "fav.me" in url.lower()
    
    def __init__(self, url, scraper=None):
        """Initialize with DeviantArt-specific properties"""
        super().__init__(url, scraper)
        self.username = None
        self.deviation_id = None
        self.deviation_uuid = None
        self.gallery_id = None
        self.page_type = self._determine_page_type(url)
        self.debug_mode = getattr(scraper, 'debug_mode', False)
        
        # Extract identifiers from URL
        self._extract_identifiers_from_url()
        
        # Load site-specific auth configuration
        self._load_api_credentials()  # This is inherited from base_handler
        
        # Set site-specific defaults from config or fallback values
        self.timeout_ms = getattr(self, 'timeout', 5000)
        self.mature_content_enabled = getattr(self, 'mature_content_enabled', True)
        self.mature_cookie_value = getattr(self, 'mature_cookie_value', '1')
        self.scroll_delay_ms = getattr(self, 'scroll_delay_ms', 1800)
        self.max_scroll_count = getattr(self, 'max_scroll_count', 6)
    
    # Keep _determine_page_type() method exactly as is
    def _determine_page_type(self, url):
        """Determine what type of DeviantArt page we're dealing with"""
        # Handle fav.me short URLs
        if "fav.me" in url:
            return "deviation"
            
        parsed_url = urlparse(url)
        path = parsed_url.path.strip('/')
        
        if not path:
            return "home"
            
        path_parts = path.split('/')
        
        # Determine page type based on path structure
        if path.startswith('art/'):
            return "deviation"
        elif path.startswith('tag/'):
            return "tag"
        elif path.startswith('search'):
            return "search"
        elif path.startswith('gallery/'):
            return "gallery"
        elif path.startswith('favourites/'):
            return "favorites"
        elif path.startswith('collections/'):
            return "collection"
        elif len(path_parts) == 1:
            # Just a username
            return "user"
        else:
            return "other"
    
    # Keep _extract_identifiers_from_url() method exactly as is
    def _extract_identifiers_from_url(self):
        """Extract username, deviation ID, etc. from the URL"""
        parsed_url = urlparse(self.url)
        path = parsed_url.path.strip('/')
        path_parts = path.split('/')
        
        # Extract username and IDs based on URL path pattern
        if self.page_type == "user" and len(path_parts) == 1:
            self.username = path_parts[0]
            if self.debug_mode:
                print(f"Extracted username: {self.username}")
                
        elif self.page_type == "deviation" and path.startswith('art/'):
            # Artwork URLs: /art/title-ID
            # Extract the ID at the end
            if len(path_parts) >= 2:
                title_id = path_parts[1]
                id_match = re.search(r'-(\d+)$', title_id)
                if id_match:
                    self.deviation_id = id_match.group(1)
                    if self.debug_mode:
                        print(f"Extracted deviation ID: {self.deviation_id}")
                        
        elif self.page_type in ["gallery", "favorites"] and len(path_parts) >= 2:
            self.username = path_parts[0]
            if len(path_parts) > 2:
                self.gallery_id = path_parts[2]
            if self.debug_mode:
                print(f"Extracted username: {self.username}, gallery ID: {self.gallery_id}")
    
    # Keep get_content_directory() method exactly as is
    def get_content_directory(self):
        """
        Generate DeviantArt-specific directory structure.
        Returns (base_dir, content_specific_dir) tuple.
        """
        # Base directory is always 'deviantart'
        base_dir = "deviantart"
        
        # Content directory based on page type
        content_parts = []
        
        if self.page_type == "user":
            if self.username:
                content_parts.append("user")
                content_parts.append(self._sanitize_directory_name(self.username))
            else:
                # Fallback
                content_parts.append("users")
        elif self.page_type == "deviation":
            if self.username:
                content_parts.append("user")
                content_parts.append(self._sanitize_directory_name(self.username))
                content_parts.append("artwork")
            else:
                content_parts.append("artwork")
                
            if self.deviation_id:
                content_parts.append(self.deviation_id)
        elif self.page_type == "gallery":
            if self.username:
                content_parts.append("user")
                content_parts.append(self._sanitize_directory_name(self.username))
                content_parts.append("gallery")
                if self.gallery_id:
                    content_parts.append(self._sanitize_directory_name(self.gallery_id))
        elif self.page_type == "favorites":
            if self.username:
                content_parts.append("user")
                content_parts.append(self._sanitize_directory_name(self.username))
                content_parts.append("favorites")
                if self.gallery_id:
                    content_parts.append(self._sanitize_directory_name(self.gallery_id))
        elif self.page_type == "tag":
            content_parts.append("tag")
            # Extract tag name from path
            parsed_url = urlparse(self.url)
            path = parsed_url.path.strip('/')
            if path.startswith('tag/'):
                tag_name = path.split('/')[1]
                content_parts.append(self._sanitize_directory_name(tag_name))
        elif self.page_type == "search":
            content_parts.append("search")
            # Extract search query
            parsed_url = urlparse(self.url)
            query = parse_qs(parsed_url.query).get('q', ['general'])[0]
            content_parts.append(self._sanitize_directory_name(query))
        else:
            # Generic path handling
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
    
    async def extract_with_direct_playwright_async(self, page: AsyncPage, **kwargs) -> list:
        """Async extraction using Playwright - Main entry point"""
        print(f"DeviantArtHandler: Extracting via Direct Playwright Async for page type: {self.page_type}")
        
        # Use site-specific or kwargs-provided settings
        timeout = kwargs.get('timeout', self.timeout_ms)
        scroll_count = kwargs.get('max_auto_scrolls', self.max_scroll_count)
        scroll_delay = kwargs.get('scroll_delay_ms', self.scroll_delay_ms)
        
        # Extract additional identifiers if they're not available from the URL
        if self.page_type == "deviation" and not self.username:
            await self._extract_identifiers_from_page_async(page)
        
        # Handle any needed cookie settings for mature content
        await self._setup_mature_content_cookies_async(page)
        
        # Different extraction methods based on page type
        if self.page_type == "deviation":
            # Single deviation page - extract the main artwork
            return await self._extract_deviation_image_async(page)
        elif self.page_type in ["user", "gallery", "favorites", "tag", "search"]:
            # Pages with multiple deviations/thumbnails
            return await self._extract_gallery_images_async(page)
        else:
            # Generic extraction for other page types
            return await self._extract_generic_images_async(page)
    
    async def _setup_mature_content_cookies_async(self, page: AsyncPage):
        """Set cookies to enable viewing mature content if possible"""
        if not PLAYWRIGHT_AVAILABLE or not self.mature_content_enabled:
            return
            
        try:
            # Try to set mature content cookies to enable viewing all content
            cookies = [
                {
                    'name': 'vd',  # Cookie for mature content viewing
                    'value': self.mature_cookie_value,
                    'domain': '.deviantart.com',
                    'path': '/'
                }
            ]
            
            # Check if cookie_file is provided in auth config
            if hasattr(self, 'cookie_file') and self.cookie_file:
                # Load cookies from file
                try:
                    with open(self.cookie_file, 'r') as f:
                        stored_cookies = json.load(f)
                        cookies.extend(stored_cookies)
                except Exception as e:
                    if self.debug_mode:
                        print(f"Error loading cookie file: {e}")
            
            # Check if specific cookies are provided in auth config
            if hasattr(self, 'cookies') and isinstance(self.cookies, list):
                cookies.extend(self.cookies)
            
            # Add the cookies to the page
            await page.context.add_cookies(cookies)
            
            if self.debug_mode:
                print("Added mature content viewing cookies")
        except Exception as e:
            if self.debug_mode:
                print(f"Error setting mature content cookies: {e}")
    
    async def _extract_identifiers_from_page_async(self, page: AsyncPage):
        """Extract additional identifiers from page content"""
        html_content = await page.content()
        if not html_content:
            return
            
        # Look for various metadata patterns in the content
        # Look for username
        if not self.username:
            username_match = re.search(r'<meta name="da:appurl" content="deviantart://deviation/([^/"]+)', html_content)
            if username_match:
                self.username = username_match.group(1)
                if self.debug_mode:
                    print(f"Found username in HTML: {self.username}")
            
            username_match2 = re.search(r'<a[^>]+data-username="([^"]+)"[^>]+class="[^"]*username[^"]*"', html_content)
            if username_match2:
                self.username = username_match2.group(1)
                if self.debug_mode:
                    print(f"Found username in HTML: {self.username}")
                    
        # Look for deviation ID
        if not self.deviation_id:
            id_match = re.search(r'<meta property="da:appurl" content="deviantart://deviation/(\d+)"', html_content)
            if id_match:
                self.deviation_id = id_match.group(1)
                if self.debug_mode:
                    print(f"Found deviation ID in HTML: {self.deviation_id}")
            
            # Look for UUID (sometimes used instead of numeric ID)
            uuid_match = re.search(r'<meta name="da:deviation_id" content="([^"]+)"', html_content)
            if uuid_match:
                self.deviation_uuid = uuid_match.group(1)
                if self.debug_mode:
                    print(f"Found deviation UUID in HTML: {self.deviation_uuid}")
    
    async def _extract_deviation_image_async(self, page: AsyncPage) -> list:
        """Extract image from a single deviation page"""
        media_items = []
        
        try:
            # Wait for deviation content to load
            await page.wait_for_selector('.dev-view-deviation', timeout=self.timeout_ms)
            
            # Check if we need to bypass the mature content filter
            mature_filter = page.locator('.dev-view-deviation.filter-warning').first
            is_mature_visible = await mature_filter.is_visible(timeout=500)
            if is_mature_visible:
                try:
                    # Click the "Yes, I am 18+" button
                    mature_btn = page.locator('button:has-text("Yes")')
                    if await mature_btn.is_visible(timeout=500):
                        await mature_btn.click()
                        await page.wait_for_timeout(2000)  # Wait for content to load
                except Exception as e:
                    if self.debug_mode:
                        print(f"Error bypassing mature content filter: {e}")
            
            # Get deviation title
            title = await page.evaluate("""() => {
                const titleElem = document.querySelector('.dev-title-container h1');
                return titleElem ? titleElem.textContent.trim() : '';
            }""")
            
            # Get artist name
            artist = await page.evaluate("""() => {
                const artistElem = document.querySelector('.dev-title-container a.username');
                return artistElem ? artistElem.textContent.trim() : '';
            }""")
            
            # Get deviation description
            description = await page.evaluate("""() => {
                const descElem = document.querySelector('.dev-description');
                return descElem ? descElem.textContent.trim() : '';
            }""")
            
            # Try to find the full-size download link first
            download_url = await page.evaluate("""() => {
                const downloadBtn = document.querySelector('a[data-hook="download_button"]');
                return downloadBtn ? downloadBtn.href : null;
            }""")
            
            if download_url:
                # Use the download URL for highest resolution
                media_items.append({
                    'url': download_url,
                    'alt': title,
                    'title': title,
                    'description': description,
                    'source_url': self.url,
                    'credits': artist,
                    'type': 'image',
                    'category': 'artwork'
                })
            else:
                # Try to get the main image
                image_data = await page.evaluate("""() => {
                    const img = document.querySelector('.dev-content-full img');
                    if (img) {
                        return {
                            src: img.src,
                            srcset: img.srcset || '',
                            alt: img.alt || ''
                        };
                    }
                    
                    // Try alternative image containers
                    const imgAlt = document.querySelector('.dev-view-deviation img');
                    if (imgAlt) {
                        return {
                            src: imgAlt.src,
                            srcset: imgAlt.srcset || '',
                            alt: imgAlt.alt || ''
                        };
                    }
                    
                    return null;
                }""")
                
                if image_data and image_data.get('src'):
                    # Get the highest resolution version of the image
                    image_url = self._get_highest_res_image(image_data.get('src'), image_data.get('srcset', ''))
                    
                    media_items.append({
                        'url': image_url,
                        'alt': image_data.get('alt', '') or title,
                        'title': title,
                        'description': description,
                        'source_url': self.url,
                        'credits': artist,
                        'type': 'image',
                        'category': 'artwork'
                    })
        except Exception as e:
            if self.debug_mode:
                print(f"Error extracting deviation with Playwright: {e}")
        
        # If Playwright extraction failed or found nothing, try metadata approach
        if not media_items:
            html_content = await page.content()
            
            # Try to find the image URL from OpenGraph metadata
            og_image_match = re.search(r'<meta property="og:image" content="([^"]+)"', html_content)
            if og_image_match:
                image_url = og_image_match.group(1)
                
                # Try to find the high-res version by modifying URL patterns
                if "wixmp" in image_url:
                    # DeviantArt CDN URLs often have resolution indicators
                    high_res_url = self._convert_to_fullsize(image_url)
                    image_url = high_res_url or image_url
                
                # Get title
                title_match = re.search(r'<meta property="og:title" content="([^"]+)"', html_content)
                title = title_match.group(1) if title_match else "DeviantArt Artwork"
                
                # Get artist
                artist_match = re.search(r'<meta property="og:site_name" content="([^"]+)"', html_content)
                artist = artist_match.group(1) if artist_match else ""
                
                # Get description
                desc_match = re.search(r'<meta property="og:description" content="([^"]+)"', html_content)
                description = desc_match.group(1) if desc_match else ""
                
                media_items.append({
                    'url': image_url,
                    'alt': title,
                    'title': title,
                    'description': description,
                    'source_url': self.url,
                    'credits': artist,
                    'type': 'image',
                    'category': 'artwork'
                })
        
        return media_items
    
    async def _extract_gallery_images_async(self, page: AsyncPage) -> list:
        """Extract images from gallery-style pages (user, gallery, etc.)"""
        media_items = []
        
        try:
            # Scroll to load more content
            await self._scroll_page_async(page)
            
            # Extract all deviation thumbnails
            deviation_data = await page.evaluate("""() => {
                const deviations = [];
                // Get all deviation links with thumbnails
                document.querySelectorAll('a[data-hook="deviation_link"]').forEach(link => {
                    const img = link.querySelector('img');
                    const title = link.querySelector('h2, .title');
                    const username = link.querySelector('.username');
                    
                    if (img) {
                        deviations.push({
                            href: link.href,
                            title: title ? title.textContent.trim() : '',
                            username: username ? username.textContent.trim() : '',
                            src: img.src,
                            srcset: img.srcset || '',
                            alt: img.alt || ''
                        });
                    }
                });
                return deviations;
            }""")
            
            # Process each deviation
            for deviation in deviation_data:
                if not deviation.get('src'):
                    continue
                    
                # Get highest resolution version of thumbnail
                image_url = self._get_highest_res_image(deviation.get('src'), deviation.get('srcset', ''))
                
                # Convert thumbnail to full-size if possible
                fullsize_url = self._convert_to_fullsize(image_url)
                
                title = deviation.get('title', '') or deviation.get('alt', '') or "DeviantArt Artwork"
                
                media_items.append({
                    'url': fullsize_url or image_url,
                    'alt': deviation.get('alt', '') or title,
                    'title': title,
                    'source_url': deviation.get('href', self.url),
                    'credits': deviation.get('username', ''),
                    'type': 'image',
                    'category': 'thumbnail'
                })
        except Exception as e:
            if self.debug_mode:
                print(f"Error extracting gallery images with Playwright: {e}")
        
        return media_items
    
    async def _extract_generic_images_async(self, page: AsyncPage) -> list:
        """Generic extraction for any DeviantArt page type"""
        media_items = []
        
        try:
            html_content = await page.content()
            
            # Find all DeviantArt CDN image URLs
            img_matches = re.findall(r'https://[a-z0-9]+\.deviantart\.net/[^"\'\s>]+', html_content)
            
            # Process unique URLs
            seen_urls = set()
            for img_url in img_matches:
                # Clean URL and ensure no duplicates
                clean_url = img_url.split('?')[0].split('#')[0].strip()
                
                if clean_url in seen_urls:
                    continue
                    
                seen_urls.add(clean_url)
                
                # Try to get the full-size version
                fullsize_url = self._convert_to_fullsize(clean_url)
                
                media_items.append({
                    'url': fullsize_url or clean_url,
                    'alt': "DeviantArt Image",
                    'title': "DeviantArt Image",
                    'source_url': self.url,
                    'type': 'image',
                    'category': 'generic'
                })
        except Exception as e:
            if self.debug_mode:
                print(f"Error extracting generic images: {e}")
        
        return media_items
    
    async def _scroll_page_async(self, page: AsyncPage, scroll_count=6, scroll_delay_ms=1800):
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
                        load_more = page.locator('button:has-text("Load More")').first
                        if await load_more.is_visible(timeout=500):
                            await load_more.click()
                            await page.wait_for_timeout(2500)  # Wait longer after clicking
                        else:
                            # Try alternative button
                            more_btn = page.locator('.more-results').first
                            if await more_btn.is_visible(timeout=500):
                                await more_btn.click()
                                await page.wait_for_timeout(2500)
                    except Exception:
                        # If clicking fails, just continue
                        pass
                
                initial_height = new_height
                
                # Break early if we have enough content
                if i >= 3:  # After 4th scroll
                    content_count = await page.evaluate('() => document.querySelectorAll("a[data-hook=\'deviation_link\']").length')
                    if content_count >= 40:
                        if self.debug_mode:
                            print(f"Found {content_count} items, stopping scrolling early")
                        break
                        
        except Exception as e:
            if self.debug_mode:
                print(f"Error during page scrolling: {e}")
    
    # Keep helper methods exactly as is, as they don't need async conversion
    def _get_highest_res_image(self, url, srcset):
        """Get the highest resolution image URL from src and srcset"""
        if not url and not srcset:
            return None
            
        # If we have a srcset, parse it to find the highest resolution
        if srcset:
            highest_res_url = url  # Default to src
            highest_width = 0
            
            # Parse srcset format: "url1 1x, url2 2x" or "url1 100w, url2 200w"
            for entry in srcset.split(','):
                parts = entry.strip().split(' ')
                if len(parts) == 2:
                    entry_url = parts[0]
                    
                    # Handle different descriptors
                    if 'w' in parts[1]:
                        try:
                            width = int(parts[1].replace('w', ''))
                            if width > highest_width:
                                highest_width = width
                                highest_res_url = entry_url
                        except ValueError:
                            pass
                    elif 'x' in parts[1]:
                        try:
                            density = float(parts[1].replace('x', ''))
                            width_equivalent = int(density * 1000)  # Rough estimate
                            if width_equivalent > highest_width:
                                highest_width = width_equivalent
                                highest_res_url = entry_url
                        except ValueError:
                            pass
            
            return highest_res_url
        
        # If we have a DeviantArt CDN URL, try to get the highest resolution version
        return self._convert_to_fullsize(url) or url
    
    def _convert_to_fullsize(self, url):
        """
        Convert a DeviantArt thumbnail/preview URL to full-size version
        This handles various DeviantArt CDN patterns
        """
        if not url:
            return None
            
        # For wixmp.com URLs (DeviantArt's image CDN)
        if "wixmp.com" in url:
            # Remove size limitations from URL
            # Pattern examples:
            # /f/...-pre.jpg -> /f/...-orig.jpg
            # /f/...-200h.jpg -> /f/...-orig.jpg
            # /f/...-350p.jpg -> /f/...-orig.jpg
            # /intermediary/... -> /orig/...
            
            fullsize_url = url
            
            # Handle preview/small size markers
            size_patterns = ['-pre.', '-small.', '-250p.', '-150p.', '-350p.', '-200h.']
            for pattern in size_patterns:
                if pattern in fullsize_url:
                    fullsize_url = fullsize_url.replace(pattern, '-orig.')
                    
            # Handle intermediary path
            if '/intermediary/' in fullsize_url:
                fullsize_url = fullsize_url.replace('/intermediary/', '/orig/')
                
            if fullsize_url != url:
                return fullsize_url
        
        # Handle older deviantart.net URLs
        elif "deviantart.net" in url:
            # For older CDN URLs:
            # Pattern examples:
            # th01.deviantart.net -> orig01.deviantart.net
            # img00.deviantart.net/1234/t/... -> img00.deviantart.net/1234/f/...
            
            fullsize_url = url
            
            # th to orig substitution
            if 'th' in fullsize_url.split('.')[0]:
                subdomain = fullsize_url.split('.')[0]
                orig_subdomain = 'orig' + subdomain[2:]
                fullsize_url = fullsize_url.replace(subdomain, orig_subdomain)
                
            # Path substitution for /t/ -> /f/
            if '/t/' in fullsize_url:
                fullsize_url = fullsize_url.replace('/t/', '/f/')
                
            if fullsize_url != url:
                return fullsize_url
                
        return None
    
    def post_process(self, media_items):
        """Clean and enhance the extracted media items"""
        if not media_items:
            return media_items
            
        processed_items = []
        seen_urls = set()
        
        for item in media_items:
            url = item.get('url')
            if not url:
                continue
                
            # Clean URL
            clean_url = url.split('?')[0].split('#')[0].strip()
            
            # Skip duplicates
            if clean_url in seen_urls:
                continue
                
            # Update URL and add to processed items
            item['url'] = clean_url
            seen_urls.add(clean_url)
            
            # Ensure proper credits format
            if item.get('credits') and 'by' not in item.get('credits', '').lower():
                item['credits'] = f"by {item['credits']} on DeviantArt"
                
            processed_items.append(item)
            
        return processed_items
    
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
    
    def pre_process(self, page):
        """Legacy pre-process method - not used in async version"""
        if self.debug_mode:
            print("WARNING: Sync pre_process method called - this should not be used")
        return page