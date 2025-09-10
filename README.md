# Calendar Busy Light

A Docker-based service that monitors your Google Calendar and controls a Tuya smart switch to create a visual "busy light" indicator. Perfect for home offices to show when you're in meetings!

## Features

- 🗓️ **Smart Calendar Monitoring**: Monitors Google Calendar with configurable lead time before meetings
- 💡 **Tuya Smart Switch Control**: Controls any Tuya-compatible smart switch/light via cloud API
- 🚨 **Visual Status Indicators**: 
  - 3 flashes on startup = system working
  - Constant flashing = error state
  - Solid on = busy/in meeting
  - Off = available
- 🐳 **Docker Ready**: One-command deployment with Docker Compose
- 🔄 **Auto-recovery**: Automatic error detection and recovery with sleep resilience
- 📊 **Comprehensive Logging**: Detailed logs for monitoring and debugging
- 🔒 **Secure Authentication**: Uses Google OAuth2 with local token storage

## Quick Start

### Prerequisites

- Docker and Docker Compose installed
- Tuya smart switch on your local network
- Google Cloud Console account
- Google Calendar access

### Setup

1. **Clone and navigate to the repository**
   ```bash
   git clone <your-repo>
   cd dnd
   ```

2. **Set up Google Calendar API credentials**
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create a new project or select existing one
   - Enable the Google Calendar API
   - Create credentials (OAuth 2.0 Client ID)
   - Choose "Desktop application" as the application type
   - Download the credentials as `credentials.json`
   - Place the file in the `data/` directory

3. **Configure your Tuya device and environment**
   ```bash
   cp env.example .env
   # Edit .env with your Tuya device details and preferences
   ```

4. **Build and run**
   ```bash
   make setup    # One-time setup
   make run      # Start monitoring
   ```

### Manual Setup

If you prefer manual setup:

```bash
# Build the container
docker-compose build

# Run the calendar busy light
docker-compose up calendar-busy-light

# Or run in background
docker-compose up -d calendar-busy-light
```

## Configuration

Environment variables in `.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `TUYA_DEVICE_ID` | - | Your Tuya device ID |
| `TUYA_DEVICE_IP` | - | Local IP address of your Tuya device |
| `TUYA_LOCAL_KEY` | - | Local key for Tuya device |
| `TUYA_VERSION` | 3.3 | Tuya protocol version |
| `LEAD_TIME_MINUTES` | 2 | Minutes before meeting to turn on light |
| `POLL_INTERVAL_SECONDS` | 60 | How often to check calendar (seconds) |

## Authentication

On first run, the application will:

1. Open a browser window for Google OAuth2 authentication
2. Ask you to sign in and grant calendar access
3. Save the authentication token locally for future runs

The authentication token is stored in `data/token.json` and will be automatically refreshed when needed.

## Output

The monitor provides several types of output:

### Console Logs
- Real-time status updates
- Event details when busy
- Connection and authentication status

### Light Status Indicators

| Light State | Meaning |
|-------------|---------|
| 3 quick flashes | ✅ System startup successful |
| Solid ON | 🔴 Busy (in meeting or meeting starting soon) |
| OFF | 🟢 Available |
| Constant flashing | 🚨 Error (Google Calendar or Tuya connection issue) |

### Application Logs
Detailed logs are saved to `logs/calendar_busy_light.log` on the host system.

## Usage Examples

### Check Current Status
```bash
# View recent logs
docker-compose logs calendar-busy-light --tail 20

# Monitor logs in real-time
docker-compose logs -f calendar-busy-light
```

### Test Tuya Device
```bash
# Test the switch manually
docker-compose run --rm calendar-busy-light python toggle_switch.py
```

### Starting/Stopping Service
```bash
# Start in background
docker-compose up -d calendar-busy-light

# Stop the service
docker-compose down
```

## How It Works

1. **Authentication**: Uses Google OAuth2 to securely access your calendar
2. **Event Detection**: Checks for events starting soon (configurable lead time)
3. **Smart Filtering**: Automatically excludes:
   - Declined events
   - Transparent/free events
   - All-day events
4. **Light Control**: Controls Tuya smart switch via cloud API when busy
5. **Status Indicators**: Visual feedback through light states (flashing, solid, off)
6. **Sleep Resilience**: Handles network disconnections and container recovery
7. **Continuous Monitoring**: Repeats check every N seconds with automatic recovery

## Troubleshooting

### Authentication Issues
```bash
# Clear stored credentials and re-authenticate
rm data/token.json
docker-compose restart calendar-busy-light
```

### Permission Errors
```bash
# Fix data directory permissions
chmod 755 data/
chmod 644 data/*
```

### Light Issues
```bash
# Test Tuya device manually
docker-compose run --rm calendar-busy-light python toggle_switch.py

# Check light constantly flashing (indicates error)
docker-compose logs calendar-busy-light --tail 50
```

### View Detailed Logs
```bash
# Check container logs
docker-compose logs calendar-busy-light

# Or enter the container
docker-compose exec calendar-busy-light bash
cat /app/logs/calendar_busy_light.log
```

## Development

### Local Development
```bash
# Mount source code for live development
docker-compose up calendar-busy-light
# Code changes are automatically reflected
```

### Test Components
```bash
# Test Google Calendar API connection
docker-compose run --rm calendar-busy-light python -c "
from calendar_busy_light import CalendarBusyLight
light = CalendarBusyLight()
print('✅ System initialized successfully!')
"
```

## File Structure

```
.
├── calendar_busy_light.py      # Main busy light application
├── calendar_monitor.py         # Simple calendar monitor (alternative)
├── toggle_switch.py           # Manual switch testing utility
├── monitor_container.sh       # Container monitoring script
├── docker-compose.yml         # Container configuration
├── Dockerfile                 # Container build instructions
├── requirements.txt           # Python dependencies
├── env.example               # Environment variables template
├── data/                     # Persistent data
│   ├── credentials.json      # Google API credentials (not in repo)
│   ├── token.json           # OAuth2 tokens (auto-generated)
│   └── heartbeat.txt        # Heartbeat monitoring file
└── logs/                    # Application logs
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Security

### Best Practices Implemented

- **No Hardcoded Secrets**: All credentials are loaded from environment variables only
- **OAuth2 Tokens**: Google tokens are stored locally and automatically refreshed
- **Secure Communication**: All communication with Google uses HTTPS
- **Minimal Privileges**: Container runs with minimal privileges
- **Gitignore Protection**: All sensitive files are properly excluded from version control

### Important Security Guidelines

⚠️ **NEVER commit real credentials to version control**

1. **Environment Variables**: Always use `.env` file for secrets
   ```bash
   cp env.example .env
   # Edit .env with your actual credentials
   ```

2. **Required Environment Variables**:
   - `TUYA_DEVICE_ID` - Your Tuya device ID
   - `TUYA_API_KEY` - Your Tuya Cloud API key  
   - `TUYA_API_SECRET` - Your Tuya Cloud API secret
   - `TUYA_DEVICE_IP` - Local IP of your device (optional, for local fallback)
   - `TUYA_LOCAL_KEY` - Local key for device (optional, for local fallback)

3. **Credential Sources**:
   - **Google Calendar**: Get credentials from [Google Cloud Console](https://console.cloud.google.com/)
   - **Tuya Cloud API**: Get API credentials from [Tuya IoT Platform](https://iot.tuya.com/cloud/)
   - **Tuya Device Details**: Use `tinytuya` wizard or Tuya Developer console

4. **File Permissions**: Ensure `.env` file has restricted permissions
   ```bash
   chmod 600 .env
   ```

5. **Container Security**: No credentials are baked into the Docker image

### What's Protected by .gitignore

- `.env` files (all variants)
- `credentials.json` and `token.json` (Google)
- All JSON files in `data/` directory
- `tinytuya.json` and other Tuya config files
- Certificate files (`.key`, `.pem`, `.p12`)
- Log files and sensitive directories

## Changelog

### v3.0.0 - Cloud API & Sleep Resilience
- Migrated to Tuya Cloud API for better reliability
- Added comprehensive sleep resilience and auto-recovery
- Enhanced container monitoring with heartbeat system
- Improved error handling and network recovery
- Better timezone handling (Europe/London)

### v2.0.0 - Calendar Busy Light
- Full calendar busy light functionality
- Tuya smart switch integration
- Visual status indicators via light states
- Docker containerization with health checks

### v1.0.0 - Initial Release
- Google Calendar integration
- Basic monitoring functionality