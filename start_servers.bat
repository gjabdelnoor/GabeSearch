@echo off
REM Portable Local RAG System Startup Script
REM This script starts your SearxNG and GabeSearch MCP Docker services.

echo.
echo =========================================================
echo   Local RAG System for LM Studio
echo   Starting SearxNG and GabeSearch MCP Docker services...
echo =========================================================
echo.

REM Check if Docker is running
docker version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Docker is not running or not installed.
    echo Please start Docker Desktop and try again.
    echo.
    pause
    exit /b 1
)

echo ✓ Docker is running
echo.

REM Get the directory where this script is located
set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"

echo Starting Docker services...
docker compose up -d

REM Check if the Docker command succeeded
if %errorlevel% neq 0 (
    echo.
    echo ERROR: Failed to start Docker services.
    echo Please check Docker Desktop for more details.
    echo.
    pause
    exit /b %errorlevel%
)

echo.
echo Services are starting up...
echo Waiting for SearxNG to initialize (45 seconds)...
timeout /t 45 /nobreak >nul

echo.
echo =========================================================
echo Checking service status...
echo =========================================================
docker compose ps

echo.
echo =========================================================
echo Testing SearxNG API...
echo =========================================================
curl "http://localhost:8888/search?q=test&format=json" 2>nul
if %errorlevel% neq 0 (
    echo.
    echo Warning: Could not test SearxNG API directly.
    echo This might be normal - the service may still be starting.
) else (
    echo.
    echo ✓ SearxNG API is responding
)

echo.
echo =========================================================
echo Setup Complete!
echo =========================================================
echo.
echo Your local RAG system is now running:
echo - SearxNG: http://localhost:8888
echo - GabeSearch MCP server: Ready for LM Studio
echo.
echo Next steps:
echo 1. Open LM Studio
echo 2. Add the GabeSearch MCP server using the config in lm-studio-config/mcp.json
echo 3. Start using web search in your conversations!
echo.
echo To stop the services later, run: docker compose down
echo.
pause
