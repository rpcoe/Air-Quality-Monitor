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

filePrefix = os.getenv("FILE_PREFIX") 
file_name = f"/sd/{filePrefix}_LOG.csv"  # Global variable to hold the current file name for logging

while True:
    print("\nfile_name:", file_name)

    with open(file_name, "r") as inputfile:      
        for line in inputfile:
            print(line)
        inputfile.close    

    #print("Finished  -  Run again? (press Enter to continue, or Ctrl+C to stop)")
    input = input()

    sleep(3)  # Sleep to allow time for the file to be read before the next input

print("stopped")