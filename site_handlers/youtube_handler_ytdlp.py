"""
Youtube Handler Ytdlp

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
Enhanced YouTube Handler using yt-dlp
Supports downloading actual video/audio files and comprehensive metadata extraction
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


class YouTubeHandlerYtDlp(BaseSiteHandler):
    """
    Enhanced YouTube Handler using yt-dlp library
    Supports actual video/audio downloads and comprehensive metadata
    """
    
    PRIORITY = 40  # Higher priority than basic YouTube handler
    
    @classmethod
    def can_handle(cls, url: str) -> bool:
        """Check if this handler can process the URL"""
        return ("youtube.com" in url.lower() or "youtu.be" in url.lower()) and YT_DLP_AVAILABLE
    
    def __init__(self, url, scraper=None):
        super().__init__(url, scraper)
        
        # Configuration - can be overridden by scraper settings
        self.download_videos = getattr(scraper, 'download_videos', True) if scraper else True
        self.download_audio = getattr(scraper, 'download_audio', False) if scraper else False
        self.max_quality = getattr(scraper, 'max_video_quality', '1080p') if scraper else '1080p'
        self.max_playlist_items = getattr(scraper, 'max_playlist_items', 50) if scraper else 50
        
        # Extract URL info
        self.video_id = None
        self.playlist_id = None  
        self.channel_id = None
        self.url_type = self._parse_youtube_url(url)
        
        # yt-dlp options
        self.ydl_opts = self._get_ydl_options()
    
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
        """Main extraction method using yt-dlp"""
        try:
            print(f"🎬 Starting yt-dlp YouTube extraction for: {self.url_type['type']}")
            
            # Override options based on kwargs
            download_videos = kwargs.get('download_videos', self.download_videos)
            download_audio = kwargs.get('download_audio', self.download_audio)
            
            # Update yt-dlp options
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
            return []
    
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
