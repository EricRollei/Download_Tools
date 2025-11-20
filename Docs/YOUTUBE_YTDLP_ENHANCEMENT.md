# YouTube Handler Enhancement with yt-dlp

## Overview

The enhanced YouTube handler uses **yt-dlp** (the modern successor to youtube-dl) to provide much more powerful YouTube content extraction capabilities compared to the basic Playwright-only handler.

## Key Improvements

### Basic Handler (youtube_handler.py)
- ✅ Extracts thumbnails and basic metadata  
- ✅ Works with Playwright only
- ❌ Cannot download actual video/audio files
- ❌ Limited metadata extraction
- ❌ No playlist/channel batch processing

### Enhanced Handler (youtube_handler_ytdlp.py)  
- ✅ **Downloads actual video files** in multiple qualities (4K, 1080p, 720p)
- ✅ **Downloads audio-only files** 
- ✅ **Comprehensive metadata extraction** (views, duration, description, etc.)
- ✅ **Playlist and channel support** with configurable limits
- ✅ **Age-restriction handling**
- ✅ **Authentication support** for private content
- ✅ **Trusted CDN domain handling**
- ✅ **Fallback to metadata-only mode**

## Installation

```bash
pip install yt-dlp
```

## Usage Examples

### 1. Metadata Only (No Downloads)
```python
handler = YouTubeHandlerYtDlp(url)
items = await handler.extract_with_direct_playwright(
    download_videos=False,
    download_audio=False
)
```

### 2. Download Videos
```python
handler = YouTubeHandlerYtDlp(url)
items = await handler.extract_with_direct_playwright(
    download_videos=True,
    download_audio=False
)
```

### 3. Download Audio Only
```python
handler = YouTubeHandlerYtDlp(url)
items = await handler.extract_with_direct_playwright(
    download_videos=False,
    download_audio=True
)
```

## Configuration Options

The handler can be configured through scraper settings:

```python
class MyScraper:
    download_videos = True        # Download video files
    download_audio = False        # Download audio files  
    max_video_quality = '1080p'   # '4K', '1080p', '720p'
    max_playlist_items = 50       # Limit playlist downloads
```

## Supported URL Types

- ✅ **Single videos**: `https://www.youtube.com/watch?v=VIDEO_ID`
- ✅ **Short URLs**: `https://youtu.be/VIDEO_ID`
- ✅ **Playlists**: `https://www.youtube.com/playlist?list=PLAYLIST_ID`
- ✅ **Channels**: `https://www.youtube.com/channel/CHANNEL_ID`
- ✅ **Channel handles**: `https://www.youtube.com/@ChannelName`

## Output Types

### Thumbnail Items
```python
{
    'url': 'https://i.ytimg.com/vi/VIDEO_ID/maxresdefault.jpg',
    'type': 'image',
    'title': 'Thumbnail: Video Title',
    'uploader': 'Channel Name',
    'duration': 240,
    'view_count': 1000000,
    'trusted_cdn': True
}
```

### Video File Items (when downloading)
```python
{
    'url': '/path/to/downloaded/video.mp4',
    'type': 'video', 
    'title': 'Video Title',
    'uploader': 'Channel Name',
    'file_size': 52428800,
    'local_file': True,
    'trusted_cdn': True
}
```

### Metadata Reference Items (no download)
```python
{
    'url': 'https://www.youtube.com/watch?v=VIDEO_ID',
    'type': 'youtube_video',
    'title': 'Video Title',
    'uploader': 'Channel Name',
    'duration': 240,
    'view_count': 1000000,
    'description': 'Video description...',
    'upload_date': '20240101',
    'trusted_cdn': True
}
```

## Integration with Main Scraper

The enhanced handler integrates seamlessly with the existing scraper system:

1. **Higher Priority**: Set to priority 40 (higher than basic handler)
2. **Automatic Fallback**: If yt-dlp not available, falls back to basic handler
3. **Trusted Domain Support**: Includes all YouTube CDN domains
4. **Domain Checking**: Properly sets `trusted_cdn=True` for all YouTube content

## Performance Considerations

- **Metadata extraction**: Very fast, similar to basic handler
- **Video downloads**: Depends on video size and internet speed
- **Playlist processing**: Limited by `max_playlist_items` setting
- **Memory usage**: Downloads use temporary files, cleaned up automatically

## Error Handling

- Graceful fallback if yt-dlp not installed
- Individual video errors don't stop playlist processing
- Network errors handled with retries (yt-dlp built-in)
- Age-restricted content handled automatically

## Testing

Run the comparison test:
```bash
python test_youtube_enhancement.py
```

This will show the differences between basic and enhanced handlers.

## Migration

To switch from basic to enhanced handler:

1. Install yt-dlp: `pip install yt-dlp`
2. The enhanced handler will automatically take priority
3. Configure download settings as needed
4. Existing code continues to work unchanged

The enhanced handler is backward compatible and provides the same interface as the basic handler, with additional capabilities when yt-dlp is available.
