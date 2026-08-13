param(
    [string]$ProjectRoot = "C:\Users\user\job_portal",
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"

$project = [System.IO.Path]::GetFullPath($ProjectRoot)
$testsDirectory = Join-Path $project "tests"
$acceptanceDirectory = Join-Path $project "acceptance_tests"
$source = Join-Path $PSScriptRoot "payload\tests\test_all_website_pages.py"
$destination = Join-Path $testsDirectory "test_all_website_pages.py"

if (-not (Test-Path -LiteralPath $testsDirectory -PathType Container)) {
    throw "Tests folder not found: $testsDirectory"
}
if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
    throw "Page-test payload not found: $source. Extract the complete ZIP first."
}

if (Test-Path -LiteralPath $destination -PathType Leaf) {
    $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    Copy-Item -LiteralPath $destination -Destination "$destination.$timestamp.bak" -Force
}

Copy-Item -LiteralPath $source -Destination $destination -Force

$installed = Select-String -LiteralPath $destination -SimpleMatch "test_seeker_user_facing_route_inventory_is_complete" -Quiet
if (-not $installed) {
    throw "Page-test installation verification failed."
}

Write-Host "All-page test file installed: $destination" -ForegroundColor Green

if ($SkipTests) {
    exit 0
}

Push-Location $project
try {
    $targets = @("tests/")
    if (Test-Path -LiteralPath $acceptanceDirectory -PathType Container) {
        $targets += "acceptance_tests/"
    }

    Write-Host "Running the complete suite with the new page tests..." -ForegroundColor Cyan
    & python -m pytest @targets -v --html=report.html --self-contained-html
    $pytestExitCode = $LASTEXITCODE
}
finally {
    Pop-Location
}

if ($pytestExitCode -ne 0) {
    Write-Host "A page check found a real issue. Send the new report.html for repair." -ForegroundColor Red
    exit $pytestExitCode
}

Write-Host "All collected tests passed." -ForegroundColor Green
Write-Host "Report: $(Join-Path $project 'report.html')"

