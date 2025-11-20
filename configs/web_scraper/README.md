# Web Scraper Authentication Configuration

This directory contains authentication configuration specifically for the **Web Image Scraper** node (Playwright-based browser automation).

## ⚠️ Important Note

This `auth_config.json` is **separate** from the main `download-tools/configs/auth_config.json` because:

1. **Different Tools**: Web Scraper uses Playwright for browser automation, while gallery-dl/yt-dlp use their own authentication systems
2. **Different Format**: Web Scraper supports full browser cookies, login automation steps, and interaction sequences
3. **No Conflicts**: Keeping them separate prevents configuration conflicts between the tools

## Configuration Format

The web scraper `auth_config.json` supports these authentication types:

### 1. Cookie Authentication
```json
{
  "sites": {
    "example.com": {
      "auth_type": "cookie",
      "domain": "example.com",
      "cookies": [
        {
          "name": "session_token",
          "value": "your_token_here",
          "domain": ".example.com",
          "path": "/",
          "secure": true,
          "httpOnly": true
        }
      ]
    }
  }
}
```

### 2. API Client Authentication
```json
{
  "sites": {
    "reddit.com": {
      "auth_type": "api_client",
      "domain": "reddit.com",
      "client_id": "your_client_id",
      "client_secret": "your_client_secret",
      "username": "your_username",
      "password": "your_password",
      "user_agent": "YourApp/1.0"
    }
  }
}
```

### 3. Login Form Authentication
```json
{
  "sites": {
    "example.com": {
      "auth_type": "login",
      "domain": "example.com",
      "username": "your_username",
      "password": "your_password",
      "login_steps": [
        {"type": "fill", "selector": "#username", "value": "{username}"},
        {"type": "fill", "selector": "#password", "value": "{password}"},
        {"type": "click", "selector": "button[type='submit']"},
        {"type": "wait", "value": "3000"}
      ]
    }
  }
}
```

### 4. Additional Configuration
```json
{
  "sites": {
    "example.com": {
      "timeout": 60000,
      "scroll_delay_ms": 1000,
      "max_scroll_count": 50,
      "wait_for_network_idle": true,
      "user_agent": "Mozilla/5.0 ..."
    }
  }
}
```

## How to Use

1. Copy `auth_config.json.example` to `auth_config.json`
2. Fill in your credentials for the sites you want to scrape
3. In the Web Image Scraper node, set the `auth_config_path` parameter to:
   - Leave empty to use default: `configs/web_scraper/auth_config.json`
   - Or provide full path to your custom config file

## Security Notes

- **Never commit** `auth_config.json` to version control
- The `.gitignore` file should exclude this file
- Store credentials securely
- Use API tokens instead of passwords when possible
- Consider using environment variables for sensitive data

## Supported Sites

The Web Scraper has specialized handlers for:
- Bluesky (bsky.app)
- Reddit
- Instagram
- Flickr
- Artsy
- DeviantArt
- Behance
- 500px
- Unsplash
- Google Arts & Culture
- WordPress sites
- YouTube
- And many more via the generic handler

## Troubleshooting

- **Cookies not working?** Export fresh cookies from your browser using a cookie extension
- **Login failing?** Check the login_steps selectors match the current website structure
- **API errors?** Verify your API credentials are current and have proper permissions

## Related Files

- `../auth_config.json` - For gallery-dl and yt-dlp authentication (separate system)
- `../../site_handlers/` - Site-specific extraction handlers
- `../../nodes/web_image_scraper_v082.py` - The Web Image Scraper node

---

*Last Updated: January 2025*
