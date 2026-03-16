@echo off
:: Build OmniDesktop.exe using PyInstaller
:: Usage: build.bat [--debug]
::
:: Output: dist\OmniDesktop.exe

cd /d "%~dp0"

echo ==============================================
echo  Omni Desktop Client - Build Script
echo ==============================================

:: Debug mode: show console window for troubleshooting
if /I "%1"=="--debug" (
    echo [DEBUG] Building with console window enabled...
    uv run pyinstaller omni_desktop.spec ^
        --noconfirm ^
        --clean ^
        -- ^
        --console
) else (
    echo Building release executable...
    uv run pyinstaller omni_desktop.spec --noconfirm --clean
)

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Build failed! See output above.
    exit /b 1
)

echo.
echo ==============================================
echo  Build complete!
echo  Executable: dist\OmniDesktop.exe
echo ==============================================
