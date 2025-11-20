# Instagram Handler Documentation

## Overview

The Instagram Handler is a comprehensive scraper for Instagram content using the Instaloader library. It supports extracting images, videos, and metadata from Instagram profiles, posts, reels, stories, and hashtags.

## Features

### ✅ Supported Content Types

- **📸 Public Profiles**: Extract all posts and videos from public Instagram profiles
- **🎬 Individual Posts**: Download specific Instagram posts using their URLs
- **🎥 Reels**: Extract Instagram Reels content
- **#️⃣ Hashtag Exploration**: Download posts from hashtag pages
- **🏷️ Tagged Posts**: Extract posts where a user is tagged (requires login)
- **📱 Stories**: Download Instagram Stories (requires login)
- **🌟 Highlights**: Access saved story highlights (requires login)

### 🔧 Technical Features

- **🔐 Session-based Authentication**: Secure login using Instaloader sessions
- **⚡ Rate Limiting**: Built-in delays to avoid being blocked
- **🛡️ Anti-detection**: Uses realistic user agents and request patterns
- **📊 Rich Metadata**: Extracts likes, comments, captions, hashtags, mentions, location data
- **🎯 Smart URL Enhancement**: Handles various Instagram URL formats
- **📷 Multi-media Support**: Downloads both images and videos
- **🎠 Carousel Support**: Handles multi-image/video posts

## Installation

The Instagram handler requires the Instaloader library:

```bash
pip install instaloader
```

For the ComfyUI environment:
```bash
A:/Comfy25/ComfyUI_windows_portable/python_embeded/python.exe -m pip install instaloader
```

## Configuration

### Basic Setup (Public Content Only)

For extracting public content, no authentication is required. Just provide Instagram URLs.

### Authentication Setup (Private Content)

To access private profiles, stories, or tagged posts, configure authentication in `configs/auth_config.json`:

```json
{
  "sites": {
    "instagram.com": {
      "authentication_type": "session",
      "username": "YOUR_INSTAGRAM_USERNAME",
      "password": "YOUR_INSTAGRAM_PASSWORD",
      "session_file": null
    }
  }
}
```

### Session Setup (Recommended)

For better security and reliability, use session-based authentication:

1. **Command Line Login**:
   ```bash
   instaloader --login YOUR_USERNAME
   ```

2. **Session Auto-save**: The handler will automatically save and reuse sessions

3. **Manual Session Path**: Update `auth_config.json` with the session file path if needed

## Usage Examples

### Profile Extraction
```python
from site_handlers.instagram_handler import InstagramHandler

# Extract from public profile
handler = InstagramHandler("https://www.instagram.com/nasa/", scraper=None)
media_items = await handler.extract_with_direct_playwright()
```

### Individual Post
```python
# Extract specific post
handler = InstagramHandler("https://www.instagram.com/p/ABC123DEF/", scraper=None)
media_items = await handler.extract_with_direct_playwright()
```

### Hashtag Exploration
```python
# Extract from hashtag
handler = InstagramHandler("https://www.instagram.com/explore/tags/nature/", scraper=None)
media_items = await handler.extract_with_direct_playwright()
```

### Stories (Requires Login)
```python
# Extract stories (needs authentication)
handler = InstagramHandler("https://www.instagram.com/stories/username/", scraper=None)
media_items = await handler.extract_with_direct_playwright()
```

## URL Format Support

The handler recognizes these Instagram URL patterns:

| Type | URL Pattern | Example |
|------|-------------|---------|
| Profile | `instagram.com/username/` | `https://www.instagram.com/nasa/` |
| Post | `instagram.com/p/shortcode/` | `https://www.instagram.com/p/ABC123DEF/` |
| Reel | `instagram.com/reel/shortcode/` | `https://www.instagram.com/reel/XYZ789/` |
| Story | `instagram.com/stories/username/story_id` | `https://www.instagram.com/stories/nasa/123/` |
| Tagged | `instagram.com/username/tagged/` | `https://www.instagram.com/nasa/tagged/` |
| Hashtag | `instagram.com/explore/tags/hashtag/` | `https://www.instagram.com/explore/tags/space/` |

## Configuration Options

### Handler Settings
```python
handler = InstagramHandler(url, scraper=None)

# Configure extraction limits
handler.max_posts = 50  # Maximum posts per profile
handler.download_videos = True  # Include videos
handler.download_stories = False  # Requires login
handler.download_tagged = False  # Tagged posts
```

### Rate Limiting
The handler includes built-in rate limiting:
- **1 second** delay between posts
- **2 seconds** delay for hashtag posts
- **Respect Instagram's rate limits** automatically

## Output Format

Each extracted media item includes:

```python
{
    'url': 'https://instagram.com/path/to/image.jpg',
    'type': 'image',  # or 'video'
    'title': 'Post title or caption',
    'description': 'Full caption text',
    'username': 'post_author',
    'full_name': 'Author Full Name',
    'shortcode': 'ABC123DEF',
    'timestamp': '2024-01-01T12:00:00',
    'likes': 1500,
    'comments': 200,
    'is_video': False,
    'width': 1080,
    'height': 1080,
    'hashtags': ['#nature', '#photography'],
    'mentions': ['@photographer'],
    'location': 'Location Name',
    'source_url': 'https://www.instagram.com/p/ABC123DEF/',
    'extraction_method': 'instaloader',
    'is_carousel': False,  # True for multi-image posts
    'carousel_count': 1    # Number of images in carousel
}
```

## Error Handling

The handler includes comprehensive error handling:

- **Rate Limiting**: Automatic delays and retry logic
- **Authentication Errors**: Clear messages for login issues
- **Network Issues**: Robust connection handling
- **Content Restrictions**: Graceful handling of private content

## Privacy and Ethics

### Responsible Usage
- ⚖️ **Respect Terms of Service**: Only use for legitimate purposes
- 🔒 **Privacy Awareness**: Don't scrape private content without permission
- ⏱️ **Rate Limiting**: Don't overwhelm Instagram's servers
- 📝 **Content Rights**: Respect copyright and attribution

### Limitations
- **Private Profiles**: Require authentication and permission
- **Stories**: 24-hour availability window
- **Rate Limits**: Instagram enforces usage limits
- **DMCA**: Respect content creators' rights

## Troubleshooting

### Common Issues

1. **"Instaloader not available"**
   ```bash
   pip install instaloader
   ```

2. **Login Required Error**
   - Configure username/password in auth_config.json
   - Or use: `instaloader --login YOUR_USERNAME`

3. **Rate Limiting**
   - Reduce `max_posts` setting
   - Increase delays between requests
   - Use authentication for higher limits

4. **Private Content Access**
   - Ensure proper authentication
   - Check account permissions
   - Verify session is valid

### Debug Mode
Enable detailed logging:
```python
handler.debug = True  # More verbose output
```

## Advanced Features

### Session Management
```python
# Auto-save sessions
handler._save_session('username')

# Load existing session
handler._load_session()
```

### Custom Filtering
```python
# Filter by media type
video_only = [item for item in results if item['is_video']]

# Filter by engagement
popular_posts = [item for item in results if item['likes'] > 1000]
```

### Bulk Processing
```python
# Process multiple profiles
profiles = ['nasa', 'natgeo', 'discovery']
for profile in profiles:
    url = f"https://www.instagram.com/{profile}/"
    handler = InstagramHandler(url, scraper=None)
    results = await handler.extract_with_direct_playwright()
```

## Integration with ComfyUI

The Instagram handler integrates seamlessly with the Web Image Scraper node:

1. **Auto-detection**: URLs are automatically routed to the Instagram handler
2. **Metadata Integration**: Rich metadata is preserved in the workflow
3. **Batch Processing**: Multiple Instagram URLs can be processed together
4. **Output Compatibility**: Results work with all downstream ComfyUI nodes

## Legal Considerations

- 📋 **Terms of Service**: Review Instagram's current ToS
- 🔒 **Data Protection**: Comply with GDPR, CCPA, and local laws
- ⚖️ **Fair Use**: Ensure your usage falls under fair use guidelines
- 🤝 **Attribution**: Give credit to original content creators

## Support and Updates

The Instagram handler is actively maintained and updated to handle Instagram's evolving platform:

- 🔄 **Regular Updates**: Adapted for Instagram API changes
- 🐛 **Bug Fixes**: Issues resolved promptly
- 💡 **Feature Requests**: Community-driven improvements
- 📚 **Documentation**: Comprehensive guides and examples

## Contributing

To contribute improvements:

1. Test changes thoroughly
2. Respect rate limits during development
3. Document new features
4. Follow ethical scraping practices

---

**Ready to extract Instagram content responsibly and efficiently!** 🚀
