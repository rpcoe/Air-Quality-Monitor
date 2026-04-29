# This code is designed to read data from either a BME280 or BME680
# sensor and send the readings to Adafruit IO. 
# It connects to WiFi, sets up an HTTP session, 
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
import ipaddress
import adafruit_bme680
from adafruit_bme280 import basic as adafruit_bme280
import adafruit_sdcard
import storage
import re
import adafruit_ntp
import rtc

#print(dir(adafruit_connection_manager))
update_interval = 250  # seconds suggest 250 when online - has to be less than 300 to guarantee one update per 5 minute cycle, can be set lower for more frequent updates if desired 
led = digitalio.DigitalInOut(board.LED)
led.direction = digitalio.Direction.OUTPUT
ledTime = 0.02  # seconds
sdExists = True
# ── Config ────────────────────────────────────────────

AIO_USERNAME  = os.getenv("AIO_USERNAME")
AIO_KEY       = os.getenv("AIO_KEY")
AIO_URL       = f"https://io.adafruit.com/api/v2/{AIO_USERNAME}/feeds"

SEALEVELPRESSURE_HPA = 1013.25

# Metar configuration
STATION = os.getenv('METAR_STATION')
METAR_URL = URL = f"https://aviationweather.gov/api/data/metar?ids={STATION}"

prefix = os.getenv('FILE_PREFIX', 'AQ0')  
file_name = "/sd/" + prefix + "_LOG" + ".csv"  # Global variable to hold the current file name for logging
last_SL_pressure = SEALEVELPRESSURE_HPA  # Initialize last known sea level pressure with the default value
gas_baseline = float(os.getenv("GAS_BASELINE", "200000"))  # This is a baseline resistance value for the gas sensor, adjust based on your environment and sensor calibration
sendAdafruit = os.getenv("SEND_TO_ADAFRUIT", "false").lower() == "true"  # Set to True to enable sending data to Adafruit IO, False to disable
# ──────────────────────────────────────────────────────

def startNewFile(file_name):  # This will create the file and write the header if it doesn't exist 
    if sdExists == False:
        print("SD card not found. Cannot create log file.")
        return
    with open(file_name, "w")  as writefile:
        writefile.write("AIR QUALITY MONITOR LOG  \n")
        writefile.write(" Time, Temp(degF), Humidity(%), Pressure(inHg), AQI, Altitude(ft), Resistance(Ohms),\n")
        writefile.close()
    print(f"New file created, writing header: {file_name}")

# Create the Network Time Protocol (NTP) object after WiFi is connected
def update_RTC_from_NTP():
    try:
        print("Syncing time with internet...")
        ntp = adafruit_ntp.NTP(pool, tz_offset=-7) # -7 for PDT
        rtc.RTC().datetime = ntp.datetime 
        print("Clock synchronized!")
    except Exception as e:
        if isinstance(e, OSError) and e.args[0] == 110:  # ETIMEDOUT
            sleep(5)  # Wait a bit before trying again
            print("NTP request timed out. Will try again.")
            ntp = adafruit_ntp.NTP(pool, tz_offset=-7) # -7 for PDT
            rtc.RTC().datetime = ntp.datetime
        else:
            print(f"Could not sync time: {e}")
            print("Logging will proceed with default system time.")



# Connect to WiFi
print("Connecting to WiFi...")
#  set static IP address to avoid issues with changing IPs and to make it easier to access the web interface. Make sure the IP address you choose is outside the range of addresses your router assigns via DHCP to avoid conflicts. You can check your router's settings to see the DHCP range and choose an IP address that is not in that range. For example, if your router assigns addresses from
# Retrieve strings from settings.toml
if DHCP_ENABLE := os.getenv("DHCP_ENABLE", "true").lower() == "true":
    print("DHCP is enabled. Connecting with dynamic IP address.")
else:
    ipv4 = os.getenv("IP_ADDRESS")   #ipaddress.IPv4Address("os.getenv('IP_ADDRESS')")
    gateway = os.getenv("MY_GATEWAY")
    netmask = os.getenv("MY_NETMASK")
    ipv4 = ipaddress.IPv4Address(ipv4)  # Convert the string to an IPv4Address object
    netmask = ipaddress.IPv4Address(netmask)  #netmask = ipaddress.IPv4Address("255.255.255.0")
    gateway = ipaddress.IPv4Address(gateway)    #("192.168.254.254")  #("192.168.254.254")
    wifi.radio.set_ipv4_address(ipv4=ipv4, netmask=netmask, gateway=gateway)

    print(f"Using IP address: {ipv4}  gateway: {gateway}  netmask: {netmask}")

wifi.radio.connect(os.getenv('CIRCUITPY_WIFI_SSID'), os.getenv('CIRCUITPY_WIFI_PASSWORD'))

print("Connected! IP:", wifi.radio.ipv4_address)

# Connect to the card and mount the filesystem.
spi = busio.SPI(board.GP18, board.GP19, board.GP16)  # SCK, MOSI, MISO
cs = digitalio.DigitalInOut(board.GP17)  # CS pin for SD card
try:

    sdcard = adafruit_sdcard.SDCard(spi, cs)
    vfs = storage.VfsFat(sdcard)
    storage.mount(vfs, "/sd")
except Exception as e:
    print(f"Error mounting SD card: {e}")
    sdExists = False
# Set up HTTPS session
pool = adafruit_connection_manager.get_radio_socketpool(wifi.radio)
ssl_context = adafruit_connection_manager.get_radio_ssl_context(wifi.radio)
https = adafruit_requests.Session(pool, ssl_context)

#requests = adafruit_requests.Session(pool, ssl.create_default_context())

update_RTC_from_NTP()  # Sync the RTC with NTP time before starting the main loop
        # TODO: Add a periodic NTP sync in the main loop to keep the RTC accurate over time, especially if the device will be running for extended periods without a reset.

def calculate_aqi(gas, humidity):
    hum_weight = 0.25
    gas_weight = 0.75
    
    # Humidity offset (ideal is 40%)
    hum_score = (100 - humidity) / (100 - 40) * (hum_weight * 100)
    
    # Gas score (this needs a rolling baseline of your highest seen resistance)
    gas_score = (gas / gas_baseline) * (gas_weight * 100)
    
    return hum_score + gas_score # Scale of 0-100 (Higher is better)


def read_data_smooth(sensorType):
    # Initialize before the loop with first reading
    slp = get_sea_level_pressure(False)  # Get the initial sea level pressure for altitude calculations
    temp_s, hum_s, pres_s, res_s, alt_s, aqi_s = read_data(sensorType,slp)
    
    # Implement a simple moving average smoothing out short-term fluctuations.
    alpha = 0.02  # Smoothing factor, adjust between 0 and 1 (higher is less smooth but more responsive)
   
    for i in range(update_interval):
        temp, hum, pres, resistance, alt, aqi = read_data(sensorType,slp)
        temp_s = alpha * temp + (1 - alpha) * temp_s
        hum_s  = alpha * hum  + (1 - alpha) * hum_s
        pres_s = alpha * pres + (1 - alpha) * pres_s
        res_s  = alpha * resistance + (1 - alpha) * res_s
        alt_s  = alpha * alt  + (1 - alpha) * alt_s
        aqi_s  = alpha * aqi  + (1 - alpha) * aqi_s
        #print(f"Smoothed Readings: Temp={temp_s:.1f}F, Hum={hum_s:.1f}%, Pres={pres_s:.2f}inHg, Res={res_s:.0f}Ω, Alt={alt_s:.2f} meters")
        sleep(1)  # Adjust the sleep time as needed to balance responsiveness with smoothing  
          # Flash LED to show activity during the update interval
        led.value = True
        sleep(ledTime)
        led.value = False

    return temp_s, hum_s, pres_s, res_s, alt_s, aqi_s   

def read_data(sensorType,pres):
    try:
        if sensorType == "BME280":
            temp = sensor.temperature * 9 / 5 + 32  # Convert to Fahrenheit
            hum = sensor.humidity
            pres = sensor.pressure 
            alt = (last_SL_pressure - pres) *8.33  # Calculate altitude based on current pressure and sea level pressure in meters
            pres = sensor.pressure * 0.02953 # converted to inches Hg
            resistance = 0  # BME280 does not have a gas sensor, so we return 0 for resistance
            aqi = 0  # AQI cannot be calculated without gas resistance, so we return 0 for AQI  
            #return temp, hum, pres, 0 ,alt ,0

        elif sensorType == "BME680":
            sensor.sea_level_pressure = last_SL_pressure # this nominal sealevel pressure is used to calculate altitude,
            temp = sensor.temperature * 9 / 5 + 32  # Convert to Fahrenheit
            hum = sensor.relative_humidity
            pres = sensor.pressure * 0.02953 # converted to inches Hg
            alt = sensor.altitude
            resistance = sensor.gas  # Get the gas resistance value from the BME680
            aqi = calculate_aqi(resistance, hum)  # Calculate the AQI based on gas resistance and humidity
    except Exception as e:
            print(f"Error reading sensor: {e}")  
            temp, hum, pres, resistance, alt, aqi = 0, 0, 0, 0, 0, 0
        #return 0,0,0,0,0,0
    return temp, hum, pres, resistance, alt, aqi


def write_data(temp, hum, pres, alt, aqi , resistance):
    now = rtc.RTC().datetime
    now = f"{now.tm_year}-{now.tm_mon:02d}-{now.tm_mday:02d} {now.tm_hour:02d}:{now.tm_min:02d}:{now.tm_sec:02d}"
    try:
        with open(file_name, "a") as f:
            f.write(f"{now}, {temp:.1f}, {hum:.1f}, {pres:.2f},  {alt:.0f},{aqi},{resistance}, \n")  
        print(f"Logged at {now}s, {temp:.1f}, {hum:.1f}, {pres:.2f}, {alt:.0f}, {aqi}, {resistance}")  #AQI (1-5): {AQI}")
    except OSError as e:
        print(f"Error writing to SD card: {e}")    

headers = {
    "X-AIO-Key": AIO_KEY,
    "Content-Type": "application/json"
}

def send_to_adafruit(feed_name, value):
    url = f"{AIO_URL}/{feed_name}/data"
    payload = f'{{"value": "{value}"}}'
    gc.collect()

    try:
        response = https.post(url, headers=headers, data=payload)
        print(f"Sent {feed_name}={value} → {response.status_code}")
        response.close()
    except Exception as e:
        print(f"Error sending {feed_name}:", e)
    finally:
        adafruit_connection_manager.connection_manager_close_all(pool)
        gc.collect()

def get_sea_level_pressure(first_run=False):
    print(f"Fetching sea level pressure for {STATION}...")
    global last_SL_pressure
    try:
        gc.collect()  # Run garbage collection to free up memory before making the request
        metar_text = None   # Clear previous METAR text to avoid confusion in case of request failure
        try:
            response = https.get(URL, timeout=15)
            metar_text = response.text
            response.close()
        except (RuntimeError, OSError) as e:
            print(f"Connection error: {e}")
            # Optional: Force a Wi-Fi reset here if it fails repeatedly

        #print(f"METAR Response: {metar_text}")  # Debug print to see the full METAR response
        sea_level_pressure = get_pressure_robust(metar_text)
           
        #print(f"Altimeter Setting:  {sea_level_pressure:.2f} hPa)")
        if first_run:
            sea_level_pressure = sea_level_pressure # Use the initial pressure reading as the starting point for sea level pressure
        else:
            sea_level_pressure = 0.95 * last_SL_pressure + 0.05 * sea_level_pressure # average the new reading with the last known sea level pressure to smooth out fluctuations
            last_SL_pressure =sea_level_pressure # Update the last known sea level pressure with the new value
        print(f"Using Sea Level Pressure: {sea_level_pressure:.2f} hPa")    
    except Exception as e:
        print(f"Error fetching sea level pressure: {e}")
        sea_level_pressure = last_SL_pressure 
    #print(f"Using Sea Level Pressure: {sea_level_pressure:.2f} hPa")
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
                if val < 500: hpa = (10000 + val) / 10 
                if val > 500: hpa = (9000 + val) / 10
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
#last_SL_pressure = SEALEVELPRESSURE_HPA  # Default sea level pressure in hPa
last_SL_pressure = get_sea_level_pressure(True)
sensorType = os.getenv("SENSOR_TYPE", "NONE").upper()  # Default to NONE if not set
if sensorType != "NONE":
    i2c = busio.I2C(board.GP21, board.GP20)  # SCL, SDA
if sensorType == "BME280":
    sensor = adafruit_bme280.Adafruit_BME280_I2C(i2c, address=0x76)
if sensorType == "BME680":        # ENS160 for air quality and AHT21 for temp and humidity
    sensor = adafruit_bme680.Adafruit_BME680_I2C(i2c, address=0x77, refresh_rate=1)
    
# Check if the file already exists to decide whether to write a header
try:
    os.stat(file_name)
    print("File exists, appending data to:", file_name )
        # Format the timestamp: YYYY-MM-DD HH:MM:SS
    now = rtc.RTC().datetime
    timestamp = f"{now.tm_year}-{now.tm_mon:02d}-{now.tm_mday:02d} {now.tm_hour:02d}:{now.tm_min:02d}:{now.tm_sec:02d}"

    with open(file_name, "a") as f:
        f.write(f"RESTART:  {timestamp}  \n")
except OSError:
    startNewFile(file_name)  # This will create the file and write the header if it doesn't exist 





# The first reading can be inaccurate, so we take an initial reading and discard it
temp, hum, pres, altitude, eCO2, resistance = read_data(sensorType=sensorType,pres=last_SL_pressure)    
sleep(10)  # Short delay before starting the main loop
print("Logging started. Press Ctrl+C to stop.\n")

while True:
        # Get the actual sensor readings
    temp, hum, pres, resistance, alt, aqi,  = read_data_smooth(sensorType=sensorType)    
    alt = alt * 3.28084 # convert to feet
    if sdExists == True:
        write_data(temp, hum, pres, alt, aqi, resistance)  # This function will write the data to the SD card 

    if sendAdafruit:
        send_to_adafruit(f"{prefix}-temperature", f"{temp:.1f}")
        send_to_adafruit(f"{prefix}-humidity", f"{hum:.0f}")
        send_to_adafruit(f"{prefix}-pressure", f"{pres:.2f}")
        send_to_adafruit(f"{prefix}-altitude", f"{alt:.0f}")
        send_to_adafruit(f"{prefix}-airquality", f"{aqi:.0f}")

        print("Data sent to Adafruit IO. Waiting for next reading...\n")

    

