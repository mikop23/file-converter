@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 필요한 부품 설치 중... (처음 한 번만 오래 걸려요)
python -m pip install -q -r requirements.txt
if errorlevel 1 (echo 파이썬이 없어요. 설명서.txt 1번을 먼저 해주세요. & pause & exit /b)
start "" pythonw app.py
