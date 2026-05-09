#  TODO List:
#  - Update webpage to show the most recent data in real time without needing to refresh the page (e.g. using JavaScript to fetch new data every few seconds and update the page dynamically)
#  - Update wepage to display BME680 gas resistance and calculated eCO2, TVOC, and AQI values once the compensation algorithm is implemented
#  - Add a simple web interface to view the data without downloading
#  - Add a graphing library to visualize the data on the web interface
#  - Add a method to upload data to a cloud service like Google Drive or AWS S3 for remote access and backup
#  - Add a method to send alerts (e.g. email or SMS) if certain thresholds are exceeded (e.g. high temperature or low pressure)

from time import sleep, time
import os
import ipaddress
import gc
import wifi
import socketpool
import asyncio
import busio
import digitalio
import board
import storage
import adafruit_sdcard
import adafruit_ntp
import adafruit_bme680
import adafruit_requests
import adafruit_connection_manager

import rtc

from adafruit_bme280 import basic as adafruit_bme280

from adafruit_httpserver import Server, Request, Response, POST
from adafruit_httpserver import ChunkedResponse

# ── Config ────────────────────────────────────────────

AIO_USERNAME  = os.getenv("AIO_USERNAME")
AIO_KEY       = os.getenv("AIO_KEY")
AIO_URL       = f"https://io.adafruit.com/api/v2/{AIO_USERNAME}/feeds"

SEALEVELPRESSURE_HPA = 1013.25

# Metar configuration
STATION = os.getenv('METAR_STATION')
METAR_URL = URL = f"https://aviationweather.gov/api/data/metar?ids={STATION}"

# Create the Network Time Protocol (NTP) object after WiFi is connected so we can sync the RTC with accurate time from the internet. This is important for accurate timestamps in our log files, especially if the device is running for a long time and may experience clock drift. We will also call this function at the start of each new day to ensure the RTC stays accurate over time.
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

def startNewFile(file_name):  # This will create the file and write the header if it doesn't exist 
    if sdExists == False:
        print("SD card not found. Cannot create log file.")
        return
    with open(file_name, "w")  as writefile:
        writefile.write("AIR QUALITY MONITOR LOG  \n")
        writefile.write(" Time, Temp(degF), Humidity(%), Pressure(inHg), AQI, Altitude(ft), Resistance(Ohms), Light(Lux)\n")
        writefile.close()
    print(f"New file created, writing header: {file_name}")

def read_data(sensorType,pres):
    tempCalib = float(os.getenv('TEMP_CALIB', 0))
    altCalib = float(os.getenv('ALT_CALIB', 0))
    try:
        if sensorType == "BME280":
            temp = sensor.temperature * 9 / 5 + 32  + tempCalib  # Convert to Fahrenheit and apply calibration
            hum = sensor.humidity
            pres = sensor.pressure 
            alt = (last_SL_pressure - pres) *8.33  + altCalib # Calculate altitude based on current pressure and sea level pressure in meters
            pres = pres * 0.02953 # converted to inches Hg
            resistance = 0  # BME280 does not have a gas sensor, so we return 0 for resistance
            aqi = 0  # AQI cannot be calculated without gas resistance, so we return 0 for AQI  
            light = 0  # BME280 does not have a light sensor, so we return 0 for light level
        if sensorType == "BME680":
            sensor.sea_level_pressure = last_SL_pressure # this nominal sealevel pressure is used to calculate altitude,
            temp = sensor.temperature * 9 / 5 + 32 + tempCalib  # Convert to Fahrenheit and apply calibration
            hum = sensor.relative_humidity
            pres = sensor.pressure * 0.02953 # converted to inches Hg
            alt = sensor.altitude + altCalib # Add altitude calibration from settings.toml
            resistance = sensor.gas  # Get the gas resistance value from the BME680
            aqi = calculate_aqi(resistance, hum)  # Calculate the AQI based on gas resistance and humidity
            light = 0  # BME680 does not have a light sensor, so we return 0 for light level
        if sensorType == "VEML7700":
            temp = 0  # VEML7700 does not measure temperature, so we return 0 for temp
            hum = 0   # VEML7700 does not measure humidity, so we return 0 for humidity
            pres = 0 # VEML7700 does not measure pressure, so we are using this feed temporarily.
            alt = 0   # Altitude cannot be calculated without pressure, so we return 0 for altitude
            resistance = 0  # VEML7700 does not have a gas sensor, so we return 0 for resistance
            aqi = 0   # VEML7700 does not have a gas sensor, so we return 0 for AQI
            light = sensor.lux  # Get the light level in lux from the VEML7700
    except Exception as e:
            print(f"Error reading sensor: {e}")  
            #temp, hum, pres, resistance, alt, aqi = 0, 0, 0, 0, 0, 0, 0
            return 0, 0, 0, 0, 0, 0, 0
    return temp, hum, pres, resistance, alt, aqi, light
def calculate_aqi(gas, hum):
    hum_weighting = 25
    gas_weight = 100-hum_weighting
    hum_baseline = 40   
    
    # Humidity offset (ideal is 40%)
    gas_offset = gas_baseline-gas
    hum_offset = hum - hum_baseline
    # Score humidity
    if hum_offset > 0:
        #hum_score = (100 - hum_baseline - hum_offset) / (100 - hum_baseline) * (hum_weighting )
        hum_score = ((100 - hum) / (100 - hum_baseline)) * (hum_weighting)

    else:
        hum_score = ((hum) / hum_baseline) * (hum_weighting )

    # Score gas  
    gas_score = (gas / gas_baseline) * (gas_weight )
    iaq_score = gas_score + hum_score
            
    return min(max(iaq_score, 0), 500)  # clamp to 0–500



def read_data_smooth(sensorType):
    # Initialize before the loop with first reading
    slp = get_sea_level_pressure(False)  # Get the initial sea level pressure for altitude calculations
    temp_s, hum_s, pres_s, res_s, alt_s, aqi_s, light_s = read_data(sensorType,slp)
    
    # Implement a simple moving average smoothing out short-term fluctuations.
    alpha = 0.02  # Smoothing factor, adjust between 0 and 1 (higher is less smooth but more responsive)
   
    for i in range(update_interval):
        temp, hum, pres, resistance, alt, aqi, light = read_data(sensorType,slp)
        temp_s = alpha * temp + (1 - alpha) * temp_s
        hum_s  = alpha * hum  + (1 - alpha) * hum_s
        pres_s = alpha * pres + (1 - alpha) * pres_s
        res_s  = alpha * resistance + (1 - alpha) * res_s
        alt_s  = alpha * alt  + (1 - alpha) * alt_s
        aqi_s  = alpha * aqi  + (1 - alpha) * aqi_s
        light_s = alpha * light + (1 - alpha) * light_s
        #print(f"Smoothed Readings: Temp={temp_s:.1f}F, Hum={hum_s:.1f}%, Pres={pres_s:.2f}inHg, Res={res_s:.0f}Ω, Alt={alt_s:.2f} meters, AQI={aqi_s:.0f}, Light={light_s:.2f} lux")
        sleep(1)  # Adjust the sleep time as needed to balance responsiveness with smoothing  
          # Flash LED to show activity during the update interval
        led.value = True
        sleep(ledTime)
        led.value = False

    return temp_s, hum_s, pres_s, res_s, alt_s, aqi_s, light_s   
"""
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
"""

def write_data(temp, hum, pres, alt, aqi , resistance, light):
    now = rtc.RTC().datetime
    now = f"{now.tm_year}-{now.tm_mon:02d}-{now.tm_mday:02d} {now.tm_hour:02d}:{now.tm_min:02d}:{now.tm_sec:02d}"
    try:
        with open(file_name, "a") as f:
            f.write(f"{now}, {temp:.1f}, {hum:.1f}, {pres:.2f},  {alt:.0f},{aqi:.0f},{resistance:.0f},{light:.0f} \n")  
        print(f"Logged at {now}s, {temp:.1f}, {hum:.1f}, {pres:.2f}, {alt:.0f}, {aqi:.0f}, {resistance:.0f},{light:.0f}")  #AQI (1-5): {AQI}")
    except OSError as e:
        print(f"Error writing to SD card: {e}")    

headers = {
    "X-AIO-Key": AIO_KEY,
    "Content-Type": "application/json"
}

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




update_interval = 20  # Set the time increment in seconds for logging data. Adjust as needed, but remember that very short intervals may fill up the SD card quickly and may not be necessary for air quality monitoring.
ledTime = .02       # time that the led is flashing each cycle
sdExists = True

led = digitalio.DigitalInOut(board.LED)
led.direction = digitalio.Direction.OUTPUT


prefix = os.getenv('FILE_PREFIX', 'AQ0')  
file_name = "/sd/" + prefix + "_LOG" + ".csv"  # Global variable to hold the current file name for logging
last_SL_pressure = SEALEVELPRESSURE_HPA  # Initialize last known sea level pressure with the default value
gas_baseline = float(os.getenv("GAS_BASELINE", "200000"))  # This is a baseline resistance value for the gas sensor, adjust based on your environment and sensor calibration
sendAdafruit = os.getenv("SEND_TO_ADAFRUIT", "false").lower() == "true"  # Set to True to enable sending data to Adafruit IO, False to disable
# ──────────────────────────────────────────────────────

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


wifi.radio.set_ipv4_address(ipv4=ipv4, netmask=netmask, gateway=gateway)

#  connect to your SSID
wifi.radio.connect(os.getenv('CIRCUITPY_WIFI_SSID'), os.getenv('CIRCUITPY_WIFI_PASSWORD'))

print(f"Connected! Visit http://{wifi.radio.ipv4_address}\n")

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


pool = socketpool.SocketPool(wifi.radio)
server = Server(pool, "/sd", debug=True)
# We add a short timeout so poll() doesn't hang or crash if nothing is happening
server.socket_timeout = 0.1
server.start(str(wifi.radio.ipv4_address),port=80)

#TODO:  Add pool for Adafruit IO connection and create a function to send data to Adafruit IO if sendAdafruit is True. This will allow us to log our data to the cloud and access it remotely, as well as integrate with other services and dashboards that support Adafruit IO.
# Set up HTTPS session
pool = adafruit_connection_manager.get_radio_socketpool(wifi.radio)
ssl_context = adafruit_connection_manager.get_radio_ssl_context(wifi.radio)
https = adafruit_requests.Session(pool, ssl_context)


update_RTC_from_NTP()  # Sync the RTC with NTP time at startup

# Get the current time from the internal clock
now = rtc.RTC().datetime

startNewFile(file_name)
# Open the new history file
 
# Format the date as YYYY-MM-DD (e.g., 2026-04-09)
date_string = f"{now.tm_year}-{now.tm_mon:02d}-{now.tm_mday:02d}"
current_day = now.tm_mday  # Set to current day to start logging to the correct file
##date_string = "2026-04-03"  # Hardcoded for testing

# Build the filename 
filePrefix = os.getenv("FILE_PREFIX")   
file_name = f"/sd/{filePrefix}_{date_string}.txt"

print(f"Current filename: {file_name}")

# Check if the file already exists to decide whether to write a header
try:
    os.stat(file_name)
    print("File exists, appending data.")
        # Format the timestamp: YYYY-MM-DD HH:MM:SS
    timestamp = f"{now.tm_year}-{now.tm_mon:02d}-{now.tm_mday:02d} {now.tm_hour:02d}:{now.tm_min:02d}:{now.tm_sec:02d}"

    with open(file_name, "a") as f:
        f.write(f"RESTART:  {timestamp}  \n")
except OSError:
    startNewFile(file_name)  # This will create the file and write the header if it doesn't exist 

global sensorType
last_SL_pressure = get_sea_level_pressure(True)
count = 0  # Counter to track when to update RTC and sea level pressure

# Create sensor object, using the board's default I2C bus.
sensorType = os.getenv("SENSOR_TYPE", "NONE").upper()  # Default to NONE if not set
try:
    if sensorType != "NONE":
        i2c = busio.I2C(board.GP21, board.GP20)  # SCL, SDA
        sleep(1)  # Short delay to ensure I2C bus is ready
    if sensorType == "BME280":
        sensor = adafruit_bme280.Adafruit_BME280_I2C(i2c, address=0x76)
    if sensorType == "BME680":        # ENS160 for air quality and AHT21 for temp and humidity
        sensor = adafruit_bme680.Adafruit_BME680_I2C(i2c, address=0x77, refresh_rate=1)
    if sensorType == "VEML7700":
        sensor = adafruit_veml7700.VEML7700(i2c)
except:
    print("No valid sensor type specified. Please set SENSOR_TYPE in settings.toml to BME280, BME680, or VEML7700.")


# The first reading can be inaccurate, so we take an initial reading and discard it
temp, hum, pres, altitude, eCO2, resistance, light = read_data(sensorType=sensorType,pres=last_SL_pressure)    
sleep(10)  # Short delay before starting the main loop
print("Logging started. Press Ctrl+C to stop.\n")




# This routine shows a simple link in your browser
@server.route("/")
def base(request: Request):
    temp, hum, pres, resistance, eCO2, TVOC = read_data(sensorType=sensorType) 
    #temp, hum, pres,eCO2, TVOC, AQI = read_data(sensorType=sensorType)
    return Response(request, f"<html><body><h1>AIR QUALITY MONITOR</h1><h2>Temp: {temp:.1f} degF</h2><h2>Humidity: {hum:.1f}%</h2><h2>Pressure: {pres:.2f} inHg</h2><h2>eCO2: {eCO2} ppm</h2><h2>TVOC: {TVOC} ppb</h2><h2>Resistance: {resistance} ohms</h2><a href='/download'>Click here to download {file_name}</a></body></html>", content_type="text/html")  #<h2>AQI (1-5): {AQI}</h2>


# This routine makes the browser download the file when you visit /download to downloads on your computer. It uses the 'Content-Disposition' header to force the download 
# # We use a generator to read the file in chunks so we don't run out of limited RAM on the Pico
# Note: this is a very basic implementation and does not include error handling for file not found or other issues. It also assumes the file is small enough to be read in chunks of 512 bytes without causing issues. 

@server.route("/download")
def download_file(request: Request):
    global file_name # Ensure we are using the most recent filename
    
    # 1. Capture the exact name and size AT THIS MOMENT
    target_file = file_name 
    file_size = os.stat(target_file)[6]
    
    download_name = target_file.split("/")[-1].replace(".txt", ".csv")

    def file_chunk_generator():
        # Use the 'target_file' variable we locked above
        with open(target_file, "rb") as f:
            bytes_sent = 0
            while bytes_sent < file_size:
                # Read 1024 or whatever is left to reach file_size
                chunk = f.read(min(1024, file_size - bytes_sent))
                if not chunk:
                    break
                yield chunk
                bytes_sent += len(chunk)

    headers = {
        "Content-Disposition": f'attachment; filename="{download_name}"',
        "Content-Length": str(file_size),
        "Connection": "close"
    }

    print(f"Finalizing download: {download_name} ({file_size} bytes)")
    return ChunkedResponse(request, file_chunk_generator, content_type="text/csv", headers=headers)

async def log_data():
    """Task to log data every {update_interval } seconds."""
    global file_name, current_day
    while True:
        temp, hum, pres, resistance, alt, aqi, light = read_data(sensorType,500) # TODO: Pass the current sea level pressure for altitude calculations
        write_data(temp, hum, pres, alt, aqi, resistance, light)
        await asyncio.sleep(update_interval)


    
async def run_server():
    """Task to handle browser requests."""
    #print("Server task started...")
    while True:
        
        try:
            # poll() checks for incoming browser requests
            server.poll()
        except Exception as e:
            # This catches "Soft" errors like timeouts without stopping the script
            print(f"Server poll error: {e}") 
            pass
        
        # Flash LED to show activity
        led.value = True
        sleep(ledTime)
        led.value = False
        
        # This is CRITICAL: it allows the logger task to run
        await asyncio.sleep(1)

async def main():
    # Run both the logger and the server at the same time
    await asyncio.gather(log_data(), run_server())



asyncio.run(main())
