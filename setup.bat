@echo off
REM RecallAI Quick Setup Script for Windows

echo 🚀 Setting up RecallAI...
echo.

REM Check Python version
echo Checking Python version...
python --version
echo.

REM Create virtual environment
echo Creating virtual environment...
python -m venv venv
echo.

REM Activate virtual environment
echo Activating virtual environment...
call venv\Scripts\activate
echo.

REM Install dependencies
echo Installing dependencies...
python -m pip install --upgrade pip
pip install -r requirements.txt
echo.

REM Create necessary directories
echo Creating directories...
if not exist "uploads" mkdir uploads
if not exist "data" mkdir data
type nul > uploads\.gitkeep
echo.

REM Copy environment file
if not exist ".env" (
    echo Creating .env file...
    copy .env.example .env
    echo.
    echo ⚠️  IMPORTANT: Edit .env and add your GEMINI_API_KEY
    echo    Get your key from: https://makersuite.google.com/app/apikey
    echo.
) else (
    echo .env file already exists
    echo.
)

echo ✅ Setup complete!
echo.
echo Next steps:
echo 1. Edit .env and add your GEMINI_API_KEY
echo 2. Add lecture PDFs to data\ folder (or upload via web interface)
echo 3. Run: python app.py
echo 4. Open: http://localhost:5000
echo.
echo To run tests: python run_tests.py
echo.
echo Happy studying! 📚
echo.
pause