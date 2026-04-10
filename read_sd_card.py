###############  This program will read the log files and print the the selected data run

import os
import board
import busio as io
import digitalio
import storage
import adafruit_sdcard
from time import sleep
import rtc

# Connect to the card and mount the filesystem.
spi = io.SPI(board.GP18, board.GP19, board.GP16)    # SCK, MOSI, MISO
cs = digitalio.DigitalInOut(board.GP17)             # CS pin for SD card
sdcard = adafruit_sdcard.SDCard(spi, cs)
vfs = storage.VfsFat(sdcard)

storage.mount(vfs, "/sd")
now = rtc.RTC().datetime
date_string = f"{now.tm_year}-{now.tm_mon:02d}-{now.tm_mday:02d}"
#date_string = "2026-04-07"  # Hardcoded for testing

# Build the filename
file_name = f"/sd/log_{date_string}.txt"

while True:
    print("\nfile_name:", file_name)


    with open(file_name, "r") as inputfile:      
        for line in inputfile:
            print(line)
        inputfile.close    
    #sleep(1)  # Need to input a new index # to read a different file
    print("Enter a new file date to display: YYYY-MM-DD")
    date_input = input()
    file_name = f"/sd/log_{date_input}.txt"#print(f"Index changed to: {index}")
    print("File changed to: ", file_name)
    sleep(3)  # Sleep to allow time for the file to be read before the next input

print("stopped")