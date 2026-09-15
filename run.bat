@echo off
cd /d "%~dp0"
echo Installing dependencies if needed...
uv sync
echo Scraping current prices...
uv run python -m scraper.cli run
if errorlevel 1 (
  echo.
  echo Scrape did not complete - see the message above. Opening the dashboard anyway.
  echo.
)
uv run python -m scraper.cli serve
pause
