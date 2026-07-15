@echo off
title Bot Trade Future AI (SOLUSDT)
echo ==============================================
echo       KHOI DONG BOT TRADE SOLANA SCALPING
echo ==============================================
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
call venv\Scripts\activate.bat
python main.py
pause
