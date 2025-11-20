# Download Tools for ComfyUI

ComfyUI custom nodes for downloading media from 1000+ websites including Instagram, Reddit, Twitter, YouTube, TikTok, and more.

## 🎉 Features

- **Gallery-dl Node** - Download images and videos from 100+ websites
  - Instagram, Reddit, Twitter/X, DeviantArt, Pixiv, and more
  - Supports authentication via browser cookies
  - Automatic file organization
  - Download archive to avoid duplicates

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
   - Enable `use_browser_cookies` for private content
   - Enable `organize_files` to sort by type
   - Enable `use_download_archive` to avoid duplicates
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

## 🔐 Authentication

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

- `gallery-dl.conf` - Gallery-dl settings
- `gallery-dl-browser-cookies.conf` - Browser cookie configuration
- `yt-dlp.conf` - Yt-dlp default settings
- `yt-dlp-audio.conf` - Audio extraction preset
- `yt-dlp-hq.conf` - High quality preset

You can create custom config files and reference them in the nodes.

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
Try:
- Run ComfyUI as administrator
- Use Firefox instead
- Export cookies manually (Method 2)

### "Instagram/Reddit downloads fail"
Authentication required:
- Enable `use_browser_cookies`
- Or export cookies from logged-in browser

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
