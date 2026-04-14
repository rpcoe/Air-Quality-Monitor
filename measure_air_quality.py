#  TODO List:
#  - Add a simple web interface to view the data without downloading
#  - Add a graphing library to visualize the data on the web interface
#  - Add a method to download data in CSV format for easier analysis in Excel or Google Sheets
#  - Add a method to upload data to a cloud service like Google Drive or AWS S3 for remote access and backup
#  - Add a method to send alerts (e.g. email or SMS) if certain thresholds are exceeded (e.g. high temperature or low pressure)

from time import sleep
import os
import ipaddress

import wifi
import socketpool
import asyncio
import busio
import digitalio
import board
import storage
import adafruit_sdcard
import adafruit_ntp
import adafruit_ahtx0
import adafruit_ens160
import rtc

from adafruit_bme280 import basic as adafruit_bme280
from adafruit_httpserver import Server, Request, Response, POST
from adafruit_httpserver import ChunkedResponse

def startNewFile(file_name):  # This will create the file and write the header if it doesn't exist 
    print("New file created, writing header.")
    with open(file_name, "w") as f:
        f.write(" ,Time, Temp(degF), Humidity(%), Pressure(inHg)\n")

timeIncrement = 30  # Set the time increment in seconds for logging data. Adjust as needed, but remember that very short intervals may fill up the SD card quickly and may not be necessary for air quality monitoring.
ledTime = .01       # time that the led is flashing each cycle

led = digitalio.DigitalInOut(board.LED)
led.direction = digitalio.Direction.OUTPUT



# Connect to the card and mount the filesystem.
spi = busio.SPI(board.GP18, board.GP19, board.GP16)  # SCK, MOSI, MISO
cs = digitalio.DigitalInOut(board.GP17)  # CS pin for SD card
sdcard = adafruit_sdcard.SDCard(spi, cs)
vfs = storage.VfsFat(sdcard)
storage.mount(vfs, "/sd")

#  to use DHCP instead of static IP, comment out the wifi.radio.set_ipv4_address() line below and uncomment the line below to connect to WiFi using DHCP. Note that using DHCP may cause issues if your router changes the assigned IP address, which can make it difficult to access the web interface. If you choose to use DHCP, you may want to set up a DHCP reservation in your router for the Pico's MAC address to ensure it always gets the same IP address.
# Connect to WiFi
#  set static IP address to avoid issues with changing IPs and to make it easier to access the web interface. Make sure the IP address you choose is outside the range of addresses your router assigns via DHCP to avoid conflicts. You can check your router's settings to see the DHCP range and choose an IP address that is not in that range. For example, if your router assigns addresses from
# Retrieve strings from settings.toml
ipv4 = os.getenv("IP_ADDRESS")   #ipaddress.IPv4Address("os.getenv('IP_ADDRESS')")
gateway = os.getenv("MY_GATEWAY")
netmask = os.getenv("MY_NETMASK")
ipv4 = ipaddress.IPv4Address(ipv4)  # Convert the string to an IPv4Address object
netmask = ipaddress.IPv4Address(netmask)  #netmask = ipaddress.IPv4Address("255.255.255.0")
gateway = ipaddress.IPv4Address(gateway)    #("192.168.254.254")  #("192.168.254.254")
print(f"Using IP address: {ipv4}  gateway: {gateway}  netmask: {netmask}")

wifi.radio.set_ipv4_address(ipv4=ipv4, netmask=netmask, gateway=gateway)


#  connect to your SSID
wifi.radio.connect(os.getenv('CIRCUITPY_WIFI_SSID'), os.getenv('CIRCUITPY_WIFI_PASSWORD'))

print(f"Connected! Visit http://{wifi.radio.ipv4_address}\n")

pool = socketpool.SocketPool(wifi.radio)
server = Server(pool, "/sd", debug=True)
# We add a short timeout so poll() doesn't hang or crash if nothing is happening
server.socket_timeout = 0.1
server.start(str(wifi.radio.ipv4_address),port=80)


# Create the NTP object after WiFi is connected
try:
    print("Syncing time with internet...")
    ntp = adafruit_ntp.NTP(pool, tz_offset=-7) # -7 for PDT
    rtc.RTC().datetime = ntp.datetime  #
    print("Clock synchronized!")
except Exception as e:
    print(f"Could not sync time: {e}")
    print("Logging will proceed with default system time.")

# Get the current time from the internal clock
now = rtc.RTC().datetime

# Open the new history file
 
# Format the date as YYYY-MM-DD (e.g., 2026-04-09)
date_string = f"{now.tm_year}-{now.tm_mon:02d}-{now.tm_mday:02d}"
current_day = now.tm_mday  # Set to current day to start logging to the correct file
#date_string = "2026-04-03"  # Hardcoded for testing
#current_day = 2  # Hardcoded for testing

# Build the filename 
file_name = f"/sd/log_{date_string}.txt"

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
    
# Create sensor object, using the board's default I2C bus.
global sensorType
sensorType = os.getenv("SENSOR_TYPE", "NONE").upper()  # Default to NONE if not set
if sensorType != "NONE":
    i2c = busio.I2C(board.GP21, board.GP20)  # SCL, SDA
if sensorType == "BME280":
    # address can change based on bme device
    # if 0x76 does not work try 0x77 :)
    sensor = adafruit_bme280.Adafruit_BME280_I2C(i2c, address=0x76)
if sensorType == "ENS160+AHT21":        # ENS160 for air quality and AHT21 for temp and humidity
    temp_humid_sensor = adafruit_ahtx0.AHTx0(i2c, address=0x38)
    air_quality_sensor = adafruit_ens160.ENS160(i2c, address=0x53)
    temp_humid_sensor = adafruit_ahtx0.AHTx0(i2c)  # This needs be tested!!!
    air_quality_sensor = adafruit_ens160.ENS160(i2c)


print("Logging started. Press Ctrl+C to stop.\n")

# This routine shows a simple link in your browser
@server.route("/")
def base(request: Request):
    temp, hum, pres,x,x1 = read_data(sensorType)
    return Response(request, f"<html><body><h1>AIR QUALITY MONITOR</h1><h2>Temp: {temp:.1f} degF</h2><h2>Humidity: {hum:.1f}%</h2><h2>Pressure: {pres:.2f} inHg</h2><a href='/download'>Click here to download {file_name}</a></body></html>", content_type="text/html")


# This routine makes the browser download the file when you visit /download to downloads on your computer. It uses the 'Content-Disposition' header to force the download 
# # We use a generator to read the file in chunks so we don't run out of limited RAM on the Pico
# Note: this is a very basic implementation and does not include error handling for file not found or other issues. It also assumes the file is small enough to be read in chunks of 512 bytes without causing issues. 

#@server.route("/download")
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
    """Task to log data every {timeIncrement} seconds."""
    global file_name, current_day
    while True:
        now = rtc.RTC().datetime

        # Check if the day has changed to start a new file
        if current_day != now.tm_mday:          # Update the date string and filename for the new day

            date_string = f"{now.tm_year}-{now.tm_mon:02d}-{now.tm_mday:02d}"
            file_name = f"/sd/log_{date_string}.txt"
            print(f"New day detected. Logging to new file: {file_name}")
            current_day= now.tm_mday
            startNewFile(file_name) 
        #print(sensorType) 

        temp, hum, pres, x,x1,x2 = read_data(sensorType=sensorType)  
        # Format the timestamp: YYYY-MM-DD HH:MM:SS 
        timestamp = f" {now.tm_hour:02d}:{now.tm_min:02d}:{now.tm_sec:02d}"
        try:
            with open(file_name, "a") as f:
                f.write(f"{timestamp}, {temp:.1f}, {hum:.1f}, {pres:.2f}\n")
            print(f"Logged at {timestamp}s, Temp: {temp:.1f}°F, Humidity: {hum:.1f}%, Pressure: {pres:.2f} inHg")
        except OSError as e:
            print(f"Error writing to SD card: {e}")
        await asyncio.sleep(timeIncrement)
    
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

def read_data(sensorType):
    try:
        if sensorType == "BME280":
            temp = sensor.temperature * 9 / 5 + 32  # Convert to Fahrenheit
            hum = sensor.humidity
            pres = sensor.pressure * 0.02953 # converted to inches Hg
            return temp, hum, pres, 0 ,0 ,0

        elif sensorType == "ENS160+AHT21":
            temp = temp_humid_sensor.temperature * 9 / 5 + 32  # Convert to Fahrenheit
            hum = temp_humid_sensor.relative_humidity
            pres = 0  # ENS160 does not measure pressure
            #air_quality = air_quality_sensor.iaq_index
            return temp, hum, pres,0 ,0, 0 #, air_quality_sensor.iaq_index, air_quality_sensor.iaq_index_accuracy


    except Exception as e:
        print(f"Error reading sensor: {e}")
        
    return 0,0,0,0,0,0



asyncio.run(main())
