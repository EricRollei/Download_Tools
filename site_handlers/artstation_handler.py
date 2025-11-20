"""
Artstation Handler

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
ArtStation-specific handler for the Web Image Scraper
Handles artist profiles, artwork pages, search results and collections.
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
    from scrapling.fetchers import PlayWrightFetcher
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    AsyncPage = None
    PlayWrightFetcher = None
    PLAYWRIGHT_AVAILABLE = False

class ArtStationHandler(BaseSiteHandler):
    """
    Handler for ArtStation.com, a platform for professional artists.
    
    Features:
    - Extract high-resolution artwork from project pages
    - Support for artist profiles, project pages, collections and search results
    - Captures project titles, descriptions and artist information
    - Proper attribution metadata
    """
    
    @classmethod
    def can_handle(cls, url):
        """Check if this handler can process the URL"""
        return "artstation.com" in url.lower()
    
    def __init__(self, url, scraper=None):
        """Initialize with ArtStation-specific properties"""
        super().__init__(url, scraper)
        self.username = None
        self.project_id = None
        self.hash_id = None  # ArtStation uses hash IDs in URLs
        self.page_type = self._determine_page_type(url)
        self.debug_mode = getattr(scraper, 'debug_mode', False)
        
        # Extract identifiers from URL
        self._extract_identifiers_from_url()
    
    def _determine_page_type(self, url):
        """Determine what type of ArtStation page we're dealing with"""
        parsed_url = urlparse(url)
        path = parsed_url.path.strip('/')
        
        if not path:
            return "home"
            
        path_parts = path.split('/')
        
        if path_parts[0] == "artwork":
            return "project"
        elif path_parts[0] == "search":
            return "search"
        elif path_parts[0] == "collections":
            return "collection"
        elif path_parts[0] == "channels":
            return "channel"
        elif path_parts[0] == "marketplace":
            return "marketplace"
        elif len(path_parts) == 1:
            # Just a username
            return "profile"
        else:
            return "other"
    
    def _extract_identifiers_from_url(self):
        """Extract username, project ID, etc. from the URL"""
        parsed_url = urlparse(self.url)
        path = parsed_url.path.strip('/')
        path_parts = path.split('/')
        
        if self.page_type == "profile" and len(path_parts) == 1:
            self.username = path_parts[0]
            if self.debug_mode:
                print(f"Extracted username: {self.username}")
                
        elif self.page_type == "project" and len(path_parts) > 1:
            # Artwork URLs: /artwork/project-name-hash
            # Extract the hash ID
            project_slug = path_parts[1]
            hash_match = re.search(r'[a-zA-Z0-9]{6,}$', project_slug)
            if hash_match:
                self.hash_id = hash_match.group(0)
                if self.debug_mode:
                    print(f"Extracted hash ID: {self.hash_id}")
    
    def get_content_directory(self):
        """
        Generate ArtStation-specific directory structure.
        Returns (base_dir, content_specific_dir) tuple.
        """
        # Base directory is always 'artstation'
        base_dir = "artstation"
        
        # Content directory based on page type
        content_parts = []
        
        if self.page_type == "profile":
            if self.username:
                content_parts.append("user")
                content_parts.append(self._sanitize_directory_name(self.username))
            else:
                # Fallback
                content_parts.append("users")
        elif self.page_type == "project":
            content_parts.append("artwork")
            if self.hash_id:
                content_parts.append(self.hash_id)
            else:
                # Extract from path
                parsed_url = urlparse(self.url)
                path = parsed_url.path.strip('/')
                if path.startswith('artwork/'):
                    project_slug = path.split('/')[1]
                    content_parts.append(self._sanitize_directory_name(project_slug))
        elif self.page_type == "search":
            content_parts.append("search")
            # Extract search query
            parsed_url = urlparse(self.url)
            query = parse_qs(parsed_url.query).get('q', ['general'])[0]
            content_parts.append(self._sanitize_directory_name(query))
        elif self.page_type == "collection":
            content_parts.append("collection")
            # Extract collection name from path
            parsed_url = urlparse(self.url)
            path = parsed_url.path.strip('/')
            if path.startswith('collections/'):
                collection_parts = path.split('/')
                if len(collection_parts) > 1:
                    collection_name = collection_parts[1]
                    content_parts.append(self._sanitize_directory_name(collection_name))
        elif self.page_type == "channel":
            content_parts.append("channel")
            # Extract channel name from path
            parsed_url = urlparse(self.url)
            path = parsed_url.path.strip('/')
            if path.startswith('channels/'):
                channel_parts = path.split('/')
                if len(channel_parts) > 1:
                    channel_name = channel_parts[1]
                    content_parts.append(self._sanitize_directory_name(channel_name))
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
    
    async def extract_with_direct_playwright_async(self, page, **kwargs):
        """Extract images using async Playwright"""
        if self.debug_mode:
            print(f"Extracting images from ArtStation page type: {self.page_type}")
            
        # Different extraction methods based on page type
        if self.page_type == "project":
            # Single project page - extract all project images
            return await self._extract_project_images_async(page)
        elif self.page_type in ["profile", "search", "collection", "channel"]:
            # Pages with multiple project thumbnails
            return await self._extract_gallery_images_async(page)
        else:
            # Generic extraction for other page types
            return await self._extract_generic_images_async(page)
    
    async def _extract_project_images_async(self, page):
        """Extract images from a project page (async version)"""
        media_items = []
        
        if PLAYWRIGHT_AVAILABLE and page:
            try:
                # Wait for project content to load
                await page.wait_for_selector('.project-assets', timeout=5000)
                
                # Get project title
                project_title = await page.evaluate("""() => {
                    const titleElem = document.querySelector('.project-title');
                    return titleElem ? titleElem.textContent.trim() : '';
                }""")
                
                # Get project description
                project_description = await page.evaluate("""() => {
                    const descElem = document.querySelector('.project-description');
                    return descElem ? descElem.textContent.trim() : '';
                }""")
                
                # Get artist name
                artist_name = await page.evaluate("""() => {
                    const artistElem = document.querySelector('.artist-name');
                    return artistElem ? artistElem.textContent.trim() : '';
                }""")
                
                # Extract all project assets (images)
                asset_data = await page.evaluate("""() => {
                    const assets = [];
                    // Get all project assets
                    document.querySelectorAll('.project-asset').forEach((asset, index) => {
                        // Look for image
                        const img = asset.querySelector('img');
                        if (img) {
                            // Check if it's in a lightbox
                            const lightbox = asset.querySelector('a.project-lightbox-link');
                            const assetLink = lightbox ? lightbox.href : '';
                            
                            // Check for asset caption
                            const caption = asset.querySelector('.asset-caption');
                            
                            assets.push({
                                index: index,
                                src: img.src || '',
                                srcset: img.srcset || '',
                                lightboxLink: assetLink,
                                caption: caption ? caption.textContent.trim() : ''
                            });
                        }
                    });
                    return assets;
                }""")
                
                # Process each asset
                for asset in asset_data:
                    # First try to get the highest-res image from the lightbox link
                    image_url = ""
                    
                    if asset.get('lightboxLink') and '/projects/' in asset.get('lightboxLink'):
                        # This is a link to the full-sized image
                        image_url = asset.get('lightboxLink')
                    else:
                        # Get the best image from srcset or src
                        image_url = self._get_highest_res_image(asset.get('src', ''), asset.get('srcset', ''))
                    
                    if not image_url:
                        continue
                    
                    # Create a title for the image
                    asset_title = asset.get('caption', '') or f"{project_title} - Image {asset.get('index', 0) + 1}"
                    
                    media_items.append({
                        'url': image_url,
                        'alt': asset_title,
                        'title': asset_title,
                        'description': project_description,
                        'source_url': self.url,
                        'credits': artist_name,
                        'type': 'image',
                        'category': 'artwork'
                    })
            except Exception as e:
                if self.debug_mode:
                    print(f"Error extracting project images with Playwright: {e}")
        
        # If no items found, try HTML parsing as fallback
        if not media_items:
            try:
                html_content = await page.content()
                # Look for project data in JSON
                json_data_match = re.search(r'window\.__INITIAL_STATE__\s*=\s*(\{.*\});', html_content, re.DOTALL)
                if json_data_match:
                    json_text = json_data_match.group(1)
                    json_data = json.loads(json_text)
                    
                    # Extract project info
                    project_data = None
                    
                    # Find the current project
                    if 'projects' in json_data:
                        for hash_id, project in json_data['projects'].items():
                            if isinstance(project, dict) and project.get('hash_id') == self.hash_id:
                                project_data = project
                                break
                    
                    if not project_data and 'projects' in json_data and json_data['projects']:
                        # Just take the first project if we can't find a match
                        for hash_id, project in json_data['projects'].items():
                            if isinstance(project, dict):
                                project_data = project
                                break
                    
                    if project_data:
                        # Extract title and author
                        project_title = project_data.get('title', '')
                        project_description = project_data.get('description', '')
                        artist_name = ""
                        
                        if 'user' in project_data and isinstance(project_data['user'], dict):
                            artist_name = project_data['user'].get('full_name', '') or project_data['user'].get('username', '')
                        
                        # Extract assets (images)
                        if 'assets' in project_data and isinstance(project_data['assets'], list):
                            for idx, asset in enumerate(project_data['assets']):
                                if isinstance(asset, dict) and 'image_url' in asset:
                                    image_url = asset['image_url']
                                    
                                    # Try to get the highest resolution version
                                    if 'asset_type' in asset and asset['asset_type'] == 'image':
                                        # Check for higher res versions
                                        for size_key in ['best_image_url', 'large_image_url', 'medium_image_url']:
                                            if size_key in asset and asset[size_key]:
                                                image_url = asset[size_key]
                                                break
                                    
                                    asset_title = asset.get('title', '') or f"{project_title} - Image {idx+1}"
                                    
                                    media_items.append({
                                        'url': image_url,
                                        'alt': asset_title,
                                        'title': asset_title,
                                        'description': project_description,
                                        'source_url': self.url,
                                        'credits': artist_name,
                                        'type': 'image',
                                        'category': 'artwork'
                                    })
            except Exception as e:
                if self.debug_mode:
                    print(f"Error parsing JSON data: {e}")
        
        return media_items

    def _extract_projects_from_json(self, json_data):
        """Extract project data from ArtStation JSON"""
        projects = []
        
        def search_json(obj, depth=0, max_depth=10):
            """Recursively search JSON for project data"""
            if depth > max_depth:
                return
            
            if isinstance(obj, dict):
                # Look for project objects
                has_project_data = False
                project_data = {'url': '', 'title': '', 'artist': '', 'href': ''}
                
                # Check for image URL
                for img_key in ['cover', 'cover_url', 'image_url', 'thumbnail_url', 'large_image_url']:
                    if img_key in obj and isinstance(obj[img_key], str) and 'artstation.com' in obj[img_key]:
                        project_data['url'] = obj[img_key]
                        has_project_data = True
                
                # Check for title
                for title_key in ['title', 'name']:
                    if title_key in obj and isinstance(obj[title_key], str):
                        project_data['title'] = obj[title_key]
                
                # Check for artist name
                if 'user' in obj and isinstance(obj['user'], dict):
                    for name_key in ['full_name', 'username', 'name']:
                        if name_key in obj['user'] and isinstance(obj['user'][name_key], str):
                            project_data['artist'] = obj['user'][name_key]
                            break
                
                # Check for permalink/href
                for link_key in ['permalink', 'url', 'link']:
                    if link_key in obj and isinstance(obj[link_key], str):
                        project_data['href'] = obj[link_key]
                
                # Add project if we have image data
                if has_project_data and project_data['url']:
                    projects.append(project_data)
                
                # Continue searching all values
                for value in obj.values():
                    search_json(value, depth + 1, max_depth)
                    
            elif isinstance(obj, list):
                for item in obj:
                    search_json(item, depth + 1, max_depth)
        
        # Start recursive search
        search_json(json_data)
        return projects

    async def _extract_gallery_images_async(self, page):
        """Extract images from gallery-style pages (search, profile, etc.) (async version)"""
        media_items = []
        
        try:
            # Scroll to load more content
            await self._scroll_page_async(page)
            
            # Extract all project cards - using updated selectors for current ArtStation DOM
            project_data = await page.evaluate("""() => {
                const projects = [];
                
                // Try multiple selector patterns for project cards
                const cardSelectors = [
                    '.gallery-grid-item', 
                    '.project-card',
                    '.project-grid-item',
                    '.artwork-grid-item',
                    'div[data-test="project-image"]',
                    '.project-list-item'
                ];
                
                // Loop through selectors until we find matching elements
                for (const selector of cardSelectors) {
                    const cards = document.querySelectorAll(selector);
                    
                    if (cards && cards.length > 0) {
                        console.log(`Found ${cards.length} cards with selector ${selector}`);
                        
                        cards.forEach(card => {
                            // Find the image element
                            const img = card.querySelector('img');
                            
                            // Find the link to the project page
                            const link = card.querySelector('a');
                            
                            if (img) {
                                // Get all possible image sources
                                const src = img.src || '';
                                const dataSrc = img.dataset.src || '';
                                const imgSource = dataSrc || src;
                                
                                // Skip if no valid image
                                if (!imgSource || imgSource.includes('placeholder') || 
                                    imgSource.includes('icon') || imgSource.includes('avatar')) {
                                    return;
                                }
                                
                                // Find title and artist info
                                let title = '';
                                let artist = '';
                                
                                // Try to find title element
                                const titleElem = card.querySelector('.project-title, .artwork-title, .title, h2, h3');
                                if (titleElem) {
                                    title = titleElem.textContent.trim();
                                }
                                
                                // Try to find artist element
                                const artistElem = card.querySelector('.artist-name, .username, .user-name, .author');
                                if (artistElem) {
                                    artist = artistElem.textContent.trim();
                                }
                                
                                // Get project URL
                                let href = '';
                                if (link && link.href) {
                                    href = link.href;
                                }
                                
                                projects.push({
                                    href: href,
                                    title: title || img.alt || 'ArtStation Project',
                                    artist: artist,
                                    src: imgSource
                                });
                            }
                        });
                        
                        // If we found projects with this selector, break out of the loop
                        if (projects.length > 0) {
                            break;
                        }
                    }
                }
                
                // If card selectors didn't work, try a more general approach
                if (projects.length === 0) {
                    // Find all substantial images on the page
                    const allImages = Array.from(document.querySelectorAll('img'))
                        .filter(img => {
                            // Filter out small images that are likely icons/UI elements
                            const rect = img.getBoundingClientRect();
                            return (rect.width > 150 && rect.height > 150) && 
                                (!img.src.includes('icon') && !img.src.includes('avatar'));
                        });
                        
                    console.log(`Found ${allImages.length} substantial images`);
                    
                    allImages.forEach(img => {
                        // Get image source
                        const src = img.src || '';
                        
                        // Find parent link if any
                        const link = img.closest('a');
                        let href = link ? link.href : '';
                        
                        // Find title if any
                        let title = img.alt || '';
                        const titleElem = img.closest('[class*="title"]') || img.closest('[class*="card"]');
                        if (titleElem) {
                            const foundTitle = titleElem.querySelector('[class*="title"]');
                            if (foundTitle) {
                                title = foundTitle.textContent.trim();
                            }
                        }
                        
                        projects.push({
                            href: href,
                            title: title || 'ArtStation Artwork',
                            artist: '',
                            src: src
                        });
                    });
                }
                
                return projects;
            }""")
            
            print(f"Extracted {len(project_data)} project cards")
            
            # Process each project
            for project in project_data:
                image_url = project.get('src', '')
                
                if not image_url:
                    continue
                
                # Convert to high-resolution version
                high_res_url = self._get_highest_res_image(image_url)
                
                # Create a title for the image
                title = project.get('title', '') or "ArtStation Project"
                
                media_items.append({
                    'url': high_res_url,
                    'alt': title,
                    'title': title,
                    'source_url': project.get('href', self.url),
                    'credits': project.get('artist', ''),
                    'type': 'image',
                    'category': 'thumbnail'
                })
            
            # If no items found using the DOM approach, try extracting from JSON
            if not media_items:
                print("No items found with DOM extraction, trying JSON extraction...")
                try:
                    # Get the page HTML content
                    html_content = await page.content()
                    
                    # Look for JSON data that might contain project information
                    json_match = re.search(r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\});', html_content, re.DOTALL)
                    if json_match:
                        # Clean up and parse the JSON
                        json_text = json_match.group(1)
                        json_text = re.sub(r'undefined', 'null', json_text)
                        json_data = json.loads(json_text)
                        
                        # Extract projects from the JSON data
                        json_projects = self._extract_projects_from_json(json_data)
                        print(f"Found {len(json_projects)} projects in JSON data")
                        
                        # Process each project from JSON
                        for project in json_projects:
                            if project.get('url'):
                                media_items.append({
                                    'url': project['url'],
                                    'alt': project.get('title', 'ArtStation Project'),
                                    'title': project.get('title', 'ArtStation Project'),
                                    'source_url': project.get('href', self.url),
                                    'credits': project.get('artist', ''),
                                    'type': 'image',
                                    'category': 'thumbnail'
                                })
                except Exception as e:
                    print(f"Error during JSON extraction: {e}")
                    import traceback
                    traceback.print_exc()
            
            # Final fallback - direct URL extraction from HTML
            if not media_items:
                print("No items found with JSON extraction, trying URL pattern extraction...")
                try:
                    html_content = await page.content()
                    
                    # Find potential image URLs that match ArtStation patterns
                    image_matches = re.findall(r'https://cdna\.artstation\.com/[^"\'\s>]+', html_content)
                    
                    # Process found URLs
                    seen_urls = set()
                    for url in image_matches:
                        # Clean URL
                        clean_url = url.split('?')[0].split('#')[0]
                        
                        # Skip duplicates
                        if clean_url in seen_urls:
                            continue
                        
                        seen_urls.add(clean_url)
                        
                        # Convert to high-res
                        high_res_url = self._get_highest_res_image(clean_url)
                        
                        media_items.append({
                            'url': high_res_url,
                            'alt': "ArtStation Image",
                            'title': "ArtStation Image",
                            'source_url': self.url,
                            'type': 'image',
                            'category': 'search_result'
                        })
                    
                    print(f"Found {len(media_items)} images with URL extraction")
                except Exception as e:
                    print(f"Error during URL extraction: {e}")
        
        except Exception as e:
            print(f"Error extracting gallery images with Playwright: {e}")
            import traceback
            traceback.print_exc()
        
        print(f"Gallery extraction found {len(media_items)} images")
        return media_items
    
    async def _extract_generic_images_async(self, page):
        """Generic extraction for any ArtStation page type (async version)"""
        media_items = []
        
        try:
            html_content = await page.content()
            
            # Find all ArtStation CDN image URLs
            img_matches = re.findall(r'https://cdna\.artstation\.com/[^"\'\s>]+', html_content)
            
            # Process unique URLs
            seen_urls = set()
            for img_url in img_matches:
                # Clean URL and ensure no duplicates
                clean_url = img_url.split('?')[0].split('#')[0].strip()
                
                if clean_url in seen_urls:
                    continue
                    
                seen_urls.add(clean_url)
                
                # Try to get the highest resolution version
                high_res_url = clean_url
                
                if "/smaller_square/" in high_res_url:
                    high_res_url = high_res_url.replace("/smaller_square/", "/large/")
                elif "/small_square/" in high_res_url:
                    high_res_url = high_res_url.replace("/small_square/", "/large/")
                elif "/medium/" in high_res_url:
                    high_res_url = high_res_url.replace("/medium/", "/large/")
                
                media_items.append({
                    'url': high_res_url,
                    'alt': "ArtStation Image",
                    'title': "ArtStation Image",
                    'source_url': self.url,
                    'type': 'image',
                    'category': 'generic'
                })
        except Exception as e:
            if self.debug_mode:
                print(f"Error in generic extraction: {e}")
        
        return media_items
    
    async def _scroll_page_async(self, page, scroll_count=5, scroll_delay_ms=1500):
        """Scroll down the page to load more content (async version)"""
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
                        load_more = page.locator('.more-content, .infinite-scroll__waypoint').first
                        is_visible = await load_more.is_visible(timeout=1000)
                        if is_visible:
                            await load_more.click()
                            await page.wait_for_timeout(2000)  # Wait longer after clicking
                    except Exception:
                        # If clicking fails, just continue
                        pass
                
                initial_height = new_height
                
                # Break early if we have enough content
                if i >= 2:  # After 3rd scroll
                    content_count = await page.evaluate('() => document.querySelectorAll(".project-card").length')
                    if content_count >= 30:
                        if self.debug_mode:
                            print(f"Found {content_count} items, stopping scrolling early")
                        break
                        
        except Exception as e:
            if self.debug_mode:
                print(f"Error during page scrolling: {e}")

    def _get_highest_res_image(self, url):
        """Get the highest resolution image URL from an ArtStation image URL"""
        if not url or not isinstance(url, str):
            return url
            
        # Skip non-ArtStation URLs
        if 'artstation.com' not in url:
            return url
        
        # Convert thumbnail URLs to full size
        if "/smaller_square/" in url:
            return url.replace("/smaller_square/", "/large/")
        elif "/small_square/" in url:
            return url.replace("/small_square/", "/large/")
        elif "/medium/" in url:
            return url.replace("/medium/", "/large/")
        elif "/small/" in url:
            return url.replace("/small/", "/large/")
        elif "/default/" in url:
            return url.replace("/default/", "/large/")
        elif "/smaller/" in url:
            return url.replace("/smaller/", "/large/")
        elif "/micro_square/" in url:
            return url.replace("/micro_square/", "/large/")
        
        # Specific pattern for assets subdirectory
        if "/assets/" in url and ("/t/" in url or "/small/" in url or "/medium/" in url):
            # Replace size indicators with large
            return re.sub(r'/assets/\d+/(.+?)/(?:t|small|medium)/', r'/assets/\d+/\1/large/', url)
        
        return url
        
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
                item['credits'] = f"by {item['credits']} on ArtStation"
                
            processed_items.append(item)
            
        return processed_items