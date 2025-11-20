"""
Behance Handler

Description: ComfyUI custom node for downloading and scraping media from websites
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
Behance-specific handler for the Web Image Scraper
Handles project pages, user profiles, collections and search results.
"""

from site_handlers.base_handler import BaseSiteHandler
from urllib.parse import urljoin, urlparse, parse_qs
from typing import List, Dict, Any, Optional, Union
import os
import json
import re
import time
import traceback
import requests

# Try importing Playwright types safely
try:
    from playwright.async_api import Page as AsyncPage
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    AsyncPage = None
    PLAYWRIGHT_AVAILABLE = False

class BehanceHandler(BaseSiteHandler):
    """
    Handler for Behance.net, a platform for creative professionals.
    """

    @classmethod
    def can_handle(cls, url):
        """Check if this handler can process the URL"""
        return "behance.net" in url.lower()

    def __init__(self, url, scraper=None):
        """Initialize with Behance-specific properties"""
        super().__init__(url, scraper)
        self.username = None
        self.project_id = None
        self.collection_id = None
        self.page_type = self._determine_page_type(url)
        self.debug_mode = getattr(scraper, 'debug_mode', False)
        self._extract_identifiers_from_url()
        if self.debug_mode:
            print(f"BehanceHandler initialized for URL: {url}, Page Type: {self.page_type}")

    def _determine_page_type(self, url):
        """Determine what type of Behance page we're dealing with"""
        parsed_url = urlparse(url)
        path = parsed_url.path.strip('/')
        if not path: return "home"
        path_parts = path.split('/')
        if path.startswith('gallery/'): return "project"
        if path.startswith('search'): return "search"
        if path.startswith('collection/'): return "collection"
        if len(path_parts) == 1: return "profile"
        if len(path_parts) == 2 and path_parts[1] == "projects": return "profile_projects"
        if len(path_parts) == 2 and path_parts[1] == "appreciated": return "profile_appreciated"
        return "other"

    def _extract_identifiers_from_url(self):
        """Extract username, project ID, etc. from the URL"""
        parsed_url = urlparse(self.url)
        path = parsed_url.path.strip('/')
        path_parts = path.split('/')
        try:
            if self.page_type in ["profile", "profile_projects", "profile_appreciated"]:
                self.username = path_parts[0]
            elif self.page_type == "project" and path.startswith('gallery/'):
                self.project_id = next((part for part in path_parts if part.isdigit()), None)
            elif self.page_type == "collection" and path.startswith('collection/'):
                self.collection_id = next((part for part in path_parts if part.isdigit()), None)
        except IndexError:
             if self.debug_mode: print("IndexError during identifier extraction from URL path.")
        if self.debug_mode:
            print(f"  Extracted Identifiers: username={self.username}, project_id={self.project_id}, collection_id={self.collection_id}")


    def get_content_directory(self):
        """Generate Behance-specific directory structure."""
        base_dir = "behance"
        content_parts = []
        username_sanitized = self._sanitize_directory_name(self.username) if self.username else None

        if self.page_type in ["profile", "profile_projects"]:
            content_parts.extend(["user", username_sanitized or "unknown_user"])
            if self.page_type == "profile_projects": content_parts.append("projects")
        elif self.page_type == "profile_appreciated":
            content_parts.extend(["user", username_sanitized or "unknown_user", "appreciated"])
        elif self.page_type == "project":
            content_parts.extend(["project", self.project_id or "unknown_project"])
        elif self.page_type == "collection":
            content_parts.extend(["collection", self.collection_id or "unknown_collection"])
        elif self.page_type == "search":
            query = parse_qs(urlparse(self.url).query).get('search', ['general'])[0]
            content_parts.extend(["search", self._sanitize_directory_name(query)])
        elif self.page_type == "collection":
            content_parts.extend(["collection", self.collection_id or "unknown_collection"])

        else:
            path_components = [self._sanitize_directory_name(p) for p in urlparse(self.url).path.strip('/').split('/') if p]
            content_parts.extend(path_components[:2] if path_components else ["general"])

        content_specific_dir = os.path.join(*[p for p in content_parts if p]) # Filter out None/empty parts
        if not content_specific_dir: content_specific_dir = "general" # Ensure it's never empty

        return (base_dir, content_specific_dir)

    # --- Strategy Methods ---

    def prefers_api(self) -> bool:
        """Behance handler does not currently use a public API for this."""
        if self.debug_mode: print("BehanceHandler prefers_api check: False")
        return False

    async def extract_api_data_async(self, **kwargs) -> list:
        """API extraction is not implemented for Behance."""
        print(f"Warning: {self.__class__.__name__} does not implement API extraction.")
        return []

    async def extract_with_direct_playwright_async(self, page: AsyncPage, **kwargs) -> list:
        """Extract media using direct Playwright."""
        print(f"BehanceHandler: Extracting via Direct Playwright for page type: {self.page_type}")
        # Add a debug check to ensure page is valid
        if not page:
            print("ERROR: Page object is None, cannot extract content")
            return []
        media_items = []
        
        try:
            # Add a short delay to ensure page is fully loaded
            print("  Adding short delay before waiting for selector...")
            await page.wait_for_timeout(2000)  # Wait 2 seconds
            
            # Different selectors for different page types
            if self.page_type == "project":
                # Try multiple selectors for project pages
                selectors = [
                    'div.Project-projectModuleContainer img',
                    '.js-project-modules img',
                    '.project-content img'
                ]
                
                for selector in selectors:
                    try:
                        count = await page.locator(selector).count()
                        if count > 0:
                            print(f"  Found matching selector: '{selector}'")
                            image_elements = page.locator(selector)
                            break
                    except:
                        continue
                else:
                    # If no selector worked, try a more generic approach
                    print("  No specific selectors matched, trying generic image selector")
                    image_elements = page.locator('img[src*="behance.net"]:not([width="16"]):not([width="24"]):not([width="32"])')
                    
            elif self.page_type in ["search", "gallery", "user", "appreciated"]:
                # Try multiple selectors for galleries, search results, etc.
                selectors = [
                    'div.ProjectCoverNeue-root img',  # Original selector
                    '.Cover-content img',             # Alternative selector
                    '.ProjectCoverNeue img',          # Another alternative
                    '.search-content img[src*="behance.net"]',  # More generic search selector
                    '.e2e-ProjectCoverNeue img'       # Another possible selector
                ]
                
                for selector in selectors:
                    try:
                        print(f"  Trying selector: '{selector}'")
                        count = await page.locator(selector).count()
                        if count > 0:
                            print(f"  Found {count} elements with selector: '{selector}'")
                            image_elements = page.locator(selector)
                            break
                    except Exception as e:
                        print(f"  Error with selector '{selector}': {e}")
                        continue
                else:
                    # If no selector worked, try a very generic approach
                    print("  No specific selectors matched, trying generic image selector")
                    image_elements = page.locator('img[src*="behance.net"]:not([width="16"]):not([width="24"]):not([width="32"])')
            else:
                # Generic approach for other page types
                image_elements = page.locator('img[src*="behance.net"]:not([width="16"]):not([width="24"]):not([width="32"])')
            
            # Extract images from the chosen selector
            count = await image_elements.count() if 'image_elements' in locals() else 0
            
            if count == 0:
                print("  No images found with any selector")
                
                # Try taking a screenshot for debugging
                if getattr(self, 'debug_mode', False):
                    try:
                        debug_dir = os.path.dirname(page.url.replace(':', '_').replace('/', '_'))
                        os.makedirs(debug_dir, exist_ok=True)
                        await page.screenshot(path=os.path.join(debug_dir, "behance_debug.png"))
                        print(f"  Saved debug screenshot to {debug_dir}")
                    except:
                        pass
                        
                # Try one last generic approach - get all substantial images
                image_elements = page.locator('img:not([width="16"]):not([width="24"]):not([width="32"])')
                count = await image_elements.count()
                if count == 0:
                    return []
            
            print(f"  Processing {count} image elements")
            
            for i in range(count):
                try:
                    img = image_elements.nth(i)
                    
                    # Skip if not visible
                    is_visible = await img.is_visible(timeout=300)
                    if not is_visible:
                        continue
                    
                    # Get image URL (try multiple attributes)
                    src = await img.get_attribute("src")
                    srcset = await img.get_attribute("srcset")
                    data_src = await img.get_attribute("data-src")
                    
                    # Use the best available source
                    image_url = None
                    if srcset:
                        image_url = self._get_highest_res_image(src, srcset)
                    elif data_src and "placeholder" not in data_src:
                        image_url = data_src
                    elif src and "placeholder" not in src:
                        image_url = src
                    
                    if not image_url or image_url.startswith('data:'):
                        continue
                    
                    # Upgrade to highest quality version if possible
                    image_url = self._upgrade_behance_url(image_url)
                    
                    # Get additional metadata
                    try:
                        alt = await img.get_attribute("alt") or ""
                        title = await img.get_attribute("title") or ""
                        
                        # Look for project title - different selectors depending on page type
                        project_title = ""
                        if self.page_type == "project":
                            try:
                                project_title_element = page.locator('.project-title').first
                                project_title = await project_title_element.text_content() if await project_title_element.is_visible(timeout=500) else ""
                                project_title = project_title.strip()
                            except:
                                pass
                        elif self.page_type in ["search", "gallery"]:
                            try:
                                # Try to find the surrounding project card and get its title
                                project_card = img.locator("xpath=ancestor::div[contains(@class, 'ProjectCoverNeue') or contains(@class, 'Cover')]").first
                                if await project_card.is_visible(timeout=500):
                                    title_elem = project_card.locator('.Title, .title, [class*="title"]').first
                                    if await title_elem.is_visible(timeout=500):
                                        project_title = await title_elem.text_content()
                                        project_title = project_title.strip()
                            except:
                                pass
                    except:
                        alt = ""
                        title = ""
                        project_title = ""
                    
                    # Create item with the metadata we have
                    final_title = project_title or title or alt or f"Behance image from {self.page_type}"
                    
                    media_items.append({
                        'url': image_url,
                        'type': 'image',
                        'title': final_title,
                        'alt': alt,
                        'source_url': page.url,
                        'platform': 'behance',
                        'page_type': self.page_type
                    })
                
                except Exception as e:
                    print(f"  Error extracting image {i}: {e}")
                    continue
            
            print(f"  Extracted {len(media_items)} media items from Behance")
            return media_items
                
        except Exception as e:
            print(f"BehanceHandler: Error during Direct Playwright extraction: {e}")
            import traceback
            traceback.print_exc()
            return []

    async def extract_with_scrapling(self, response, **kwargs) -> list:
        """Extract media using Scrapling response (HTML fallback)."""
        print("BehanceHandler: Attempting extraction via Scrapling (HTML Fallback)...")
        self.start_time = time.time()

        html_content = self._get_page_content_from_response(response) # Get HTML from response
        if not html_content:
            print("BehanceHandler: No HTML content found in Scrapling response.")
            return []

        media_items = []
        json_data = self._extract_json_from_html(html_content)
        if json_data:
            if self.page_type == "project":
                media_items = self._parse_project_json(json_data, **kwargs)
            elif self.page_type in ["profile", "profile_projects", "profile_appreciated", "search", "collection"]:
                 media_items = self._parse_gallery_json(json_data, **kwargs)

        if not media_items:
             print("BehanceHandler: JSON extraction failed or not applicable, falling back to HTML regex.")
             media_items = self._extract_generic_images_html(html_content, **kwargs)

        print(f"BehanceHandler: Scrapling extraction found {len(media_items)} items.")
        return await self.post_process(media_items) # Apply post-processing

    # --- Internal Helper Methods ---

    async def _extract_project_images(self, page: AsyncPage, **kwargs) -> list:
        """Extract images from a project page using Playwright."""
        media_items = []
        try:
            await page.wait_for_selector('.project-module', timeout=15000) # Generic module selector

            project_title_elem = page.locator('h1.ProjectHeader-title').first
            project_title = await project_title_elem.text_content(timeout=5000) if await project_title_elem.is_visible(timeout=5000) else "Untitled Project"
            
            project_owner_elem = page.locator('.ProjectHeader-ownerList a').first
            project_owner = await project_owner_elem.text_content(timeout=5000) if await project_owner_elem.is_visible(timeout=5000) else "Unknown Owner"
            
            if self.debug_mode: print(f"  Project Title: {project_title}, Owner: {project_owner}")

            image_elements_locator = page.locator('.project-module-image img, .ImageElement-imageContainer img')
            image_count = await image_elements_locator.count()
            if self.debug_mode: print(f"  Found {image_count} potential image elements.")

            for idx in range(image_count):
                img_element = image_elements_locator.nth(idx)
                src = await img_element.get_attribute('src')
                srcset = await img_element.get_attribute('srcset')
                image_url = self.parse_srcset(srcset) or src

                alt = await img_element.get_attribute('alt') or ""
                title_attr = await img_element.get_attribute('title') or ""

                try:
                    module = img_element.locator('xpath=ancestor::*[contains(@class, "project-module")]').first
                    caption_elem = module.locator('.project-module-caption, .Caption-root')
                    caption = await self._safe_get_text(caption_elem)
                except Exception:
                    caption = ""

                image_title = self.merge_fields(caption, alt, title_attr, f"{project_title} - Image {idx+1}")

                media_items.append({
                    'url': image_url,
                    'alt': alt.strip() or image_title,
                    'title': image_title,
                    'source_url': self.url,
                    'credits': project_owner,
                    'type': 'image',
                    'category': 'project_image'
                })
        except Exception as e:
            print(f"  Error extracting project images with Playwright: {e}")
            traceback.print_exc()

        print(f"  _extract_project_images found {len(media_items)} items.")
        return await self.post_process(media_items) # Apply post-processing

    async def _extract_gallery_images(self, page: AsyncPage, **kwargs) -> list:
        """Extract images from gallery-style pages using Playwright."""
        media_items = []
        try:
            correct_selector = "div.ProjectCoverNeue-root"

            # --- Add small delay ---
            print("  Adding short delay before waiting for selector...")
            await page.wait_for_timeout(1500) # Wait 1.5 seconds
            # --- End delay ---

            # Wait for project covers to load
            print(f"  Waiting for selector: '{correct_selector}'")
            await page.wait_for_selector(correct_selector, timeout=30000)
            
            # Extract all project cards using Playwright
            project_cards_locator = page.locator(correct_selector)
            card_count = await project_cards_locator.count()
            if self.debug_mode: print(f"  Found {card_count} potential project cards using '{correct_selector}'.")

            if self.page_type in ["profile_projects", "collection"]:
                print(f"  Special handling for page type: {self.page_type}")
            if self.page_type == "profile_appreciated":
                print("  Special handling for appreciated projects page.")
                
            for i in range(card_count):
                card = project_cards_locator.nth(i)
                img_element = card.locator('img').first
                
                # Check if image element exists and is visible
                if not await img_element.is_visible(timeout=500):
                    continue
                    
                src = await img_element.get_attribute('src')
                srcset = await img_element.get_attribute('srcset') 
                image_url = self.parse_srcset(srcset) or src

                title_element = card.locator('.ProjectCoverNeue-title, .Title, .title, [class*="title"]').first
                title = await self._safe_get_text(title_element)
                
                alt = await img_element.get_attribute('alt')
                aria_label = await img_element.get_attribute('aria-label')
                img_title = await img_element.get_attribute('title')

                caption_text = ""
                try:
                    module = img_element.locator('xpath=ancestor::*[contains(@class, "ProjectCoverNeue-root")]').first
                    caption_element = module.locator('figcaption')
                    caption_text = await self._safe_get_text(caption_element)
                except Exception:
                    pass

                final_title = self.merge_fields(title, caption_text, aria_label, img_title, alt, "Behance Image")
                
                owner_element = card.locator('.ProjectCoverNeue-owner, .Cover-owner, .owner, [class*="owner"]').first
                owner = await self._safe_get_text(owner_element)
                
                # Get link to full project if available
                href = await card.get_attribute('href')

                # Optional: Navigate into the full project page and extract more
                if href:
                    try:
                        await page.goto(urljoin(self.url, href), timeout=15000)
                        await page.wait_for_selector(".project-module", timeout=5000)
                        project_images = await self._extract_project_images(page, **kwargs)
                        media_items.extend(project_images)
                        continue  # Skip thumbnail if we got detail images
                    except Exception as e:
                        print(f"  Failed to extract project at {href}: {e}")
                        # fallback to thumbnail below if needed

                media_items.append({
                    'url': image_url,
                    'alt': alt or final_title,
                    'title': final_title,
                    'source_url': urljoin(self.url, href) if href else self.url,
                    'credits': owner,
                    'type': 'image',
                    'category': 'thumbnail'
                })
        except Exception as e:
            print(f"  Error extracting gallery images with Playwright: {e}")
            if "Timeout" in str(e):
                 print(f"  Timeout likely occurred waiting for or interacting with elements matching '{correct_selector}'.")
                 print(f"  Verify the selector is correct and the page content (including project cards) is fully loaded.")
                 print(f"  NOTE: The earlier 'Execution context was destroyed' error during scrolling is the most likely cause, preventing content from loading correctly.")
            traceback.print_exc()

        print(f"  _extract_gallery_images found {len(media_items)} items.")
        return await self.post_process(media_items) # Apply post-processing

    async def _extract_generic_images_pw(self, page: AsyncPage, **kwargs) -> list:
        """Generic extraction for any Behance page type using Playwright."""
        media_items = []
        print("  Running generic Playwright image extraction for Behance...")
        try:
            image_elements_locator = page.locator('img')
            image_count = await image_elements_locator.count()
            seen_urls = set()

            for i in range(image_count):
                img_element = image_elements_locator.nth(i)
                src = await img_element.get_attribute('src')
                srcset = await img_element.get_attribute('srcset')
                alt = await img_element.get_attribute('alt') or ''

                image_url = self._get_highest_res_image(src, srcset)

                if not image_url or 'spacer.gif' in image_url or not 'behance.net' in image_url:
                    continue

                clean_url = image_url.split('?')[0].split('#')[0]
                if clean_url in seen_urls:
                    continue
                seen_urls.add(clean_url)

                try:
                     bounding_box = await img_element.bounding_box(timeout=500)
                     if bounding_box and (bounding_box['width'] < 100 or bounding_box['height'] < 100):
                          if self.debug_mode: print(f"    Skipping likely small/icon image: {clean_url}")
                          continue
                except Exception:
                     pass

                media_items.append({
                    'url': clean_url,
                    'alt': alt.strip() or "Behance Image",
                    'title': alt.strip() or "Behance Image",
                    'source_url': self.url,
                    'credits': "Behance",
                    'type': 'image',
                    'category': 'generic_pw'
                })
        except Exception as e:
            print(f"  Error during generic Playwright extraction: {e}")
            traceback.print_exc()

        print(f"  _extract_generic_images_pw found {len(media_items)} items.")
        return await self.post_process(media_items)

    def _get_page_content_from_response(self, response) -> str:
        """Get HTML content from a Scrapling response object."""
        try:
            if hasattr(response, 'text'):
                return response.text
            elif hasattr(response, 'content'):
                 return response.content.decode('utf-8', errors='ignore')
        except Exception as e:
            if self.debug_mode: print(f"Error getting content from response: {e}")
        return ""

    def _extract_json_from_html(self, html_content: str) -> Optional[Dict]:
        """Extracts the __INITIAL_STATE__ JSON embedded in Behance HTML."""
        if not html_content: return None
        json_data_match = re.search(r'window\.__INITIAL_STATE__\s*=\s*(\{.*\});?\s*</script>', html_content, re.DOTALL)
        if json_data_match:
            try:
                json_text = json_data_match.group(1)
                json_data = json.loads(json_text)
                if self.debug_mode: print("  Successfully extracted __INITIAL_STATE__ JSON from HTML.")
                return json_data
            except json.JSONDecodeError as e:
                if self.debug_mode: print(f"  Error decoding __INITIAL_STATE__ JSON: {e}")
            except Exception as e:
                 if self.debug_mode: print(f"  Unexpected error processing __INITIAL_STATE__ JSON: {e}")
        else:
             if self.debug_mode: print("  __INITIAL_STATE__ JSON not found in HTML.")
        return None

    def _parse_project_json(self, json_data: Dict, **kwargs) -> list:
        """Parses project media items from the __INITIAL_STATE__ JSON."""
        media_items = []
        if not json_data: return media_items
        if self.debug_mode: print("  Parsing project JSON...")

        try:
            project_info = json_data.get('project', {}).get('project', {})
            project_title = project_info.get('name', "Untitled Project")
            project_owner = "Unknown Owner"
            owners = project_info.get('owners', [])
            if owners and isinstance(owners, list):
                project_owner = owners[0].get('display_name', project_owner)

            modules = project_info.get('modules', [])
            for idx, module in enumerate(modules):
                if isinstance(module, dict) and module.get('type') == 'image':
                    image_url = ""
                    sizes = module.get('sizes', {})
                    if isinstance(sizes, dict):
                         for size_key in ['original', 'max_1920', 'max_1200', 'max_1024', '1400', 'source']:
                              if size_key in sizes and sizes[size_key]:
                                   image_url = sizes[size_key]
                                   break
                    if not image_url:
                         image_url = module.get('src')

                    if not image_url or 'spacer.gif' in image_url:
                        continue

                    caption = module.get('caption_plain', module.get('caption', ''))
                    alt = module.get('alt', '')
                    image_title = caption.strip() or f"{project_title} - Image {idx+1}"

                    media_items.append({
                        'url': image_url,
                        'alt': alt.strip() or image_title,
                        'title': image_title.strip(),
                        'source_url': self.url,
                        'credits': project_owner,
                        'type': 'image',
                        'category': 'project_image_json'
                    })
        except Exception as e:
            print(f"  Error parsing project JSON: {e}")
            traceback.print_exc()

        return media_items

    def _parse_gallery_json(self, json_data: Dict, **kwargs) -> list:
        """Parses gallery/thumbnail media items from the __INITIAL_STATE__ JSON."""
        media_items = []
        if not json_data: return media_items
        if self.debug_mode: print("  Parsing gallery JSON...")

        try:
            projects_data = json_data.get('profile', {}).get('projects', {}).get('projects') \
                         or json_data.get('search', {}).get('projects', {}).get('projects') \
                         or json_data.get('collection', {}).get('projects', {}).get('projects') \
                         or json_data.get('appreciate', {}).get('projects', {}).get('projects')

            if not projects_data or not isinstance(projects_data, dict):
                 if self.debug_mode: print("  Projects data not found or not in expected format in JSON.")
                 return media_items

            for project_id, project in projects_data.items():
                if not isinstance(project, dict): continue

                covers = project.get('covers', {})
                image_url = ""
                for size in ["original", "808", "404", "202", "115", "source"]:
                    if size in covers and covers[size]:
                        image_url = covers[size]
                        break

                if not image_url or 'spacer.gif' in image_url:
                    continue

                title = project.get('name', "Behance Project")
                owner = "Unknown Owner"
                owners = project.get('owners', [])
                if owners and isinstance(owners, list):
                    owner = owners[0].get('display_name', owner)

                project_slug = self._sanitize_directory_name(title.lower().replace(' ', '-'))[:50]
                project_url = f"https://www.behance.net/gallery/{project_id}/{project_slug}"

                media_items.append({
                    'url': image_url,
                    'alt': title.strip(),
                    'title': title.strip(),
                    'source_url': project_url,
                    'credits': owner.strip(),
                    'type': 'image',
                    'category': 'thumbnail_json'
                })
        except Exception as e:
            print(f"  Error parsing gallery JSON: {e}")
            traceback.print_exc()

        return media_items

    def _extract_generic_images_html(self, html_content: str, **kwargs) -> list:
        """Generic extraction for any Behance page type using HTML regex."""
        media_items = []
        if not html_content: return media_items
        if self.debug_mode: print("  Running generic HTML regex image extraction for Behance...")

        img_pattern = r'(?:src|srcset)=["\']?([^"\'\s>]+(?:behance\.net)[^"\'\s>]+)["\']?'
        seen_urls = set()

        for match in re.finditer(img_pattern, html_content, re.IGNORECASE):
            url_match = match.group(1)
            possible_urls = url_match.replace('\\', '').split(',')
            for part in possible_urls:
                url = part.strip().split(' ')[0]

                if not url or 'spacer.gif' in url or not 'behance.net' in url:
                    continue

                clean_url = url.split('?')[0].split('#')[0]
                if clean_url in seen_urls:
                    continue

                if any(low_res in clean_url for low_res in ['/115/', '/202/', '/230/']):
                     high_res_url = self._get_highest_res_image(clean_url, '')
                     if high_res_url and high_res_url != clean_url:
                          clean_url = high_res_url
                          seen_urls.add(clean_url)

                media_items.append({
                    'url': clean_url,
                    'alt': "Behance Image",
                    'title': "Behance Image",
                    'source_url': self.url,
                    'credits': "Behance",
                    'type': 'image',
                    'category': 'generic_html'
                })

        return media_items

    def _get_highest_res_image(self, url, srcset):
        """Get the highest resolution image URL from src and srcset."""
        highest_res_url = url if url else ""

        if srcset:
            candidates = []
            for entry in srcset.split(','):
                parts = entry.strip().split()
                if len(parts) >= 1:
                    entry_url = parts[0]
                    width = 0
                    if len(parts) == 2:
                        descriptor = parts[1]
                        if 'w' in descriptor: width = int(descriptor.replace('w', ''))
                        elif 'x' in descriptor: width = int(float(descriptor.replace('x', '')) * 800)
                    candidates.append({'url': entry_url, 'width': width})

            if candidates:
                candidates.sort(key=lambda x: x['width'], reverse=True)
                best_candidate = next((c for c in candidates if c['width'] > 100), None)
                if best_candidate:
                     highest_res_url = best_candidate['url']
                     upgraded_srcset_url = self._upgrade_behance_url(highest_res_url)
                     if upgraded_srcset_url != highest_res_url and self.debug_mode:
                          print(f"  Upgraded srcset URL from {highest_res_url} to {upgraded_srcset_url}")
                     return upgraded_srcset_url

        if highest_res_url:
             upgraded_url = self._upgrade_behance_url(highest_res_url)
             if upgraded_url != highest_res_url and self.debug_mode:
                  print(f"  Upgraded src URL from {highest_res_url} to {upgraded_url}")
             return upgraded_url

        return None

    def _upgrade_behance_url(self, url):
         """Tries to replace resolution markers with 'source' or 'original'."""
         if not url: return url

         replacements = {
             '/115/': '/original/', '/202/': '/original/', '/230/': '/original/',
             '/404/': '/original/', '/808/': '/original/', '/1400/': '/original/',
             '/max_800/': '/source/', '/max_1200/': '/source/', '/max_1920/': '/source/'
         }
         url = re.sub(r'(/project_modules/(?:fs|disp|)/[^/]+)/\d+(/\d+)?/', r'\1/source/', url)
         url = re.sub(r'(/covers/)\d+(/\d+)?/', r'\1original/', url)
         url = re.sub(r'(/projects/)\d+(/\d+)?/', r'\1source/', url)

         for old, new in replacements.items():
             if old in url:
                 url = url.replace(old, new)
                 break

         return url

    async def post_process(self, media_items):
        """Clean and enhance the extracted media items."""
        processed_items = []
        seen_urls = set()

        for item in media_items:
            url = item.get('url')
            if not url: continue

            clean_url = url.split('?')[0].split('#')[0].strip()
            if not clean_url or clean_url in seen_urls:
                continue

            upgraded_url = self._upgrade_behance_url(clean_url)
            if upgraded_url in seen_urls: continue

            item['url'] = upgraded_url
            seen_urls.add(upgraded_url)

            credits = item.get('credits', '').strip()
            if credits and 'behance' not in credits.lower():
                 item['credits'] = f"{credits} on Behance"
            elif not credits:
                 item['credits'] = "Behance"

            processed_items.append(item)

        if self.debug_mode: print(f"Post-processing finished. Kept {len(processed_items)} unique items.")
        return processed_items