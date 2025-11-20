"""
Setup External Integration

Description: Setup script for configuring MCP integration with Claude Desktop
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

 #!/usr/bin/env python3
"""
Quick Start Script for Web Image Scraper MCP Integration

This script helps you get started with using the web-image-scraper outside of ComfyUI.
"""

import sys
import os
import subprocess
from pathlib import Path

def print_header():
    print("🚀 Web Image Scraper v0.81 - External Integration Setup")
    print("=" * 60)
    print()

def check_environment():
    """Check if we're in the right directory"""
    current_dir = Path.cwd()
    
    # Check for key files
    nodes_dir = current_dir / "nodes"
    scraper_file = nodes_dir / "web-image-scraper-node_v081.py"
    
    if not scraper_file.exists():
        print("❌ Error: web-image-scraper-node_v081.py not found")
        print(f"   Current directory: {current_dir}")
        print("   Please run this script from the Metadata_system directory")
        return False
    
    print("✅ Environment check passed")
    print(f"   Working directory: {current_dir}")
    return True

def install_mcp_dependencies():
    """Install MCP dependencies"""
    print("\n📦 Installing MCP Dependencies...")
    
    try:
        # Check if mcp is already installed
        import mcp
        print("✅ MCP already installed")
        return True
    except ImportError:
        pass
    
    try:
        # Install MCP
        subprocess.check_call([sys.executable, "-m", "pip", "install", "mcp"])
        print("✅ MCP installed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install MCP: {e}")
        print("   You can install manually with: pip install mcp")
        return False

def test_basic_functionality():
    """Test that the scraper can be imported and used"""
    print("\n🧪 Testing Basic Functionality...")
    
    try:
        # Test import
        import importlib.util
        scraper_path = Path.cwd() / "nodes" / "web-image-scraper-node_v081.py"
        
        spec = importlib.util.spec_from_file_location("web_scraper", str(scraper_path))
        web_scraper_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(web_scraper_module)
        
        EricWebFileScraper = web_scraper_module.EricWebFileScraper
        
        # Test initialization
        scraper = EricWebFileScraper()
        print("✅ Scraper import and initialization successful")
        return True
        
    except Exception as e:
        print(f"❌ Basic functionality test failed: {e}")
        return False

def create_claude_config():
    """Create sample Claude Desktop configuration"""
    print("\n📝 Creating Claude Desktop Configuration...")
    
    current_dir = Path.cwd().resolve()
    
    config = {
        "mcpServers": {
            "web-image-scraper": {
                "command": "python",
                "args": [str(current_dir / "mcp_web_scraper_server.py")],
                "env": {
                    "PYTHONPATH": str(current_dir)
                }
            }
        }
    }
    
    config_file = current_dir / "claude_desktop_config_sample.json"
    
    import json
    with open(config_file, 'w') as f:
        json.dump(config, indent=2, fp=f)
    
    print(f"✅ Sample configuration saved to: {config_file}")
    print("\n📋 To use with Claude Desktop:")
    print("1. Copy the content of claude_desktop_config_sample.json")
    print("2. Add it to your Claude Desktop configuration file")
    print("3. Restart Claude Desktop")
    
    return True

def show_usage_examples():
    """Show usage examples"""
    print("\n🎯 Usage Examples:")
    print("-" * 40)
    
    print("\n1. CLI Usage (Instagram - optimized for 199+ posts):")
    print('   python web_scraper_cli.py --url "https://www.instagram.com/nasa/" --output-dir "nasa_images"')
    
    print("\n2. CLI Usage (Bluesky with quality filter):")
    print('   python web_scraper_cli.py --url "https://bsky.app/profile/user.bsky.social" --min-width 1920')
    
    print("\n3. MCP Server (start for external tools):")
    print("   python mcp_web_scraper_server.py")
    
    print("\n4. Direct Python Import:")
    print("""   import sys, importlib.util
   spec = importlib.util.spec_from_file_location("scraper", "nodes/web-image-scraper-node_v081.py")
   module = importlib.util.module_from_spec(spec)
   spec.loader.exec_module(module)
   scraper = module.EricWebFileScraper()""")

def show_recent_improvements():
    """Show recent performance improvements"""
    print("\n🚀 Recent Performance Improvements:")
    print("-" * 40)
    print("✅ Instagram: 45 → 199+ posts extracted (4.4x improvement)")
    print("✅ Stories: Enabled with authentication")
    print("✅ HEIC Support: Apple image format compatibility")
    print("✅ Rate Limiting: Optimized for faster, safer extraction")
    print("✅ Error Handling: Robust location query handling")
    print("✅ Deduplication: Enhanced duplicate detection")

def main():
    """Main setup function"""
    print_header()
    
    # Check environment
    if not check_environment():
        return 1
    
    # Show recent improvements
    show_recent_improvements()
    
    # Test basic functionality
    if not test_basic_functionality():
        print("\n⚠️  Basic functionality test failed, but MCP/CLI may still work")
    
    # Install MCP (optional)
    mcp_installed = install_mcp_dependencies()
    
    # Create Claude config
    create_claude_config()
    
    # Show usage examples
    show_usage_examples()
    
    # Final summary
    print("\n" + "=" * 60)
    print("🎉 Setup Complete!")
    print()
    print("✅ Available Interfaces:")
    print("   • CLI: web_scraper_cli.py")
    if mcp_installed:
        print("   • MCP Server: mcp_web_scraper_server.py")
    else:
        print("   • MCP Server: Available (install mcp package)")
    print("   • Direct Import: Load web-image-scraper-node_v081.py")
    
    print("\n🎯 Key Features:")
    print("   • Instagram profiles (199+ posts vs 45 before)")
    print("   • Bluesky profiles")
    print("   • Stories support (with authentication)")
    print("   • 18+ specialized site handlers")
    print("   • Advanced filtering and deduplication")
    print("   • Metadata extraction")
    
    print("\n📚 Documentation:")
    print("   • MCP_INTEGRATION_GUIDE.md - Complete usage guide")
    print("   • test_integration.py - Test all components")
    print("   • claude_desktop_config_sample.json - Claude setup")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
