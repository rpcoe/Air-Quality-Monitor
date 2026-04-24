# This code is designed to read data from either a BME280 or BME680
# sensor and send the readings to Adafruit IO. 
# It connects to WiFi, sets up an HTTPS session, 
# and defines functions to send data to Adafruit IO and read sensor data. 
# The main loop continuously reads sensor data and sends it to Adafruit IO 
# at specified intervals, while also flashing an LED to indicate activity.


import gc

import wifi
import adafruit_requests
import adafruit_connection_manager
from time import time, sleep
import os
import ssl
import busio
import board
import digitalio
import adafruit_bme680
from adafruit_bme280 import basic as adafruit_bme280
import re


update_interval = 30  # seconds suggest 60 when online
led = digitalio.DigitalInOut(board.LED)
led.direction = digitalio.Direction.OUTPUT
ledTime = 0.02  # seconds
# ── Config ────────────────────────────────────────────

AIO_USERNAME  = os.getenv("AIO_USERNAME")
AIO_KEY       = os.getenv("AIO_KEY")
AIO_URL       = f"https://io.adafruit.com/api/v2/{AIO_USERNAME}/feeds"

SEALEVELPRESSURE_HPA = 1013.25

# Metar configuration
STATION = os.getenv('METAR_STATION')
METAR_URL = URL = f"https://aviationweather.gov/api/data/metar?ids={STATION}"

# ──────────────────────────────────────────────────────
# Connect to WiFi
print("Connecting to WiFi...")
wifi.radio.connect(os.getenv('CIRCUITPY_WIFI_SSID'), os.getenv('CIRCUITPY_WIFI_PASSWORD'))

print("Connected! IP:", wifi.radio.ipv4_address)

# Set up HTTPS session
pool = adafruit_connection_manager.get_radio_socketpool(wifi.radio)
ssl_context = adafruit_connection_manager.get_radio_ssl_context(wifi.radio)
https = adafruit_requests.Session(pool, ssl_context)

requests = adafruit_requests.Session(pool, ssl.create_default_context())


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

def read_data(sensorType):
    try:
        if sensorType == "BME280":
            temp = sensor.temperature * 9 / 5 + 32  # Convert to Fahrenheit
            hum = sensor.humidity
            pres = sensor.pressure * 0.02953 # converted to inches Hg
            return temp, hum, pres, 0 ,0 ,0

        elif sensorType == "BME680":
            temp = sensor.temperature * 9 / 5 + 32  # Convert to Fahrenheit
            hum = sensor.relative_humidity
            pres = sensor.pressure * 0.02953 # converted to inches Hg
            alt = sensor.altitude
            resistance = sensor.gas  # Get the gas resistance value from the BME680
                        
            return temp, hum, pres, resistance, alt, 0 #, eCO2, TVOC, AQI need to be calculated based on the gas resistance and compensation values, which requires additional code to implement the ENS160 algorithm. For now, we will return 0 for these values as placeholders.
    except Exception as e:
        print(f"Error reading sensor: {e}")
        
    return 0,0,0,0,0,0

def get_sea_level_pressure(first_run=False):
    print(f"Fetching sea level pressure for {STATION}...")
    global last_SL_pressure
    try:
        gc.collect()  # Run garbage collection to free up memory before making the request
        metar_text = None   # Clear previous METAR text to avoid confusion in case of request failure
        try:
            response = requests.get(URL, timeout=15)
            metar_text = response.text
            response.close()
        except (RuntimeError, OSError) as e:
            print(f"Connection error: {e}")
            # Optional: Force a Wi-Fi reset here if it fails repeatedly

        print(f"METAR Response: {metar_text}")  # Debug print to see the full METAR response
        sea_level_pressure = get_pressure_robust(metar_text)
           
        print(f"Altimeter Setting:  {sea_level_pressure:.2f} hPa)")
        if first_run:
            sea_level_pressure = sea_level_pressure # Use the initial pressure reading as the starting point for sea level pressure
        else:
            sea_level_pressure = 0.95 * last_SL_pressure + 0.05 * sea_level_pressure #
            last_SL_pressure =sea_level_pressure # Update the last known sea level pressure with the new value
        
    except Exception as e:
        print(f"Error fetching sea level pressure: {e}")
        sea_level_pressure = last_SL_pressure 
    print(f"Using Sea Level Pressure: {sea_level_pressure:.2f} hPa")
    return sea_level_pressure

def get_pressure_robust(text):
    if text is None or "METAR" not in text:
        return None

    try:
        # 1. Search for SLP (High Resolution)
        if "SLP" in text:
            idx = text.find("SLP")
            # Extract the 3 digits after 'SLP'
            slp_str = text[idx+3 : idx+6]
            if slp_str.isdigit():
                val = int(slp_str)
                # Logic: SLP130 -> 1013.0, SLP992 -> 999.2
                hpa = (10000 + val) / 10 if val < 1000 else (9000 + val) / 10
                return hpa

        # 2. Fallback to Altimeter (A2992)
        if " A" in text: # Look for space then A to avoid other letters
            idx = text.find(" A") + 1
            alt_str = text[idx+1 : idx+5]
            if alt_str.isdigit():
                inhg = float(alt_str) / 100
                return inhg * 33.8639
                
    except Exception as e:
        print(f"Parsing error: {e}")
        
    return None
# ── Main loop ─────────────────────────────────────────
global sensorType
global last_SL_pressure 
#last_SL_pressure = SEALEVELPRESSURE_HPA  # Default sea level pressure in hPa
last_SL_pressure = get_sea_level_pressure(True)
sensorType = os.getenv("SENSOR_TYPE", "NONE").upper()  # Default to NONE if not set
if sensorType != "NONE":
    i2c = busio.I2C(board.GP21, board.GP20)  # SCL, SDA
if sensorType == "BME280":
    # address can change based on bme device
    # if 0x76 does not work try 0x77 :)
    sensor = adafruit_bme280.Adafruit_BME280_I2C(i2c, address=0x76)
if sensorType == "BME680":        # ENS160 for air quality and AHT21 for temp and humidity
    sensor = adafruit_bme680.Adafruit_BME680_I2C(i2c, address=0x77) 
    #sensor.sea_level_pressure = SEALEVELPRESSURE_HPA  # this nominal sealevel pressure is used to calculate altitude,
                            # you can adjust it to your local sea level pressure for more accurate altitude readings
                            # This will be different based on your location and weather conditions, so you may want to update it periodically for better accuracy. 
                            # You can find the current sea level pressure for your location from a local weather station or online weather service.
pressure = get_sea_level_pressure(False)     # this nominal sealevel pressure is used to calculate altitude,
sensor.sea_level_pressure = pressure

print(f"Current Sea Level Pressure: {pressure} hPa")

# The first reading can be inaccurate, so we take an initial reading and discard it
temp, hum, pres, resistance, altitude,eCO2,  = read_data(sensorType=sensorType)    
sleep(10)  # Short delay before starting the main loop
print("Logging started. Press Ctrl+C to stop.\n")

while True:

    # Get the actual sensor readings
    sensor.sea_level_pressure = get_sea_level_pressure(False)  # Update sea level pressure before each reading for better altitude accuracy  
    temp, hum, pres, resistance, alt, eCO2,  = read_data(sensorType=sensorType)    
    alt = alt * 3.28084 # convert to feet
    send_to_adafruit("temperature", f"{temp:.1f}")
    send_to_adafruit("humidity", f"{hum:.1f}")
    send_to_adafruit("pressure", f"{pres:.2f}")
    send_to_adafruit("resistance", f"{resistance:.1f}")
    send_to_adafruit("altitude", f"{alt:.1f}")
    print("Data sent to Adafruit IO. Waiting for next reading...\n")

# Flash LED to show activity during the update interval
    for i in range(update_interval):
        led.value = True
        sleep(ledTime)
        led.value = False
        sleep(1)  # Wait for 1 second before the next flash, adjust as needed

