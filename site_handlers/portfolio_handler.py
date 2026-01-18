"""
Portfolio Handler

Description: Handler for model portfolio sites like juliaromanova.com that use clickable image galleries
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
"""

"""
Portfolio handler for simple model portfolio sites with clickable image galleries.
Handles sites like juliaromanova.com, artfolio-powered sites, and similar simple galleries.
"""

from site_handlers.base_handler import BaseSiteHandler
from urllib.parse import urljoin, urlparse
import re
import time
import traceback

# Try importing Playwright types safely
try:
    from playwright.async_api import Page as AsyncPage
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    AsyncPage = None
    PLAYWRIGHT_AVAILABLE = False


class PortfolioHandler(BaseSiteHandler):
    """
    Handler for simple portfolio sites with clickable image galleries.
    
    Targets sites that:
    - Have thumbnail galleries where clicking opens larger images
    - Use patterns like /galleries/, /portfolio/, /photos/
    - Often use numbered image paths or ID-based URLs
    - Include artfolio.com-powered sites
    """

    # Sites and patterns this handler can process
    KNOWN_PORTFOLIO_PATTERNS = [
        r'juliaromanova\.com',
        r'artfolio\.com',
        r'/galleries?/',
        r'/portfolio/',
        r'/photos?/',
        r'/book/',
        r'/albums?/',
        r'/models?/',
        r'/shoots?/',
    ]
    
    # Image URL patterns that indicate resizable images (can be upgraded to larger versions)
    RESIZABLE_PATTERNS = [
        (r'g_10_', 'g_30_'),  # Artfolio pattern: 10% thumb to 30% large
        (r'_thumb\.', '_full.'),
        (r'_small\.', '_large.'),
        (r'_t\.', '_l.'),
        (r'/s/', '/l/'),  # some sites use /s/ for small
        (r'/small/', '/large/'),
        (r'/thumb/', '/full/'),
        (r'width=\d+', 'width=2000'),
        (r'w=\d+', 'w=2000'),
        (r'size=\w+', 'size=original'),
    ]

    # Sites that have their own specific handlers - don't handle these
    EXCLUDED_DOMAINS = [
        'modelmayhem.com',
        'instagram.com',
        'flickr.com',
        '500px.com',
        'deviantart.com',
        'artstation.com',
        'behance.net',
    ]

    @classmethod
    def can_handle(cls, url):
        """Check if this handler can process the URL"""
        url_lower = url.lower()
        
        # Don't handle sites that have their own specific handlers
        for excluded_domain in cls.EXCLUDED_DOMAINS:
            if excluded_domain in url_lower:
                return False
        
        # Check for known portfolio patterns
        for pattern in cls.KNOWN_PORTFOLIO_PATTERNS:
            if re.search(pattern, url_lower, re.IGNORECASE):
                print(f"PortfolioHandler can handle: {url} (matched pattern: {pattern})")
                return True
        
        return False

    def __init__(self, url, scraper=None):
        """Initialize the portfolio handler"""
        super().__init__(url, scraper)
        self.debug_mode = True
        self.gallery_links = []
        self.seen_urls = set()
        self.image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.tiff']
        print(f"PortfolioHandler initialized for URL: {url}")

    def prefers_api(self):
        """This handler doesn't use APIs"""
        return False

    def requires_api(self):
        """This handler doesn't require API access"""
        return False

    async def extract_media_items_async(self, page):
        """
        Extract media items from portfolio gallery pages.
        
        This handler:
        1. Finds all gallery links (clickable thumbnails)
        2. Extracts direct image URLs from thumbnails
        3. Upgrades thumbnail URLs to full-size versions
        """
        print(f"PortfolioHandler: Extracting media from {self.url}")
        start_time = time.time()
        media_items = []
        
        # Get the Playwright page
        pw_page = await self._get_playwright_page_async(page)
        if not pw_page:
            print("No Playwright page available, falling back to DOM extraction")
            return await self._extract_from_html(page)
        
        try:
            # Wait for the page to load
            await pw_page.wait_for_load_state('networkidle', timeout=15000)
            
            # First, try to extract all images directly with full resolution
            media_items = await self._extract_and_upgrade_images(pw_page)
            
            # If we found images, return them
            if media_items:
                print(f"PortfolioHandler: Found {len(media_items)} media items")
                return media_items
            
            # Fallback: Extract from gallery links and navigate to each
            gallery_items = await self._extract_gallery_links(pw_page)
            if gallery_items:
                media_items.extend(gallery_items)
            
        except Exception as e:
            print(f"PortfolioHandler error: {e}")
            traceback.print_exc()
        
        print(f"PortfolioHandler: Extracted {len(media_items)} media items in {time.time() - start_time:.2f}s")
        return media_items

    async def _extract_and_upgrade_images(self, pw_page):
        """Extract images from the page and upgrade to full resolution"""
        media_items = []
        
        try:
            # Get all images from the page
            images = await pw_page.evaluate('''
                () => {
                    const imgs = document.querySelectorAll('img');
                    const result = [];
                    
                    imgs.forEach(img => {
                        const src = img.src || img.dataset.src || img.getAttribute('data-lazy-src') || '';
                        if (src && !src.includes('data:image') && !src.includes('blank.gif')) {
                            // Get the largest version we can find
                            const srcset = img.srcset || '';
                            let largestSrc = src;
                            let largestWidth = img.naturalWidth || 0;
                            
                            // Parse srcset for larger versions
                            if (srcset) {
                                const srcsetParts = srcset.split(',');
                                for (const part of srcsetParts) {
                                    const match = part.trim().match(/^(\S+)\s+(\d+)w$/);
                                    if (match) {
                                        const [, url, width] = match;
                                        if (parseInt(width) > largestWidth) {
                                            largestWidth = parseInt(width);
                                            largestSrc = url;
                                        }
                                    }
                                }
                            }
                            
                            // Get parent link if exists (for galleries)
                            let parentLink = null;
                            const link = img.closest('a');
                            if (link && link.href) {
                                parentLink = link.href;
                            }
                            
                            result.push({
                                src: largestSrc,
                                originalSrc: src,
                                alt: img.alt || '',
                                title: img.title || '',
                                width: img.naturalWidth || 0,
                                height: img.naturalHeight || 0,
                                parentLink: parentLink
                            });
                        }
                    });
                    
                    return result;
                }
            ''')
            
            print(f"PortfolioHandler: Found {len(images)} images on page")
            
            for img_data in images:
                src = img_data.get('src', '')
                if not src:
                    continue
                
                # Skip tracking pixels and tiny images
                width = img_data.get('width', 0)
                height = img_data.get('height', 0)
                if width > 0 and width < 50 and height > 0 and height < 50:
                    continue
                
                # Try to upgrade to full resolution
                full_res_url = self._upgrade_to_full_resolution(src)
                
                # Skip if we've already seen this URL
                if full_res_url in self.seen_urls:
                    continue
                self.seen_urls.add(full_res_url)
                
                media_item = {
                    'url': full_res_url,
                    'original_url': src,
                    'type': 'image',
                    'alt_text': img_data.get('alt', ''),
                    'title': img_data.get('title', ''),
                    'source': 'portfolio_handler',
                    'parent_link': img_data.get('parentLink', '')
                }
                media_items.append(media_item)
            
        except Exception as e:
            print(f"Error extracting images: {e}")
            traceback.print_exc()
        
        return media_items

    def _upgrade_to_full_resolution(self, url):
        """
        Upgrade a thumbnail URL to full resolution version.
        Uses known patterns to transform URLs.
        """
        upgraded_url = url
        
        for pattern, replacement in self.RESIZABLE_PATTERNS:
            if re.search(pattern, url):
                upgraded_url = re.sub(pattern, replacement, url)
                if upgraded_url != url:
                    print(f"Upgraded URL: {url[:50]}... -> {upgraded_url[:50]}...")
                    break
        
        return upgraded_url

    async def _extract_gallery_links(self, pw_page):
        """Extract links to gallery pages (for multi-page galleries)"""
        media_items = []
        
        try:
            # Get all links that look like gallery item links
            links = await pw_page.evaluate('''
                () => {
                    const links = document.querySelectorAll('a');
                    const galleryLinks = [];
                    
                    for (const link of links) {
                        const href = link.href;
                        // Look for gallery/portfolio-style links with numbers or slugs
                        if (href && (
                            href.match(/\\/galleries?\\/.*\\/\\d+/) ||
                            href.match(/\\/portfolio\\/.*\\//) ||
                            href.match(/\\/photos?\\/.*\\//) ||
                            href.match(/\\/book\\/[\\w-]+/) ||
                            href.match(/\\/albums?\\/.*\\//)
                        )) {
                            // Check if link contains an image (thumbnail)
                            const img = link.querySelector('img');
                            if (img) {
                                galleryLinks.push({
                                    href: href,
                                    title: link.title || img.alt || '',
                                    thumbSrc: img.src || ''
                                });
                            }
                        }
                    }
                    
                    return galleryLinks;
                }
            ''')
            
            print(f"PortfolioHandler: Found {len(links)} gallery links")
            
            # For each gallery link, try to extract the full-size image
            for link_data in links:
                href = link_data.get('href', '')
                thumb_src = link_data.get('thumbSrc', '')
                
                if href in self.seen_urls:
                    continue
                self.seen_urls.add(href)
                
                # Try to derive full-res URL from thumbnail
                if thumb_src:
                    full_res_url = self._upgrade_to_full_resolution(thumb_src)
                    
                    if full_res_url not in self.seen_urls:
                        self.seen_urls.add(full_res_url)
                        media_item = {
                            'url': full_res_url,
                            'original_url': thumb_src,
                            'type': 'image',
                            'alt_text': link_data.get('title', ''),
                            'source': 'portfolio_handler',
                            'gallery_page': href
                        }
                        media_items.append(media_item)
            
        except Exception as e:
            print(f"Error extracting gallery links: {e}")
            traceback.print_exc()
        
        return media_items

    async def _get_playwright_page_async(self, page):
        """Get the underlying Playwright page object"""
        if not PLAYWRIGHT_AVAILABLE:
            return None
            
        # Handle different page wrapper types
        if hasattr(page, '_playwright_page'):
            return page._playwright_page
        elif hasattr(page, 'page'):
            return page.page
        elif isinstance(page, AsyncPage) if AsyncPage else False:
            return page
        elif hasattr(page, 'playwright_page'):
            return page.playwright_page
        
        return page

    async def _extract_from_html(self, page):
        """Fallback HTML extraction when Playwright isn't available"""
        media_items = []
        
        try:
            # Try to get HTML content
            html = None
            if hasattr(page, 'html'):
                html = page.html
            elif hasattr(page, 'content'):
                html = await page.content() if callable(page.content) else page.content
            
            if html:
                # Simple regex to find image URLs
                img_pattern = r'<img[^>]+src=["\']([^"\']+)["\']'
                matches = re.findall(img_pattern, html, re.IGNORECASE)
                
                for src in matches:
                    if src and not src.startswith('data:'):
                        full_url = urljoin(self.url, src)
                        full_res = self._upgrade_to_full_resolution(full_url)
                        
                        if full_res not in self.seen_urls:
                            self.seen_urls.add(full_res)
                            media_items.append({
                                'url': full_res,
                                'original_url': full_url,
                                'type': 'image',
                                'source': 'portfolio_handler_html'
                            })
        
        except Exception as e:
            print(f"Error in HTML extraction: {e}")
        
        return media_items

    async def extract_with_direct_playwright(self, page, **kwargs):
        """Direct Playwright extraction method called by the scraper"""
        return await self.extract_media_items_async(page)
