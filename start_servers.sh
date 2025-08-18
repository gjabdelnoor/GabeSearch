#!/bin/bash

# Portable Local RAG System Startup Script
# This script starts your SearxNG and GabeSearch MCP Docker services.

echo
echo "========================================================="
echo "  Local RAG System for LM Studio"
echo "  Starting SearxNG and GabeSearch MCP Docker services..."
echo "========================================================="
echo

# Check if Docker is running
if ! docker version > /dev/null 2>&1; then
    echo "ERROR: Docker is not running or not installed."
    echo "Please start Docker Desktop and try again."
    echo
    exit 1
fi

echo "✓ Docker is running"
echo

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "Starting Docker services..."
docker compose up -d

# Check if the Docker command succeeded
if [ $? -ne 0 ]; then
    echo
    echo "ERROR: Failed to start Docker services."
    echo "Please check Docker Desktop for more details."
    echo
    exit 1
fi

echo
echo "Services are starting up..."
echo "Waiting for SearxNG to initialize (45 seconds)..."
sleep 45

echo
echo "========================================================="
echo "Checking service status..."
echo "========================================================="
docker compose ps

echo
echo "========================================================="
echo "Testing SearxNG API..."
echo "========================================================="
if curl -s "http://localhost:8888/search?q=test&format=json" > /dev/null 2>&1; then
    echo "✓ SearxNG API is responding"
else
    echo "Warning: Could not test SearxNG API directly."
    echo "This might be normal - the service may still be starting."
fi

echo
echo "========================================================="
echo "Setup Complete!"
echo "========================================================="
echo
echo "Your local RAG system is now running:"
echo "- SearxNG: http://localhost:8888"
echo "- GabeSearch MCP server: Ready for LM Studio"
echo
echo "Next steps:"
echo "1. Open LM Studio"
echo "2. Add the GabeSearch MCP server using the config in lm-studio-config/mcp.json"
echo "3. Start using web search in your conversations!"
echo
echo "To stop the services later, run: docker compose down"
echo
