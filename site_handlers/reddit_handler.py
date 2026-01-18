"""
Reddit Handler

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
Reddit (reddit.com) specific handler for the Web Image Scraper - Async Version
"""

from site_handlers.base_handler import BaseSiteHandler 
from urllib.parse import urljoin, urlparse, parse_qs
import time
import traceback
import os
import re
import json
from typing import List, Dict, Any, Optional, Union
import requests

# Import AsyncPRAW
try:
    import asyncpraw 
    import asyncprawcore
    ASYNCPRAW_AVAILABLE = True
except ImportError:
    asyncpraw = None
    asyncprawcore = None
    ASYNCPRAW_AVAILABLE = False
    print("Warning: asyncpraw library not found. Reddit handler API will be limited.")

# Safe import for Playwright types
try:
    from playwright.async_api import Page as AsyncPage
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    AsyncPage = None
    PLAYWRIGHT_AVAILABLE = False

class RedditHandler(BaseSiteHandler):
    """
    Handler for reddit.com.
    Focuses on extracting images and videos from subreddits, user profiles, and individual posts.
    
    Features:
    - API-based extraction (preferred, requires authentication)
    - HTML-based extraction (fallback if API fails)
    - Support for various Reddit page types (subreddit, user, post)
    - Handles various media types (images, galleries, videos)
    """

    # Image hosting domains commonly used by Reddit
    REDDIT_IMAGE_DOMAINS = [
        'i.redd.it',
        'preview.redd.it',
        'i.imgur.com',
        'imgur.com',
        'redgifs.com',
        'gfycat.com',
    ]
    
    # Video domains
    REDDIT_VIDEO_DOMAINS = [
        'v.redd.it',
        'youtube.com',
        'youtu.be',
        'streamable.com',
        'gfycat.com'
    ]

    @classmethod
    def can_handle(cls, url):
        """Check if this handler can process the URL"""
        return ("reddit.com" in url.lower() or 
               "redd.it" in url.lower() or 
               "old.reddit.com" in url.lower())

    def __init__(self, url, scraper=None):
        """Initialize RedditHandler with URL and scraper instance."""
        super().__init__(url, scraper) # Call parent __init__

        # Initialize Reddit-specific attributes
        self.subreddit = None
        self.post_id = None
        self.username = None
        self.praw_instance = None # For AsyncPRAW
        self.user_agent = "GenericScraper/1.0" # Default user agent
        self.max_pages = 3  # Default value for max_pages
        
        # Add missing timeout attributes
        self.max_execution_time = 90.0  # Default max execution time in seconds
        
        # --- API Credentials ---
        self.client_id = None
        self.client_secret = None
        self.api_username = None
        self.password = None
        self.api_available = False # Default to False

        # --- Assign debug_mode ---
        self.debug_mode = getattr(scraper, 'debug_mode', False)
        
        # --- Extract identifiers from URL ---
        self._extract_identifiers_from_url()

        # --- Load API credentials ---
        # Credentials will be loaded lazily in prefers_api() when the scraper's auth_config is available


    def prefers_api(self) -> bool:
        """Reddit handler prefers API if credentials were loaded."""
        # Ensure credentials are loaded from scraper's auth_config if not already done
        if not self.api_available and self.scraper:
            self._load_api_credentials()
        
        # Check if the necessary attributes exist AND have truthy values
        has_creds = bool(self.client_id and self.client_secret)
        print(f"RedditHandler prefers_api check. Result: {has_creds} (api_available={self.api_available})")
        return has_creds

    async def extract_api_data_async(self, **kwargs) -> list:
        """Extract media using the AsyncPRAW library.""" 
        print("RedditHandler: Attempting API data extraction via AsyncPRAW...")
        self.start_time = time.time()
        self.max_pages = kwargs.get('max_pages', self.max_pages)
        self.max_execution_time = kwargs.get('timeout', self.max_execution_time)

        # Make sure we have AsyncPRAW
        if not ASYNCPRAW_AVAILABLE:
            print("AsyncPRAW library not available.")
            return []

        # --- Initialize AsyncPRAW ---
        try:
            if not self.praw_instance:
                try:
                    # Ensure credentials are loaded if not already
                    if not self.api_available:
                        self._load_api_credentials()
                        if not self.api_available:
                            print("AsyncPRAW Error: API credentials not available.")
                            return []

                    print("Initializing AsyncPRAW...")
                    self.praw_instance = asyncpraw.Reddit(
                        client_id=self.client_id,
                        client_secret=self.client_secret,
                        user_agent=self.user_agent,
                        # Optional: Add username/password if using script auth type
                        # username=self.api_username,
                        # password=self.password,
                    )
                    
                    # No await here - read_only is a regular property
                    print(f"AsyncPRAW initialized. Read-only: {self.praw_instance.read_only}")

                except Exception as e:
                    print(f"AsyncPRAW Initialization Error: {e}")
                    traceback.print_exc()
                    return []

            # Call the AsyncPRAW-based extraction logic
            media_items = await self._extract_media_via_asyncpraw()
            return media_items
            
        finally:
            # Make sure to close the client session to avoid resource leaks
            if self.praw_instance:
                try:
                    await self.praw_instance.close()
                    print("AsyncPRAW client closed properly")
                except Exception as e:
                    print(f"Error closing AsyncPRAW client: {e}")

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
            # Accept NSFW warning if present
            {"type": "wait_for_selector", "selector": "button:has-text('Yes')", "timeout": 3000},
            {"type": "click", "selector": "button:has-text('Yes')"},
            # Accept cookies if present
            {"type": "wait_for_selector", "selector": "button:has-text('Accept all')", "timeout": 3000},
            {"type": "click", "selector": "button:has-text('Accept all')"},
            # Dismiss login popup if present
            {"type": "wait_for_selector", "selector": "button[aria-label='Close']", "timeout": 3000},
            {"type": "click", "selector": "button[aria-label='Close']"}
        ]

    async def _extract_media_via_asyncpraw(self):
        """Extract media using the initialized AsyncPRAW instance."""
        if not self.praw_instance:
            print("AsyncPRAW instance not available for extraction.")
            return []

        media_items = []
        start_time = time.time()

        try:
            # Determine what to extract based on URL type
            if self.post_id:
                print(f"AsyncPRAW: Extracting media from post ID: {self.post_id}")
                submission = await self.praw_instance.submission(id=self.post_id)
                # For asyncpraw we need to call _fetch to get data
                await submission._fetch()
                post_items = await self._process_asyncpraw_submission(submission)
                media_items.extend(post_items)

            elif self.subreddit:
                print(f"AsyncPRAW: Extracting media from subreddit: r/{self.subreddit}")
                subreddit = await self.praw_instance.subreddit(self.subreddit)
                # Fetch posts (e.g., hot, new, top) - AsyncPRAW handles pagination differently
                # Set a reasonable limit to avoid fetching indefinitely
                post_limit = 200 # Example: Fetch up to 200 posts
                count = 0
                async for submission in subreddit.hot(limit=post_limit):
                    if time.time() - start_time > self.max_execution_time:
                         print(f"Reached maximum execution time ({self.max_execution_time}s), stopping AsyncPRAW subreddit extraction.")
                         break
                    post_items = await self._process_asyncpraw_submission(submission)
                    media_items.extend(post_items)
                    count += 1
                    if count % 25 == 0: # Print progress
                         print(f"  Processed {count} posts...")
                print(f"Finished processing {count} posts from r/{self.subreddit}.")

            elif self.username:
                print(f"AsyncPRAW: Extracting media from user: u/{self.username}")
                redditor = await self.praw_instance.redditor(self.username)
                submissions = redditor.submissions.new(limit=100) # Example limit
                count = 0
                async for submission in submissions:
                     if time.time() - start_time > self.max_execution_time:
                          print(f"Reached maximum execution time ({self.max_execution_time}s), stopping AsyncPRAW user extraction.")
                          break
                     post_items = await self._process_asyncpraw_submission(submission)
                     media_items.extend(post_items)
                     count += 1
                     if count % 25 == 0: 
                         print(f"  Processed {count} user posts...")
                print(f"Finished processing {count} posts from u/{self.username}.")

        except asyncprawcore.exceptions.NotFound:
             print(f"AsyncPRAW Error: Subreddit, post, or user not found.")
        except asyncprawcore.exceptions.Forbidden as e:
             print(f"AsyncPRAW Error: Access forbidden (private subreddit, banned, etc.). {e}")
        except asyncprawcore.exceptions.Redirect as e:
             print(f"AsyncPRAW Error: Subreddit redirection occurred. {e}")
        except Exception as e:
            print(f"Error during AsyncPRAW media extraction: {e}")
            traceback.print_exc()
        finally:
            # Close the client to release resources
            await self.praw_instance.close()

        elapsed_time = time.time() - start_time
        print(f"AsyncPRAW extraction completed in {elapsed_time:.2f} seconds with {len(media_items)} potential items.")
        return self.post_process(media_items) # Apply post-processing

    async def _process_asyncpraw_submission(self, submission):
        """Extracts media items from a single AsyncPRAW submission model."""
        media_items = []
        try:
            # Get permalink - in asyncpraw this is a property
            permalink = submission.permalink
            post_url = f"https://www.reddit.com{permalink}"
            post_title = submission.title
            
            # In asyncpraw, these can be coroutines
            subreddit_name = submission.subreddit.display_name
            
            # Check if author exists (might be deleted)
            author_name = '[deleted]'
            if hasattr(submission, 'author') and submission.author:
                try:
                    author_name = submission.author.name
                except:
                    author_name = '[deleted]'

            if author_name == '[deleted]' or submission.removed_by_category:
                return []

            meta_title = self.merge_fields(post_title, f"Reddit Post {submission.id}")
            credit_line = f"Reddit: r/{subreddit_name} by u/{author_name}"

            # Check if it's a self post (text post)
            if not submission.is_self and hasattr(submission, 'url'):
                url = submission.url
                
                # Check if this is an external video host that needs resolution
                if self._is_external_video_host(url):
                    resolved = await self._resolve_external_video_url(url)
                    if resolved:
                        media_items.append({
                            'url': resolved['url'],
                            'alt': post_title,
                            'title': resolved.get('title') or meta_title,
                            'source_url': post_url,
                            'credits': credit_line,
                            'type': 'video',
                            'width': resolved.get('width', 0),
                            'height': resolved.get('height', 0),
                            'duration': resolved.get('duration'),
                            '_headers': {'Referer': url}  # Use original URL as referer
                        })
                elif self._is_image_url(url):
                    media_items.append({
                        'url': url,
                        'alt': post_title,
                        'title': meta_title,
                        'source_url': post_url,
                        'credits': credit_line,
                        'type': 'image',
                        '_headers': {'Referer': post_url}
                    })
                elif self._is_video_url(url):
                    # For v.redd.it links, they usually need special handling too
                    if 'v.redd.it' in url:
                        resolved = await self._resolve_external_video_url(url)
                        if resolved:
                            media_items.append({
                                'url': resolved['url'],
                                'alt': post_title,
                                'title': meta_title,
                                'source_url': post_url,
                                'credits': credit_line,
                                'type': 'video',
                                '_headers': {'Referer': post_url}
                            })
                    else:
                        media_items.append({
                            'url': url,
                            'alt': post_title,
                            'title': meta_title,
                            'source_url': post_url,
                            'credits': credit_line,
                            'type': 'video',
                            '_headers': {'Referer': post_url}
                        })

            # Handle Reddit-hosted videos
            if submission.is_video and submission.media and 'reddit_video' in submission.media:
                video_url = submission.media['reddit_video'].get('fallback_url')
                if video_url:
                    media_items.append({
                        'url': video_url,
                        'alt': post_title,
                        'title': meta_title,
                        'source_url': post_url,
                        'credits': credit_line,
                        'type': 'video',
                        '_headers': {'Referer': post_url}
                    })

            # Handle galleries in submission
            if hasattr(submission, 'is_gallery') and submission.is_gallery and hasattr(submission, 'media_metadata'):
                for media_id, meta in submission.media_metadata.items():
                    if meta.get('e') == 'Image' and meta.get('status') == 'valid':
                        image_url = meta['s'].get('u', '').replace('&amp;', '&')
                        if image_url:
                            media_items.append({
                                'url': image_url,
                                'alt': post_title,
                                'title': meta_title,
                                'source_url': post_url,
                                'credits': credit_line,
                                'type': 'image',
                                '_headers': {'Referer': post_url}
                            })

            # Handle crossposts
            if hasattr(submission, 'crosspost_parent_list') and submission.crosspost_parent_list:
                parent_id = submission.crosspost_parent_list[0]['id']
                parent_submission = await self.praw_instance.submission(id=parent_id)
                await parent_submission._fetch()
                crosspost_items = await self._process_asyncpraw_submission(parent_submission)
                for item in crosspost_items:
                    item['credits'] += f" (crosspost from r/{subreddit_name})"
                media_items.extend(crosspost_items)

        except Exception as e:
            print(f"Error processing AsyncPRAW submission (ID: {getattr(submission, 'id', 'N/A')}): {e}")
            traceback.print_exc()

        return media_items

    async def extract_with_direct_playwright_async(self, page: AsyncPage, **kwargs) -> list:
        """Extract media using direct Playwright DOM interaction (async version)"""
        print("RedditHandler: Attempting extraction via Direct Playwright (DOM)...")

        # Run interaction sequence (from UI, kwargs, or default)
        interaction_sequence = kwargs.get("interaction_sequence") or getattr(self, "interaction_sequence", None)
        if not interaction_sequence:
            interaction_sequence = self.get_default_interaction_sequence()
        await self._run_interaction_sequence(page, interaction_sequence)

        # Scroll to load more content
        await self._scroll_until_loaded_async(page)

        # Extract media using DOM
        return await self._extract_media_from_dom_async(page, **kwargs)

    async def extract_with_scrapling(self, response, **kwargs) -> list:
        """Extract media using Scrapling response (HTML/JSON fallback). Already async in base class."""
        print("RedditHandler: Attempting extraction via Scrapling (HTML/JSON Fallback)...")
        self.start_time = time.time()  # Reset start time

        # Try parsing HTML from the response (which includes __NEXT_DATA__)
        media_items = await self._extract_media_from_html_content_async(response)
        if media_items:
            print(f"Scrapling HTML/__NEXT_DATA__ extraction found {len(media_items)} items")
        else:
            print("Scrapling HTML/__NEXT_DATA__ extraction found 0 items.")

        # Return whatever was found by HTML parsing (could be empty)
        # Post-processing is handled within _extract_media_from_html_content
        return media_items

    def _extract_identifiers_from_url(self):
        """Extract subreddit, post ID, or username from the URL."""
        # This method doesn't use async operations, so it remains synchronous
        parsed_url = urlparse(self.url)
        path = parsed_url.path.strip('/')
        path_parts = path.split('/')

        # Check for user profile URLs (e.g., /u/username, /user/username)
        if len(path_parts) >= 2 and path_parts[0] in ['u', 'user']:
            self.username = path_parts[1]
            if self.debug_mode: print(f"  Identified as user profile: u/{self.username}")
            return

        # Check for subreddit URLs (e.g., /r/subreddit)
        if len(path_parts) >= 2 and path_parts[0] == 'r':
            self.subreddit = path_parts[1]
            # Check for post URLs within a subreddit (e.g., /r/subreddit/comments/post_id/...)
            if len(path_parts) >= 4 and path_parts[2] == 'comments':
                self.post_id = path_parts[3]
                if self.debug_mode: print(f"  Identified as post: r/{self.subreddit}/comments/{self.post_id}")
            else:
                 if self.debug_mode: print(f"  Identified as subreddit: r/{self.subreddit}")
            return

        # Fallback if no specific pattern matched (might be invalid or different structure)
        if self.debug_mode: print("  Could not identify specific Reddit type from URL path.")


    def _load_api_credentials(self):
        """Load API credentials from the scraper's auth config."""
        # This method doesn't use async operations, so it remains synchronous
        if not hasattr(self.scraper, 'auth_config') or not self.scraper.auth_config:
            print("RedditHandler: No auth_config found in scraper")
            return False
            
        # Get site config for reddit.com
        site_config = None
        if 'sites' in self.scraper.auth_config:
            if 'reddit.com' in self.scraper.auth_config['sites']:
                site_config = self.scraper.auth_config['sites']['reddit.com']
                
        if not site_config:
            print("RedditHandler: No reddit.com configuration found in auth_config")
            return False
            
        # Extract the required fields
        self.client_id = site_config.get('client_id', '')
        self.client_secret = site_config.get('client_secret', '')
        self.api_username = site_config.get('username', '')
        self.password = site_config.get('password', '')
        self.user_agent = site_config.get('user_agent', 'GenericScraper/1.0')
        
        # Check if we have the minimum required credentials
        has_creds = bool(self.client_id and self.client_secret)
        
        print(f"Reddit API Credentials Loaded: client_id={bool(self.client_id)}, "
              f"client_secret={bool(self.client_secret)}, username={bool(self.api_username)}")
              
        self.api_available = has_creds
        return has_creds

    def _is_image_url(self, url):
        """Check if a URL points to an image"""
        # This method doesn't use async operations, so it remains synchronous
        # Check domain
        if any(domain in url.lower() for domain in self.REDDIT_IMAGE_DOMAINS):
            return True
            
        # Check extension
        if any(url.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']):
            return True
            
        return False

    def _is_video_url(self, url):
        """Check if a URL points to a video"""
        # This method doesn't use async operations, so it remains synchronous
        # Check domain
        if any(domain in url.lower() for domain in self.REDDIT_VIDEO_DOMAINS):
            return True
            
        # Check extension
        if any(url.lower().endswith(ext) for ext in ['.mp4', '.webm', '.mov']):
            return True
            
        return False

    def _is_external_video_host(self, url: str) -> bool:
        """Check if URL is from an external video host that needs resolution."""
        external_hosts = ['redgifs.com', 'gfycat.com', 'imgur.com/a/', 'imgur.com/gallery/']
        return any(host in url.lower() for host in external_hosts)

    async def _resolve_external_video_url(self, url: str) -> Optional[Dict[str, Any]]:
        """
        Resolve external video host URLs (RedGifs, Gfycat, Imgur) to direct video URLs.
        Uses yt-dlp as it has excellent support for these sites.
        
        Returns:
            Dict with 'url' and 'type' keys, or None if resolution fails
        """
        import subprocess
        import tempfile
        
        try:
            print(f"RedditHandler: Resolving external video URL: {url}")
            
            # Use yt-dlp to extract video info
            result = subprocess.run(
                ['yt-dlp', '--dump-json', '--no-download', url],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0 and result.stdout:
                info = json.loads(result.stdout)
                
                # Get the best video URL
                video_url = info.get('url')
                if not video_url:
                    # Try to get from formats
                    formats = info.get('formats', [])
                    if formats:
                        # Prefer mp4, then webm
                        for fmt in reversed(formats):
                            if fmt.get('ext') == 'mp4' and fmt.get('url'):
                                video_url = fmt['url']
                                break
                        if not video_url:
                            video_url = formats[-1].get('url')
                
                if video_url:
                    print(f"RedditHandler: Resolved to: {video_url[:80]}...")
                    return {
                        'url': video_url,
                        'type': 'video',
                        'ext': info.get('ext', 'mp4'),
                        'title': info.get('title', ''),
                        'duration': info.get('duration'),
                        'width': info.get('width'),
                        'height': info.get('height')
                    }
            else:
                print(f"RedditHandler: yt-dlp failed for {url}: {result.stderr[:200] if result.stderr else 'no error'}")
                
        except subprocess.TimeoutExpired:
            print(f"RedditHandler: Timeout resolving {url}")
        except Exception as e:
            print(f"RedditHandler: Error resolving external video: {e}")
        
        return None

    async def _extract_media_from_dom_async(self, page: AsyncPage, **kwargs) -> list:
        """Extract media from DOM using async Playwright"""
        media_items = []
        if not PLAYWRIGHT_AVAILABLE:
            print("Playwright not available for DOM extraction.")
            return []

        try:
            # Find all images
            all_images = await page.locator("img").all()
            for img in all_images:
                src = await img.get_attribute("src")
                srcset = await img.get_attribute("srcset")
                alt = await img.get_attribute("alt") or ""
                title_attr = await img.get_attribute("title") or ""

                # Get best image URL
                image_url = self.parse_srcset(srcset) or src
                if not image_url or 'spacer' in image_url or 'pixel' in image_url:
                    continue

                # Try to find container element
                try:
                    # Find parent container (post)
                    container = await img.locator("xpath=ancestor::*[contains(@class, 'Post') or contains(@data-testid, 'post-container')]").first
                except Exception:
                    container = None

                # Try to get caption text
                caption = ""
                if container:
                    caption_elem = await container.locator("h1, h2, p").first
                    if caption_elem:
                        caption = await caption_elem.inner_text()

                # Create title
                final_title = self.merge_fields(alt, title_attr, caption, "Reddit Image")

                # Add to media items
                media_items.append({
                    'url': image_url,
                    'alt': alt,
                    'title': final_title,
                    'source_url': page.url,
                    'credits': "Reddit (DOM scrape)",
                    'type': 'image'
                })

        except Exception as e:
            print(f"Error during DOM-based Reddit media extraction: {e}")
            traceback.print_exc()

        return media_items

    async def _scroll_until_loaded_async(self, page: AsyncPage, selector="img", max_scrolls=20, pause_ms=1000):
        """Scroll the page until no new content loads (async version)"""
        last_count = 0
        for _ in range(max_scrolls):
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(pause_ms)
            
            # Check if there are more images
            new_count = await page.locator(selector).count()
            if new_count == last_count:
                break
            last_count = new_count

    async def _extract_media_from_html_content_async(self, response) -> list:
        """Extract media items from HTML content (used by Scrapling strategy)."""
        media_items = []
        html_content = ""
        if hasattr(response, 'text'):
            html_content = response.text
        elif hasattr(response, 'html_content'): # Check scrapling's attribute
            html_content = response.html_content
        elif hasattr(response, 'content'): # Fallback for raw requests response
                try:
                    html_content = response.content.decode('utf-8', errors='ignore')
                except: pass
        else:
            print("Could not get HTML content from Scrapling response.")
            return []

        # --- START: __NEXT_DATA__ Parsing ---
        next_data_pattern = re.compile(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.DOTALL)
        match = next_data_pattern.search(html_content)
        if match:
            print("Found __NEXT_DATA__ script, attempting to parse...")
            try:
                next_data = json.loads(match.group(1))
                # Navigate through the complex structure to find posts
                # Structure can vary, this is based on common observations
                posts_data = next_data.get('props', {}).get('pageProps', {}).get('pageLayer', {}).get('structuredData', {}).get('itemListElement')

                # Alternative path (seen in some layouts)
                if not posts_data:
                        posts_data = next_data.get('props', {}).get('pageProps', {}).get('listings', {}).get('posts')
                        if posts_data and isinstance(posts_data, dict) and 'models' in posts_data:
                            # Extract posts from the 'models' dictionary
                            posts_list = list(posts_data['models'].values())
                            # Convert to the expected format for _process_post_data
                            # This requires mapping fields, which can be complex.
                            # For now, let's use a simplified approach focusing on media URLs
                            print(f"  Parsing {len(posts_list)} posts from listings.posts.models...")
                            for post_model in posts_list:
                                if not isinstance(post_model, dict): continue
                                # Directly look for media URLs in the model
                                url = post_model.get('source', {}).get('url') # Common location for i.redd.it
                                if not url and post_model.get('media', {}).get('type') == 'image':
                                    url = post_model.get('media', {}).get('content')
                                if not url and post_model.get('media', {}).get('type') == 'video':
                                        url = post_model.get('media', {}).get('dashUrl') # Or hlsUrl

                                if url and self._is_image_url(url):
                                        media_items.append({
                                            'url': url.replace('&amp;', '&'),
                                            'alt': post_model.get('title', 'Reddit Media (JSON)'),
                                            'title': post_model.get('title', 'Reddit Media (JSON)'),
                                            'source_url': f"https://www.reddit.com{post_model.get('permalink', '')}",
                                            'credits': f"r/{post_model.get('subreddit', {}).get('name', '')} by u/{post_model.get('authorInfo', {}).get('name', '')}",
                                            'type': 'image',
                                            'category': 'next_data_image'
                                        })
                                elif url and self._is_video_url(url):
                                        media_items.append({
                                            'url': url.replace('&amp;', '&'),
                                            'alt': post_model.get('title', 'Reddit Media (JSON)'),
                                            'title': post_model.get('title', 'Reddit Media (JSON)'),
                                            'source_url': f"https://www.reddit.com{post_model.get('permalink', '')}",
                                            'credits': f"r/{post_model.get('subreddit', {}).get('name', '')} by u/{post_model.get('authorInfo', {}).get('name', '')}",
                                            'type': 'video',
                                            'category': 'next_data_video'
                                        })
                                # Handle galleries within the model if possible (complex)
                                if post_model.get('media', {}).get('gallery'):
                                        gallery_data = post_model.get('media', {}).get('gallery', {}).get('items')
                                        media_metadata = post_model.get('media', {}).get('mediaMetadata')
                                        if gallery_data and media_metadata:
                                            # Simplified gallery extraction from JSON model
                                            for item in gallery_data:
                                                media_id = item.get('mediaId')
                                                if media_id and media_id in media_metadata:
                                                    meta = media_metadata[media_id]
                                                    if meta.get('status') == 'valid' and meta.get('e') == 'Image' and 's' in meta:
                                                            gallery_url = meta['s'].get('u', '').replace('&amp;', '&')
                                                            if gallery_url:
                                                                media_items.append({
                                                                    'url': gallery_url,
                                                                    'alt': post_model.get('title', 'Reddit Gallery Image (JSON)'),
                                                                    'title': post_model.get('title', 'Reddit Gallery Image (JSON)'),
                                                                    'source_url': f"https://www.reddit.com{post_model.get('permalink', '')}",
                                                                    'credits': f"r/{post_model.get('subreddit', {}).get('name', '')} by u/{post_model.get('authorInfo', {}).get('name', '')}",
                                                                    'type': 'image',
                                                                    'category': 'next_data_gallery'
                                                                })
                # Process structuredData format if found
                elif posts_data and isinstance(posts_data, list):
                    print(f"  Parsing {len(posts_data)} items from structuredData.itemListElement...")
                    for item in posts_data:
                        if not isinstance(item, dict): continue
                        # Extract media URL - structure might vary
                        image_url = item.get('image', {}).get('url') or item.get('thumbnailUrl')
                        video_url = item.get('video', {}).get('contentUrl')
                        post_url = item.get('url') or self.url
                        title = item.get('name') or item.get('headline') or "Reddit Media (JSON)"
                        author = item.get('author', {}).get('name') or "Unknown"
                        subreddit = urlparse(post_url).path.split('/')[2] if '/r/' in post_url else ""

                        if image_url and self._is_image_url(image_url):
                            media_items.append({
                                'url': image_url.replace('&amp;', '&'),
                                'alt': title,
                                'title': title,
                                'source_url': post_url,
                                'credits': f"r/{subreddit} by u/{author}",
                                'type': 'image',
                                'category': 'next_data_image'
                            })
                        elif video_url and self._is_video_url(video_url):
                             media_items.append({
                                'url': video_url.replace('&amp;', '&'),
                                'alt': title,
                                'title': title,
                                'source_url': post_url,
                                'credits': f"r/{subreddit} by u/{author}",
                                'type': 'video',
                                'category': 'next_data_video'
                            })

                if media_items:
                     print(f"  Successfully extracted {len(media_items)} items from __NEXT_DATA__.")
                     # If we got data from JSON, we can skip the fragile regex below
                     return self.post_process(media_items) # Apply post-processing
                else:
                     print("  __NEXT_DATA__ found, but no media items extracted (structure might have changed).")

            except Exception as e:
                print(f"Error parsing __NEXT_DATA__: {e}")
                traceback.print_exc() # Show full traceback for debugging JSON structure
        else:
             print("Did not find __NEXT_DATA__ script. Falling back to regex.")
        # --- END: __NEXT_DATA__ Parsing ---

        # --- Fallback Regex Parsing (Keep as last resort) ---
        if not media_items: # Only run if __NEXT_DATA__ parsing failed
            print("  Running fallback regex parsing on HTML...")
            try:
                # Extract image URLs
                # Look for Reddit image domains in img tags
                for domain in self.REDDIT_IMAGE_DOMAINS:
                    img_pattern = re.compile(f'<img[^>]+src=["\']([^"\']*{domain}[^"\']*)["\']', re.IGNORECASE)
                    matches = img_pattern.findall(html_content)
                    for url in matches:
                        media_items.append({'url': url, 'type': 'image', 'source_url': self.url})

                # Extract image URLs from CSS backgrounds
                bg_pattern = re.compile(r'background(-image)?:\s*url\(["\']?([^"\'()]+)["\']?\)', re.IGNORECASE)
                matches = bg_pattern.findall(html_content)
                for match_tuple in matches: # Iterate through tuples from findall
                    url = match_tuple[1] # The second group contains the URL
                    if any(domain in url for domain in self.REDDIT_IMAGE_DOMAINS):
                        media_items.append({'url': url, 'type': 'image', 'source_url': self.url})

                # Extract video URLs
# Extract video URLs
                for domain in self.REDDIT_VIDEO_DOMAINS:
                    video_pattern = re.compile(f'<source[^>]+src=["\']([^"\']*{domain}[^"\']*)["\']', re.IGNORECASE)
                    matches = video_pattern.findall(html_content)
                    for url in matches:
                        media_items.append({'url': url, 'type': 'video', 'source_url': self.url})

            except Exception as e:
                print(f"Error extracting media from HTML content via regex: {e}")
        # --- End Fallback Regex Parsing ---


        # Remove duplicates and add default metadata (only if using regex fallback)
        if not match: # Only apply this if __NEXT_DATA__ wasn't found/parsed
            seen_urls = set()
            unique_items = []
            for item in media_items:
                item_url = item['url']
                if item_url not in seen_urls:
                    seen_urls.add(item_url)
                    # Add default metadata if missing
                    item.setdefault('alt', 'Reddit Media (HTML)')
                    item.setdefault('title', 'Reddit Media (HTML)')
                    item.setdefault('credits', 'Reddit')
                    unique_items.append(item)
            media_items = unique_items

        return self.post_process(media_items) # Apply post-processing


    def post_process(self, media_items):
        """Post-process media items to improve quality and remove duplicates"""
        # This method doesn't use async operations, so it remains synchronous
        if not media_items:
            return []
            
        try:
            # Improve image URLs where possible (e.g., get full resolution)
            for item in media_items:
                if item['type'] == 'image':
                    # If it's a preview.redd.it URL, try to convert to i.redd.it for full resolution
                    if 'preview.redd.it' in item['url']:
                        # Example: https://preview.redd.it/abc123.jpg?width=640&crop=...
                        # Convert to: https://i.redd.it/abc123.jpg
                        try:
                            parsed_url = urlparse(item['url'])
                            path = parsed_url.path
                            if path.startswith('/'):
                                path = path[1:]
                            full_res_url = f"https://i.redd.it/{path}"
                            print(f"Upgraded preview URL to full resolution: {item['url']} -> {full_res_url}")
                            item['url'] = full_res_url
                        except Exception as e:
                            if self.debug_mode:
                                print(f"Error upgrading preview URL: {e}")
                    
                    # Remove dimensions and other parameters from imgur URLs to get full resolution
                    if 'imgur.com' in item['url'] and '?' in item['url']:
                        item['url'] = item['url'].split('?')[0]
            
            # Remove duplicate URLs while preserving order
            seen_urls = set()
            unique_items = []
            for item in media_items:
                if item['url'] not in seen_urls:
                    seen_urls.add(item['url'])
                    unique_items.append(item)
                    
            print(f"Post-processing: {len(media_items)} -> {len(unique_items)} unique items")
            return unique_items
            
        except Exception as e:
            print(f"Error during post-processing: {e}")
            traceback.print_exc()
            return media_items

    def get_content_directory(self):
        """
        Generate Reddit-specific directory structure.
        Returns (base_dir, content_specific_dir) tuple.
        """
        # This method doesn't use async operations, so it remains synchronous
        # Base directory is always 'reddit'
        base_dir = "reddit"
        
        # Content-specific directory based on what we're scraping
        content_parts = []
        
        if self.subreddit:
            content_parts.append(self._sanitize_directory_name(self.subreddit))
        elif self.username:
            content_parts.append("user")
            content_parts.append(self._sanitize_directory_name(self.username))
        elif self.post_id:
            content_parts.append("post") 
            content_parts.append(self._sanitize_directory_name(self.post_id))
        else:
            # Parse from URL path if needed
            parsed_url = urlparse(self.url)
            path = parsed_url.path.strip('/')
            path_components = [self._sanitize_directory_name(p) for p in path.split('/') if p]
            if path_components:
                content_parts.extend(path_components)
        
        # Ensure there's at least one part
        if not content_parts:
            content_parts.append("general")
        
        # Join all parts to form the path
        content_specific_dir = os.path.join(*content_parts)
        
        return (base_dir, content_specific_dir)

    def _sanitize_directory_name(self, name):
        """Sanitize directory name to avoid invalid characters."""
        # This method doesn't use async operations, so it remains synchronous
        return re.sub(r'[<>:"/\\|?*]', '_', name)

    async def _save_debug_info_async(self, page_or_response):
        """Save debug information for troubleshooting (async version)"""
        try:
            html_content = ""
            if hasattr(page_or_response, 'content'):
                if callable(getattr(page_or_response, 'content')):
                    html_content = await page_or_response.content()
                else:
                    html_content = page_or_response.content
            elif hasattr(page_or_response, 'text'):
                if callable(getattr(page_or_response, 'text')):
                    html_content = await page_or_response.text()
                else:
                    html_content = page_or_response.text
                    
            if not html_content:
                print("No HTML content available for debug info")
                return
                
            # Create debug directory
            debug_dir = os.path.join(os.path.dirname(__file__), "debug")
            os.makedirs(debug_dir, exist_ok=True)
            
            # Save the HTML content
            debug_file = os.path.join(debug_dir, "reddit_debug.html")
            with open(debug_file, "w", encoding="utf-8") as f:
                f.write(html_content)
                
            print(f"Saved debug info to {debug_file}")
        except Exception as e:
            print(f"Error saving debug info: {e}")