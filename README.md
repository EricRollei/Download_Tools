# Download Tools for ComfyUI

ComfyUI custom nodes for downloading media from 1000+ websites including Instagram, Reddit, Twitter, YouTube, TikTok, and more.

## 🎉 Features

- **Gallery-dl Node** - Download images and videos from 100+ websites
  - Instagram, Reddit, Twitter/X, DeviantArt, Pixiv, and more
  - **Resolution filtering** - Skip small images (default: 768px minimum)
  - Supports authentication via config file or browser cookies
  - Automatic file organization
  - Download archive to avoid duplicates
  - **Persistent config paths** - Paths are remembered between sessions
  - **Configurable timeout** - Up to 1 hour for large downloads

- **Yt-dlp Node** - Download videos and audio from 1000+ platforms
  - YouTube, TikTok, Vimeo, Twitch, and more
  - Multiple quality options
  - Audio extraction support
  - Playlist support

## 📦 Installation

### Using ComfyUI Manager (Recommended)

1. Open ComfyUI Manager
2. Search for "Download Tools"
3. Click Install

### Manual Installation

1. Clone or download this repository to your ComfyUI custom_nodes folder:
   ```powershell
   cd ComfyUI/custom_nodes
   git clone https://github.com/EricRollei/download-tools.git
   ```

2. Install dependencies:
   ```powershell
   # Windows (using ComfyUI's Python)
   .\ComfyUI\python_embeded\python.exe -m pip install -r download-tools\requirements.txt
   
   # Or using system Python
   pip install -r download-tools/requirements.txt
   ```

3. (Optional) Install FFmpeg for audio extraction:
   - Windows: `choco install ffmpeg` or download from https://ffmpeg.org/
   - macOS: `brew install ffmpeg`
   - Linux: `apt-get install ffmpeg`

4. Restart ComfyUI

## 🚀 Quick Start

### Gallery-dl Downloader

1. Add "Gallery-dl Downloader" node to your workflow
2. Enter a URL (e.g., Instagram profile, Reddit post)
3. Configure options:
   - Set `config_path` to `./configs/gallery-dl.conf` (auto-saved for next time)
   - Enable `filter_by_resolution` to skip small images (768px default)
   - Enable `organize_files` to sort by type
   - Enable `use_download_archive` to avoid duplicates
   - Increase `download_timeout` for large galleries (default: 600s)
4. Execute!

**Supported Sites:** Instagram, Reddit, Twitter, DeviantArt, Pixiv, Tumblr, Pinterest, Flickr, and 90+ more. See [gallery-dl supported sites](https://github.com/mikf/gallery-dl/blob/master/docs/supportedsites.md).

### Yt-dlp Downloader

1. Add "Yt-dlp Downloader" node to your workflow
2. Enter a URL (e.g., YouTube video)
3. Choose format:
   - `best` - Best quality video
   - `audio-only` - Extract audio (requires FFmpeg)
   - Custom format string
4. Execute!

**Supported Sites:** YouTube, TikTok, Vimeo, Twitch, Facebook, Instagram, Twitter, and 1000+ more. See [yt-dlp supported sites](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md).

## � Instagram Downloads

**For Instagram, use Gallery-dl as it is better.** Gallery-dl has native Instagram API support, handles pagination, rate limits, and can download posts, stories, reels, and highlights.

### Recommended Settings

| Setting | Value | Notes |
|---------|-------|-------|
| `config_path` | `./configs/gallery-dl.conf` | Contains all site credentials (auto-saved) |
| `cookie_file` | *(leave empty)* | Cookies are in config file |
| `use_browser_cookies` | ❌ False | Config file is more reliable |
| `filter_by_resolution` | ✅ True | Skip thumbnails and small images |
| `min_image_width/height` | 768 | Minimum resolution in pixels |

### One Config For All Sites

The `gallery-dl.conf` file contains credentials for **all supported sites** (Instagram, Reddit, 500px, DeviantArt, Pinterest, Flickr, Bluesky). Gallery-dl automatically uses the right credentials based on the URL you're downloading from.

### Why Not Browser Cookies?

- **Chrome/Edge:** Require admin privileges AND browser must be closed
- **Firefox:** Works without admin, but less reliable than config file
- **Config file:** Most reliable method - always works

### Setting Up Instagram Authentication

1. **Export your Instagram cookies** from Chrome/Firefox using "Get cookies.txt LOCALLY" extension
2. **Copy the key cookies** to `configs/gallery-dl.conf` in the `instagram` section:
   ```json
   "instagram": {
       "cookies": {
           "sessionid": "YOUR_SESSION_ID",
           "ds_user_id": "YOUR_USER_ID", 
           "csrftoken": "YOUR_CSRF_TOKEN",
           "mid": "YOUR_MID_VALUE"
       }
   }
   ```
3. **Use in node:**
   - Set `config_path` to `./configs/gallery-dl.conf`
   - Leave `cookie_file` empty
   - Set `use_browser_cookies` to False

### Cookie Expiration

Instagram session cookies expire after ~1 year. If downloads start failing with 401 errors, export fresh cookies from your browser.

## �🔐 Authentication

Many sites require authentication for private content:

### Method 1: Browser Cookies (Automatic)

1. Log into the website in your browser
2. Enable `use_browser_cookies` in the node
3. Select your browser (Chrome, Firefox, Edge, etc.)
4. The node will automatically use your login session

### Method 2: Export Cookies

1. Install browser extension: "Get cookies.txt LOCALLY"
2. Log into the website
3. Export cookies
4. Save to `configs/instagram_cookies.json` (or site-specific file)
5. Set `cookie_file` parameter in the node

## 📁 Configuration

Config files are stored in `download-tools/configs/`:

- `gallery-dl.conf` - **Main config** with credentials for all sites (Instagram, Reddit, 500px, DeviantArt, Pinterest, Flickr, Bluesky)
- `gallery-dl.conf.example` - Template for creating your own config
- `yt-dlp.conf` - Yt-dlp default settings
- `yt-dlp-audio.conf` - Audio extraction preset
- `yt-dlp-hq.conf` - High quality preset

### Persistent Paths

Config file paths are **automatically saved** between ComfyUI sessions. Once you set `config_path` or `cookie_file`, they'll be remembered for next time.

## 📚 Documentation

Detailed guides available in `Docs/`:

- `gallery_dl_node_complete_guide.md` - Complete gallery-dl usage
- `yt_dlp_node_complete_guide.md` - Complete yt-dlp usage
- `gallery_dl_authentication_guide.md` - Authentication setup
- `gallery_dl_advanced_options_guide.md` - Advanced features

## 🐛 Troubleshooting

### "gallery-dl not found"
Already installed! It's a Python package. The node will find it automatically.

### "Chrome cookies not accessible"
Chrome locks its cookie database while running. Solutions:
- Close Chrome completely before running
- Run ComfyUI as administrator
- Use Firefox instead (doesn't require admin)
- **Best:** Use config file with cookies (see Instagram section above)

### "Instagram/Reddit downloads fail"
Authentication required:
- Use `config_path: ./configs/gallery-dl.conf` with cookies
- Or enable `use_browser_cookies` with Firefox
- 401 Unauthorized = expired cookies, export fresh ones

### "Downloads timing out"
For large galleries:
- Increase `download_timeout` (default: 600s, max: 3600s = 1 hour)
- Large Instagram profiles may need the full hour

### "Too many small images"
Enable resolution filtering:
- Set `filter_by_resolution` to True
- Adjust `min_image_width` and `min_image_height` (default: 768px)
- Videos are never filtered, only images

### "CUDA out of memory" / "FFmpeg not found"
For audio extraction:
- Install FFmpeg separately
- Or use video formats

## ⚙️ Requirements

- Python 3.10+
- ComfyUI
- gallery-dl (auto-installed)
- yt-dlp (auto-installed)
- FFmpeg (optional, for audio extraction)

## 📄 License

Copyright (c) 2025 Eric Hiss. All rights reserved.

**Dual License:**
- **Non-Commercial Use:** Licensed under [Creative Commons Attribution-NonCommercial 4.0 International License (CC BY-NC 4.0)](http://creativecommons.org/licenses/by-nc/4.0/)
- **Commercial Use:** Requires a separate commercial license. Contact: eric@historic.camera or eric@rollei.us

See [LICENSE.md](LICENSE.md) for full terms.

### Third-Party Tools

- **gallery-dl** (GNU GPL v2) by Mike Fährmann: https://github.com/mikf/gallery-dl
- **yt-dlp** (Unlicense/Public Domain): https://github.com/yt-dlp/yt-dlp

See [CREDITS.md](CREDITS.md) for complete dependency list.

## 👥 Contributing

Contributions welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## 📧 Contact

- **Author:** Eric Hiss
- **GitHub:** [EricRollei](https://github.com/EricRollei)
- **Email:** eric@historic.camera, eric@rollei.us

## 🙏 Acknowledgments

- **ComfyUI** community for the platform
- **Mike Fährmann** for gallery-dl
- **yt-dlp** contributors for the excellent video downloader

---

**Ready to download!** 🚀 Add the nodes to your workflow and start downloading media from across the web.
