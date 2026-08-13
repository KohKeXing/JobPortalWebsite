$ErrorActionPreference = "Stop"

Write-Host "Installing acceptance-test packages..." -ForegroundColor Cyan
python -m pip install -r acceptance_tests/requirements.txt

Write-Host "Running JobPortal acceptance tests..." -ForegroundColor Cyan
python -m pytest -c acceptance_tests/pytest.ini acceptance_tests

if ($LASTEXITCODE -ne 0) {
    throw "Acceptance tests failed. Review the output above and acceptance_report.html."
}

Write-Host "All acceptance tests passed." -ForegroundColor Green
Write-Host "Report: acceptance_report.html"
