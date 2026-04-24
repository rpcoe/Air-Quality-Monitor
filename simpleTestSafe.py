import wifi
import adafruit_requests
import adafruit_connection_manager
import time
import os

# ── Config ────────────────────────────────────────────
WIFI_SSID     = "YOUR_SSID"
WIFI_PASSWORD = "YOUR_PASSWORD"

AIO_USERNAME  = "your username"
AIO_KEY       = "your aio key"
AIO_URL       = f"https://io.adafruit.com/api/v2/{AIO_USERNAME}/feeds"