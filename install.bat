@echo off
chcp 65001 >nul
title SubAlign 一键安装

echo ============================================
echo   SubAlign 字幕自动对齐工具 - 一键安装
echo ============================================
echo.

:: ========== 检查 Python ==========
echo [1/4] 检查 Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] 未检测到 Python，正在下载安装...
    echo     请在弹出的安装界面中勾选 "Add Python to PATH"
    echo.
    curl -L -o python_installer.exe https://www.python.org/ftp/python/3.12.9/python-3.12.9-amd64.exe
    start /wait python_installer.exe /passive InstallAllUsers=0 PrependPath=1
    del python_installer.exe
    echo [√] Python 安装完成，请关闭此窗口重新运行本脚本
    pause
    exit /b
)
for /f "tokens=*" %%i in ('python --version') do echo     %%i [√]

:: ========== 检查 ffmpeg ==========
echo [2/4] 检查 ffmpeg...
ffmpeg -version >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] 未检测到 ffmpeg
    echo.
    echo     请选择安装方式：
    echo     1. 如果你有 scoop：在终端运行  scoop install ffmpeg
    echo     2. 如果你有 choco： 在终端运行  choco install ffmpeg
    echo     3. 手动下载：https://www.gyan.dev/ffmpeg/builds/
    echo        下载 ffmpeg-release-essentials.zip
    echo        解压后将 bin 目录添加到系统 PATH
    echo.
    echo     安装 ffmpeg 后重新运行本脚本
    pause
    exit /b
)
echo     ffmpeg [√]

:: ========== 安装 SubAlign ==========
echo [3/4] 安装 SubAlign...
cd /d "%~dp0"
pip install -e . >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] 安装失败，尝试使用 --user 模式...
    pip install -e . --user
)
echo     SubAlign [√]

:: ========== 验证 ==========
echo [4/4] 验证安装...
subalign --help >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] subalign 命令未找到，可能需要重启终端
    echo     或尝试：python -m subalign.cli --help
) else (
    echo     subalign 命令 [√]
)

echo.
echo ============================================
echo   安装完成！
echo ============================================
echo.
echo   使用方法：
echo     方式1（推荐）：双击 start_gui.bat 打开图形界面
echo     方式2：命令行输入 subalign --help 查看帮助
echo.
echo   如需 GPU 加速（可选，显著提速）：
echo     pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu118
echo     pip install whisperx
echo.
pause
