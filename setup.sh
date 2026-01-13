#!/bin/bash

# RecallAI Quick Setup Script
# Run this after cloning the repository

echo "🚀 Setting up RecallAI..."
echo ""

# Check Python version
echo "Checking Python version..."
python3 --version

# Create venv
echo ""
echo "Creating virtual environment..."
python3 -m venv venv

# Activate venv
echo ""
echo "Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo ""
echo "Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Create necessary dirs
echo ""
echo "Creating directories..."
mkdir -p uploads
mkdir -p data
touch uploads/.gitkeep

# Copy env file
echo ""
if [ ! -f .env ]; then
    echo "Creating .env file..."
    cp .env.example .env
    echo "⚠️  IMPORTANT: Edit .env and add your GEMINI_API_KEY"
    echo "   Get your key from: https://makersuite.google.com/app/apikey"
else
    echo ".env file already exists"
fi

echo ""
echo "Creating sample lecture file..."
echo "Note: You'll need to convert sample_lecture.txt to PDF manually"
echo "Or download your own lecture PDFs to the data/ folder"

echo ""
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "1. Edit .env and add your GEMINI_API_KEY"
echo "2. Add lecture PDFs to data/ folder (or upload via web interface)"
echo "3. Run: python app.py"
echo "4. Open: http://localhost:5000"
echo ""
echo "To run tests: python run_tests.py"
echo ""
echo "Happy studying! 📚"