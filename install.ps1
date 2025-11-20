# Installation script for Download Tools ComfyUI Nodes
# Copyright (c) 2025 Eric Hiss
# This file is part of Download Tools and is licensed under CC BY-NC 4.0
# For commercial use, please contact: eric@rollei.us

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Download Tools Installation" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Get the script directory
$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $SCRIPT_DIR

Write-Host "Installing in: $SCRIPT_DIR" -ForegroundColor Yellow
Write-Host ""

# Check if Python is available
Write-Host "Checking Python..." -ForegroundColor Green
try {
    $pythonVersion = & python --version 2>&1
    Write-Host "Found: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "ERROR: Python not found!" -ForegroundColor Red
    Write-Host "Please install Python 3.8 or higher and add it to PATH" -ForegroundColor Yellow
    exit 1
}

# Check if we're in a ComfyUI custom_nodes directory
if (-not (Test-Path "..\..\requirements.txt")) {
    Write-Host "WARNING: This doesn't appear to be in ComfyUI's custom_nodes directory" -ForegroundColor Yellow
    Write-Host "Expected path: ComfyUI/custom_nodes/download-tools" -ForegroundColor Yellow
    $continue = Read-Host "Continue anyway? (y/n)"
    if ($continue -ne "y") {
        exit 0
    }
}

# Install Python dependencies
Write-Host ""
Write-Host "Installing Python dependencies..." -ForegroundColor Green
Write-Host "This may take a few minutes..." -ForegroundColor Yellow
Write-Host ""

if (Test-Path "requirements.txt") {
    & python -m pip install -r requirements.txt
    if ($LASTEXITCODE -eq 0) {
        Write-Host ""
        Write-Host "✓ Python dependencies installed successfully" -ForegroundColor Green
    } else {
        Write-Host ""
        Write-Host "ERROR: Failed to install Python dependencies" -ForegroundColor Red
        Write-Host "Try running: python -m pip install -r requirements.txt" -ForegroundColor Yellow
        exit 1
    }
} else {
    Write-Host "ERROR: requirements.txt not found!" -ForegroundColor Red
    exit 1
}

# Check for optional FFmpeg
Write-Host ""
Write-Host "Checking for FFmpeg (optional, but recommended)..." -ForegroundColor Green
try {
    $ffmpegVersion = & ffmpeg -version 2>&1 | Select-Object -First 1
    Write-Host "✓ FFmpeg found: $ffmpegVersion" -ForegroundColor Green
} catch {
    Write-Host "⚠ FFmpeg not found" -ForegroundColor Yellow
    Write-Host "FFmpeg is required for audio extraction with yt-dlp" -ForegroundColor Yellow
    Write-Host "Download from: https://ffmpeg.org/download.html" -ForegroundColor Cyan
}

# Create config directory if it doesn't exist
if (-not (Test-Path "configs")) {
    New-Item -ItemType Directory -Path "configs" | Out-Null
    Write-Host "✓ Created configs directory" -ForegroundColor Green
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Installation Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "1. Restart ComfyUI" -ForegroundColor White
Write-Host "2. Look for 'Download Tools' category in the node menu" -ForegroundColor White
Write-Host "3. Check the README.md for usage examples" -ForegroundColor White
Write-Host ""
Write-Host "Documentation:" -ForegroundColor Yellow
Write-Host "- README.md: Quick start guide" -ForegroundColor White
Write-Host "- Docs/yt_dlp_node_complete_guide.md: yt-dlp node guide" -ForegroundColor White
Write-Host "- Docs/gallery_dl_node_complete_guide.md: gallery-dl node guide" -ForegroundColor White
Write-Host "- Docs/gallery_dl_authentication_guide.md: Authentication setup" -ForegroundColor White
Write-Host ""
Write-Host "For issues or questions:" -ForegroundColor Yellow
Write-Host "- GitHub: https://github.com/EricRollei/download-tools" -ForegroundColor Cyan
Write-Host "- Email: eric@rollei.us" -ForegroundColor Cyan
Write-Host ""
