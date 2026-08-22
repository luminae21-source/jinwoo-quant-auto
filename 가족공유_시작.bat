@echo off
cd /d %~dp0
for %%f in (*.exe) do start "" "%%f" --lan
