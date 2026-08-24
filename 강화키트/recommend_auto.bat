@echo off
cd /d "%~dp0"
echo Jinwoo Quant - refresh latest data and build recommendations...
py -m pip install --quiet pykrx finance-datareader pandas numpy
py -W ignore recommend_pipeline.py
echo.
echo Done. Recommendation dashboard opened in browser.
timeout /t 4 >nul
