@echo off
echo Building FTR Exporter Pipeline Executable...

:: Check if pyinstaller is in PATH
where pyinstaller >nul 2>nul
if errorlevel 1 (
    echo PyInstaller not found in PATH! Attempting to run via local AppData path...
    "%APPDATA%\Python\Python314\Scripts\pyinstaller.exe" --noconfirm --onefile --windowed --icon "icon\fireteam_raven_exporter.ico" --add-data "g7_master_converter.py;." g7_pipeline_gui.py
    if errorlevel 1 (
        echo.
        echo ERROR: Could not find or run PyInstaller. Please ensure it is installed by running:
        echo pip install pyinstaller
        pause
        exit /b 1
    )
) else (
    pyinstaller --noconfirm --onefile --windowed --icon "icon\fireteam_raven_exporter.ico" --add-data "g7_master_converter.py;." g7_pipeline_gui.py
)

echo.
echo Build complete! The executable is located in the "dist" folder.
pause
