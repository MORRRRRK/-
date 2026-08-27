@echo off
cd /d "%~dp0"
call .venv\Scripts\activate.bat
chcp 65001 >nul
if not exist "backups" mkdir "backups"
set TS=%date:~0,4%%date:~5,2%%date:~8,2%_%time:~0,2%%time:~3,2%%time:~6,2%
set TS=%TS: =0%
set TS=%TS::=%
set BACKUP_FILE=backups\pre_build_finance_%TS%.db
if exist "dist\财务软件\data\finance.db" (
  copy /y "dist\财务软件\data\finance.db" "%BACKUP_FILE%" >nul
)
pyinstaller --noconfirm --clean --windowed --name 财务软件 --icon app\assets\app_icon.ico --add-data "app\assets;app\assets" --add-data "app\web;app\web" run.py
if errorlevel 1 goto error
pyinstaller --noconfirm --clean --onefile --console --name updater_helper tools\updater_helper.py
if errorlevel 1 goto error
copy /y "dist\updater_helper.exe" "dist\财务软件\updater_helper.exe"
if not exist "dist\财务软件\data" mkdir "dist\财务软件\data"
if not exist "dist\财务软件\data\finance.db" (
  if exist "%BACKUP_FILE%" (
    copy /y "%BACKUP_FILE%" "dist\财务软件\data\finance.db" >nul
  ) else if exist "data\finance.db" (
    copy /y data\finance.db "dist\财务软件\data\finance.db" >nul
  )
)
echo Done: dist\财务软件\财务软件.exe
pause
exit /b 0
:error
echo Build failed
pause
exit /b 1
