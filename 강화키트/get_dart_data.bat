@echo off
cd /d "%~dp0"
echo Fetching OpenDART EBITDA / FCF data
echo API key is read from .dart_key automatically
py -m pip install --quiet --upgrade requests pandas
echo self test:
py -W ignore dart_value_factors.py --selftest
echo fetching top 500 by mcap, FY2020-2025 ...
py -W ignore dart_value_factors.py
echo.
echo DONE. output file is created in this folder.
pause
