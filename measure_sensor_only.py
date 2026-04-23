# This code is designed to read data from either a BME280 or BME680
# sensor and send the readings to Adafruit IO. 
# It connects to WiFi, sets up an HTTPS session, 
# and defines functions to send data to Adafruit IO and read sensor data. 
# The main loop continuously reads sensor data and sends it to Adafruit IO 
# at specified intervals, while also flashing an LED to indicate activity.


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


update_interval = 30  # seconds suggest 60 when online
led = digitalio.DigitalInOut(board.LED)
led.direction = digitalio.Direction.OUTPUT
ledTime = 0.02  # seconds
# ── Config ────────────────────────────────────────────

AIO_USERNAME  = os.getenv("AIO_USERNAME")
AIO_KEY       = os.getenv("AIO_KEY")
AIO_URL       = f"https://io.adafruit.com/api/v2/{AIO_USERNAME}/feeds"

SEALEVELPRESSURE_HPA = 1013.25

# OpenWeather API Configuration
CITY = "Redondo Beach"
COUNTRY_CODE = "US"
UNITS = "metric"  # 'metric' for hPa
API_URL = f"http://api.openweathermap.org/data/2.5/weather?q={CITY},{COUNTRY_CODE}&appid={os.getenv('OPENWEATHER_TOKEN')}&units={UNITS}"
            # Version 2.5 of the OpenWeather API is used here, which provides current weather data including sea level pressure.
            # This version is deprecated but still functional. You can also use version 3.0 of the API, which may require adjustments to the URL and response parsing.
            #   and also requires a credit card for the free tier, so version 2.5 is used here for simplicity and accessibility.

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
    print(f"Fetching sea level pressure for {CITY}...")
    global last_SL_pressure
    try:
        response = requests.get(API_URL)
        data = response.json()
        #print (f"API Response: {data}")  # Debug print to see the full API response
        # OpenWeather provides 'pressure' in the 'main' dictionary.
        # By default, this is the pressure at sea level for that location.
        # A change of 1 hPa corresponds to a change of 27 feet in altitude, so we can use this value directly for our sea level pressure.
        if first_run:
            sea_level_pressure = data["main"]["pressure"]  # Use the initial pressure reading as the starting point for sea level pressure
        else:
            sea_level_pressure = 0.95 * last_SL_pressure + 0.05 * data["main"]["pressure"] #
            last_SL_pressure =sea_level_pressure # Update the last known sea level pressure with the new value
        
        response.close()
    except Exception as e:
        print(f"Error fetching sea level pressure: {e}")
        sea_level_pressure = last_SL_pressure 

    return sea_level_pressure

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


