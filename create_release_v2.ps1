# PowerShell script to create GitHub Release for Version 2.0
# Requires GitHub CLI (gh) to be installed and authenticated

Write-Host "Creating GitHub Release for Version 2.0..." -ForegroundColor Green

# Check if GitHub CLI is installed
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    Write-Host "ERROR: GitHub CLI (gh) is not installed!" -ForegroundColor Red
    Write-Host "Please install it from: https://cli.github.com/" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Or create the release manually:" -ForegroundColor Yellow
    Write-Host "1. Go to: https://github.com/me-suzy/BEBE-Task-Recorder/releases/new" -ForegroundColor Cyan
    Write-Host "2. Tag: v2.0" -ForegroundColor Cyan
    Write-Host "3. Title: BEBE Task Recorder - Version 2.0" -ForegroundColor Cyan
    Write-Host "4. Description: Copy from RELEASE_V2.md" -ForegroundColor Cyan
    Write-Host "5. Upload: Bebe - Task Recorder - Version 2.0.exe" -ForegroundColor Cyan
    Write-Host "6. Upload: Bebe - Task Recorder - Version 2.0.png" -ForegroundColor Cyan
    exit 1
}

# Check if authenticated
$authStatus = gh auth status 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Not authenticated with GitHub CLI!" -ForegroundColor Red
    Write-Host "Please run: gh auth login" -ForegroundColor Yellow
    exit 1
}

# Read release notes
$releaseNotes = Get-Content "RELEASE_V2.md" -Raw

# Create release draft
Write-Host "Creating release draft..." -ForegroundColor Yellow
gh release create v2.0 `
    --title "BEBE Task Recorder - Version 2.0" `
    --notes "$releaseNotes" `
    --draft `
    "Bebe - Task Recorder - Version 2.0.exe" `
    "Bebe - Task Recorder - Version 2.0.png"

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "✅ Release draft created successfully!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Next steps:" -ForegroundColor Yellow
    Write-Host "1. Review the draft at: https://github.com/me-suzy/BEBE-Task-Recorder/releases" -ForegroundColor Cyan
    Write-Host "2. Edit the release if needed" -ForegroundColor Cyan
    Write-Host "3. Click 'Publish release' when ready" -ForegroundColor Cyan
} else {
    Write-Host ""
    Write-Host "❌ Failed to create release!" -ForegroundColor Red
    Write-Host "Please create it manually at: https://github.com/me-suzy/BEBE-Task-Recorder/releases/new" -ForegroundColor Yellow
}

