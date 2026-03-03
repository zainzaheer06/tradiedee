@echo off
echo ========================================
echo Installing Call Recording Dependencies
echo ========================================
echo.

echo Installing oss2 (Alibaba Cloud OSS SDK)...
pip install oss2==2.18.0

echo.
echo ========================================
echo Installation Complete!
echo ========================================
echo.
echo Next steps:
echo 1. Make sure .env has OSS credentials
echo 2. Start agent worker: python agent.py start
echo 3. Start Flask app: python app.py
echo 4. Make a test call
echo 5. Check call logs for recording
echo.
echo See RECORDING_SETUP.md for details
pause
