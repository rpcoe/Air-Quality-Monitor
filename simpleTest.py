import wifi
import adafruit_requests
import adafruit_connection_manager
import time
import os

# ── Config ────────────────────────────────────────────
WIFI_SSID     = "YOUR_SSID"
WIFI_PASSWORD = "YOUR_PASSWORD"

AIO_USERNAME  = "robcoe1500"
AIO_KEY       = "aio_yKLJ21BMWEcGUXaVHhGbKfhHvCO7"
AIO_URL       = f"https://io.adafruit.com/api/v2/{AIO_USERNAME}/feeds"
# ──────────────────────────────────────────────────────

# Connect to WiFi
print("Connecting to WiFi...")
wifi.radio.connect(os.getenv('CIRCUITPY_WIFI_SSID'), os.getenv('CIRCUITPY_WIFI_PASSWORD'))

print("Connected! IP:", wifi.radio.ipv4_address)

# Set up HTTPS session
pool = adafruit_connection_manager.get_radio_socketpool(wifi.radio)
ssl_context = adafruit_connection_manager.get_radio_ssl_context(wifi.radio)
https = adafruit_requests.Session(pool, ssl_context)

headers = {
    "X-AIO-Key": AIO_KEY,
    "Content-Type": "application/json"
}

def send_to_adafruit(feed_name, value):
    url = f"{AIO_URL}/{feed_name}/data"
    payload = f'{{"value": "{value}"}}'
    try:
        response = https.post(url, headers=headers, data=payload)
        print(f"Sent {feed_name}={value} → {response.status_code}")
        response.close()
    except Exception as e:
        print(f"Error sending {feed_name}:", e)

# ── Main loop ─────────────────────────────────────────
while True:
    # Replace these with your actual sensor readings
    temperature = 24.5
    humidity    = 55.0

    send_to_adafruit("temperature", temperature)
    send_to_adafruit("humidity", humidity)

    time.sleep(10)  # Send every 10 seconds

# Connect to WiFi


