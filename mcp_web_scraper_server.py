"""
Mcp Web Scraper Server

Description: Model Context Protocol (MCP) server for web scraping integration with Claude Desktop and other MCP clients
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
- Uses Model Context Protocol SDK (MIT License): https://github.com/modelcontextprotocol
- See CREDITS.md for complete list of all dependencies
"""

#!/usr/bin/env python3
"""
MCP Server for Eric's Web Image Scraper v0.81

This MCP server exposes the web-image-scraper functionality for use with
Claude Desktop, LM Studio, or any MCP-compatible application.

Features:
- Full web scraping capabilities from the ComfyUI node
- Support for Instagram, Bluesky, and generic websites
- Image and video downloading with metadata
- Deduplication and filtering
- Async support with proper error handling

Install dependencies:
pip install mcp scrapling playwright imagehash pillow requests
playwright install

Usage with Claude Desktop:
Add to your claude_desktop_config.json:
{
  "mcpServers": {
    "web-image-scraper": {
      "command": "python",
      "args": ["path/to/mcp_web_scraper_server.py"]
    }
  }
}
"""

import asyncio
import json
import logging
import os
import sys
from typing import Any, Dict, List, Optional, Union
from pathlib import Path

# Add the current directory to Python path for imports
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

try:
    from mcp.server.models import InitializationOptions
    from mcp.server import NotificationOptions, Server
    from mcp.types import (
        CallToolRequest,
        CallToolResult,
        ListToolsRequest,
        TextContent,
        Tool,
    )
except ImportError:
    print("MCP not installed. Install with: pip install mcp")
    sys.exit(1)

# Import the scraper components
try:
    # Try to import the web scraper directly using the actual filename
    import importlib.util
    import os
    
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

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("web-scraper-mcp")

# Initialize the MCP server
app = Server("web-image-scraper")

# Global scraper instance
scraper_instance = None

def initialize_scraper():
    """Initialize the scraper instance"""
    global scraper_instance
    if scraper_instance is None:
        scraper_instance = EricWebFileScraper()
        logger.info("🚀 Web scraper initialized")
    return scraper_instance

@app.list_tools()
async def handle_list_tools() -> list[Tool]:
    """List available tools"""
    return [
        Tool(
            name="scrape_web_images",
            description="Scrape images and videos from websites with advanced options",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "URL to scrape (supports Instagram, Bluesky, or any website). Can be multiple URLs separated by newlines."
                    },
                    "output_dir": {
                        "type": "string", 
                        "description": "Output directory for downloaded files",
                        "default": "web_scraper_output"
                    },
                    "min_width": {
                        "type": "integer",
                        "description": "Minimum image width",
                        "default": 512
                    },
                    "min_height": {
                        "type": "integer", 
                        "description": "Minimum image height",
                        "default": 512
                    },
                    "max_files": {
                        "type": "integer",
                        "description": "Maximum files to download (0 = unlimited)",
                        "default": 1000
                    },
                    "download_images": {
                        "type": "boolean",
                        "description": "Download images",
                        "default": True
                    },
                    "download_videos": {
                        "type": "boolean",
                        "description": "Download videos", 
                        "default": True
                    },
                    "same_domain_only": {
                        "type": "boolean",
                        "description": "Stay on the same domain",
                        "default": True
                    },
                    "filename_prefix": {
                        "type": "string",
                        "description": "Prefix for downloaded files",
                        "default": "WS81_"
                    },
                    "extract_metadata": {
                        "type": "boolean",
                        "description": "Extract and save metadata",
                        "default": True
                    },
                    "hash_algorithm": {
                        "type": "string",
                        "description": "Hash algorithm for deduplication",
                        "enum": ["average_hash", "phash", "dhash", "whash", "none"],
                        "default": "average_hash"
                    },
                    "move_duplicates": {
                        "type": "boolean",
                        "description": "Move duplicates to subfolder instead of deleting",
                        "default": False
                    },
                    "timeout_seconds": {
                        "type": "number",
                        "description": "Page load timeout in seconds",
                        "default": 100.0
                    },
                    "use_stealth_mode": {
                        "type": "boolean",
                        "description": "Use stealth mode to avoid detection",
                        "default": False
                    },
                    "max_auto_scrolls": {
                        "type": "integer",
                        "description": "Maximum automatic scrolls",
                        "default": 150
                    }
                },
                "required": ["url"]
            }
        ),
        Tool(
            name="scrape_instagram_profile", 
            description="Specialized Instagram profile scraping with stories support",
            inputSchema={
                "type": "object",
                "properties": {
                    "username": {
                        "type": "string",
                        "description": "Instagram username (without @)"
                    },
                    "output_dir": {
                        "type": "string",
                        "description": "Output directory",
                        "default": "instagram_scraper_output"
                    },
                    "max_posts": {
                        "type": "integer", 
                        "description": "Maximum posts to download",
                        "default": 200
                    },
                    "include_stories": {
                        "type": "boolean",
                        "description": "Include stories (requires authentication)",
                        "default": True
                    },
                    "min_width": {
                        "type": "integer",
                        "description": "Minimum image width",
                        "default": 512
                    },
                    "min_height": {
                        "type": "integer",
                        "description": "Minimum image height", 
                        "default": 512
                    }
                },
                "required": ["username"]
            }
        ),
        Tool(
            name="scrape_bluesky_profile",
            description="Specialized Bluesky profile scraping",
            inputSchema={
                "type": "object", 
                "properties": {
                    "username": {
                        "type": "string",
                        "description": "Bluesky username (with or without .bsky.social)"
                    },
                    "output_dir": {
                        "type": "string",
                        "description": "Output directory",
                        "default": "bluesky_scraper_output" 
                    },
                    "max_posts": {
                        "type": "integer",
                        "description": "Maximum posts to scrape",
                        "default": 200
                    },
                    "min_width": {
                        "type": "integer",
                        "description": "Minimum image width",
                        "default": 512
                    },
                    "min_height": {
                        "type": "integer",
                        "description": "Minimum image height",
                        "default": 512
                    }
                },
                "required": ["username"]
            }
        ),
        Tool(
            name="get_scraper_status",
            description="Get current scraper configuration and capabilities",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        )
    ]

@app.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool calls"""
    try:
        scraper = initialize_scraper()
        
        if name == "scrape_web_images":
            return await handle_scrape_web_images(arguments)
        elif name == "scrape_instagram_profile":
            return await handle_scrape_instagram_profile(arguments)
        elif name == "scrape_bluesky_profile":
            return await handle_scrape_bluesky_profile(arguments)
        elif name == "get_scraper_status":
            return await handle_get_scraper_status(arguments)
        else:
            raise ValueError(f"Unknown tool: {name}")
            
    except Exception as e:
        logger.error(f"Error in tool {name}: {e}")
        return [TextContent(type="text", text=f"Error: {str(e)}")]

async def handle_scrape_web_images(args: dict) -> list[TextContent]:
    """Handle general web scraping"""
    scraper = initialize_scraper()
    
    # Set default values
    defaults = {
        "output_dir": "web_scraper_output",
        "min_width": 512,
        "min_height": 512, 
        "max_files": 1000,
        "download_images": True,
        "download_videos": True,
        "same_domain_only": True,
        "filename_prefix": "WS81_",
        "extract_metadata": True,
        "hash_algorithm": "average_hash",
        "move_duplicates": False,
        "timeout_seconds": 100.0,
        "use_stealth_mode": False,
        "max_auto_scrolls": 150
    }
    
    # Merge arguments with defaults
    kwargs = {**defaults, **args}
    
    try:
        logger.info(f"🔍 Starting web scrape for: {kwargs['url']}")
        
        # Call the scraper
        result = scraper.scrape_files(**kwargs)
        
        # Parse the result tuple
        (output_path, processed_files, total_found, total_downloaded, 
         total_videos, total_images, total_skipped, total_deduplicated,
         total_failed, total_audio, total_moved, total_links_found,
         total_pages_visited, stats_json) = result
        
        # Create summary
        summary = {
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
            "processed_files": processed_files[:10] if processed_files else [],  # Limit to first 10
            "settings_used": {
                "url": kwargs["url"],
                "min_dimensions": f"{kwargs['min_width']}x{kwargs['min_height']}",
                "max_files": kwargs["max_files"],
                "file_types": {
                    "images": kwargs["download_images"],
                    "videos": kwargs["download_videos"]
                }
            }
        }
        
        if len(processed_files) > 10:
            summary["note"] = f"Showing first 10 files of {len(processed_files)} total"
        
        return [TextContent(type="text", text=json.dumps(summary, indent=2))]
        
    except Exception as e:
        logger.error(f"Scraping failed: {e}")
        return [TextContent(type="text", text=f"❌ Scraping failed: {str(e)}")]

async def handle_scrape_instagram_profile(args: dict) -> list[TextContent]:
    """Handle Instagram profile scraping"""
    username = args["username"].lstrip("@")
    url = f"https://www.instagram.com/{username}/"
    
    # Build arguments for the main scraper
    scraper_args = {
        "url": url,
        "output_dir": args.get("output_dir", "instagram_scraper_output"),
        "min_width": args.get("min_width", 512),
        "min_height": args.get("min_height", 512),
        "max_files": args.get("max_posts", 200),
        "download_images": True,
        "download_videos": True,
        "extract_metadata": True,
        "filename_prefix": f"IG_{username}_",
        "use_url_as_folder": True,
        "same_domain_only": True
    }
    
    # Add Instagram-specific note
    result = await handle_scrape_web_images(scraper_args)
    
    # Add Instagram-specific information
    if result and result[0].text:
        data = json.loads(result[0].text)
        data["instagram_notes"] = [
            "🔐 Stories require authentication (configure in configs/auth_config.json)",
            "📱 Recent optimization increased extraction from ~45 to 199+ posts",
            "🎬 Reels are included in regular post extraction",
            "⭐ Highlights are partially supported"
        ]
        
        return [TextContent(type="text", text=json.dumps(data, indent=2))]
    
    return result

async def handle_scrape_bluesky_profile(args: dict) -> list[TextContent]:
    """Handle Bluesky profile scraping"""
    username = args["username"]
    if not username.endswith(".bsky.social"):
        username = f"{username}.bsky.social"
    
    url = f"https://bsky.app/profile/{username}"
    
    # Build arguments for the main scraper
    scraper_args = {
        "url": url,
        "output_dir": args.get("output_dir", "bluesky_scraper_output"),
        "min_width": args.get("min_width", 512),
        "min_height": args.get("min_height", 512),
        "max_files": args.get("max_posts", 200),
        "download_images": True,
        "download_videos": True,
        "extract_metadata": True,
        "filename_prefix": f"BSKY_{username.split('.')[0]}_",
        "use_url_as_folder": True,
        "same_domain_only": True,
        "max_auto_scrolls": 200  # Bluesky needs more scrolling
    }
    
    return await handle_scrape_web_images(scraper_args)

async def handle_get_scraper_status(args: dict) -> list[TextContent]:
    """Get scraper status and capabilities"""
    scraper = initialize_scraper()
    
    # Check for optional dependencies
    capabilities = {
        "core_functionality": "✅ Available",
        "scrapling_support": "✅ Available" if hasattr(scraper, '_scrape_with_scrapling') else "❌ Not available",
        "playwright_support": "✅ Available" if hasattr(scraper, '_scrape_with_direct_playwright') else "❌ Not available",
        "imagehash_deduplication": "✅ Available",
        "supported_sites": [
            "Instagram (with authentication for stories)",
            "Bluesky", 
            "Generic websites",
            "YouTube (metadata)",
            "TikTok (limited)",
            "Reddit (limited)"
        ],
        "supported_formats": {
            "images": [".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tiff", ".svg", ".heic", ".heif"],
            "videos": [".mp4", ".webm", ".mov", ".avi", ".mkv", ".m4v", ".3gp"],
            "audio": [".mp3", ".wav", ".ogg", ".m4a", ".aac"]
        }
    }
    
    # Check authentication status
    try:
        import os
        auth_file = os.path.join(os.path.dirname(__file__), "configs", "auth_config.json")
        if os.path.exists(auth_file):
            with open(auth_file, 'r') as f:
                auth_config = json.load(f)
                if 'instagram.com' in auth_config:
                    capabilities["instagram_authentication"] = "✅ Configured"
                else:
                    capabilities["instagram_authentication"] = "⚠️ Not configured"
        else:
            capabilities["instagram_authentication"] = "❌ No auth config found"
    except Exception:
        capabilities["instagram_authentication"] = "❌ Error checking auth"
    
    status = {
        "scraper_version": "v0.81",
        "mcp_server_status": "✅ Running",
        "capabilities": capabilities,
        "default_settings": {
            "min_dimensions": "512x512",
            "max_files": 1000,
            "timeout": "100 seconds",
            "deduplication": "average_hash algorithm",
            "stealth_mode": "Available"
        },
        "recent_improvements": [
            "🚀 Instagram extraction: 45 → 199+ posts",
            "📱 Stories support with authentication", 
            "🎬 Enhanced video/reel handling",
            "🔄 HEIC/HEIF file format support",
            "⚡ Faster rate limiting optimization"
        ]
    }
    
    return [TextContent(type="text", text=json.dumps(status, indent=2))]

async def main():
    """Main server function"""
    # Import here to avoid issues if mcp not available
    from mcp.server.stdio import stdio_server
    
    logger.info("🚀 Starting Web Image Scraper MCP Server...")
    
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="web-image-scraper",
                server_version="1.0.0",
                capabilities=app.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )

if __name__ == "__main__":
    # Set up proper async handling
    try:
        import nest_asyncio
        nest_asyncio.apply()
    except ImportError:
        pass
    
    asyncio.run(main())
