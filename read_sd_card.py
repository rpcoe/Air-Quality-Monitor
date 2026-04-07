###############  This program will read the index file and print the lastest data run


import os
import board
import busio as io
import digitalio
import storage
import adafruit_sdcard
#import microcontroller
from time import sleep

# Connect to the card and mount the filesystem.
spi = io.SPI(board.GP18, board.GP19, board.GP16)    # SCK, MOSI, MISO
cs = digitalio.DigitalInOut(board.GP17)             # CS pin for SD card
sdcard = adafruit_sdcard.SDCard(spi, cs)
vfs = storage.VfsFat(sdcard)

storage.mount(vfs, "/sd")


with open("/sd/indexfile.txt", "r") as inputfile:
    for line in inputfile:
        i= line
        #print(i)
    inputfile.close
    index = int(line.strip())
    print("\nLast File Index =",index)

while True:
    file_name = "/sd/history"+str(index)+".txt"
    print("\nfilename:", file_name)


    with open(file_name, "r") as inputfile:      
        for line in inputfile:
            print(line)
        inputfile.close    
    #sleep(1)  # Need to input a new index # to read a different file
    print("Enter a new file index to display:")
    index = input() 
    #print(f"Index changed to: {index}")
    print("Index changed to: index =", index)

print("stopped")