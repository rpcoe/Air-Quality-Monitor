import wifi
import socketpool
import adafruit_requests

wifi.radio.connect("YOUR_SSID", "YOUR_PASSWORD")
pool = socketpool.SocketPool(wifi.radio)
https = adafruit_requests.Session(pool, ssl_context)

SCRIPT_URL = "https://script.google.com/macros/s/YOUR_SCRIPT_ID/exec"

# Send sensor data
temp = 23.5
humidity = 60

url = f"{SCRIPT_URL}?temp={temp}&humidity={humidity}"
response = https.get(url)
print(response.text)  # Should print "OK"




"""
Option 2: Google Apps Script Web App (Recommended ✅)
This is the easiest and most reliable method. You deploy a Google Apps Script as a web app that acts as a middleman — the Pico W sends a simple HTTP GET/POST, and the script writes to the sheet.
1. Create the Apps Script (in Google Sheets → Extensions → Apps Script):
javascriptfunction doGet(e) {
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
  var row = [new Date(), e.parameter.temp, e.parameter.humidity];
  sheet.appendRow(row);
  return ContentService.createTextOutput("OK");
}
Deploy as a Web App (access: Anyone).

"""