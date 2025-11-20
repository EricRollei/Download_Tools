"""
Youtube Handler

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
Enhanced YouTube Handler with yt-dlp support
Consolidates basic Playwright functionality with yt-dlp capabilities
"""

import os
import json
import asyncio
import tempfile
from typing import List, Dict, Optional, Any
from urllib.parse import urlparse, parse_qs
from site_handlers.base_handler import BaseSiteHandler

try:
    import yt_dlp
    YT_DLP_AVAILABLE = True
except ImportError:
    YT_DLP_AVAILABLE = False
    print("yt-dlp not available. Install with: pip install yt-dlp")
    # Create a dummy class for type hints when yt-dlp is not available
    class yt_dlp:
        class YoutubeDL:
            pass


class YouTubeHandler(BaseSiteHandler):
    """
    Enhanced YouTube Handler supporting both yt-dlp and Playwright
    Handles authentication, age restrictions, and comprehensive content extraction
    """
    
    PRIORITY = 5  # High priority
    
    @classmethod
    def can_handle(cls, url):
        """Check if this handler can process the URL."""
        return "youtube.com" in url.lower() or "youtu.be" in url.lower()
    
    def get_trusted_domains(self):
        """Return list of trusted CDN domains for YouTube"""
        return [
            "ytimg.com",           # YouTube thumbnails
            "ggpht.com",          # YouTube profile images  
            "youtube.com",        # Main domain
            "youtu.be",          # Short URLs
            "googlevideo.com",   # Video streams
            "googleusercontent.com"  # Various Google CDN content
        ]
    
    def __init__(self, url, scraper=None):
        super().__init__(url, scraper)
        
        # Configuration - can be overridden by scraper settings
        self.download_videos = getattr(scraper, 'download_videos', False) if scraper else False
        self.download_audio = getattr(scraper, 'download_audio', False) if scraper else False
        self.max_quality = getattr(scraper, 'max_video_quality', '1080p') if scraper else '1080p'
        self.max_playlist_items = getattr(scraper, 'max_playlist_items', 50) if scraper else 50
        
        # URL parsing
        self.video_id = None
        self.playlist_id = None  
        self.channel_id = None
        self.page_type = self._determine_page_type(url)
        self.url_type = self._parse_youtube_url(url)
        
        # Authentication
        self.auth_credentials = None
        self._load_auth_credentials()
        
        # yt-dlp options
        self.ydl_opts = self._get_ydl_options() if YT_DLP_AVAILABLE else None
    
    def _determine_page_type(self, url):
        """Determine what type of YouTube page we're dealing with."""
        parsed_url = urlparse(url)
        path = parsed_url.path
        
        if "/watch" in path:
            return "video"
        elif "/channel/" in path or "/c/" in path or "/user/" in path or "/@" in path:
            return "channel"
        elif "/playlist" in path:
            return "playlist"
        else:
            return "other"
    
    def _parse_youtube_url(self, url: str) -> Dict[str, Any]:
        """Parse YouTube URL to extract type and identifiers"""
        try:
            parsed = urlparse(url)
            query_params = parse_qs(parsed.query)
            
            result = {
                'type': 'unknown',
                'video_id': None,
                'playlist_id': None,
                'channel_id': None,
                'channel_handle': None
            }
            
            # Extract video ID
            if 'watch' in parsed.path and 'v' in query_params:
                result['type'] = 'video'
                result['video_id'] = query_params['v'][0]
                self.video_id = result['video_id']
                
                # Check if it's part of a playlist
                if 'list' in query_params:
                    result['playlist_id'] = query_params['list'][0]
                    self.playlist_id = result['playlist_id']
                    
            elif 'youtu.be' in parsed.netloc:
                result['type'] = 'video'
                result['video_id'] = parsed.path.strip('/')
                self.video_id = result['video_id']
                
            elif 'playlist' in parsed.path and 'list' in query_params:
                result['type'] = 'playlist'
                result['playlist_id'] = query_params['list'][0]
                self.playlist_id = result['playlist_id']
                
            elif any(x in parsed.path for x in ['/channel/', '/c/', '/user/', '/@']):
                result['type'] = 'channel'
                # Extract channel info from path
                path_parts = [p for p in parsed.path.split('/') if p]
                if len(path_parts) >= 2:
                    if path_parts[0] == 'channel':
                        result['channel_id'] = path_parts[1]
                        self.channel_id = result['channel_id']
                    elif path_parts[0] in ['c', 'user'] or parsed.path.startswith('/@'):
                        result['channel_handle'] = path_parts[1] if path_parts[0] != '@' else path_parts[0][1:]
            
            return result
            
        except Exception as e:
            print(f"Error parsing YouTube URL: {e}")
            return {'type': 'unknown'}
    
    def _get_ydl_options(self) -> Dict[str, Any]:
        """Get yt-dlp options based on configuration"""
        opts = {
            'quiet': False,
            'no_warnings': False,
            'extract_flat': False,
            'writeinfojson': True,
            'writethumbnail': True,
            'writesubtitles': False,
            'writeautomaticsub': False,
            'ignoreerrors': True,
        }
        
        # Quality settings
        if self.download_videos:
            if self.max_quality == '4K':
                opts['format'] = 'best[height<=2160]'
            elif self.max_quality == '1080p':
                opts['format'] = 'best[height<=1080]'
            elif self.max_quality == '720p':
                opts['format'] = 'best[height<=720]'
            else:
                opts['format'] = 'best'
        elif self.download_audio:
            opts['format'] = 'bestaudio/best'
        else:
            # Just extract metadata and thumbnails
            opts['skip_download'] = True
        
        # Playlist limits
        if self.url_type.get('type') in ['playlist', 'channel']:
            opts['playlistend'] = self.max_playlist_items
        
        return opts
    
    async def extract_with_direct_playwright(self, page=None, **kwargs) -> List[Dict]:
        """Main extraction method - tries yt-dlp first, falls back to Playwright"""
        
        # Override options based on kwargs
        download_videos = kwargs.get('download_videos', self.download_videos)
        download_audio = kwargs.get('download_audio', self.download_audio)
        
        # Try yt-dlp first if available and we want downloads or enhanced metadata
        if YT_DLP_AVAILABLE and (download_videos or download_audio or kwargs.get('use_ytdlp', True)):
            try:
                print(f"🎬 Using yt-dlp for YouTube extraction: {self.url_type['type']}")
                return await self._extract_with_ytdlp(**kwargs)
            except Exception as e:
                print(f"⚠ yt-dlp extraction failed, falling back to Playwright: {e}")
        
        # Fallback to Playwright extraction
        if page:
            print(f"📱 Using Playwright fallback for YouTube extraction: {self.page_type}")
            return await self._extract_with_playwright(page, **kwargs)
        else:
            print("❌ No page provided for Playwright fallback")
            return []
    
    async def _extract_with_ytdlp(self, **kwargs) -> List[Dict]:
        """Extract content using yt-dlp"""
        try:
            # Update yt-dlp options based on kwargs
            download_videos = kwargs.get('download_videos', self.download_videos)
            download_audio = kwargs.get('download_audio', self.download_audio)
            
            if not download_videos and not download_audio:
                self.ydl_opts['skip_download'] = True
            else:
                self.ydl_opts.pop('skip_download', None)
            
            # Create temporary directory for downloads
            with tempfile.TemporaryDirectory() as temp_dir:
                self.ydl_opts['outtmpl'] = os.path.join(temp_dir, '%(title)s.%(ext)s')
                
                # Extract content using yt-dlp
                media_items = []
                
                with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                    # Extract info without downloading first
                    info = ydl.extract_info(self.url, download=False)
                    
                    if info:
                        media_items = await self._process_yt_dlp_info(info, ydl, temp_dir, **kwargs)
                
                print(f"✅ yt-dlp extraction complete: {len(media_items)} items found")
                return media_items
                
        except Exception as e:
            print(f"❌ Error in yt-dlp extraction: {e}")
            raise
    
    async def _process_yt_dlp_info(self, info: Dict, ydl: yt_dlp.YoutubeDL, temp_dir: str, **kwargs) -> List[Dict]:
        """Process yt-dlp extracted info into media items"""
        media_items = []
        
        try:
            # Handle different content types
            if info.get('_type') == 'playlist':
                # Process playlist entries
                print(f"📋 Processing playlist with {len(info.get('entries', []))} entries")
                
                for entry in info.get('entries', []):
                    if entry:
                        entry_items = await self._process_single_video_info(entry, ydl, temp_dir, **kwargs)
                        media_items.extend(entry_items)
                        
            else:
                # Single video
                print(f"🎥 Processing single video: {info.get('title', 'Unknown')}")
                entry_items = await self._process_single_video_info(info, ydl, temp_dir, **kwargs)
                media_items.extend(entry_items)
        
        except Exception as e:
            print(f"Error processing yt-dlp info: {e}")
        
        return media_items
    
    async def _process_single_video_info(self, info: Dict, ydl: yt_dlp.YoutubeDL, temp_dir: str, **kwargs) -> List[Dict]:
        """Process a single video's info into media items"""
        media_items = []
        
        try:
            video_id = info.get('id', '')
            title = info.get('title', 'Unknown Video')
            uploader = info.get('uploader', '')
            duration = info.get('duration', 0)
            view_count = info.get('view_count', 0)
            description = info.get('description', '')
            upload_date = info.get('upload_date', '')
            
            # Create base metadata
            base_metadata = {
                'title': title,
                'uploader': uploader,
                'duration': duration,
                'view_count': view_count,
                'description': description[:500] if description else '',  # Truncate long descriptions
                'upload_date': upload_date,
                'video_id': video_id,
                'source_url': f"https://www.youtube.com/watch?v={video_id}",
                'extraction_method': 'yt-dlp'
            }
            
            # Add thumbnail
            thumbnail_url = info.get('thumbnail')
            if thumbnail_url:
                media_items.append({
                    'url': thumbnail_url,
                    'type': 'image',
                    'title': f"Thumbnail: {title}",
                    'alt': title,
                    'credits': f"YouTube: {uploader}",
                    'category': 'youtube_thumbnail',
                    'trusted_cdn': True,  # YouTube thumbnails are trusted
                    **base_metadata
                })
            
            # Add video file if downloading
            if kwargs.get('download_videos', self.download_videos) and not self.ydl_opts.get('skip_download'):
                # Download the video
                video_path = await self._download_video(info, ydl, temp_dir)
                if video_path and os.path.exists(video_path):
                    media_items.append({
                        'url': video_path,  # Local file path
                        'type': 'video',
                        'title': title,
                        'credits': f"YouTube: {uploader}",
                        'file_size': os.path.getsize(video_path),
                        'local_file': True,
                        'trusted_cdn': True,
                        **base_metadata
                    })
            
            # Add audio file if downloading audio
            if kwargs.get('download_audio', self.download_audio):
                audio_path = await self._download_audio(info, ydl, temp_dir)
                if audio_path and os.path.exists(audio_path):
                    media_items.append({
                        'url': audio_path,  # Local file path
                        'type': 'audio',
                        'title': f"Audio: {title}",
                        'credits': f"YouTube: {uploader}",
                        'file_size': os.path.getsize(audio_path),
                        'local_file': True,
                        'trusted_cdn': True,
                        **base_metadata
                    })
            
            # If not downloading files, create a reference item
            if self.ydl_opts.get('skip_download'):
                media_items.append({
                    'url': f"https://www.youtube.com/watch?v={video_id}",
                    'type': 'youtube_video',
                    'title': title,
                    'credits': f"YouTube: {uploader}",
                    'trusted_cdn': True,
                    **base_metadata
                })
        
        except Exception as e:
            print(f"Error processing single video info: {e}")
        
        return media_items
    
    async def _download_video(self, info: Dict, ydl: yt_dlp.YoutubeDL, temp_dir: str) -> Optional[str]:
        """Download video file using yt-dlp"""
        try:
            # Create a new ydl instance for video download
            video_opts = self.ydl_opts.copy()
            video_opts['outtmpl'] = os.path.join(temp_dir, f"video_{info['id']}.%(ext)s")
            
            with yt_dlp.YoutubeDL(video_opts) as video_ydl:
                video_ydl.download([info['webpage_url']])
                
                # Find the downloaded file
                for file in os.listdir(temp_dir):
                    if file.startswith(f"video_{info['id']}"):
                        return os.path.join(temp_dir, file)
        
        except Exception as e:
            print(f"Error downloading video: {e}")
        
        return None
    
    async def _download_audio(self, info: Dict, ydl: yt_dlp.YoutubeDL, temp_dir: str) -> Optional[str]:
        """Download audio file using yt-dlp"""
        try:
            # Create a new ydl instance for audio download
            audio_opts = self.ydl_opts.copy()
            audio_opts['format'] = 'bestaudio/best'
            audio_opts['outtmpl'] = os.path.join(temp_dir, f"audio_{info['id']}.%(ext)s")
            
            with yt_dlp.YoutubeDL(audio_opts) as audio_ydl:
                audio_ydl.download([info['webpage_url']])
                
                # Find the downloaded file
                for file in os.listdir(temp_dir):
                    if file.startswith(f"audio_{info['id']}"):
                        return os.path.join(temp_dir, file)
        
        except Exception as e:
            print(f"Error downloading audio: {e}")
        
        return None
    
    async def _extract_with_playwright(self, page, **kwargs) -> List[Dict]:
        """Fallback Playwright extraction with authentication support"""
        media_items = []
        
        try:
            print(f"Extracting YouTube content: {self.page_type}")
            
            # Apply authentication BEFORE navigating to the video
            if self.auth_credentials:
                print("Applying YouTube authentication...")
                await self._apply_authentication(page)
            else:
                print("No YouTube authentication configured")
            
            if self.page_type == "video":
                return await self._extract_video_playwright(page, **kwargs)
            elif self.page_type == "channel":
                return await self._extract_channel_playwright(page, **kwargs)
            elif self.page_type == "playlist":
                return await self._extract_playlist_playwright(page, **kwargs)
            else:
                return await self._extract_generic_playwright(page, **kwargs)
                
        except Exception as e:
            print(f"Error in Playwright extraction: {e}")
            return []
    
    async def _extract_video_playwright(self, page, **kwargs):
        """Extract a single YouTube video using Playwright."""
        media_items = []
        
        try:
            # If we applied cookies, we're already on YouTube, navigate to the specific video
            if self.auth_credentials and self.auth_credentials.get('auth_type') == 'cookie':
                print(f"Navigating to video: {self.url}")
                await page.goto(self.url, timeout=30000)
            
            # Accept cookies if needed
            await self._handle_consent(page)
            
            # Check for age restriction
            age_restricted = await self._check_age_restriction(page)
            if age_restricted:
                print("Handled age-restricted content")
            
            # Wait for page to load properly
            await page.wait_for_load_state('networkidle', timeout=15000)
            
            # Check if we hit an age restriction page
            if await page.query_selector('text="Sign in to confirm your age"') or await page.query_selector('[data-testid="age-gate"]'):
                print("⚠ Age restriction detected - authentication may be needed")
            
            # Extract video metadata
            video_data = await self._extract_video_metadata(page)
            
            # Create video reference item
            if video_data and self.video_id:
                media_items.append({
                    'url': f"https://www.youtube.com/watch?v={self.video_id}",
                    'title': video_data.get('title', ''),
                    'alt': video_data.get('title', ''),
                    'credits': f"YouTube: {video_data.get('channel', '')}",
                    'source_url': self.url,
                    'type': 'youtube_video',
                    'video_id': self.video_id,
                    'metadata': video_data,
                    'trusted_cdn': True,
                    'extraction_method': 'playwright'
                })
            
            # Try to get thumbnail image
            if self.video_id:
                # YouTube thumbnails follow a consistent pattern
                thumbnail_url = f"https://i.ytimg.com/vi/{self.video_id}/maxresdefault.jpg"
                
                media_items.append({
                    'url': thumbnail_url,
                    'title': f"Thumbnail: {video_data.get('title', '')}",
                    'alt': video_data.get('title', ''),
                    'credits': f"YouTube: {video_data.get('channel', '')}",
                    'source_url': self.url,
                    'type': 'image',
                    'category': 'youtube_thumbnail',
                    'trusted_cdn': True,  # YouTube thumbnails are from trusted CDN
                    'extraction_method': 'playwright'
                })
                
        except Exception as e:
            print(f"Error extracting YouTube video: {e}")
        
        return media_items
    
    async def _extract_channel_playwright(self, page, **kwargs):
        """Extract videos from a YouTube channel using Playwright."""
        # Basic implementation - could be expanded
        return []
    
    async def _extract_playlist_playwright(self, page, **kwargs):
        """Extract videos from a YouTube playlist using Playwright."""
        # Basic implementation - could be expanded  
        return []
        
    async def _extract_generic_playwright(self, page, **kwargs):
        """Extract from other YouTube pages using Playwright."""
        # Basic implementation - could be expanded
        return []
    
    async def _extract_video_metadata(self, page):
        """Extract video metadata from the page."""
        try:
            video_data = {}
            
            # Extract title
            title_element = await page.query_selector('h1.title .style-scope.ytd-video-primary-info-renderer')
            if not title_element:
                title_element = await page.query_selector('[data-testid="title"]')
            if not title_element:
                title_element = await page.query_selector('h1')
            
            if title_element:
                video_data['title'] = await title_element.text_content()
            
            # Extract channel name
            channel_element = await page.query_selector('a.yt-simple-endpoint.style-scope.yt-formatted-string')
            if not channel_element:
                channel_element = await page.query_selector('.owner-name a')
            
            if channel_element:
                video_data['channel'] = await channel_element.text_content()
                video_data['channelUrl'] = await channel_element.get_attribute('href')
                if video_data['channelUrl'] and not video_data['channelUrl'].startswith('http'):
                    video_data['channelUrl'] = 'https://www.youtube.com' + video_data['channelUrl']
            
            # Extract view count
            views_element = await page.query_selector('.view-count')
            if not views_element:
                views_element = await page.query_selector('[aria-label*="views"]')
                
            if views_element:
                views_text = await views_element.text_content()
                video_data['views'] = views_text.strip() if views_text else ''
            
            print(f"YouTube video metadata: {video_data}")
            return video_data
            
        except Exception as e:
            print(f"Error extracting video metadata: {e}")
            return {}
    
    def _load_auth_credentials(self):
        """Load authentication credentials if available."""
        # Check if scraper has auth config
        if hasattr(self.scraper, 'auth_config') and self.scraper.auth_config:
            domain_key = 'youtube.com'
            self.auth_credentials = self.scraper.auth_config.get(domain_key)
            
            if self.auth_credentials:
                print(f"Loaded YouTube authentication credentials for {domain_key}")
        
        # Also check for API credentials
        self._load_api_credentials()
    
    def _load_api_credentials(self):
        """Load API credentials for YouTube API access."""
        print("--- DEBUG: _load_api_credentials called for YouTubeHandler ---")
        
        if hasattr(self.scraper, 'auth_config') and self.scraper.auth_config:
            youtube_config = self.scraper.auth_config.get('youtube.com', {})
            print(f"  DEBUG: Looking for credentials for domain: youtube.com")
            
            if youtube_config:
                print(f"  DEBUG: Found credentials for youtube.com: {list(youtube_config.keys())}")
                
                # Check if API key is available
                api_key = youtube_config.get('api_key')
                if api_key:
                    self.api_key = api_key
                    print(f"  DEBUG: API key found: {api_key[:10]}...")
                    print(f"  DEBUG: API available: True")
                else:
                    print(f"  DEBUG: API available: False")
            else:
                print(f"  DEBUG: No credentials found for youtube.com")
                print(f"  DEBUG: API available: False")
        else:
            print(f"  DEBUG: No auth config available")
            print(f"  DEBUG: API available: False")
    
    async def _apply_authentication(self, page):
        """Apply authentication (cookies or login)."""
        if not self.auth_credentials:
            return
            
        auth_type = self.auth_credentials.get('auth_type', '')
        
        if auth_type == 'cookie':
            await self._apply_cookies(page)
        elif auth_type == 'login':
            await self._perform_login(page)
    
    async def _apply_cookies(self, page):
        """Apply YouTube session cookies."""
        try:
            cookies = self.auth_credentials.get('cookies', [])
            if not cookies:
                print("No cookies to apply")
                return
                
            print(f"Applying {len(cookies)} YouTube cookies...")
            
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
            
            # Navigate to YouTube to activate cookies
            print("Navigating to YouTube to activate cookies...")
            await page.goto("https://www.youtube.com", timeout=30000)
            await page.wait_for_timeout(2000)
            
            # Check if logged in
            if await page.query_selector('[aria-label*="Account menu"]') or await page.query_selector('#avatar-btn'):
                print("✓ Successfully logged in with cookies")
            else:
                print("⚠ Cookies applied but login status unclear")
                
        except Exception as e:
            print(f"Error applying YouTube cookies: {e}")
    
    async def _perform_login(self, page):
        """Perform username/password login to YouTube."""
        try:
            username = self.auth_credentials.get('username', '')
            password = self.auth_credentials.get('password', '')
            
            if not username or password:
                print("Username or password not provided")
                return
            
            print("Performing YouTube login...")
            
            # Navigate to Google login
            await page.goto("https://accounts.google.com/signin", timeout=30000)
            
            # Fill username
            username_field = await page.wait_for_selector('input[type="email"]', timeout=10000)
            await username_field.fill(username)
            await page.click('button:has-text("Next")')
            
            # Fill password
            password_field = await page.wait_for_selector('input[type="password"]', timeout=10000)
            await password_field.fill(password)
            await page.click('button:has-text("Next")')
            
            # Wait for login to complete
            await page.wait_for_timeout(3000)
            
            print("YouTube login completed")
            
        except Exception as e:
            print(f"YouTube login failed: {e}")
    
    async def _handle_consent(self, page):
        """Handle YouTube consent/cookie dialogs."""
        try:
            # Look for consent dialog
            consent_button = await page.query_selector('button:has-text("Accept")')
            if not consent_button:
                consent_button = await page.query_selector('button:has-text("I agree")')
            if not consent_button:
                consent_button = await page.query_selector('[aria-label*="Accept"]')
                
            if consent_button:
                await consent_button.click()
                await page.wait_for_timeout(2000)
                print("Handled consent dialog")
            else:
                print("No consent dialog found or already handled")
                
        except Exception as e:
            print(f"Error handling consent: {e}")
    
    async def _check_age_restriction(self, page):
        """Check if content is age-restricted and handle accordingly."""
        try:
            # Look for age restriction indicators
            age_restricted_selectors = [
                '[data-testid="age-gate"]',
                '.age-gate',
                ':has-text("Sign in to confirm your age")',
                ':has-text("This video may be inappropriate")',
                ':has-text("Age-restricted video")'
            ]
            
            for selector in age_restricted_selectors:
                if await page.query_selector(selector):
                    print("Age-restricted content detected")
                    
                    # Try to click "I understand and wish to proceed"
                    proceed_button = await page.query_selector('button:has-text("I understand")')
                    if proceed_button:
                        await proceed_button.click()
                        await page.wait_for_timeout(2000)
                        return True
                        
            return False
        except Exception as e:
            print(f"Error checking age restriction: {e}")
            return False