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

from adafruit_bme280 import basic as adafruit_bme280
from adafruit_httpserver import Server, Request, Response, POST


timeIncrement = 10  # Set the time increment in seconds
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
#file_name = "/sd/history"+str(index)+".txt"  # file_name needs to be global to be used in the server route
#file_name = "/sd/history1.txt"



#  uncomment this section out to start a new index file each run
with open("/sd/indexfile.txt", "w") as writefile:   
    print( 0, file=writefile)
    writefile.close()

with open("/sd/indexfile.txt", "r") as inputfile:
    for line in inputfile:
        i= line
        #print(i)
    inputfile.close
    index = int(line.strip()) + 1  # Increment index to start a new file
    print("\nindex =",index)
    file_name = "/sd/history"+str(index)+".txt"  # file_name needs to be global to be used in the server route

print("\nfilename:", file_name)

 # start a new index file from 0
 #comment this out to start a new index file saving the data from previous runs
with open("/sd/indexfile.txt", "w") as writefile:       
    print(str(index), file=writefile)
    writefile.close()



# Open the new history file in append mode ('a')
# We write the header first
with open(file_name, "w") as f:
    f.write("Time(s), Temp(°F), Humidity(%), Pressure(inHg)\n")

print("Logging started. Press Ctrl+C to stop.\n")

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

# This route makes the browser download the file when you visit /download
@server.route("/download")
def download_file(request: Request):
    # Change 'history1.txt' to your actual file_name variable logic
    with open(file_name, "r") as f:
        return Response(request, f.read(), content_type="text/plain")

# This route shows a simple link in your browser
@server.route("/")
def base(request: Request):
    return Response(request, f"<html><body><h1>Pico W Data Logger</h1><a href='/download'>Click here to download {file_name}</a></body></html>", content_type="text/html")

async def log_data():
    """Task to log data every 10 seconds."""
    total_time = 0
    while True:
        temp = bme280.temperature * 9 / 5 + 32  # Convert to Fahrenheit
        hum = bme280.relative_humidity
        pres = bme280.pressure * 0.02953 # converted to inches
        
        with open(file_name, "a") as f:
            f.write(f"{total_time}, {temp:.2f}, {hum:.2f}, {pres:.2f}\n")
        
        print(f"Logged at {total_time}s, Temp: {temp:.2f}°F, Humidity: {hum:.2f}%, Pressure: {pres:.2f} inHg")
        total_time += timeIncrement
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
            # print(f"Server poll error: {e}") 
            pass
        
        # This is CRITICAL: it allows the logger task to run
        await asyncio.sleep(0.1)

async def main():
    # Run both the logger and the server at the same time
    await asyncio.gather(log_data(), run_server())

asyncio.run(main())
"""
total_time = 0
while True:
    try:
        # Flash LED to show activity
        led.value = True
        sleep(ledTime)
        led.value = False

        # Gather data from BME280 
        temp = bme280.temperature* 9 / 5 + 32
        humidity = bme280.relative_humidity
        pressure = bme280.pressure * 0.02953  # Convert hPa to inHg

        # Append data to the SD card file
        with open(file_name, "a") as f:
            data_string = f"{total_time}, {temp:.2f}, {humidity:.2f}, {pressure:.2f}\n"
            f.write(data_string)
            print("Time, Temp(°F), Humidity(%), Pressure(inHg):", data_string.strip())

        # Wait for the next increment
        sleep(timeIncrement - ledTime)
        total_time += timeIncrement

    except OSError as e:
        print("SD card error or sensor unplugged:", e)
        break
"""