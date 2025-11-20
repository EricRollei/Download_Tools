"""
Base Handler

Description: Base handler class for site-specific web scraping implementations
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
Base class for site-specific handlers for the Web Image Scraper
"""
import os
import re
import json
import asyncio
import time
import random
from urllib.parse import urlparse
from typing import Optional, List, Dict, Any, Union


class BaseSiteHandler:
    """
    Base class that all site-specific handlers should inherit from.
    
    Site handlers allow customized scraping logic for specific websites
    that may have unique structures or requirements.
    """
    
    @classmethod
    def can_handle(cls, url):
        """
        Determine if this handler can process the given URL.
        
        Args:
            url (str): The URL to check
            
        Returns:
            bool: True if this handler can process the URL, False otherwise
        """
        return False
    
    def __init__(self, url, scraper):
        """
        Initialize the handler.
        
        Args:
            url (str): The URL to scrape
            scraper (EricWebFileScraper): The main scraper instance
        """
        self.url = url
        self.scraper = scraper
        self.domain = self._extract_domain(url)
        
    def _extract_domain(self, url):
        """Extract domain from URL"""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc
            # Remove www. prefix if present
            if domain.startswith('www.'):
                domain = domain[4:]
            return domain
        except Exception as e:
            print(f"Error extracting domain: {e}")
            return "unknown_domain"

    # --- API preference (async-compatible) ---
    def prefers_api(self) -> bool:
        """
        Does this handler prefer to use an API for extraction?
        If True, the scraper will attempt to call extract_api_data_async.
        """
        return False  # Default to False

    def requires_api(self) -> bool:
        """
        Does this handler require API access to function?
        If True, the scraper will always use the API method and warn if unavailable.
        """
        return False  # Default: most handlers do not require API

    # --- Async API extraction method ---
    async def extract_api_data_async(self, **kwargs) -> list:
        """
        Extract media items using a site-specific API asynchronously.
        Should be implemented by handlers that return True for prefers_api().

        Args:
            **kwargs: May include auth_config, max_pages, timeout, etc.

        Returns:
            list: A list of media item dictionaries.
        """
        print(f"Warning: {self.__class__.__name__} prefers API but does not implement extract_api_data_async.")
        return []

    # --- Main extraction method (async-only) ---
    async def extract_with_direct_playwright(self, page, **kwargs) -> list:
        """Extract media using Playwright page object with enhanced CDN handling."""
        print(f"Base extract_with_direct_playwright called for {self.__class__.__name__}")
        
        # Check for specialized async implementation
        if hasattr(self, 'extract_with_direct_playwright_async'):
            print(f"  Using specialized async extraction for {self.__class__.__name__}")
            return await self.extract_with_direct_playwright_async(page, **kwargs)
        
        # Get same_domain_only setting
        same_domain_only = kwargs.get('same_domain_only', True)
        
        # Extract media items using generic method
        media_items = []
        
        if hasattr(self.scraper, '_extract_media_from_pw_page'):
            basic_items = await self.scraper._extract_media_from_pw_page(page, self.url, **kwargs)
            media_items.extend(basic_items)
        
        # If same_domain_only is enabled, try to extract CDN images specifically
        if same_domain_only:
            print(f"  Extracting CDN images for {self.__class__.__name__}")
            cdn_items = await self.extract_cdn_images(page, self.url)
            
            if cdn_items:
                print(f"  Found {len(cdn_items)} CDN images")
                media_items.extend(cdn_items)
        
        # Mark trusted CDN domains
        for item in media_items:
            if 'url' in item:
                url = item['url']
                if self.is_trusted_domain(url):
                    item['trusted_cdn'] = True
                
                # Try to get highest resolution
                high_res_url = self.get_highest_resolution_url(url)
                if high_res_url != url:
                    item['url'] = high_res_url
        
        print(f"  Base handler found {len(media_items)} media items")
        return media_items


    # --- Scrapling extraction (async-only) ---
    async def extract_with_scrapling(self, response, **kwargs) -> list:
        """
        Extract media items using a Scrapling response object (async implementation).
        Called when the 'scrapling' strategy is chosen.

        Args:
            response: The Scrapling response object (often contains lxml tree).
            **kwargs: May include min_width, min_height, extract_metadata, etc.

        Returns:
            list: A list of media item dictionaries.
        """
        print(f"Warning: {self.__class__.__name__} using generic Scrapling extraction via scraper.")
        # Use async pattern consistently
        if self.scraper and hasattr(self.scraper, '_extract_media_from_scrapling_page'):
            return await self.scraper._extract_media_from_scrapling_page(response, self.url, **kwargs)
        return []

    async def post_process(self, media_items):
        """
        Perform site-specific post-processing on extracted media items.
        
        Args:
            media_items (list): List of media item dictionaries
            
        Returns:
            list: Processed list of media item dictionaries
        """
        return media_items

    def get_content_directory(self):
        """
        Generate a meaningful directory path based on the content of the URL.
        Returns a tuple of (base_dir, content_specific_dir)
        """
        # Extract domain as base directory
        parsed_url = urlparse(self.url)
        domain = parsed_url.netloc
        if domain.startswith('www.'):
            domain = domain[4:]
        
        # Use the first part of the domain (e.g., 'pinterest' from 'pinterest.com')
        base_dir = self._sanitize_directory_name(domain.split('.')[0])
        
        # Create content-specific directory from path components
        path = parsed_url.path.strip('/')
        if path:
            path_components = [self._sanitize_directory_name(p) for p in path.split('/') if p]
            if path_components:
                content_specific_dir = os.path.join(*path_components[:3])  # Limit depth to 3
            else:
                content_specific_dir = "general"
        else:
            content_specific_dir = "general"
        
        return (base_dir, content_specific_dir)
        
    def _sanitize_directory_name(self, name):
        """
        Sanitize a string to be used as a directory or file name component.
        """
        if not name:
            return "default"
            
        # Replace spaces with underscores
        sanitized = name.replace(' ', '_')
        
        # Remove invalid characters for directory names
        sanitized = re.sub(r'[<>:"/\\|?*]', '_', sanitized)
        
        # Collapse multiple underscores
        sanitized = re.sub(r'_+', '_', sanitized)
        
        # Remove leading/trailing underscores
        sanitized = sanitized.strip('_')

        # Limit length (optional, adjust as needed)
        max_len = 50 
        if len(sanitized) > max_len:
            sanitized = sanitized[:max_len]
            
        # Ensure it's not empty after sanitization
        if not sanitized:
            return "default"

        return sanitized.lower()  # Return lowercase for consistency

    def _load_api_credentials(self):
        """
        Loads API credentials from the scraper's auth_data based on the site's domain.
        Dynamically sets attributes on the handler instance for all found key-value pairs.
        """
        # --- START DEBUG PRINTS ---
        print(f"--- DEBUG: _load_api_credentials called for {self.__class__.__name__} ---")
        self.api_available = False # Default to False

        if not hasattr(self, 'scraper') or self.scraper is None:
            print("  DEBUG: No scraper instance available")
            return False
            
        if not hasattr(self.scraper, 'auth_config') or not self.scraper.auth_config:
            print("  DEBUG: No auth_config found in scraper")
            return False

        # Get auth configuration and check for valid structure
        auth_config = self.scraper.auth_config
        if not isinstance(auth_config, dict) or not auth_config.get('sites'):
            print("  DEBUG: Invalid auth_config structure")
            return False
            
        auth_data = auth_config.get('sites', {})
        if not auth_data:
            print("  DEBUG: Empty sites data in auth_config")
            return False

        print(f"  DEBUG: Looking for credentials for domain: {self.domain}")
        
        # Try to find credentials for this domain or its parent domain
        domain_key = self._get_domain_key()
        if not domain_key or domain_key not in auth_data:
            print(f"  DEBUG: No credentials found for domain: {domain_key}")
            return False
            
        # Get credentials and set as attributes
        credentials = auth_data[domain_key]
        print(f"  DEBUG: Found credentials for {domain_key}: {list(credentials.keys())}")
        
        for key, value in credentials.items():
            setattr(self, key, value)
            
        # Set API availability flag
        api_keys_found = any(key for key in credentials.keys() if 'key' in key.lower() or 'token' in key.lower())
        self.api_available = api_keys_found
        
        print(f"  DEBUG: API available: {self.api_available}")
        return True
    def is_cdn_domain(self, domain: str) -> bool:
        """
        Check if a domain is likely a CDN.
        
        Args:
            domain (str): Domain to check
            
        Returns:
            bool: True if the domain appears to be a CDN
        """
        cdn_indicators = [
            'cloudfront.net',
            'cloudflare.com',
            'akamaihd.net',
            'akamaiedge.net',
            'fastly.net',
            'googleapis.com',
            'gstatic.com',
            'cdninstagram.com',
            'twimg.com',
            'imgix.net',
            'cdn.',
            'static.',
            'assets.',
            'media.',
            'content.',
            'images.'
        ]
        
        return any(indicator in domain.lower() for indicator in cdn_indicators)

    def get_domain_from_url(self, url: str) -> str:
        """
        Get normalized domain from URL.
        
        Args:
            url (str): URL to extract domain from
            
        Returns:
            str: Normalized domain
        """
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            
            # Remove www. prefix if present
            if domain.startswith('www.'):
                domain = domain[4:]
                
            return domain
        except Exception:
            return ""


    def is_trusted_domain(self, url: str) -> bool:
        """
        Check if a URL's domain is trusted.
        
        Args:
            url (str): URL to check
            
        Returns:
            bool: True if domain is trusted
        """
        # Get domain from URL
        domain = self.get_domain_from_url(url)
        if not domain:
            return False
            
        # Check if domain matches a trusted domain
        trusted_domains = self.get_trusted_domains()
        if any(trusted_domain in domain for trusted_domain in trusted_domains):
            return True
            
        # Also check if it's a CDN domain
        return self.is_cdn_domain(domain)

    def get_trusted_domains(self) -> list:
        """
        Return a list of domains that should be considered 'trusted' and allowed
        even when same_domain_only is enabled.
        
        Override this method in site-specific handlers to add trusted domains.
        """
        return []


    def get_highest_resolution_url(self, url: str) -> str:
        """
        Try to get the highest resolution version of an image URL.
        
        Args:
            url (str): Original image URL
            
        Returns:
            str: Highest resolution URL, or original if no higher found
        """
        try:
            # Check for common resolution patterns in URLs
            dim_match = re.search(r'[_-](\d+)x(\d+)', url)
            if dim_match:
                width = int(dim_match.group(1))
                height = int(dim_match.group(2))
                
                # If dimensions are already large, return as is
                if width >= 1200 or height >= 1200:
                    return url
                    
                # Try to create higher resolution URL
                prefix = url[:dim_match.start()]
                suffix = url[dim_match.end():]
                
                # Determine new dimensions preserving aspect ratio
                aspect_ratio = width / height
                if aspect_ratio > 1:  # Landscape
                    new_width = 1200
                    new_height = int(new_width / aspect_ratio)
                else:  # Portrait or square
                    new_height = 1200
                    new_width = int(new_height * aspect_ratio)
                    
                # Create new URL
                seperator = url[dim_match.start()]  # Keep original separator (- or _)
                return f"{prefix}{seperator}{new_width}x{new_height}{suffix}"
            
            # Check for width/height parameters in query string
            query_match = re.search(r'[?&](w|width)=(\d+).*?[?&](h|height)=(\d+)', url)
            if query_match:
                width = int(query_match.group(2))
                height = int(query_match.group(4))
                
                if width >= 1200 or height >= 1200:
                    return url
                    
                # Replace with higher values
                aspect_ratio = width / height
                if aspect_ratio > 1:
                    new_width = 1200
                    new_height = int(new_width / aspect_ratio)
                else:
                    new_height = 1200
                    new_width = int(new_height * aspect_ratio)
                    
                # Create new URL with replaced parameters
                new_url = re.sub(
                    r'([?&])(w|width)=(\d+)', 
                    f'\\1\\2={new_width}', 
                    url
                )
                new_url = re.sub(
                    r'([?&])(h|height)=(\d+)', 
                    f'\\1\\2={new_height}', 
                    new_url
                )
                return new_url
            
            return url
        except Exception:
            return url


    async def extract_cdn_images(self, page, base_url: str) -> List[Dict]:
        """
        Extract images specifically from CDN domains.
        
        Args:
            page: Playwright page
            base_url: Original base URL
            
        Returns:
            List[Dict]: List of media items
        """
        media_items = []
        
        try:
            # Get all image sources
            cdn_urls = await page.evaluate("""
                () => {
                    const urls = [];
                    const processedUrls = new Set();
                    
                    // Function to add URL if unique
                    const addUrl = (url) => {
                        if (!processedUrls.has(url)) {
                            processedUrls.add(url);
                            urls.push(url);
                        }
                    };
                    
                    // 1. Direct image sources
                    document.querySelectorAll('img').forEach(img => {
                        if (img.src && !img.src.startsWith('data:')) {
                            addUrl(img.src);
                        }
                        
                        if (img.srcset) {
                            const srcset = img.srcset.split(',');
                            for (const src of srcset) {
                                const parts = src.trim().split(' ');
                                if (parts[0] && !parts[0].startsWith('data:')) {
                                    addUrl(parts[0]);
                                }
                            }
                        }
                    });
                    
                    // 2. Background images
                    document.querySelectorAll('*').forEach(el => {
                        try {
                            const style = window.getComputedStyle(el);
                            if (style.backgroundImage && style.backgroundImage !== 'none') {
                                const match = style.backgroundImage.match(/url\\(['"]?(.*?)['"]?\\)/);
                                if (match && match[1] && !match[1].startsWith('data:')) {
                                    addUrl(match[1]);
                                }
                            }
                        } catch (e) {}
                    });
                    
                    // 3. Find in scripts
                    document.querySelectorAll('script').forEach(script => {
                        if (script.textContent) {
                            const imgRegex = /(https?:\\/\\/[^\\s'")]*\\.(jpg|jpeg|png|webp|gif))/g;
                            const matches = script.textContent.match(imgRegex);
                            if (matches) {
                                matches.forEach(url => addUrl(url));
                            }
                        }
                    });
                    
                    return Array.from(processedUrls);
                }
            """)
            
            # Filter to keep only CDN URLs
            for url in cdn_urls:
                domain = self.get_domain_from_url(url)
                if self.is_cdn_domain(domain):
                    # Try to extract dimensions from filename
                    width = height = 0
                    dim_match = re.search(r'(\d+)x(\d+)', url)
                    if dim_match:
                        width = int(dim_match.group(1))
                        height = int(dim_match.group(2))
                    
                    # Create media item
                    media_items.append({
                        'url': url,
                        'type': 'image',
                        'title': f"Image from {self.domain}",
                        'width': width,
                        'height': height,
                        'trusted_cdn': True,
                        'source_url': base_url
                    })
            
            return media_items
            
        except Exception as e:
            print(f"Error extracting CDN images: {e}")
            return []


    def _get_domain_key(self) -> Optional[str]:
        """Find the matching domain key in auth_config."""
        if not self.domain:
            return None
            
        # Try exact domain match
        if hasattr(self, 'scraper') and self.scraper and hasattr(self.scraper, 'auth_config'):
            auth_config = self.scraper.auth_config
            if isinstance(auth_config, dict) and 'sites' in auth_config:
                # Direct match
                if self.domain in auth_config['sites']:
                    return self.domain
                    
                # Try without 'www' prefix
                if self.domain.startswith('www.') and self.domain[4:] in auth_config['sites']:
                    return self.domain[4:]
                    
                # Try parent domain (for subdomains)
                parts = self.domain.split('.')
                if len(parts) > 2:
                    parent_domain = '.'.join(parts[-2:])
                    if parent_domain in auth_config['sites']:
                        return parent_domain
        
        # Default to returning the domain itself even if not found
        return self.domain

    def parse_srcset(self, srcset: str) -> Optional[str]:
        """
        Given a srcset string, returns the URL of the highest resolution image.
        """
        if not srcset:
            return None
        try:
            candidates = [item.strip().split() for item in srcset.split(',') if item.strip()]
            sorted_candidates = sorted(
                ((url, int(width[:-1])) for url, width in candidates if width.endswith('w')),
                key=lambda x: x[1], reverse=True
            )
            return sorted_candidates[0][0] if sorted_candidates else None
        except Exception as e:
            print(f"Error parsing srcset: {e}")
            return None

    def merge_fields(self, *fields, default="Untitled"):
        """
        Return the first non-empty field in order.
        """
        return next((f for f in fields if f and isinstance(f, str) and f.strip()), default)

    async def _safe_get_text(self, locator, timeout=1000) -> str:
        """
        Returns the inner text of a locator with a timeout, safe fallback.
        Async version for compatibility.
        """
        try:
            if locator and await locator.is_visible(timeout=timeout):
                return await locator.inner_text(timeout=timeout)
        except Exception:
            return ""
        return ""