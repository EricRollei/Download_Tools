"""
Bsky Handler

Description: Bluesky social media scraping handler with profile and media extraction
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
- Uses Scrapling (Apache 2.0) for content extraction: https://github.com/D4Vinci/Scrapling
- See CREDITS.md for complete list of all dependencies
"""

"""
Bluesky (bsky.app) specific handler for the Web Image Scraper
"""

from site_handlers.base_handler import BaseSiteHandler
from urllib.parse import urlparse
import re
import time
import traceback
import asyncio
from concurrent.futures import ThreadPoolExecutor


# Safe import for atproto
try:
    from atproto import Client, models
    ATPROTO_AVAILABLE = True
except ImportError:
    Client = None
    models = None
    ATPROTO_AVAILABLE = False
    print("Warning: atproto library not found. Bluesky handler will be limited.")

# Safe import for Playwright types
try:
    from playwright.async_api import Page as AsyncPage
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    AsyncPage = None
    PLAYWRIGHT_AVAILABLE = False

class BskyHandler(BaseSiteHandler):
    """
    Handler for Bluesky (bsky.app).
    Uses the atproto library to fetch posts and images via the API.
    Supports profiles, individual posts, and hashtags.
    """
    # Expanded regex to identify various Bluesky patterns
    BSKY_URL_PATTERN = re.compile(r"https?://(?:www\.)?bsky\.app/(?:profile/([^/]+)(?:/post/([^/]+))?|hashtag/([^/?#]+))")
    
    # Pattern for simple usernames or hashtags without full URLs
    SIMPLE_PATTERN = re.compile(r"^(@?[a-zA-Z0-9._-]+(?:\.[a-zA-Z0-9._-]+)*|#[a-zA-Z0-9_]+)$")

    def __init__(self, url, scraper=None):
        super().__init__(url, scraper)
        self.profile_did = None
        self.post_id = None
        self.hashtag = None
        self.search_type = None  # 'profile', 'post', 'hashtag'
        self.client = None
        self.api_available = ATPROTO_AVAILABLE # API is available if library is installed
        self.api_authenticated = False
        self.bsky_username = None
        self.bsky_password = None

        self.debug_mode = getattr(scraper, 'debug_mode', False)
        self.max_pages = 3 # Corresponds to fetching multiple feed pages
        self.max_execution_time = 90.0
        self.start_time = time.time()

        self._parse_bsky_url()
        print(f"BskyHandler initialized for URL: {url}. API Available: {self.api_available}")

    @staticmethod
    def can_handle(url):
        """Enhanced URL handling for Bluesky"""
        # Check for full URLs
        if BskyHandler.BSKY_URL_PATTERN.match(url):
            return True
        # Check for simple patterns (usernames, hashtags)
        if BskyHandler.SIMPLE_PATTERN.match(url.strip()):
            return True
        return False

    def _parse_bsky_url(self):
        """Enhanced URL parsing for profiles, posts, and hashtags"""
        # Try full URL pattern first
        match = self.BSKY_URL_PATTERN.match(self.url)
        if match:
            self.profile_did = match.group(1)  # Profile handle
            self.post_id = match.group(2)      # Post ID (if present)
            self.hashtag = match.group(3)      # Hashtag (if present)
            
            if self.hashtag:
                self.search_type = 'hashtag'
                print(f"Parsed Bluesky hashtag URL: #{self.hashtag}")
            elif self.post_id:
                self.search_type = 'post'
                print(f"Parsed Bluesky post URL: Profile={self.profile_did}, Post={self.post_id}")
            else:
                self.search_type = 'profile'
                print(f"Parsed Bluesky profile URL: Profile={self.profile_did}")
        else:
            # Try simple pattern (username or hashtag without full URL)
            simple_match = self.SIMPLE_PATTERN.match(self.url.strip())
            if simple_match:
                text = simple_match.group(1)
                if text.startswith('#'):
                    self.hashtag = text[1:]  # Remove the # symbol
                    self.search_type = 'hashtag'
                    print(f"Parsed simple hashtag: #{self.hashtag}")
                else:
                    # Remove @ if present
                    self.profile_did = text.lstrip('@')
                    self.search_type = 'profile'
                    print(f"Parsed simple profile: {self.profile_did}")
            else:
                print(f"Could not parse Bluesky URL: {self.url}")
                self.search_type = None

    def _load_api_credentials(self):
        """Load API credentials from the scraper's auth config with flexible field mapping."""
        print(">>> Starting _load_api_credentials")
        
        # Initialize API availability as False
        self.api_available = ATPROTO_AVAILABLE  # Base availability on library presence
        
        if not hasattr(self.scraper, 'auth_config') or not self.scraper.auth_config:
            print("BskyHandler: No auth_config found in scraper")
            return False
            
        # Get site config for bsky.app
        site_config = None
        if 'sites' in self.scraper.auth_config:
            for domain in ['bsky.app', 'bsky']:
                if domain in self.scraper.auth_config['sites']:
                    site_config = self.scraper.auth_config['sites'][domain]
                    break
                
        if not site_config:
            print("BskyHandler: No bsky.app configuration found in auth_config")
            return False
            
        # Be flexible about field names - try multiple possibilities
        # For username/handle
        self.bsky_username = (
            site_config.get('username') or 
            site_config.get('handle') or 
            site_config.get('user') or
            site_config.get('email') or
            ''
        )
        
        # For password
        self.bsky_password = (
            site_config.get('password') or 
            site_config.get('app_password') or 
            site_config.get('appPassword') or
            site_config.get('secret') or
            ''
        )
        
        # Store all config values for flexible access
        self.site_config = site_config
        
        # Check if we have the minimum required credentials
        has_creds = bool(self.bsky_username and self.bsky_password)
        
        print(f"Bluesky Credentials Loaded: Username={bool(self.bsky_username)}")
        
        # Only set API available if we have both library and credentials
        self.api_available = ATPROTO_AVAILABLE and has_creds

        print(f">>> Finished _load_api_credentials with username={self.bsky_username[:4] + '...' if self.bsky_username else None}")
        return has_creds

    def _authenticate_api(self):
        """Authenticate with the Bluesky API, ensuring credentials are loaded."""
        print(f">>> Starting _authenticate_api with username={self.bsky_username or None}")
        if not self.api_available or self.api_authenticated:
            return self.api_authenticated

        # If credentials were not loaded earlier, try loading now
        if (not self.bsky_username or not self.bsky_password) and hasattr(self, 'scraper'):
            self._load_api_credentials()

        if not self.bsky_username or not self.bsky_password:
            print("Bluesky username or password missing. Cannot authenticate.")
            return False

        # Proceed with login using atproto Client
        try:
            from atproto import Client
            self.client = Client()
            profile = self.client.login(self.bsky_username, self.bsky_password)
            print(f"Bluesky authentication successful for {profile.handle}")
            self.api_authenticated = True
            return True
        except ImportError:
            print("Error: atproto library not installed. Install with 'pip install atproto'.")
            self.api_available = False
            return False
        except Exception as e:
            print(f"Bluesky authentication failed: {e}")
            traceback.print_exc()
            self.api_authenticated = False
            return False


    async def extract_api_data_async(self, **kwargs):
        """
        Async wrapper that runs the synchronous extract_api_data in a thread so
        ComfyUI's event loop never blocks.
        """
        print("BskyHandler: Starting async API data extraction…")
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor() as pool:
            # Run the synchronous method in a thread pool and await its result
            media_items = await loop.run_in_executor(
                pool, lambda: self.extract_api_data(**kwargs)
            )
            
        # Debug the results before returning
        print(f"Async API extraction completed – found {len(media_items)} items.")
        if len(media_items) > 0:
            print(f"First image URL: {media_items[0].get('url', 'No URL')}")
            
        return media_items

    def prefers_api(self) -> bool:
        """Bluesky handler prefers API if credentials were loaded."""
        has_api = getattr(self, 'api_available', False)
        print(f"BskyHandler prefers_api check. API Available: {has_api}")
        return has_api

    async def extract_with_direct_playwright_async(self, page: AsyncPage, **kwargs) -> list:
        """DOM extraction is not the preferred method for Bluesky."""
        print("Warning: Bluesky handler called with Direct Playwright strategy. API is preferred. Returning empty list.")
        return []

    async def extract_with_scrapling_async(self, response, **kwargs) -> list:
        """HTML extraction is not the preferred method for Bluesky."""
        print("Warning: Bluesky handler called with Scrapling strategy. API is preferred. Returning empty list.")
        return []

    def extract_api_data(self, **kwargs):
        """
        Fetches Bluesky posts via atproto and returns image / video (and thumbnail)
        URLs as media_items.
        """
        print("BskyHandler: Attempting API data extraction…")

        # honour timeout & start-time
        self.start_time = time.time()
        self.max_execution_time = kwargs.get('timeout', self.max_execution_time)
        max_posts = kwargs.get('max_posts', 500)  # Increased from 50
        max_api_pages = kwargs.get('max_api_pages', 10)  # Default to 10 pages
        
        media_items = []
        processed_urls = set()  # Track URLs to avoid duplicates

        # Make sure we're logged in
        if not self._authenticate_api():
            print("Failed to authenticate with Bluesky API.")
            return media_items     # ← empty

        try:
            client = self.client  # convenience
            
            if self.search_type == 'hashtag':
                # Search for hashtag posts
                media_items = self._search_hashtag(self.hashtag, max_posts, max_api_pages)
            elif self.profile_did:
                # Handle profile-based search (existing logic)
                actor_did = self._resolve_actor_did(self.profile_did)
                if not actor_did:
                    print(f"Could not resolve DID for {self.profile_did}")
                    return media_items

                media_items = self._search_profile_posts(actor_did, max_posts, max_api_pages, processed_urls)
            else:
                print("No valid search target found (no profile or hashtag)")
                return media_items

        except Exception as e:
            print(f"Error during Bluesky API extraction: {e}")
            traceback.print_exc()

        print(f"API scraping found {len(media_items)} items.")
        return media_items

    def _search_hashtag(self, hashtag, max_posts, max_api_pages):
        """Search for posts containing a specific hashtag"""
        print(f"Searching for hashtag: #{hashtag}")
        media_items = []
        processed_urls = set()
        
        try:
            # Use the search API to find posts with the hashtag
            search_query = f"#{hashtag}"
            cursor = None
            page_count = 0
            
            while page_count < max_api_pages and len(media_items) < max_posts:
                if time.time() - self.start_time > self.max_execution_time:
                    print(f"Reached max execution time ({self.max_execution_time}s)")
                    break
                
                page_count += 1
                page_limit = min(25, max_posts - len(media_items))  # Smaller pages for search
                
                # Search API parameters
                params = {
                    'q': search_query,
                    'limit': page_limit,
                }
                
                if cursor:
                    params['cursor'] = cursor
                
                print(f"Searching hashtag page {page_count} (limit: {page_limit})")
                search_results = self.client.app.bsky.feed.search_posts(params)
                
                if not getattr(search_results, 'posts', None) or len(search_results.posts) == 0:
                    print("No posts returned from hashtag search.")
                    break
                
                posts_in_page = len(search_results.posts)
                print(f"Found {posts_in_page} posts for hashtag #{hashtag} in page {page_count}")
                
                # Process each post for media
                for post in search_results.posts:
                    if len(media_items) >= max_posts:
                        break
                    
                    post_media = self._extract_media_from_post(post, processed_urls)
                    media_items.extend(post_media)
                
                # Get cursor for next page
                cursor = getattr(search_results, 'cursor', None)
                
                # Stop if no more results or no cursor
                if not cursor or posts_in_page < page_limit:
                    print(f"No more hashtag results (cursor: {bool(cursor)}, posts: {posts_in_page})")
                    break
                    
        except Exception as e:
            print(f"Error searching hashtag #{hashtag}: {e}")
            traceback.print_exc()
        
        return media_items

    def _search_profile_posts(self, actor_did, max_posts, max_api_pages, processed_urls):
        """Search for posts from a specific profile (existing logic moved here)"""
        media_items = []
        
        # Setup for pagination
        cursor = None
        page_count = 0
        total_posts_processed = 0

        while page_count < max_api_pages and total_posts_processed < max_posts:
            if time.time() - self.start_time > self.max_execution_time:
                print(f"Reached max execution time ({self.max_execution_time}s)")
                break
            
            page_count += 1
            page_limit = min(100, max_posts - total_posts_processed)  # Get up to 100 per page
            
            # Prepare params for the API request
            params = {
                'actor': actor_did, 
                'limit': page_limit,
                # Note: Removed 'posts_with_media' filter as it's unreliable for some profiles
                'includePins': True,  # Include pinned posts
            }
            
            # Add cursor for pagination if we have one
            if cursor:
                params['cursor'] = cursor
            
            print(f"Fetching page {page_count} (limit: {page_limit}) from profile: {actor_did}")
            feed = self.client.app.bsky.feed.get_author_feed(params)
            
            if not getattr(feed, 'feed', None) or len(feed.feed) == 0:
                print("No posts returned from API for this page.")
                break

            posts_in_page = len(feed.feed)
            print(f"Found {posts_in_page} posts in page {page_count}")
            total_posts_processed += posts_in_page
            
            # Get cursor for next page
            cursor = getattr(feed, 'cursor', None)
            
            for feed_item in feed.feed:
                if time.time() - self.start_time > self.max_execution_time:
                    print(f"Reached max execution time ({self.max_execution_time}s)")
                    break

                # Extract media from the post
                post = feed_item.post
                post_media = self._extract_media_from_post(post, processed_urls)
                media_items.extend(post_media)
            
            # Stop if no more posts or no cursor for next page
            if not cursor or posts_in_page < page_limit:
                print(f"No more posts to fetch (cursor: {bool(cursor)}, posts in batch: {posts_in_page})")
                break
        
        return media_items

    def _extract_media_from_post(self, post, processed_urls):
        """Extract media items from a single post (common logic for profiles and hashtags)"""
        media_items = []
        
        # Extract post data
        post_uri = getattr(post, 'uri', "")
        rkey = post_uri.split('/')[-1] if post_uri else ""
        post_url = (f"https://bsky.app/profile/{post.author.handle}/post/{rkey}"
                    if rkey else self.url)
        
        # Debug post structure to help identify where images might be
        if self.debug_mode:
            print(f"Processing post: {post_uri}")
            print(f"Post has embed: {hasattr(post, 'embed')}")
            if hasattr(post, 'embed'):
                print(f"Embed type: {type(post.embed)}")

        # Step 1: Check standard image embeds
        embed = getattr(post, "embed", None)
        if embed:
            from atproto import models
            
            # --- IMAGES EMBEDDED DIRECTLY ---
            if isinstance(embed, models.AppBskyEmbedImages.View):
                for image in embed.images:
                    img_url = getattr(image, 'fullsize', None) or image.thumb
                    if not img_url or img_url in processed_urls:
                        continue
                        
                    processed_urls.add(img_url)
                    print(f"Found image URL: {img_url}")
                    
                    media_items.append({
                        'url'        : img_url,
                        'alt'        : getattr(image, 'alt', "") or "Bluesky image",
                        'title'      : f"Post by {post.author.handle}",
                        'source_url' : post_url,
                        'credits'    : post.author.handle,
                        'type'       : 'image',
                        'trusted_cdn': True,  # Mark Bluesky CDN URLs as trusted
                    })

            # --- VIDEOS EMBEDDED DIRECTLY ---
            elif isinstance(embed, models.AppBskyEmbedVideo.View):
                # For video embeds, the data is directly on the embed object
                video_url = getattr(embed, 'playlist', None)
                if video_url and video_url not in processed_urls:
                    processed_urls.add(video_url)
                    media_items.append({
                        'url'        : video_url,
                        'alt'        : getattr(embed, 'alt', "") or "Bluesky video",
                        'title'      : f"Post by {post.author.handle}",
                        'source_url' : post_url,
                        'credits'    : post.author.handle,
                        'type'       : 'video',
                        'trusted_cdn': True,  # Mark Bluesky CDN URLs as trusted
                    })

                # Also get thumbnail if available
                thumb_url = getattr(embed, 'thumbnail', None)
                if thumb_url and thumb_url not in processed_urls:
                    processed_urls.add(thumb_url)
                    media_items.append({
                        'url'        : thumb_url,
                        'alt'        : getattr(embed, 'alt', "") or "Bluesky video thumbnail",
                        'title'      : f"Post by {post.author.handle} (thumbnail)",
                        'source_url' : post_url,
                        'credits'    : post.author.handle,
                        'type'       : 'image',
                        'trusted_cdn': True,  # Mark Bluesky CDN URLs as trusted
                    })

            # --- EXTERNAL LINKS WITH MEDIA ---
            elif isinstance(embed, models.AppBskyEmbedExternal.View):
                ext = embed.external
                hi_url = getattr(ext, "uri", None)
                thumb_url = getattr(ext, "thumb", None)

                # High resolution media
                if hi_url and hi_url not in processed_urls:
                    processed_urls.add(hi_url)
                    hi_type = "video" if hi_url.endswith(('.mp4', '.m3u8', '.webm', '.mov')) else "image"
                    media_items.append({
                        "url"        : hi_url,
                        "alt"        : getattr(ext, 'description', "") or getattr(ext, 'title', "") or "Bluesky external",
                        "title"      : f"External by {post.author.handle}",
                        "source_url" : post_url,
                        "credits"    : post.author.handle,
                        "type"       : hi_type,
                        "trusted_cdn": True,  # Mark Bluesky CDN URLs as trusted
                    })

                # Thumbnail
                if thumb_url and thumb_url not in processed_urls:
                    processed_urls.add(thumb_url)
                    media_items.append({
                        "url"        : thumb_url,
                        "alt"        : getattr(ext, 'title', "") or "Bluesky link thumbnail",
                        "title"      : f"Thumbnail by {post.author.handle}",
                        "source_url" : post_url,
                        "credits"    : post.author.handle,
                        "type"       : "image",
                        "trusted_cdn": True,  # Mark Bluesky CDN URLs as trusted
                    })
        
        # Step 2: Check for record.embed (nested embeds)
        record = getattr(post, "record", None)
        if record and hasattr(record, "embed"):
            from atproto import models
            record_embed = record.embed
            if isinstance(record_embed, models.AppBskyEmbedImages.View):
                for image in record_embed.images:
                    img_url = getattr(image, 'fullsize', None) or image.thumb
                    if not img_url or img_url in processed_urls:
                        continue
                        
                    processed_urls.add(img_url)
                    print(f"Found image URL from record.embed: {img_url}")
                    
                    media_items.append({
                        'url'        : img_url,
                        'alt'        : getattr(image, 'alt', "") or "Bluesky image",
                        'title'      : f"Post by {post.author.handle}",
                        'source_url' : post_url,
                        'credits'    : post.author.handle,
                        'type'       : 'image',
                        'trusted_cdn': True,  # Mark Bluesky CDN URLs as trusted
                    })
        
        return media_items


    def _resolve_actor_did(self, actor_identifier):
        """Resolves a handle to a DID if necessary."""
        if actor_identifier.startswith('did:'):
            return actor_identifier # Already a DID
        try:
            print(f"Resolving Bluesky handle: {actor_identifier}")
            response = self.client.resolve_handle(actor_identifier)
            print(f"Resolved to DID: {response.did}")
            return response.did
        except Exception as e:
            print(f"Could not resolve handle {actor_identifier}: {e}")
            return None

    def _process_bsky_post(self, post_data, post_uri) -> list:
        """Extracts media items from a single Bluesky post model."""
        items = []
        if not post_data.embed or not isinstance(post_data.embed, models.AppBskyEmbedImages.Main):
            return items

        post_text = post_data.text if hasattr(post_data, 'text') else ""
        author_handle = post_data.author.handle if hasattr(post_data, 'author') and hasattr(post_data.author, 'handle') else "unknown"

        for image in post_data.embed.images:
            items.append({
                'url': image.fullsize, # Use fullsize URL
                'alt': image.alt or post_text, # Use image alt text or fallback to post text
                'title': f"Bluesky post by {author_handle}",
                'source_url': f"https://bsky.app/profile/{post_data.author.handle}/post/{post_uri.split('/')[-1]}" if post_uri else self.url,
                'credits': author_handle,
                'type': 'image'
            })
        return items

    def post_process(self, media_items):
        # No specific post-processing needed for Bluesky API results currently
        return media_items

    def get_content_directory(self):
        base_dir = "bsky"
        
        if self.search_type == 'hashtag':
            content_dir = f"hashtag_{self._sanitize_directory_name(self.hashtag)}"
        elif self.profile_did:
            # Sanitize handle/DID for directory name
            content_dir = self._sanitize_directory_name(self.profile_did)
        else:
            content_dir = "unknown_profile"
            
        return base_dir, content_dir

    def _debug_auth_config(self):
        """Debug function to print auth config information."""
        print("\n--- Bluesky Auth Config Debug ---")
        if not hasattr(self.scraper, 'auth_config'):
            print("No auth_config attribute in scraper")
            return
        
        if not self.scraper.auth_config:
            print("Empty auth_config in scraper")
            return
        
        print(f"Auth config keys: {self.scraper.auth_config.keys()}")
        
        if 'sites' in self.scraper.auth_config:
            print(f"Sites in config: {list(self.scraper.auth_config['sites'].keys())}")
            
            for domain in ['bsky.app', 'bsky']:
                if domain in self.scraper.auth_config['sites']:
                    site_config = self.scraper.auth_config['sites'][domain]
                    print(f"Found config for domain: {domain}")
                    print(f"Keys in site config: {list(site_config.keys())}")
                    
                    # Check for username formats
                    username_keys = ['username', 'handle', 'user', 'email']
                    for key in username_keys:
                        if key in site_config:
                            print(f"Found username as '{key}': {bool(site_config[key])}")
                    
                    # Check for password formats
                    password_keys = ['password', 'app_password', 'appPassword', 'secret']
                    for key in password_keys:
                        if key in site_config:
                            print(f"Found password as '{key}': {bool(site_config[key])}")
        
        print("--- End Debug Output ---\n")

    # _sanitize_directory_name is inherited from BaseSiteHandler