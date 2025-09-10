#!/usr/bin/env python3
"""
Calendar Busy Light Service
Monitors Google Calendar and controls Tuya smart switch based on meeting status.
"""

import os
import time
import json
import logging
import threading
import socket
import random
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

import tinytuya
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('/app/logs/calendar_busy_light.log')
    ]
)
logger = logging.getLogger(__name__)

class NetworkUtils:
    """Utility class for network connectivity checks and retry logic"""
    
    @staticmethod
    def is_network_available(timeout: int = 5) -> bool:
        """Check if network connectivity is available"""
        try:
            # Try to connect to Google's DNS server
            socket.create_connection(("8.8.8.8", 53), timeout=timeout)
            return True
        except (socket.timeout, socket.error, OSError):
            return False
    
    @staticmethod
    def wait_for_network(max_wait: int = 300, check_interval: int = 10) -> bool:
        """Wait for network connectivity to be restored"""
        logger.info("🌐 Waiting for network connectivity...")
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
            if NetworkUtils.is_network_available():
                logger.info("✅ Network connectivity restored")
                return True
            
            logger.info(f"❌ Network still unavailable, retrying in {check_interval}s...")
            time.sleep(check_interval)
        
        logger.error(f"❌ Network not available after {max_wait}s")
        return False
    
    @staticmethod
    def retry_with_exponential_backoff(func, max_retries: int = 5, initial_delay: float = 1.0, max_delay: float = 60.0):
        """Retry a function with exponential backoff"""
        for attempt in range(max_retries):
            try:
                return func()
            except Exception as e:
                if attempt == max_retries - 1:
                    raise e
                
                delay = min(initial_delay * (2 ** attempt) + random.uniform(0, 1), max_delay)
                logger.warning(f"Attempt {attempt + 1} failed: {e}. Retrying in {delay:.1f}s...")
                time.sleep(delay)
        
        raise Exception(f"All {max_retries} retry attempts failed")

class TuyaController:
    """Controls Tuya smart switch with cloud API connection recovery"""
    
    def __init__(self, device_id: str, api_key: str, api_secret: str, api_region: str = 'eu', device_ip: str = None, local_key: str = None, version: float = 3.3):
        self.device_id = device_id
        self.api_key = api_key
        self.api_secret = api_secret
        self.api_region = api_region
        # Keep legacy parameters for backward compatibility but prefer cloud API
        self.device_ip = device_ip
        self.local_key = local_key
        self.version = version
        self.cloud = None
        self.device = None
        self.last_state = None
        self.connection_verified = False
        self.last_successful_connection = None
        self.use_cloud_api = True  # Default to cloud API
        
    def connect(self) -> bool:
        """Initialize connection to Tuya device with retry logic"""
        def _connect():
            if self.use_cloud_api:
                # Use cloud API
                self.cloud = tinytuya.Cloud(
                    apiRegion=self.api_region,
                    apiKey=self.api_key,
                    apiSecret=self.api_secret,
                    apiDeviceID=self.device_id
                )
                
                # Test connection by getting device status
                status = self.cloud.getstatus(self.device_id)
                if status.get('success') and status.get('result'):
                    # Find switch status in the result array
                    switch_status = None
                    for item in status['result']:
                        if item.get('code') == 'switch':
                            switch_status = item.get('value')
                            break
                    
                    if switch_status is not None:
                        self.connection_verified = True
                        self.last_state = switch_status
                        self.last_successful_connection = time.time()
                        logger.info(f"✅ Tuya cloud device connected successfully. Current state: {self.last_state}")
                        return True
                    else:
                        raise Exception(f"Switch status not found in cloud response: {status}")
                else:
                    raise Exception(f"Invalid cloud device status: {status}")
            else:
                # Fallback to local network connection
                self.device = tinytuya.OutletDevice(self.device_id, self.device_ip, self.local_key)
                self.device.set_version(self.version)
                
                # Test connection
                status = self.device.status()
                if 'dps' in status and '1' in status['dps']:
                    self.connection_verified = True
                    self.last_state = status['dps']['1']
                    self.last_successful_connection = time.time()
                    logger.info(f"✅ Tuya local device connected successfully. Current state: {self.last_state}")
                    return True
                else:
                    self.connection_verified = False
                    raise Exception(f"Invalid device status: {status}")
        
        try:
            return NetworkUtils.retry_with_exponential_backoff(_connect, max_retries=3)
        except Exception as e:
            logger.error(f"❌ Tuya connection failed after retries: {e}")
            self.connection_verified = False
            return False
    
    def ensure_connection(self) -> bool:
        """Ensure device connection is active, reconnect if needed"""
        # Check if we need to reconnect (connection older than 5 minutes or not verified)
        if (not self.connection_verified or 
            not self.last_successful_connection or
            time.time() - self.last_successful_connection > 300):
            
            logger.info("🔄 Reconnecting to Tuya device...")
            return self.connect()
        
        # Test existing connection
        try:
            if self.use_cloud_api and self.cloud:
                status = self.cloud.getstatus(self.device_id)
                if status.get('success'):
                    self.last_successful_connection = time.time()
                    return True
                else:
                    logger.warning("⚠️ Tuya cloud device connection test failed, reconnecting...")
                    return self.connect()
            elif self.device:
                status = self.device.status()
                if 'dps' in status:
                    self.last_successful_connection = time.time()
                    return True
                else:
                    logger.warning("⚠️ Tuya local device connection test failed, reconnecting...")
                    return self.connect()
            else:
                logger.warning("⚠️ No device connection available, reconnecting...")
                return self.connect()
        except Exception as e:
            logger.warning(f"⚠️ Tuya connection check failed: {e}, reconnecting...")
            return self.connect()
    
    def set_state(self, state: bool) -> bool:
        """Set switch state (True=ON, False=OFF) with connection recovery"""
        # Ensure we have a valid connection
        if not self.ensure_connection():
            logger.error("❌ Cannot establish device connection")
            return False
        
        def _set_state():
            if self.use_cloud_api and self.cloud:
                # Use cloud API
                result = self.cloud.sendcommand(self.device_id, {
                    'commands': [{'code': 'switch', 'value': state}]
                })
                if result.get('success'):
                    self.last_state = state
                    logger.info(f"🔌 Switch {'ON' if state else 'OFF'} (via cloud)")
                    return True
                else:
                    raise Exception(f"Cloud device returned error: {result}")
            else:
                # Use local connection
                result = self.device.set_status(state, '1')
                if 'Error' not in str(result):
                    self.last_state = state
                    logger.info(f"🔌 Switch {'ON' if state else 'OFF'} (via local)")
                    return True
                else:
                    raise Exception(f"Local device returned error: {result}")
        
        try:
            return NetworkUtils.retry_with_exponential_backoff(_set_state, max_retries=3)
        except Exception as e:
            logger.error(f"❌ Failed to set switch state after retries: {e}")
            # Mark connection as invalid so next call will reconnect
            self.connection_verified = False
            return False
    
    def flash(self, times: int = 3, duration: float = 1) -> bool:
        """Flash the switch a specified number of times"""
        if not (self.cloud or self.device):
            return False
            
        logger.info(f"💡 Flashing switch {times} times")
        original_state = self.last_state
        
        try:
            for i in range(times):
                # Turn on
                if not self.set_state(True):
                    return False
                time.sleep(duration)
                
                # Turn off
                if not self.set_state(False):
                    return False
                time.sleep(duration)
            
            # Restore original state
            if original_state is not None:
                self.set_state(original_state)
            
            return True
        except Exception as e:
            logger.error(f"❌ Error during flash sequence: {e}")
            return False
    
    def flash_error(self, stop_event: threading.Event):
        """Flash continuously to indicate error state"""
        logger.warning("🚨 Starting error flash sequence")
        while not stop_event.is_set():
            self.set_state(True)
            if stop_event.wait(0.3):
                break
            self.set_state(False)
            if stop_event.wait(0.3):
                break

class GoogleCalendarMonitor:
    """Monitors Google Calendar for busy status with robust error handling"""
    
    SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']
    
    def __init__(self, credentials_path: str = '/app/data/credentials.json', 
                 token_path: str = '/app/data/token.json'):
        self.credentials_path = credentials_path
        self.token_path = token_path
        self.service = None
        self.calendar_id = 'primary'
        self.last_successful_auth = None
        self.credentials = None
        
    def authenticate(self) -> bool:
        """Authenticate with Google Calendar API with enhanced error handling"""
        def _authenticate():
            creds = None
            
            # Load existing token
            if os.path.exists(self.token_path):
                try:
                    creds = Credentials.from_authorized_user_file(self.token_path, self.SCOPES)
                    logger.info("📋 Loaded existing Google Calendar credentials")
                except Exception as e:
                    logger.warning(f"⚠️ Error loading token, will re-authenticate: {e}")
            
            # If no valid credentials, authenticate
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    try:
                        creds.refresh(Request())
                        logger.info("🔄 Refreshed Google Calendar credentials")
                    except Exception as e:
                        logger.warning(f"⚠️ Token refresh failed, need new auth: {e}")
                        # Clear the token file and try full auth
                        if os.path.exists(self.token_path):
                            os.remove(self.token_path)
                        creds = None
                
                if not creds:
                    if not os.path.exists(self.credentials_path):
                        raise Exception(f"Credentials file not found: {self.credentials_path}")
                    
                    # For containerized environments, we can't run interactive auth
                    # The user must provide a valid token.json file
                    raise Exception("No valid credentials available. Please provide valid token.json file.")
                
                # Save credentials
                try:
                    with open(self.token_path, 'w') as token:
                        token.write(creds.to_json())
                    logger.info("💾 Saved authentication token")
                except Exception as e:
                    logger.warning(f"⚠️ Could not save token: {e}")
            
            # Build service
            self.service = build('calendar', 'v3', credentials=creds)
            self.credentials = creds
            self.last_successful_auth = time.time()
            logger.info("✅ Google Calendar service initialized")
            return True
        
        try:
            return NetworkUtils.retry_with_exponential_backoff(_authenticate, max_retries=3)
        except Exception as e:
            logger.error(f"❌ Google Calendar authentication failed after retries: {e}")
            return False
    
    def ensure_authenticated(self) -> bool:
        """Ensure we have valid authentication, re-authenticate if needed"""
        # Check if we need to re-authenticate (auth older than 30 minutes or service is None)
        if (not self.service or 
            not self.last_successful_auth or
            time.time() - self.last_successful_auth > 1800):  # 30 minutes
            
            logger.info("🔄 Re-authenticating with Google Calendar...")
            return self.authenticate()
        
        # Check if credentials are still valid
        if self.credentials and self.credentials.expired:
            logger.info("🔄 Credentials expired, refreshing...")
            return self.authenticate()
        
        return True
    
    def get_todays_events(self) -> list[Dict[str, Any]]:
        """Get all events for today"""
        if not self.service:
            return []
        
        try:
            # Get start and end of today in UTC
            now = datetime.utcnow()
            start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end_of_day = now.replace(hour=23, minute=59, second=59, microsecond=999999)
            
            events_result = self.service.events().list(
                calendarId=self.calendar_id,
                timeMin=start_of_day.isoformat() + 'Z',
                timeMax=end_of_day.isoformat() + 'Z',
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            return events_result.get('items', [])
            
        except Exception as e:
            logger.error(f"❌ Error getting today's events: {e}")
            return []
    
    def format_event_time(self, event: Dict[str, Any]) -> str:
        """Format event start/end times for display"""
        try:
            start = event['start'].get('dateTime', event['start'].get('date'))
            end = event['end'].get('dateTime', event['end'].get('date'))
            
            # Parse times
            if 'T' in start:  # DateTime format
                start_dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
                end_dt = datetime.fromisoformat(end.replace('Z', '+00:00'))
                return f"{start_dt.strftime('%H:%M')}-{end_dt.strftime('%H:%M')}"
            else:  # All-day event
                return "All day"
        except Exception:
            return "Time unknown"
    
    def is_busy_soon(self, lead_time_minutes: int = 1) -> tuple[bool, Optional[str]]:
        """
        Check if user will be busy within lead_time_minutes
        Returns (is_busy, event_summary)
        """
        if not self.ensure_authenticated():
            return False, "Authentication failed"
        
        def _check_busy_soon():
            now = datetime.utcnow()
            check_until = now + timedelta(minutes=lead_time_minutes)
            
            # Get events in the next lead_time_minutes
            events_result = self.service.events().list(
                calendarId=self.calendar_id,
                timeMin=now.isoformat() + 'Z',
                timeMax=check_until.isoformat() + 'Z',
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            events = events_result.get('items', [])
            
            for event in events:
                # Check if event shows as busy
                transparency = event.get('transparency', 'opaque')
                if transparency == 'opaque':  # opaque = busy, transparent = free
                    summary = event.get('summary', 'Busy')
                    start_time = event['start'].get('dateTime', event['start'].get('date'))
                    time_str = self.format_event_time(event)
                    logger.info(f"📅 NEW UPCOMING EVENT: {summary} ({time_str})")
                    return True, summary
            
            return False, None
        
        try:
            return NetworkUtils.retry_with_exponential_backoff(_check_busy_soon, max_retries=3)
        except HttpError as e:
            logger.error(f"❌ Google Calendar API error: {e}")
            return False, f"API Error: {e}"
        except Exception as e:
            logger.error(f"❌ Error checking calendar: {e}")
            return False, f"Error: {e}"
    
    def is_currently_busy(self) -> tuple[bool, Optional[str]]:
        """
        Check if user is currently in a meeting
        Returns (is_busy, event_summary)
        """
        if not self.ensure_authenticated():
            return False, "Authentication failed"
        
        def _check_currently_busy():
            now = datetime.utcnow()
            
            # Get current events
            events_result = self.service.events().list(
                calendarId=self.calendar_id,
                timeMin=now.isoformat() + 'Z',
                timeMax=now.isoformat() + 'Z',
                singleEvents=True
            ).execute()
            
            events = events_result.get('items', [])
            
            for event in events:
                start = event['start'].get('dateTime', event['start'].get('date'))
                end = event['end'].get('dateTime', event['end'].get('date'))
                
                # Parse times
                start_dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
                end_dt = datetime.fromisoformat(end.replace('Z', '+00:00'))
                now_dt = now.replace(tzinfo=start_dt.tzinfo)
                
                # Check if currently in meeting
                if start_dt <= now_dt <= end_dt:
                    transparency = event.get('transparency', 'opaque')
                    if transparency == 'opaque':
                        summary = event.get('summary', 'Busy')
                        logger.info(f"📅 Currently in meeting: {summary}")
                        return True, summary
            
            return False, None
        
        try:
            return NetworkUtils.retry_with_exponential_backoff(_check_currently_busy, max_retries=3)
        except Exception as e:
            logger.error(f"❌ Error checking current calendar status: {e}")
            return False, f"Error: {e}"

class BusyLightService:
    """Main service orchestrating calendar monitoring and light control"""
    
    def __init__(self):
        # Load configuration from environment - NO DEFAULT VALUES FOR SECRETS
        self.device_id = os.getenv('TUYA_DEVICE_ID')
        self.device_ip = os.getenv('TUYA_DEVICE_IP')
        self.local_key = os.getenv('TUYA_LOCAL_KEY')
        self.device_version = float(os.getenv('TUYA_VERSION', '3.3'))
        self.lead_time = int(os.getenv('LEAD_TIME_MINUTES', '2'))
        self.poll_interval = int(os.getenv('POLL_INTERVAL_SECONDS', '30'))
        
        # Load Tuya Cloud API credentials - REQUIRED FROM ENVIRONMENT
        self.api_key = os.getenv('TUYA_API_KEY')
        self.api_secret = os.getenv('TUYA_API_SECRET')
        self.api_region = os.getenv('TUYA_API_REGION', 'eu')
        
        # Validate required credentials
        if not all([self.device_id, self.api_key, self.api_secret]):
            raise ValueError("Missing required environment variables: TUYA_DEVICE_ID, TUYA_API_KEY, TUYA_API_SECRET")
        
        # Initialize components with cloud API support
        self.tuya = TuyaController(
            device_id=self.device_id, 
            api_key=self.api_key,
            api_secret=self.api_secret,
            api_region=self.api_region,
            device_ip=self.device_ip, 
            local_key=self.local_key, 
            version=self.device_version
        )
        self.calendar = GoogleCalendarMonitor()
        
        # State tracking
        self.is_busy = False
        self.error_flash_thread = None
        self.error_stop_event = threading.Event()
        self.running = True
        
        # Heartbeat mechanism
        self.last_heartbeat = time.time()
        self.heartbeat_file = '/app/data/heartbeat.txt'
        self.heartbeat_thread = None
        self.heartbeat_stop_event = threading.Event()
        
    def startup_sequence(self) -> bool:
        """Perform startup checks and flash sequence"""
        logger.info("🚀 Starting Calendar Busy Light Service")
        
        # Test Tuya connection
        if not self.tuya.connect():
            logger.error("❌ Failed to connect to Tuya device")
            return False
        
        # Test Google Calendar
        if not self.calendar.authenticate():
            logger.error("❌ Failed to authenticate with Google Calendar")
            return False
        
        # Success flash sequence
        logger.info("✅ All systems connected - performing startup flash")
        self.tuya.flash(times=3, duration=1)
        
        # Immediate status check and light setting
        logger.info("🔍 Checking current calendar status...")
        try:
            busy_soon, event_soon = self.calendar.is_busy_soon(self.lead_time)
            currently_busy, current_event = self.calendar.is_currently_busy()
            
            should_be_on = busy_soon or currently_busy
            current_event_name = event_soon or current_event
            
            if should_be_on:
                self.is_busy = True
                if busy_soon and not currently_busy:
                    logger.info(f"⚠️  STARTUP: Upcoming meeting - {current_event_name} (starting in {self.lead_time} minute)")
                else:
                    logger.info(f"🔴 STARTUP: Currently busy - {current_event_name}")
                logger.info("💡 Setting light ON immediately")
                self.tuya.set_state(True)
            else:
                self.is_busy = False
                logger.info("🟢 STARTUP: Currently free")
                logger.info("💡 Setting light OFF")
                self.tuya.set_state(False)
                
        except Exception as e:
            logger.error(f"❌ Error during startup status check: {e}")
            # Default to off if there's an error
            self.is_busy = False
            self.tuya.set_state(False)
        
        return True
    
    def update_heartbeat(self):
        """Update heartbeat timestamp"""
        self.last_heartbeat = time.time()
        try:
            with open(self.heartbeat_file, 'w') as f:
                f.write(f"{self.last_heartbeat}\n")
        except Exception as e:
            logger.warning(f"⚠️ Could not write heartbeat file: {e}")
    
    def start_heartbeat_monitor(self):
        """Start heartbeat monitoring thread"""
        def heartbeat_worker():
            while not self.heartbeat_stop_event.is_set():
                try:
                    self.update_heartbeat()
                    if self.heartbeat_stop_event.wait(30):  # Update every 30 seconds
                        break
                except Exception as e:
                    logger.error(f"❌ Heartbeat error: {e}")
        
        if self.heartbeat_thread and self.heartbeat_thread.is_alive():
            return
        
        self.heartbeat_stop_event.clear()
        self.heartbeat_thread = threading.Thread(target=heartbeat_worker, daemon=True)
        self.heartbeat_thread.start()
        logger.info("💓 Heartbeat monitor started")
    
    def stop_heartbeat_monitor(self):
        """Stop heartbeat monitoring"""
        if self.heartbeat_thread and self.heartbeat_thread.is_alive():
            self.heartbeat_stop_event.set()
            self.heartbeat_thread.join(timeout=2)
            logger.info("💓 Heartbeat monitor stopped")
    
    def start_error_flash(self):
        """Start continuous error flashing"""
        if self.error_flash_thread and self.error_flash_thread.is_alive():
            return
        
        self.error_stop_event.clear()
        self.error_flash_thread = threading.Thread(
            target=self.tuya.flash_error, 
            args=(self.error_stop_event,)
        )
        self.error_flash_thread.start()
    
    def stop_error_flash(self):
        """Stop error flashing"""
        if self.error_flash_thread and self.error_flash_thread.is_alive():
            self.error_stop_event.set()
            self.error_flash_thread.join(timeout=2)
    
    def log_daily_events(self):
        """Log a summary of today's events"""
        try:
            events = self.calendar.get_todays_events()
            
            if not events:
                logger.info("📋 Today's Schedule: No events found")
                return
            
            logger.info("📋 Today's Schedule:")
            busy_events = []
            free_events = []
            
            for event in events:
                summary = event.get('summary', 'Untitled Event')
                time_str = self.calendar.format_event_time(event)
                transparency = event.get('transparency', 'opaque')
                
                if transparency == 'opaque':  # Busy event
                    busy_events.append(f"   🔴 {time_str} - {summary}")
                else:  # Free time
                    free_events.append(f"   🟢 {time_str} - {summary}")
            
            # Log busy events first
            for event in busy_events:
                logger.info(event)
            
            # Then free events
            for event in free_events:
                logger.info(event)
                
            logger.info(f"📊 Total: {len(busy_events)} busy, {len(free_events)} free events")
            
        except Exception as e:
            logger.error(f"❌ Error logging daily events: {e}")
    
    def run(self):
        """Main service loop"""
        if not self.startup_sequence():
            logger.error("❌ Startup failed - starting error flash")
            self.start_error_flash()
            return
        
        # Start heartbeat monitoring
        self.start_heartbeat_monitor()
        
        logger.info("🔄 Starting monitoring loop (checking on the minute)")
        
        # Sync to the next minute boundary
        now = datetime.now()
        seconds_until_next_minute = 60 - now.second - (now.microsecond / 1000000)
        next_check_time = (now + timedelta(seconds=seconds_until_next_minute)).strftime('%H:%M:%S')
        
        if seconds_until_next_minute > 1:  # Only wait if more than 1 second
            logger.info(f"⏳ Syncing to minute boundary. First check at {next_check_time}")
            time.sleep(seconds_until_next_minute)
        
        # Track previous state to detect new events
        previous_busy_state = False
        previous_event_name = None
        
        while self.running:
            try:
                # Check network connectivity first
                if not NetworkUtils.is_network_available():
                    logger.warning("🌐 Network unavailable, waiting for connectivity...")
                    if not NetworkUtils.wait_for_network(max_wait=300):  # Wait up to 5 minutes
                        logger.error("❌ Network still unavailable, continuing with error state")
                        self.start_error_flash()
                        time.sleep(self.poll_interval)
                        continue
                    
                    # Re-establish connections after network comes back
                    logger.info("🔄 Network restored, re-establishing connections...")
                    if not self.tuya.connect():
                        logger.warning("⚠️ Failed to reconnect to Tuya device")
                    if not self.calendar.authenticate():
                        logger.warning("⚠️ Failed to re-authenticate with Google Calendar")
                
                logger.info(f"⏰ Calendar check at {datetime.now().strftime('%H:%M:%S')}")
                
                # Get today's events summary
                self.log_daily_events()
                
                # Check if busy soon or currently busy
                busy_soon, event_soon = self.calendar.is_busy_soon(self.lead_time)
                currently_busy, current_event = self.calendar.is_currently_busy()
                
                should_be_on = busy_soon or currently_busy
                current_event_name = event_soon or current_event
                
                # Log status
                if should_be_on:
                    if not previous_busy_state or current_event_name != previous_event_name:
                        if busy_soon and not currently_busy:
                            logger.info(f"⚠️  UPCOMING: {current_event_name} (starting in {self.lead_time} minutes)")
                        else:
                            logger.info(f"🔴 CURRENTLY BUSY: {current_event_name}")
                else:
                    if previous_busy_state:
                        logger.info("🟢 NOW FREE")
                    else:
                        logger.info("🟢 Still free - no upcoming meetings")
                
                # Update light state if changed
                if should_be_on != self.is_busy:
                    self.is_busy = should_be_on
                    
                    if should_be_on:
                        logger.info(f"💡 Turning light ON for: {current_event_name}")
                        self.tuya.set_state(True)
                    else:
                        logger.info("💡 Turning light OFF - available")
                        self.tuya.set_state(False)
                
                # Update tracking variables
                previous_busy_state = should_be_on
                previous_event_name = current_event_name
                
                # Stop error flashing if we're working
                self.stop_error_flash()
                
                # Calculate time until next minute
                now = datetime.now()
                seconds_until_next_minute = 60 - now.second - (now.microsecond / 1000000)
                
                logger.info(f"✅ Check complete. Next check at {(now + timedelta(seconds=seconds_until_next_minute)).strftime('%H:%M:%S')}")
                logger.info("-" * 60)  # Separator line
                
                # Wait until the next minute
                time.sleep(seconds_until_next_minute)
                
            except Exception as e:
                logger.error(f"❌ Error in main loop: {e}")
                self.start_error_flash()
                time.sleep(self.poll_interval)
    
    def stop(self):
        """Stop the service"""
        logger.info("🛑 Stopping Calendar Busy Light Service")
        self.running = False
        self.stop_error_flash()
        self.stop_heartbeat_monitor()
        
        # Turn off light
        if self.tuya.connection_verified:
            self.tuya.set_state(False)

def main():
    """Main entry point"""
    # Ensure log directory exists
    os.makedirs('/app/logs', exist_ok=True)
    
    service = BusyLightService()
    
    try:
        service.run()
    except KeyboardInterrupt:
        logger.info("🛑 Received interrupt signal")
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
    finally:
        service.stop()

if __name__ == "__main__":
    main()
