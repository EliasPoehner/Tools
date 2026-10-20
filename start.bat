@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
    py -3 -m venv .venv || goto :error
)
rem Abhängigkeiten (neu) installieren, wenn requirements.txt sich geändert hat oder die letzte Installation scheiterte.
fc /b requirements.txt .venv\requirements.installed >nul 2>&1 || (
    .venv\Scripts\python -m pip install -q -r requirements.txt || goto :error
    copy /y requirements.txt .venv\requirements.installed >nul
)
start "" .venv\Scripts\pythonw.exe main.py
exit /b 0

:error
echo.
echo Einrichtung fehlgeschlagen - ist Python installiert (py -3)?
pause
exit /b 1
