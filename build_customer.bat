@echo off
cd /d "%~dp0"
call .venv\Scripts\activate.bat
pyinstaller --noconfirm --clean --windowed --name 财务软件客户版 --icon app\assets\app_icon.ico --add-data "app\assets;app\assets" run.py
if errorlevel 1 goto error
if not exist "dist\财务软件客户版" mkdir "dist\财务软件客户版"
echo customer> "dist\财务软件客户版\edition.ini"
echo Done: dist\财务软件客户版\财务软件客户版.exe
pause
exit /b 0
:error
echo Build failed
pause
exit /b 1
