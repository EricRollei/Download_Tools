"""
Download Tools - ComfyUI Custom Node Package

Description: Media downloading nodes for ComfyUI. Supports downloading from 1000+ websites
    including Instagram, Reddit, Twitter, YouTube, TikTok, and more using gallery-dl and yt-dlp.

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
This package uses the following third-party tools:
- gallery-dl (GNU GPL v2) by Mike Fährmann: https://github.com/mikf/gallery-dl
- yt-dlp (Unlicense/Public Domain): https://github.com/yt-dlp/yt-dlp
- browser-cookie3 (GNU GPL v3) for cookie extraction
See CREDITS.md for complete list of dependencies and their licenses.
"""

import os
import sys
from pathlib import Path

# Initialize node mappings
NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}

# Get the nodes directory
def get_nodes_dir():
    """Get the absolute path to the nodes directory."""
    return os.path.join(os.path.dirname(__file__), "nodes")

# Dynamically load all node modules from the nodes directory
def load_nodes():
    """Load all Python modules from the nodes directory."""
    nodes_dir = get_nodes_dir()
    
    if not os.path.exists(nodes_dir):
        print(f"[Download Tools] Warning: nodes directory not found at {nodes_dir}")
        return
    
    # Add nodes directory to Python path
    if nodes_dir not in sys.path:
        sys.path.insert(0, nodes_dir)
    
    # Import each Python file in the nodes directory
    for filename in os.listdir(nodes_dir):
        if filename.endswith(".py") and not filename.startswith("_"):
            module_name = filename[:-3]
            try:
                # Import the module
                module_path = os.path.join(nodes_dir, filename)
                print(f"[Download Tools] Loading node: {module_name}")
                
                # Read and execute the module
                with open(module_path, 'r', encoding='utf-8') as f:
                    module_code = f.read()
                
                # Create a module namespace
                module_namespace = {
                    '__name__': f'download_tools.nodes.{module_name}',
                    '__file__': module_path,
                }
                
                # Execute the module code
                exec(module_code, module_namespace)
                
                # Extract NODE_CLASS_MAPPINGS and NODE_DISPLAY_NAME_MAPPINGS
                if 'NODE_CLASS_MAPPINGS' in module_namespace:
                    NODE_CLASS_MAPPINGS.update(module_namespace['NODE_CLASS_MAPPINGS'])
                    print(f"[Download Tools] ✓ Registered classes from {module_name}: {list(module_namespace['NODE_CLASS_MAPPINGS'].keys())}")
                
                if 'NODE_DISPLAY_NAME_MAPPINGS' in module_namespace:
                    NODE_DISPLAY_NAME_MAPPINGS.update(module_namespace['NODE_DISPLAY_NAME_MAPPINGS'])
                
            except Exception as e:
                print(f"[Download Tools] Error loading {module_name}: {e}")
                import traceback
                traceback.print_exc()

# Load all nodes
load_nodes()

# Print summary
print(f"[Download Tools] Loaded {len(NODE_CLASS_MAPPINGS)} node(s):")
for node_name in NODE_CLASS_MAPPINGS.keys():
    display_name = NODE_DISPLAY_NAME_MAPPINGS.get(node_name, node_name)
    print(f"  - {display_name} ({node_name})")

# Export for ComfyUI
__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS']
