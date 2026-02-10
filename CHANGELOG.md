# Changelog

All notable changes to Download Tools for ComfyUI will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.8.5] - 2026-02-09

### Added
- **BellazonHandler** — New IPS/Invision Community forum handler for bellazon.com
  - Full-resolution image extraction via `<a href>` links and `data-full-image` attributes
  - Zero-thumbnail guarantee with 3-layer `.thumb.` URL rejection (JS, Python, post_process)
  - Automatic multi-page pagination (detects total pages, navigates all)
  - Spoiler/hidden content auto-opening (`<details>` blocks, IPS spoiler markup)
  - YouTube/Vimeo video link collection with URL normalisation
  - Lightbox link support (`data-ipslightbox`)
- Gallery-dl Downloader improvements:
  - Real-time progress output via threaded stdout/stderr streaming
  - ComfyUI cancel button support for long-running downloads
  - Skip already-organized files to avoid redundant processing
  - Seed parameter for forced re-execution
- `configs/yt-dlp.conf.example` — Clean template for yt-dlp configuration

### Changed
- Gallery-dl default timeout increased to 1800s (30 min), max to 36000s (10 hr)
- README updated with comprehensive Web Image Scraper section and 25+ handler table
- Updated config documentation to use `.example` pattern

### Fixed
- IPS forum thumbnail URL leak — discovered that IPS uses different hashes for
  thumbnail vs full-res URLs; regex-stripping `.thumb.` produced wrong/404 URLs

### Security
- Removed plaintext credentials from `configs/yt-dlp.conf` in repository
- Added `configs/yt-dlp.conf` to `.gitignore` to prevent future credential exposure
- Created `.example` template pattern for sensitive config files

## [0.8.3] - 2025-XX-XX

### Added
- Initial public release preparation
- License headers added to all Python files
- Comprehensive documentation
- GitHub issue and PR templates

## [0.8.2] - 2025-01-XX

### Added
- Web Image Scraper v0.82 with advanced site-specific handlers
- Support for 15+ specialized site handlers (Instagram, Bluesky, ArtStation, etc.)
- Model Context Protocol (MCP) server integration for Claude Desktop
- Browser automation with Playwright for JavaScript-heavy sites
- Scrapling integration for efficient HTML parsing
- Authentication support via cookies and login credentials
- Profile/session management for maintaining login states

### Changed
- Improved Instagram scraping with higher image discovery rates
- Enhanced error handling across all scraping handlers
- Better progress reporting and status messages

### Fixed
- Instagram authentication issues
- Bluesky media extraction reliability
- Various site-specific scraping issues

## [0.8.0] - 2024-XX-XX

### Added
- Gallery-dl Downloader node
- Yt-dlp Downloader node
- Browser cookie extraction support
- Multi-format video/audio download support
- Download archive to prevent duplicates
- Configuration file support

### Features
- Download from 100+ sites via gallery-dl
- Video/audio from 1000+ platforms via yt-dlp
- Automatic file organization
- Quality selection options
- Playlist support

## Key Features by Component

### Gallery-dl Downloader
- Instagram, Reddit, Twitter/X, DeviantArt, Pixiv, Tumblr
- Browser cookie authentication
- Archive system for duplicate prevention
- Custom configuration support
- Metadata extraction

### Yt-dlp Downloader
- YouTube, TikTok, Vimeo, Twitch, and 1000+ platforms
- Multiple quality presets
- Audio extraction (requires FFmpeg)
- Playlist download support
- Custom format selection

### Web Image Scraper
- Playwright browser automation
- Site-specific handlers for optimal extraction
- Authentication via cookies or login
- Progress tracking and resume capability
- Metadata collection
- Image filtering by dimensions

### MCP Integration
- Claude Desktop integration via Model Context Protocol
- External tool support for AI-assisted workflows
- Structured prompts and responses

## Development

### Documentation
- Comprehensive guides in `Docs/` folder
- Authentication setup guides
- Advanced configuration options
- Troubleshooting guides

### License
- Dual license: CC BY-NC 4.0 (non-commercial) / Commercial license required
- All code properly attributed
- Third-party dependencies documented in CREDITS.md

---

For more details on any release, see the [README.md](README.md) or check the [commit history](https://github.com/EricRollei/download_tools/commits/main).
