@echo off
cd /d "%~dp0"
echo Jinwoo Quant - archive history and open hub...
py -W ignore jq_history.py
py -W ignore jq_hub.py
timeout /t 3 >nul
