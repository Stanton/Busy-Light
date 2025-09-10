#!/bin/bash

# Calendar Busy Light Startup Script
# This script sets up and starts the calendar busy light service

set -e

echo "🚀 Calendar Busy Light Setup"
echo "=============================="

# Check if Docker is running
if ! docker info >/dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker first."
    exit 1
fi

# Check if docker-compose is available
if ! command -v docker-compose >/dev/null 2>&1; then
    echo "❌ docker-compose not found. Please install Docker Compose."
    exit 1
fi

# Create necessary directories
echo "📁 Creating directories..."
mkdir -p data logs

# Check for Google credentials
if [ ! -f "data/credentials.json" ]; then
    echo "❌ Google Calendar credentials not found!"
    echo ""
    echo "Please follow these steps:"
    echo "1. Go to https://console.cloud.google.com/"
    echo "2. Create a project and enable Google Calendar API"
    echo "3. Create OAuth2 credentials (Desktop Application)"
    echo "4. Download as 'credentials.json'"
    echo "5. Place the file in the 'data/' directory"
    echo ""
    echo "Then run this script again."
    exit 1
fi

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo "⚠️  No .env file found. Please copy env.example to .env and configure:"
    echo "   cp env.example .env"
    echo "   # Then edit .env with your actual device details:"
    echo "   - TUYA_DEVICE_ID"
    echo "   - TUYA_DEVICE_IP" 
    echo "   - TUYA_LOCAL_KEY"
    echo "   - TUYA_API_KEY"
    echo "   - TUYA_API_SECRET"
    echo ""
fi

# Build and start the service
echo "🔨 Building Docker image..."
docker-compose build

echo "🚀 Starting Calendar Busy Light service..."
docker-compose up -d

# Wait a moment for startup
sleep 3

# Show status
echo ""
echo "📊 Service Status:"
docker-compose ps

echo ""
echo "📋 Next Steps:"
echo "1. Check logs: docker-compose logs -f calendar-busy-light"
echo "2. Watch for 3 startup flashes on your light"
echo "3. Complete Google authentication if prompted in logs"
echo "4. Your busy light is now active!"
echo ""
echo "🛑 To stop: docker-compose down"
echo "📖 For help: see README_BUSY_LIGHT.md"
