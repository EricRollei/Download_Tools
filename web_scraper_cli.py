"""
Web Scraper Cli

Description: Command-line interface for web scraping with support for Instagram, Bluesky, and other platforms
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
- Uses Playwright (Apache 2.0): https://github.com/microsoft/playwright
- Uses Scrapling (Apache 2.0): https://github.com/D4Vinci/Scrapling
- See CREDITS.md for complete list of all dependencies
"""

#!/usr/bin/env python3
"""
Standalone CLI Wrapper for Eric's Web Image Scraper v0.81

This script allows you to use the web-image-scraper functionality outside of ComfyUI
via command line interface. Perfect for automation, scripts, or testing.

Usage Examples:
  # Basic Instagram profile scraping
  python web_scraper_cli.py --url "https://www.instagram.com/nasa/" --output-dir "nasa_images"
  
  # Bluesky profile with custom settings
  python web_scraper_cli.py --url "https://bsky.app/profile/user.bsky.social" --max-files 500 --min-width 1024
  
  # Multiple URLs with metadata
  python web_scraper_cli.py --url "https://example.com/" --url "https://another-site.com/" --extract-metadata
  
  # High-quality image filtering
  python web_scraper_cli.py --url "https://instagram.com/photographer/" --min-width 1920 --min-height 1080 --max-files 50

Install Dependencies:
  pip install scrapling playwright imagehash pillow requests
  playwright install
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import List, Optional

# Add current directory to path for imports
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

try:
    # Import the scraper using the actual filename
    import importlib.util
    
    scraper_path = os.path.join(current_dir, 'nodes', 'web-image-scraper-node_v081.py')
    spec = importlib.util.spec_from_file_location("web_image_scraper_node_v081", scraper_path)
    web_scraper_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(web_scraper_module)
    EricWebFileScraper = web_scraper_module.EricWebFileScraper
    print("✅ Successfully imported EricWebFileScraper")
except Exception as e:
    print(f"❌ Could not import EricWebFileScraper: {e}")
    print("Make sure you're running this from the Metadata_system directory")
    sys.exit(1)

def create_parser() -> argparse.ArgumentParser:
    """Create argument parser"""
    parser = argparse.ArgumentParser(
        description="Eric's Web Image Scraper v0.81 - Standalone CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Instagram profile (199+ posts vs 45 before optimization)
  python web_scraper_cli.py --url "https://www.instagram.com/nasa/" --output-dir "nasa_images" --max-files 200

  # Bluesky profile with high-quality filter
  python web_scraper_cli.py --url "https://bsky.app/profile/user.bsky.social" --min-width 1920 --min-height 1080

  # Multiple sites with metadata extraction
  python web_scraper_cli.py --url "https://example.com/" --url "https://portfolio.com/" --extract-metadata --save-metadata-json

  # Stealth mode for difficult sites
  python web_scraper_cli.py --url "https://protected-site.com/" --use-stealth-mode --timeout 120

  # Continue previous run
  python web_scraper_cli.py --url "https://large-site.com/" --continue-last-run --output-dir "previous_output"
        """
    )
    
    # Required arguments
    parser.add_argument(
        "--url", "-u",
        action="append",
        required=True,
        help="URL(s) to scrape. Can be specified multiple times for multiple URLs."
    )
    
    # Output settings
    parser.add_argument(
        "--output-dir", "-o",
        default="web_scraper_output",
        help="Output directory for downloaded files (default: web_scraper_output)"
    )
    
    parser.add_argument(
        "--filename-prefix",
        default="WS81_",
        help="Prefix for downloaded files (default: WS81_)"
    )
    
    # Image filtering
    parser.add_argument(
        "--min-width",
        type=int,
        default=512,
        help="Minimum image width (default: 512)"
    )
    
    parser.add_argument(
        "--min-height", 
        type=int,
        default=512,
        help="Minimum image height (default: 512)"
    )
    
    parser.add_argument(
        "--max-files",
        type=int,
        default=1000,
        help="Maximum files to download, 0=unlimited (default: 1000)"
    )
    
    # Content types
    parser.add_argument(
        "--no-images",
        action="store_true",
        help="Skip image downloads"
    )
    
    parser.add_argument(
        "--no-videos",
        action="store_true", 
        help="Skip video downloads"
    )
    
    parser.add_argument(
        "--download-audio",
        action="store_true",
        help="Download audio files"
    )
    
    # Behavior options
    parser.add_argument(
        "--same-domain-only",
        action="store_true",
        default=True,
        help="Stay on the same domain (default: enabled)"
    )
    
    parser.add_argument(
        "--allow-off-domain",
        action="store_true",
        help="Allow downloading from other domains"
    )
    
    parser.add_argument(
        "--continue-last-run",
        action="store_true",
        help="Continue from previous run to avoid duplicates"
    )
    
    # Metadata options
    parser.add_argument(
        "--extract-metadata",
        action="store_true",
        default=True,
        help="Extract image metadata (default: enabled)"
    )
    
    parser.add_argument(
        "--save-metadata-json",
        action="store_true",
        default=True,
        help="Save metadata to JSON file (default: enabled)"
    )
    
    parser.add_argument(
        "--metadata-format",
        choices=["json", "csv", "md"],
        default="json",
        help="Metadata export format (default: json)"
    )
    
    # Deduplication
    parser.add_argument(
        "--hash-algorithm",
        choices=["average_hash", "phash", "dhash", "whash", "none"],
        default="average_hash",
        help="Hash algorithm for deduplication (default: average_hash)"
    )
    
    parser.add_argument(
        "--move-duplicates",
        action="store_true",
        help="Move duplicates to subfolder instead of deleting"
    )
    
    # Browser settings
    parser.add_argument(
        "--timeout",
        type=float,
        default=100.0,
        help="Page load timeout in seconds (default: 100)"
    )
    
    parser.add_argument(
        "--handler-timeout",
        type=float,
        default=120.0,
        help="API handler timeout in seconds (default: 120)"
    )
    
    parser.add_argument(
        "--use-stealth-mode",
        action="store_true",
        help="Use stealth mode to avoid detection"
    )
    
    parser.add_argument(
        "--stealth-level",
        choices=["basic", "enhanced", "extreme"],
        default="basic",
        help="Stealth mode level (default: basic)"
    )
    
    # Scrolling options
    parser.add_argument(
        "--max-auto-scrolls",
        type=int,
        default=150,
        help="Maximum automatic scrolls (default: 150)"
    )
    
    parser.add_argument(
        "--scroll-delay",
        type=int,
        default=1000,
        help="Scroll delay in milliseconds (default: 1000)"
    )
    
    # Crawling options
    parser.add_argument(
        "--crawl-links",
        action="store_true",
        help="Follow links to other pages"
    )
    
    parser.add_argument(
        "--crawl-depth",
        type=int,
        default=1,
        help="Link crawling depth (default: 1)"
    )
    
    parser.add_argument(
        "--max-pages",
        type=int,
        default=10,
        help="Maximum pages to visit when crawling (default: 10)"
    )
    
    # Output options
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress output except errors"
    )
    
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output"
    )
    
    parser.add_argument(
        "--json-output",
        action="store_true",
        help="Output results in JSON format"
    )
    
    return parser

def validate_args(args) -> None:
    """Validate command line arguments"""
    # Handle domain restrictions
    if args.allow_off_domain:
        args.same_domain_only = False
    
    # Handle content type flags
    if args.no_images:
        args.download_images = False
    else:
        args.download_images = True
        
    if args.no_videos:
        args.download_videos = False
    else:
        args.download_videos = True
    
    # Validate dimensions
    if args.min_width < 0 or args.min_height < 0:
        raise ValueError("Minimum dimensions cannot be negative")
    
    if args.max_files < 0:
        raise ValueError("Max files cannot be negative")
    
    # Validate timeouts
    if args.timeout <= 0 or args.handler_timeout <= 0:
        raise ValueError("Timeouts must be positive")

def format_results(result_tuple, args) -> str:
    """Format scraping results for output"""
    (output_path, processed_files, total_found, total_downloaded,
     total_videos, total_images, total_skipped, total_deduplicated,
     total_failed, total_audio, total_moved, total_links_found,
     total_pages_visited, stats_json) = result_tuple
    
    if args.json_output:
        # JSON output format
        result_data = {
            "status": "success",
            "output_path": output_path,
            "statistics": {
                "total_found": total_found,
                "total_downloaded": total_downloaded,
                "total_images": total_images,
                "total_videos": total_videos,
                "total_audio": total_audio,
                "total_skipped": total_skipped,
                "total_deduplicated": total_deduplicated,
                "total_failed": total_failed,
                "total_moved": total_moved,
                "total_links_found": total_links_found,
                "total_pages_visited": total_pages_visited
            },
            "processed_files": processed_files,
            "raw_stats": json.loads(stats_json) if stats_json else None
        }
        return json.dumps(result_data, indent=2)
    else:
        # Human-readable format
        lines = [
            "🎉 Scraping Complete!",
            "=" * 50,
            f"📁 Output Directory: {output_path}",
            f"📊 Files Found: {total_found}",
            f"⬇️  Downloaded: {total_downloaded}",
            f"🖼️  Images: {total_images}",
            f"🎥 Videos: {total_videos}",
        ]
        
        if total_audio > 0:
            lines.append(f"🎵 Audio: {total_audio}")
        
        lines.extend([
            f"⏭️  Skipped: {total_skipped}",
            f"🔄 Deduplicated: {total_deduplicated}",
        ])
        
        if total_moved > 0:
            lines.append(f"📦 Moved Duplicates: {total_moved}")
        
        if total_failed > 0:
            lines.append(f"❌ Failed: {total_failed}")
        
        if total_links_found > 0:
            lines.append(f"🔗 Links Found: {total_links_found}")
        
        if total_pages_visited > 1:
            lines.append(f"📄 Pages Visited: {total_pages_visited}")
        
        if processed_files:
            lines.extend([
                "",
                "📋 Sample Files:",
                *[f"  • {f}" for f in processed_files[:5]]
            ])
            
            if len(processed_files) > 5:
                lines.append(f"  ... and {len(processed_files) - 5} more")
        
        return "\n".join(lines)

async def main():
    """Main CLI function"""
    parser = create_parser()
    args = parser.parse_args()
    
    try:
        validate_args(args)
    except ValueError as e:
        print(f"❌ Argument error: {e}")
        sys.exit(1)
    
    # Initialize scraper
    if not args.quiet:
        print("🚀 Initializing Eric's Web Image Scraper v0.81...")
    
    scraper = EricWebFileScraper()
    
    # Prepare arguments for scraper
    scraper_kwargs = {
        "url": "\n".join(args.url),  # Join multiple URLs with newlines
        "output_dir": args.output_dir,
        "min_width": args.min_width,
        "min_height": args.min_height,
        "max_files": args.max_files,
        "download_images": args.download_images,
        "download_videos": args.download_videos,
        "download_audio": args.download_audio,
        "same_domain_only": args.same_domain_only,
        "filename_prefix": args.filename_prefix,
        "continue_last_run": args.continue_last_run,
        "extract_metadata": args.extract_metadata,
        "save_metadata_json": args.save_metadata_json,
        "metadata_export_format": args.metadata_format,
        "hash_algorithm": args.hash_algorithm,
        "move_duplicates": args.move_duplicates,
        "timeout_seconds": args.timeout,
        "handler_timeout": args.handler_timeout,
        "use_stealth_mode": args.use_stealth_mode,
        "stealth_mode_level": args.stealth_level,
        "max_auto_scrolls": args.max_auto_scrolls,
        "scroll_delay_ms": args.scroll_delay,
        "crawl_links": args.crawl_links,
        "crawl_depth": args.crawl_depth,
        "max_pages": args.max_pages,
    }
    
    try:
        if not args.quiet:
            print(f"🔍 Starting scrape for {len(args.url)} URL(s)...")
            if args.verbose:
                print(f"📋 Settings: {json.dumps({k: v for k, v in scraper_kwargs.items() if k != 'url'}, indent=2)}")
        
        # Run the scraper
        result = scraper.scrape_files(**scraper_kwargs)
        
        # Format and display results
        output = format_results(result, args)
        print(output)
        
    except KeyboardInterrupt:
        print("\n⏹️  Scraping interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Scraping failed: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    # Handle async properly
    try:
        import nest_asyncio
        nest_asyncio.apply()
    except ImportError:
        pass
    
    # Run the main function
    asyncio.run(main())
