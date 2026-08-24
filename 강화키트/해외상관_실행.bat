@echo off
cd /d "%~dp0"
echo Jinwoo Quant - Korea vs US/HK peer correlation...
py -m pip install --quiet yfinance pandas numpy
py -W ignore overseas_corr.py
echo.
echo Done. Output HTML created in this folder.
timeout /t 4 >nul
