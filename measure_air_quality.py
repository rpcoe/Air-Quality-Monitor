#  TODO List:
#  - Add a simple web interface to view the data without downloading
#  - Start a new history file each day at midnight
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
        f.write("Time, Temp(degF), Humidity(%), Pressure(inHg)\n")

timeIncrement = 30  # Set the time increment in seconds for logging data. Adjust as needed, but remember that very short intervals may fill up the SD card quickly and may not be necessary for air quality monitoring.
ledTime = .01       # time that the led is flashing each cycle

led = digitalio.DigitalInOut(board.LED)
led.direction = digitalio.Direction.OUTPUT

# Create sensor object, using the board's default I2C bus.
i2c = busio.I2C(board.GP21, board.GP20)  # SCL, SDA

# address can change based on bme device
# if 0x76 does not work try 0x77 :)
bme280 = adafruit_bme280.Adafruit_BME280_I2C(i2c, address=0x76)

# Connect to the card and mount the filesystem.
spi = busio.SPI(board.GP18, board.GP19, board.GP16)  # SCK, MOSI, MISO
cs = digitalio.DigitalInOut(board.GP17)  # CS pin for SD card
sdcard = adafruit_sdcard.SDCard(spi, cs)
vfs = storage.VfsFat(sdcard)
storage.mount(vfs, "/sd")


# Connect to WiFi
#  set static IP address
ipv4 = ipaddress.IPv4Address("192.168.254.230")
netmask = ipaddress.IPv4Address("255.255.255.0")
gateway = ipaddress.IPv4Address("192.168.254.254")
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
except OSError:
    startNewFile(file_name)  # This will create the file and write the header if it doesn't exist 
    



print("Logging started. Press Ctrl+C to stop.\n")

# We write the header first

    # Format the timestamp: YYYY-MM-DD HH:MM:SS
timestamp = f"{now.tm_year}-{now.tm_mon:02d}-{now.tm_mday:02d} {now.tm_hour:02d}:{now.tm_min:02d}:{now.tm_sec:02d}"

print(f"Current time: {timestamp}")
with open(file_name, "a") as f:
    f.write(f"RESTART:  {timestamp}  \n")
#    f.write(f"Time, Temp(°F), Humidity(%), Pressure(inHg):  Index = {index}  \n")


# This routine shows a simple link in your browser
@server.route("/")
def base(request: Request):
    temp, hum, pres = read_data_bme280()
    return Response(request, f"<html><body><h1>AIR QUALITY MONITOR</h1><h2>Temp: {temp:.1f} degF</h2><h2>Humidity: {hum:.1f}%</h2><h2>Pressure: {pres:.2f} inHg</h2><a href='/download'>Click here to download {file_name}</a></body></html>", content_type="text/html")


# This routine makes the browser download the file when you visit /download to downloads on your computer. It uses the 'Content-Disposition' header to force the download 
# # We use a generator to read the file in chunks so we don't run out of limited RAM on the Pico
# Note: this is a very basic implementation and does not include error handling for file not found or other issues. It also assumes the file is small enough to be read in chunks of 512 bytes without causing issues. 

@server.route("/download")
def download_file(request: Request):
    
    # 1. Get the actual size of the file in bytes
    file_stats = os.stat(file_name)
    file_size = file_stats[6] # Index 6 is the size in bytes
    
    # 2. Prepare the filename for the PC
    download_name = file_name.split("/")[-1].replace(".txt", ".csv")

    def file_chunk_generator():
        with open(file_name, "rb") as f:
            while True:
                chunk = f.read(1024) # Increased to 1024 for speed
                if not chunk:
                    break
                yield chunk

    # 3. Explicitly tell Chrome the file size and name
    headers = {
        "Content-Disposition": f'attachment; filename="{download_name}"',
        "Content-Length": str(file_size),
        "Connection": "close"
    }

    print(f"Sending {download_name} ({file_size} bytes)...")
    
    return ChunkedResponse(
        request, 
        file_chunk_generator, 
        content_type="text/csv", 
        headers=headers
    )

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
            # Write header to the new file
            #with open(file_name, "w") as f:
            #    f.write("Time, Temp(degF), Humidity(%), Pressure(inHg)\n")

        #date_string = f"{now.tm_year}-{now.tm_mon:02d}-{current_day:02d}"
        #file_name = f"/sd/log_{date_string}.txt"
        
        temp, hum, pres = read_data_bme280()        
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

def read_data_bme280():
    try:
        temp = bme280.temperature * 9 / 5 + 32  # Convert to Fahrenheit
        hum = bme280.relative_humidity
        pres = bme280.pressure * 0.02953 # converted to inches Hg
    except Exception as e:
        print(f"Error reading BME280 sensor: {e}")
        temp = 0
        hum = 0
        pres = 0
    return temp, hum, pres



asyncio.run(main())
