@echo off
cd /d "%~dp0"
call .venv\Scripts\activate.bat
chcp 65001 >nul
pyinstaller --noconfirm --clean --onefile --console --name updater_helper tools\updater_helper.py
if errorlevel 1 goto error
pyinstaller --noconfirm --clean --windowed --name 财务软件客户版 --icon app\assets\app_icon.ico --add-data "app\assets;app\assets" --add-data "app\web;app\web" run.py
if errorlevel 1 goto error
if not exist "dist\财务软件客户版" mkdir "dist\财务软件客户版"
echo customer> "dist\财务软件客户版\edition.ini"
copy /y "dist\updater_helper.exe" "dist\财务软件客户版\updater_helper.exe"
echo repo=MORRRRRK/finance-releases> "dist\财务软件客户版\update_config.ini"
echo Done: dist\财务软件客户版\财务软件客户版.exe
pause
exit /b 0
:error
echo Build failed
pause
exit /b 1
