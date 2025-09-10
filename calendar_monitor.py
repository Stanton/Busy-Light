#!/usr/bin/env python3
"""
Google Calendar Busy/Free Monitor
A simple application that monitors Google Calendar for busy/free status
"""

import os
import time
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Google Calendar API imports
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Load environment variables
load_dotenv()

# Configuration
SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']
TOKEN_FILE = '/app/data/token.json'
CREDENTIALS_FILE = '/app/data/credentials.json'
STATUS_FILE = '/app/data/calendar_status.txt'

# Environment variables
CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL_SECONDS', 60))
LOOKAHEAD_MINUTES = int(os.getenv('CALENDAR_LOOKAHEAD_MINUTES', 30))
TIMEZONE = os.getenv('TIMEZONE', 'UTC')

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/app/calendar_monitor.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class GoogleCalendarMonitor:
    """Monitor Google Calendar for busy/free status"""
    
    def __init__(self):
        self.service = None
        self.setup_google_calendar()
        logger.info("📅 Google Calendar Monitor initialized")
        
    def setup_google_calendar(self):
        """Set up Google Calendar API authentication"""
        creds = None
        
        # Load existing token
        if os.path.exists(TOKEN_FILE):
            creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        
        # If no valid credentials, go through auth flow
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                    logger.info("🔄 Refreshed Google Calendar credentials")
                except Exception as e:
                    logger.error(f"❌ Failed to refresh credentials: {e}")
                    creds = None
            
            if not creds:
                if not os.path.exists(CREDENTIALS_FILE):
                    raise FileNotFoundError(
                        f"Google credentials file not found: {CREDENTIALS_FILE}\n"
                        "Please download credentials.json from Google Cloud Console"
                    )
                
                flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
                creds = flow.run_local_server(port=0)
                logger.info("✅ New Google Calendar credentials obtained")
            
            # Save credentials for next run
            with open(TOKEN_FILE, 'w') as token:
                token.write(creds.to_json())
                logger.info("💾 Saved Google Calendar credentials")
        
        # Build the service
        self.service = build('calendar', 'v3', credentials=creds)
        logger.info("🔗 Connected to Google Calendar API")
    
    def get_calendar_status(self):
        """Check if user is currently busy based on calendar events"""
        try:
            # Calculate time range
            now = datetime.utcnow()
            end_time = now + timedelta(minutes=LOOKAHEAD_MINUTES)
            
            # Format times for API
            time_min = now.isoformat() + 'Z'
            time_max = end_time.isoformat() + 'Z'
            
            logger.debug(f"🔍 Checking calendar from {time_min} to {time_max}")
            
            # Get events from primary calendar
            events_result = self.service.events().list(
                calendarId='primary',
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            events = events_result.get('items', [])
            
            # Filter for events that are happening now or soon
            busy_events = []
            for event in events:
                # Skip events without start time (all-day events)
                if 'dateTime' not in event.get('start', {}):
                    continue
                
                # Skip declined events
                attendees = event.get('attendees', [])
                user_status = None
                for attendee in attendees:
                    if attendee.get('self'):
                        user_status = attendee.get('responseStatus')
                        break
                
                if user_status == 'declined':
                    logger.debug(f"⏭️  Skipping declined event: {event.get('summary', 'No title')}")
                    continue
                
                # Skip events marked as free
                transparency = event.get('transparency', 'opaque')
                if transparency == 'transparent':
                    logger.debug(f"⏭️  Skipping transparent event: {event.get('summary', 'No title')}")
                    continue
                
                busy_events.append(event)
                logger.debug(f"📅 Found busy event: {event.get('summary', 'No title')}")
            
            # Determine busy status
            is_busy = len(busy_events) > 0
            
            # Create status info
            status_info = {
                'is_busy': is_busy,
                'event_count': len(busy_events),
                'total_events': len(events),
                'check_time': now.isoformat(),
                'lookahead_minutes': LOOKAHEAD_MINUTES,
                'events': [
                    {
                        'summary': event.get('summary', 'No title'),
                        'start': event.get('start', {}).get('dateTime', ''),
                        'end': event.get('end', {}).get('dateTime', '')
                    }
                    for event in busy_events
                ]
            }
            
            logger.info(f"📊 Calendar status: {'🔴 BUSY' if is_busy else '🟢 FREE'} "
                       f"({len(busy_events)} busy events)")
            
            return status_info
            
        except HttpError as error:
            logger.error(f"❌ Google Calendar API error: {error}")
            return None
        except Exception as error:
            logger.error(f"❌ Calendar check failed: {error}")
            return None
    
    def save_status(self, status_info):
        """Save current status to file"""
        try:
            status_text = f"BUSY: {status_info['is_busy']}\n"
            status_text += f"EVENTS: {status_info['event_count']}\n"
            status_text += f"CHECKED: {status_info['check_time']}\n"
            status_text += f"LOOKAHEAD: {status_info['lookahead_minutes']} minutes\n"
            
            with open(STATUS_FILE, 'w') as f:
                f.write(status_text)
                
            logger.debug(f"💾 Status saved to {STATUS_FILE}")
            
        except Exception as e:
            logger.error(f"❌ Failed to save status: {e}")
    
    def run_monitoring_loop(self):
        """Run the main monitoring loop"""
        logger.info(f"🚀 Starting calendar monitoring (checking every {CHECK_INTERVAL}s)")
        logger.info(f"⏰ Lookahead window: {LOOKAHEAD_MINUTES} minutes")
        
        try:
            while True:
                # Check calendar status
                status_info = self.get_calendar_status()
                
                if status_info:
                    # Save status
                    self.save_status(status_info)
                    
                    # Log current status
                    if status_info['is_busy']:
                        logger.info(f"🔴 BUSY - {status_info['event_count']} active events")
                        for event in status_info['events']:
                            logger.info(f"   📅 {event['summary']}")
                    else:
                        logger.info(f"🟢 FREE - No busy events in next {LOOKAHEAD_MINUTES} minutes")
                else:
                    logger.warning("⚠️  Could not determine calendar status")
                
                # Wait before next check
                logger.debug(f"😴 Sleeping for {CHECK_INTERVAL} seconds...")
                time.sleep(CHECK_INTERVAL)
                
        except KeyboardInterrupt:
            logger.info("👋 Calendar monitoring stopped by user")
        except Exception as e:
            logger.error(f"❌ Monitoring loop error: {e}")
            raise

def main():
    """Main application entry point"""
    logger.info("🚀 Google Calendar Monitor Starting")
    logger.info(f"⚙️  Configuration:")
    logger.info(f"   Check interval: {CHECK_INTERVAL} seconds")
    logger.info(f"   Lookahead: {LOOKAHEAD_MINUTES} minutes")
    logger.info(f"   Timezone: {TIMEZONE}")
    logger.info(f"   Status file: {STATUS_FILE}")
    
    try:
        monitor = GoogleCalendarMonitor()
        monitor.run_monitoring_loop()
    except Exception as e:
        logger.error(f"❌ Application failed: {e}")
        return 1
    
    return 0

if __name__ == '__main__':
    exit(main())

