@echo off
cd /d "%~dp0"
call .venv\Scripts\activate.bat
chcp 65001 >nul
pyinstaller --noconfirm --clean --windowed --name 财务软件 --icon app\assets\app_icon.ico --add-data "app\assets;app\assets" --add-data "app\web;app\web" run.py
if errorlevel 1 goto error
pyinstaller --noconfirm --clean --onefile --console --name updater_helper tools\updater_helper.py
if errorlevel 1 goto error
copy /y "dist\updater_helper.exe" "dist\财务软件\updater_helper.exe"
if not exist "dist\财务软件\data" mkdir "dist\财务软件\data"
copy /y data\finance.db "dist\财务软件\data\finance.db"
echo Done: dist\财务软件\财务软件.exe
pause
exit /b 0
:error
echo Build failed
pause
exit /b 1
