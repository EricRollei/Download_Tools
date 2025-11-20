"""
Site handlers package for Web Image Scraper (async version)
"""

from .base_handler import BaseSiteHandler

# Import async Playwright
try:
    from playwright.async_api import Page as AsyncPage, async_playwright
    PLAYWRIGHT_AVAILABLE = True
    print("Site handlers: Playwright (async) import succeeded")
except ImportError:
    AsyncPage = None
    async_playwright = None
    PLAYWRIGHT_AVAILABLE = False
    print("Site handlers: Playwright (async) import failed")

# Import Scrapling as fallback
try:
    from scrapling.fetchers import PlayWrightFetcher
    SCRAPLING_AVAILABLE = True
    print("Site handlers: Scrapling import succeeded")
    
    # Utility function to extract Playwright page from Scrapling
    async def get_playwright_page(page_adaptor):
        """Obtain the underlying async Playwright Page object from a Scrapling response."""
        if not PLAYWRIGHT_AVAILABLE:
            return None
        try:
            # Try different access patterns to get the page object
            if hasattr(page_adaptor, '_response') and hasattr(page_adaptor._response, 'page'):
                return page_adaptor._response.page
            elif hasattr(page_adaptor, '_page'):
                return page_adaptor._page
            elif hasattr(PlayWrightFetcher, '_last_pw_page'):
                return PlayWrightFetcher._last_pw_page
        except Exception as e:
            print(f"Error accessing async Playwright page: {e}")
        return None
    
    # Add the method to BaseSiteHandler
    BaseSiteHandler.get_playwright_page = get_playwright_page
    
except ImportError:
    PlayWrightFetcher = None
    SCRAPLING_AVAILABLE = False
    print("Site handlers: Scrapling import failed")