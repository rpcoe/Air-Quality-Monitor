#  TODO List:
#  - Update webpage to show the most recent data in real time without needing to refresh the page
#  - Update webpage to display BME680 gas resistance and calculated eCO2, TVOC, and AQI values
#  - Add a graphing library to visualize the data on the web interface
#  - Add a method to send alerts (e.g. email or SMS) if certain thresholds are exceeded

from time import sleep, time
import os
import ipaddress
import gc
import wifi
import ssl
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
import adafruit_veml7700

from adafruit_httpserver import Server, Request, Response, POST
from adafruit_httpserver import ChunkedResponse

# ── Config ────────────────────────────────────────────

AIO_USERNAME  = os.getenv("AIO_USERNAME")
AIO_KEY       = os.getenv("AIO_KEY")
# FIX #1: Correct Adafruit IO URL — post to a specific feed's data endpoint, not the feed list
# Replace "air-quality" with your actual feed key from io.adafruit.com
AIO_FEED_KEY  = os.getenv("AIO_KEY", "air-quality")
AIO_URL       = f"https://io.adafruit.com/api/v2/{AIO_USERNAME}/feeds"

SEALEVELPRESSURE_HPA = 1013.25

# Metar configuration
STATION   = os.getenv('METAR_STATION')
METAR_URL = URL = f"https://aviationweather.gov/api/data/metar?ids={STATION}"

prefix = os.getenv('FILE_PREFIX', 'AQ0')  
# FIX #2: Rename to aio_headers to avoid collision with the local 'headers' var in download_file()
aio_headers = {
    "X-AIO-Key": AIO_KEY,
    "Content-Type": "application/json"
}


# ── NTP ───────────────────────────────────────────────
# FIX #3: Use managed_pool (defined below) instead of undefined 'pool'
def update_RTC_from_NTP():
    try:
        print("Syncing time with internet...")
        ntp = adafruit_ntp.NTP(managed_pool, tz_offset=-7)  # -7 for PDT
        rtc.RTC().datetime = ntp.datetime
        print("Clock synchronized!")
    except Exception as e:
        if isinstance(e, OSError) and e.args[0] == 110:  # ETIMEDOUT
            sleep(5)
            print("NTP request timed out. Will try again.")
            try:
                ntp = adafruit_ntp.NTP(managed_pool, tz_offset=-7)
                rtc.RTC().datetime = ntp.datetime
            except Exception as e2:
                print(f"NTP retry failed: {e2}")
        else:
            print(f"Could not sync time: {e}")
            print("Logging will proceed with default system time.")


def startNewFile(file_name):
    if sdExists == False:
        print("SD card not found. Cannot create log file.")
        return
    with open(file_name, "w") as writefile:
        writefile.write("AIR QUALITY MONITOR LOG  \n")
        writefile.write(" Time, Temp(degF), Humidity(%), Pressure(inHg), AQI, Altitude(ft), Resistance(Ohms), Light(Lux)\n")
    print(f"New file created, writing header: {file_name}")


def read_data(sensorType, pres):
    tempCalib = float(os.getenv('TEMP_CALIB', 0))
    altCalib  = float(os.getenv('ALT_CALIB', 0))
    try:
        if sensorType == "BME280":
            temp       = sensor.temperature * 9 / 5 + 32 + tempCalib
            hum        = sensor.humidity
            pres       = sensor.pressure
            alt        = (last_SL_pressure - pres) * 8.33 + altCalib
            pres       = pres * 0.02953
            resistance = 0
            aqi        = 0
            light      = 0
        elif sensorType == "BME680":
            sensor.sea_level_pressure = last_SL_pressure
            temp       = sensor.temperature * 9 / 5 + 32 + tempCalib
            hum        = sensor.relative_humidity
            pres       = sensor.pressure * 0.02953
            alt        = sensor.altitude + altCalib
            resistance = sensor.gas
            aqi        = calculate_aqi(resistance, hum)
            light      = 0
        elif sensorType == "VEML7700":
            temp       = 0
            hum        = 0
            pres       = 0
            alt        = 0
            resistance = 0
            aqi        = 0
            light      = sensor.lux
        else:
            return 0, 0, 0, 0, 0, 0, 0
    except Exception as e:
        print(f"Error reading sensor: {e}")
        return 0, 0, 0, 0, 0, 0, 0
    return temp, hum, pres, resistance, alt, aqi, light


def calculate_aqi(gas, hum):
    hum_weighting = 25
    gas_weight     = 100 - hum_weighting
    hum_baseline   = 40
    gas_offset     = gas_baseline - gas
    hum_offset     = hum - hum_baseline

    if hum_offset > 0:
        hum_score = ((100 - hum) / (100 - hum_baseline)) * hum_weighting
    else:
        hum_score = (hum / hum_baseline) * hum_weighting

    gas_score = (gas / gas_baseline) * gas_weight
    iaq_score = gas_score + hum_score
    return min(max(iaq_score, 0), 500)


# FIX #4: Replace blocking sleep() in the smoothing loop with asyncio.sleep() so the
#          web server keeps responding during the update interval.
async def read_data_smooth(sensorType):
    slp = get_sea_level_pressure(False)
    temp_s, hum_s, pres_s, res_s, alt_s, aqi_s, light_s = read_data(sensorType, slp)
    alpha = 0.02

    for i in range(update_interval):
        temp, hum, pres, resistance, alt, aqi, light = read_data(sensorType, slp)
        temp_s  = alpha * temp      + (1 - alpha) * temp_s
        hum_s   = alpha * hum       + (1 - alpha) * hum_s
        pres_s  = alpha * pres      + (1 - alpha) * pres_s
        res_s   = alpha * resistance + (1 - alpha) * res_s
        alt_s   = alpha * alt       + (1 - alpha) * alt_s
        aqi_s   = alpha * aqi       + (1 - alpha) * aqi_s
        light_s = alpha * light     + (1 - alpha) * light_s

        led.value = True
        await asyncio.sleep(ledTime)   # non-blocking flash
        led.value = False
        await asyncio.sleep(1)         # non-blocking 1 s wait

    return temp_s, hum_s, pres_s, res_s, alt_s, aqi_s, light_s


def write_data(temp, hum, pres, alt, aqi, resistance, light):
    now = rtc.RTC().datetime
    now = f"{now.tm_year}-{now.tm_mon:02d}-{now.tm_mday:02d} {now.tm_hour:02d}:{now.tm_min:02d}:{now.tm_sec:02d}"
    try:
        with open(file_name, "a") as f:
            f.write(f"{now}, {temp:.1f}, {hum:.1f}, {pres:.2f},  {alt:.0f},{aqi:.0f},{resistance:.0f},{light:.0f} \n")
        print(f"Logged at {now}  {temp:.1f}F, {hum:.1f}%, {pres:.2f}inHg, {alt:.0f}ft, aqi={aqi:.0f}, res={resistance:.0f}, lux={light:.0f}")
    except OSError as e:
        print(f"Error writing to SD card: {e}")


# FIX #5: Correct Adafruit IO send function
#   - Uses the proper /feeds/{key}/data endpoint (set in AIO_URL above)
#   - Sends auth headers (aio_headers)
#   - Always closes the response
#   - Wrapped in try/except so a failure doesn't crash the logger
def send_to_adafruit(temp, hum, pres, aqi, alt , light):
    if not sendAdafruit:
        return
    gc.collect()
    prefix = os.getenv('FILE_PREFIX', 'AQ0')
    feeds = [
        ("aq1-temperature", temp),
        ("{prefix}-humidity",    hum),
        ("{prefix}-altitude",    pres),
        ("{prefix}-aqi",         aqi),
        ("{prefix}-light",       light),
    ]
    for feed_key, value in feeds:
       # url = f"https://io.adafruit.com/api/v2/{AIO_USERNAME}/feeds/{feed_key}/data"
        url = f"{AIO_URL}/{feed_key}/data"
        print(f"Sending to AIO {url}: {value}")
        try:
            response = https.post(url, json={"value": value}, headers=aio_headers, timeout=10)
            print(f"AIO {feed_key}: {response.status_code}")
            response.close()
        except OSError as e:
            print(f"Adafruit IO error on {feed_key}: {e}")
            # OSError 113 = EHOSTUNREACH — network gone; skip remaining feeds this cycle
            break

def get_sea_level_pressure(first_run=False):
    global last_SL_pressure, https
    print(f"Fetching sea level pressure for {STATION}...")
    gc.collect()
    metar_text = None

    for attempt in range(3):
        try:
            response   = https.get(METAR_URL, timeout=15)
            metar_text = response.text
            response.close()
            break                          # success
        except OSError as e:
            print(f"METAR attempt {attempt+1} failed: {e}")
            # Rebuild the session EVERY retry — clears EINPROGRESS/DNS state
            try:
                https = adafruit_requests.Session(managed_pool, ssl_context)
            except Exception as rebuild_err:
                print(f"Session rebuild failed: {rebuild_err}")
            gc.collect()
            sleep(3)                       # give the radio time to settle
    
    sea_level_pressure = get_pressure_robust(metar_text)
    if sea_level_pressure is None:
        print("Using last known SLP.")
        return last_SL_pressure

    if not first_run:
        sea_level_pressure = 0.95 * last_SL_pressure + 0.05 * sea_level_pressure
        last_SL_pressure   = sea_level_pressure

    print(f"SLP: {sea_level_pressure:.2f} hPa")
    return sea_level_pressure


def get_pressure_robust(text):
    if text is None or "METAR" not in text:
        return None
    try:
        if "SLP" in text:
            idx     = text.find("SLP")
            slp_str = text[idx+3 : idx+6]
            if slp_str.isdigit():
                val = int(slp_str)
                hpa = (10000 + val) / 10 if val < 500 else (9000 + val) / 10
                return hpa
        if " A" in text:
            idx     = text.find(" A") + 1
            alt_str = text[idx+1 : idx+5]
            if alt_str.isdigit():
                inhg = float(alt_str) / 100
                return inhg * 33.8639
    except Exception as e:
        print(f"Parsing error: {e}")
    return None


# ── Constants ─────────────────────────────────────────
update_interval = 20
ledTime         = 0.02
sdExists        = True

led           = digitalio.DigitalInOut(board.LED)
led.direction = digitalio.Direction.OUTPUT

prefix           = os.getenv('FILE_PREFIX', 'AQ0')
last_SL_pressure = SEALEVELPRESSURE_HPA
gas_baseline     = float(os.getenv("GAS_BASELINE", "200000"))
sendAdafruit     = os.getenv("SEND_TO_ADAFRUIT", "false").lower() == "true"
# Global flag
need_slp_update = False

# ── WiFi ──────────────────────────────────────────────
print("Connecting to WiFi...")

# FIX #6: Only call set_ipv4_address() when DHCP is disabled
DHCP_ENABLE = os.getenv("DHCP_ENABLE", "true").lower() == "true"
if DHCP_ENABLE:
    print("DHCP is enabled. Connecting with dynamic IP address.")
else:
    ipv4    = ipaddress.IPv4Address(os.getenv("IP_ADDRESS"))
    netmask = ipaddress.IPv4Address(os.getenv("MY_NETMASK"))
    gateway = ipaddress.IPv4Address(os.getenv("MY_GATEWAY"))
    wifi.radio.set_ipv4_address(ipv4=ipv4, netmask=netmask, gateway=gateway)
    print(f"Using IP: {ipv4}  gateway: {gateway}  netmask: {netmask}")

wifi.radio.connect(os.getenv('CIRCUITPY_WIFI_SSID'), os.getenv('CIRCUITPY_WIFI_PASSWORD'))
print(f"Connected! Visit http://{wifi.radio.ipv4_address}\n")

# ── SD Card ───────────────────────────────────────────
spi = busio.SPI(board.GP18, board.GP19, board.GP16)
cs  = digitalio.DigitalInOut(board.GP17)
try:
    sdcard = adafruit_sdcard.SDCard(spi, cs)
    vfs    = storage.VfsFat(sdcard)
    storage.mount(vfs, "/sd")
except Exception as e:
    print(f"Error mounting SD card: {e}")
    sdExists = False

# ── Network stack (ONE pool for everything) ───────────
managed_pool = adafruit_connection_manager.get_radio_socketpool(wifi.radio)
ssl_context  = adafruit_connection_manager.get_radio_ssl_context(wifi.radio)
https        = adafruit_requests.Session(managed_pool, ssl_context)

# ── Web server ────────────────────────────────────────
server = Server(managed_pool, "/sd", debug=True)
server.socket_timeout = 1.0   # FIX #7: 0.1 s was too short for a shared pool
server.start(str(wifi.radio.ipv4_address), port=80)

# ── NTP sync & file setup ─────────────────────────────
update_RTC_from_NTP()

now         = rtc.RTC().datetime
date_string = f"{now.tm_year}-{now.tm_mon:02d}-{now.tm_mday:02d}"
current_day = now.tm_mday
filePrefix  = os.getenv("FILE_PREFIX")
file_name   = f"/sd/{filePrefix}_{date_string}.csv"
print(f"Current filename: {file_name}")

try:
    os.stat(file_name)
    print("File exists, appending data.")
    timestamp = f"{now.tm_year}-{now.tm_mon:02d}-{now.tm_mday:02d} {now.tm_hour:02d}:{now.tm_min:02d}:{now.tm_sec:02d}"
    with open(file_name, "a") as f:
        f.write(f"RESTART:  {timestamp}  \n")
except OSError:
    startNewFile(file_name)

last_SL_pressure = get_sea_level_pressure(True)
count = 0

# ── Sensor init ───────────────────────────────────────
sensorType = os.getenv("SENSOR_TYPE", "NONE").upper()
try:
    if sensorType != "NONE":
        i2c = busio.I2C(board.GP21, board.GP20)
        sleep(1)
    if sensorType == "BME280":
        sensor = adafruit_bme280.Adafruit_BME280_I2C(i2c, address=0x76)
    elif sensorType == "BME680":
        sensor = adafruit_bme680.Adafruit_BME680_I2C(i2c, address=0x77, refresh_rate=1)
    elif sensorType == "VEML7700":
        sensor = adafruit_veml7700.VEML7700(i2c)
except Exception as e:
    print(f"Sensor init failed: {e}")

# Discard first (potentially noisy) reading
temp, hum, pres, altitude, eCO2, resistance, light = read_data(sensorType=sensorType, pres=last_SL_pressure)
sleep(10)
print("Logging started. Press Ctrl+C to stop.\n")


# ── Web routes ────────────────────────────────────────

# FIX #8: Re-enable the home route (was accidentally commented out)
@server.route("/")
def base(request: Request):
    temp, hum, pres, resistance, alt, aqi, light = read_data(sensorType=sensorType, pres=last_SL_pressure)
    return Response(request,
        f"<html><body>"
        f"<h1>AIR QUALITY MONITOR</h1>"
        f"<h2>Temp: {temp:.1f} degF</h2>"
        f"<h2>Humidity: {hum:.1f}%</h2>"
        f"<h2>Pressure: {pres:.2f} inHg</h2>"
        f"<h2>AQI: {aqi:.0f}</h2>"
        f"<h2>Resistance: {resistance:.0f} ohms</h2>"
        f"<h2>Light: {light:.0f} lux</h2>"
        f"<a href='/download'>Download {file_name}</a>"
        f"</body></html>",
        content_type="text/html")


@server.route("/download")
def download_file(request: Request):
    global file_name
    target_file   = file_name
    file_size     = os.stat(target_file)[6]
    download_name = target_file.split("/")[-1].replace(".txt", ".csv")

    def file_chunk_generator():
        with open(target_file, "rb") as f:
            bytes_sent = 0
            while bytes_sent < file_size:
                chunk = f.read(min(1024, file_size - bytes_sent))
                if not chunk:
                    break
                yield chunk
                bytes_sent += len(chunk)

    resp_headers = {
        "Content-Disposition": f'attachment; filename="{download_name}"',
        "Content-Length": str(file_size),
        "Connection": "close"
    }
    print(f"Sending: {download_name} ({file_size} bytes)")
    return ChunkedResponse(request, file_chunk_generator, content_type="text/csv", headers=resp_headers)


# ── Async tasks ───────────────────────────────────────

async def log_data():
    """Log sensor data and optionally push to Adafruit IO."""
    global file_name, current_day, count, last_SL_pressure, need_slp_update
    while True:
        # Check for day rollover → new log file
        now = rtc.RTC().datetime
        if now.tm_mday != current_day:
            current_day = now.tm_mday
            date_string = f"{now.tm_year}-{now.tm_mon:02d}-{now.tm_mday:02d}"
            file_name   = f"/sd/{filePrefix}_{date_string}.csv"
            startNewFile(file_name)
            update_RTC_from_NTP()  # re-sync at day boundary

        # Smooth readings (now async — server keeps polling during this)
        temp, hum, pres, resistance, alt, aqi, light = await read_data_smooth(sensorType)
        write_data(temp, hum, pres, alt, aqi, resistance, light)

        # FIX #9: Adafruit IO send is now in the right place (inside the async logger)
        #          and uses the correct function with proper headers + error handling
        if sendAdafruit:
            send_to_adafruit(temp, hum, pres, aqi, resistance, light)

        # Every 10 cycles update sea level pressure
        count += 1
        if count >= 10:
            count = 0
            need_slp_update = True
            #last_SL_pressure = get_sea_level_pressure(False)


async def run_server():
    global need_slp_update, last_SL_pressure
    while True:
        if need_slp_update:
            need_slp_update = False
            await asyncio.sleep(0.5)   # let any in-flight poll() socket drain
            gc.collect()
            last_SL_pressure = get_sea_level_pressure(False)

        try:
            server.poll()
        except Exception as e:
            print(f"Server poll error: {e}")
        await asyncio.sleep(0)


async def main():
    await asyncio.gather(log_data(), run_server())


asyncio.run(main())
