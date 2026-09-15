@echo off
cd /d "%~dp0"
echo Installing dependencies if needed...
python -m pip install -q -r requirements.txt
echo Scraping current prices...
python -m scraper.cli run
if errorlevel 1 (
  echo.
  echo Scrape failed. Previous data is intact. Opening the dashboard anyway.
  echo.
)
python -m scraper.cli serve
pause
