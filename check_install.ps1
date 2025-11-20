# Verification script for Download Tools Installation
# Copyright (c) 2025 Eric Hiss
# This file is part of Download Tools and is licensed under CC BY-NC 4.0

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Download Tools Installation Check" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Get the script directory
$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $SCRIPT_DIR

$allGood = $true

# Check Python
Write-Host "Checking Python..." -ForegroundColor Green
try {
    $pythonVersion = & python --version 2>&1
    Write-Host "✓ Python: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "✗ Python not found!" -ForegroundColor Red
    $allGood = $false
}

# Check required packages
Write-Host ""
Write-Host "Checking Python packages..." -ForegroundColor Green

$packages = @(
    "gallery_dl",
    "yt_dlp",
    "browser_cookie3",
    "requests",
    "tqdm",
    "colorama",
    "jsonschema"
)

foreach ($package in $packages) {
    try {
        $output = & python -c "import $package; print($package.__version__ if hasattr($package, '__version__') else 'installed')" 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Host "✓ $package`: $output" -ForegroundColor Green
        } else {
            Write-Host "✗ $package not found" -ForegroundColor Red
            $allGood = $false
        }
    } catch {
        Write-Host "✗ $package not found" -ForegroundColor Red
        $allGood = $false
    }
}

# Check FFmpeg
Write-Host ""
Write-Host "Checking FFmpeg (optional)..." -ForegroundColor Green
try {
    $ffmpegVersion = & ffmpeg -version 2>&1 | Select-Object -First 1
    Write-Host "✓ FFmpeg: $ffmpegVersion" -ForegroundColor Green
} catch {
    Write-Host "⚠ FFmpeg not found (optional, needed for audio extraction)" -ForegroundColor Yellow
}

# Check directory structure
Write-Host ""
Write-Host "Checking directory structure..." -ForegroundColor Green

$directories = @("nodes", "configs", "Docs")
foreach ($dir in $directories) {
    if (Test-Path $dir) {
        Write-Host "✓ $dir/ exists" -ForegroundColor Green
    } else {
        Write-Host "✗ $dir/ missing" -ForegroundColor Red
        $allGood = $false
    }
}

# Check key files
Write-Host ""
Write-Host "Checking key files..." -ForegroundColor Green

$files = @(
    "__init__.py",
    "requirements.txt",
    "README.md",
    "LICENSE.md",
    "nodes\yt_dlp_downloader.py",
    "nodes\gallery_dl_downloader.py"
)

foreach ($file in $files) {
    if (Test-Path $file) {
        Write-Host "✓ $file exists" -ForegroundColor Green
    } else {
        Write-Host "✗ $file missing" -ForegroundColor Red
        $allGood = $false
    }
}

# Check config files
Write-Host ""
Write-Host "Checking configuration files..." -ForegroundColor Green

$configFiles = Get-ChildItem -Path "configs" -Filter "*.conf" -ErrorAction SilentlyContinue
if ($configFiles.Count -gt 0) {
    Write-Host "✓ Found $($configFiles.Count) config file(s)" -ForegroundColor Green
    foreach ($config in $configFiles) {
        Write-Host "  - $($config.Name)" -ForegroundColor Gray
    }
} else {
    Write-Host "⚠ No .conf files in configs/" -ForegroundColor Yellow
    Write-Host "  This is OK if using default settings" -ForegroundColor Gray
}

# Final status
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
if ($allGood) {
    Write-Host "Installation Status: OK" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "✓ All required components are installed" -ForegroundColor Green
    Write-Host ""
    Write-Host "You can now:" -ForegroundColor Yellow
    Write-Host "1. Restart ComfyUI" -ForegroundColor White
    Write-Host "2. Find nodes under 'Download Tools' category" -ForegroundColor White
    Write-Host "3. Start downloading media!" -ForegroundColor White
} else {
    Write-Host "Installation Status: INCOMPLETE" -ForegroundColor Red
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Some components are missing. Please:" -ForegroundColor Yellow
    Write-Host "1. Run install.ps1 to install dependencies" -ForegroundColor White
    Write-Host "2. Check error messages above" -ForegroundColor White
    Write-Host "3. Contact support if issues persist" -ForegroundColor White
}
Write-Host ""
