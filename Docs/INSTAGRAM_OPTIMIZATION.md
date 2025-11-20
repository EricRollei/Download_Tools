# Instagram Handler Configuration Guide

## Overview
The Instagram handler has been optimized to capture significantly more content from Instagram profiles. Here are the key improvements and configuration options:

## ⚡ Performance Improvements

### 1. Increased Post Limits
- **Default**: 200 posts (increased from 50)
- **Customizable**: Can be set higher via scraper configuration
- **Result**: 4x more content extraction

### 2. Faster Rate Limiting
- **Before**: 1 second between requests
- **After**: 0.5 seconds between requests
- **Result**: 2x faster extraction speed

### 3. Better Error Handling
- **Location queries**: Silent handling of Instagram API location errors
- **Metadata extraction**: Fallback extraction if full metadata fails
- **Network issues**: Increased timeout and retry attempts

### 4. Enhanced File Support
- **HEIC files**: Now supported (Apple's image format)
- **HEIF files**: Now supported
- **Result**: No more "Unsupported file type" errors for modern iPhone photos

## 🛠️ Configuration Options

### Basic Settings
The handler automatically detects these settings:
- Max posts: 200 (can be customized)
- Download videos: ✅ Enabled
- Download stories: ❌ Disabled (requires login)
- Download highlights: ❌ Disabled (requires login)

### Custom Post Limits
To extract more than 200 posts, you can modify the `max_posts` setting:

```python
# In your scraper configuration
scraper.max_posts = 500  # Extract up to 500 posts
```

### Cookie Authentication
The handler uses your Instagram cookies for authenticated access:
- Location: `configs/auth_config.json`
- Section: `instagram.com`
- Includes: 12 cookies for full authentication

## 📊 Expected Results

### Before Optimization
- **Posts found**: ~45-50
- **Speed**: Slower due to 1s delays
- **Errors**: Location query failures
- **HEIC files**: Skipped

### After Optimization
- **Posts found**: 150-200+ (depending on profile)
- **Speed**: 2x faster extraction
- **Errors**: Gracefully handled
- **HEIC files**: Successfully downloaded

## 🎯 Usage Tips

### For Maximum Content
1. **Increase max_posts**: Set to 500 or higher for large profiles
2. **Use authentication**: Ensures access to all public content
3. **Run during off-peak hours**: Better success rates
4. **Monitor progress**: Check console output for real-time updates

### For Speed vs Completeness
- **Fast extraction**: Keep default 200 posts
- **Complete extraction**: Set max_posts to 1000+
- **Profile size**: Check profile.mediacount first

### Troubleshooting

#### If you get fewer posts than expected:
1. **Check rate limiting**: Instagram may be throttling requests
2. **Verify authentication**: Ensure cookies are valid
3. **Profile privacy**: Some content may be restricted
4. **Network issues**: Try again with stable connection

#### If extraction is slow:
1. **Reduce max_posts**: Lower the limit temporarily
2. **Check internet speed**: Slow networks affect extraction
3. **Instagram load**: High server load can slow responses

## 🔧 Advanced Configuration

### Custom Timeout Settings
```python
# Increase timeout for slow networks
handler.loader.request_timeout = 60  # 60 seconds

# Increase connection attempts
handler.loader.max_connection_attempts = 5
```

### Content Type Selection
```python
# Enable additional content types (requires authentication)
handler.download_stories = True      # Enable stories
handler.download_highlights = True   # Enable highlights
handler.download_tagged = True       # Enable tagged posts
```

## 📈 Performance Monitoring

Watch the console output for these indicators:
- `📥 Processed X posts...` - Progress updates every 10 posts
- `⏹️ Reached maximum posts limit` - Hit the configured limit
- `⚠️ Error processing post` - Individual post failures (usually harmless)
- `✅ Instagram extraction complete` - Final count

## 🎉 Success Metrics

A successful extraction should show:
- **High success rate**: 90%+ posts processed without errors
- **Good variety**: Mix of recent and older content
- **Efficient timing**: ~0.5-1 second per post
- **Clean output**: Minimal error messages

The optimized handler should now capture 3-4x more content while being more reliable and faster!
