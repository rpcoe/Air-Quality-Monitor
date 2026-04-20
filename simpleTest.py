import os
import time
import ssl
import wifi
import socketpool
import adafruit_requests
import gc

# WiFi Credentials
SSID = os.getenv('CIRCUITPY_WIFI_SSID')
PASSWORD = os.getenv('CIRCUITPY_WIFI_PASSWORD')
GOOGLE_URL = "https://script.google.com/macros/s/AKfycbyQC5fRongvaSKxAYIJ2KjSwiX0PAdh_EEW1TudO8hkFb0e2OyD6n6RB3oHopVnh5k2zQ/exec"
print("Connecting to WiFi...")
wifi.radio.connect(SSID, PASSWORD)

pool = socketpool.SocketPool(wifi.radio)
context = ssl.create_default_context()

# --- THE FIX: Load the certificate file ---
try:
    context.load_verify_locations(cafile="/roots.pem")
    print("Successfully loaded roots.pem")
except Exception as e:
    print(f"Failed to load roots.pem: {e}")

requests = adafruit_requests.Session(pool, context)

def send_test():
    gc.collect()
    test_data = "Time_Test, 1, 2, 3, 4"
    print(f"\nSending to Google: {test_data}")
    
    try:
        # Note: Google URLs use 302 redirects, requests handles this.
        with requests.post(GOOGLE_URL, data=test_data, timeout=30) as response:
            print(f"Status: {response.status_code}")
            print(f"Body: {response.text}")
            response.close()
    except Exception as e:
        print(f"Connection Error: {e}")

send_test()