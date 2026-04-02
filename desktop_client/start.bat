@echo off
chcp 65001 >nul
title AstrBot VTuber Desktop Client

echo ========================================
echo   AstrBot VTuber Desktop Client
echo ========================================
echo.

cd /d "%~dp0"

if not exist "node_modules" (
    echo [INFO] First time running, installing dependencies...
    echo.
    
    where pnpm >nul 2>nul
    if %errorlevel% equ 0 (
        echo [INFO] Found pnpm, using pnpm install...
        pnpm install
    ) else (
        where npm >nul 2>nul
        if %errorlevel% equ 0 (
            echo [INFO] Found npm, using npm install...
            npm install
        ) else (
            echo [ERROR] Neither pnpm nor npm found!
            echo [ERROR] Please install Node.js first: https://nodejs.org/
            echo.
            pause
            exit /b 1
        )
    )
    
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to install dependencies!
        pause
        exit /b 1
    )
    echo.
    echo [INFO] Dependencies installed successfully!
    echo.
)

echo [INFO] Starting AstrBot VTuber Desktop Client...
echo.

where pnpm >nul 2>nul
if %errorlevel% equ 0 (
    pnpm dev
) else (
    npm run dev
)

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Failed to start the application!
    pause
)
