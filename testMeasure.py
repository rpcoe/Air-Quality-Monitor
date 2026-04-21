import wifi
import adafruit_requests
import adafruit_connection_manager
import time
import os
import busio
import board
import adafruit_bme680
from adafruit_bme280 import basic as adafruit_bme280



# ── Config ────────────────────────────────────────────
WIFI_SSID     = "YOUR_SSID"
WIFI_PASSWORD = "YOUR_PASSWORD"

AIO_USERNAME  = os.getenv("AIO_USERNAME")
AIO_KEY       = os.getenv("AIO_KEY")
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
            #altitude = sensor.altitude 
            # Feed that data into ENS160 for compensation
            #air_quality_sensor.temperature_compensation = temp
            #air_quality_sensor.humidity_compensation = hum
            resistance = sensor.gas  # Get the gas resistance value from the BME680
            #eCO2 = air_quality_sensor.eCO2
            #TVOC = air_quality_sensor.TVOC  
            #AQI = air_quality_sensor.AQI  
            
            #print(f"eCO2: {eCO2} ppm, TVOC: {TVOC} ppb, AQI (1-5): {AQI}")

            return temp, hum, pres, resistance, 0, 0 #, eCO2, TVOC, AQI need to be calculated based on the gas resistance and compensation values, which requires additional code to implement the ENS160 algorithm. For now, we will return 0 for these values as placeholders.


    except Exception as e:
        print(f"Error reading sensor: {e}")
        
    return 0,0,0,0,0,0

# ── Main loop ─────────────────────────────────────────
global sensorType
sensorType = os.getenv("SENSOR_TYPE", "NONE").upper()  # Default to NONE if not set
if sensorType != "NONE":
    i2c = busio.I2C(board.GP21, board.GP20)  # SCL, SDA
if sensorType == "BME280":
    # address can change based on bme device
    # if 0x76 does not work try 0x77 :)
    sensor = adafruit_bme280.Adafruit_BME280_I2C(i2c, address=0x76)
if sensorType == "BME680":        # ENS160 for air quality and AHT21 for temp and humidity
    sensor = adafruit_bme680.Adafruit_BME680_I2C(i2c, address=0x77)  
    # Change this to match your local sea level pressure (hPa) for altitude
    #sensor.sea_level_pressure = 1013.25

print("Logging started. Press Ctrl+C to stop.\n")

while True:
    # Get the actual sensor readings
    
    temp, hum, pres, resistance, eCO2, TVOC = read_data(sensorType=sensorType)  

    send_to_adafruit("temperature", f"{temp:.1f}")
    send_to_adafruit("humidity", f"{hum:.1f}")
    send_to_adafruit("pressure", f"{pres:.1f}")
    send_to_adafruit("resistance", f"{resistance:.1f}")

    time.sleep(10)  # Send every 10 seconds
