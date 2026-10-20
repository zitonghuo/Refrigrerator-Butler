@echo off
chcp 65001 >nul
cd /d "%~dp0"
python --version >nul 2>&1
if errorlevel 1 (
  echo 请先安装 Python 3.10 或更高版本，并添加到 PATH。
  pause
  exit /b 1
)
echo 浏览器访问 http://127.0.0.1:8765
python server\app.py
pause
