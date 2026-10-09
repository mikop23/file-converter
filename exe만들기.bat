@echo off
chcp 65001 >nul
cd /d "%~dp0"
python -m pip install -q -r requirements.txt pyinstaller
set EXTRA=
if exist bin\pandoc.exe set EXTRA=--add-binary "bin\pandoc.exe;bin"
python -m PyInstaller --noconfirm --windowed --name FileConverter %EXTRA% app.py
echo.
echo 완료: dist\FileConverter 폴더 안의 FileConverter.exe
pause
