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

from pathlib import Path
from typing import Any, Dict, List, Tuple


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

        # Use config file if provided
        if self.config_path:
            command += ["--config", self.config_path]
            self.debug_info.append(f"📄 Using config file: {self.config_path}")

        # Detect target sites for better authentication handling
        target_sites = set()
        for url in urls:
            if 'instagram.com' in url:
                target_sites.add('instagram')
            elif 'reddit.com' in url:
                target_sites.add('reddit')
            elif 'twitter.com' in url or 'x.com' in url:
                target_sites.add('twitter')
            # Add more site detection as needed
        
        if target_sites:
            self.debug_info.append(f"🎯 Detected target sites: {', '.join(target_sites)}")
            
        # Check for known problematic sites
        if 'reddit' in target_sites:
            self.debug_info.append("⚠️ WARNING: Reddit may hang or require updated API credentials")
            self.debug_info.append("   Consider testing with Instagram or other sites first")

        # Handle cookie file (takes precedence over browser cookies)
        if self.cookie_file:
            # Warn if using cookies for non-matching sites (but allow Instagram + config combo)
            if target_sites and 'instagram' not in target_sites:
                self.debug_info.append(f"⚠️ Warning: Using Instagram cookies for {', '.join(target_sites)} - this may cause authentication conflicts")
            elif target_sites and 'instagram' in target_sites:
                self.debug_info.append("🔗 Using Instagram cookies - optimal setup!")
            
            converted_cookie_file = self._convert_cookie_file()
            if converted_cookie_file:
                command += ["--cookies", converted_cookie_file]
                self.debug_info.append(f"🍪 Using cookie file: {converted_cookie_file}")
        elif self.use_browser_cookies:
            command += ["--cookies-from-browser", self.browser_name]
            self.debug_info.append(f"🍪 Extracting cookies from {self.browser_name} browser")
            # Test if browser cookies can be accessed
            self._test_browser_cookie_access()

        if self.use_download_archive:
            command += ["--download-archive", self.archive_file]
            self.debug_info.append(f"📦 Using download archive: {self.archive_file}")

        if self.skip_videos:
            command += [
                "--filter",
                "extension not in ('mp4', 'webm', 'mkv', 'avi', 'mov', 'wmv', 'flv', 'm4v')",
            ]
            self.debug_info.append("🎬 Video files will be skipped")

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
        """Sort downloaded files into subfolders by type (images, videos, etc.) within each profile directory"""
        if not downloaded_files:
            self.debug_info.append("📂 No files to organize")
            return
            
        try:
            # Define file type categories
            image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.tiff', '.svg', '.heic', '.avif'}
            video_extensions = {'.mp4', '.webm', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.m4v', '.3gp', '.ogv', '.mpg', '.mpeg'}
            audio_extensions = {'.mp3', '.wav', '.flac', '.aac', '.ogg', '.m4a', '.wma', '.opus'}
            
            # Group files by their parent directory (profile/site directories)
            files_by_profile = {}
            
            for file_path in downloaded_files:
                if not os.path.exists(file_path):
                    self.debug_info.append(f"⚠️ File no longer exists: {os.path.basename(file_path)}")
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
        if os.path.exists(self.output_dir):
            for root, dirs, files in os.walk(self.output_dir):
                for file in files:
                    if not file.endswith((".json", ".txt")):  # Skip metadata and cookie files
                        existing_files.add(os.path.join(root, file))

        # Build and execute command
        command = self._build_command(urls)

        # Execute download process with timeout handling
        process_success = True
        process_returncode = 0
        stdout = ""
        stderr = ""
        
        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                cwd=self.output_dir,  # Set working directory
            )
            stdout, stderr = process.communicate(timeout=300)  # 5 minute timeout
            process_returncode = process.returncode
        except subprocess.TimeoutExpired:
            process.kill()
            process_success = False
            process_returncode = -1
            stderr = "Download process timed out after 5 minutes"
            stdout = ""
            self.debug_info.append("⏰ Download timed out, but continuing with file organization...")
        except Exception as e:
            process_success = False
            process_returncode = -1
            stderr = f"Download process failed: {str(e)}"
            stdout = ""
            self.debug_info.append(f"❌ Download failed: {e}, but continuing with file organization...")

        # Count only newly downloaded files (files that weren't there before)
        new_downloaded_files = []
        all_current_files = set()
        if os.path.exists(self.output_dir):
            for root, dirs, files in os.walk(self.output_dir):
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
        return {
            "required": {
                "url_list": ("STRING", {
                    "multiline": True,
                    "default": "# Enter URLs here, one per line\n# Example:\n# https://imgur.com/gallery/example\n# https://example.com/image.jpg"
                }),
                "output_dir": ("STRING", {
                    "default": "./gallery-dl-output",
                    "tooltip": "Directory where downloaded files will be saved"
                })
            },
            "optional": {
                "url_file": ("STRING", {
                    "default": "",
                    "tooltip": "Path to a text file containing URLs (one per line)"
                }),
                "config_path": ("STRING", {
                    "default": "",
                    "tooltip": "Path to gallery-dl config file. For Instagram: LEAVE EMPTY (not needed). For Reddit: use './configs/gallery-dl-no-reddit.conf' to disable Reddit or './configs/gallery-dl.conf' with your API credentials."
                }),
                "cookie_file": ("STRING", {
                    "default": "",
                    "tooltip": "Path to exported cookie JSON file. For Instagram: use './configs/instagram_cookies.json'. For Reddit: LEAVE EMPTY (use browser cookies instead)."
                }),
                "use_browser_cookies": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "Use browser cookies for authentication (ignored if cookie file is provided)"
                }),
                "browser_name": (["firefox", "chrome", "chromium", "edge", "safari", "opera"], {
                    "default": "firefox",
                    "tooltip": "Browser to extract cookies from (Firefox works without admin, Chrome/Edge require admin)"
                }),
                "use_download_archive": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "Use archive file to skip already downloaded content"
                }),
                "archive_file": ("STRING", {
                    "default": "./gallery-dl-archive.sqlite3",
                    "tooltip": "Path to the download archive database"
                }),
                "skip_videos": ("BOOLEAN", {
                    "default": False,
                    "tooltip": "Skip video files, download only images"
                }),
                "extract_metadata": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "Save download metadata to JSON file"
                }),
                "organize_files": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "Sort downloaded files into subfolders (images/, videos/, audio/, other/)"
                }),
                "instagram_include": (["posts", "stories", "highlights", "reels", "tagged", "info", "avatar", "all", "posts,stories", "posts,reels", "stories,highlights"], {
                    "default": "posts",
                    "tooltip": "For Instagram profiles: What to include (posts, stories, highlights, reels, tagged, info, avatar, or all)"
                }),
                "extra_options": ("STRING", {
                    "default": "",
                    "tooltip": "Additional options for gallery-dl (e.g., '--no-skip-download')"
                })
            }
        }

    RETURN_TYPES = ("STRING", "STRING", "INT", "BOOLEAN")
    RETURN_NAMES = ("output_dir", "summary", "download_count", "success")
    FUNCTION = "execute"
    CATEGORY = "Downloaders"

    DESCRIPTION = "Download images and media from various websites using gallery-dl"

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
        extract_metadata: bool = True,
        organize_files: bool = True,
        # New advanced options
        instagram_include: str = "posts",
        extra_options: str = "",
    ) -> Tuple[str, str, int, bool]:
        """
        Execute the gallery-dl download process.

        Returns:
            tuple: (output_dir, summary, download_count, success)
        """
        try:
            # Clean up input parameters  
            if url_file and url_file.strip() == "":
                url_file = None
            if config_path and config_path.strip() == "":
                config_path = None
            if cookie_file and cookie_file.strip() == "":
                cookie_file = None
            if archive_file and archive_file.strip() == "":
                archive_file = "./gallery-dl-archive.sqlite3"

            # Convert relative paths to absolute paths
            output_dir = os.path.abspath(output_dir)
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
                extract_metadata=extract_metadata,
                organize_files=organize_files,
                instagram_include=instagram_include,
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
    "GalleryDLDownloader": "Gallery-dl Downloader",
}

# Export for ComfyUI
__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "GalleryDLNode", "GalleryDLDownloader"]
