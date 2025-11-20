# Web File Scraper Node (ComfyUI)

This node scrapes images, videos, and other media from web pages using Playwright and Scrapling, with advanced support for authentication, scrolling, and custom site interactions.

---

## Features

- Fetches images, videos, and audio from modern and classic web pages
- Handles JavaScript-heavy sites with Playwright
- Supports login/authentication and session reuse
- Customizable interaction sequences (JSON) for site-specific automation
- Screenshot support for full page or specific elements (CSS selectors)
- Metadata extraction and export
- Duplicate detection and filtering

---

## UI Fields: JSON Interaction Sequence & CSS Selectors

### 1. **Interaction Sequence (JSON)**

**Purpose:**  
Automate complex site interactions such as clicking, filling forms, navigating galleries, or paging through images.

**How to Use:**  
- Enter a JSON array describing each step.
- Each step is an object with a `type` (e.g., `click`, `fill`, `wait_for_selector`), a `selector`, and optional parameters.

**Supported Step Types:**
- `wait_for_selector`: Wait for an element to appear.
- `click`: Click an element.
- `fill`: Fill a form field.
- `press`: Press a key (e.g., Tab, Enter).
- `wait_for_timeout`: Wait for a specified time in milliseconds.

**Example: Paging Through a Gallery**
```json
[
    {"type": "wait_for_selector", "selector": ".gallery__item img"},
    {"type": "click", "selector": ".gallery__item img"},
    {"type": "wait_for_selector", "selector": ".pswp__img"},
    {"type": "click", "selector": ".pswp__button--arrow--next"},
    {"type": "wait_for_selector", "selector": ".pswp__img"},
    {"type": "click", "selector": ".pswp__button--arrow--next"},
    {"type": "wait_for_selector", "selector": ".pswp__img"}
    // ...repeat as needed for more images
]
```
> **Tip:** If your node does not support loops, repeat the click/wait pairs for as many images as you want to process.

**Example: Login Flow**
```json
[
    {"type": "wait_for_selector", "selector": "input[type='email']"},
    {"type": "fill", "selector": "input[type='email']", "value": "<USERNAME>"},
    {"type": "press", "selector": "input[type='email']", "key": "Tab"},
    {"type": "wait_for_selector", "selector": "input[type='password']"},
    {"type": "fill", "selector": "input[type='password']", "value": "<PASSWORD>"},
    {"type": "click", "selector": "button[type='submit']"},
    {"type": "wait_for_timeout", "timeout": 2000}
]
```
> `<USERNAME>` and `<PASSWORD>` will be replaced by your credentials if supported by the handler.

---

artsy.net example json to be pasted in the UI

[
    {"type": "wait_for_selector", "selector": "button:has-text('Agree'), button:has-text('Accept')", "timeout": 4000},
    {"type": "click", "selector": "button:has-text('Agree'), button:has-text('Accept')"},
    {"type": "wait_for_timeout", "timeout": 1000},
    {"type": "wait_for_selector", "selector": "button[aria-label='Close']", "timeout": 3000},
    {"type": "click", "selector": "button[aria-label='Close']"},
    {"type": "wait_for_timeout", "timeout": 1000},
    {"type": "scroll", "scroll_count": 10, "scroll_delay": 1000}
]

tumblr.com example json to be pasted in the UI
[
    {"type": "wait_for_selector", "selector": "button:has-text('Accept all')", "timeout": 4000},
    {"type": "click", "selector": "button:has-text('Accept all')"},
    {"type": "wait_for_selector", "selector": "button[aria-label='Close']", "timeout": 3000},
    {"type": "click", "selector": "button[aria-label='Close']"}
]

### 2. **Screenshot Elements (CSS Selectors)**

**Purpose:**  
Capture screenshots of specific elements on the page, rather than the whole page.

**How to Use:**  
- Enter one or more CSS selectors (one per line).
- The node will take a screenshot of each matching element after interactions.

**Example:**
```
.pswp__img
.main-image
#gallery
```

**Typical Use Cases:**
- Capture only the main image in a lightbox/gallery.
- Debug what a specific element looks like after interaction.
- Avoid capturing popups, ads, or overlays.

---

### 3. **Best Practices & Tips**

- **No "goto" step needed** if the node already loads the URL you enter.
- **Repeat click/wait steps** for galleries if your node does not support loops.
- **Inspect elements with F12** in your browser to find reliable selectors.
- **Enable `take_screenshot`** in the UI to activate screenshotting.
- **Use debug mode** to get extra logs and screenshots for troubleshooting.

---

## Example: Scraping a Gallery with Screenshots

**Site:** [https://www.veespeers.com/immortal](https://www.veespeers.com/immortal)

**Interaction Sequence:**
```json
[
    {"type": "wait_for_selector", "selector": ".gallery__item img"},
    {"type": "click", "selector": ".gallery__item img"},
    {"type": "wait_for_selector", "selector": ".pswp__img"},
    {"type": "click", "selector": ".pswp__button--arrow--next"},
    {"type": "wait_for_selector", "selector": ".pswp__img"},
    {"type": "click", "selector": ".pswp__button--arrow--next"},
    {"type": "wait_for_selector", "selector": ".pswp__img"}
    // ...repeat as needed
]
```

**Screenshot Elements (CSS):**
```
.pswp__img
```

---

## Troubleshooting

- If you see fewer images than expected, increase the number of click/wait pairs.
- If elements are not found, double-check your CSS selectors with browser DevTools.
- For login-required sites, ensure your credentials are set up in `auth_config.json` and referenced in your interaction sequence.

---

## Advanced

- You can combine scrolling, clicking, and filling forms in your interaction sequence.
- For sites with dynamic content, increase scroll depth and delays in the node options.

---

## Credits

Developed by EricWebFileScraper contributors.  
Powered by Playwright, Scrapling, and ComfyUI.

---

**For more help or to request features, open an issue or contact the maintainer.**