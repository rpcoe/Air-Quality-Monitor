import os
import wifi
import socketpool
import board
import time
from digitalio import DigitalInOut, Direction
from adafruit_httpserver import Server, Request, Response, POST

# 1. Setup Onboard LED
led = DigitalInOut(board.LED)
led.direction = Direction.OUTPUT

# 2. Connect to WiFi
print("Connecting to WiFi...")
wifi.radio.connect(os.getenv('CIRCUITPY_WIFI_SSID'), os.getenv('CIRCUITPY_WIFI_PASSWORD'))
print(f"Connected! IP Address: {wifi.radio.ipv4_address}")

# 3. Initialize Server
pool = socketpool.SocketPool(wifi.radio)
server = Server(pool, debug=True)

# 4. Define the HTML Interface
def webpage():
    status = "ON" if led.value else "OFF"
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body {{ font-family: sans-serif; text-align: center; background: #f4f4f4; }}
            .btn {{ padding: 20px 40px; font-size: 20px; color: white; border: none; border-radius: 8px; cursor: pointer; }}
            .on {{ background-color: #4CAF50; }}
            .off {{ background-color: #f44336; }}
        </style>
    </head>
    <body>
        <h1>Pico W LED Control</h1>
        <p>The LED is currently: <strong>{status}</strong></p>
        <form method="POST"><button class="btn on" name="toggle" value="ON" type="submit">Turn ON</button></form><br>
        <form method="POST"><button class="btn off" name="toggle" value="OFF" type="submit">Turn OFF</button></form>
    </body>
    </html>
    """

# 5. Define Routes
@server.route("/", [POST, "GET"])
def base(request: Request):
    if request.method == POST:
        raw_text = request.body.decode("utf-8")
        if "toggle=ON" in raw_text:
            led.value = True
        elif "toggle=OFF" in raw_text:
            led.value = False
            
    return Response(request, webpage(), content_type="text/html")

# 6. Start Server
server.start(str(wifi.radio.ipv4_address),port=80)

while True:
    try:
        server.poll()
    except Exception as e:
        print(f"Error: {e}")
        continue