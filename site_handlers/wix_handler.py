"""
Wix Handler

Description: Handler for Wix-powered websites with image galleries
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
Wix handler for websites built on the Wix platform.
Handles image extraction and resolution upgrades for Wix's image CDN.

Wix image URL patterns:
- static.wixstatic.com/media/[id]/v1/fill/w_[w],h_[h],q_[q],...
- static.wixstatic.com/media/[id]~mv2.jpg (original)
- static.wixstatic.com/media/[id].jpg

Transform parameters:
- w_[width] - target width
- h_[height] - target height  
- q_[quality] - quality (1-100)
- al_c - alignment center
- usm_0.66_1.00_0.01 - unsharp mask
- enc_avif - encoding format (avif, webp, jpg, png)
"""

from site_handlers.base_handler import BaseSiteHandler
from urllib.parse import urljoin, urlparse, parse_qs, urlencode
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


class WixHandler(BaseSiteHandler):
    """
    Handler for Wix-powered websites.
    
    Wix sites use static.wixstatic.com for image hosting with URL-based
    image transformations. This handler extracts images and upgrades
    them to maximum resolution.
    """

    # Patterns to identify Wix sites
    WIX_PATTERNS = [
        r'wixstatic\.com',
        r'wix\.com',
        r'wixsite\.com',
        r'_wix_',
        r'wix-code',
    ]
    
    # Known Wix-powered domains (model agencies, portfolios, etc.)
    KNOWN_WIX_DOMAINS = [
        r'new1mgmt\.com',
        r'modelwerk\.de',
        r'nextmodels\.com',
        # Add more known Wix sites as discovered
    ]

    @classmethod
    def can_handle(cls, url):
        """Check if this handler can process the URL"""
        url_lower = url.lower()
        
        # Check for known Wix domains
        for pattern in cls.KNOWN_WIX_DOMAINS:
            if re.search(pattern, url_lower, re.IGNORECASE):
                print(f"WixHandler can handle: {url} (known Wix domain: {pattern})")
                return True
        
        # Check for Wix patterns in URL
        for pattern in cls.WIX_PATTERNS:
            if re.search(pattern, url_lower, re.IGNORECASE):
                print(f"WixHandler can handle: {url} (matched pattern: {pattern})")
                return True
        
        return False

    def __init__(self, url, scraper=None):
        """Initialize the Wix handler"""
        super().__init__(url, scraper)
        self.debug_mode = True
        self.seen_urls = set()
        self.seen_base_ids = set()  # Track base image IDs to avoid duplicates
        print(f"WixHandler initialized for URL: {url}")

    def prefers_api(self):
        """This handler doesn't use APIs"""
        return False

    def requires_api(self):
        """This handler doesn't require API access"""
        return False

    async def extract_media_items_async(self, page):
        """
        Extract media items from Wix-powered pages.
        """
        print(f"WixHandler: Extracting media from {self.url}")
        start_time = time.time()
        media_items = []
        
        # Get the Playwright page
        pw_page = await self._get_playwright_page_async(page)
        if not pw_page:
            print("No Playwright page available")
            return []
        
        try:
            # Wait for the page to fully load
            await pw_page.wait_for_load_state('networkidle', timeout=20000)
            
            # Give extra time for Wix's lazy loading
            await pw_page.wait_for_timeout(2000)
            
            # Scroll to trigger lazy loading
            await self._scroll_page(pw_page)
            
            # Extract images from multiple sources
            media_items = await self._extract_wix_images(pw_page)
            
            # Extract videos from the page
            video_items = await self._extract_wix_videos(pw_page)
            media_items.extend(video_items)
            
            # Also try to get images from network requests
            network_images = await self._extract_from_page_resources(pw_page)
            
            # Merge and deduplicate
            for item in network_images:
                base_id = self._extract_wix_image_id(item.get('url', ''))
                if base_id and base_id not in self.seen_base_ids:
                    self.seen_base_ids.add(base_id)
                    media_items.append(item)
            
        except Exception as e:
            print(f"WixHandler error: {e}")
            traceback.print_exc()
        
        print(f"WixHandler: Extracted {len(media_items)} media items in {time.time() - start_time:.2f}s")
        return media_items

    async def _scroll_page(self, pw_page):
        """Scroll the page to trigger lazy loading"""
        try:
            # Get page height
            scroll_height = await pw_page.evaluate('document.body.scrollHeight')
            viewport_height = await pw_page.evaluate('window.innerHeight')
            
            # Scroll in increments
            current_position = 0
            scroll_step = viewport_height * 0.8
            
            while current_position < scroll_height:
                current_position += scroll_step
                await pw_page.evaluate(f'window.scrollTo(0, {current_position})')
                await pw_page.wait_for_timeout(500)
                
                # Check if height increased (more content loaded)
                new_height = await pw_page.evaluate('document.body.scrollHeight')
                if new_height > scroll_height:
                    scroll_height = new_height
            
            # Scroll back to top
            await pw_page.evaluate('window.scrollTo(0, 0)')
            await pw_page.wait_for_timeout(500)
            
        except Exception as e:
            print(f"Error scrolling page: {e}")

    async def _extract_wix_videos(self, pw_page):
        """
        Extract videos from Wix-powered pages.
        
        Wix videos are hosted at video.wixstatic.com with this pattern:
        - https://video.wixstatic.com/video/{video_id}/1080p/mp4/file.mp4
        
        Video IDs can be found from:
        1. Direct video src attributes
        2. Gallery items marked as video (poster images with 'f003' suffix)
        3. Data attributes in gallery containers
        """
        media_items = []
        seen_video_ids = set()
        
        try:
            # Extract video data from the page
            video_data = await pw_page.evaluate('''
                () => {
                    const results = {
                        directVideos: [],
                        galleryVideos: [],
                        videoContainers: []
                    };
                    
                    // 1. Get ALL video elements - check multiple src attributes
                    const videos = document.querySelectorAll('video');
                    for (const video of videos) {
                        // Check multiple possible source attributes
                        let src = video.src || video.currentSrc || '';
                        const poster = video.poster || '';
                        
                        // Also check source child elements
                        if (!src) {
                            const sourceEl = video.querySelector('source');
                            if (sourceEl) src = sourceEl.src || '';
                        }
                        
                        // Any wixstatic video URL (including video.wixstatic.com)
                        if (src && (src.includes('wixstatic.com') || src.includes('wix.com'))) {
                            results.directVideos.push({
                                src: src,
                                poster: poster,
                                type: 'direct',
                                className: video.className
                            });
                        }
                        // Poster images can help identify video IDs
                        if (poster && poster.includes('wixstatic')) {
                            results.directVideos.push({
                                poster: poster,
                                type: 'poster_reference'
                            });
                        }
                    }
                    
                    // 2. Get gallery items marked as videos
                    const galleryVideoItems = document.querySelectorAll('[class*="gallery-item-video"]');
                    for (const item of galleryVideoItems) {
                        const img = item.querySelector('img');
                        const video = item.querySelector('video');
                        
                        // Get poster/thumbnail image which contains the video ID
                        if (img && img.src && img.src.includes('wixstatic')) {
                            // Video poster images typically end with f003 or f000
                            const src = img.src;
                            results.galleryVideos.push({
                                posterSrc: src,
                                hasVideoElement: !!video,
                                type: 'gallery_video'
                            });
                        }
                    }
                    
                    // 3. Look for video containers with data attributes
                    const videoContainers = document.querySelectorAll('[class*="video"]');
                    for (const container of videoContainers) {
                        const videoEl = container.querySelector('video[src*="video.wixstatic"]');
                        if (videoEl) {
                            results.videoContainers.push({
                                src: videoEl.src,
                                type: 'container'
                            });
                        }
                    }
                    
                    return results;
                }
            ''')
            
            print(f"WixHandler: Found {len(video_data.get('directVideos', []))} direct videos, "
                  f"{len(video_data.get('galleryVideos', []))} gallery videos, "
                  f"{len(video_data.get('videoContainers', []))} container videos")
            
            # Process direct videos (already have full URLs)
            for vid in video_data.get('directVideos', []):
                src = vid.get('src', '')
                print(f"WixHandler: Processing direct video - src: {src[:100] if src else 'None'}...")
                
                # Check for any wixstatic video URL
                if src and ('video.wixstatic.com' in src or 'wixstatic.com' in src):
                    video_id = self._extract_wix_video_id(src)
                    print(f"WixHandler: Extracted video ID: {video_id}")
                    
                    if video_id and video_id not in seen_video_ids:
                        seen_video_ids.add(video_id)
                        # Upgrade to 1080p if not already
                        full_url = self._upgrade_wix_video_url(src)
                        print(f"WixHandler: Upgraded video URL to: {full_url}")
                        media_items.append({
                            'url': full_url,
                            'original_url': src,
                            'type': 'video',
                            'poster': vid.get('poster', ''),
                            'source': 'wix_handler_video',
                            'page_url': self.url,  # For Referer header
                            'qualities': {
                                '1080p': f"https://video.wixstatic.com/video/{video_id}/1080p/mp4/file.mp4",
                                '720p': f"https://video.wixstatic.com/video/{video_id}/720p/mp4/file.mp4",
                                '480p': f"https://video.wixstatic.com/video/{video_id}/480p/mp4/file.mp4"
                            }
                        })
            
            # Process gallery videos (construct URLs from poster images)
            for vid in video_data.get('galleryVideos', []):
                poster_src = vid.get('posterSrc', '')
                if poster_src:
                    video_id = self._extract_video_id_from_poster(poster_src)
                    if video_id and video_id not in seen_video_ids:
                        seen_video_ids.add(video_id)
                        # Construct direct MP4 URL
                        video_url = f"https://video.wixstatic.com/video/{video_id}/1080p/mp4/file.mp4"
                        media_items.append({
                            'url': video_url,
                            'type': 'video',
                            'poster': poster_src,
                            'source': 'wix_handler_gallery_video',
                            'page_url': self.url,  # For Referer header
                            'qualities': {
                                '1080p': f"https://video.wixstatic.com/video/{video_id}/1080p/mp4/file.mp4",
                                '720p': f"https://video.wixstatic.com/video/{video_id}/720p/mp4/file.mp4",
                                '480p': f"https://video.wixstatic.com/video/{video_id}/480p/mp4/file.mp4"
                            }
                        })
                        print(f"WixHandler: Constructed video URL for ID {video_id}")
            
            # Process video containers
            for vid in video_data.get('videoContainers', []):
                src = vid.get('src', '')
                if src and 'video.wixstatic.com' in src:
                    video_id = self._extract_wix_video_id(src)
                    if video_id and video_id not in seen_video_ids:
                        seen_video_ids.add(video_id)
                        full_url = self._upgrade_wix_video_url(src)
                        media_items.append({
                            'url': full_url,
                            'original_url': src,
                            'type': 'video',
                            'source': 'wix_handler_container_video'
                        })
            
        except Exception as e:
            print(f"Error extracting Wix videos: {e}")
            traceback.print_exc()
        
        print(f"WixHandler: Extracted {len(media_items)} videos")
        return media_items

    def _extract_wix_video_id(self, url):
        """Extract video ID from a Wix video URL"""
        if not url:
            return None
        
        # Pattern: video.wixstatic.com/video/{video_id}/quality/mp4/file.mp4
        # Example: video.wixstatic.com/video/b52b2f_19e70a48dd054abfb015bb2598c1ff8d/1080p/mp4/file.mp4
        match = re.search(r'video\.wixstatic\.com/video/([a-f0-9]+_[a-f0-9]+)', url)
        if match:
            return match.group(1)
        return None

    def _extract_video_id_from_poster(self, poster_url):
        """
        Extract video ID from a poster image URL.
        
        Poster images have patterns like:
        - b52b2f_0a5d15df38dc4c08a18238b03b87082af003.jpg (f003 suffix = poster frame)
        - The video ID is the part before 'f003' or 'f000'
        """
        if not poster_url:
            return None
        
        # Pattern: media/{id}f003.jpg or media/{id}f000.jpg
        # We need to strip the f00X suffix to get the video ID
        patterns = [
            # Match ID with frame suffix (f003, f000, etc.)
            r'/media/([a-f0-9]+_[a-f0-9]+?)f\d{3}(?:~mv2)?\.(?:jpg|jpeg|png|webp)',
            r'/media/([a-f0-9]+_[a-f0-9]+?)f\d{3}\.(?:jpg|jpeg|png|webp)',
            # Direct ID pattern
            r'/media/([a-f0-9]+_[a-f0-9]{32})',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, poster_url, re.IGNORECASE)
            if match:
                video_id = match.group(1)
                # Clean up any trailing frame indicator
                video_id = re.sub(r'f\d{3}$', '', video_id)
                return video_id
        
        return None

    def _upgrade_wix_video_url(self, url):
        """Upgrade video URL to highest quality (1080p)"""
        if not url:
            return url
        
        # Replace quality specifier with 1080p
        upgraded = re.sub(r'/\d{3,4}p/', '/1080p/', url)
        return upgraded

    async def _extract_wix_images(self, pw_page):
        """Extract and upgrade Wix images from the page"""
        media_items = []
        
        try:
            # Get all images with their sources
            images = await pw_page.evaluate('''
                () => {
                    const results = [];
                    
                    // Get all img elements
                    const imgs = document.querySelectorAll('img');
                    for (const img of imgs) {
                        const src = img.src || img.dataset.src || img.getAttribute('data-src') || '';
                        const srcset = img.srcset || '';
                        
                        if (src) {
                            results.push({
                                src: src,
                                srcset: srcset,
                                alt: img.alt || '',
                                width: img.naturalWidth || img.width || 0,
                                height: img.naturalHeight || img.height || 0
                            });
                        }
                    }
                    
                    // Also check for background images in styles
                    const allElements = document.querySelectorAll('*');
                    for (const el of allElements) {
                        const style = window.getComputedStyle(el);
                        const bgImage = style.backgroundImage;
                        if (bgImage && bgImage !== 'none' && bgImage.includes('wixstatic')) {
                            const match = bgImage.match(/url\\(["']?([^"']+)["']?\\)/);
                            if (match) {
                                results.push({
                                    src: match[1],
                                    srcset: '',
                                    alt: '',
                                    width: 0,
                                    height: 0,
                                    isBackground: true
                                });
                            }
                        }
                    }
                    
                    // Check for Wix gallery data
                    const galleryData = document.querySelectorAll('[data-image-info]');
                    for (const el of galleryData) {
                        try {
                            const info = JSON.parse(el.getAttribute('data-image-info'));
                            if (info && info.imageData && info.imageData.uri) {
                                results.push({
                                    src: 'https://static.wixstatic.com/media/' + info.imageData.uri,
                                    srcset: '',
                                    alt: info.imageData.title || '',
                                    width: info.imageData.width || 0,
                                    height: info.imageData.height || 0,
                                    fromGalleryData: true
                                });
                            }
                        } catch (e) {}
                    }
                    
                    return results;
                }
            ''')
            
            print(f"WixHandler: Found {len(images)} image elements")
            
            for img_data in images:
                src = img_data.get('src', '')
                srcset = img_data.get('srcset', '')
                
                # Skip non-wix images and tracking pixels
                if not src:
                    continue
                if 'wixstatic' not in src and 'wix.com' not in src:
                    continue
                if img_data.get('width', 0) > 0 and img_data.get('width', 0) < 50:
                    continue
                
                # Extract base image ID
                base_id = self._extract_wix_image_id(src)
                if not base_id:
                    continue
                    
                # Skip if we've already processed this image
                if base_id in self.seen_base_ids:
                    continue
                self.seen_base_ids.add(base_id)
                
                # Try to get highest resolution from srcset first
                best_url = self._get_best_from_srcset(srcset) if srcset else None
                
                # Upgrade to maximum resolution
                if best_url:
                    full_res_url = self._upgrade_wix_url(best_url)
                else:
                    full_res_url = self._upgrade_wix_url(src)
                
                if full_res_url in self.seen_urls:
                    continue
                self.seen_urls.add(full_res_url)
                
                media_item = {
                    'url': full_res_url,
                    'original_url': src,
                    'type': 'image',
                    'alt_text': img_data.get('alt', ''),
                    'source': 'wix_handler',
                    'original_width': img_data.get('width', 0),
                    'original_height': img_data.get('height', 0)
                }
                media_items.append(media_item)
            
        except Exception as e:
            print(f"Error extracting Wix images: {e}")
            traceback.print_exc()
        
        return media_items

    def _extract_wix_image_id(self, url):
        """Extract the base image ID from a Wix URL"""
        if not url:
            return None
            
        # Pattern: /media/[id]_[hash]~mv2.jpg or /media/[id].jpg
        # Example: b52b2f_1f9ee9ba5e6c4b4792257297be983580~mv2.jpg
        patterns = [
            r'/media/([a-f0-9]+_[a-f0-9]+[^/]*?)(?:/v1/|\.(?:jpg|jpeg|png|webp|gif))',
            r'/media/([a-f0-9]+_[^/]+?)(?:~mv2)?\.(?:jpg|jpeg|png|webp|gif)',
            r'/media/([a-f0-9_]+)(?:/|~|\.)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url, re.IGNORECASE)
            if match:
                return match.group(1)
        
        return None

    def _get_best_from_srcset(self, srcset):
        """Parse srcset and return the highest resolution URL"""
        if not srcset:
            return None
            
        best_url = None
        best_width = 0
        
        # Parse srcset: "url1 800w, url2 1200w, ..."
        parts = srcset.split(',')
        for part in parts:
            part = part.strip()
            match = re.match(r'(\S+)\s+(\d+)w', part)
            if match:
                url, width = match.groups()
                width = int(width)
                if width > best_width:
                    best_width = width
                    best_url = url
        
        return best_url

    def _upgrade_wix_url(self, url):
        """
        Upgrade a Wix image URL to maximum resolution.
        
        Strategies:
        1. Request original by removing transforms
        2. Request very large dimensions
        3. Change quality to maximum
        """
        if not url:
            return url
            
        # If it's already an original URL (no /v1/fill/ or /v1/fit/), return as-is
        if '/v1/fill/' not in url and '/v1/crop/' not in url and '/v1/fit/' not in url:
            # Try to ensure we get the raw image
            return url
        
        try:
            # Extract the base media URL and transform it
            # Pattern: https://static.wixstatic.com/media/[id]/v1/fill/w_X,h_Y,.../filename.ext
            # Or: https://static.wixstatic.com/media/[id]/v1/fit/w_X,h_Y,.../filename.ext
            
            # Strategy 1: Request maximum resolution (4K+)
            # Replace dimension parameters with large values
            upgraded = url
            
            # Replace width with large value (Wix typically supports up to 5000)
            upgraded = re.sub(r'w_\d+', 'w_4000', upgraded)
            
            # Replace height with large value
            upgraded = re.sub(r'h_\d+', 'h_5000', upgraded)
            
            # Set quality to maximum (90 is usually best balance, 100 can cause issues)
            upgraded = re.sub(r'q_\d+', 'q_95', upgraded)
            
            # Change fit to fill for better quality (fit may letterbox)
            # Actually keep as-is since fit respects aspect ratio
            
            # Prefer JPEG over AVIF/WebP for better compatibility and quality
            upgraded = re.sub(r'enc_avif', 'enc_auto', upgraded)
            upgraded = re.sub(r'enc_webp', 'enc_auto', upgraded)
            
            # Remove quality_auto which adds compression
            upgraded = re.sub(r',quality_auto', '', upgraded)
            
            print(f"WixHandler: Upgraded URL dimensions to 4000x5000")
            
            return upgraded
            
        except Exception as e:
            print(f"Error upgrading Wix URL: {e}")
            return url

    async def _extract_from_page_resources(self, pw_page):
        """Extract images from page resources/network requests"""
        media_items = []
        
        try:
            # Get all loaded resources
            resources = await pw_page.evaluate('''
                () => {
                    const resources = [];
                    
                    // Check performance entries for loaded resources
                    if (window.performance && window.performance.getEntriesByType) {
                        const entries = window.performance.getEntriesByType('resource');
                        for (const entry of entries) {
                            if (entry.initiatorType === 'img' || 
                                entry.name.match(/\\.(jpg|jpeg|png|webp|gif|avif)/i)) {
                                resources.push(entry.name);
                            }
                        }
                    }
                    
                    return resources;
                }
            ''')
            
            for url in resources:
                if 'wixstatic' not in url:
                    continue
                    
                base_id = self._extract_wix_image_id(url)
                if not base_id or base_id in self.seen_base_ids:
                    continue
                
                full_res_url = self._upgrade_wix_url(url)
                
                if full_res_url not in self.seen_urls:
                    self.seen_urls.add(full_res_url)
                    media_items.append({
                        'url': full_res_url,
                        'original_url': url,
                        'type': 'image',
                        'source': 'wix_handler_network'
                    })
            
        except Exception as e:
            print(f"Error extracting from page resources: {e}")
        
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

    async def extract_with_direct_playwright(self, page, **kwargs):
        """Direct Playwright extraction method called by the scraper"""
        return await self.extract_media_items_async(page)
