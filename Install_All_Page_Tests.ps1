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
$conftestSource = Join-Path $PSScriptRoot "payload\tests\conftest.py"
$conftestDestination = Join-Path $testsDirectory "conftest.py"
$authenticationTest = Join-Path $acceptanceDirectory "test_authentication.py"

if (-not (Test-Path -LiteralPath $testsDirectory -PathType Container)) {
    throw "Tests folder not found: $testsDirectory"
}
if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
    throw "Page-test payload not found: $source. Extract the complete ZIP first."
}
if (-not (Test-Path -LiteralPath $conftestSource -PathType Leaf)) {
    throw "Fixture payload not found: $conftestSource."
}

if (Test-Path -LiteralPath $destination -PathType Leaf) {
    $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    Copy-Item -LiteralPath $destination -Destination "$destination.$timestamp.bak" -Force
    if (Test-Path -LiteralPath $conftestDestination -PathType Leaf) {
        Copy-Item -LiteralPath $conftestDestination -Destination "$conftestDestination.$timestamp.bak" -Force
    }
}

Copy-Item -LiteralPath $source -Destination $destination -Force
Copy-Item -LiteralPath $conftestSource -Destination $conftestDestination -Force

# Login now opens the Explore Positions route at /seeker. Keep the
# authentication acceptance test aligned with that implemented behaviour.
if (Test-Path -LiteralPath $authenticationTest -PathType Leaf) {
    $authenticationContent = [System.IO.File]::ReadAllText($authenticationTest)
    $oldExpectation = 'assert response.get_json()["redirect"] == "/dashboard"'
    $newExpectation = 'assert response.get_json()["redirect"] == "/seeker"'

    if ($authenticationContent.Contains($oldExpectation)) {
        $authenticationContent = $authenticationContent.Replace(
            $oldExpectation,
            $newExpectation
        )
        [System.IO.File]::WriteAllText(
            $authenticationTest,
            $authenticationContent,
            [System.Text.UTF8Encoding]::new($false)
        )
    }
    elseif (-not $authenticationContent.Contains($newExpectation)) {
        throw "Could not find the login redirect assertion in $authenticationTest."
    }
}

$installed = Select-String -LiteralPath $destination -SimpleMatch "test_seeker_user_facing_route_inventory_is_complete" -Quiet
if (-not $installed) {
    throw "Page-test installation verification failed."
}
$fixtureInstalled = Select-String -LiteralPath $conftestDestination -SimpleMatch "seeker_main.JOB_SEEKER_ROLE" -Quiet
if (-not $fixtureInstalled) {
    throw "Acceptance fixture installation verification failed."
}

Write-Host "Acceptance test files installed in: $testsDirectory" -ForegroundColor Green

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