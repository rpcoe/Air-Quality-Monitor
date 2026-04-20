import os
import time
import ssl
import wifi
import socketpool
import adafruit_requests
import gc

# --- CONFIGURATION ---
SSID = os.getenv('CIRCUITPY_WIFI_SSID')
PASSWORD = os.getenv('CIRCUITPY_WIFI_PASSWORD')
# Ensure this is the NEW URL from your 'Extensions > Apps Script' deployment
GOOGLE_URL = "https://script.google.com/macros/s/AKfycbwm3MqHXCctVr5MR9NevO448VF6aZekrgrpKhTuyuaQEKOQdm7kny2iDAmOa8GxrMUe3w/exec"

# --- WIFI SETUP ---
print("Connecting to WiFi...")
wifi.radio.connect(SSID, PASSWORD)
print(f"Connected! IP: {wifi.radio.ipv4_address}")

pool = socketpool.SocketPool(wifi.radio)
requests = adafruit_requests.Session(pool, ssl.create_default_context())

def test_sync(data_to_send):
    gc.collect()
    print(f"\nAttempting to send: {data_to_send}")
    try:
        # Google requires a POST
        with requests.post(GOOGLE_URL, data=data_to_send, timeout=30) as response:
            print(f"Status Code: {response.status_code}")
            print(f"Response Text: {response.text}")
            if response.status_code == 200:
                print("SUCCESS: Check your Google Sheet!")
            else:
                print("FAILED: Server reached but returned an error.")
    except Exception as e:
        print(f"CONNECTION ERROR: {e}")

# --- RUN TEST ---
counter = 1
while True:
    test_string = f"TEST_TIME, {counter}, 72.5, 45, 29.92"
    test_sync(test_string)
    
    counter += 1
    print("Waiting 15 seconds for next test...")
    time.sleep(15)