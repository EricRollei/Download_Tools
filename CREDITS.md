# Credits and Third-Party Licenses

This project relies on excellent open-source tools for media downloading.

## Core Download Tools

### gallery-dl

- **License:** GNU GPL v2
- **Copyright:** Mike Fährmann
- **Repository:** https://github.com/mikf/gallery-dl
- **Used for:** Downloading images and media from 100+ websites
- **License URL:** https://github.com/mikf/gallery-dl/blob/master/LICENSE

gallery-dl is an amazing tool that supports downloading from Instagram, Reddit, Twitter, DeviantArt, Pixiv, and many more sites. We are grateful to Mike Fährmann and all contributors.

### yt-dlp

- **License:** Unlicense (Public Domain)
- **Copyright:** yt-dlp contributors
- **Repository:** https://github.com/yt-dlp/yt-dlp
- **Used for:** Downloading videos and audio from 1000+ platforms
- **License URL:** https://github.com/yt-dlp/yt-dlp/blob/master/LICENSE

yt-dlp is a powerful youtube-dl fork with active development and numerous improvements. We thank all contributors to this essential tool.

## Python Dependencies

### Core Libraries

- **[Requests](https://requests.readthedocs.io/)**
  - License: Apache 2.0
  - Copyright: Kenneth Reitz and Contributors
  - Used for: HTTP requests and API interactions

- **[urllib3](https://urllib3.readthedocs.io/)**
  - License: MIT
  - Copyright: Andrey Petrov and Contributors
  - Used for: HTTP client functionality

- **[tqdm](https://github.com/tqdm/tqdm)**
  - License: MIT / MPL 2.0
  - Copyright: Casper da Costa-Luis and Contributors
  - Used for: Progress bars and status indicators

- **[colorama](https://github.com/tartley/colorama)**
  - License: BSD 3-Clause
  - Copyright: Jonathan Hartley
  - Used for: Cross-platform colored terminal output

- **[jsonschema](https://python-jsonschema.readthedocs.io/)**
  - License: MIT
  - Copyright: Julian Berman
  - Used for: JSON schema validation

### Authentication Support

- **[browser-cookie3](https://github.com/borisbabic/browser_cookie3)**
  - License: GNU GPL v3
  - Copyright: Boris Babic
  - Used for: Extracting cookies from web browsers for authentication

## Optional Dependencies

### FFmpeg

- **License:** GNU GPL v2+ / LGPL v2.1+
- **Copyright:** FFmpeg team
- **Website:** https://ffmpeg.org/
- **Used for:** Video/audio conversion and processing (required by yt-dlp for audio extraction)

FFmpeg is not a Python dependency but is required for certain yt-dlp features like audio extraction.

## ComfyUI Integration

This package is designed as a custom node collection for:

- **[ComfyUI](https://github.com/comfyanonymous/ComfyUI)**
  - License: GNU GPL v3
  - Copyright: ComfyAnonymous and Contributors
  - The powerful and modular stable diffusion GUI

## License Compatibility

This project is released under a dual license (Non-Commercial: CC BY-NC 4.0 / Commercial: Contact for license). Please note:

- **GPL-licensed dependencies** (gallery-dl, browser-cookie3): If you distribute this software, you must comply with GPL requirements, which may require releasing your source code.
- **Commercial use**: If you wish to use this commercially, you must obtain our commercial license AND ensure compliance with all third-party dependency licenses.

## Attribution

If you use this project in your work, please provide attribution:

```
Download Tools for ComfyUI
Author: Eric Hiss (GitHub: EricRollei)
License: Dual License (CC BY-NC 4.0 / Commercial)
Repository: https://github.com/EricRollei/download-tools
```

## Acknowledgments

Special thanks to:

- **The ComfyUI community** for creating an amazing extensible platform
- **Mike Fährmann** for gallery-dl, an incredibly comprehensive downloader
- **yt-dlp contributors** for maintaining the best video downloader available
- All the open-source developers who maintain the libraries this project depends on

## Reporting Issues

If you believe any license information is incorrect or incomplete, please:

1. Open an issue on our GitHub repository
2. Contact: eric@historic.camera or eric@rollei.us

We take license compliance seriously and will address any concerns promptly.

---

**Last Updated:** January 2025
