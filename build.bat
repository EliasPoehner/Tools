@echo off
rem Baut dist\werkbank.exe (eine Datei, ohne Konsole). Nutzt dieselbe .venv wie start.bat.
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
    py -3 -m venv .venv || goto :error
)
.venv\Scripts\python -m pip install -q -r requirements.txt pyinstaller || goto :error
rem Tools werden zur Laufzeit per pkgutil gefunden -> explizit mit einpacken, ebenso die pynput-Backends.
.venv\Scripts\python -m PyInstaller --noconfirm --clean --onefile --windowed --name werkbank ^
    --collect-submodules tools --collect-submodules pynput main.py || goto :error
echo.
echo Fertig: dist\werkbank.exe
exit /b 0

:error
echo.
echo Build fehlgeschlagen.
if not defined CI pause
exit /b 1
