"""
Web Image Scraper V082

Description: Advanced web scraping node with Playwright and Scrapling for comprehensive media extraction from any website
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
Eric Web File Scraper Node - v0.82 (Download Tools Edition)

This node scrapes images and videos from a specified URL and saves them to a directory.
It uses the scrapling library with Playwright for modern web pages and imagehash for deduplication.
It can filter media by minimum dimensions, offers a continue function, and keeps only the largest version of duplicate images.

Migrated to download-tools package with separate web_scraper auth config.

Features:
- Fetches images and/or videos from specified URLs using scrapling & Playwright
- Supports modern web pages with JavaScript and dynamic content
- Extracts alt text, titles, and other metadata from images
- Filters images by minimum dimensions
- Detects and removes duplicate images, keeping the largest resolution
- Can continue from a previous run to avoid duplicates
- Reports number of files found and downloaded
- Returns file paths for further processing
- Returns detailed statistics about the scraping process (JSON format)
- Option to move duplicates to a subfolder instead of deleting
- Built-in scrolling to load lazy content


Make sure you have scrapling, playwright and imagehash installed:
pip install scrapling playwright imagehash
playwright install
"""

import os
import time
import requests
import json
import hashlib
import random
import asyncio
import concurrent.futures
import mimetypes
from typing import Optional, Union, List, Dict, Any, Tuple
try:
    import nest_asyncio
    nest_asyncio.apply()
except ImportError:
    print("Warning: nest_asyncio not available. Some async functionality may be limited.")
from PIL import Image
from io import BytesIO
from urllib.parse import urljoin, urlparse
try:
    import folder_paths
except ImportError:
    print("Warning: folder_paths not available (running outside ComfyUI)")
    folder_paths = None
import re
import traceback
import sys
from threading import Timer
import importlib
import inspect
from collections import defaultdict       
import pkgutil
from pathlib import Path
import shutil
import subprocess
import tempfile
import requests
try:
    import scrapling
    SCRAPLING_IMPORT_SUCCESS = True
except ImportError:
    print("Warning: scrapling not available")
    scrapling = None
    SCRAPLING_IMPORT_SUCCESS = False
import pathlib


# Direct Playwright support
try:
    import playwright
    from playwright.async_api import async_playwright, Page as AsyncPage
    PLAYWRIGHT_AVAILABLE = True
    try:
        playwright_version = getattr(playwright, '__version__', 'version unknown')
        print(f"Successfully imported Playwright async API (version: {playwright_version})")
    except:
        print(f"Successfully imported Playwright async API (version information unavailable)")
except ImportError:
    playwright = None
    async_playwright = None
    AsyncPage = None
    PLAYWRIGHT_AVAILABLE = False
    print("Playwright import failed.")

# Add proper import for imagehash with error handling
try:
    import imagehash
    IMAGEHASH_AVAILABLE = True
except ImportError:
    print("Warning: imagehash module not found. Image deduplication will be limited.")
    imagehash = None
    IMAGEHASH_AVAILABLE = False


# Scrapling support - as a fallback


try:
    from scrapling.parser import Adaptor
    from scrapling.fetchers import PlayWrightFetcher
    SCRAPLING_AVAILABLE = True
    print("Successfully imported Scrapling and PlayWrightFetcher")
except ImportError:
    print("Scrapling import failed. Some functionality will be limited.")
    Adaptor = None
    PlayWrightFetcher = None
    SCRAPLING_AVAILABLE = False

# Import site handlers with fallback
try:
    from ..site_handlers.generic_handler_with_auth import GenericWebsiteWithAuthHandler
except ImportError:
    try:
        import sys
        import os
        # Add the parent directory to path to find site_handlers
        parent_dir = os.path.dirname(os.path.dirname(__file__))
        if parent_dir not in sys.path:
            sys.path.insert(0, parent_dir)
        from site_handlers.generic_handler_with_auth import GenericWebsiteWithAuthHandler
    except ImportError as e:
        print(f"Warning: Could not import GenericWebsiteWithAuthHandler: {e}")
        # Create a dummy handler class as fallback
        class GenericWebsiteWithAuthHandler:
            def __init__(self, url, scraper):
                self.url = url
                self.scraper = scraper
            
            @staticmethod
            def can_handle(url):
                return True
            
            def prefers_api(self):
                return False
            
            def requires_api(self):
                return False
            
            async def extract_with_direct_playwright(self, page, **kwargs):
                return []
            
            async def extract_with_scrapling(self, response, **kwargs):
                return []

SUPPORTED_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp', '.tiff', '.svg', '.heic', '.heif'}
SUPPORTED_VIDEO_EXTENSIONS = {'.mp4', '.webm', '.mov', '.m3u8', '.avi', '.flv', '.mkv'}
SUPPORTED_AUDIO_EXTENSIONS = {'.mp3', '.wav', '.aac', '.ogg', '.flac'}

def load_site_handlers():
    """Dynamically load all site handlers"""
    handlers = []
    handlers_path = Path(__file__).parent.parent / "site_handlers"
    print(f"Looking for site handlers in: {handlers_path}")

    # Check if handlers directory exists
    if not handlers_path.exists():
        print(f"Warning: site_handlers directory not found at {handlers_path}")
        return []

    # Ensure site_handlers directory is in path
    if str(handlers_path) not in sys.path:
        sys.path.insert(0, str(handlers_path))
        print(f"Added {handlers_path} to sys.path")
    
    # Also make sure parent is in path for proper imports
    parent_path = str(handlers_path.parent)
    if parent_path not in sys.path:
        sys.path.insert(0, parent_path)
        print(f"Added {parent_path} to sys.path")

    # Create __init__.py if it doesn't exist
    init_file = handlers_path / "__init__.py"
    if not init_file.exists():
        with open(init_file, "w") as f:
            f.write('"""Site handlers package"""')
        print(f"Created missing {init_file}")

    try:
        # First try to import base handler using standard import
        BaseSiteHandler = None
        try:
            from site_handlers.base_handler import BaseSiteHandler
            print(f"Successfully imported BaseSiteHandler from site_handlers.base_handler")
        except ImportError as e:
            print(f"Error importing BaseSiteHandler standard way: {e}")
            # Fallback to direct file import if needed
            base_handler_path = handlers_path / "base_handler.py"
            if base_handler_path.exists():
                try:
                    spec = importlib.util.spec_from_file_location("base_handler", base_handler_path)
                    base_handler_module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(base_handler_module)
                    BaseSiteHandler = base_handler_module.BaseSiteHandler
                    print(f"Successfully imported BaseSiteHandler directly from {base_handler_path}")
                except Exception as direct_import_error:
                    print(f"Error loading BaseSiteHandler directly: {direct_import_error}")
                    BaseSiteHandler = None
            else:
                print(f"Cannot find BaseSiteHandler implementation at {base_handler_path}")

        # If we still don't have BaseSiteHandler, create a dummy one
        if BaseSiteHandler is None:
            print("Creating dummy BaseSiteHandler for fallback")
            class BaseSiteHandler:
                def __init__(self, url, scraper):
                    self.url = url
                    self.scraper = scraper
                
                @staticmethod
                def can_handle(url):
                    return False
                
                def prefers_api(self):
                    return False
                
                def requires_api(self):
                    return False

        # Now process each handler file
        for handler_file in handlers_path.glob("*.py"):
            module_name = handler_file.stem
            if module_name != "base_handler" and module_name != "__init__":
                try:
                    # Try normal import first
                    module_full_name = f"site_handlers.{module_name}"
                    module = importlib.import_module(module_full_name)
                    print(f"Loaded module: {module_name}")
                    
                    # Find handler classes in the module
                    handler_count = 0
                    for name, obj in inspect.getmembers(module):
                        if inspect.isclass(obj) and hasattr(obj, 'can_handle'):
                            try:
                                if BaseSiteHandler and issubclass(obj, BaseSiteHandler) and obj != BaseSiteHandler:
                                    print(f"  Found handler class: {name}")
                                    handlers.append(obj)
                                    handler_count += 1
                                elif not BaseSiteHandler and hasattr(obj, 'can_handle'):
                                    # If we don't have BaseSiteHandler, just check for can_handle method
                                    print(f"  Found handler class (no base check): {name}")
                                    handlers.append(obj)
                                    handler_count += 1
                            except TypeError:
                                pass  # Not a subclass we can check
                    
                    if handler_count == 0:
                        print(f"  Warning: No handler classes found in {module_name}")
                        
                except Exception as e:
                    print(f"Error loading site handler {module_name}: {e}")
                    traceback.print_exc()

        # Sort handlers to prioritize specific site handlers over generic ones
        # This ensures RedditHandler gets tested before GenericWebsiteWithAuthHandler
        def get_handler_priority(handler_class):
            # Give GenericWebsiteWithAuthHandler lowest priority
            if handler_class.__name__ == "GenericWebsiteWithAuthHandler":
                return 999
            # Give enhanced YouTube handler high priority
            elif handler_class.__name__ == "YouTubeHandler":
                return 5
            # Give site-specific handlers higher priority
            elif handler_class.__name__ in ["RedditHandler", "BskyHandler", "FlickrHandler", "ArtsyHandler"]:
                return 10
            # Default priority
            return 100
            
        # Sort handlers by priority
        handlers.sort(key=get_handler_priority)
        print(f"Sorted handlers by priority: {[h.__name__ for h in handlers]}")

    except Exception as e:
        print(f"Error in site handler loading process: {e}")
        traceback.print_exc()

    print(f"Finished loading site handlers. Found: {len(handlers)}")
    return handlers

loaded_handlers = {handler.__name__: handler for handler in load_site_handlers()}

def colored_print(message, color_code="94"):
    """
    Prints a message in the specified ANSI color.
    Args:
        message (str): The message to print.
        color_code (str): ANSI color code as a string (default is "94" for bright blue).
        94 is bright blue, 92 is bright green, 93 is yellow, 91 is red.
    """
    print(f"\033[{color_code}m{message}\033[0m")

class EricWebFileScraper:
    # --- ComfyUI Node Definition ---
    @classmethod
    def INPUT_TYPES(cls):
        # Define common hash algorithms based on availability
        hash_algos = ["average_hash", "phash", "dhash", "whash"] if IMAGEHASH_AVAILABLE else ["none"]

        return {
            "required": {
                "url": ("STRING", {"multiline": True, "default": "", "placeholder": "Enter URLs (one per line) or profiles:\nbsky.app/profile/username\nusername (for Bluesky)\n#hashtag (for Bluesky)"}),
                "output_dir": ("STRING", {"multiline": False, "default": "web_scraper_output"}),
                # --- Basic Filters ---
                "min_width": ("INT", {"default": 512, "min": 0, "max": 10000, "step": 1}),
                "min_height": ("INT", {"default": 512, "min": 0, "max": 10000, "step": 1}),
                "max_files": ("INT", {"default": 1000, "min": 0, "max": 5000, "step": 10, "display": "Max Files (0=unlimited)"}),
                # --- Download Options ---
                "download_images": ("BOOLEAN", {"default": True}),
                "download_videos": ("BOOLEAN", {"default": True}),
                "same_domain_only": ("BOOLEAN", {"default": True, "label_on": "Stay on Domain", "label_off": "Allow Off-Domain"}),
                "filename_prefix": ("STRING", {"multiline": False, "default": "WS81_"}),
            },
            "optional": {
                # --- Strategy & Behavior ---
                "use_direct_playwright": ("BOOLEAN", {"default": True, "label_on": "Use Direct Browser", "label_off": "Skip Direct Browser"}),
                "continue_last_run": ("BOOLEAN", {"default": False, "label_on": "Continue Previous", "label_off": "Start Fresh"}),
                "use_url_as_folder": ("BOOLEAN", {"default": True, "label_on": "URL Subfolder", "label_off": "Domain Subfolder"}),
                # --- Deduplication ---
                "move_duplicates": ("BOOLEAN", {"default": False, "label_on": "Move Duplicates", "label_off": "Delete Duplicates"}),
                "hash_algorithm": (hash_algos,),
                # --- Metadata ---
                "extract_metadata": ("BOOLEAN", {"default": True, "label_on": "Extract Metadata", "label_off": "Skip Metadata"}),
                "save_metadata_json": ("BOOLEAN", {"default": True, "label_on": "Save Metadata File", "label_off": "Skip Metadata File"}),
                # --- Crawling Options ---
                "crawl_links": ("BOOLEAN", {"default": False, "label_on": "Follow Links", "label_off": "Single Page"}),
                "crawl_depth": ("INT", {"default": 1, "min": 1, "max": 5, "step": 1, "display": "Link Crawl Depth"}),
                "max_pages": ("INT", {"default": 10, "min": 1, "max": 100, "step": 1, "display": "Max Pages to Visit"}),
                
                # --- Media Types ---
                "download_audio": ("BOOLEAN", {"default": False, "label_on": "Extract Audio", "label_off": "Skip Audio"}),
                
                # --- Export Options ---
                "metadata_export_format": (["json", "csv", "md"], {"default": "json"}),
                # --- Browser Control ---
                "timeout_seconds": ("FLOAT", {"default": 100.0, "min": 5.0, "max": 600.0, "step": 5.0, "display": "Page Load Timeout (s)"}),
                "handler_timeout": ("FLOAT", {"default": 120.0, "min": 10.0, "max": 1200.0, "step": 10.0, "display": "Handler/API Timeout (s)"}),
                "max_api_pages": ("INT", {"default": 3, "min": 1, "max": 100, "step": 1, "display": "Max API Pages"}),
                "wait_for_network_idle": ("BOOLEAN", {"default": False, "label_on": "Wait Network Idle", "label_off": "Wait Page Load"}),
                "playwright_wait_ms": ("INT", {"default": 1000, "min": 0, "max": 60000, "step": 100, "display": "Extra Wait (ms)"}),
                "use_stealth_mode": ("BOOLEAN", {"default": False, "label_on": "Use Stealth Mode", "label_off": "Normal Browser"}),
                "stealth_mode_level": (["basic", "enhanced", "extreme"], {"default": "basic"}),                
                
                # --- Scrolling ---
                "use_auto_scroll": ("BOOLEAN", {"default": True, "label_on": "Auto Scroll", "label_off": "Fixed Scroll/None"}),
                "max_auto_scrolls": ("INT", {"default": 150, "min": 0, "max": 500, "step": 5, "display": "Max Auto Scrolls"}),
                "scroll_down_times": ("INT", {"default": 150, "min": 0, "max": 200, "step": 1, "display": "Fixed Scroll Times"}),
                "scroll_delay_ms": ("INT", {"default": 1000, "min": 50, "max": 5000, "step": 50, "display": "Scroll Delay (ms)"}),
                # --- Interactions & Auth ---
                "interaction_sequence": ("STRING", {"multiline": True, "placeholder": '[{"type": "click", "selector": "#button"}, ...]', "display": "Interaction Sequence (JSON)"}),
                "auth_config_path": ("STRING", {"default": "", "placeholder": "Path to auth_config.json"}),
                "save_cookies": ("BOOLEAN", {"default": False, "label_on": "Save Cookies", "label_off": "Don't Save Cookies"}),
                # --- Screenshots & Debug ---
                "take_screenshot": ("BOOLEAN", {"default": False, "label_on": "Take Screenshot", "label_off": "No Screenshot"}),
                "screenshot_elements": ("STRING", {"multiline": True, "placeholder": "CSS selectors (one per line)", "display": "Screenshot Elements (Optional)"}),
                "screenshot_full_page": ("BOOLEAN", {"default": False, "label_on": "Full Page", "label_off": "Viewport Only"}),
                "debug_mode": ("BOOLEAN", {"default": False, "display": "Enable Debug Mode"}),
                # --- Advanced Options ---
                "use_stealth_mode": ("BOOLEAN", {"default": False, "label_on": "Use Stealth Mode", "label_off": "Normal Browser"}),
                "use_parallel": ("BOOLEAN", {"default": True, "label_on": "Parallel Downloads", "label_off": "Sequential Downloads"}),
                "max_workers": ("INT", {"default": 4, "min": 1, "max": 16, "step": 1, "display": "Parallel Workers"}),
                "reuse_sessions": ("BOOLEAN", {"default": True, "label_on": "Reuse Sessions", "label_off": "New Session"}),
                "session_expiry_hours": ("FLOAT", {"default": 24.0, "min": 1.0, "max": 720.0, "step": 1.0, "display": "Session Expiry (hours)"}),
                "capture_network_stream": ("BOOLEAN", {"default": False, "label_on": "Sniff Responses", "label_off": "Skip Sniff"}),
                "dump_cache_after_run": ("BOOLEAN", {"default": False, "label_on": "Carve Cache After Run", "label_off": "Skip Cache Carve"}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING", "INT", "INT", "INT", "INT", "INT", "INT", "INT", "INT", "INT", "INT", "INT", "STRING")
    RETURN_NAMES = (
        "output_path", "metadata_json_path",
        "files_found", "files_downloaded", "videos_downloaded", "duplicates_removed", "duplicates_moved",
        "skipped_small", "skipped_platform", "skipped_not_media", "skipped_already_processed",
        "failed_download", "screenshots_taken",
        "stats_summary"
    )
    FUNCTION = "scrape_files"
    CATEGORY = "download-tools/Scrapers"
    OUTPUT_NODE = True

    # --- Initialization ---
    def __init__(self):
        self.pw_resources = None  # Tuple: (playwright, browser, context, page)
        self.scrapling_available = SCRAPLING_AVAILABLE
        self.playwright_available = PLAYWRIGHT_AVAILABLE
        self.imagehash_available = IMAGEHASH_AVAILABLE
        self.site_handlers = loaded_handlers
        self.processed_urls = set()
        self.metadata_file = "download_metadata.json"
        self.image_extensions = SUPPORTED_IMAGE_EXTENSIONS
        self.video_extensions = SUPPORTED_VIDEO_EXTENSIONS
        self.audio_extensions = SUPPORTED_AUDIO_EXTENSIONS
        self.auth_config = None
        self.debug_mode = False
        self.cancellation_requested = False  # Add cancellation flag
        self.files_saved_this_session = []  # Track files saved in current session
        self.save_batch_size = 10  # Save progress every N files

        # Initialize session manager
        sessions_dir = os.path.join(os.path.dirname(__file__), "sessions")
        self.session_manager = SessionManager(sessions_dir)
        
        # Add stealth mode flag
        self.use_stealth_mode = False

    def load_configuration_preset(self, preset_name):
        """
        Load a predefined configuration preset.
        
        Args:
            preset_name: Name of the preset to load
            
        Returns:
            Dictionary of configuration parameters
        """
        presets = {
            "high_quality_images": {
                "min_width": 800,
                "min_height": 1024,
                "download_images": True,
                "download_videos": False,
                "use_auto_scroll": True,
                "max_auto_scrolls": 20,
                "use_stealth_mode": True,
                "use_parallel": True,
                "max_workers": 4
            },
            "videos_only": {
                "min_width": 0,
                "min_height": 0,
                "download_images": False,
                "download_videos": True,
                "use_auto_scroll": True,
                "max_auto_scrolls": 10,
                "use_stealth_mode": True,
                "use_parallel": True,
                "max_workers": 2
            },
            "social_media": {
                "min_width": 512,
                "min_height": 512,
                "download_images": True,
                "download_videos": True,
                "use_auto_scroll": True,
                "max_auto_scrolls": 50,
                "use_stealth_mode": True,
                "use_parallel": True,
                "max_workers": 4,
                "reuse_sessions": True
            },
            "art_websites": {
                "min_width": 800,
                "min_height": 800,
                "download_images": True,
                "download_videos": False,
                "use_auto_scroll": True,
                "max_auto_scrolls": 30,
                "use_stealth_mode": True,
                "use_parallel": True,
                "max_workers": 6
            },
            "deep_scrape": {
                "min_width": 0,
                "min_height": 0,
                "download_images": True,
                "download_videos": True,
                "use_auto_scroll": True,
                "max_auto_scrolls": 100,
                "scroll_delay_ms": 1000,
                "playwright_wait_ms": 2000,
                "use_stealth_mode": True,
                "use_parallel": True,
                "max_workers": 8,
                "wait_for_network_idle": True
            }
        }
        
        if preset_name not in presets:
            print(f"Unknown preset: {preset_name}. Using default.")
            return {}
        
        print(f"Loaded configuration preset: {preset_name}")
        return presets[preset_name]

    # --- Main Execution Method ---

    def scrape_files(self, url, output_dir, **kwargs):
        """
        Synchronous entry point required by ComfyUI.
        Simply delegates to the async implementation.
        """
        colored_print("--- EricWebFileScraper v0.8 ---", "94")  # Bright blue
        
        # Sanitize output directory
        if folder_paths:
            if not output_dir or output_dir.strip() == "":
                output_dir = folder_paths.get_output_directory()
            
            if not os.path.isabs(output_dir):
                output_dir = os.path.join(folder_paths.get_output_directory(), output_dir)
            
            output_dir = os.path.normpath(output_dir)
            output_dir = os.path.abspath(output_dir)
        else:
            # Fallback if folder_paths is not available (e.g. running standalone)
            output_dir = os.path.abspath(output_dir)
        
        import asyncio
        import nest_asyncio
        

        # Allow nested event loops (needed for ComfyUI)
        nest_asyncio.apply()
        
        # Try to reuse existing event loop if available (better for ComfyUI)
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                raise RuntimeError("Loop is closed")
        except (RuntimeError, AttributeError):
            # No loop exists or it's closed, create a new one
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        # Run the async scraping task
        # Note: Don't close the loop as ComfyUI may still need it
        return loop.run_until_complete(self._async_scrape_files(url, output_dir, **kwargs))

    async def _async_scrape_files(self, url, output_dir, **kwargs):
        """Main async method for scraping files with support for multiple URLs."""
        self.start_time = time.time()
        self.processed_urls.clear()
        self.pw_resources = None
        self.auth_config = None
        self.cancellation_requested = False  # Reset cancellation flag
        self.files_saved_this_session = []  # Reset files tracking

        # Get important kwargs with defaults
        use_parallel = kwargs.get('use_parallel', True)
        max_workers = kwargs.get('max_workers', 4)

        # Get advanced options
        self.use_stealth_mode = kwargs.get('use_stealth_mode', False)
        reuse_sessions = kwargs.get('reuse_sessions', True)
        
        try:
            # Parse multiple URLs from input
            urls_to_process = self._parse_multiple_urls(url)
            print(f"Processing {len(urls_to_process)} URL(s): {urls_to_process}")
            
            # Check for cancellation before starting
            if self._check_cancellation():
                return self._create_cancelled_result(output_dir)
            
            # If multiple URLs, process them sequentially with separate subfolders
            if len(urls_to_process) > 1:
                return await self._process_multiple_urls(urls_to_process, output_dir, **kwargs)
            else:
                # Single URL - use existing logic
                single_url = urls_to_process[0] if urls_to_process else url
                return await self._process_single_url(single_url, output_dir, **kwargs)
        except KeyboardInterrupt:
            print("\n🛑 Scraping cancelled by user")
            self.cancellation_requested = True
            return self._create_cancelled_result(output_dir)
        except Exception as e:
            print(f"\n❌ Error in scraping: {e}")
            raise

    def _parse_multiple_urls(self, url_input):
        """Parse multiple URLs from multiline input, handle Bluesky shortcuts"""
        if not url_input or not url_input.strip():
            return []
        
        # Split by newlines and filter out empty lines
        raw_lines = [line.strip() for line in url_input.split('\n') if line.strip()]
        
        urls = []
        for line in raw_lines:
            # Expand Bluesky shortcuts
            expanded_urls = self._expand_bluesky_shortcuts(line)
            urls.extend(expanded_urls)
        
        return urls
    
    def _check_cancellation(self):
        """Check if cancellation has been requested (ComfyUI doesn't provide direct cancellation, so we check for KeyboardInterrupt)"""
        try:
            # This is a simple check - in practice, ComfyUI may terminate the process
            return self.cancellation_requested
        except KeyboardInterrupt:
            self.cancellation_requested = True
            return True
        except:
            return False
    
    def _create_cancelled_result(self, output_dir):
        """Create a result tuple for cancelled operations"""
        files_saved = len(self.files_saved_this_session)
        print(f"\n⚠️ Scraping cancelled. Saved {files_saved} files before cancellation.")
        
        # Return the expected tuple format with cancelled status
        return (
            output_dir,  # output_path
            "",  # metadata_json_path
            0,   # files_found
            files_saved,  # files_downloaded
            0,   # videos_downloaded  
            0,   # duplicates_removed
            0,   # duplicates_moved
            0,   # skipped_small
            0,   # skipped_platform
            0,   # skipped_not_media
            0,   # skipped_already_processed
            0,   # failed_download
            0,   # screenshots_taken
            f"Cancelled after saving {files_saved} files"  # stats_summary
        )
    
    def _expand_bluesky_shortcuts(self, text):
        """Expand Bluesky shortcuts into full URLs"""
        text = text.strip()
        
        # DEBUG: Log the expansion process
        print(f"🔍 [EXPAND DEBUG] Input: '{text}'")
        print(f"    Starts with http/https: {text.startswith(('http://', 'https://'))}")
        
        # Check for malformed URLs (common typos) - be more specific to avoid false positives
        if (text.startswith('https:/') and not text.startswith('https://')) or \
           (text.startswith('http:/') and not text.startswith('http://')) or \
           text.startswith('https//') or text.startswith('http//'):
            print(f"⚠️ [URL WARNING] Detected malformed URL: '{text}'")
            print(f"    Looks like a typo in the protocol. Did you mean:")
            
            # Try to fix common typos
            if text.startswith('https:/') and not text.startswith('https://'):
                # Handle cases like "https:/https://..." - remove the malformed part
                if 'https://' in text:
                    # Find the first valid https:// and use from there
                    https_pos = text.find('https://')
                    corrected = text[https_pos:]
                elif 'http://' in text:
                    # Find the first valid http:// and use from there  
                    http_pos = text.find('http://')
                    corrected = text[http_pos:]
                else:
                    # Simple case: just fix the protocol
                    corrected = text.replace('https:/', 'https://', 1)
                print(f"    → {corrected}")
                print(f"🔧 [AUTO-FIX] Attempting to correct malformed URL")
                return [corrected]
            elif text.startswith('http:/') and not text.startswith('http://'):
                # Handle cases like "http:/https://..." or "http:/http://..."
                if 'https://' in text:
                    https_pos = text.find('https://')
                    corrected = text[https_pos:]
                elif 'http://' in text:
                    http_pos = text.find('http://')
                    corrected = text[http_pos:]
                else:
                    corrected = text.replace('http:/', 'http://', 1)
                print(f"    → {corrected}")
                print(f"🔧 [AUTO-FIX] Attempting to correct malformed URL")
                return [corrected]
            elif text.startswith('https//'):
                corrected = text.replace('https//', 'https://', 1)
                print(f"    → {corrected}")
                print(f"🔧 [AUTO-FIX] Attempting to correct malformed URL")
                return [corrected]
            elif text.startswith('http//'):
                corrected = text.replace('http//', 'http://', 1)
                print(f"    → {corrected}")
                print(f"🔧 [AUTO-FIX] Attempting to correct malformed URL")
                return [corrected]
        
        # Already a full URL - return as is
        if text.startswith(('http://', 'https://')):
            print(f"🔍 [EXPAND DEBUG] → Returning as full URL: {text}")
            return [text]
        
        # Hashtag without #
        if text.startswith('#'):
            hashtag = text[1:]  # Remove #
            result = f"https://bsky.app/hashtag/{hashtag}"
            print(f"🔍 [EXPAND DEBUG] → Treating as hashtag: {result}")
            return [result]
        
        # Simple username (could be Bluesky)
        if '.' in text or text.isalnum() or '_' in text or '-' in text:
            # Looks like a potential Bluesky handle
            username = text.lstrip('@')  # Remove @ if present
            result = f"https://bsky.app/profile/{username}"
            print(f"🔍 [EXPAND DEBUG] → Treating as Bluesky username: {result}")
            return [result]
        
        # Fallback - treat as URL if it contains domain-like patterns
        if '/' in text or '.' in text:
            print(f"🔍 [EXPAND DEBUG] → Treating as fallback URL: {text}")
            return [text]
        
        print(f"🔍 [EXPAND DEBUG] → No match, returning empty")
        return []
    
    async def _process_multiple_urls(self, urls, output_dir, **kwargs):
        """Process multiple URLs sequentially with separate subfolders"""
        combined_stats = {
            'files_found': 0,
            'files_downloaded': 0,
            'downloads_succeeded_image': 0,
            'downloads_succeeded_video': 0,
            'duplicates_removed': 0,
            'duplicates_moved': 0,
            'skipped_small': 0,
            'skipped_platform': 0,
            'skipped_not_media': 0,
            'skipped_already_processed': 0,
            'downloads_failed': 0,
            'screenshots_taken': 0,
            'total_urls_processed': len(urls),
            'successful_urls': 0,
            'failed_urls': 0,
        }
        
        all_output_paths = []
        all_metadata_paths = []
        
        print(f"Processing {len(urls)} URLs with individual subfolders...")
        
        for i, single_url in enumerate(urls, 1):
            # Check for cancellation before each URL
            if self.cancellation_requested or self._check_cancellation():
                print(f"\n🛑 URL processing cancelled by user after {i-1}/{len(urls)} URLs")
                break
                
            print(f"\n=== Processing URL {i}/{len(urls)}: {single_url} ===")
            
            try:
                # Process single URL
                result = await self._process_single_url(single_url, output_dir, **kwargs)
                
                # Unpack results
                (output_path, metadata_json_path, files_found, files_downloaded, videos_downloaded,
                 duplicates_removed, duplicates_moved, skipped_small, skipped_platform,
                 skipped_not_media, skipped_already_processed, failed_download, screenshots_taken, stats_summary) = result
                
                # Accumulate stats
                combined_stats['files_found'] += files_found
                combined_stats['files_downloaded'] += files_downloaded
                combined_stats['downloads_succeeded_video'] += videos_downloaded
                combined_stats['duplicates_removed'] += duplicates_removed
                combined_stats['duplicates_moved'] += duplicates_moved
                combined_stats['skipped_small'] += skipped_small
                combined_stats['skipped_platform'] += skipped_platform
                combined_stats['skipped_not_media'] += skipped_not_media
                combined_stats['skipped_already_processed'] += skipped_already_processed
                combined_stats['downloads_failed'] += failed_download
                combined_stats['screenshots_taken'] += screenshots_taken
                combined_stats['successful_urls'] += 1
                
                all_output_paths.append(output_path)
                if metadata_json_path:
                    all_metadata_paths.append(metadata_json_path)
                
                print(f"✅ Successfully processed {single_url}")
                
            except Exception as e:
                print(f"❌ Failed to process {single_url}: {e}")
                combined_stats['failed_urls'] += 1
                traceback.print_exc()
        
        # Calculate combined image downloads
        combined_stats['downloads_succeeded_image'] = (combined_stats['files_downloaded'] - 
                                                      combined_stats['downloads_succeeded_video'])
        
        # Create summary
        combined_output_path = "; ".join(all_output_paths) if all_output_paths else ""
        combined_metadata_path = "; ".join(all_metadata_paths) if all_metadata_paths else ""
        
        duration = time.time() - self.start_time
        stats_summary = (
            f"Multi-URL Processing Complete in {duration:.2f}s.\n"
            f"URLs: {combined_stats['successful_urls']}/{combined_stats['total_urls_processed']} successful.\n"
            f"Total Found: {combined_stats['files_found']}, Downloaded: {combined_stats['files_downloaded']} "
            f"(Img: {combined_stats['downloads_succeeded_image']}, Vid: {combined_stats['downloads_succeeded_video']}).\n"
            f"Skipped: {combined_stats['skipped_small']}+{combined_stats['skipped_platform']}+{combined_stats['skipped_not_media']}+{combined_stats['skipped_already_processed']}, "
            f"Failed: {combined_stats['downloads_failed']}, Screenshots: {combined_stats['screenshots_taken']}.\n"
            f"Output: {combined_output_path}"
        )
        
        print(f"\n{stats_summary}")
        
        return (
            combined_output_path,
            combined_metadata_path,
            combined_stats['files_found'],
            combined_stats['files_downloaded'],
            combined_stats['downloads_succeeded_video'],
            combined_stats['duplicates_removed'],
            combined_stats['duplicates_moved'],
            combined_stats['skipped_small'],
            combined_stats['skipped_platform'],
            combined_stats['skipped_not_media'],
            combined_stats['skipped_already_processed'],
            combined_stats['downloads_failed'],
            combined_stats['screenshots_taken'],
            stats_summary
        )
    
    async def _process_single_url(self, url, output_dir, **kwargs):
        """Process a single URL (existing logic moved here)"""
        # Get important kwargs with defaults
        use_parallel = kwargs.get('use_parallel', True)
        max_workers = kwargs.get('max_workers', 4)

        # Get advanced options
        self.use_stealth_mode = kwargs.get('use_stealth_mode', False)
        reuse_sessions = kwargs.get('reuse_sessions', True)
        session_expiry_hours = kwargs.get('session_expiry_hours', 24.0)
        session_expiry_seconds = int(session_expiry_hours * 3600)
        
        # Get new options
        crawl_links = kwargs.get('crawl_links', False)
        crawl_depth = kwargs.get('crawl_depth', 1)
        max_pages = kwargs.get('max_pages', 10)
        download_audio = kwargs.get('download_audio', False)
        metadata_export_format = kwargs.get('metadata_export_format', 'json')

        # Update save_cookies logic to work with session manager
        if reuse_sessions:
            save_cookies = True
        else:
            save_cookies = kwargs.get('save_cookies', False)
        
        # Initialize variables early
        media_items_from_pages = []    
        final_files_data = []
        downloaded_images_cache = {}
        output_path = None
        session_expiry_hours = kwargs.get('session_expiry_hours', 24.0)
        
        # Convert session expiry to seconds
        session_expiry_seconds = int(session_expiry_hours * 3600)
        
        # Get new options
        crawl_links = kwargs.get('crawl_links', False)
        crawl_depth = kwargs.get('crawl_depth', 1)
        max_pages = kwargs.get('max_pages', 10)
        download_audio = kwargs.get('download_audio', False)
        metadata_export_format = kwargs.get('metadata_export_format', 'json')

        # Update save_cookies logic to work with session manager
        if reuse_sessions:
            save_cookies = True
        else:
            save_cookies = kwargs.get('save_cookies', False)
        
        # Initialize variables early
        media_items_from_pages = []    
        final_files_data = []
        downloaded_images_cache = {}
        output_path = None

        stats = {
            "start_time": self.start_time, "end_time": 0, "duration": 0,
            "urls_found_on_pages": 0, "downloads_attempted": 0,
            "downloads_succeeded_image": 0, "downloads_succeeded_video": 0,
            "duplicates_removed": 0, "duplicates_moved": 0,
            "skipped_small": 0, "skipped_platform": 0, "skipped_not_media": 0, "skipped_already_processed": 0,
            "failed_download": 0, "failed_image_error": 0, "failed_other": 0,
            "metadata_files_saved": 0, "screenshots_taken": 0,
            "files_loaded_from_metadata": 0,
            "strategy_used": "None", "handler_used": "None", "error": None
        }

        # Extract kwargs parameters

        use_direct_pw = kwargs.get('use_direct_playwright', True)
        auth_config_path = kwargs.get('auth_config_path', "")
        self.debug_mode = kwargs.get('debug_mode', False)
        continue_last_run = kwargs.get('continue_last_run', False)
        use_url_as_folder = kwargs.get('use_url_as_folder', True)
        filename_prefix = kwargs.get('filename_prefix', 'file_')
        min_width = kwargs.get('min_width', 0)
        min_height = kwargs.get('min_height', 0)
        max_files = kwargs.get('max_files', 0)
        download_images = kwargs.get('download_images', True)
        download_videos = kwargs.get('download_videos', False)
        extract_metadata = kwargs.get('extract_metadata', True)
        save_metadata_json = kwargs.get('save_metadata_json', True)
        move_duplicates = kwargs.get('move_duplicates', False)
        hash_algorithm = kwargs.get('hash_algorithm', "average_hash")
        timeout_seconds = kwargs.get('timeout_seconds', 60.0)
        handler_timeout = kwargs.get('handler_timeout', 90.0)
        max_api_pages = kwargs.get('max_api_pages', 3)
        wait_for_network_idle = kwargs.get('wait_for_network_idle', False)
        playwright_wait_ms = kwargs.get('playwright_wait_ms', 0)
        interaction_sequence = kwargs.get('interaction_sequence', "")
        use_auto_scroll = kwargs.get('use_auto_scroll', True)
        max_auto_scrolls = kwargs.get('max_auto_scrolls', 50)
        scroll_down_times = kwargs.get('scroll_down_times', 0)
        scroll_delay_ms = kwargs.get('scroll_delay_ms', 500)
        take_screenshot = kwargs.get('take_screenshot', False)
        screenshot_elements = kwargs.get('screenshot_elements', "")
        screenshot_full_page = kwargs.get('screenshot_full_page', False)
        save_cookies = kwargs.get('save_cookies', False)
        same_domain_only = kwargs.get('same_domain_only', True)

        # Create the output directory and load previous data if needed
        initial_file_count = 0
        if continue_last_run:
            output_path, final_files_data, downloaded_images_cache, stats = self.load_previous_run_data(
                output_dir, url, use_url_as_folder, stats
            )
            initial_file_count = len(final_files_data)
            print(f"Continuing last run. Loaded {initial_file_count} files from metadata.")
            for item in final_files_data:
                self.mark_url_processed(item.get('url'))

        if not output_path:
            try:
                handler_instance = self._get_handler_for_url(url)
                output_path = self.create_output_directory(output_dir, url, use_url_as_folder, handler_instance)
                initial_file_count = 0
                print(f"Created output directory: {output_path}")
            except Exception as e:
                stats["error"] = f"Failed to create output directory: {e}"
                print(f"Error: {stats['error']}")
                return ("", "", 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, json.dumps(stats))

        print(f"Saving files to: {output_path}")

        if not self.playwright_available and (use_direct_pw or not self.scrapling_available):
            stats["error"] = "Playwright library not found, which is required for direct interaction or as Scrapling fallback."
            print(f"Error: {stats['error']}")
            return ("", "", 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, json.dumps(stats))
        if not self.imagehash_available and not move_duplicates:
            print("Warning: imagehash library not found. Duplicate detection disabled.")

        if not url or not urlparse(url).scheme in ['http', 'https']:
            stats["error"] = f"Invalid or missing URL: {url}"
            print(f"Error: {stats['error']}")
            return ("", "", 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, json.dumps(stats))

        self.auth_config = self.load_auth_config(auth_config_path)

        handler_instance = self._get_handler_for_url(url)
        if handler_instance:
            # Make sure auth data is accessible to the handler
            handler_instance.scraper = self
            
            # If the handler has a method to load API credentials, call it
            if hasattr(handler_instance, '_load_api_credentials'):
                handler_instance._load_api_credentials()

        # Just use the handler instance we already set up
        stats["handler_used"] = type(handler_instance).__name__
        print(f"Using handler: {stats['handler_used']}")

        # If crawling is enabled, use the new method instead of standard extraction
        if crawl_links and crawl_depth > 0:
            try:
                print(f"Starting link crawling (depth: {crawl_depth}, max pages: {max_pages})")
                
                # Use stealth mode if enabled
                use_stealth = kwargs.get("use_stealth_mode", False)
                if use_stealth:
                    stealth_level = kwargs.get("stealth_mode_level", "basic")
                    print(f"Using stealth mode (level: {stealth_level})")
                    self.pw_resources = await self._init_stealth_playwright(**kwargs)
                else:
                    # Initialize Playwright
                    self.pw_resources = await self._init_direct_playwright(**kwargs)

                if not self.pw_resources:
                    raise RuntimeError("Failed to initialize Playwright.")

                _, _, _, page, _ = self.pw_resources
                
                # Authentication
                if self.auth_config:
                    await self.authenticate_with_site(page, url, self.auth_config, save_cookies, output_path)
                
                # Navigate to page
                wait_until_strategy = "networkidle" if kwargs.get('wait_for_network_idle', False) else "load"
                await page.goto(url, timeout=int(timeout_seconds * 1000), wait_until=wait_until_strategy)
                
                kwargs.pop("same_domain_only", None)  # remove duplicate if present
                # Extract and follow links - pass stats and output_path for direct downloads
                media_items_from_pages = await self._extract_and_follow_links(
                    page=page,
                    base_url=url,
                    max_depth=crawl_depth,
                    current_depth=0,
                    visited_urls=None,
                    same_domain_only=same_domain_only,
                    max_pages=max_pages,
                    stats=stats,
                    output_path=output_path,
                    min_width=min_width,
                    min_height=min_height,
                    extract_metadata=extract_metadata,
                    debug_mode=self.debug_mode,
                    filename_prefix=filename_prefix,
                    hash_algorithm=hash_algorithm,
                    download_images=download_images,
                    download_videos=download_videos,
                    move_duplicates=move_duplicates,
                    max_files=max_files,
                    use_parallel=use_parallel,
                    max_workers=max_workers
                )

                # Store cache flags so _cleanup_resources() can read them later
                self.dump_cache_after_run = kwargs.get("dump_cache_after_run", False)
                self.last_output_path     = kwargs.get("output_path", "")
                
                # Update stats with found items if any
                if media_items_from_pages:
                    print(f"Link crawling found and downloaded {len(media_items_from_pages)} items")
                    final_files_data.extend(media_items_from_pages)
                    stats["files_found"] = len(final_files_data)
                
            except Exception as e:
                print(f"Error during link crawling: {e}")
                traceback.print_exc()
                stats["error"] = f"Crawling Error: {e}"
                media_items_from_pages = []
        else:
            try:
                strategy_chosen = "None"
                # 1. If the handler requires API, always use API
                if hasattr(handler_instance, "requires_api") and handler_instance.requires_api():
                    print(f"Handler {type(handler_instance).__name__} requires API. Forcing API extraction.")
                    strategy_chosen = "API"
                    stats["strategy_used"] = strategy_chosen
                    media_items_from_pages = await self._scrape_with_api(
                        handler_instance, url, **kwargs, output_path=output_path
                    )
                # 2. If the handler prefers API, use it if possible
                elif handler_instance.prefers_api():
                    strategy_chosen = "API"
                    stats["strategy_used"] = strategy_chosen
                    media_items_from_pages = await self._scrape_with_api(
                        handler_instance, url, **kwargs, output_path=output_path
                    )
                # 3. Otherwise, use Playwright or Scrapling fallback
                elif use_direct_pw and self.playwright_available:
                    strategy_chosen = "Direct Playwright"
                    stats["strategy_used"] = strategy_chosen
                    media_items_from_pages = await self._scrape_with_direct_playwright(
                        url, handler_instance, **kwargs, output_path=output_path, stats=stats
                    )
                elif self.scrapling_available:
                    strategy_chosen = "Scrapling Fallback"
                    stats["strategy_used"] = strategy_chosen
                    media_items_from_pages = await self._scrape_with_scrapling(
                        url, handler_instance, **kwargs, output_path=output_path, stats=stats
                    )
                else:
                    stats["error"] = "No suitable scraping strategy available (Playwright/Scrapling missing or disabled)."
                    print(f"Error: {stats['error']}")
                    raise RuntimeError(stats["error"])

                print(f"Strategy '{strategy_chosen}' finished. Found {len(media_items_from_pages)} potential media items.")
                stats["urls_found_on_pages"] = len(media_items_from_pages)

                if not media_items_from_pages:
                    print("No media items found by the scraping strategy.")
                else:
                    download_kwargs = {
                        'filename_prefix': filename_prefix,
                        'min_width': min_width,
                        'min_height': min_height,
                        'hash_algorithm': hash_algorithm,
                        'download_images': download_images,
                        'download_videos': download_videos,
                        'move_duplicates': move_duplicates,
                        'max_files': max_files,
                        'save_metadata_json': save_metadata_json,
                        'initial_file_count': initial_file_count,
                        'url': url,
                        'downloaded_images_cache': downloaded_images_cache,
                        'extract_metadata': extract_metadata,
                        'same_domain_only': same_domain_only
                    }
                    
                    if use_parallel:
                        newly_downloaded_data, downloaded_images_cache = await self._process_download_queue_parallel(
                            media_items_from_pages, output_path, stats, max_workers=max_workers, **download_kwargs
                        )
                    else: 
                        newly_downloaded_data, downloaded_images_cache = await self._process_download_queue(
                            media_items_from_pages, output_path, stats, **download_kwargs
                        )
                    
                    # Add newly downloaded files to final data for statistics
                    if newly_downloaded_data:
                        final_files_data.extend(newly_downloaded_data)
                        print(f"Added {len(newly_downloaded_data)} successfully downloaded files to final data")

                # Add audio extraction if enabled
                if download_audio and PLAYWRIGHT_AVAILABLE and self.pw_resources:
                    try:
                        _, _, _, page, _ = self.pw_resources
                        audio_items = await self._extract_audio_sources(page)
                        if audio_items:
                            print(f"Found {len(audio_items)} audio items")
                            media_items_from_pages.extend(audio_items)
                    except Exception as e:
                        print(f"Error extracting audio: {e}")
            except Exception as e:
                stats["error"] = f"Scraping failed: {type(e).__name__}: {e}"
                print(f"Error during scraping process: {stats['error']}")
                traceback.print_exc()
            finally:
                # Cleanup
                await self._cleanup_resources()

        # Finalization (same as before)
        stats["end_time"] = time.time()
        stats["duration"] = round(stats["end_time"] - stats["start_time"], 2)
        stats["files_downloaded"] = stats["downloads_succeeded_image"] + stats["downloads_succeeded_video"]
        stats["files_found"] = len(final_files_data)

        # Safely handle metadata saving
        metadata_json_path = ""
        if output_path and isinstance(output_path, str):
            try:
                metadata_json_path = os.path.join(output_path, self.metadata_file)
                self.save_download_metadata(output_path, url, final_files_data)
                print(f"Saved final metadata to: {metadata_json_path}")
                if save_metadata_json and final_files_data:
                    try:
                        self.export_metadata(final_files_data, output_path, format=metadata_export_format)
                    except Exception as e:
                        print(f"Error exporting metadata: {e}")
            except Exception as meta_save_e:
                print(f"Error saving final metadata: {meta_save_e}")
                stats["error"] = stats.get("error", "") + f" | Metadata Save Error: {meta_save_e}"
                metadata_json_path = ""
        else:
            print("Warning: Output path was not determined. Skipping final metadata save.")
            if not stats["error"]:
                stats["error"] = "Output path could not be determined."

        # Prepare stats summary string (same as before)
        safe_output_path_str = str(output_path) if output_path else "N/A"
        summary = (
            f"Finished in {stats['duration']}s. Strategy: {stats['strategy_used']}, Handler: {stats['handler_used']}.\n"
            f"Found: {stats['urls_found_on_pages']}, Attempted: {stats['downloads_attempted']}, Kept: {stats['files_found']} "
            f"(Img: {stats['downloads_succeeded_image']}, Vid: {stats['downloads_succeeded_video']}).\n"
            f"Skipped (Small/Platform/NotMedia/Processed): {stats['skipped_small']}/{stats['skipped_platform']}/{stats['skipped_not_media']}/{stats['skipped_already_processed']}.\n"
            f"Duplicates (Removed/Moved): {stats['duplicates_removed']}/{stats['duplicates_moved']}.\n"
            f"Failed: {stats['failed_download']}, Screenshots: {stats['screenshots_taken']}.\n"
            f"Output: {safe_output_path_str}"
        )
        if stats["error"]:
            summary += f"\nError: {stats['error']}"
        print(summary)

        # Return values matching RETURN_TYPES
        return_output_path = output_path if output_path else ""
        return (
            return_output_path, metadata_json_path,
            stats["files_found"], stats["files_downloaded"], stats["downloads_succeeded_video"],
            stats["duplicates_removed"], stats["duplicates_moved"],
            stats["skipped_small"], stats["skipped_platform"], stats["skipped_not_media"], stats["skipped_already_processed"],
            stats["failed_download"], stats["screenshots_taken"],
            summary
        )

    # --- Helper Methods ---
    def _get_handler_for_url(self, url):
        """Get the appropriate handler for the given URL"""
        print(f"Finding handler for URL: {url}")
        
        for handler_name, HandlerClass in self.site_handlers.items():
            try:
                can_handle = HandlerClass.can_handle(url)
                if can_handle:
                    print(f"Selected handler: {handler_name}")
                    handler_instance = HandlerClass(url, self)
                    return handler_instance
            except Exception as e:
                print(f"Error testing handler {handler_name}: {e}")
                
        # Default fallback if no handler is found
        print("No specific handler found, using GenericWebsiteWithAuthHandler")
        return GenericWebsiteWithAuthHandler(url, self)

    # -- Live network sniffer -------------------------------------------------
    async def _attach_response_sniffer(self, page, output_dir):
        """
        Streams every image/video response body to <output_dir>.
        Called once per page.
        """
        from pathlib import Path
        import mimetypes, hashlib, os

        Path(output_dir).mkdir(parents=True, exist_ok=True)

        async def _handler(resp):
            try:
                mime = resp.headers.get("content-type", "")
                if not mime.startswith(("image/", "video/")):
                    return
                body = await resp.body()
                ext = mimetypes.guess_extension(mime.split(";")[0]) or ".bin"
                name = hashlib.sha1(resp.url.encode()).hexdigest()[:12] + ext
                fn  = Path(output_dir) / name
                if not fn.exists():
                    fn.write_bytes(body)
                    if self.debug_mode:
                        print(f"[sniffer] {resp.url}  →  {fn.name}")
            except Exception as e:
                if self.debug_mode:
                    print(f"[sniffer] {e}  on  {resp.url}")

        page.on("response", _handler)



    # --- Strategy Methods ---
    async def _scrape_with_api(self, handler, url, **kwargs):
        """Scrape using the handler's API method (async version)."""
        print("Attempting API scraping strategy...")
        print(f"Handler type: {type(handler).__name__}")
        
        try:
            # Pass relevant kwargs to the handler's API method
            api_kwargs = {
                'max_pages': kwargs.get('max_api_pages', 3),
                'timeout': kwargs.get('handler_timeout', 90.0),
            }
            
            # For BskyHandler, ensure auth config is loaded
            if type(handler).__name__ == 'BskyHandler':
                print("BskyHandler detected - ensuring authentication setup...")
                if hasattr(handler, '_load_api_credentials'):
                    handler._load_api_credentials()
            
            # Check if the handler has an async API method
            if hasattr(handler, 'extract_api_data_async'):
                print("Using async API method...")
                media_items = await handler.extract_api_data_async(**api_kwargs)
            else:
                # Fall back to sync version if available
                print("Using sync API method...")
                media_items = handler.extract_api_data(**api_kwargs)
            
            print(f"API scraping found {len(media_items)} items.")
            return media_items
        except NotImplementedError:
            print(f"Handler {type(handler).__name__} prefers API but does not implement extract_api_data.")
            return []
        except Exception as e:
            print(f"Error during API scraping: {e}")
            traceback.print_exc()
            return []

    async def _scrape_with_direct_playwright(self, url, handler, **kwargs):
        """Scrape using direct Playwright browser interaction (async)."""
        print("Attempting Direct Playwright scraping strategy...")
        media_items = []
        page = None
        output_path = kwargs.get('output_path', '')
        stats = kwargs.get('stats', {})

        try:
            # Initialize Playwright
            self.pw_resources = await self._init_direct_playwright(**kwargs)
            if not self.pw_resources:
                raise RuntimeError("Failed to initialize Playwright.")
            pw_instance, browser, context, page, user_data_dir = self.pw_resources

            if kwargs.get("capture_network_stream", False):
                await self._attach_response_sniffer(page, output_path)

            # Authentication
            if self.auth_config:
                await self.authenticate_with_site(page, url, self.auth_config, kwargs.get('save_cookies', False), output_path)

            # Navigate to page
            timeout_ms = int(kwargs.get('timeout_seconds', 60.0) * 1000)
            wait_until_strategy = "networkidle" if kwargs.get('wait_for_network_idle', False) else "load"
            print(f"Navigating to {url} with timeout {timeout_ms}ms, wait_until='{wait_until_strategy}'")
            await page.goto(url, timeout=timeout_ms, wait_until=wait_until_strategy)
            print("Navigation complete.")

            # Optional extra wait
            extra_wait = kwargs.get('playwright_wait_ms', 0)
            if extra_wait > 0:
                print(f"Performing extra wait: {extra_wait}ms")
                await page.wait_for_timeout(extra_wait)

            # Perform interactions (scrolling, clicks, etc.)
            await self._perform_page_interactions(page, **kwargs)

            # Take initial screenshot if requested
            if kwargs.get('take_screenshot', False):
                await self.take_screenshots(page, output_path, kwargs.get('screenshot_elements', ""), kwargs.get('screenshot_full_page', False), stats)

            # Extract media using the handler
            print(f"Calling handler '{type(handler).__name__}' for Playwright extraction...")
            handler_kwargs = {
                'min_width': kwargs.get('min_width', 0),
                'min_height': kwargs.get('min_height', 0),
                'extract_metadata': kwargs.get('extract_metadata', True),
                'same_domain_only': kwargs.get('same_domain_only', True),
                'timeout': kwargs.get('handler_timeout', 90.0),
                # --- Add these for scrolling ---
                'max_scrolls': kwargs.get('max_auto_scrolls', 50),
                'scroll_delay_ms': kwargs.get('scroll_delay_ms', 1000),
                'scroll_container_selector': kwargs.get('scroll_container_selector', None),  # Pass from UI or preset
            }
            media_items = await handler.extract_with_direct_playwright(page, **handler_kwargs)
            
            # Try generic extraction if handler found nothing and debug mode is on
            if not media_items and self.debug_mode:
                print("Handler found no items. Trying generic extraction as fallback...")
                generic_items = await self._extract_media_from_pw_page(page, url, **kwargs)
                if generic_items:
                    print(f"Generic extraction found {len(generic_items)} items")
                    media_items = generic_items
                
                # Take debug screenshot if nothing found
                if not media_items:
                    debug_ss_path = os.path.join(output_path, "debug_extraction_failure.png")
                    await page.screenshot(path=debug_ss_path, full_page=True)
                    print(f"Saved debug screenshot to {debug_ss_path}")

            # Save cookies if requested AFTER interactions and extraction
            if kwargs.get('save_cookies', False) and self.auth_config:
                domain = urlparse(url).netloc
                site_config = self.get_site_auth_config(domain, self.auth_config)
                if site_config:
                    cookie_path = os.path.join(output_path, f"{domain}_cookies.json")
                    try:
                        await context.storage_state(path=cookie_path)
                        print(f"Saved cookies to {cookie_path}")
                    except Exception as cookie_error:
                        print(f"Error saving cookies: {cookie_error}")

        except Exception as e:
            print(f"Error during Direct Playwright scraping: {e}")
            traceback.print_exc()
            stats['error'] = f"Playwright Error: {e}"
            # Try to take a screenshot on error if debug mode is on
            if self.debug_mode and page:
                try:
                    error_screenshot_path = os.path.join(output_path, "debug_playwright_error.png")
                    await page.screenshot(path=error_screenshot_path, full_page=True)
                    print(f"Saved error screenshot to {error_screenshot_path}")
                except Exception as ss_error:
                    print(f"Could not take error screenshot: {ss_error}")

        # Note: Cleanup happens in the main _async_scrape_files finally block
        return media_items


    async def _scrape_with_scrapling(self, url, handler, **kwargs):
        """Scrape using the Scrapling library (async version)."""
        print("Attempting Scrapling scraping strategy...")
        if not SCRAPLING_AVAILABLE:
            print("Scrapling library not available.")
            return []

        media_items = []
        output_path = kwargs.get('output_path', '')
        stats = kwargs.get('stats', {})

        try:
            # Configure Scrapling Adaptor (Scrapling itself isn't async, so we run it in thread)
            import concurrent.futures
            loop = asyncio.get_event_loop()
            
            with concurrent.futures.ThreadPoolExecutor() as pool:
                response = await loop.run_in_executor(
                    pool, 
                    lambda: Adaptor(fetcher=PlayWrightFetcher(headless=True)).get(
                        url, 
                        timeout=kwargs.get('timeout_seconds', 60.0)
                    )
                )

            if not response or not response.ok:
                print(f"Scrapling failed to fetch URL: {response.status_code if response else 'No response'}")
                stats['error'] = f"Scrapling Fetch Error: {response.status_code if response else 'No response'}"
                return []

            print("Scrapling fetch successful.")

            # Extract media using the handler - updated to always use async pattern
            print(f"Calling handler '{type(handler).__name__}' for Scrapling extraction...")
            handler_kwargs = {
                'min_width': kwargs.get('min_width', 0),
                'min_height': kwargs.get('min_height', 0),
                'extract_metadata': kwargs.get('extract_metadata', True),
                'same_domain_only': kwargs.get('same_domain_only', True),
                'timeout': kwargs.get('handler_timeout', 90.0),
            }
            
            # Always use the async extract_with_scrapling method
            media_items = await handler.extract_with_scrapling(response, **handler_kwargs)

        except Exception as e:
            print(f"Error during Scrapling scraping: {e}")
            traceback.print_exc()
            stats['error'] = f"Scrapling Error: {e}"

        return media_items


    async def _extract_and_follow_links(
        self,
        page: AsyncPage,
        base_url,
        max_depth=1,
        current_depth=0,
        visited_urls=None,
        same_domain_only=True,
        max_pages=10,
        stats=None,
        output_path=None,
        *,
        min_width=0,
        min_height=0,
        extract_metadata=True,
        debug_mode=False,
        filename_prefix="file_",
        hash_algorithm="average_hash",
        download_images=True,
        download_videos=False,
        move_duplicates=False,
        max_files=0,
        use_parallel=True,
        max_workers=4
    ):
        """Extract content from the current page and follow links (async version)."""
        if visited_urls is None:
            visited_urls = set()

        # Check if we've reached the maximum depth or page count
        if current_depth > max_depth or len(visited_urls) >= max_pages:
            return []

        # Get current URL and ensure it's properly normalized
        current_url = page.url
        # Normalize URL to prevent slight variations causing duplicate processing
        normalized_url = self._normalize_url(current_url)
        
        # Check if URL was already visited
        if normalized_url in visited_urls:
            print(f"Skipping already visited URL: {current_url}")
            return []
            
        # Mark URL as visited BEFORE processing
        visited_urls.add(normalized_url)
        print(f"Processing page at depth {current_depth}: {current_url}")

        media_items = []
        media_items_for_download = []

        try:
            handler_instance = self._get_handler_for_url(current_url)
            handler_instance.scraper = self

            if hasattr(handler_instance, '_load_api_credentials'):
                handler_instance._load_api_credentials()

            if output_path and not hasattr(self, 'output_path'):
                self.output_path = output_path

            if stats and not hasattr(self, 'stats'):
                self.stats = stats

            handler_kwargs = {
                'min_width': min_width,
                'min_height': min_height,
                'extract_metadata': extract_metadata,
                'same_domain_only': same_domain_only,
                'timeout': 90.0,
                'debug_mode': debug_mode
            }

            try:
                page_media_items = await handler_instance.extract_with_direct_playwright(page, **handler_kwargs)
                media_items.extend(page_media_items)
            except Exception as e:
                print(f"Error extracting with handler: {e}")
                traceback.print_exc()

            if not media_items and debug_mode:
                try:
                    generic_items = await self._extract_media_from_pw_page(page, current_url)
                    if generic_items:
                        print(f"Found {len(generic_items)} items with generic extraction")
                        media_items.extend(generic_items)
                except Exception as e:
                    print(f"Error during generic extraction: {e}")

            if media_items and output_path:
                print(f"Found {len(media_items)} media items, processing for download")

                download_kwargs = {
                    'filename_prefix': filename_prefix,
                    'min_width': min_width,
                    'min_height': min_height,
                    'hash_algorithm': hash_algorithm,
                    'download_images': download_images,
                    'download_videos': download_videos,
                    'move_duplicates': move_duplicates,
                    'max_files': max_files,
                    'save_metadata_json': True,
                    'initial_file_count': 0,
                    'url': current_url,
                    'downloaded_images_cache': {},
                    'extract_metadata': extract_metadata,
                    'same_domain_only': same_domain_only
                }

                try:
                    if use_parallel:
                        downloaded_data, _ = await self._process_download_queue_parallel(
                            media_items, output_path, stats, max_workers=max_workers, **download_kwargs
                        )
                    else:
                        downloaded_data, _ = await self._process_download_queue(
                            media_items, output_path, stats, **download_kwargs
                        )

                    if downloaded_data:
                        print(f"Successfully downloaded {len(downloaded_data)} items from {current_url}")
                        media_items_for_download.extend(downloaded_data)
                except Exception as download_err:
                    print(f"Error during download process: {download_err}")
                    traceback.print_exc()

        except Exception as e:
            print(f"Error extracting from {current_url}: {e}")

        if current_depth == max_depth:
            return media_items_for_download

        links = []
        try:
            link_locator = page.locator("a[href]:visible")
            link_count = await link_locator.count()

            for i in range(min(link_count, 50)):
                link = link_locator.nth(i)
                href = await link.get_attribute("href")

                if not href or href.startswith("#") or href.startswith("javascript:"):
                    continue

                if not href.startswith(("http://", "https://")):
                    href = urljoin(current_url, href)

                base_domain = urlparse(base_url).netloc
                link_domain = urlparse(href).netloc

                if same_domain_only and link_domain != base_domain:
                    continue

                if href not in visited_urls:
                    links.append(href)

            def link_priority(url):
                lower_url = url.lower()
                if any(term in lower_url for term in ['gallery', 'exhibit', 'artwork', 'asset', 'collection']):
                    return 0
                if any(term in lower_url for term in ['login', 'about', 'contact', 'terms', 'policy']):
                    return 2
                return 1

            links.sort(key=link_priority)

        except Exception as e:
            print(f"Error extracting links from {current_url}: {e}")

        link_count = min(len(links), max_pages - len(visited_urls))
        if link_count > 0:
            print(f"Following {link_count} links at depth {current_depth}")

            for i, link in enumerate(links[:link_count]):
                try:
                    print(f"  Following link {i+1}/{link_count}: {link}")
                    await page.goto(link, timeout=30000)
                    await page.wait_for_load_state("domcontentloaded")
                    await self._auto_scroll_page(page, max_scrolls=2, delay_ms=500)

                    sub_items = await self._extract_and_follow_links(
                        page=page,
                        base_url=base_url,
                        max_depth=max_depth,
                        current_depth=current_depth + 1,
                        visited_urls=visited_urls,
                        same_domain_only=same_domain_only,
                        max_pages=max_pages,
                        stats=stats,
                        output_path=output_path,
                        min_width=min_width,
                        min_height=min_height,
                        extract_metadata=extract_metadata,
                        debug_mode=debug_mode,
                        filename_prefix=filename_prefix,
                        hash_algorithm=hash_algorithm,
                        download_images=download_images,
                        download_videos=download_videos,
                        move_duplicates=move_duplicates,
                        max_files=max_files,
                        use_parallel=use_parallel,
                        max_workers=max_workers
                    )

                    media_items_for_download.extend(sub_items)
                    self._rate_limit(urlparse(link).netloc)

                except Exception as e:
                    print(f"Error following link {link}: {e}")

        return media_items_for_download

    def _carve_chrome_cache(self, cache_dir, output_dir):
        """
        Very simple Chrome SimpleCache carver – saves every image/* object.
        """
        import mimetypes, re, hashlib, pathlib
        CRLF = b"\r\n\r\n"
        ct_rx = re.compile(rb"(?i)^content-type:\s*([^\s;]+)", re.M)
        cache_dir = pathlib.Path(cache_dir)
        out      = pathlib.Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        for blob in cache_dir.glob("f_*"):
            data = blob.read_bytes()
            hdr_pos = data.find(b"HTTP/")
            if hdr_pos == -1:
                continue
            hdr_end = data.find(CRLF, hdr_pos)
            if hdr_end == -1:
                continue
            m = ct_rx.search(data, hdr_pos, hdr_end)
            if not m:
                continue
            mime = m.group(1).decode().lower()
            if not mime.startswith("image/"):
                continue
            payload = data[hdr_end+4:]
            ext = mimetypes.guess_extension(mime) or ".bin"
            name = hashlib.sha1(payload).hexdigest()[:12] + ext
            fn   = out / name
            if not fn.exists():
                fn.write_bytes(payload)
                if self.debug_mode:
                    print(f"[cache] {fn.name}")


    def _normalize_url(self, url):
        """
        Normalize a URL to prevent slight variations causing duplicate processing.
        
        Args:
            url: URL to normalize
            
        Returns:
            Normalized URL string
        """
        try:
            parsed = urlparse(url)
            
            # Remove trailing slashes
            path = parsed.path.rstrip('/')
            
            # Remove common tracking parameters
            query_params = {}
            if parsed.query:
                for param in parsed.query.split('&'):
                    if '=' in param:
                        key, value = param.split('=', 1)
                        # Skip common tracking parameters
                        if key.lower() not in ['utm_source', 'utm_medium', 'utm_campaign', 
                                            'fbclid', 'gclid', 'msclkid', '_ga', 
                                            'ref', 'source']:
                            query_params[key] = value
            
            # Build new query string
            query = '&'.join([f"{k}={v}" for k, v in sorted(query_params.items())])
            
            # Normalize and rebuild URL
            normalized = f"{parsed.scheme}://{parsed.netloc}{path}"
            if query:
                normalized += f"?{query}"
                
            return normalized
        except Exception as e:
            print(f"Error normalizing URL {url}: {e}")
            return url

    def _get_highest_res_from_srcset(self, srcset):
        """Parse srcset attribute and return the highest resolution image URL."""
        if not srcset:
            return None
            
        try:
            highest_width = 0
            highest_res_url = None
            
            # Split the srcset into individual entries
            entries = [entry.strip() for entry in srcset.split(',')]
            
            for entry in entries:
                parts = entry.split()
                if len(parts) != 2:  # Must have URL and descriptor
                    continue
                    
                url, descriptor = parts
                
                # Handle width descriptors (e.g., 1920w)
                if descriptor.endswith('w'):
                    try:
                        width = int(descriptor[:-1])
                        if width > highest_width:
                            highest_width = width
                            highest_res_url = url
                    except ValueError:
                        continue
                        
                # Handle density descriptors (e.g., 2x)
                elif descriptor.endswith('x'):
                    try:
                        density = float(descriptor[:-1])
                        width_equivalent = int(density * 1000)
                        if width_equivalent > highest_width:
                            highest_width = width_equivalent
                            highest_res_url = url
                    except ValueError:
                        continue
                        
            return highest_res_url
            
        except Exception as e:
            print(f"Error parsing srcset: {e}")
            return None

    # --- Helper Methods ---


    async def _cleanup_resources(self):
        """Cleans up Playwright resources with improved error handling."""
        if not self.pw_resources:
            return
                
        print("Cleaning up Playwright resources...")
        pw, browser, context, page, user_data_dir = self.pw_resources

        cleanup_success = True
        
        # Helper function to handle cleanup with better error reporting
        async def cleanup_component(component, close_method, name):
            nonlocal cleanup_success
            if not component:
                return True
                
            try:
                # Different components have different close methods
                if close_method == "close" and hasattr(component, "is_closed") and callable(getattr(component, "is_closed")):
                    if not component.is_closed():
                        await getattr(component, "close")()
                elif close_method == "stop":
                    await component.stop()
                elif close_method == "close":
                    await component.close()
                    
                return True
            except Exception as e:
                cleanup_success = False
                print(f"Error cleaning up {name}: {e}")
                if self.debug_mode:
                    traceback.print_exc()
                return False
        
        # Clean up in reverse order of creation (page → context → browser → playwright)
        await cleanup_component(page, "close", "page")
        await cleanup_component(context, "close", "context")
        await cleanup_component(browser, "close", "browser")
        await cleanup_component(pw, "stop", "playwright instance")
        
        from pathlib import Path
        if self.pw_user_data_dir and getattr(self, "dump_cache_after_run", False):
            cache_dir = Path(self.pw_user_data_dir) / "Default" / "Cache" / "Cache_Data"
            if cache_dir.exists():
                self._carve_chrome_cache(cache_dir, getattr(self, "last_output_path", ""))
            shutil.rmtree(self.pw_user_data_dir, ignore_errors=True)

        # Reset the resources reference
        self.pw_resources = None
        
        if cleanup_success:
            print("All Playwright resources successfully cleaned up.")
        else:
            print("Warning: Some Playwright resources may not have been properly cleaned up.")

    async def _init_stealth_playwright(self, **kwargs):
        """
        Initialize a Playwright instance with stealth capabilities.
        
        Args:
            **kwargs: Additional options for initialization including:
                - stealth_mode_level: 'basic', 'enhanced', 'extreme' (default: 'basic')
                - enhanced_stealth: bool (for backward compatibility)
                - mobile_emulation: bool (default: False)
                - headful: bool (default: False) - run in headful mode for debugging
                
        Returns:
            Tuple of (playwright_instance, browser, context, page) or None on failure
        """
        if not PLAYWRIGHT_AVAILABLE:
            print("Playwright library not available.")
            return None
            
        try:
            import tempfile
            import pathlib

            user_data_dir = None
            use_persistent = kwargs.get("dump_cache_after_run", False)

            stealth_level = kwargs.get('stealth_mode_level', 'basic')
            if kwargs.get('enhanced_stealth', False) and stealth_level == 'basic':
                stealth_level = 'enhanced'
            print(f"Initializing stealth Playwright (level: {stealth_level})...")

            playwright_instance = await async_playwright().start()
            if not playwright_instance:
                print("Failed to start Playwright")
                return None

            user_agent = self._get_random_user_agent()
            browser_args = [
                '--disable-blink-features=AutomationControlled',
                '--disable-web-security',
                '--no-sandbox'
            ]
            if stealth_level in ['enhanced', 'extreme']:
                browser_args.extend([
                    '--disable-features=IsolateOrigins,site-per-process',
                    '--disable-site-isolation-trials',
                    '--disable-features=BlockInsecurePrivateNetworkRequests',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage'
                ])
            if stealth_level == 'extreme':
                browser_args.extend([
                    '--disable-accelerated-2d-canvas',
                    '--disable-gpu',
                    '--no-first-run',
                    '--no-service-autorun',
                    '--password-store=basic',
                    '--use-mock-keychain',
                    '--disable-extensions'
                ])

            context_options = {
                "user_agent": user_agent,
                "viewport": {"width": 5120, "height": 2880},
                "device_scale_factor": 1.0
            }
            if stealth_level in ['enhanced', 'extreme']:
                context_options.update({
                    "locale": "en-US",
                    "timezone_id": "America/New_York",
                    "color_scheme": "light"
                })
            if kwargs.get('mobile_emulation', False):
                context_options.update({
                    "has_touch": True,
                    "is_mobile": True
                })
            else:
                context_options.update({
                    "has_touch": False,
                    "is_mobile": False
                })

            # --- Persistent context support ---
            if use_persistent:
                user_data_dir = pathlib.Path(tempfile.mkdtemp(prefix="pwprof_"))
                browser = await playwright_instance.chromium.launch_persistent_context(
                    user_data_dir=str(user_data_dir),
                    headless=not kwargs.get('headful', False),
                    args=browser_args,
                    **context_options
                )
                context = browser  # persistent context IS the context
                page = await context.new_page()
            else:
                browser = await playwright_instance.chromium.launch(
                    headless=not kwargs.get('headful', False),
                    args=browser_args
                )
                context = await browser.new_context(**context_options)
                page = await context.new_page()

            # Add stealth scripts based on level
            basic_stealth_script = """
            () => {
                // Pass WebDriver test
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => false,
                    configurable: true
                });
                
                // Pass Chrome test
                window.chrome = {
                    runtime: {},
                };
            }
            """
            
            enhanced_stealth_script = """
            () => {
                // Pass WebDriver test
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => false,
                    configurable: true
                });
                
                // Pass Chrome test
                window.chrome = {
                    runtime: {},
                };
                
                // Pass permissions test
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ?
                        Promise.resolve({ state: Notification.permission }) :
                        originalQuery(parameters)
                );
                
                // Add language and plugins
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['en-US', 'en'],
                    configurable: true
                });
                
                // Add hardware concurrency
                Object.defineProperty(navigator, 'hardwareConcurrency', {
                    get: () => 8,
                    configurable: true
                });
                
                // Override platform
                Object.defineProperty(navigator, 'platform', {
                    get: () => 'Win32',
                    configurable: true
                });
            }
            """
            
            extreme_stealth_script = """
            () => {
                // Pass WebDriver test
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => false,
                    configurable: true
                });
                
                // Pass Chrome test
                window.chrome = {
                    runtime: {},
                };
                
                // Pass permissions test
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ?
                        Promise.resolve({ state: Notification.permission }) :
                        originalQuery(parameters)
                );
                
                // Add language and plugins
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['en-US', 'en'],
                    configurable: true
                });
                
                // Add hardware concurrency
                Object.defineProperty(navigator, 'hardwareConcurrency', {
                    get: () => 8,
                    configurable: true
                });
                
                // Override platform
                Object.defineProperty(navigator, 'platform', {
                    get: () => 'Win32',
                    configurable: true
                });
                
                // Spoof plugins
                const originalPlugins = Object.getOwnPropertyDescriptor(Navigator.prototype, 'plugins');
                if (originalPlugins) {
                    Object.defineProperty(navigator, 'plugins', {
                        get: () => {
                            const plugins = {
                                length: 5,
                                item: () => null,
                                namedItem: () => null,
                                refresh: () => {}
                            };
                            for (let i = 0; i < 5; i++) {
                                plugins[i] = { name: `Plugin ${i}`, description: `Description ${i}` };
                            }
                            return plugins;
                        },
                        configurable: true
                    });
                }
                
                // Spoof canvas fingerprinting
                const originalGetContext = HTMLCanvasElement.prototype.getContext;
                if (originalGetContext) {
                    HTMLCanvasElement.prototype.getContext = function(type) {
                        const context = originalGetContext.apply(this, arguments);
                        if (type === '2d') {
                            const originalGetImageData = context.getImageData;
                            context.getImageData = function() {
                                const imageData = originalGetImageData.apply(this, arguments);
                                // Add slight random noise to prevent fingerprinting
                                const pixels = imageData.data;
                                for (let i = 0; i < pixels.length; i += 4) {
                                    pixels[i] = pixels[i] + (Math.random() < 0.5 ? 0 : 1);
                                    pixels[i+1] = pixels[i+1] + (Math.random() < 0.5 ? 0 : 1);
                                    pixels[i+2] = pixels[i+2] + (Math.random() < 0.5 ? 0 : 1);
                                }
                                return imageData;
                            };
                        }
                        return context;
                    };
                }
                
                // Use webGL renderer spoofing
                const getParameter = WebGLRenderingContext.prototype.getParameter;
                WebGLRenderingContext.prototype.getParameter = function(parameter) {
                    // UNMASKED_VENDOR_WEBGL
                    if (parameter === 37445) {
                        return 'Intel Inc.';
                    }
                    // UNMASKED_RENDERER_WEBGL
                    if (parameter === 37446) {
                        return 'Intel Iris OpenGL Engine';
                    }
                    return getParameter.apply(this, arguments);
                };
            }
            """
            
            # Auto-click cookie consent script for extreme mode
            cookie_consent_script = """
            () => {
                // Auto-click cookie consent buttons after page loads
                setTimeout(() => {
                    const cookieSelectors = [
                        'button[aria-label*="Accept"]',
                        'button[aria-label*="Agree"]',
                        'button[aria-label*="consent"]',
                        'button:has-text("Accept all")',
                        'button:has-text("Accept cookies")',
                        'button:has-text("I agree")',
                        '.cookie-banner button',
                        '#consent-modal button'
                    ];
                    
                    cookieSelectors.forEach(selector => {
                        const button = document.querySelector(selector);
                        if (button && button.offsetParent !== null) {
                            console.log('Auto-clicking cookie consent button');
                            button.click();
                        }
                    });
                }, 3000);
            }
            """
            
            basic_stealth_script = """ ... """
            enhanced_stealth_script = """ ... """
            extreme_stealth_script = """ ... """
            cookie_consent_script = """ ... """

            if stealth_level == 'basic':
                await context.add_init_script(basic_stealth_script)
            elif stealth_level == 'enhanced':
                await context.add_init_script(enhanced_stealth_script)
            elif stealth_level == 'extreme':
                await context.add_init_script(extreme_stealth_script)
                await context.add_init_script(cookie_consent_script)

            context.set_default_timeout(kwargs.get('timeout_ms', 60000))
            context.set_default_navigation_timeout(kwargs.get('timeout_ms', 60000))

            
            # Create page
            page = await context.new_page()
            
            if not page:
                print("Failed to create page")
                if context:
                    await context.close()
                if browser:
                    await browser.close()
                if playwright_instance:
                    await playwright_instance.stop()
                return None
            
            # Handle dialogs automatically
            page.on("dialog", lambda dialog: dialog.dismiss())

            # Store for cleanup
            if use_persistent:
                self.pw_user_data_dir = str(user_data_dir)
            else:
                self.pw_user_data_dir = None

            print(f"Stealth Playwright initialized (level: {stealth_level}) with user agent: {user_agent[:50]}...")
            return (playwright_instance, browser, context, page, user_data_dir)

        except Exception as e:
            print(f"Failed to initialize stealth Playwright: {e}")
            traceback.print_exc()
            
            # Clean up resources
            if 'page' in locals() and page:
                try:
                    await page.close()
                except:
                    pass
            if 'context' in locals() and context:
                try:
                    await context.close()
                except:
                    pass
            if 'browser' in locals() and browser:
                try:
                    await browser.close()
                except:
                    pass
            if 'playwright_instance' in locals() and playwright_instance:
                try:
                    await playwright_instance.stop()
                except:
                    pass
            
            return None
            

    async def _process_download_queue(self, media_items_to_process, output_path, stats, **kwargs):
        """Downloads files from the queue, performs deduplication, and saves metadata (async version)."""
        downloaded_files_data = []
        processed_count = 0
        initial_file_count = kwargs.get('initial_file_count', 0)
        max_files = kwargs.get('max_files', 0)
        downloaded_images_cache = kwargs.get('downloaded_images_cache', {})

        # Create duplicates folder if needed
        move_duplicates = kwargs.get('move_duplicates', False)
        duplicates_folder = None
        if move_duplicates:
            duplicates_folder = os.path.join(output_path, "_duplicates")
            os.makedirs(duplicates_folder, exist_ok=True)

        total_items = len(media_items_to_process)
        print(f"Processing download queue: {total_items} items found.")

        for index, item_data in enumerate(media_items_to_process):
            # Check max files limit (considering files from previous run)
            current_total_files = initial_file_count + len(downloaded_files_data)
            if max_files > 0 and current_total_files >= max_files:
                print(f"Reached max files limit ({max_files}). Stopping download queue.")
                break

            item_url = item_data.get('url')
            if not item_url:
                print(f"Skipping item {index + 1}/{total_items}: Missing URL.")
                stats["skipped_not_media"] += 1
                continue

            # Check if already processed in this run or loaded from previous
            if self.check_url_processed(item_url):
                print(f"Skipping item {index + 1}/{total_items}: Already processed URL {item_url}")
                stats["skipped_already_processed"] += 1
                continue

            # Check domain restrictions if same_domain_only is enabled
            if kwargs.get('same_domain_only', True):
                item_domain = urlparse(item_url).netloc
                base_url = kwargs.get('url', '')
                base_domain = urlparse(base_url).netloc
                
                # Check if this is a trusted CDN URL marked by the handler
                is_trusted_cdn = item_data.get('trusted_cdn', False)
                
                # Debug: Show what's happening
                if item_domain != base_domain:
                    print(f"  Domain check: {item_domain} vs {base_domain}, trusted_cdn={is_trusted_cdn}")
                
                if item_domain != base_domain and not is_trusted_cdn:
                    print(f"Skipping item {index + 1}/{total_items}: Off-domain URL {item_url}")
                    stats["skipped_platform"] += 1
                    self.mark_url_processed(item_url)
                    continue

            print(f"Processing item {index + 1}/{total_items}: {item_url}")
            stats["downloads_attempted"] += 1

            try:
                # Download the file and get its details - this could also be made async
                # but keeping it sync for now as it's primarily file I/O
                download_result = self.download_file(
                    item_data,
                    output_path,
                    index,
                    kwargs.get('filename_prefix', 'file_'),
                    kwargs.get('min_width', 0),
                    kwargs.get('min_height', 0),
                    kwargs.get('hash_algorithm', 'average_hash'),
                    kwargs.get('download_images', True),
                    kwargs.get('download_videos', True)
                )

                if download_result:
                    file_path, file_type, width, height, file_hash, download_error = download_result

                    if download_error:
                        print(f"  Skipping: {download_error}")
                        if "small" in download_error.lower(): stats["skipped_small"] += 1
                        elif "platform" in download_error.lower(): stats["skipped_platform"] += 1
                        elif "not media" in download_error.lower(): stats["skipped_not_media"] += 1
                        else: stats["failed_download"] += 1
                        self.mark_url_processed(item_url) # Mark as processed even if skipped/failed
                        continue

                    # --- Deduplication ---
                    is_duplicate = False
                    duplicate_info = None
                    if file_type == 'image' and file_hash and IMAGEHASH_AVAILABLE and kwargs['hash_algorithm'] != 'none':
                        if file_hash in downloaded_images_cache:
                            is_duplicate = True
                            duplicate_info = downloaded_images_cache[file_hash]
                            print(f"  Duplicate detected: Hash {file_hash} matches {duplicate_info['filename']}")
                        else:
                            # Add to cache if not duplicate
                            downloaded_images_cache[file_hash] = {
                                'filename': os.path.basename(file_path),
                                'filepath': file_path,
                                'width': width,
                                'height': height,
                                'url': item_url # Store original URL
                            }

                    if is_duplicate and duplicate_info:
                        stats["duplicates_removed"] += 1 # Increment even if moving
                        # Compare resolutions, keep the larger one
                        existing_res = duplicate_info['width'] * duplicate_info['height']
                        current_res = width * height
                        keep_existing = existing_res >= current_res

                        if keep_existing:
                            print(f"  Keeping existing file: {duplicate_info['filename']} ({duplicate_info['width']}x{duplicate_info['height']})")
                            # Delete or move the newly downloaded file
                            if move_duplicates:
                                try:
                                    new_filename = os.path.basename(file_path)
                                    move_path = os.path.join(duplicates_folder, new_filename)
                                    os.rename(file_path, move_path)
                                    print(f"  Moved new duplicate to: {move_path}")
                                    stats["duplicates_moved"] += 1
                                except Exception as move_err:
                                    print(f"  Error moving duplicate {file_path}: {move_err}. Deleting instead.")
                                    os.remove(file_path)
                            else:
                                os.remove(file_path)
                                print(f"  Deleted new duplicate: {os.path.basename(file_path)}")
                            # Mark URL as processed, don't add to final list
                            self.mark_url_processed(item_url)
                            continue # Skip adding this duplicate to downloaded_files_data
                        else:
                            print(f"  Replacing existing file: {duplicate_info['filename']} with new file {os.path.basename(file_path)} ({width}x{height})")
                            # Delete or move the OLD file
                            old_filepath = duplicate_info['filepath']
                            if move_duplicates:
                                try:
                                    old_filename = os.path.basename(old_filepath)
                                    move_path = os.path.join(duplicates_folder, old_filename)
                                    os.rename(old_filepath, move_path)
                                    print(f"  Moved old duplicate to: {move_path}")
                                    stats["duplicates_moved"] += 1
                                except Exception as move_err:
                                    print(f"  Error moving duplicate {old_filepath}: {move_err}. Deleting instead.")
                                    if os.path.exists(old_filepath): os.remove(old_filepath)
                            else:
                                if os.path.exists(old_filepath):
                                     os.remove(old_filepath)
                                     print(f"  Deleted old duplicate: {os.path.basename(old_filepath)}")

                            # Remove old entry from final_files_data if it was added in a previous run
                            final_files_data[:] = [d for d in final_files_data if d.get('filepath') != old_filepath]

                            # Update cache with the new, larger file
                            downloaded_images_cache[file_hash] = {
                                'filename': os.path.basename(file_path),
                                'filepath': file_path,
                                'width': width,
                                'height': height,
                                'url': item_url
                            }
                            # Proceed to add the new file's metadata below

                    # --- Add to successful downloads ---
                    file_metadata = {
                        'filename': os.path.basename(file_path),
                        'filepath': file_path, # Store full path for potential later use
                        'url': item_url,
                        'type': file_type,
                        'width': width,
                        'height': height,
                        'hash': str(file_hash) if file_hash else None,
                        'source_page_url': kwargs.get('url', ''), # Main URL from scrape_files
                        # Add metadata from the original item_data if extracting
                        'alt': item_data.get('alt') if kwargs.get('extract_metadata') else None,
                        'title': item_data.get('title') if kwargs.get('extract_metadata') else None,
                        'credits': item_data.get('credits') if kwargs.get('extract_metadata') else None,
                        'original_source_url': item_data.get('source_url') # URL from handler
                    }
                    downloaded_files_data.append(file_metadata)
                    self.mark_url_processed(item_url) # Mark as successfully processed

                    if file_type == 'image':
                        stats["downloads_succeeded_image"] += 1
                    elif file_type == 'video':
                        stats["downloads_succeeded_video"] += 1

                    # Save individual metadata file if requested
                    if kwargs.get('save_metadata_json', True):
                        self.save_metadata_file(file_path, file_metadata, output_path)
                        stats["metadata_files_saved"] += 1

                else:
                    # download_file returned None, indicating a failure during download/processing
                    print(f"  Failed to download or process item: {item_url}")
                    stats["failed_download"] += 1
                    self.mark_url_processed(item_url) # Mark as processed even if failed

            except Exception as e:
                print(f"  Error processing item {item_url}: {e}")
                traceback.print_exc()
                stats["failed_other"] += 1
                self.mark_url_processed(item_url) # Mark as processed on error

        print(f"Finished processing download queue. Successfully processed {len(downloaded_files_data)} new files.")
        return downloaded_files_data, downloaded_images_cache


    def download_file(self, url_or_dict, output_path, index, prefix, min_width, min_height, hash_algo, download_images, download_videos):
        """Downloads a single file, checks dimensions, calculates hash, and returns details."""
        if isinstance(url_or_dict, dict):
            url = url_or_dict.get('url')
            if not url: 
                print("Missing URL in item dictionary")
                return None, None, None, None, None, "Missing URL"
        else:
            url = url_or_dict # Assume it's just the URL string

        if not url:
            print("Empty URL provided")
            return None, None, None, None, None, "Missing URL"

        # Basic URL validation
        parsed_url = urlparse(url)
        if not parsed_url.scheme or not parsed_url.netloc:
            print(f"Invalid URL format: {url}")
            return None, None, None, None, None, f"Invalid URL format: {url}"

        # Determine file type and check if we should download it
        file_ext = os.path.splitext(parsed_url.path)[1].lower()
        
        # No extension? Try to guess from the URL or default to .jpg
        if not file_ext:
            if 'image' in url.lower() or any(img_format in url.lower() for img_format in ['jpeg', 'jpg', 'png', 'webp']):
                file_ext = '.jpg'
            elif 'video' in url.lower() or any(vid_format in url.lower() for vid_format in ['mp4', 'webm', 'mov']):
                file_ext = '.mp4'
            else:
                file_ext = '.jpg'  # Default to jpg
        
        is_image = file_ext in self.image_extensions
        is_video = file_ext in self.video_extensions
        is_audio = file_ext in self.audio_extensions

        # If extension detection failed, check if we can detect from the url keywords
        if not (is_image or is_video or is_audio):
            if 'image' in url.lower():
                is_image = True
                file_ext = '.jpg'
            elif 'video' in url.lower():
                is_video = True
                file_ext = '.mp4'

        file_type = None
        if is_image and download_images:
            file_type = 'image'
        elif is_video and download_videos:
            file_type = 'video'
        elif is_audio:  # Handle audio based on global flag
            file_type = 'audio'
        else:
            reason = "Unsupported file type"
            if is_image and not download_images: reason = "Image download disabled"
            if is_video and not download_videos: reason = "Video download disabled"
            return None, None, None, None, None, f"Skipped ({reason}): {url}"

        try:
            print(f"  Downloading {file_type}: {url}")
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
            response = requests.get(url, stream=True, timeout=30, headers=headers)
            
            if response.status_code != 200:
                print(f"HTTP error {response.status_code} for {url}")
                return None, None, None, None, None, f"HTTP error {response.status_code}"
            
            response.raise_for_status()


            content_type = response.headers.get('content-type', '').lower()
            # Further check content type if extension was ambiguous
            if file_type == 'image' and not content_type.startswith('image/'):
                return None, None, None, None, None, f"Skipped (Content-Type not image: {content_type}): {url}"
            if file_type == 'video' and not content_type.startswith('video/'):
                return None, None, None, None, None, f"Skipped (Content-Type not video: {content_type}): {url}"
            if file_type == 'audio' and not content_type.startswith('audio/'):
                return None, None, None, None, None, f"Skipped (Content-Type not audio: {content_type}): {url}"


            # Generate filename
            # Use hash of URL for more uniqueness, fallback to index
            try:
                url_hash = hashlib.sha1(url.encode()).hexdigest()[:10]
                filename = f"{prefix}{url_hash}{file_ext}"
            except Exception:
                filename = f"{prefix}{index:04d}{file_ext}"
            filepath = os.path.join(output_path, filename)

            width, height = 0, 0
            file_hash = None

            # Process Image
            if file_type == 'image':
                try:
                    # Read image content
                    content = response.content
                    
                    # Create BytesIO object with proper closure
                    img_data = BytesIO(content)
                    try:
                        with Image.open(img_data) as img:
                            width, height = img.size
                            print(f"Checking image: {url} ({width}x{height}), min: {min_width}x{min_height}")
                            # Check dimensions first before further processing
                            if (min_width > 0 and width < min_width) or \
                            (min_height > 0 and height < min_height):
                                return None, file_type, width, height, None, f"Skipped (Too small: {width}x{height})"

                            # Calculate hash if library available and algo selected
                            file_hash = None
                            if IMAGEHASH_AVAILABLE and hash_algo != 'none':
                                hash_func = getattr(imagehash, hash_algo, None)
                                if hash_func:
                                    file_hash = hash_func(img)
                                else:
                                    print(f"  Warning: Unknown hash algorithm '{hash_algo}'. Skipping hash.")
                            
                            # Save the image file immediately after processing
                            with open(filepath, 'wb') as f:
                                f.write(content)
                            print(f"  Saved image: {filename} ({width}x{height})")
                            
                            # Return successful result
                            return filepath, file_type, width, height, file_hash, None

                    finally:
                        # Ensure BytesIO is closed
                        img_data.close()
                        
                except Exception as img_err:
                    # Clean up potentially partially saved file on image error
                    if os.path.exists(filepath): 
                        os.remove(filepath)
                    print(f"  Error processing image: {img_err}")
                    if self.debug_mode:
                        traceback.print_exc()
                    return None, file_type, 0, 0, None, f"Failed (Image processing error: {img_err})"

            # Process Video
            elif file_type == 'video':
                # Save video file (no dimension check or hashing for videos currently)
                with open(filepath, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                print(f"  Saved video: {filename}")
                # Set width/height to 0 for videos as we don't extract them yet
                width, height = 0, 0
            
            # Process Audio
            elif file_type == 'audio':
                # same as video – just stream to disk
                with open(filepath, "wb") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                print(f"  Saved audio: {filename}")
                # Set width/height to 0 for audio as we don't extract them yet
                width, height = 0, 0

            return filepath, file_type, width, height, file_hash, None # Success

        except requests.exceptions.RequestException as req_err:
            return None, file_type, 0, 0, None, f"Failed (Download error: {req_err})"
        except Exception as e:
            return None, file_type, 0, 0, None, f"Failed (Unexpected error: {e})"


    def create_output_directory(self, base_dir, url, use_url_folder, handler=None):
        """Creates the output directory structure."""
        # Use ComfyUI's output directory as the root
        output_root = folder_paths.get_output_directory()
        base_output_dir = os.path.join(output_root, base_dir)

        dir_name_part = "default"
        if handler:
             # Use handler's directory logic if available
             try:
                 handler_base, handler_content = handler.get_content_directory()
                 # Combine handler parts, ensuring they are sanitized
                 sanitized_base = handler._sanitize_directory_name(handler_base)
                 sanitized_content = handler._sanitize_directory_name(handler_content)
                 dir_name_part = os.path.join(sanitized_base, sanitized_content)
             except Exception as e:
                 print(f"Handler {type(handler).__name__} failed to provide directory: {e}. Using default.")
                 # Fallback to domain/URL logic
                 parsed_url = urlparse(url)
                 domain = parsed_url.netloc
                 sanitized_domain = handler._sanitize_directory_name(domain) if handler else re.sub(r'[<>:"/\\|?*]', '_', domain)
                 if use_url_folder:
                     # Create a folder name from the URL path + query
                     path_part = parsed_url.path.strip('/') + ('_' + parsed_url.query if parsed_url.query else '')
                     sanitized_path = handler._sanitize_directory_name(path_part)[:50] if handler else re.sub(r'[<>:"/\\|?*]', '_', path_part)[:50]
                     dir_name_part = os.path.join(sanitized_domain, sanitized_path if sanitized_path else "root")
                 else:
                     dir_name_part = sanitized_domain

        else:
             # Fallback if no handler (shouldn't happen with Generic handler)
             parsed_url = urlparse(url)
             domain = parsed_url.netloc
             sanitized_domain = re.sub(r'[<>:"/\\|?*]', '_', domain)
             if use_url_folder:
                 path_part = parsed_url.path.strip('/') + ('_' + parsed_url.query if parsed_url.query else '')
                 sanitized_path = re.sub(r'[<>:"/\\|?*]', '_', path_part)[:50]
                 dir_name_part = os.path.join(sanitized_domain, sanitized_path if sanitized_path else "root")
             else:
                 dir_name_part = sanitized_domain


        # Ensure dir_name_part is not empty
        if not dir_name_part:
             dir_name_part = "default_site"

        final_path = os.path.join(base_output_dir, dir_name_part)
        os.makedirs(final_path, exist_ok=True)
        return final_path


    def mark_url_processed(self, url):
        """Adds a URL to the set of processed URLs for the current run."""
        if url:
            self.processed_urls.add(url)

    def check_url_processed(self, url):
        """Checks if a URL has already been processed in the current run."""
        return url in self.processed_urls

    def load_previous_run_data(self, base_output_dir, url, use_url_as_folder, stats):
        """Loads data from metadata file if 'continue_last_run' is enabled."""
        output_path = self.create_output_directory(base_output_dir, url, use_url_as_folder, None) # Determine path first
        metadata_filepath = os.path.join(output_path, self.metadata_file)
        loaded_files_data = []
        image_cache = {}

        if os.path.exists(metadata_filepath):
            print(f"Found previous metadata file: {metadata_filepath}")
            try:
                with open(metadata_filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # Check if it's the correct format (list of dicts)
                    if isinstance(data, list):
                         loaded_files_data = data
                         stats["files_loaded_from_metadata"] = len(loaded_files_data)
                         print(f"Loaded {len(loaded_files_data)} file records from previous run.")

                         # Rebuild image hash cache from loaded data
                         if IMAGEHASH_AVAILABLE:
                             for item in loaded_files_data:
                                 if item.get('type') == 'image' and item.get('hash') and item['hash'] != 'None':
                                     try:
                                         # Ensure filepath is correct relative to output_path
                                         item_filepath = os.path.join(output_path, item['filename'])
                                         if os.path.exists(item_filepath): # Only cache if file exists
                                             image_cache[item['hash']] = {
                                                 'filename': item['filename'],
                                                 'filepath': item_filepath, # Use corrected path
                                                 'width': item.get('width', 0),
                                                 'height': item.get('height', 0),
                                                 'url': item.get('url')
                                             }
                                         else:
                                             print(f"  Warning: File {item['filename']} from metadata not found. Skipping cache entry.")
                                     except Exception as cache_err:
                                         print(f"  Error rebuilding cache for {item.get('filename')}: {cache_err}")
                             print(f"Rebuilt image hash cache with {len(image_cache)} entries.")

                    else:
                         print("  Metadata file has unexpected format. Ignoring.")
            except json.JSONDecodeError:
                print("  Error decoding metadata file. Ignoring.")
            except Exception as e:
                print(f"  Error loading metadata file: {e}")
        else:
            print("No previous metadata file found to continue from.")

        return output_path, loaded_files_data, image_cache, stats


    def save_download_metadata(self, output_path, url, files_data):
        """Saves the overall metadata for the run."""
        metadata_filepath = os.path.join(output_path, self.metadata_file)
        try:
            # Ensure filepaths in metadata are relative to output_path for portability
            relative_files_data = []
            for item in files_data:
                 new_item = item.copy()
                 # Keep only filename, not full path
                 if 'filepath' in new_item:
                     new_item['filename'] = os.path.basename(new_item['filepath'])
                     del new_item['filepath']
                 relative_files_data.append(new_item)

            with open(metadata_filepath, 'w', encoding='utf-8') as f:
                json.dump(relative_files_data, f, indent=4, ensure_ascii=False)
            # print(f"Saved overall run metadata to {metadata_filepath}") # Reduce verbosity
        except Exception as e:
            print(f"Error saving overall metadata file {metadata_filepath}: {e}")


    async def _perform_page_interactions(self, page: AsyncPage, **kwargs):
        """Performs scrolling and custom interactions on the page (async version)."""
        if not page: return

        # --- Scrolling ---
        use_auto = kwargs.get('use_auto_scroll', True)
        max_scrolls = kwargs.get('max_auto_scrolls', 50)
        fixed_times = kwargs.get('scroll_down_times', 0)
        delay_ms = kwargs.get('scroll_delay_ms', 500)

        if use_auto and max_scrolls > 0:
            await self._auto_scroll_page(page, max_scrolls, delay_ms)
        elif fixed_times > 0:
            await self._scroll_down_fixed(page, fixed_times, delay_ms)
        else:
            print("Scrolling disabled.")

        # --- Custom Interactions ---
        interaction_json = kwargs.get('interaction_sequence', "")
        if interaction_json:
            try:
                interactions = json.loads(interaction_json)
                if not isinstance(interactions, list):
                    raise ValueError("Interaction sequence must be a JSON list.")

                print(f"Performing {len(interactions)} custom interactions...")
                for i, action in enumerate(interactions):
                    action_type = action.get('type', '').lower()
                    selector = action.get('selector')
                    value = action.get('value')
                    delay = action.get('delay_ms', 100)

                    print(f"  Action {i+1}: Type='{action_type}', Selector='{selector}'")

                    if not selector:
                        print("    Skipping: Missing selector.")
                        continue

                    element = page.locator(selector).first

                    is_visible = await element.is_visible(timeout=5000)
                    if not is_visible:
                        print(f"    Skipping: Element '{selector}' not visible.")
                        continue

                    if action_type == 'click':
                        await element.click()
                    elif action_type == 'fill':
                        if value is None:
                            print("    Skipping fill: Missing 'value'.")
                            continue
                        await element.fill(value)
                    elif action_type == 'check':
                        await element.check()
                    elif action_type == 'uncheck':
                        await element.uncheck()
                    elif action_type == 'select':
                        if value is None:
                            print("    Skipping select: Missing 'value'.")
                            continue
                        await element.select_option(value)
                    else:
                        print(f"    Skipping: Unknown action type '{action_type}'.")
                        continue

                    print(f"    Action '{action_type}' performed. Waiting {delay}ms.")
                    await page.wait_for_timeout(delay)

            except json.JSONDecodeError:
                print(f"Error: Invalid JSON in interaction sequence: {interaction_json}")
            except Exception as e:
                print(f"Error performing custom interactions: {e}")
                traceback.print_exc()

    async def take_screenshots(self, page: AsyncPage, output_path: str, elements_selector: str, full_page: bool, stats: dict):
        """Takes screenshots of the page or specific elements (async version)."""
        if not page: return
        print("Taking screenshot(s)...")
        try:
            selectors = [s.strip() for s in elements_selector.splitlines() if s.strip()] if elements_selector else []

            if selectors:
                # Screenshot specific elements
                for i, selector in enumerate(selectors):
                    try:
                        element = page.locator(selector).first
                        is_visible = await element.is_visible(timeout=5000)
                        if is_visible:
                            ss_path = os.path.join(output_path, f"screenshot_element_{i+1}.png")
                            await element.screenshot(path=ss_path)
                            print(f"  Saved element screenshot: {os.path.basename(ss_path)}")
                            stats["screenshots_taken"] += 1
                        else:
                            print(f"  Skipping screenshot for hidden element: {selector}")
                    except Exception as el_ss_err:
                        print(f"  Error taking screenshot for element '{selector}': {el_ss_err}")
            else:
                # Screenshot the whole page (or viewport)
                ss_path = os.path.join(output_path, "screenshot_page.png")
                await page.screenshot(path=ss_path, full_page=full_page)
                print(f"  Saved {'full page' if full_page else 'viewport'} screenshot: {os.path.basename(ss_path)}")
                stats["screenshots_taken"] += 1

        except Exception as e:
            print(f"Error taking screenshots: {e}")
            traceback.print_exc()


    async def authenticate_with_site(self, page: AsyncPage, url: str, auth_config: dict, save_cookies: bool, output_path: str):
        """Enhanced authentication with session reuse (async version)."""
        if not page or not auth_config: 
            return

        domain = urlparse(url).netloc
        site_config = self.get_site_auth_config(domain, auth_config)
        if not site_config:
            return

        print(f"Attempting authentication for domain: {domain}")
        
        # --- STRATEGY 0: Try to use existing session ---
        if hasattr(self, 'session_manager') and self.session_manager.has_valid_session(domain):
            print(f"Found valid stored session for {domain}, attempting to use it...")
            try:
                current_context = page.context
                current_browser = current_context.browser
                
                # Load session into new context
                new_context = await self.session_manager.load_into_context(domain, current_browser)
                if new_context:
                    new_page = await new_context.new_page()
                    
                    # Update resources
                    pw_instance, _, _, _, user_data_dir = self.pw_resources        # unpack 5 items
                    self.pw_resources = (
                        pw_instance,
                        current_browser,
                        new_context,
                        new_page,
                        user_data_dir                                           # keep the profile path
                    )
                    
                    # Test if session is valid
                    await new_page.goto(url, timeout=60000, wait_until="domcontentloaded")
                    
                    # Check if we're logged in
                    is_logged_in = await self._verify_login_success(new_page, site_config)
                    
                    if is_logged_in:
                        print(f"Successfully used stored session for {domain}")
                        
                        # Clean up old context
                        try:
                            if current_context and current_context != new_context:
                                await current_context.close()
                        except Exception as e:
                            print(f"Warning: Error closing old context: {e}")
                            
                        return  # Success!
                    else:
                        print(f"Stored session for {domain} is no longer valid")
                        # Delete the invalid session
                        self.session_manager.delete_session(domain)
                        
                        # Clean up and continue to other auth methods
                        try:
                            await new_context.close()
                        except:
                            pass
                        
                        # Create fresh context
                        default_context = await current_browser.new_context()
                        default_page = await default_context.new_page()
                        
                        # Update references
                        self.pw_resources = (
                            pw_instance,
                            current_browser,
                            default_context,
                            default_page,
                            user_data_dir          # keep whatever was already there (may be None)
                        )
                        
                        # Set page for subsequent auth methods
                        page = default_page
                        await page.goto(url, timeout=60000, wait_until="domcontentloaded")
                
            except Exception as e:
                print(f"Error using stored session: {e}")
        
        # --- Strategy 1: Load Cookies ---
        cookie_file = site_config.get('cookie_file')
        cookie_path = None
        if cookie_file:
            cookie_path = os.path.join(output_path, cookie_file) if not os.path.isabs(cookie_file) else cookie_file

        if cookie_path and os.path.exists(cookie_path):
            try:
                print(f"Loading cookies from: {cookie_path}")
                current_context = page.context
                current_browser = current_context.browser
                
                new_context = await current_browser.new_context(storage_state=cookie_path)
                new_page = await new_context.new_page()
                
                pw_instance, _, _, _, user_data_dir = self.pw_resources        # unpack 5 items
                self.pw_resources = (
                    pw_instance,
                    current_browser,
                    new_context,
                    new_page,
                    user_data_dir                                           # keep the profile path
                )
                
                try:
                    if current_context and current_context != new_context:
                        await current_context.close()
                except Exception as e:
                    print(f"Warning: Error closing old context: {e}")
                
                await new_page.goto(url, timeout=60000, wait_until="domcontentloaded")
                return
                
            except Exception as e:
                print(f"Error loading cookies: {e}")

        # --- Strategy 2: Perform Login Steps ---
        login_steps = site_config.get('login_steps')
        if isinstance(login_steps, list):
            print("Performing login steps...")
            try:
                for i, step in enumerate(login_steps):
                    step_type = step.get('type', '').lower()
                    selector = step.get('selector')
                    value = step.get('value')
                    delay = step.get('delay_ms', 200)

                    print(f"  Login Step {i+1}: Type='{step_type}', Selector='{selector}'")

                    if not selector:
                        print("    Skipping: Missing selector.")
                        continue

                    element = page.locator(selector).first

                    # Wait for element to be ready
                    await element.wait_for(state="visible", timeout=15000)

                    if step_type == 'fill':
                        if value is None:
                            print("    Skipping fill: Missing 'value'.")
                            continue
                        actual_value = value
                        if '{username}' in value and site_config.get('username'):
                            actual_value = actual_value.replace('{username}', site_config['username'])
                        if '{password}' in value and site_config.get('password'):
                            actual_value = actual_value.replace('{password}', site_config['password'])
                        await element.fill(actual_value)
                    elif step_type == 'click':
                        await element.click()
                    elif step_type == 'wait':
                        wait_time = int(value) if value else delay
                        print(f"    Waiting for {wait_time}ms...")
                        await page.wait_for_timeout(wait_time)
                        continue
                    else:
                        print(f"    Skipping: Unknown login step type '{step_type}'.")
                        continue

                    print(f"    Step '{step_type}' performed. Waiting {delay}ms.")
                    await page.wait_for_timeout(delay)

                print("Login steps completed.")

                # Save cookies after successful login steps if requested
                if save_cookies and output_path:
                    cookie_file_to_save = site_config.get('cookie_file', f"{domain}_cookies.json")
                    save_path = os.path.join(output_path, cookie_file_to_save)
                    try:
                        await page.context.storage_state(path=save_path)
                        print(f"Saved session cookies to: {save_path}")
                    except Exception as e:
                        print(f"Error saving cookies after login: {e}")

            except Exception as e:
                print(f"Error during login steps: {e}")
                traceback.print_exc()
        
        # After successful login, store the session if requested
        if save_cookies and hasattr(self, "session_manager"):
            _, _, context, _, _ = self.pw_resources   # five slots now
            self.session_manager.store_session(domain, context)

    async def _verify_login_success(self, page, site_config):
        """Verify if login was successful by checking for login indicators (async version)."""
        try:
            success_selectors = site_config.get('login_success_selectors', [
                '.logged-in', '.user-avatar', '.account-menu',
                '[data-testid="user-menu"]', '.user-profile'
            ])
            
            for selector in success_selectors:
                try:
                    elem = page.locator(selector).first
                    is_visible = await elem.is_visible(timeout=2000)
                    if is_visible:
                        print(f"Login success confirmed with selector: {selector}")
                        return True
                except:
                    continue
            
            login_form_selectors = site_config.get('login_form_selectors', [
                'form[action*="login"]', 'button:has-text("Log in")',
                'button:has-text("Sign in")', 'a:has-text("Log in")'
            ])
            
            for selector in login_form_selectors:
                try:
                    elem = page.locator(selector).first
                    is_visible = await elem.is_visible(timeout=2000)
                    if is_visible:
                        return False
                except:
                    continue
            
            return True
            
        except Exception as e:
            print(f"Error verifying login: {e}")
            return False

    def get_site_auth_config(self, domain, auth_config):
        """Retrieves the specific configuration for a domain from the loaded auth_config."""
        if not auth_config or not domain:
            return None
        # Allow matching subdomains, e.g. 'login.example.com' should match 'example.com' config
        parts = domain.split('.')
        for i in range(len(parts) - 1):
            sub_domain = '.'.join(parts[i:])
            if sub_domain in auth_config:
                # print(f"Found auth config for domain match: {sub_domain}")
                return auth_config[sub_domain]
        # Check exact domain last
        if domain in auth_config:
             # print(f"Found auth config for exact domain: {domain}")
             return auth_config[domain]

        return None


    def load_auth_config(self, config_file_path):
        """Loads the authentication configuration JSON file."""
        if not config_file_path:
            # Try default paths - web_scraper config first (for download-tools), then fallback to generic
            possible_paths = [
                os.path.join(os.path.dirname(__file__), "..", "configs", "web_scraper", "auth_config.json"),
                os.path.join(os.path.dirname(os.path.dirname(__file__)), "configs", "web_scraper", "auth_config.json"),
                os.path.join(os.path.dirname(__file__), "auth_config.json"),
                os.path.join(os.path.dirname(__file__), "..", "configs", "auth_config.json"),
                os.path.join(os.path.dirname(os.path.dirname(__file__)), "configs", "auth_config.json")
            ]
            
            for path in possible_paths:
                if os.path.exists(path):
                    config_file_path = path
                    print(f"Using auth config path: {config_file_path}")
                    break
            
            if not config_file_path:
                print("No auth config path provided and default not found.")
                return None

        if not os.path.exists(config_file_path):
            print(f"Authentication config file not found: {config_file_path}")
            return None

        try:
            with open(config_file_path, 'r', encoding='utf-8') as f:
                raw_config = json.load(f)
                
            # Ensure proper structure with 'sites' key
            config = {'sites': {}} 
            if 'sites' in raw_config:
                config['sites'] = raw_config['sites']
            elif isinstance(raw_config, dict):
                # For backward compatibility: if no 'sites' key but is a dict
                config['sites'] = raw_config
                
            print(f"Successfully loaded authentication config from: {config_file_path}")
            
            # Print available sites for debugging
            print(f"Auth config contains settings for: {', '.join(config['sites'].keys())}")
            
            return config
        except json.JSONDecodeError:
            print(f"Error: Invalid JSON in authentication config file: {config_file_path}")
        except Exception as e:
            print(f"Error loading authentication config file {config_file_path}: {e}")

        return None

    async def _get_playwright_page(self, response) -> Optional[AsyncPage]:
        """Attempts to get the underlying Playwright page from a Scrapling response."""
        # This depends heavily on Scrapling's internal structure and fetcher used
        if not response or not hasattr(response, 'request') or not response.request:
            return None
        fetcher = getattr(response.request, 'fetcher', None)
        if fetcher and isinstance(fetcher, PlayWrightFetcher):
            # Accessing internal _page attribute - this is fragile!
            page = getattr(fetcher, '_page', None)
            if page and isinstance(page, AsyncPage):
                return page
        # Fallback: Check if response itself has a page attribute (less likely)
        page_attr = getattr(response, 'page', None)
        if page_attr and isinstance(page_attr, AsyncPage):
            return page_attr

        print("Could not retrieve Playwright page from Scrapling response.")
        return None

    async def _auto_scroll_page(self, page: AsyncPage, max_scrolls: int, delay_ms: int):
        """Enhanced scrolling that intelligently loads content (async version)."""
        if not page: 
            return
        
        print(f"Starting enhanced auto-scroll: max_scrolls={max_scrolls}, delay={delay_ms}ms")
        scroll_count = 0
        last_height = -1
        last_content_count = 0  # Initialize here
        consecutive_no_change = 0
        no_change_threshold = 3  # Stop after 3 consecutive scrolls with no change
        
        # Define selectors to track content
        content_selector = "img, video, .post, .card, article, figure, .media"
        
        while scroll_count < max_scrolls:
            try:
                # Get current page metrics
                current_height = await page.evaluate("document.body.scrollHeight")
                current_content_count = await page.locator(content_selector).count()
                
                # Check if both height and content count are unchanged
                if current_height == last_height and current_content_count == last_content_count:
                    consecutive_no_change += 1
                    if consecutive_no_change >= no_change_threshold:
                        print("  Stopping auto-scroll: Page content stable.")
                        
                        # Try to click "Load More" buttons before giving up
                        try:
                            load_more = page.locator(
                                "button:has-text('Load More'), .load-more, [class*='load-more']"
                            ).first
                            
                            is_visible = await load_more.is_visible(timeout=1000)
                            if is_visible:
                                print("  Found load more button, clicking...")
                                await load_more.click()
                                await page.wait_for_timeout(delay_ms * 2)
                                
                                # Check if clicking worked
                                new_content_count = await page.locator(content_selector).count()
                                if new_content_count > current_content_count:
                                    print(f"  Load more added {new_content_count - current_content_count} items")
                                    consecutive_no_change = 0
                                    last_content_count = new_content_count
                                    continue
                        except Exception:
                            pass
                            
                        # If we tried buttons but nothing changed, exit
                        break
                else:
                    consecutive_no_change = 0  # Reset counter
                
                # Scroll to bottom
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                
                # Update tracking metrics
                last_height = current_height
                last_content_count = current_content_count
                
                scroll_count += 1
                await page.wait_for_timeout(delay_ms)
                
                # Every few scrolls, check for lazy-loaded images
                if scroll_count % 3 == 0:
                    await self._ensure_lazy_images_loaded(page)
                
            except Exception as scroll_err:
                print(f"  Error during auto-scroll: {scroll_err}")
                break
        
        print(f"Finished auto-scroll after {scroll_count} scrolls. Found {last_content_count} content elements.")

    async def _ensure_lazy_images_loaded(self, page: "AsyncPage"):
        """
        Ensures lazy-loaded images with various data-* attributes are swapped in.
        """
        try:
            lazy_img_count = await page.evaluate("""
                () => {
                    const lazyImgs = document.querySelectorAll('img[data-src], img[data-lazy], img[loading="lazy"], img[data-original], img[data-srcset]');
                    let count = 0;
                    lazyImgs.forEach(img => {
                        // Try all possible lazy attributes
                        const dataSrc = img.getAttribute('data-src') || img.getAttribute('data-lazy') || img.getAttribute('data-original');
                        if (dataSrc && (!img.src || img.src.includes('placeholder'))) {
                            img.src = dataSrc;
                            count++;
                        }
                        // Handle data-srcset
                        const dataSrcset = img.getAttribute('data-srcset');
                        if (dataSrcset && !img.srcset) {
                            img.srcset = dataSrcset;
                            count++;
                        }
                    });
                    return count;
                }
            """)
            if lazy_img_count > 0 and self.debug_mode:
                print(f"  Helped load {lazy_img_count} lazy images")
        except Exception as e:
            if self.debug_mode:
                print(f"  Error ensuring images loaded: {e}")
    def _detect_and_handle_content_blocker(self, page):
        """Detect and handle common content blockers like cookie notices and modals."""
        try:
            # Common cookie consent selectors
            cookie_selectors = [
                "button:has-text('Accept')", 
                "button:has-text('Accept All')",
                "button:has-text('I Accept')",
                "button:has-text('Agree')",
                "[aria-label='Accept cookies']",
                ".cookie-accept",
                ".consent-accept"
            ]
            
            # Try each selector
            for selector in cookie_selectors:
                button = page.locator(selector).first
                if button.is_visible(timeout=1000):
                    print(f"  Found cookie consent button: {selector}, clicking...")
                    button.click()
                    page.wait_for_timeout(1000)
                    return True
                    
            # Check for modal overlays
            modal_selectors = [
                ".modal button:has-text('Close')",
                "[aria-label='Close modal']",
                ".modal-close",
                ".close-button"
            ]
            
            for selector in modal_selectors:
                button = page.locator(selector).first
                if button.is_visible(timeout=1000):
                    print(f"  Found modal close button: {selector}, clicking...")
                    button.click()
                    page.wait_for_timeout(1000)
                    return True
                    
            return False
        except Exception as e:
            print(f"Error handling content blockers: {e}")
            return False

    def _extract_links_from_page(self, page, current_url, required_domain=None):
        """Extract links from a page, optionally filtering by domain."""
        try:
            # Run JavaScript to extract all links
            links = page.evaluate("""() => {
                const uniqueLinks = new Set();
                
                // Get links from <a> tags
                document.querySelectorAll('a[href]').forEach(a => {
                    if (a.href && a.href.startsWith('http')) {
                        uniqueLinks.add(a.href);
                    }
                });
                
                return Array.from(uniqueLinks);
            }""")
            
            # Filter links if required_domain is specified
            if required_domain:
                filtered_links = []
                for link in links:
                    try:
                        link_domain = urlparse(link).netloc
                        if link_domain == required_domain:
                            filtered_links.append(link)
                    except:
                        continue
                links = filtered_links
            
            # Filter out common non-content URLs
            filtered_links = []
            for link in links:
                # Skip URLs that are unlikely to contain media content
                if any(pattern in link.lower() for pattern in [
                    '/login', '/signup', '/signin', '/register', 
                    '/terms', '/privacy', '/about', '/contact',
                    '/help', '/faq', '/support', '/legal',
                    '/settings', '/account', '/profile',
                    'javascript:', 'mailto:', 'tel:', '/tag/',
                    '/category/', '/search?', '/logout', '/password'
                ]):
                    continue
                    
                # Make sure the link isn't the current URL
                if link != current_url:
                    filtered_links.append(link)
                    
            return filtered_links
        except Exception as e:
            print(f"Error extracting links: {e}")
            return []
    def _extract_media_metadata(self, page, element_locator):
        """
        Extract rich metadata for a media element.
        
        Args:
            page: Playwright page
            element_locator: Locator for the media element
            
        Returns:
            Dictionary of metadata
        """
        metadata = {}
        
        try:
            # Get element attributes
            alt = element_locator.get_attribute("alt") or ""
            title_attr = element_locator.get_attribute("title") or ""
            aria_label = element_locator.get_attribute("aria-label") or ""
            
            # Basic metadata
            metadata["alt"] = alt
            metadata["title_attr"] = title_attr
            metadata["aria_label"] = aria_label
            
            # Look for parent containers with more metadata
            try:
                # Check for figure/figcaption pattern
                figure = element_locator.locator("xpath=ancestor::figure[1]").first
                if figure.is_visible(timeout=500):
                    figcaption = figure.locator("figcaption").first
                    if figcaption.is_visible(timeout=500):
                        metadata["caption"] = figcaption.inner_text().strip()
                    
                    # Look for credit elements
                    credit_elem = figure.locator(".credit, .author, .byline, [rel='author']").first
                    if credit_elem.is_visible(timeout=500):
                        metadata["credits"] = credit_elem.inner_text().strip()
            except Exception:
                pass
                
            # Try to find a heading/title near the element
            try:
                # Look upward for heading
                parent_container = element_locator.locator("xpath=ancestor::div[position() <= 3]").first
                if parent_container.is_visible(timeout=500):
                    heading = parent_container.locator("h1, h2, h3, .title").first
                    if heading.is_visible(timeout=500):
                        metadata["heading"] = heading.inner_text().strip()
            except Exception:
                pass
                
            # Create a final title from the best available information
            title_candidates = [
                metadata.get("caption", ""),
                metadata.get("heading", ""),
                metadata.get("aria_label", ""),
                metadata.get("alt", ""),
                metadata.get("title_attr", "")
            ]
            
            metadata["final_title"] = next((t for t in title_candidates if t), "Untitled")
            
            return metadata
            
        except Exception as e:
            print(f"Error extracting metadata: {e}")
            return {
                "final_title": "Untitled",
                "alt": alt if 'alt' in locals() else ""
            }

    def _extract_video_sources(self, page, video_element):
        """
        Extract all available video sources from a video element.
        
        Args:
            page: Playwright page
            video_element: Locator for the video element
            
        Returns:
            List of video source URLs
        """
        sources = []
        
        try:
            # Get direct src attribute
            src = video_element.get_attribute("src")
            if src and not src.startswith('data:'):
                sources.append(src)
                
            # Get source elements inside the video
            source_locator = video_element.locator("source")
            for i in range(source_locator.count()):
                source = source_locator.nth(i)
                source_src = source.get_attribute("src")
                if source_src and not source_src.startswith('data:'):
                    sources.append(source_src)
                    
            # Check for poster attribute (thumbnail)
            poster = video_element.get_attribute("poster")
            if poster and not poster.startswith('data:'):
                sources.append({"thumbnail": poster})
                
            # Try to evaluate video.currentSrc which may contain the resolved source
            try:
                current_src = page.evaluate("""(video) => {
                    return video.currentSrc || null;
                }""", video_element)
                
                if current_src and not current_src.startswith('data:'):
                    sources.append(current_src)
            except Exception:
                pass
                
            return sources
                
        except Exception as e:
            print(f"Error extracting video sources: {e}")
            return []

# Add to EricWebFileScraper class
    def _detect_special_content_structure(self, page, url):
        """
        Detect and handle special content structures like image galleries, sliders, etc.
        
        Args:
            page: Playwright page
            url: Page URL
            
        Returns:
            List of extracted media items or None if no special structures detected
        """
        try:
            # Check for common gallery structures
            gallery_selectors = [
                ".gallery", ".slider", ".carousel", 
                "[role='listbox']", "[data-testid='carousel']",
                ".image-gallery", ".lightbox-gallery"
            ]
            
            for selector in gallery_selectors:
                gallery = page.locator(selector).first
                if gallery.is_visible(timeout=1000):
                    print(f"  Detected gallery structure: {selector}")
                    
                    # Extract gallery items
                    items_locator = gallery.locator("img, .gallery-item, .carousel-item")
                    items_count = items_locator.count()
                    
                    if items_count > 0:
                        print(f"  Found {items_count} gallery items, extracting...")
                        
                        media_items = []
                        for i in range(items_count):
                            item = items_locator.nth(i)
                            if not item.is_visible(timeout=500):
                                continue
                                
                            # Check if it contains an image
                            img = item.locator("img").first
                            if img.is_visible(timeout=500):
                                src = img.get_attribute("src")
                                if src and not src.startswith('data:'):
                                    # Get metadata
                                    metadata = self._extract_media_metadata(page, img)
                                    
                                    media_items.append({
                                        'url': src,
                                        'alt': metadata.get("alt", ""),
                                        'title': metadata.get("final_title", "Gallery Image"),
                                        'credits': metadata.get("credits", ""),
                                        'source_url': url,
                                        'type': 'image',
                                        'category': 'gallery'
                                    })
                                    
                        return media_items
            
            return None  # No special structures detected
            
        except Exception as e:
            print(f"Error detecting special content structure: {e}")
            return None
    def _rate_limit(self, domain):
        """
        Implements domain-specific rate limiting to avoid being blocked.
        Should be called before making requests to a domain.
        """
        # Track last request time per domain
        if not hasattr(self, 'last_request_times'):
            self.last_request_times = {}
            
        # Default delay of 2 seconds between requests to same domain
        default_delay = 2.0  
        
        # Domain-specific delays (add more as needed)
        domain_delays = {
            'reddit.com': 3.0,
            'artstation.com': 2.5,
            'behance.net': 2.0
        }
        
        # Get appropriate delay
        delay = domain_delays.get(domain, default_delay)
        
        # Check if we need to wait
        current_time = time.time()
        last_time = self.last_request_times.get(domain, 0)
        elapsed = current_time - last_time
        
        if elapsed < delay:
            wait_time = delay - elapsed
            if self.debug_mode:
                print(f"Rate limiting: waiting {wait_time:.2f}s for {domain}")
            time.sleep(wait_time)
        
        # Update the last request time
        self.last_request_times[domain] = time.time()
    def _analyze_image_quality(self, image_url, min_width, min_height):
        """
        Analyze image quality to determine if it should be downloaded.
        
        Args:
            image_url: URL of the image
            min_width: Minimum width threshold
            min_height: Minimum height threshold
            
        Returns:
            Tuple of (should_download, reason, metadata)
        """
        try:
            # Send a HEAD request first to check content type
            head_response = requests.head(image_url, timeout=5)
            
            # Check if it's an image
            content_type = head_response.headers.get('content-type', '')
            if not content_type.startswith('image/'):
                return False, f"Not an image (Content-Type: {content_type})", {}
                
            # Check content length if available
            content_length = head_response.headers.get('content-length')
            if content_length and int(content_length) < 10000:  # Less than 10KB
                return False, f"Image too small (Size: {content_length} bytes)", {}
                
            # Only download full content if we need to check dimensions
            if min_width > 0 or min_height > 0:
                response = requests.get(image_url, stream=True, timeout=10)
                response.raise_for_status()
                
                with Image.open(BytesIO(response.content)) as img:
                    width, height = img.size
                    
                    if (min_width > 0 and width < min_width) or (min_height > 0 and height < min_height):
                        return False, f"Image too small (Dimensions: {width}x{height})", {}
                        
                    # Get additional metadata while we have the image open
                    metadata = {
                        'width': width,
                        'height': height,
                        'format': img.format,
                        'aspect_ratio': width / height if height > 0 else 0
                    }
                    
                    # Skip likely icons or tiny images
                    if width < 50 or height < 50:
                        return False, "Image too small (likely an icon)", metadata
                    
                    # Skip transparent/blank images
                    if 'A' in img.getbands() and self._is_mostly_transparent(img):
                        return False, "Image mostly transparent", metadata
                        
                    return True, "", metadata
            
            # If no dimension checks needed, assume it's good
            return True, "", {}
            
        except Exception as e:
            return False, f"Error analyzing image: {e}", {}
            
    def _is_mostly_transparent(self, img):
        """Check if an image is mostly transparent."""
        # Extract alpha channel and calculate transparency
        alpha = img.getchannel('A')
        transparent_pixels = sum(1 for pixel in alpha.getdata() if pixel < 128)
        total_pixels = alpha.width * alpha.height
        
        # If more than 80% transparent, consider it mostly transparent
        return transparent_pixels > (total_pixels * 0.8)

    def save_metadata_file(self, media_filepath, metadata, output_path):
        """Saves a comprehensive .json file alongside the media file."""
        try:
            base_filename = os.path.splitext(media_filepath)[0]
            metadata_filepath = base_filename + ".json"
            
            # Ensure metadata filepath is within the output_path for safety
            if os.path.dirname(metadata_filepath) != output_path:
                print(f"  Warning: Metadata path mismatch, not saving: {metadata_filepath}")
                return
                
            # Enrich the metadata
            enriched_metadata = metadata.copy()
            
            # Add timestamps
            enriched_metadata['download_time'] = time.time()
            enriched_metadata['download_timestamp'] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            
            # Add source and extraction information
            if 'source_url' not in enriched_metadata:
                enriched_metadata['source_url'] = "Unknown"
                
            # Add file information
            file_info = {
                'filename': os.path.basename(media_filepath),
                'extension': os.path.splitext(media_filepath)[1].lower(),
                'filepath': media_filepath,
                'size_bytes': os.path.getsize(media_filepath) if os.path.exists(media_filepath) else 0
            }
            enriched_metadata['file_info'] = file_info
            
            # Add extraction method used
            enriched_metadata['extraction_method'] = getattr(self, 'current_extraction_method', 'unknown')
            
            # Save enriched metadata
            with open(metadata_filepath, 'w', encoding='utf-8') as f:
                json.dump(enriched_metadata, f, indent=4, ensure_ascii=False)
                
        except Exception as e:
            print(f"  Error saving enriched metadata file: {e}")



    async def _process_download_queue_parallel(self, media_items_to_process, output_path, stats, **kwargs):
        """Downloads files from the queue in parallel with improved thread safety."""
        from concurrent.futures import ThreadPoolExecutor
        import threading
        import asyncio
        
        downloaded_files_data = []
        initial_file_count = kwargs.get('initial_file_count', 0)
        max_files = kwargs.get('max_files', 0)
        downloaded_images_cache = kwargs.get('downloaded_images_cache', {})
        max_workers = kwargs.get('max_workers', 4)
        
        # Create duplicates folder if needed
        move_duplicates = kwargs.get('move_duplicates', False)
        duplicates_folder = None
        if move_duplicates:
            duplicates_folder = os.path.join(output_path, "_duplicates")
            os.makedirs(duplicates_folder, exist_ok=True)
        
        total_items = len(media_items_to_process)
        print(f"Processing download queue in parallel: {total_items} items found, using {max_workers} workers")
        print(f"  Note: Files will be saved immediately as they download (progress saved every {self.save_batch_size} files)")
        
        # Create a single lock for all synchronized operations
        global_lock = threading.RLock()  # Reentrant lock to avoid deadlocks
        

        def download_worker(item_index, item_data):
            nonlocal stats, downloaded_images_cache, downloaded_files_data
            
            # Check for cancellation first
            if self.cancellation_requested or self._check_cancellation():
                print(f"\n🛑 Download cancelled by user (worker {item_index})")
                return None
            
            item_url = item_data.get('url')
            if not item_url:
                with global_lock:
                    stats["skipped_not_media"] += 1
                return None
            
            # Debug the URL we're trying to download
            print(f"Attempting to download: {item_url}")
            
            # Check if already processed - needs synchronization
            with global_lock:
                if self.check_url_processed(item_url):
                    stats["skipped_already_processed"] += 1
                    return None
                
                # Mark as being processed immediately to prevent race condition
                self.mark_url_processed(item_url)
                
                # Check max files limit under lock
                current_count = initial_file_count + len(downloaded_files_data)
                if max_files > 0 and current_count >= max_files:
                    return None
                    
                stats["downloads_attempted"] += 1
            
            # Check domain restrictions - if "same_domain_only" is enabled, check if URL domain matches
            # or is a trusted CDN domain
            if kwargs.get('same_domain_only', True):
                item_domain = urlparse(item_url).netloc
                base_url = kwargs.get('url', '')
                base_domain = urlparse(base_url).netloc
                
                # Check if this is a trusted CDN URL marked by the handler
                is_trusted_cdn = item_data.get('trusted_cdn', False)
                
                # Debug: Show what's happening
                if item_domain != base_domain:
                    with global_lock:
                        print(f"  Domain check: {item_domain} vs {base_domain}, trusted_cdn={is_trusted_cdn}")
                
                if item_domain != base_domain and not is_trusted_cdn:
                    with global_lock:
                        stats["skipped_platform"] += 1
                        print(f"Skipping off-domain URL: {item_url}")
                    return None

            try:
                # Rate limit by domain to be polite (doesn't need the lock)
                domain = urlparse(item_url).netloc
                self._rate_limit(domain)
                
                # Download the file (no lock needed for downloading)
                download_result = self.download_file(
                    item_data,
                    output_path,
                    item_index,
                    kwargs.get('filename_prefix', 'file_'),
                    kwargs.get('min_width', 0),
                    kwargs.get('min_height', 0),
                    kwargs.get('hash_algorithm', 'average_hash'),
                    kwargs.get('download_images', True),
                    kwargs.get('download_videos', True)
                )
                
                # Handle download errors
                if not download_result:
                    with global_lock:
                        stats["failed_download"] += 1
                        print(f"Download failed for {item_url}: No result returned")
                    return None
                
                file_path, file_type, width, height, file_hash, download_error = download_result
                
                if download_error:
                    with global_lock:
                        print(f"Download error for {item_url}: {download_error}")
                        stats["failed_download"] += 1
                    return None
                    
                # Success path
                print(f"Successfully downloaded: {item_url} to {file_path}")
                
                # Track file immediately for cancellation recovery
                with global_lock:
                    self.files_saved_this_session.append(file_path)
                    
                    # Save progress periodically (every N files)
                    if len(self.files_saved_this_session) % self.save_batch_size == 0:
                        print(f"  💾 Progress saved: {len(self.files_saved_this_session)} files downloaded so far")
                
                # All operations that modify shared state need locking
                with global_lock:
                    # Handle deduplication
                    is_duplicate = False
                    duplicate_info = None
                    
                    if file_type == 'image' and file_hash and IMAGEHASH_AVAILABLE and kwargs['hash_algorithm'] != 'none':
                        if file_hash in downloaded_images_cache:
                            is_duplicate = True
                            duplicate_info = downloaded_images_cache[file_hash]
                            stats["duplicates_removed"] += 1
                        else:
                            # Add to cache if not duplicate
                            downloaded_images_cache[file_hash] = {
                                'filename': os.path.basename(file_path),
                                'filepath': file_path,
                                'width': width,
                                'height': height,
                                'url': item_url
                            }
                    
                    # Handle duplicate resolution
                    if is_duplicate and duplicate_info:
                        existing_res = duplicate_info['width'] * duplicate_info['height']
                        current_res = width * height
                        keep_existing = existing_res >= current_res
                        
                        if keep_existing:
                            # Delete or move the newly downloaded file
                            if move_duplicates:
                                try:
                                    new_filename = os.path.basename(file_path)
                                    move_path = os.path.join(duplicates_folder, new_filename)
                                    os.rename(file_path, move_path)
                                    stats["duplicates_moved"] += 1
                                except Exception:
                                    os.remove(file_path)
                            else:
                                os.remove(file_path)
                            return None
                        else:
                            # Replace existing with new higher-res version
                            old_filepath = duplicate_info['filepath']
                            if move_duplicates:
                                try:
                                    old_filename = os.path.basename(old_filepath)
                                    move_path = os.path.join(duplicates_folder, old_filename)
                                    os.rename(old_filepath, move_path)
                                    stats["duplicates_moved"] += 1
                                except Exception:
                                    if os.path.exists(old_filepath): 
                                        os.remove(old_filepath)
                            else:
                                if os.path.exists(old_filepath):
                                    os.remove(old_filepath)
                            
                            # Update cache with the new, larger file
                            downloaded_images_cache[file_hash] = {
                                'filename': os.path.basename(file_path),
                                'filepath': file_path,
                                'width': width,
                                'height': height,
                                'url': item_url
                            }
                    
                    # Build file metadata
                    file_metadata = {
                        'filename': os.path.basename(file_path),
                        'filepath': file_path,
                        'url': item_url,
                        'type': file_type,
                        'width': width,
                        'height': height,
                        'hash': str(file_hash) if file_hash else None,
                        'source_page_url': kwargs.get('url', ''),
                        'alt': item_data.get('alt') if kwargs.get('extract_metadata') else None,
                        'title': item_data.get('title') if kwargs.get('extract_metadata') else None,
                        'credits': item_data.get('credits') if kwargs.get('extract_metadata') else None,
                        'original_source_url': item_data.get('source_url')
                    }
                    
                    if file_type == 'image':
                        stats["downloads_succeeded_image"] += 1
                    elif file_type == 'video':
                        stats["downloads_succeeded_video"] += 1
                    elif file_type == 'audio':
                        stats["downloads_succeeded_audio"] += 1
                    
                    # Save individual metadata file if requested
                    if kwargs.get('save_metadata_json', True):
                        self.save_metadata_file(file_path, file_metadata, output_path)
                        stats["metadata_files_saved"] += 1
                    
                    return file_metadata
                        
            except Exception as e:
                print(f"  Error processing item {item_url}: {e}")
                with global_lock:
                    stats["failed_other"] += 1
                return None
        
        # Process in batches using event loop with ThreadPoolExecutor
        loop = asyncio.get_event_loop()

        # Filter items before processing to avoid unnecessary work
        with global_lock:
            # Check max files limit before starting
            if max_files > 0 and initial_file_count >= max_files:
                print(f"Already reached max files limit ({max_files}). No additional downloads needed.")
                return downloaded_files_data, downloaded_images_cache
                
            # Filter out items that have already been processed
            filtered_items = []
            for index, item_data in enumerate(media_items_to_process):
                item_url = item_data.get('url')
                if item_url and not self.check_url_processed(item_url):
                    filtered_items.append((index, item_data))
        
        # Process in batches for better control
        batch_size = min(max_workers * 2, len(filtered_items))
        for i in range(0, len(filtered_items), batch_size):
            # Check for cancellation before each batch
            if self.cancellation_requested or self._check_cancellation():
                print(f"\n🛑 Download cancelled by user after {len(downloaded_files_data)} files")
                break
                
            batch = filtered_items[i:i+batch_size]
            print(f"  Processing batch {i//batch_size + 1}/{(len(filtered_items) + batch_size - 1)//batch_size} ({len(batch)} items)")
            
            # Create a thread pool for this batch
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # Submit batch to thread pool and run via asyncio
                futures = [loop.run_in_executor(executor, download_worker, index, item_data) 
                        for index, item_data in batch]
                
                # Wait for all futures to complete
                batch_results = await asyncio.gather(*futures, return_exceptions=True)
                
                # Process the results with proper locking
                with global_lock:
                    for result in batch_results:
                        if isinstance(result, Exception):
                            print(f"Error in download worker: {result}")
                            continue
                            
                        if result:  # If we got a valid result
                            downloaded_files_data.append(result)
                            
                    # Check if we've reached the max files limit
                    current_count = initial_file_count + len(downloaded_files_data)
                    if max_files > 0 and current_count >= max_files:
                        print(f"Reached max files limit ({max_files}). Stopping after current batch.")
                        break
        
        print(f"Parallel download complete. Downloaded {len(downloaded_files_data)} new files.")
        return downloaded_files_data, downloaded_images_cache

    def _filter_urls(self, urls, base_url, same_domain_only=True, **kwargs):
        """
        Filter URLs based on domain, patterns, and exclusions.
        
        Args:
            urls: List of URLs to filter
            base_url: Base URL for making relative URLs absolute
            same_domain_only: Whether to restrict to same domain
            **kwargs: Additional filtering options
            
        Returns:
            Filtered list of URLs
        """
        if not urls:
            return []
        
        filtered_urls = []
        base_domain = urlparse(base_url).netloc
        
        # Additional filters
        exclude_patterns = kwargs.get('exclude_patterns', [
            r'/ads/', r'/advertisement', r'/pixel', r'/tracker', r'/tracking',
            r'/cdn-cgi/', r'/favicon', r'/icon', r'/logo', r'/avatar'
        ])
        
        include_patterns = kwargs.get('include_patterns', [])
        min_url_length = kwargs.get('min_url_length', 10)
        
        # Get trusted domains from handler if available
        trusted_domains = []
        if hasattr(self, 'site_handlers'):
            for handler_name, handler_class in self.site_handlers.items():
                try:
                    handler_instance = handler_class(base_url, self)
                    if hasattr(handler_instance, 'get_trusted_domains'):
                        trusted_domains.extend(handler_instance.get_trusted_domains())
                except Exception as e:
                    if self.debug_mode:
                        print(f"Error getting trusted domains from handler {handler_name}: {e}")
        
        # Convert patterns to compiled regex
        exclude_regex = [re.compile(pattern, re.IGNORECASE) for pattern in exclude_patterns]
        include_regex = [re.compile(pattern, re.IGNORECASE) for pattern in include_patterns]
        
        # Track seen URLs to avoid duplicates
        seen_urls = set()
        
        for url in urls:
            # Skip empty URLs
            if not url or len(url) < min_url_length:
                continue
            
            # Make URL absolute if relative
            if url.startswith('/'):
                parsed_base = urlparse(base_url)
                url = f"{parsed_base.scheme}://{parsed_base.netloc}{url}"
            elif url.startswith('./') or url.startswith('../'):
                url = urljoin(base_url, url)
            elif not url.startswith(('http://', 'https://')):
                # Skip non-http URLs (like data:, javascript:, etc.)
                continue
            
            # Skip if already seen
            if url in seen_urls:
                continue
            
            # Check domain restriction
            parsed_url = urlparse(url)
            url_domain = parsed_url.netloc
            
            is_trusted_domain = False
            if trusted_domains:
                # Check if this URL matches any trusted domain
                is_trusted_domain = any(trusted_domain in url_domain for trusted_domain in trusted_domains)
            
            # If same_domain_only is enabled, check domain unless it's a trusted domain
            if same_domain_only and url_domain != base_domain and not is_trusted_domain:
                continue
            
            # Check exclusion patterns
            if any(pattern.search(url) for pattern in exclude_regex):
                continue
            
            # Check inclusion patterns if specified
            if include_regex and not any(pattern.search(url) for pattern in include_regex):
                continue
            
            # URL passed all filters
            filtered_urls.append(url)
            seen_urls.add(url)
        
        return filtered_urls

    def _get_random_user_agent(self):
        """
        Returns a random realistic user agent to avoid detection.
        """
        # Define a list of modern, realistic user agents
        user_agents = [
            # Chrome on Windows
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.99 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36",
            # Chrome on macOS
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.99 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36",
            # Firefox on Windows
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:96.0) Gecko/20100101 Firefox/96.0",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:95.0) Gecko/20100101 Firefox/95.0",
            # Firefox on macOS
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:96.0) Gecko/20100101 Firefox/96.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:95.0) Gecko/20100101 Firefox/95.0",
            # Safari on macOS
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.2 Safari/605.1.15",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.1 Safari/605.1.15",
            # Edge on Windows
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.99 Safari/537.36 Edg/97.0.1072.69",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36 Edg/96.0.1054.62"
        ]
        
        return random.choice(user_agents)

    async def _init_direct_playwright(self, **kwargs):
        """Initializes an async Playwright instance with full stealth functionality."""
        if not PLAYWRIGHT_AVAILABLE:
            print("Playwright library not available.")
            return None

        try:
            print("Initializing Playwright (async)...")
            playwright_instance = await async_playwright().start()
            if not playwright_instance:
                print("Failed to start Playwright")
                return None

            user_agent = self._get_random_user_agent()
            print(f"Using user agent: {user_agent[:50]}...")

            browser_args = []
            if self.use_stealth_mode:
                browser_args = [
                    '--disable-blink-features=AutomationControlled',
                    '--disable-features=IsolateOrigins,site-per-process',
                    '--disable-site-isolation-trials',
                    '--disable-features=BlockInsecurePrivateNetworkRequests',
                    '--disable-web-security',
                    '--no-sandbox'
                ]

            # Define context options BEFORE launching browser
            context_options = {
                "user_agent": user_agent,
                "viewport": {"width": 5120, "height": 2880},
                "device_scale_factor": 1.0
            }
            if self.use_stealth_mode:
                context_options.update({
                    "locale": "en-US",
                    "timezone_id": "America/New_York",
                    "has_touch": False,
                    "is_mobile": False,
                    "color_scheme": 'light'
                })

            use_persistent = kwargs.get("dump_cache_after_run", False)
            user_data_dir = None

            if use_persistent:
                user_data_dir = pathlib.Path(tempfile.mkdtemp(prefix="pwprof_"))
                browser = await playwright_instance.chromium.launch_persistent_context(
                    user_data_dir=str(user_data_dir),
                    headless=True,
                    args=browser_args,
                    **context_options
                )
                context = browser  # persistent context IS the context
                page = await context.new_page()
            else:
                browser = await playwright_instance.chromium.launch(
                    headless=True, args=browser_args
                )
                context = await browser.new_context(**context_options)
                page = await context.new_page()

            self.pw_user_data_dir = str(user_data_dir) if user_data_dir else None

            # Add stealth mode script to avoid detection
            print("Adding stealth script...")
            stealth_js = """
            () => {
                // Pass WebDriver test
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => false,
                });
                
                // Pass Chrome test
                window.chrome = {
                    runtime: {},
                };
                
                // Pass permissions test
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ?
                        Promise.resolve({ state: Notification.permission }) :
                        originalQuery(parameters)
                );
                
                // Prevent iframe detection
                const iframe = document.createElement('iframe');
                iframe.srcdoc = "<!DOCTYPE html><html><head></head><body></body></html>";
                document.head.appendChild(iframe);
                window.navigator.plugins = iframe.contentWindow.navigator.plugins;
                document.head.removeChild(iframe);
                
                // Use webGL renderer
                const getParameter = WebGLRenderingContext.prototype.getParameter;
                WebGLRenderingContext.prototype.getParameter = function(parameter) {
                    // UNMASKED_VENDOR_WEBGL
                    if (parameter === 37445) {
                        return 'Intel Inc.';
                    }
                    // UNMASKED_RENDERER_WEBGL
                    if (parameter === 37446) {
                        return 'Intel Iris OpenGL Engine';
                    }
                    return getParameter.apply(this, arguments);
                };
                
                // Add language and platform overrides
                Object.defineProperty(navigator, 'platform', {
                    get: () => 'Win32',
                });
                
                Object.defineProperty(navigator, 'hardwareConcurrency', {
                    get: () => 8,
                });
                
                // Mock plugins for more authenticity
                Object.defineProperty(navigator, 'plugins', {
                    get: () => {
                        const plugins = [
                            { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
                            { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '' },
                            { name: 'Native Client', filename: 'internal-nacl-plugin', description: '' }
                        ];
                        
                        plugins.__proto__ = window.PluginArray.prototype;
                        
                        plugins.item = idx => plugins[idx];
                        plugins.namedItem = name => plugins.find(plugin => plugin.name === name);
                        
                        return plugins;
                    }
                });
            }
            """
            
            # Explicitly await script injection
            await context.add_init_script(stealth_js)
            
            # Set navigation timeout
            print("Setting navigation timeout...")
            context.set_default_navigation_timeout(90 * 1000)
            
            # Create page with proper error handling
            print("Creating page...")
            page = await context.new_page()
            if not page:
                print("Failed to create page")
                if context:
                    await context.close()
                if browser:
                    await browser.close()
                if playwright_instance:
                    await playwright_instance.stop()
                return None
            
            # Handle dialogs automatically
            page.on("dialog", lambda dialog: dialog.dismiss())
            
            print("Playwright initialization complete!")
            
            # Store references for cleanup
            self.pw_resources = (playwright_instance, browser, context, page, user_data_dir)
            return self.pw_resources
            
        except Exception as e:
            print(f"Failed to initialize Playwright: {e}")
            traceback.print_exc()
            
            # Clean up any resources created so far
            try:
                if 'page' in locals() and page:
                    await page.close()
            except Exception as page_err:
                print(f"Error closing page: {page_err}")
                
            try:
                if 'context' in locals() and context:
                    await context.close()
            except Exception as ctx_err:
                print(f"Error closing context: {ctx_err}")
                
            try:
                if 'browser' in locals() and browser:
                    await browser.close()
            except Exception as browser_err:
                print(f"Error closing browser: {browser_err}")
                
            try:
                if 'playwright_instance' in locals() and playwright_instance:
                    await playwright_instance.stop()
            except Exception as pw_err:
                print(f"Error stopping Playwright: {pw_err}")
                
            return None

    def _verify_content_integrity(self, url, headers=None):
        """
        Verify if content at URL is valid and accessible.
        
        Args:
            url: URL to verify
            headers: Optional HTTP headers
            
        Returns:
            tuple: (is_valid, content_type, status_code, content_length)
        """
        try:
            if not headers:
                headers = {'User-Agent': self._get_random_user_agent()}
            
            # Make a HEAD request to check basics without downloading content
            response = requests.head(url, timeout=10, headers=headers, allow_redirects=True)
            
            # Check status code
            if response.status_code != 200:
                return False, None, response.status_code, 0
            
            # Check content type
            content_type = response.headers.get('content-type', '').lower()
            content_length = int(response.headers.get('content-length', 0))
            
            # Basic validation by content type
            is_valid = False
            
            # For images
            if any(ct in content_type for ct in ['image/jpeg', 'image/png', 'image/gif', 'image/webp']):
                # Check reasonable size
                is_valid = content_length >= 5000 and content_length < 20000000  # 5KB to 20MB
            
            # For videos
            elif any(ct in content_type for ct in ['video/mp4', 'video/webm', 'video/quicktime']):
                # Check reasonable size
                is_valid = content_length >= 50000 and content_length < 200000000  # 50KB to 200MB
            
            return is_valid, content_type, response.status_code, content_length
            
        except requests.exceptions.RequestException as e:
            print(f"Error verifying content at {url}: {e}")
            return False, None, 0, 0

    async def _scroll_down_fixed(self, page: AsyncPage, times: int, delay_ms: int):
        """Scrolls down the page a fixed number of times (async version)."""
        if not page: return
        print(f"Starting fixed scroll: times={times}, delay={delay_ms}ms")
        for i in range(times):
            try:
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(delay_ms)
            except Exception as scroll_err:
                print(f"  Error during fixed scroll {i+1}: {scroll_err}")
                break
        print("Finished fixed scroll.")


    # --- Generic Extraction Methods (Already Implemented in previous steps) ---
    async def _extract_media_from_pw_page(self, page: AsyncPage, url: str, **kwargs):
        """Generic extraction of media items using Playwright page (async version)."""
        print("Using generic Playwright extraction...")
        media_items = []
        
        try:
            # Extract images
            if kwargs.get('download_images', True):
                img_locator = page.locator("img:not([width='16']):not([width='24']):not([width='32'])")
                img_count = await img_locator.count()
                print(f"Found {img_count} potential image elements")
                
                for i in range(img_count):
                    img = img_locator.nth(i)
                    
                    # Skip if not visible
                    is_visible = await img.is_visible(timeout=500)
                    if not is_visible:
                        continue
                        
                    # Get image attributes
                    src = await img.get_attribute("src")
                    srcset = await img.get_attribute("srcset")
                    alt = await img.get_attribute("alt") or ""
                    title_attr = await img.get_attribute("title") or ""
                    
                    # Skip common non-content images
                    if not src or any(x in src.lower() for x in ['spacer.gif', 'pixel.gif', 'transparent.gif', 'icon']):
                        continue
                        
                    # Process srcset
                    image_url = src
                    if srcset:
                        high_res = self._get_highest_res_from_srcset(srcset)
                        if high_res:
                            image_url = high_res
                    
                    # Skip data URLs
                    if not image_url or image_url.startswith('data:'):
                        continue
                        
                    # Make absolute URL
                    if image_url.startswith('/'):
                        parsed = urlparse(url)
                        base = f"{parsed.scheme}://{parsed.netloc}"
                        image_url = urljoin(base, image_url)
                    
                    # Look for parent containers
                    caption = ""
                    credits = ""
                    try:
                        figure = img.locator("xpath=ancestor::figure[1]").first
                        figure_visible = await figure.is_visible(timeout=500)
                        
                        if figure_visible:
                            figcaption = figure.locator("figcaption").first
                            figcaption_visible = await figcaption.is_visible(timeout=500)
                            if figcaption_visible:
                                caption = await figcaption.inner_text()
                                caption = caption.strip()
                            
                            credit_elem = figure.locator(".credit, .author, [rel='author']").first
                            credit_visible = await credit_elem.is_visible(timeout=500)
                            if credit_visible:
                                credits = await credit_elem.inner_text()
                                credits = credits.strip()
                    except Exception:
                        pass
                    
                    title = caption or alt or title_attr or "Image from " + urlparse(url).netloc
                    
                    media_items.append({
                        'url': image_url,
                        'alt': alt,
                        'title': title,
                        'credits': credits,
                        'source_url': url,
                        'type': 'image'
                    })
            
            bg_imgs = await page.evaluate("""
                () => Array.from(document.querySelectorAll('*'))
                    .map(el => getComputedStyle(el).backgroundImage)
                    .filter(bg => bg && bg.startsWith('url('))
                    .map(bg => bg.slice(4, -1).replace(/["']/g, ""))
            """)
            for bg_url in bg_imgs:
                if bg_url and not bg_url.startswith('data:'):
                    media_items.append({
                        'url': bg_url,
                        'title': "Background Image",
                        'source_url': url,
                        'type': 'image'
                    })
            # --- Extract images from iframes ---
            iframe_elements = await page.query_selector_all("iframe")
            for iframe in iframe_elements:
                try:
                    frame = await iframe.content_frame()
                    if frame:
                        print("Extracting images from iframe...")
                        iframe_items = await self._extract_media_from_pw_page(frame, frame.url, **kwargs)
                        if iframe_items:
                            media_items.extend(iframe_items)
                except Exception as e:
                    print(f"Error extracting from iframe: {e}")

            # --- Extract images from data-* attributes on any element ---
            data_attrs = ["data-large", "data-image", "data-original", "data-url"]
            for attr in data_attrs:
                elements = await page.locator(f"[{attr}]").all()
                for el in elements:
                    url = await el.get_attribute(attr)
                    if url and url.startswith("http"):
                        media_items.append({
                            'url': url,
                            'title': f"Image from {attr}",
                            'source_url': url,
                            'type': 'image'
                        })

            # Extract videos if enabled
            if kwargs.get('download_videos', False):
                video_locator = page.locator("video, source[type*='video']")
                video_count = await video_locator.count()
                print(f"Found {video_count} potential video elements")
                
                for i in range(video_count):
                    video = video_locator.nth(i)
                    
                    video_url = await video.get_attribute("src")
                    if not video_url or video_url.startswith('data:'):
                        continue
                        
                    # Make URL absolute if relative
                    if video_url.startswith('/'):
                        parsed = urlparse(url)
                        base = f"{parsed.scheme}://{parsed.netloc}"
                        video_url = urljoin(base, video_url)
                    
                    media_items.append({
                        'url': video_url,
                        'title': "Video from " + urlparse(url).netloc,
                        'source_url': url,
                        'type': 'video'
                    })

            picture_locator = page.locator("picture source")
            picture_count = await picture_locator.count()
            for i in range(picture_count):
                source = picture_locator.nth(i)
                srcset = await source.get_attribute("srcset")
                if srcset:
                    high_res = self._get_highest_res_from_srcset(srcset)
                    if high_res and not high_res.startswith('data:'):
                        media_items.append({
                            'url': high_res,
                            'title': "Responsive Image",
                            'source_url': url,
                            'type': 'image'
                        })
            
            print(f"Generic Playwright extraction found {len(media_items)} media items")
            return media_items
            
        except Exception as e:
            print(f"Error during generic Playwright extraction: {e}")
            traceback.print_exc()
            return []

    async def _extract_media_from_scrapling_page(self, response, url, **kwargs):
        """
        Generic extraction of media items using Scrapling response (async version).
        This is used as a fallback when site-specific handlers don't override extraction.
        """
        print("Using generic Scrapling extraction...")
        media_items = []
        
        try:
            # Get HTML content from the response
            html_content = ""
            if hasattr(response, 'text'):
                html_content = response.text
            elif hasattr(response, 'html_content'):
                html_content = response.html_content
            elif hasattr(response, 'content'):
                try:
                    html_content = response.content.decode('utf-8', errors='ignore')
                except:
                    pass
                    
            if not html_content:
                print("Could not get HTML content from Scrapling response")
                return []
                
            # Extract image URLs
            img_patterns = [
                r'<img[^>]+src=["\'](https?://[^"\']+)["\']',
                r'<img[^>]+srcset=["\'](https?://[^"\']+)["\']',
                r'url\(["\']?(https?://[^"\'()]+)["\']?\)',  # CSS background images
            ]
            
            seen_urls = set()
            
            # Process patterns based on what we want to download
            if kwargs.get('download_images', True):
                for pattern in img_patterns:
                    matches = re.findall(pattern, html_content)
                    for img_url in matches:
                        # Skip duplicates and invalid URLs
                        if img_url in seen_urls or not img_url or img_url.startswith('data:'):
                            continue
                        
                        seen_urls.add(img_url)
                        
                        # Skip common non-content images
                        if any(x in img_url.lower() for x in ['spacer.gif', 'pixel.gif', 'transparent.gif', 'icon']):
                            continue
                            
                        # Add to media items
                        media_items.append({
                            'url': img_url,
                            'title': "Image from " + urlparse(url).netloc,
                            'source_url': url,
                            'type': 'image'
                        })
            
            # Extract video URLs if enabled
            if kwargs.get('download_videos', False):
                video_patterns = [
                    r'<video[^>]+src=["\'](https?://[^"\']+)["\']',
                    r'<source[^>]+src=["\'](https?://[^"\']+)["\']'
                ]
                
                for pattern in video_patterns:
                    matches = re.findall(pattern, html_content)
                    for video_url in matches:
                        if video_url in seen_urls or not video_url:
                            continue
                            
                        seen_urls.add(video_url)
                        
                        # Add to media items
                        media_items.append({
                            'url': video_url,
                            'title': "Video from " + urlparse(url).netloc,
                            'source_url': url,
                            'type': 'video'
                        })
                    
            print(f"Generic Scrapling extraction found {len(media_items)} media items")
            return media_items
            
        except Exception as e:
            print(f"Error during generic Scrapling extraction: {e}")
            traceback.print_exc()
            return []


    def _safe_playwright_operation(self, operation, error_msg="Playwright operation failed", 
                                retry_count=1, recovery_action=None):
        """
        Execute a Playwright operation safely with retries and error recovery.
        
        Args:
            operation: Function to execute (lambda or function reference)
            error_msg: Message to log on failure
            retry_count: Number of retry attempts
            recovery_action: Optional function to call for recovery before retry
            
        Returns:
            Operation result or None on failure
        """
        for attempt in range(retry_count + 1):
            try:
                result = operation()
                return result
            except Exception as e:
                print(f"{error_msg}: {e}")
                if attempt < retry_count:
                    print(f"Retrying... (Attempt {attempt + 1}/{retry_count})")
                    if recovery_action:
                        try:
                            recovery_action()
                        except Exception as rec_err:
                            print(f"Recovery action failed: {rec_err}")
                else:
                    traceback.print_exc() if self.debug_mode else None
                    return None

    # ---  Advanced Media types ---
    async def _extract_audio_sources(self, page):
        """Extract audio sources from the page (async version)."""
        audio_items = []
        
        try:
            audio_locator = page.locator("audio, audio source")
            audio_count = await audio_locator.count()
            print(f"Found {audio_count} potential audio elements")
            
            for i in range(audio_count):
                audio = audio_locator.nth(i)
                
                audio_url = await audio.get_attribute("src")
                if not audio_url or audio_url.startswith('data:'):
                    continue
                    
                if audio_url.startswith('/'):
                    parsed = urlparse(page.url)
                    base = f"{parsed.scheme}://{parsed.netloc}"
                    audio_url = urljoin(base, audio_url)
                
                title = ""
                try:
                    parent = audio.locator("xpath=./parent::*").first
                    title_elem = parent.locator(".title, [title], [aria-label]").first
                    title_visible = await title_elem.is_visible(timeout=500)
                    if title_visible:
                        text = await title_elem.inner_text()
                        title_attr = await title_elem.get_attribute("title")
                        aria = await title_elem.get_attribute("aria-label")
                        title = text or title_attr or aria
                except:
                    pass
                
                audio_items.append({
                    'url': audio_url,
                    'title': title or "Audio from " + urlparse(page.url).netloc,
                    'source_url': page.url,
                    'type': 'audio'
                })
        
        except Exception as e:
            print(f"Error extracting audio sources: {e}")
        
        return audio_items

    def export_metadata(self, metadata_items, output_path, format="json"):
        """
        Export metadata in various formats.
        
        Args:
            metadata_items: List of metadata dictionaries
            output_path: Directory to save output
            format: Output format (json, csv, md)
            
        Returns:
            Path to the output file
        """
        if not metadata_items:
            return None
        
        try:
            if format.lower() == "json":
                # Export as JSON
                output_file = os.path.join(output_path, "metadata_export.json")
                with open(output_file, "w", encoding="utf-8") as f:
                    json.dump(metadata_items, f, indent=2)
                
            elif format.lower() == "csv":
                # Export as CSV
                import csv
                output_file = os.path.join(output_path, "metadata_export.csv")
                
                # Get all possible fields
                fields = set()
                for item in metadata_items:
                    fields.update(item.keys())
                
                # Sort fields to ensure consistent output
                fields = sorted(list(fields))
                
                with open(output_file, "w", encoding="utf-8", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=fields)
                    writer.writeheader()
                    for item in metadata_items:
                        writer.writerow(item)
                
            elif format.lower() == "md":
                # Export as Markdown
                output_file = os.path.join(output_path, "metadata_export.md")
                with open(output_file, "w", encoding="utf-8") as f:
                    f.write("# Media Metadata Export\n\n")
                    f.write(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                    
                    for i, item in enumerate(metadata_items):
                        f.write(f"## Item {i+1}\n\n")
                        for key, value in item.items():
                            f.write(f"- **{key}**: {value}\n")
                        f.write("\n")
            
            else:
                print(f"Unsupported export format: {format}")
                return None
            
            print(f"Exported metadata to: {output_file}")
            return output_file
            
        except Exception as e:
            print(f"Error exporting metadata: {e}")
            return None

class SessionManager:
    """
    Manages browser sessions and authentication state with clear async/sync separation.
    """
    def __init__(self, base_path="sessions"):
        self.base_path = base_path
        self.active_sessions = {}
        self.session_metadata = {}
        
        # Create sessions directory if it doesn't exist
        os.makedirs(self.base_path, exist_ok=True)
        self._load_session_metadata()
    
    def _get_domain_session_path(self, domain):
        """Get path to session storage for a domain. (Sync)"""
        # Sanitize domain for filename
        safe_domain = re.sub(r'[^\w\-\.]', '_', domain)
        return os.path.join(self.base_path, f"{safe_domain}_session.json")
    
    def _load_session_metadata(self):
        """Load metadata about all stored sessions. (Sync)"""
        metadata_path = os.path.join(self.base_path, "sessions_metadata.json")
        if os.path.exists(metadata_path):
            try:
                with open(metadata_path, 'r') as f:
                    self.session_metadata = json.load(f)
            except Exception as e:
                print(f"Error loading session metadata: {e}")
                self.session_metadata = {}
    
    def _save_session_metadata(self):
        """Save metadata about all stored sessions. (Sync)"""
        metadata_path = os.path.join(self.base_path, "sessions_metadata.json")
        try:
            with open(metadata_path, 'w') as f:
                json.dump(self.session_metadata, f, indent=2)
        except Exception as e:
            print(f"Error saving session metadata: {e}")
    
    def has_valid_session(self, domain):
        """Check if there's a valid session for the domain. (Sync)"""
        if domain in self.session_metadata:
            # Check expiration if set
            expiry = self.session_metadata[domain].get('expires_at', 0)
            if expiry == 0 or expiry > time.time():
                # Check if session file exists
                session_path = self._get_domain_session_path(domain)
                return os.path.exists(session_path)
        return False
    
    def get_session_path(self, domain):
        """Get the path to the session file for a domain. (Sync)"""
        return self._get_domain_session_path(domain)
    
    async def store_session(self, domain, context, expiry_seconds=86400):
        """
        Store a browser context's session for a domain. (Async)
        
        Args:
            domain: Domain to store session for
            context: Playwright browser context
            expiry_seconds: Session validity in seconds (default: 24 hours)
            
        Returns:
            bool: Success status
        """
        try:
            session_path = self._get_domain_session_path(domain)
            
            # Save browser state - this needs to be awaited (async operation)
            await context.storage_state(path=session_path)
            
            # Update metadata (sync operation)
            self.session_metadata[domain] = {
                'created_at': time.time(),
                'expires_at': time.time() + expiry_seconds,
                'path': session_path
            }
            
            # Save metadata (sync operation)
            self._save_session_metadata()
            
            print(f"Stored session for {domain}")
            return True
        except Exception as e:
            print(f"Error storing session for {domain}: {e}")
            return False
    
    async def load_into_context(self, domain, browser):
        """
        Load a stored session into a new browser context. (Async)
        
        Args:
            domain: Domain to load session for
            browser: Playwright browser instance
            
        Returns:
            New browser context with loaded session, or None if failed
        """
        if not self.has_valid_session(domain):
            return None
        
        try:
            session_path = self._get_domain_session_path(domain)
            # This needs to be awaited (async operation)
            context = await browser.new_context(storage_state=session_path)
            print(f"Loaded session for {domain}")
            return context
        except Exception as e:
            print(f"Error loading session for {domain}: {e}")
            return None
    
    def delete_session(self, domain):
        """Delete a stored session for a domain. (Sync)"""
        try:
            session_path = self._get_domain_session_path(domain)
            if os.path.exists(session_path):
                os.remove(session_path)
            
            if domain in self.session_metadata:
                del self.session_metadata[domain]
                self._save_session_metadata()
            
            print(f"Deleted session for {domain}")
            return True
        except Exception as e:
            print(f"Error deleting session for {domain}: {e}")
            return False

# --- Node Registration ---
NODE_CLASS_MAPPINGS = {
    "EricWebFileScraper_v082": EricWebFileScraper
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "EricWebFileScraper_v082": "Web Image Scraper v0.82"
}