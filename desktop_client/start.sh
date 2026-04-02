#!/bin/bash

echo "========================================"
echo "  AstrBot VTuber Desktop Client"
echo "========================================"
echo ""

cd "$(dirname "$0")"

if [ ! -d "node_modules" ]; then
    echo "[INFO] First time running, installing dependencies..."
    echo ""
    
    if command -v pnpm &> /dev/null; then
        echo "[INFO] Found pnpm, using pnpm install..."
        pnpm install
    elif command -v npm &> /dev/null; then
        echo "[INFO] Found npm, using npm install..."
        npm install
    else
        echo "[ERROR] Neither pnpm nor npm found!"
        echo "[ERROR] Please install Node.js first: https://nodejs.org/"
        exit 1
    fi
    
    if [ $? -ne 0 ]; then
        echo "[ERROR] Failed to install dependencies!"
        exit 1
    fi
    echo ""
    echo "[INFO] Dependencies installed successfully!"
    echo ""
fi

echo "[INFO] Starting AstrBot VTuber Desktop Client..."
echo ""

if command -v pnpm &> /dev/null; then
    pnpm dev
else
    npm run dev
fi

if [ $? -ne 0 ]; then
    echo ""
    echo "[ERROR] Failed to start the application!"
    read -p "Press Enter to exit..."
fi
