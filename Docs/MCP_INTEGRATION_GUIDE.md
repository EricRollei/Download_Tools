# Web Image Scraper MCP Integration Guide

## Overview

The web-image-scraper v0.81 can now be used outside of ComfyUI through:
1. **MCP Server** - For Claude Desktop, LM Studio, and other MCP clients
2. **CLI Interface** - For command-line usage and automation
3. **Direct Python Import** - For custom integrations

## 🚀 Recent Performance Improvements

- **Instagram**: Increased from 45 to 199+ posts extracted
- **Stories Support**: Enabled with authentication
- **HEIC Support**: Added Apple image format compatibility
- **Rate Limiting**: Optimized for faster, safer extraction

## Installation

```bash
# Install dependencies
pip install mcp scrapling playwright imagehash pillow requests

# Install browser
playwright install
```

## 1. MCP Server Setup

### For Claude Desktop

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "web-image-scraper": {
      "command": "python",
      "args": ["path/to/Metadata_system/mcp_web_scraper_server.py"],
      "env": {
        "PYTHONPATH": "path/to/Metadata_system"
      }
    }
  }
}
```

### For LM Studio

1. Start the MCP server:
```bash
cd /path/to/Metadata_system
python mcp_web_scraper_server.py
```

2. Configure LM Studio to connect to the MCP server

### Available MCP Tools

1. **scrape_web_images** - General web scraping
2. **scrape_instagram_profile** - Specialized Instagram extraction  
3. **scrape_bluesky_profile** - Specialized Bluesky extraction
4. **get_scraper_status** - Check capabilities and configuration

## 2. CLI Interface

### Basic Usage

```bash
# Instagram profile (optimized for 200+ posts)
python web_scraper_cli.py --url "https://www.instagram.com/nasa/" --output-dir "nasa_images"

# Bluesky profile with quality filter
python web_scraper_cli.py --url "https://bsky.app/profile/user.bsky.social" --min-width 1920 --min-height 1080

# Multiple URLs with metadata
python web_scraper_cli.py --url "https://example.com/" --url "https://portfolio.com/" --extract-metadata

# Stealth mode for protected sites
python web_scraper_cli.py --url "https://difficult-site.com/" --use-stealth-mode --timeout 120
```

### Advanced Options

```bash
# Continue previous run
python web_scraper_cli.py --url "https://large-site.com/" --continue-last-run --output-dir "previous_output"

# High-quality images only
python web_scraper_cli.py --url "https://photography-site.com/" --min-width 2048 --min-height 1536 --max-files 100

# JSON output for automation
python web_scraper_cli.py --url "https://site.com/" --json-output --quiet
```

## 3. Direct Python Import

```python
import sys
sys.path.append('path/to/Metadata_system')

from nodes.web_image_scraper_node_v081 import EricWebFileScraper

# Initialize scraper
scraper = EricWebFileScraper()

# Configure and run
result = scraper.scrape_files(
    url="https://www.instagram.com/nasa/",
    output_dir="nasa_images",
    min_width=512,
    min_height=512,
    max_files=200,
    download_images=True,
    download_videos=True,
    extract_metadata=True
)

# Parse results
(output_path, processed_files, total_found, total_downloaded,
 total_videos, total_images, total_skipped, total_deduplicated,
 total_failed, total_audio, total_moved, total_links_found,
 total_pages_visited, stats_json) = result

print(f"Downloaded {total_downloaded} files to {output_path}")
```

## 4. Configuration

### Authentication Setup

For Instagram stories and enhanced access, configure authentication in `configs/auth_config.json`:

```json
{
  "instagram.com": {
    "authentication_type": "cookies",
    "user_id": "your_user_id",
    "cookies": [
      {"name": "sessionid", "value": "your_session", "domain": ".instagram.com"},
      {"name": "ds_user_id", "value": "your_id", "domain": ".instagram.com"}
    ]
  }
}
```

### Site Handlers

The scraper automatically detects and uses specialized handlers for:
- Instagram (with stories support)
- Bluesky 
- TikTok
- Reddit
- Generic websites

## 5. Example Integrations

### Automation Script

```python
#!/usr/bin/env python3
import subprocess
import json

def scrape_profile(platform, username, output_dir):
    """Scrape a social media profile"""
    if platform == "instagram":
        url = f"https://www.instagram.com/{username}/"
    elif platform == "bluesky":
        url = f"https://bsky.app/profile/{username}.bsky.social"
    else:
        raise ValueError(f"Unsupported platform: {platform}")
    
    cmd = [
        "python", "web_scraper_cli.py",
        "--url", url,
        "--output-dir", output_dir,
        "--json-output",
        "--quiet"
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    return json.loads(result.stdout)

# Usage
stats = scrape_profile("instagram", "nasa", "nasa_images")
print(f"Downloaded {stats['statistics']['total_downloaded']} files")
```

### Batch Processing

```bash
#!/bin/bash
# Batch scrape multiple Instagram profiles

profiles=("nasa" "spacex" "natgeo" "bbcearth")

for profile in "${profiles[@]}"; do
    echo "Scraping $profile..."
    python web_scraper_cli.py \
        --url "https://www.instagram.com/$profile/" \
        --output-dir "instagram_batch/$profile" \
        --max-files 100 \
        --min-width 1024 \
        --extract-metadata
done
```

## 6. MCP Usage Examples

### With Claude Desktop

```
Please scrape the Instagram profile @nasa using the web scraper and show me the statistics.

Parameters:
- Username: nasa
- Output directory: nasa_images
- Max posts: 200
- Include stories: true
```

### API Call Format

```json
{
  "method": "tools/call",
  "params": {
    "name": "scrape_instagram_profile",
    "arguments": {
      "username": "nasa",
      "output_dir": "nasa_images", 
      "max_posts": 200,
      "include_stories": true,
      "min_width": 1024,
      "min_height": 1024
    }
  }
}
```

## 7. Troubleshooting

### Common Issues

1. **Import Errors**: Ensure you're running from the Metadata_system directory
2. **Missing Dependencies**: Install with `pip install scrapling playwright imagehash`
3. **Browser Issues**: Run `playwright install` to download browsers
4. **Authentication**: Configure `configs/auth_config.json` for Instagram stories

### Performance Tips

1. **Use stealth mode** for difficult sites
2. **Increase timeouts** for slow networks
3. **Configure authentication** for private content
4. **Use quality filters** to reduce file count
5. **Enable deduplication** to avoid duplicates

## 8. Feature Summary

### ✅ Supported Sites
- Instagram (199+ posts, stories with auth)
- Bluesky (full profile support)
- Generic websites (universal compatibility)
- YouTube, TikTok, Reddit (limited)

### ✅ File Types
- Images: JPG, PNG, WebP, GIF, HEIC, HEIF, SVG
- Videos: MP4, WebM, MOV, AVI, MKV
- Audio: MP3, WAV, OGG, M4A (optional)

### ✅ Features
- Advanced filtering by dimensions
- Metadata extraction and export
- Duplicate detection and removal
- Rate limiting and stealth mode
- Multi-URL processing
- Continue from previous runs
- Link crawling and pagination

The web-image-scraper is now fully accessible outside ComfyUI with enhanced capabilities! 🚀
