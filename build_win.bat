@echo off
cd /d "%~dp0"

echo.
echo   Building NOEMA for Windows...
echo.

pip install pyinstaller pywebview --quiet
if errorlevel 1 (
    echo ERROR: pip install failed. Make sure Python is installed.
    pause
    exit /b 1
)

if exist build rmdir /s /q build
if exist dist  rmdir /s /q dist

pyinstaller NOEMA_win.spec
if errorlevel 1 (
    echo ERROR: PyInstaller failed.
    pause
    exit /b 1
)

echo.
echo   Done! The NOEMA folder is in dist\NOEMA\
echo.
echo   To distribute: zip the dist\NOEMA\ folder and share it.
echo   Users run: dist\NOEMA\NOEMA.exe
echo.
echo   Requirements for users:
echo     - Windows 10 or 11
echo     - Microsoft Edge WebView2 (installed by default on Win 10/11)
echo     - Ollama running at http://localhost:11434
echo.
pause
