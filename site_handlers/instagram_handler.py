"""
Instagram Handler

Description: Instagram-specific scraping handler with authentication and optimization support
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
- Uses Playwright (Apache 2.0) for browser automation: https://github.com/microsoft/playwright
- See CREDITS.md for complete list of all dependencies
"""

"""
Instagram Handler using Instaloader library
Handles Instagram profiles, posts, stories, reels, and IGTV content.
"""

import os
import re
import time
import json
import asyncio
import traceback
from typing import List, Dict, Optional, Any
from urllib.parse import urlparse, parse_qs
from datetime import datetime

try:
    import instaloader
    INSTALOADER_AVAILABLE = True
except ImportError:
    INSTALOADER_AVAILABLE = False
    print("Instaloader not available. Install with: pip install instaloader")

from .base_handler import BaseSiteHandler


class InstagramHandler(BaseSiteHandler):
    """Handler for Instagram URLs using Instaloader library"""
    
    @classmethod
    def can_handle(cls, url: str) -> bool:
        """Check if this handler can process the given URL"""
        return "instagram.com" in url.lower() and INSTALOADER_AVAILABLE
    
    def __init__(self, url, scraper=None):
        super().__init__(url, scraper)
        
        # Configuration - can be overridden by scraper settings
        self.max_posts = getattr(scraper, 'max_posts', 200) if scraper else 200
        self.download_videos = True
        self.download_stories = True  # Stories enabled with authentication
        self.download_highlights = True  # Highlights enabled with authentication
        self.download_tagged = False  # Tagged posts
        
        # Instaloader instance
        self.loader = None
        self.session_file = None
        
        # State tracking
        self.processed_items = set()
        self.download_dir = None
    
    def get_trusted_domains(self):
        """Return list of trusted CDN domains for Instagram"""
        return [
            "scontent-lhr8-1.cdninstagram.com",
            "scontent-lhr8-2.cdninstagram.com", 
            "scontent.cdninstagram.com",
            "scontent.fbcdn.net",
            "scontent-lhr.xx.fbcdn.net",
            "instagram.com",
            "cdninstagram.com",
            "fbcdn.net"
        ]
        
    def _initialize_instaloader(self) -> bool:
        """Initialize Instaloader with optimal settings"""
        try:
            if not INSTALOADER_AVAILABLE:
                print("❌ Instaloader library not available. Install with: pip install instaloader")
                return False
                
            # Create Instaloader instance with optimized settings
            self.loader = instaloader.Instaloader(
                # Download settings
                download_videos=self.download_videos,
                download_video_thumbnails=False,
                download_geotags=True,
                download_comments=False,
                save_metadata=True,
                compress_json=True,
                
                # Filename template
                filename_pattern='{target}_{shortcode}_{date_utc:%Y%m%d_%H%M%S}',
                
                # Behavior settings
                sleep=True,  # Respect rate limits
                max_connection_attempts=5,  # Increased attempts
                request_timeout=45,  # Longer timeout
                
                # Avoid detection
                user_agent='Instagram 219.0.0.12.117 Android',
                resume_prefix=None,
            )
            
            # Try to load session if available
            self._load_session()
            
            print("✅ Instaloader initialized successfully")
            return True
            
        except Exception as e:
            print(f"❌ Error initializing Instaloader: {e}")
            return False
    
    def _load_session(self) -> bool:
        """Load existing Instagram session if available"""
        try:
            # Check for session file in auth config
            auth_config = self._load_auth_config()
            if not auth_config:
                return False
                
            instagram_config = auth_config.get('instagram.com', {})
            auth_type = instagram_config.get('authentication_type', 'session')
            
            # Handle cookie-based authentication
            if auth_type == 'cookies':
                return self._setup_cookie_authentication(instagram_config)
            
            # Handle session-based authentication
            username = instagram_config.get('username')
            session_file = instagram_config.get('session_file')
            
            if username and session_file and os.path.exists(session_file):
                print(f"📁 Loading session for user: {username}")
                self.loader.load_session_from_file(username, session_file)
                print("✅ Session loaded successfully")
                return True
            elif username:
                print(f"👤 Username configured: {username} (no session file)")
                
        except Exception as e:
            print(f"⚠️  Could not load session: {e}")
            
        return False
    
    def _setup_cookie_authentication(self, instagram_config: Dict) -> bool:
        """Setup authentication using browser cookies"""
        try:
            cookies = instagram_config.get('cookies', [])
            user_id = instagram_config.get('user_id')
            
            if not cookies:
                print("⚠️  No cookies found in configuration")
                return False
            
            print(f"🍪 Setting up cookie authentication for user ID: {user_id}")
            
            # Create a requests session with cookies for Instaloader
            import requests
            session = requests.Session()
            
            # Add cookies to session
            for cookie in cookies:
                session.cookies.set(
                    name=cookie['name'],
                    value=cookie['value'],
                    domain=cookie.get('domain', '.instagram.com'),
                    path=cookie.get('path', '/'),
                    secure=cookie.get('secure', True)
                )
            
            # Set the session in Instaloader context
            # This is a bit tricky as Instaloader manages its own session
            # We'll use a hybrid approach
            
            # Try to extract username from ds_user_id cookie
            username = None
            ds_user_id = user_id
            
            if ds_user_id:
                # Create a temporary session file with the cookie data
                self._create_session_from_cookies(ds_user_id, cookies)
                print(f"✅ Cookie authentication setup complete for user {ds_user_id}")
                return True
            else:
                print("⚠️  Could not extract user ID from cookies")
                return False
                
        except Exception as e:
            print(f"❌ Error setting up cookie authentication: {e}")
            return False
    
    def _create_session_from_cookies(self, user_id: str, cookies: List[Dict]) -> None:
        """Create Instaloader session from browser cookies"""
        try:
            # Extract essential cookies for Instagram authentication
            essential_cookies = {}
            
            for cookie in cookies:
                name = cookie['name']
                value = cookie['value']
                
                # Map important Instagram cookies
                if name == 'sessionid':
                    essential_cookies['sessionid'] = value
                elif name == 'csrftoken':
                    essential_cookies['csrftoken'] = value
                elif name == 'ds_user_id':
                    essential_cookies['ds_user_id'] = value
                elif name == 'rur':
                    essential_cookies['rur'] = value
            
            # Set up Instaloader with cookie session
            # This requires some internal Instaloader session manipulation
            if hasattr(self.loader, 'context') and essential_cookies.get('sessionid'):
                # Try to set the session directly
                try:
                    # Access Instaloader's internal session
                    self.loader.context._session.cookies.update(essential_cookies)
                    self.loader.context.username = user_id  # Use user_id as identifier
                    print("🔧 Applied cookies to Instaloader session")
                except Exception as inner_e:
                    print(f"⚠️  Could not apply cookies directly: {inner_e}")
                    # Fallback: continue without cookie integration
            
            print(f"💾 Session created for user ID: {user_id}")
            
        except Exception as e:
            print(f"⚠️  Error creating session from cookies: {e}")
    
    async def _extract_with_playwright_cookies(self, page) -> List[Dict]:
        """Extract Instagram content using Playwright with cookie authentication"""
        try:
            print("🎭 Starting Playwright-based Instagram extraction")
            
            # Apply cookies to page
            await self._apply_instagram_cookies(page)
            
            # Navigate to URL
            await page.goto(self.url, wait_until='networkidle')
            await asyncio.sleep(2)
            
            # Parse URL to determine extraction method
            url_info = self._parse_instagram_url(self.url)
            
            media_items = []
            if url_info['type'] == 'profile':
                media_items = await self._playwright_extract_profile(page, url_info['username'])
            elif url_info['type'] in ['post', 'reel']:
                media_items = await self._playwright_extract_post(page)
            elif url_info['type'] == 'story':
                media_items = await self._playwright_extract_story(page)
            else:
                print(f"⚠️  Playwright extraction not implemented for type: {url_info['type']}")
                return []
            
            # Post-process to add trusted_cdn flag for Instagram CDN URLs
            for item in media_items:
                url = item.get('url', '')
                if any(domain in url for domain in ['cdninstagram.com', 'fbcdn.net', 'scontent']):
                    item['trusted_cdn'] = True
            
            return media_items
                
        except Exception as e:
            print(f"❌ Error in Playwright extraction: {e}")
            return []
    
    async def _apply_instagram_cookies(self, page) -> None:
        """Apply Instagram cookies to Playwright page"""
        try:
            auth_config = self._load_auth_config()
            if not auth_config:
                return
                
            instagram_config = auth_config.get('instagram.com', {})
            cookies = instagram_config.get('cookies', [])
            
            if not cookies:
                return
            
            print(f"🍪 Applying {len(cookies)} cookies to Playwright page")
            
            # Convert cookies to Playwright format
            playwright_cookies = []
            for cookie in cookies:
                playwright_cookie = {
                    'name': cookie['name'],
                    'value': cookie['value'],
                    'domain': cookie.get('domain', '.instagram.com'),
                    'path': cookie.get('path', '/'),
                    'secure': cookie.get('secure', True),
                    'httpOnly': cookie.get('httpOnly', False)
                }
                playwright_cookies.append(playwright_cookie)
            
            # Add cookies to page context
            await page.context.add_cookies(playwright_cookies)
            print("✅ Cookies applied successfully")
            
        except Exception as e:
            print(f"⚠️  Error applying cookies: {e}")
    
    async def _playwright_extract_profile(self, page, username: str) -> List[Dict]:
        """Extract profile content using Playwright"""
        try:
            print(f"👤 Extracting profile with Playwright: {username}")
            
            # Wait for page to load
            await page.wait_for_selector('article', timeout=10000)
            
            # Scroll to load more content
            await self._playwright_scroll_profile(page)
            
            # Extract image/video URLs
            media_items = []
            
            # Look for post links
            post_links = await page.query_selector_all('a[href*="/p/"]')
            print(f"📸 Found {len(post_links)} post links")
            
            for i, link in enumerate(post_links[:self.max_posts]):
                try:
                    href = await link.get_attribute('href')
                    if href and '/p/' in href:
                        # Extract shortcode from URL
                        shortcode = href.split('/p/')[-1].split('/')[0]
                        
                        # Find associated image
                        img = await link.query_selector('img')
                        if img:
                            src = await img.get_attribute('src')
                            alt = await img.get_attribute('alt')
                            
                            if src:
                                media_item = {
                                    'url': src,
                                    'type': 'image',
                                    'title': f"Post by {username}",
                                    'description': alt or '',
                                    'username': username,
                                    'shortcode': shortcode,
                                    'source_url': f"https://www.instagram.com{href}",
                                    'extraction_method': 'playwright_cookies',
                                    'timestamp': None,  # Would need additional parsing
                                    'likes': None,
                                    'comments': None
                                }
                                media_items.append(media_item)
                                
                    # Rate limiting
                    if i % 10 == 0 and i > 0:
                        await asyncio.sleep(1)
                        
                except Exception as e:
                    print(f"⚠️  Error processing post link {i}: {e}")
                    continue
            
            print(f"✅ Playwright profile extraction complete: {len(media_items)} items")
            return media_items
            
        except Exception as e:
            print(f"❌ Error in Playwright profile extraction: {e}")
            return []
    
    async def _playwright_extract_post(self, page) -> List[Dict]:
        """Extract single post using Playwright"""
        try:
            print("📸 Extracting single post with Playwright")
            
            # Wait for main image/video
            await page.wait_for_selector('article img, article video', timeout=10000)
            
            media_items = []
            
            # Look for images
            images = await page.query_selector_all('article img')
            for img in images:
                src = await img.get_attribute('src')
                alt = await img.get_attribute('alt')
                
                if src and 'instagram.com' in src:
                    media_item = {
                        'url': src,
                        'type': 'image',
                        'title': 'Instagram post',
                        'description': alt or '',
                        'source_url': self.url,
                        'extraction_method': 'playwright_cookies'
                    }
                    media_items.append(media_item)
            
            # Look for videos
            videos = await page.query_selector_all('article video')
            for video in videos:
                src = await video.get_attribute('src')
                
                if src:
                    media_item = {
                        'url': src,
                        'type': 'video',
                        'title': 'Instagram video',
                        'description': '',
                        'source_url': self.url,
                        'extraction_method': 'playwright_cookies'
                    }
                    media_items.append(media_item)
            
            print(f"✅ Playwright post extraction complete: {len(media_items)} items")
            return media_items
            
        except Exception as e:
            print(f"❌ Error in Playwright post extraction: {e}")
            return []
    
    async def _playwright_extract_story(self, page) -> List[Dict]:
        """Extract story using Playwright"""
        try:
            print("📱 Extracting story with Playwright")
            
            # Stories require more complex handling
            # This is a basic implementation
            await page.wait_for_selector('[data-testid="story-viewer"]', timeout=10000)
            
            # Look for story media
            media_items = []
            
            # Stories are typically in video or img elements within the story viewer
            media_elements = await page.query_selector_all('[data-testid="story-viewer"] img, [data-testid="story-viewer"] video')
            
            for element in media_elements:
                src = await element.get_attribute('src')
                tag_name = await element.evaluate('el => el.tagName.toLowerCase()')
                
                if src:
                    media_item = {
                        'url': src,
                        'type': 'video' if tag_name == 'video' else 'image',
                        'title': 'Instagram story',
                        'description': '',
                        'source_url': self.url,
                        'extraction_method': 'playwright_cookies',
                        'is_story': True
                    }
                    media_items.append(media_item)
            
            print(f"✅ Playwright story extraction complete: {len(media_items)} items")
            return media_items
            
        except Exception as e:
            print(f"❌ Error in Playwright story extraction: {e}")
            return []
    
    async def _playwright_scroll_profile(self, page) -> None:
        """Scroll profile page to load more content"""
        try:
            print("📜 Scrolling to load more content")
            
            for i in range(5):  # Scroll 5 times
                await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                await asyncio.sleep(2)
                
                # Check if load more button exists and click it
                load_more = await page.query_selector('button:has-text("Load more")')
                if load_more:
                    await load_more.click()
                    await asyncio.sleep(2)
            
        except Exception as e:
            print(f"⚠️  Error during scrolling: {e}")
    
    def _save_session(self, username: str) -> None:
        """Save current session for future use"""
        try:
            if not username or not self.loader:
                return
                
            # Create session directory
            session_dir = os.path.join(os.path.dirname(__file__), '..', 'configs', 'sessions')
            os.makedirs(session_dir, exist_ok=True)
            
            session_file = os.path.join(session_dir, f'instagram_{username}.session')
            self.loader.save_session_to_file(session_file)
            
            print(f"💾 Session saved to: {session_file}")
            
            # Update auth config with session file path
            self._update_auth_config_session(username, session_file)
            
        except Exception as e:
            print(f"⚠️  Could not save session: {e}")
    
    def _update_auth_config_session(self, username: str, session_file: str) -> None:
        """Update auth config with session file path"""
        try:
            config_path = os.path.join(os.path.dirname(__file__), '..', 'configs', 'auth_config.json')
            
            # Load existing config
            auth_config = {}
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    auth_config = json.load(f)
            
            # Update Instagram section
            if 'instagram.com' not in auth_config:
                auth_config['instagram.com'] = {}
                
            auth_config['instagram.com'].update({
                'username': username,
                'session_file': session_file,
                'authentication_type': 'session'
            })
            
            # Save updated config
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(auth_config, f, indent=2)
                
        except Exception as e:
            print(f"⚠️  Could not update auth config: {e}")
    
    def _parse_instagram_url(self, url: str) -> Dict[str, Any]:
        """Parse Instagram URL to determine content type and target"""
        try:
            parsed = urlparse(url)
            path_parts = [p for p in parsed.path.split('/') if p]
            
            result = {
                'type': 'unknown',
                'username': None,
                'shortcode': None,
                'reel_id': None,
                'story_id': None,
                'highlight_id': None,
                'hashtag': None
            }
            
            if not path_parts:
                return result
            
            # Profile URLs: instagram.com/username/
            if len(path_parts) == 1 and not path_parts[0].startswith(('p', 'reel', 'stories', 'explore')):
                result['type'] = 'profile'
                result['username'] = path_parts[0]
                
            # Post URLs: instagram.com/p/shortcode/
            elif len(path_parts) >= 2 and path_parts[0] == 'p':
                result['type'] = 'post'
                result['shortcode'] = path_parts[1]
                
            # Reel URLs: instagram.com/reel/shortcode/
            elif len(path_parts) >= 2 and path_parts[0] == 'reel':
                result['type'] = 'reel'
                result['shortcode'] = path_parts[1]
                
            # Stories: instagram.com/stories/username/story_id
            elif len(path_parts) >= 3 and path_parts[0] == 'stories':
                result['type'] = 'story'
                result['username'] = path_parts[1]
                result['story_id'] = path_parts[2] if len(path_parts) > 2 else None
                
            # Hashtag: instagram.com/explore/tags/hashtag/
            elif len(path_parts) >= 3 and path_parts[0] == 'explore' and path_parts[1] == 'tags':
                result['type'] = 'hashtag'
                result['hashtag'] = path_parts[2]
                
            # Profile with section: instagram.com/username/tagged/ etc.
            elif len(path_parts) >= 2:
                result['username'] = path_parts[0]
                section = path_parts[1]
                
                if section == 'tagged':
                    result['type'] = 'profile_tagged'
                elif section == 'reels':
                    result['type'] = 'profile_reels'
                else:
                    result['type'] = 'profile'
            
            return result
            
        except Exception as e:
            print(f"Error parsing Instagram URL: {e}")
            return {'type': 'unknown'}
    
    async def extract_with_direct_playwright(self, page=None, **kwargs) -> List[Dict]:
        """Main extraction method using Instaloader with Playwright fallback"""
        try:
            print("🔄 Starting Instagram extraction...")
            
            # Check authentication method
            auth_config = self._load_auth_config()
            instagram_config = auth_config.get('instagram.com', {}) if auth_config else {}
            auth_type = instagram_config.get('authentication_type', 'session')
            
            # For cookie authentication, try Playwright approach first
            if auth_type == 'cookies' and page:
                print("🍪 Using cookie-based Playwright extraction")
                media_items = await self._extract_with_playwright_cookies(page)
                if media_items:
                    return media_items
                print("⚠️  Playwright extraction failed, falling back to Instaloader")
            
            # Use Instaloader approach
            print("📚 Using Instaloader extraction")
            
            # Initialize Instaloader
            if not self._initialize_instaloader():
                print("❌ Instaloader initialization failed")
                return []
            
            # Parse URL to determine what to download
            url_info = self._parse_instagram_url(self.url)
            print(f"📋 Detected content type: {url_info['type']}")
            
            media_items = []
            
            # Route to appropriate extraction method
            if url_info['type'] == 'profile':
                media_items = await self._extract_profile(url_info['username'])
            elif url_info['type'] == 'profile_tagged':
                media_items = await self._extract_profile_tagged(url_info['username'])
            elif url_info['type'] == 'profile_reels':
                media_items = await self._extract_profile_reels(url_info['username'])
            elif url_info['type'] in ['post', 'reel']:
                media_items = await self._extract_single_post(url_info['shortcode'])
            elif url_info['type'] == 'story':
                media_items = await self._extract_story(url_info['username'], url_info['story_id'])
            elif url_info['type'] == 'hashtag':
                media_items = await self._extract_hashtag(url_info['hashtag'])
            else:
                print(f"❌ Unsupported Instagram URL type: {url_info['type']}")
                return []
            
            print(f"✅ Instagram extraction complete: {len(media_items)} items found")
            
            # Post-process to add trusted_cdn flag for Instagram CDN URLs
            for item in media_items:
                url = item.get('url', '')
                if any(domain in url for domain in ['cdninstagram.com', 'fbcdn.net', 'scontent']):
                    item['trusted_cdn'] = True
            
            return media_items
            
        except Exception as e:
            print(f"❌ Error in Instagram extraction: {e}")
            traceback.print_exc()
            return []
    
    async def _extract_profile(self, username: str) -> List[Dict]:
        """Extract posts from an Instagram profile"""
        try:
            print(f"👤 Extracting profile: {username}")
            
            # Get profile
            profile = instaloader.Profile.from_username(self.loader.context, username)
            
            print(f"📊 Profile info: {profile.full_name} (@{profile.username})")
            print(f"📝 Bio: {profile.biography[:100]}..." if profile.biography else "📝 No bio")
            print(f"📸 Posts: {profile.mediacount}")
            print(f"👥 Followers: {profile.followers}")
            
            media_items = []
            post_count = 0
            
            # Iterate through posts
            for post in profile.get_posts():
                if post_count >= self.max_posts:
                    print(f"⏹️  Reached maximum posts limit: {self.max_posts}")
                    break
                
                try:
                    item = await self._process_post(post, username)
                    if item:
                        media_items.append(item)
                        
                    post_count += 1
                    
                    # Progress update
                    if post_count % 10 == 0:
                        print(f"📥 Processed {post_count} posts...")
                        
                    # Rate limiting - faster but still respectful
                    await asyncio.sleep(0.5)
                    
                except Exception as e:
                    print(f"⚠️  Error processing post {post.shortcode}: {e}")
                    continue
            
            # Extract stories if enabled and authenticated
            if self.download_stories and self.loader.context.is_logged_in:
                try:
                    print("📱 Extracting stories...")
                    story_items = await self._extract_stories(username)
                    media_items.extend(story_items)
                    print(f"✅ Added {len(story_items)} stories")
                except Exception as e:
                    print(f"⚠️  Error extracting stories: {e}")
            
            # Extract highlights if enabled and authenticated
            if self.download_highlights and self.loader.context.is_logged_in:
                try:
                    print("⭐ Extracting highlights...")
                    highlight_items = await self._extract_highlights(username)
                    media_items.extend(highlight_items)
                    print(f"✅ Added {len(highlight_items)} highlights")
                except Exception as e:
                    print(f"⚠️  Error extracting highlights: {e}")

            return media_items
            
        except Exception as e:
            print(f"❌ Error extracting profile {username}: {e}")
            return []
    
    async def _extract_single_post(self, shortcode: str) -> List[Dict]:
        """Extract a single Instagram post/reel"""
        try:
            print(f"📸 Extracting single post: {shortcode}")
            
            # Get post
            post = instaloader.Post.from_shortcode(self.loader.context, shortcode)
            
            item = await self._process_post(post)
            return [item] if item else []
            
        except Exception as e:
            print(f"❌ Error extracting post {shortcode}: {e}")
            return []
    
    async def _extract_profile_tagged(self, username: str) -> List[Dict]:
        """Extract tagged posts from a profile"""
        try:
            print(f"🏷️  Extracting tagged posts for: {username}")
            
            if not self.download_tagged:
                print("⏭️  Tagged posts download disabled")
                return []
            
            profile = instaloader.Profile.from_username(self.loader.context, username)
            media_items = []
            
            for post in profile.get_tagged_posts():
                item = await self._process_post(post, username)
                if item:
                    media_items.append(item)
                
                # Rate limiting
                await asyncio.sleep(1)
            
            return media_items
            
        except Exception as e:
            print(f"❌ Error extracting tagged posts for {username}: {e}")
            return []
    
    async def _extract_profile_reels(self, username: str) -> List[Dict]:
        """Extract reels from a profile"""
        try:
            print(f"🎬 Extracting reels for: {username}")
            
            profile = instaloader.Profile.from_username(self.loader.context, username)
            media_items = []
            
            # Note: Instaloader doesn't have a specific method for reels only
            # We'll filter regular posts for video content
            for post in profile.get_posts():
                if post.is_video:
                    item = await self._process_post(post, username)
                    if item:
                        media_items.append(item)
                
                # Rate limiting
                await asyncio.sleep(1)
            
            return media_items
            
        except Exception as e:
            print(f"❌ Error extracting reels for {username}: {e}")
            return []
    
    async def _extract_story(self, username: str, story_id: str = None) -> List[Dict]:
        """Extract Instagram stories (requires login)"""
        try:
            print(f"📱 Extracting stories for: {username}")
            
            if not self.download_stories:
                print("⏭️  Stories download disabled")
                return []
            
            # Stories require authentication
            if not self.loader.context.is_logged_in:
                print("🔐 Stories require login - please configure authentication")
                return []
            
            profile = instaloader.Profile.from_username(self.loader.context, username)
            media_items = []
            
            # Get stories
            for story in self.loader.get_stories([profile.userid]):
                for item in story.get_items():
                    processed_item = await self._process_story_item(item, username)
                    if processed_item:
                        media_items.append(processed_item)
            
            return media_items
            
        except Exception as e:
            print(f"❌ Error extracting stories for {username}: {e}")
            return []
    
    async def _extract_highlights(self, username: str) -> List[Dict]:
        """Extract highlights from a profile"""
        try:
            print(f"⭐ Extracting highlights for: {username}")
            
            # Highlights require authentication
            if not self.loader.context.is_logged_in:
                print("🔐 Highlights require login - please configure authentication")
                return []
            
            profile = instaloader.Profile.from_username(self.loader.context, username)
            media_items = []
            
            # Get highlights - Instaloader doesn't have direct highlight support
            # We'll use a workaround to get highlights via story highlights
            try:
                # This is a more advanced feature that might need additional implementation
                # For now, we'll provide a placeholder that can be enhanced later
                print("⚠️  Highlight extraction requires additional Instagram API access")
                print("🔄 This feature will be enhanced in future updates")
                return []
                
            except Exception as e:
                print(f"⚠️  Highlights extraction not fully implemented yet: {e}")
                return []
            
        except Exception as e:
            print(f"❌ Error extracting highlights for {username}: {e}")
            return []
    
    async def _extract_hashtag(self, hashtag: str) -> List[Dict]:
        """Extract posts from a hashtag"""
        try:
            print(f"#️⃣ Extracting hashtag: #{hashtag}")
            
            # Get hashtag
            hashtag_obj = instaloader.Hashtag.from_name(self.loader.context, hashtag)
            
            print(f"📊 Hashtag #{hashtag}: {hashtag_obj.mediacount} posts")
            
            media_items = []
            post_count = 0
            
            # Get top posts from hashtag
            for post in hashtag_obj.get_posts():
                if post_count >= self.max_posts:
                    break
                
                item = await self._process_post(post, f"hashtag_{hashtag}")
                if item:
                    media_items.append(item)
                
                post_count += 1
                
                # Rate limiting
                await asyncio.sleep(2)  # Slower for hashtags
            
            return media_items
            
        except Exception as e:
            print(f"❌ Error extracting hashtag #{hashtag}: {e}")
            return []
    
    async def _process_post(self, post, source_username: str = None) -> Optional[Dict]:
        """Process an individual Instagram post into media item format"""
        try:
            # Skip if already processed
            if post.shortcode in self.processed_items:
                return None
            
            self.processed_items.add(post.shortcode)
            
            # Determine media type
            if post.is_video:
                media_type = 'video'
                url = post.video_url
            else:
                media_type = 'image'
                url = post.url
            
            # Extract metadata with improved error handling
            try:
                location_name = None
                try:
                    if hasattr(post, 'location') and post.location:
                        location_name = post.location.name
                except Exception as location_error:
                    # Silently handle location access errors (common Instagram API issue)
                    pass
                
                media_item = {
                    'url': url,
                    'type': media_type,
                    'title': self._get_post_title(post),
                    'description': post.caption if post.caption else "",
                    'username': post.owner_username,
                    'full_name': post.owner_profile.full_name if hasattr(post.owner_profile, 'full_name') else "",
                    'shortcode': post.shortcode,
                    'timestamp': post.date_utc.isoformat() if post.date_utc else None,
                    'likes': post.likes,
                    'comments': post.comments,
                    'is_video': post.is_video,
                    'width': getattr(post, 'dimensions', {}).get('width', 0),
                    'height': getattr(post, 'dimensions', {}).get('height', 0),
                    'hashtags': list(post.caption_hashtags) if post.caption_hashtags else [],
                    'mentions': list(post.caption_mentions) if post.caption_mentions else [],
                    'location': location_name,
                    'source_url': f"https://www.instagram.com/p/{post.shortcode}/",
                    'source_username': source_username,
                    'extraction_method': 'instaloader'
                }
            except Exception as metadata_error:
                print(f"⚠️  Error extracting metadata for {post.shortcode}: {metadata_error}")
                # Create minimal metadata if full extraction fails
                media_item = {
                    'url': url,
                    'type': media_type,
                    'title': f"Instagram Post {post.shortcode}",
                    'description': "",
                    'username': getattr(post, 'owner_username', 'unknown'),
                    'shortcode': post.shortcode,
                    'source_url': f"https://www.instagram.com/p/{post.shortcode}/",
                    'extraction_method': 'instaloader'
                }
            
            # Handle carousel posts (multiple images/videos)
            if post.typename == 'GraphSidecar':
                media_item['is_carousel'] = True
                media_item['carousel_count'] = post.mediacount
                
                # For carousel, we'll create separate items for each media
                # This is the first item, others will be processed separately
            
            print(f"  📎 {media_type.title()}: {media_item['title'][:50]}... ({post.shortcode})")
            
            return media_item
            
        except Exception as e:
            print(f"⚠️  Error processing post: {e}")
            return None
    
    async def _process_story_item(self, story_item, username: str) -> Optional[Dict]:
        """Process an Instagram story item"""
        try:
            # Determine media type
            if story_item.is_video:
                media_type = 'video'
                url = story_item.video_url
            else:
                media_type = 'image'
                url = story_item.url
            
            media_item = {
                'url': url,
                'type': media_type,
                'title': f"Story by {username}",
                'description': "",
                'username': username,
                'timestamp': story_item.date_utc.isoformat() if story_item.date_utc else None,
                'is_video': story_item.is_video,
                'is_story': True,
                'story_id': getattr(story_item, 'mediaid', None),
                'source_url': f"https://www.instagram.com/stories/{username}/",
                'extraction_method': 'instaloader'
            }
            
            return media_item
            
        except Exception as e:
            print(f"⚠️  Error processing story item: {e}")
            return None
    
    def _get_post_title(self, post) -> str:
        """Generate a title for the post"""
        try:
            # Try to get a meaningful title from caption
            if post.caption:
                # Take first line or first 50 characters
                title = post.caption.split('\n')[0][:50].strip()
                if title:
                    return title
            
            # Fallback to post type and username
            post_type = "Video" if post.is_video else "Photo"
            return f"{post_type} by {post.owner_username}"
            
        except:
            return f"Instagram post {post.shortcode}"
    
    def _load_auth_config(self) -> Optional[Dict]:
        """Load authentication configuration"""
        try:
            config_path = os.path.join(os.path.dirname(__file__), '..', 'configs', 'auth_config.json')
            
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    
                # Check if config has 'sites' key (new format)
                if 'sites' in config:
                    return config['sites']
                else:
                    # Assume old format where sites are at root level
                    return config
                    
        except Exception as e:
            print(f"Could not load auth config: {e}")
        
        return None
