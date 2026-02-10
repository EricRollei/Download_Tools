"""
Gallery Dl Downloader

Description: Gallery-dl downloader node for ComfyUI - downloads media from 100+ websites including Instagram, Reddit, Twitter, etc.
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
- Uses gallery-dl (GNU GPL v2) by Mike Fährmann: https://github.com/mikf/gallery-dl
- See CREDITS.md for complete list of all dependencies
"""

"""
Gallery-dl Downloader Node for ComfyUI
Downloads images and media from various websites using gallery-dl

Features:
- Download from URLs or URL files
- Browser cookie support
- Download archive to avoid duplicates
- Video filtering options
- Metadata extraction
- Configurable output directory

Author: Eric Hiss
Version: 1.0.0
Date: July 2025
"""

import os
import re
import shutil
import json
import subprocess
import tempfile
import urllib.parse
import folder_paths

from pathlib import Path
from typing import Any, Dict, List, Tuple

# Import persistent settings manager
try:
    from ..utils.persistent_settings import get_persistent_setting, set_persistent_setting
    PERSISTENT_SETTINGS_AVAILABLE = True
except ImportError:
    try:
        import sys
        utils_dir = os.path.dirname(os.path.dirname(__file__))
        if utils_dir not in sys.path:
            sys.path.insert(0, utils_dir)
        from utils.persistent_settings import get_persistent_setting, set_persistent_setting
        PERSISTENT_SETTINGS_AVAILABLE = True
    except ImportError:
        PERSISTENT_SETTINGS_AVAILABLE = False
        def get_persistent_setting(node_type, key, default=""):
            return default
        def set_persistent_setting(node_type, key, value):
            return False
        print("Warning: persistent_settings not available. Config paths will not persist.")


class GalleryDLDownloader:
    def __init__(
        self,
        url_list: List[str] = None,
        url_file: str = None,
        output_dir: str = "./gallery-dl-output",
        config_path: str = None,
        cookie_file: str = None,
        use_browser_cookies: bool = False,
        browser_name: str = "firefox",
        use_download_archive: bool = True,
        archive_file: str = "./gallery-dl-archive.sqlite3",
        skip_videos: bool = False,
        extract_metadata: bool = True,
        organize_files: bool = True,
        # New advanced options
        instagram_include: str = "posts",
        extra_options: str = "",
        # Minimum resolution filtering
        min_image_width: int = 768,
        min_image_height: int = 768,
        filter_by_resolution: bool = True,
        # Timeout settings
        download_timeout: int = 1800,
    ):
        self.url_list = url_list or []
        self.url_file = url_file
        self.output_dir = output_dir
        self.config_path = config_path
        self.cookie_file = cookie_file
        self.use_browser_cookies = use_browser_cookies
        self.browser_name = browser_name
        self.use_download_archive = use_download_archive
        self.archive_file = archive_file
        self.skip_videos = skip_videos
        self.extract_metadata = extract_metadata
        self.organize_files = organize_files
        self.instagram_include = instagram_include
        self.extra_options = extra_options
        self.min_image_width = min_image_width
        self.min_image_height = min_image_height
        self.filter_by_resolution = filter_by_resolution
        self.download_timeout = download_timeout
        
        # Initialize debug info
        self.debug_info = []  # Store debug information for status reporting

    def _check_gallery_dl_installed(self) -> bool:
        """Check if gallery-dl is installed and accessible."""
        try:
            result = subprocess.run(
                ["gallery-dl", "--version"], capture_output=True, text=True, timeout=10
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def _build_command(self, urls: List[str]) -> List[str]:
        command = ["gallery-dl"]

        command += ["-d", self.output_dir]

        # Detect target sites for better authentication handling
        target_sites = set()
        for url in urls:
            if 'instagram.com' in url:
                target_sites.add('instagram')
            elif 'reddit.com' in url:
                target_sites.add('reddit')
            elif 'twitter.com' in url or 'x.com' in url:
                target_sites.add('twitter')
            elif 'flickr.com' in url:
                target_sites.add('flickr')
            elif 'deviantart.com' in url:
                target_sites.add('deviantart')
            elif '500px.com' in url:
                target_sites.add('500px')
            elif 'pinterest' in url:
                target_sites.add('pinterest')
            elif 'bsky.app' in url or 'bluesky' in url:
                target_sites.add('bluesky')
            elif 'tumblr.com' in url:
                target_sites.add('tumblr')
            elif 'artstation.com' in url:
                target_sites.add('artstation')
        
        if target_sites:
            self.debug_info.append(f"🎯 Detected target sites: {', '.join(target_sites)}")
            
        # Check for known problematic sites
        if 'reddit' in target_sites:
            self.debug_info.append("⚠️ WARNING: Reddit may hang or require updated API credentials")
            self.debug_info.append("   Consider testing with Instagram or other sites first")

        # Use config file if provided (contains site-specific credentials)
        if self.config_path:
            command += ["--config", self.config_path]
            self.debug_info.append(f"📄 Using config file: {self.config_path}")

        # Handle authentication: Browser cookies toggle vs cookie file
        # When use_browser_cookies is TRUE: use browser cookies (even if cookie file exists)
        # When use_browser_cookies is FALSE: use cookie file if provided
        if self.use_browser_cookies:
            # User explicitly wants browser cookies
            command += ["--cookies-from-browser", self.browser_name]
            self.debug_info.append(f"🍪 Using cookies from {self.browser_name} browser (toggle enabled)")
            if self.cookie_file:
                self.debug_info.append(f"   ℹ️ Note: Cookie file '{self.cookie_file}' ignored - browser cookies selected")
            # Test if browser cookies can be accessed
            self._test_browser_cookie_access()
        elif self.cookie_file:
            # Use cookie file when browser cookies toggle is off
            converted_cookie_file = self._convert_cookie_file()
            if converted_cookie_file:
                command += ["--cookies", converted_cookie_file]
                self.debug_info.append(f"🍪 Using cookie file: {converted_cookie_file}")
                if 'instagram' in target_sites:
                    self.debug_info.append("🔗 Instagram + cookie file - optimal setup!")

        if self.use_download_archive:
            command += ["--download-archive", self.archive_file]
            self.debug_info.append(f"📦 Using download archive: {self.archive_file}")

        if self.skip_videos:
            command += [
                "--filter",
                "extension not in ('mp4', 'webm', 'mkv', 'avi', 'mov', 'wmv', 'flv', 'm4v')",
            ]
            self.debug_info.append("🎬 Video files will be skipped")

        # Add minimum resolution filter for images if enabled
        if self.filter_by_resolution and (self.min_image_width > 0 or self.min_image_height > 0):
            # gallery-dl filter expression for minimum resolution
            # IMPORTANT: Not all extractors provide width/height metadata (e.g., Bunkr, Cyberdrop)
            # gallery-dl uses eval() with metadata as locals(), so we can use locals().get()
            # If width/height don't exist, we default to 99999 so the file passes the filter
            # (download files with unknown dimensions rather than skip them)
            filter_expr = []
            if self.min_image_width > 0:
                # If width is not available in metadata, default to 99999 (pass filter)
                filter_expr.append(f"locals().get('width', 99999) >= {self.min_image_width}")
            if self.min_image_height > 0:
                # If height is not available in metadata, default to 99999 (pass filter)
                filter_expr.append(f"locals().get('height', 99999) >= {self.min_image_height}")
            
            # Combine with video filter if needed, or apply image filter
            # Note: gallery-dl only allows one --filter, so we need to combine
            if self.skip_videos:
                # Already added video filter above, need to modify it
                # Remove the last filter we added and combine
                command = [c for c in command if c != "--filter"]
                command = [c for c in command if "extension not in" not in c]
                combined_filter = f"(extension not in ('mp4', 'webm', 'mkv', 'avi', 'mov', 'wmv', 'flv', 'm4v')) and ({' and '.join(filter_expr)})"
                command += ["--filter", combined_filter]
            else:
                # Only filter images by resolution (videos pass through)
                # Apply filter only to images, let videos through
                # Also pass through if width/height are not available (unknown dimensions)
                filter_condition = f"(extension in ('mp4', 'webm', 'mkv', 'avi', 'mov', 'wmv', 'flv', 'm4v')) or ({' and '.join(filter_expr)})"
                command += ["--filter", filter_condition]
            
            self.debug_info.append(f"📐 Minimum resolution filter: {self.min_image_width}x{self.min_image_height}px (files with unknown dimensions will be downloaded)")

        # Add rate limiting to be respectful to servers (use correct format)
        command += ["--sleep", "1.0"]
        
        # Add retry logic
        command += ["--retries", "3"]
        
        self.debug_info.append(f"⚡ Rate limiting: 1.0 second between requests, 3 retries on failure")

        # Handle advanced options by creating a dynamic config file
        if self.instagram_include != "posts" or self.extra_options:
            dynamic_config_path = self._create_dynamic_config(target_sites)
            if dynamic_config_path:
                command += ["--config", dynamic_config_path]
                self.debug_info.append(f"📄 Using dynamic config: {dynamic_config_path}")

        # Parse any extra options from the extra_options field
        if self.extra_options:
            extra_args = self._parse_extra_options(self.extra_options)
            if extra_args:
                command.extend(extra_args)
                self.debug_info.append(f"➕ Added extra options: {' '.join(extra_args)}")

        command += urls
        return command

    def _create_dynamic_config(self, target_sites: set) -> str:
        """Create a dynamic config file with advanced options."""
        try:
            # Create a temporary config file
            config_data = {}
            
            # Add Instagram-specific options
            if 'instagram' in target_sites and self.instagram_include != "posts":
                config_data["extractor"] = {
                    "instagram": {
                        "include": self.instagram_include
                    }
                }
                self.debug_info.append(f"📸 Instagram include: {self.instagram_include}")
            
            # If we have config data, write it to a temporary file
            if config_data:
                import tempfile
                temp_config = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, dir=self.output_dir)
                json.dump(config_data, temp_config, indent=2)
                temp_config.close()
                
                self.debug_info.append(f"📄 Created dynamic config with {len(config_data)} sections")
                return temp_config.name
            
        except Exception as e:
            self.debug_info.append(f"❌ Error creating dynamic config: {e}")
        
        return None

    def _parse_extra_options(self, extra_options: str) -> List[str]:
        """Parse extra command-line options for gallery-dl."""
        try:
            # Split by spaces but respect quoted strings
            import shlex
            args = shlex.split(extra_options)
            
            # Validate that arguments start with -- or -
            valid_args = []
            for arg in args:
                if arg.startswith('-'):
                    valid_args.append(arg)
                elif valid_args and not valid_args[-1].startswith('-'):
                    # This is likely a value for the previous argument
                    valid_args.append(arg)
                else:
                    # This is an argument value
                    valid_args.append(arg)
            
            return valid_args
            
        except Exception as e:
            self.debug_info.append(f"❌ Error parsing extra options: {e}")
            return []

    def _organize_files_by_type(self, downloaded_files: List[str]) -> None:
        """Sort downloaded files into subfolders by type (images, videos, etc.) within each profile directory.
        Only organizes files that are NOT already in images/, videos/, audio/, or other/ folders."""
        if not downloaded_files:
            self.debug_info.append("📂 No files to organize")
            return
            
        try:
            # Define file type categories
            image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.tiff', '.svg', '.heic', '.avif'}
            video_extensions = {'.mp4', '.webm', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.m4v', '.3gp', '.ogv', '.mpg', '.mpeg'}
            audio_extensions = {'.mp3', '.wav', '.flac', '.aac', '.ogg', '.m4a', '.wma', '.opus'}
            
            # Folders that indicate file is already organized - skip these
            organized_folder_names = {'images', 'videos', 'audio', 'other'}
            
            # Group files by their parent directory (profile/site directories)
            files_by_profile = {}
            
            for file_path in downloaded_files:
                if not os.path.exists(file_path):
                    self.debug_info.append(f"⚠️ File no longer exists: {os.path.basename(file_path)}")
                    continue
                
                # Skip files that are already in an organized folder
                parent_folder = os.path.basename(os.path.dirname(file_path))
                if parent_folder.lower() in organized_folder_names:
                    self.debug_info.append(f"⏭️ Skipping already-organized: {os.path.basename(file_path)}")
                    continue
                    
                # Skip files that shouldn't be organized
                filename = os.path.basename(file_path)
                if (filename.endswith((".json", ".txt", ".log", ".tmp")) or 
                    filename.startswith("tmp") or 
                    "cookie" in filename.lower() or
                    filename.startswith(".")):
                    continue
                    
                # Get the relative path from output_dir
                try:
                    rel_path = os.path.relpath(file_path, self.output_dir)
                    path_parts = rel_path.split(os.sep)
                    
                    # If file is in a subdirectory (like instagram/username/), organize within that directory
                    if len(path_parts) > 1:
                        # File is in a subdirectory - organize within that profile directory
                        profile_dir = os.path.join(self.output_dir, *path_parts[:-1])  # All parts except filename
                        if profile_dir not in files_by_profile:
                            files_by_profile[profile_dir] = []
                        files_by_profile[profile_dir].append(file_path)
                        self.debug_info.append(f"📄 Queued {filename} for organization in {os.path.relpath(profile_dir, self.output_dir)}")
                    else:
                        # File is at root level - organize in root level folders
                        if self.output_dir not in files_by_profile:
                            files_by_profile[self.output_dir] = []
                        files_by_profile[self.output_dir].append(file_path)
                        self.debug_info.append(f"📄 Queued {filename} for organization in root")
                        
                except Exception as e:
                    self.debug_info.append(f"⚠️ Error processing path {file_path}: {e}")
                    # Fallback to root level organization
                    if self.output_dir not in files_by_profile:
                        files_by_profile[self.output_dir] = []
                    files_by_profile[self.output_dir].append(file_path)
            
            if not files_by_profile:
                self.debug_info.append("📂 No valid files found for organization")
                return
                
            total_files_moved = {'images': 0, 'videos': 0, 'audio': 0, 'other': 0}
            
            # Organize files within each profile directory
            for profile_dir, files_list in files_by_profile.items():
                if not files_list:
                    continue
                    
                profile_name = os.path.relpath(profile_dir, self.output_dir) if profile_dir != self.output_dir else "root"
                self.debug_info.append(f"📂 Processing {len(files_list)} files in {profile_name}")
                
                # Create type-specific subdirectories within this profile directory
                type_dirs = {
                    'images': os.path.join(profile_dir, "images"),
                    'videos': os.path.join(profile_dir, "videos"),
                    'audio': os.path.join(profile_dir, "audio"),
                    'other': os.path.join(profile_dir, "other")
                }
                
                profile_files_moved = {'images': 0, 'videos': 0, 'audio': 0, 'other': 0}
                
                for file_path in files_list:
                    if not os.path.exists(file_path):
                        self.debug_info.append(f"⚠️ File disappeared during organization: {os.path.basename(file_path)}")
                        continue
                        
                    # Get file extension and determine category
                    ext = os.path.splitext(file_path)[1].lower()
                    filename = os.path.basename(file_path)
                    
                    # Determine target directory
                    if ext in image_extensions:
                        category = 'images'
                    elif ext in video_extensions:
                        category = 'videos'
                    elif ext in audio_extensions:
                        category = 'audio'
                    else:
                        category = 'other'
                    
                    target_dir = type_dirs[category]
                    
                    # Create target directory if it doesn't exist
                    try:
                        os.makedirs(target_dir, exist_ok=True)
                    except Exception as e:
                        self.debug_info.append(f"❌ Failed to create directory {target_dir}: {e}")
                        continue
                    
                    # Move file to appropriate subfolder
                    target_path = os.path.join(target_dir, filename)
                    
                    # Handle name conflicts
                    counter = 1
                    base_name, extension = os.path.splitext(filename)
                    while os.path.exists(target_path):
                        target_filename = f"{base_name}_{counter}{extension}"
                        target_path = os.path.join(target_dir, target_filename)
                        counter += 1
                    
                    try:
                        shutil.move(file_path, target_path)
                        profile_files_moved[category] += 1
                        total_files_moved[category] += 1
                        self.debug_info.append(f"📁 Moved {filename} to {profile_name}/{category}/ folder")
                    except Exception as e:
                        self.debug_info.append(f"❌ Failed to move {filename}: {e}")
                        continue
                
                # Log summary for this profile
                profile_total = sum(profile_files_moved.values())
                if profile_total > 0:
                    self.debug_info.append(f"📂 Organized {profile_total} files in {profile_name}:")
                    for category, count in profile_files_moved.items():
                        if count > 0:
                            self.debug_info.append(f"   📁 {category}: {count} files")
                else:
                    self.debug_info.append(f"⚠️ No files were moved in {profile_name}")
            
            # Overall summary
            total_moved = sum(total_files_moved.values())
            if total_moved > 0:
                self.debug_info.append(f"📂 Total file organization complete: {total_moved} files moved")
                for category, count in total_files_moved.items():
                    if count > 0:
                        self.debug_info.append(f"   📁 Total {category}: {count} files")
            else:
                self.debug_info.append("⚠️ No files were organized - check if files exist and are valid media files")
            
        except Exception as e:
            self.debug_info.append(f"❌ Critical error in file organization: {e}")
            import traceback
            self.debug_info.append(f"❌ Traceback: {traceback.format_exc()}")

    def run(self) -> Dict[str, Any]:
        """Execute the gallery-dl download process."""
        # Check if gallery-dl is installed
        if not self._check_gallery_dl_installed():
            raise RuntimeError(
                "gallery-dl is not installed or not accessible. "
                "Please install it using: pip install gallery-dl"
            )

        # Prepare URLs
        if self.url_file:
            if not os.path.exists(self.url_file):
                raise FileNotFoundError(f"URL file not found: {self.url_file}")
            with open(self.url_file, "r", encoding="utf-8") as f:
                urls = [line.strip() for line in f if line.strip()]
        else:
            urls = [url.strip() for url in self.url_list if url.strip()]

        if not urls:
            raise ValueError("No URLs provided for download.")

        # Create output directory and record existing files
        os.makedirs(self.output_dir, exist_ok=True)
        
        # Get list of files before download to track new files
        existing_files = set()
        # Also track filenames in organized folders to avoid re-organizing
        organized_folder_names = {'images', 'videos', 'audio', 'other'}
        if os.path.exists(self.output_dir):
            for root, dirs, files in os.walk(self.output_dir):
                for file in files:
                    if not file.endswith((".json", ".txt")):  # Skip metadata and cookie files
                        existing_files.add(os.path.join(root, file))

        # Build and execute command
        command = self._build_command(urls)

        # Execute download process with timeout handling and real-time output
        process_success = True
        process_returncode = 0
        stdout_lines = []
        stderr_lines = []
        
        # Import ComfyUI's interrupt mechanism
        try:
            from comfy.model_management import processing_interrupted
        except ImportError:
            processing_interrupted = lambda: False
        
        try:
            # Print command info for console logging
            print(f"\n{'='*60}")
            print(f"🚀 Gallery-dl Download Starting")
            print(f"📥 URLs: {len(urls)}")
            print(f"⏱️ Timeout: {self.download_timeout}s ({self.download_timeout // 60} min)")
            print(f"🛑 To cancel: Press Cancel button in ComfyUI")
            print(f"{'='*60}\n")
            
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                cwd=self.output_dir,  # Set working directory
            )
            
            # Use threading to read output without blocking
            import time
            import threading
            import queue
            
            output_queue = queue.Queue()
            
            def reader_thread(pipe, q):
                try:
                    for line in iter(pipe.readline, ''):
                        q.put(line)
                    pipe.close()
                except:
                    pass
            
            # Start reader thread
            reader = threading.Thread(target=reader_thread, args=(process.stdout, output_queue))
            reader.daemon = True
            reader.start()
            
            start_time = time.time()
            file_count = 0
            cancelled = False
            
            while True:
                # Check for ComfyUI cancel button FIRST
                if processing_interrupted():
                    process.kill()
                    process.wait()
                    cancelled = True
                    process_success = False
                    process_returncode = -2
                    stderr_lines.append("Download cancelled by user")
                    self.debug_info.append(f"🛑 Download cancelled by user after {file_count} files")
                    print(f"\n🛑 CANCELLED by user - {file_count} files downloaded")
                    print(f"💡 TIP: Run again to continue - already-downloaded files will be skipped!")
                    break
                
                # Check timeout
                elapsed = time.time() - start_time
                if elapsed > self.download_timeout:
                    process.kill()
                    process.wait()
                    process_success = False
                    process_returncode = -1
                    stderr_lines.append(f"Download process timed out after {self.download_timeout // 60} minutes")
                    self.debug_info.append(f"⏰ Download timed out after {self.download_timeout}s ({file_count} files downloaded)")
                    print(f"\n⏰ TIMEOUT after {elapsed:.0f}s - {file_count} files downloaded")
                    print(f"💡 TIP: Run again to continue - already-downloaded files will be skipped automatically!")
                    break
                
                # Check if process has finished
                if process.poll() is not None:
                    break
                
                # Read available output from queue (non-blocking)
                try:
                    while True:
                        try:
                            line = output_queue.get_nowait()
                            if line:
                                stdout_lines.append(line.rstrip())
                                # Print progress to console
                                if "# " in line or line.strip().endswith(('.jpg', '.png', '.gif', '.mp4', '.webp', '.webm')):
                                    file_count += 1
                                    # Print every 10 files or specific milestones
                                    if file_count % 10 == 0 or file_count in [1, 5, 25, 50, 100]:
                                        print(f"📥 Downloaded: {file_count} files ({elapsed:.0f}s elapsed)")
                        except queue.Empty:
                            break
                except:
                    pass
                    
                # Sleep 1 second between cancel checks to reduce CPU usage
                time.sleep(1.0)
            
            # Get any remaining output
            if not cancelled:
                try:
                    remaining_stdout, remaining_stderr = process.communicate(timeout=5)
                    if remaining_stdout:
                        stdout_lines.extend(remaining_stdout.splitlines())
                    if remaining_stderr:
                        stderr_lines.extend(remaining_stderr.splitlines())
                except:
                    pass
            
            process_returncode = process.returncode if process.returncode is not None else 0
            
            if not cancelled and process_returncode != -1:
                print(f"\n{'='*60}")
                print(f"✅ Download completed: {file_count} files in {time.time() - start_time:.0f}s")
                print(f"{'='*60}\n")
            
        except subprocess.TimeoutExpired:
            process.kill()
            process_success = False
            process_returncode = -1
            stderr_lines.append(f"Download process timed out after {self.download_timeout // 60} minutes")
            self.debug_info.append(f"⏰ Download timed out after {self.download_timeout}s, but continuing with file organization...")
        except Exception as e:
            process_success = False
            process_returncode = -1
            stderr_lines.append(f"Download process failed: {str(e)}")
            self.debug_info.append(f"❌ Download failed: {e}, but continuing with file organization...")
        
        stdout = "\n".join(stdout_lines)
        stderr = "\n".join(stderr_lines)

        # Count only newly downloaded files (files that weren't there before)
        new_downloaded_files = []
        all_current_files = set()
        if os.path.exists(self.output_dir):
            for root, dirs, files in os.walk(self.output_dir):
                # Skip scanning inside organized folders - those files are already handled
                parent_folder = os.path.basename(root)
                if parent_folder.lower() in organized_folder_names:
                    continue
                    
                for file in files:
                    # Skip metadata, config, and cookie files more comprehensively
                    if file.endswith((".json", ".txt", ".log", ".tmp")) or file.startswith("tmp") or "cookie" in file.lower():
                        continue
                    file_path = os.path.join(root, file)
                    all_current_files.add(file_path)
                    if file_path not in existing_files:
                        new_downloaded_files.append(file_path)

        self.debug_info.append(f"📊 Files before download: {len(existing_files)}")
        self.debug_info.append(f"📊 Files after download: {len(all_current_files)}")
        self.debug_info.append(f"📊 New files this run: {len(new_downloaded_files)}")

        # Always attempt file organization if enabled, even if there were errors
        organization_attempted = False
        if self.organize_files:
            self.debug_info.append("📂 Starting file organization by type...")
            organization_attempted = True
            try:
                # Only organize if we have files to organize
                if new_downloaded_files:
                    # Track original filenames to match after organization
                    original_filenames = set()
                    for file_path in new_downloaded_files:
                        original_filenames.add(os.path.basename(file_path))
                    
                    self.debug_info.append(f"📋 Files to organize: {len(new_downloaded_files)}")
                    
                    self._organize_files_by_type(new_downloaded_files)
                    
                    # Re-scan for organized files to update paths
                    organized_files = []
                    if os.path.exists(self.output_dir):
                        for root, dirs, files in os.walk(self.output_dir):
                            for file in files:
                                # Skip metadata, config, and cookie files
                                if file.endswith((".json", ".txt", ".log", ".tmp")) or file.startswith("tmp") or "cookie" in file.lower():
                                    continue
                                # Check if this file was one of the newly downloaded files by filename
                                if file in original_filenames:
                                    file_path = os.path.join(root, file)
                                    organized_files.append(file_path)
                    
                    new_downloaded_files = organized_files
                    self.debug_info.append(f"📂 Organization completed successfully. Final file count: {len(new_downloaded_files)}")
                else:
                    self.debug_info.append("📂 No files to organize")
                
            except Exception as e:
                self.debug_info.append(f"❌ File organization failed: {e}")
                import traceback
                self.debug_info.append(f"❌ Traceback: {traceback.format_exc()}")
                # Continue with unorganized files rather than failing completely

        result = {
            "command": " ".join(command),
            "stdout": stdout,
            "stderr": stderr,
            "returncode": process_returncode,
            "output_dir": self.output_dir,
            "downloaded_files": new_downloaded_files,  # Only new files
            "download_count": len(new_downloaded_files),  # Only new files
            "success": process_success and process_returncode == 0,
        }

        # Save metadata if requested
        if self.extract_metadata:
            metadata_path = Path(self.output_dir) / "gallery-dl-metadata.json"
            try:
                with open(metadata_path, "w", encoding="utf-8") as f:
                    json.dump(result, f, indent=2)
            except Exception as e:
                print(f"Warning: Could not save metadata: {e}")

        return result

    def _convert_cookie_file(self) -> str:
        """Convert exported cookie JSON to Netscape format for gallery-dl."""
        try:
            self.debug_info.append(f"🔍 Converting cookie file: {self.cookie_file}")
            
            if not os.path.exists(self.cookie_file):
                self.debug_info.append(f"❌ Cookie file not found: {self.cookie_file}")
                return None
                
            # Read the exported cookie JSON
            with open(self.cookie_file, 'r', encoding='utf-8') as f:
                cookies = json.load(f)
                
            if not isinstance(cookies, list):
                self.debug_info.append("❌ Cookie file should contain a JSON array")
                return None
                
            # Convert to Netscape format (gallery-dl's preferred format)
            netscape_file = os.path.join(self.output_dir, 'cookies.txt')
            os.makedirs(self.output_dir, exist_ok=True)
            
            with open(netscape_file, 'w', encoding='utf-8') as f:
                f.write("# Netscape HTTP Cookie File\n")
                f.write("# This file contains cookies exported for gallery-dl\n")
                
                cookie_count = 0
                for cookie in cookies:
                    try:
                        # Extract cookie fields
                        domain = cookie.get('domain', '')
                        include_subdomains = 'TRUE' if domain.startswith('.') else 'FALSE'
                        path = cookie.get('path', '/')
                        secure = 'TRUE' if cookie.get('secure', False) else 'FALSE'
                        
                        # Handle expiration
                        expiration = cookie.get('expirationDate')
                        if expiration:
                            # Convert to timestamp
                            expiration = str(int(expiration))
                        else:
                            # Set far future expiration for session cookies
                            expiration = '2147483647'  # Max 32-bit timestamp
                            
                        name = cookie.get('name', '')
                        value = cookie.get('value', '')
                        
                        if name and domain:
                            # Write in Netscape format: domain, subdomain, path, secure, expiration, name, value
                            f.write(f"{domain}\t{include_subdomains}\t{path}\t{secure}\t{expiration}\t{name}\t{value}\n")
                            cookie_count += 1
                            
                    except Exception as e:
                        self.debug_info.append(f"⚠️ Error processing cookie {cookie.get('name', 'unknown')}: {e}")
                        continue
                        
            self.debug_info.append(f"✅ Converted {cookie_count} cookies to Netscape format")
            self.debug_info.append(f"📄 Cookie file created: {netscape_file}")
            
            # Verify critical Instagram cookies are present
            instagram_cookies = [c for c in cookies if c.get('name') in ['sessionid', 'csrftoken', 'ds_user_id']]
            if instagram_cookies:
                cookie_names = [c.get('name') for c in instagram_cookies]
                self.debug_info.append(f"🔑 Found critical Instagram cookies: {', '.join(cookie_names)}")
            
            return netscape_file
            
        except json.JSONDecodeError as e:
            self.debug_info.append(f"❌ Invalid JSON in cookie file: {e}")
            return None
        except Exception as e:
            self.debug_info.append(f"❌ Error converting cookie file: {e}")
            return None

    def _test_browser_cookie_access(self):
        """Test if browser cookies can be accessed and add debug info."""
        try:
            # Try to import browser_cookie3 to check if it's available
            import browser_cookie3
            
            # Test cookie access for the specified browser
            if self.browser_name.lower() == 'firefox':
                try:
                    cookies = browser_cookie3.firefox()
                    cookie_count = len(list(cookies))
                    self.debug_info.append(f"✅ Firefox: Found {cookie_count} cookies")
                except Exception as e:
                    self.debug_info.append(f"❌ Firefox cookie access failed: {str(e)}")
                    
            elif self.browser_name.lower() in ['chrome', 'chromium']:
                try:
                    cookies = browser_cookie3.chrome()
                    cookie_count = len(list(cookies))
                    self.debug_info.append(f"✅ Chrome: Found {cookie_count} cookies")
                except Exception as e:
                    self.debug_info.append(f"❌ Chrome cookie access failed: {str(e)}")
                    
            elif self.browser_name.lower() == 'edge':
                try:
                    cookies = browser_cookie3.edge()
                    cookie_count = len(list(cookies))
                    self.debug_info.append(f"✅ Edge: Found {cookie_count} cookies")
                except Exception as e:
                    self.debug_info.append(f"❌ Edge cookie access failed: {str(e)}")
                    
            elif self.browser_name.lower() == 'safari':
                try:
                    cookies = browser_cookie3.safari()
                    cookie_count = len(list(cookies))
                    self.debug_info.append(f"✅ Safari: Found {cookie_count} cookies")
                except Exception as e:
                    self.debug_info.append(f"❌ Safari cookie access failed: {str(e)}")
                    
            else:
                self.debug_info.append(f"⚠️ Browser {self.browser_name} may not be fully supported")
                
        except ImportError:
            self.debug_info.append("❌ browser_cookie3 library not installed - install with: pip install browser-cookie3")
        except Exception as e:
            self.debug_info.append(f"❌ Browser cookie test failed: {str(e)}")


class GalleryDLNode:
    """
    ComfyUI Node for downloading images and media using gallery-dl.

    Supports downloading from various websites including:
    - Image hosting sites (imgur, flickr, etc.)
    - Social media platforms (Twitter, Instagram, etc.)
    - Art platforms (DeviantArt, ArtStation, etc.)
    - And many more supported by gallery-dl
    """

    @classmethod
    def INPUT_TYPES(cls) -> Dict[str, Any]:
        # Load saved config paths from persistent settings
        saved_config_path = get_persistent_setting("gallery_dl", "config_path", "")
        saved_cookie_file = get_persistent_setting("gallery_dl", "cookie_file", "")
        
        return {
            "required": {
                "url_list": ("STRING", {
                    "multiline": True,
                    "default": "# Enter URLs here, one per line\n# Supports 100+ sites: Instagram, Reddit, Twitter/X, DeviantArt, Pixiv, 500px, Flickr, Pinterest, Bluesky, and more\n# Examples:\n# https://www.instagram.com/username/\n# https://www.reddit.com/r/subreddit/\n# https://twitter.com/username",
                    "tooltip": "Enter URLs to download from, one per line. Supports Instagram, Reddit, Twitter/X, DeviantArt, Pixiv, 500px, Flickr, Pinterest, Bluesky, and 90+ other sites. Lines starting with # are ignored."
                }),
                "output_dir": ("STRING", {
                    "default": "./gallery-dl-output",
                    "tooltip": "Directory where downloaded files will be saved. Relative paths are relative to ComfyUI's output folder. Files are organized into subfolders by site and user."
                })
            },
            "optional": {
                "url_file": ("STRING", {
                    "default": "",
                    "tooltip": "Optional: Path to a text file containing URLs (one per line). Useful for batch downloading from a prepared list. Leave empty to use url_list above."
                }),
                "config_path": ("STRING", {
                    "default": saved_config_path,
                    "tooltip": "Path to gallery-dl.conf config file. This single file contains credentials for ALL sites (Instagram, Reddit, 500px, etc.) - gallery-dl auto-selects the right ones based on URL. Path is auto-saved for next time. Recommended: ./configs/gallery-dl.conf"
                }),
                "cookie_file": ("STRING", {
                    "default": saved_cookie_file,
                    "tooltip": "Path to exported cookie file (Netscape/JSON format). Only used when 'Use Browser Cookies' is OFF and you need site-specific cookies not in config. Usually leave empty - config file credentials work better. Path is auto-saved."
                }),
                "use_browser_cookies": ("BOOLEAN", {
                    "default": False,
                    "label_on": "Browser Cookies",
                    "label_off": "Config/Cookie File",
                    "tooltip": "OFF (recommended): Use credentials from config file - most reliable. ON: Extract cookies directly from browser (Firefox works best; Chrome/Edge require admin rights and browser closed)."
                }),
                "browser_name": (["firefox", "chrome", "chromium", "edge", "safari", "opera"], {
                    "default": "firefox",
                    "tooltip": "Browser to extract cookies from when 'Use Browser Cookies' is ON. Firefox recommended - works without admin rights. Chrome/Edge need admin + browser closed."
                }),
                "use_download_archive": ("BOOLEAN", {
                    "default": True,
                    "label_on": "Skip Downloaded",
                    "label_off": "Re-download All",
                    "tooltip": "ON (recommended): Track downloaded files in SQLite database to skip duplicates on future runs. OFF: Re-download everything, may create duplicates."
                }),
                "archive_file": ("STRING", {
                    "default": "./gallery-dl-archive.sqlite3",
                    "tooltip": "Path to download archive database (SQLite). Tracks what's been downloaded to avoid duplicates. Delete this file to force re-downloading everything."
                }),
                "skip_videos": ("BOOLEAN", {
                    "default": False,
                    "label_on": "Images Only",
                    "label_off": "Images + Videos",
                    "tooltip": "ON: Download only images, skip all video files. OFF: Download both images and videos. Useful when you only want still images from a mixed gallery."
                }),
                "filter_by_resolution": ("BOOLEAN", {
                    "default": True,
                    "label_on": "Filter Small Images",
                    "label_off": "Keep All Sizes",
                    "tooltip": "ON: Skip images smaller than min_image_width/height (removes thumbnails, icons, low-res images). Videos are never filtered. Sites without dimension metadata (Bunkr, Cyberdrop) will download all images. OFF: Download all images regardless of size."
                }),
                "min_image_width": ("INT", {
                    "default": 768,
                    "min": 0,
                    "max": 8192,
                    "step": 64,
                    "tooltip": "Minimum image width in pixels when filter_by_resolution is ON. Images narrower than this are skipped. Set to 0 to disable width filtering. Note: Sites that don't provide dimension metadata will download all images."
                }),
                "min_image_height": ("INT", {
                    "default": 768,
                    "min": 0,
                    "max": 8192,
                    "step": 64,
                    "tooltip": "Minimum image height in pixels when filter_by_resolution is ON. Images shorter than this are skipped. Set to 0 to disable height filtering. Note: Sites that don't provide dimension metadata will download all images."
                }),
                "extract_metadata": ("BOOLEAN", {
                    "default": True,
                    "label_on": "Save Metadata",
                    "label_off": "No Metadata",
                    "tooltip": "ON: Save download metadata to JSON file (URLs, timestamps, file counts, errors). Useful for tracking what was downloaded. OFF: No metadata file created."
                }),
                "organize_files": ("BOOLEAN", {
                    "default": True,
                    "label_on": "Sort by Type",
                    "label_off": "All in One Folder",
                    "tooltip": "ON: Sort downloaded files into subfolders by type (images/, videos/, audio/, other/). OFF: Put all files in the main output folder without sorting."
                }),
                "instagram_include": (["posts", "stories", "highlights", "reels", "tagged", "info", "avatar", "all", "posts,stories", "posts,reels", "stories,highlights"], {
                    "default": "posts",
                    "tooltip": "Instagram only: What content to download. 'posts' = feed posts, 'stories' = current stories (24hr), 'highlights' = saved story highlights, 'reels' = reels videos, 'all' = everything. Combine with comma: 'posts,reels'."
                }),
                "download_timeout": ("INT", {
                    "default": 1800,
                    "min": 60,
                    "max": 36000,
                    "step": 60,
                    "tooltip": "Maximum time in seconds for this run. Default 1800s (30 min). For huge galleries: 7200=2hr, 14400=4hr, 28800=8hr. TIP: If it times out, just run again - gallery-dl automatically resumes from where it left off using the download archive!"
                }),
                "extra_options": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "Advanced gallery-dl options (one per line or space-separated):\n• --limit N: Max N files to download\n• --range 1-50: Download items 1-50 only\n• --no-download: Simulate without downloading\n• --write-metadata: Save per-file JSON metadata\n• --ugoira-conv: Convert Pixiv ugoira to video\n• -v: Verbose output for debugging\n• --sleep N: Wait N seconds between requests\n• --retries N: Retry failed downloads N times\n\nFolder organization examples:\n• Kemono by post: -o directory=[\"{service}\",\"{user}\",\"{id}_{title}\"]\n• Flat by user: -o directory=[\"{category}\",\"{user}\"]\n\nSee docs: https://github.com/mikf/gallery-dl/blob/master/docs/options.md"
                }),
                "seed": ("INT", {
                    "default": 0,
                    "min": 0,
                    "max": 0xffffffffffffffff,
                    "tooltip": "Random seed to force re-execution. Click 🎲 to randomize or change manually. Useful for resuming downloads after timeout - change the seed to run again without modifying other settings."
                })
            }
        }

    RETURN_TYPES = ("STRING", "STRING", "INT", "BOOLEAN")
    RETURN_NAMES = ("output_dir", "summary", "download_count", "success")
    FUNCTION = "execute"
    CATEGORY = "Downloaders"

    DESCRIPTION = "Download images and media from 100+ websites using gallery-dl. Supports Instagram, Reddit, Twitter/X, DeviantArt, Pixiv, 500px, Flickr, Pinterest, Bluesky, and more. Features: resolution filtering, duplicate detection, automatic file organization, and persistent config paths."

    def execute(
        self,
        url_list: str,
        output_dir: str,
        url_file: str = None,
        config_path: str = None,
        cookie_file: str = None,
        use_browser_cookies: bool = False,
        browser_name: str = "firefox",
        use_download_archive: bool = True,
        archive_file: str = "./gallery-dl-archive.sqlite3",
        skip_videos: bool = False,
        filter_by_resolution: bool = True,
        min_image_width: int = 768,
        min_image_height: int = 768,
        extract_metadata: bool = True,
        organize_files: bool = True,
        # New advanced options
        instagram_include: str = "posts",
        download_timeout: int = 1800,
        extra_options: str = "",
        seed: int = 0,
    ) -> Tuple[str, str, int, bool]:
        """
        Execute the gallery-dl download process.

        Returns:
            tuple: (output_dir, summary, download_count, success)
        """
        try:
            # Save original config values for persistence before cleaning
            original_config_path = config_path.strip() if config_path else ""
            original_cookie_file = cookie_file.strip() if cookie_file else ""
            
            # Clean up input parameters  
            if url_file and url_file.strip() == "":
                url_file = None
            if config_path and config_path.strip() == "":
                config_path = None
            if cookie_file and cookie_file.strip() == "":
                cookie_file = None
            if archive_file and archive_file.strip() == "":
                archive_file = "./gallery-dl-archive.sqlite3"
            
            # Save config_path and cookie_file for future use if they were provided
            if original_config_path:
                set_persistent_setting("gallery_dl", "config_path", original_config_path)
                print(f"Saved config_path for future use: {original_config_path}")
            if original_cookie_file:
                set_persistent_setting("gallery_dl", "cookie_file", original_cookie_file)
                print(f"Saved cookie_file for future use: {original_cookie_file}")

            # Sanitize output directory
            base_output_dir = os.path.abspath(folder_paths.get_output_directory())
            
            if not output_dir or output_dir.strip() == "":
                output_dir = base_output_dir
            else:
                # Handle relative paths - make relative to ComfyUI output directory
                if not os.path.isabs(output_dir):
                    output_dir = os.path.join(base_output_dir, output_dir)
                
                # Normalize path to resolve .. and .
                output_dir = os.path.normpath(output_dir)
                output_dir = os.path.abspath(output_dir)
                
                # Security check: Ensure path is within base_output_dir
                try:
                    if os.path.commonpath([base_output_dir, output_dir]) != base_output_dir:
                        print(f"Warning: Path '{output_dir}' is outside the allowed output directory. Reverting to default.")
                        output_dir = base_output_dir
                except ValueError:
                    # Can happen on Windows if paths are on different drives
                    print(f"Warning: Path '{output_dir}' is on a different drive. Reverting to default.")
                    output_dir = base_output_dir

            if archive_file:
                archive_file = os.path.abspath(archive_file)
            if config_path:
                # Handle relative paths relative to PDF_tools directory
                if not os.path.isabs(config_path):
                    pdf_tools_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                    config_path = os.path.join(pdf_tools_dir, config_path)
                config_path = os.path.abspath(config_path)
            if cookie_file:
                # Handle relative paths relative to PDF_tools directory (same as config_path)
                if not os.path.isabs(cookie_file):
                    pdf_tools_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                    cookie_file = os.path.join(pdf_tools_dir, cookie_file)
                cookie_file = os.path.abspath(cookie_file)
            if url_file:
                url_file = os.path.abspath(url_file)

            # Create downloader instance
            downloader = GalleryDLDownloader(
                url_list=url_list.splitlines() if url_list.strip() else [],
                url_file=url_file,
                output_dir=output_dir,
                config_path=config_path,
                cookie_file=cookie_file,
                use_browser_cookies=use_browser_cookies,
                browser_name=browser_name,
                use_download_archive=use_download_archive,
                archive_file=archive_file,
                skip_videos=skip_videos,
                filter_by_resolution=filter_by_resolution,
                min_image_width=min_image_width,
                min_image_height=min_image_height,
                extract_metadata=extract_metadata,
                organize_files=organize_files,
                instagram_include=instagram_include,
                download_timeout=download_timeout,
                extra_options=extra_options,
            )

            # Execute download
            result = downloader.run()
            
            # Compile debug information
            debug_section = ""
            if downloader.debug_info:
                debug_section = "\n\n🔧 Debug Information:\n" + "\n".join(downloader.debug_info)

            # Create summary
            if result["success"]:
                summary = (
                    f"✅ Download completed successfully\n"
                    f"📁 Output directory: {result['output_dir']}\n"
                    f"📊 Files downloaded: {result['download_count']}\n"
                    f"💾 Command used: {result['command'][:100]}{'...' if len(result['command']) > 100 else ''}"
                )
                if result["stderr"]:
                    summary += f"\n⚠️ Warnings: {result['stderr'][:200]}{'...' if len(result['stderr']) > 200 else ''}"
                summary += debug_section
            else:
                summary = (
                    f"❌ Download failed (exit code: {result['returncode']})\n"
                    f"📁 Output directory: {result['output_dir']}\n"
                    f"📊 Files downloaded: {result['download_count']}\n"
                    f"🔍 Error: {result['stderr'][:300]}{'...' if len(result['stderr']) > 300 else ''}"
                )
                summary += debug_section

            return (
                result["output_dir"],
                summary,
                result["download_count"],
                result["success"],
            )

        except Exception as e:
            error_summary = f"❌ Error: {str(e)}"
            return (
                output_dir if "output_dir" in locals() else "./gallery-dl-output",
                error_summary,
                0,
                False,
            )


# Additional utility functions for the node
def check_gallery_dl_installation():
    """Helper function to check if gallery-dl is properly installed."""
    try:
        result = subprocess.run(
            ["gallery-dl", "--version"], capture_output=True, text=True, timeout=5
        )
        return result.returncode == 0, result.stdout if result.returncode == 0 else result.stderr
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False, "gallery-dl not found in PATH"


# Node mappings for ComfyUI registration
NODE_CLASS_MAPPINGS = {
    "GalleryDLDownloader": GalleryDLNode,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "GalleryDLDownloader": "Social Media Downloader (gallery-dl)",
}

# Export for ComfyUI
__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "GalleryDLNode", "GalleryDLDownloader"]
