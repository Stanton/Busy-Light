import tinytuya
import time
import json
import os

# Device configuration - Load from environment variables
DEVICE_ID = os.getenv('TUYA_DEVICE_ID')
DEVICE_IP = os.getenv('TUYA_DEVICE_IP')
LOCAL_KEY = os.getenv('TUYA_LOCAL_KEY')
VERSION = float(os.getenv('TUYA_VERSION', '3.3'))

# Validate required configuration
if not all([DEVICE_ID, DEVICE_IP, LOCAL_KEY]):
    print("❌ Missing required environment variables:")
    print("   TUYA_DEVICE_ID, TUYA_DEVICE_IP, TUYA_LOCAL_KEY")
    print("   Please set these in your .env file or environment")
    exit(1)

def get_cloud_connection():
    """Get cloud connection for status monitoring"""
    try:
        with open('tinytuya.json', 'r') as f:
            config = json.load(f)
        
        return tinytuya.Cloud(
            apiRegion=config['apiRegion'],
            apiKey=config['apiKey'], 
            apiSecret=config['apiSecret']
        )
    except Exception as e:
        print(f"❌ Could not connect to cloud: {e}")
        return None

def toggle_switch_continuously():
    """
    Toggles the Tuya smart device on and off every second continuously.
    """
    
    # Initialize the device connection
    device = tinytuya.OutletDevice(DEVICE_ID, DEVICE_IP, LOCAL_KEY)
    device.set_version(VERSION)
    
    print(f"🔌 Starting continuous toggle for Tuya device")
    print(f"📍 Device: {DEVICE_ID} at {DEVICE_IP}")
    print("Press Ctrl+C to stop\n")
    
    try:
        while True:
            # Get current device status
            data = device.status()
            
            if 'dps' in data and '1' in data['dps']:
                current_state = data['dps']['1']
                
                # Toggle the state (switch is typically on DPS '1')
                new_state = not current_state
                result = device.set_status(new_state, '1')
                
                state_text = "ON" if new_state else "OFF"
                timestamp = time.strftime("%H:%M:%S")
                print(f"[{timestamp}] Device toggled to {state_text}")
                
            else:
                print(f"❌ Failed to retrieve device status. Response: {data}")
                
            # Wait 1 second before next toggle
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n🛑 Stopping device toggle...")
    except Exception as e:
        print(f"❌ Error: {e}")

def get_device_status():
    """
    Helper function to check the current status of the Garden Lights.
    """
    device = tinytuya.OutletDevice(DEVICE_ID, DEVICE_IP, LOCAL_KEY)
    device.set_version(VERSION)
    
    data = device.status()
    print(f"Garden Lights Status: {data}")
    return data

def single_toggle():
    """
    Performs a single toggle operation (useful for testing).
    """
    device = tinytuya.OutletDevice(DEVICE_ID, DEVICE_IP, LOCAL_KEY)
    device.set_version(VERSION)
    
    # Get current status
    data = device.status()
    
    if 'dps' in data and '1' in data['dps']:
        current_state = data['dps']['1']
        new_state = not current_state
        
        result = device.set_status(new_state, '1')
        state_text = "ON" if new_state else "OFF"
        print(f"Garden Lights toggled to {state_text} - Result: {result}")
    else:
        print(f"Failed to retrieve device status. Response: {data}")

if __name__ == "__main__":
    # Run the continuous toggle function
    toggle_switch_continuously()
