"""
Yt Dlp Downloader

Description: Yt-dlp downloader node for ComfyUI - downloads videos and audio from 1000+ platforms including YouTube, TikTok, etc.
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
- Uses yt-dlp (Unlicense/Public Domain): https://github.com/yt-dlp/yt-dlp
- See CREDITS.md for complete list of all dependencies
"""

"""
Yt-dlp Downloader Node for ComfyUI
Downloads audio and video from various websites using yt-dlp

Features:
- Download from URLs or batch files
- Browser cookie support
- Download archive to avoid duplicates
- Format selection (video quality, audio-only, etc.)
- Post-processing options (audio extraction, format conversion)
- Subtitle downloads
- Configurable output directory
- File organization by type

Author: Eric Hiss
Version: 1.0.0
Date: January 2025
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


class YtDlpDownloader:
    def __init__(
        self,
        url_list: List[str] = None,
        batch_file: str = None,
        output_dir: str = "./yt-dlp-output",
        config_path: str = None,
        cookie_file: str = None,
        use_browser_cookies: bool = False,
        browser_name: str = "firefox",
        use_download_archive: bool = True,
        archive_file: str = "./yt-dlp-archive.txt",
        format_selector: str = "best",
        extract_audio: bool = False,
        audio_format: str = "mp3",
        audio_quality: str = "192",
        download_subtitles: bool = False,
        subtitle_langs: str = "en",
        embed_subtitles: bool = False,
        write_info_json: bool = True,
        organize_files: bool = True,
        # Advanced options
        extra_options: str = "",
        rate_limit: str = "",
        concurrent_fragments: str = "1",
        playlist_start: str = "",
        playlist_end: str = "",
    ):
        self.url_list = url_list or []
        self.batch_file = batch_file
        self.output_dir = output_dir
        self.config_path = config_path
        self.cookie_file = cookie_file
        self.use_browser_cookies = use_browser_cookies
        self.browser_name = browser_name
        self.use_download_archive = use_download_archive
        self.archive_file = archive_file
        self.format_selector = format_selector
        self.extract_audio = extract_audio
        self.audio_format = audio_format
        self.audio_quality = audio_quality
        self.download_subtitles = download_subtitles
        self.subtitle_langs = subtitle_langs
        self.embed_subtitles = embed_subtitles
        self.write_info_json = write_info_json
        self.organize_files = organize_files
        self.extra_options = extra_options
        self.rate_limit = rate_limit
        self.concurrent_fragments = concurrent_fragments
        self.playlist_start = playlist_start
        self.playlist_end = playlist_end
        
        # Initialize debug info
        self.debug_info = []  # Store debug information for status reporting

    def _check_yt_dlp_installed(self) -> bool:
        """Check if yt-dlp is installed and accessible."""
        try:
            result = subprocess.run(
                ["yt-dlp", "--version"], capture_output=True, text=True, timeout=10
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def _check_ffmpeg_installed(self) -> bool:
        """Check if ffmpeg is installed (needed for audio extraction and format conversion)."""
        try:
            result = subprocess.run(
                ["ffmpeg", "-version"], capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                self.debug_info.append("✅ FFmpeg is available for audio extraction and merging")
                return True
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        
        self.debug_info.append("⚠️ FFmpeg not found - audio extraction and format merging may not work")
        return False

    def _build_command(self, urls: List[str]) -> List[str]:
        command = ["yt-dlp"]

        # Output directory
        command += ["-o", f"{self.output_dir}/%(uploader)s/%(title)s.%(ext)s"]
        self.debug_info.append(f"📁 Output directory: {self.output_dir}")

        # Detect target sites for better configuration
        target_sites = set()
        for url in urls:
            if 'youtube.com' in url or 'youtu.be' in url:
                target_sites.add('youtube')
            elif 'twitter.com' in url or 'x.com' in url:
                target_sites.add('twitter')
            elif 'tiktok.com' in url:
                target_sites.add('tiktok')
            elif 'instagram.com' in url:
                target_sites.add('instagram')
            elif 'twitch.tv' in url:
                target_sites.add('twitch')
            # Add more site detection as needed
        
        if target_sites:
            self.debug_info.append(f"🎯 Detected target sites: {', '.join(target_sites)}")

        # Use config file if provided
        if self.config_path:
            command += ["--config-location", self.config_path]
            self.debug_info.append(f"📄 Using config file: {self.config_path}")

        # Handle cookie file (takes precedence over browser cookies)
        if self.cookie_file:
            command += ["--cookies", self.cookie_file]
            self.debug_info.append(f"🍪 Using cookie file: {self.cookie_file}")
        elif self.use_browser_cookies:
            command += ["--cookies-from-browser", self.browser_name]
            self.debug_info.append(f"🍪 Extracting cookies from {self.browser_name} browser")
            self._test_browser_cookie_access()

        # Download archive
        if self.use_download_archive:
            command += ["--download-archive", self.archive_file]
            self.debug_info.append(f"📦 Using download archive: {self.archive_file}")

        # Format selection
        if self.format_selector and self.format_selector != "best":
            command += ["-f", self.format_selector]
            self.debug_info.append(f"🎬 Format selector: {self.format_selector}")

        # Audio extraction
        if self.extract_audio:
            command += ["-x", "--audio-format", self.audio_format]
            if self.audio_quality:
                command += ["--audio-quality", self.audio_quality]
            self.debug_info.append(f"🎵 Extracting audio: {self.audio_format} quality {self.audio_quality}")

        # Subtitle options
        if self.download_subtitles:
            command += ["--write-subs"]
            if self.subtitle_langs:
                command += ["--sub-langs", self.subtitle_langs]
            self.debug_info.append(f"📝 Downloading subtitles: {self.subtitle_langs}")
            
            if self.embed_subtitles:
                command += ["--embed-subs"]
                self.debug_info.append("📝 Embedding subtitles in video files")

        # Metadata
        if self.write_info_json:
            command += ["--write-info-json"]
            self.debug_info.append("📄 Writing metadata JSON files")

        # Rate limiting
        if self.rate_limit:
            command += ["--limit-rate", self.rate_limit]
            self.debug_info.append(f"⚡ Rate limit: {self.rate_limit}")

        # Concurrent fragments
        if self.concurrent_fragments and self.concurrent_fragments != "1":
            command += ["--concurrent-fragments", self.concurrent_fragments]
            self.debug_info.append(f"⚡ Concurrent fragments: {self.concurrent_fragments}")

        # Playlist options
        if self.playlist_start:
            command += ["--playlist-start", self.playlist_start]
            self.debug_info.append(f"📋 Playlist start: {self.playlist_start}")
        
        if self.playlist_end:
            command += ["--playlist-end", self.playlist_end]
            self.debug_info.append(f"📋 Playlist end: {self.playlist_end}")

        # Add some standard options for better experience
        command += ["--no-warnings"]  # Reduce noise
        command += ["--ignore-errors"]  # Continue on errors
        command += ["--retries", "3"]  # Retry failed downloads
        
        self.debug_info.append("🔧 Added standard options: no-warnings, ignore-errors, 3 retries")

        # Parse any extra options from the extra_options field
        if self.extra_options:
            extra_args = self._parse_extra_options(self.extra_options)
            if extra_args:
                command.extend(extra_args)
                self.debug_info.append(f"➕ Added extra options: {' '.join(extra_args)}")

        # Add URLs or batch file
        if self.batch_file:
            command += ["--batch-file", self.batch_file]
        else:
            command += urls

        return command

    def _parse_extra_options(self, extra_options: str) -> List[str]:
        """Parse extra command-line options for yt-dlp."""
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

    def _test_browser_cookie_access(self) -> None:
        """Test if browser cookies can be accessed."""
        try:
            import browser_cookie3
            
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

    def _organize_files_by_type(self, downloaded_files: List[str]) -> None:
        """Sort downloaded files into subfolders by type (videos, audio, etc.) within each profile directory"""
        if not downloaded_files:
            self.debug_info.append("📂 No files to organize")
            return
            
        try:
            # Define file type categories
            video_extensions = {'.mp4', '.webm', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.m4v', '.3gp', '.ogv', '.mpg', '.mpeg', '.ts', '.m2ts'}
            audio_extensions = {'.mp3', '.wav', '.flac', '.aac', '.ogg', '.m4a', '.wma', '.opus', '.webm'}  # webm can be audio-only
            subtitle_extensions = {'.srt', '.vtt', '.ass', '.ssa', '.sub', '.idx', '.smi', '.rt', '.sbv'}
            
            # Group files by their parent directory (profile/channel directories)
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
                    
                    # If file is in a subdirectory (like youtube/channelname/), organize within that directory
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
                
            total_files_moved = {'videos': 0, 'audio': 0, 'subtitles': 0, 'other': 0}
            
            # Organize files within each profile directory
            for profile_dir, files_list in files_by_profile.items():
                if not files_list:
                    continue
                    
                profile_name = os.path.relpath(profile_dir, self.output_dir) if profile_dir != self.output_dir else "root"
                self.debug_info.append(f"📂 Processing {len(files_list)} files in {profile_name}")
                
                # Create type-specific subdirectories within this profile directory
                type_dirs = {
                    'videos': os.path.join(profile_dir, "videos"),
                    'audio': os.path.join(profile_dir, "audio"), 
                    'subtitles': os.path.join(profile_dir, "subtitles"),
                    'other': os.path.join(profile_dir, "other")
                }
                
                profile_files_moved = {'videos': 0, 'audio': 0, 'subtitles': 0, 'other': 0}
                
                for file_path in files_list:
                    if not os.path.exists(file_path):
                        self.debug_info.append(f"⚠️ File disappeared during organization: {os.path.basename(file_path)}")
                        continue
                        
                    # Get file extension and determine category
                    ext = os.path.splitext(file_path)[1].lower()
                    filename = os.path.basename(file_path)
                    
                    # Special handling for webm files - check if they're audio-only
                    if ext == '.webm':
                        # Try to determine if it's audio-only by checking with ffprobe if available
                        try:
                            result = subprocess.run(
                                ["ffprobe", "-v", "quiet", "-show_streams", "-select_streams", "v", file_path],
                                capture_output=True, text=True, timeout=5
                            )
                            if result.returncode == 0 and result.stdout.strip():
                                # Has video stream
                                category = 'videos'
                            else:
                                # No video stream, likely audio-only
                                category = 'audio'
                        except (subprocess.TimeoutExpired, FileNotFoundError):
                            # Can't determine, default based on extract_audio setting
                            category = 'audio' if self.extract_audio else 'videos'
                    else:
                        # Determine target directory
                        if ext in video_extensions:
                            category = 'videos'
                        elif ext in audio_extensions:
                            category = 'audio'
                        elif ext in subtitle_extensions:
                            category = 'subtitles'
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
        """Execute the yt-dlp download process."""
        # Check if yt-dlp is installed
        if not self._check_yt_dlp_installed():
            raise RuntimeError(
                "yt-dlp is not installed or not accessible. "
                "Please install it using: pip install yt-dlp"
            )

        # Check ffmpeg if audio extraction is enabled
        if self.extract_audio or self.embed_subtitles:
            self._check_ffmpeg_installed()

        # Prepare URLs
        if self.batch_file:
            if not os.path.exists(self.batch_file):
                raise FileNotFoundError(f"Batch file not found: {self.batch_file}")
            with open(self.batch_file, "r", encoding="utf-8") as f:
                urls = [line.strip() for line in f if line.strip() and not line.strip().startswith('#')]
        else:
            urls = [url.strip() for url in self.url_list if url.strip() and not url.strip().startswith('#')]

        if not urls:
            raise ValueError("No URLs provided for download.")

        # Create output directory and record existing files
        os.makedirs(self.output_dir, exist_ok=True)
        
        # Get list of files before download to track new files
        existing_files = set()
        if os.path.exists(self.output_dir):
            for root, dirs, files in os.walk(self.output_dir):
                for file in files:
                    if not file.endswith((".json", ".txt")):  # Skip metadata files
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
            stdout, stderr = process.communicate(timeout=600)  # 10 minute timeout
            process_returncode = process.returncode
        except subprocess.TimeoutExpired:
            process.kill()
            process_success = False
            process_returncode = -1
            stderr = "Download process timed out after 10 minutes"
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

        return result


class YtDlpNode:
    """
    ComfyUI Node for downloading audio and video using yt-dlp.

    Supports downloading from hundreds of websites including:
    - YouTube, YouTube Music
    - TikTok, Instagram, Twitter/X
    - Twitch, Vimeo, Dailymotion
    - SoundCloud, Bandcamp
    - And many more supported by yt-dlp
    """

    @classmethod
    def INPUT_TYPES(cls) -> Dict[str, Any]:
        return {
            "required": {
                "url_list": ("STRING", {
                    "multiline": True,
                    "default": "# Enter URLs here, one per line\n# Example:\n# https://www.youtube.com/watch?v=example\n# https://soundcloud.com/user/track"
                }),
                "output_dir": ("STRING", {
                    "default": "./yt-dlp-output",
                    "tooltip": "Directory where downloaded files will be saved"
                })
            },
            "optional": {
                "batch_file": ("STRING", {
                    "default": "",
                    "tooltip": "Path to a text file containing URLs (one per line)"
                }),
                "config_path": ("STRING", {
                    "default": "",
                    "tooltip": "Path to yt-dlp config file"
                }),
                "cookie_file": ("STRING", {
                    "default": "",
                    "tooltip": "Path to Netscape cookies file (for authenticated downloads)"
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
                    "default": "./yt-dlp-archive.txt",
                    "tooltip": "Path to the download archive file"
                }),
                "format_selector": (["best", "worst", "best[height<=720]", "best[height<=480]", "bestvideo+bestaudio", "bestvideo", "bestaudio", "mp4", "webm"], {
                    "default": "best",
                    "tooltip": "Video format to download. 'best' gets highest quality, 'bestaudio' gets audio only"
                }),
                "extract_audio": ("BOOLEAN", {
                    "default": False,
                    "tooltip": "Extract audio from videos (requires ffmpeg)"
                }),
                "audio_format": (["mp3", "aac", "flac", "m4a", "opus", "vorbis", "wav"], {
                    "default": "mp3",
                    "tooltip": "Audio format when extracting audio"
                }),
                "audio_quality": (["32", "64", "128", "192", "256", "320"], {
                    "default": "192",
                    "tooltip": "Audio quality in kbps (for lossy formats)"
                }),
                "download_subtitles": ("BOOLEAN", {
                    "default": False,
                    "tooltip": "Download subtitle files"
                }),
                "subtitle_langs": ("STRING", {
                    "default": "en",
                    "tooltip": "Subtitle languages to download (comma-separated, e.g., 'en,es,fr' or 'all')"
                }),
                "embed_subtitles": ("BOOLEAN", {
                    "default": False,
                    "tooltip": "Embed subtitles in video files (requires ffmpeg)"
                }),
                "write_info_json": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "Save video metadata to JSON files"
                }),
                "organize_files": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "Sort downloaded files into subfolders (videos/, audio/, subtitles/, other/)"
                }),
                "rate_limit": ("STRING", {
                    "default": "",
                    "tooltip": "Maximum download rate (e.g., '1M' for 1MB/s, '500K' for 500KB/s)"
                }),
                "concurrent_fragments": (["1", "2", "4", "8"], {
                    "default": "1",
                    "tooltip": "Number of fragments to download concurrently"
                }),
                "playlist_start": ("STRING", {
                    "default": "",
                    "tooltip": "Playlist start index (leave empty for all)"
                }),
                "playlist_end": ("STRING", {
                    "default": "",
                    "tooltip": "Playlist end index (leave empty for all)"
                }),
                "extra_options": ("STRING", {
                    "default": "",
                    "tooltip": "Additional options for yt-dlp (e.g., '--write-thumbnail --embed-metadata')"
                })
            }
        }

    RETURN_TYPES = ("STRING", "STRING", "INT", "BOOLEAN")
    RETURN_NAMES = ("output_dir", "summary", "download_count", "success")
    FUNCTION = "execute"
    CATEGORY = "Downloaders"

    DESCRIPTION = "Download audio and video from hundreds of websites using yt-dlp"

    def execute(
        self,
        url_list: str,
        output_dir: str,
        batch_file: str = None,
        config_path: str = None,
        cookie_file: str = None,
        use_browser_cookies: bool = False,
        browser_name: str = "firefox",
        use_download_archive: bool = True,
        archive_file: str = "./yt-dlp-archive.txt",
        format_selector: str = "best",
        extract_audio: bool = False,
        audio_format: str = "mp3",
        audio_quality: str = "192",
        download_subtitles: bool = False,
        subtitle_langs: str = "en",
        embed_subtitles: bool = False,
        write_info_json: bool = True,
        organize_files: bool = True,
        rate_limit: str = "",
        concurrent_fragments: str = "1",
        playlist_start: str = "",
        playlist_end: str = "",
        extra_options: str = "",
    ) -> Tuple[str, str, int, bool]:
        """
        Execute the yt-dlp download process.

        Returns:
            tuple: (output_dir, summary, download_count, success)
        """
        try:
            # Clean up input parameters  
            if batch_file and batch_file.strip() == "":
                batch_file = None
            if config_path and config_path.strip() == "":
                config_path = None
            if cookie_file and cookie_file.strip() == "":
                cookie_file = None
            if archive_file and archive_file.strip() == "":
                archive_file = "./yt-dlp-archive.txt"
            if rate_limit and rate_limit.strip() == "":
                rate_limit = None
            if playlist_start and playlist_start.strip() == "":
                playlist_start = None
            if playlist_end and playlist_end.strip() == "":
                playlist_end = None

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
            if batch_file:
                batch_file = os.path.abspath(batch_file)

            # Create downloader instance
            downloader = YtDlpDownloader(
                url_list=url_list.splitlines() if url_list.strip() else [],
                batch_file=batch_file,
                output_dir=output_dir,
                config_path=config_path,
                cookie_file=cookie_file,
                use_browser_cookies=use_browser_cookies,
                browser_name=browser_name,
                use_download_archive=use_download_archive,
                archive_file=archive_file,
                format_selector=format_selector,
                extract_audio=extract_audio,
                audio_format=audio_format,
                audio_quality=audio_quality,
                download_subtitles=download_subtitles,
                subtitle_langs=subtitle_langs,
                embed_subtitles=embed_subtitles,
                write_info_json=write_info_json,
                organize_files=organize_files,
                rate_limit=rate_limit,
                concurrent_fragments=concurrent_fragments,
                playlist_start=playlist_start,
                playlist_end=playlist_end,
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
                output_dir if "output_dir" in locals() else "./yt-dlp-output",
                error_summary,
                0,
                False,
            )


# Additional utility functions for the node
def check_yt_dlp_installation():
    """Helper function to check if yt-dlp is properly installed."""
    try:
        result = subprocess.run(
            ["yt-dlp", "--version"], capture_output=True, text=True, timeout=5
        )
        return result.returncode == 0, result.stdout if result.returncode == 0 else result.stderr
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False, "yt-dlp not found in PATH"


# Node mappings for ComfyUI registration
NODE_CLASS_MAPPINGS = {
    "YtDlpDownloader": YtDlpNode,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "YtDlpDownloader": "YouTube Downloader (yt-dlp)",
}

# Export for ComfyUI
__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "YtDlpNode", "YtDlpDownloader"]
