
function pullFromAdafruitIO() {
  var spreadsheet = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = spreadsheet.getActiveSheet();

  var temp     = getFeedValue("aq2-temperature");
  var humidity = getFeedValue("aq2-humidity");
  var pressure = getFeedValue("aq2-pressure");
  var altitude = getFeedValue("aq2-altitude");
  var airqual  = getFeedValue("aq2-airquality");

  var row = [new Date(), temp, humidity, altitude, pressure, airqual];
  var rowAlt = [new Date(), temp, humidity, altitude, -pressure, airqual];

  if (parseFloat(pressure) < 0) {
    // Write to Data-ALT sheet only
    var altSheet = spreadsheet.getSheetByName("Data-ALT");

    // Create the sheet if it doesn't exist
    if (!altSheet) {
      altSheet = spreadsheet.insertSheet("Data-ALT");
      altSheet.appendRow(["Timestamp", "Temperature F", "Humidity %", "Altitude ft", "Pressure inHg", "Air Quality Index"]);
    }

    altSheet.appendRow(rowAlt);
    Logger.log(`Pressure below 0 (${pressure}) — logged to Data-ALT only`);
  } else {
    // Write to active sheet only
    if (sheet.getLastRow() === 0) {
      sheet.appendRow(["Timestamp", "Temperature F", "Humidity %", "Altitude ft", "Pressure inHg", "Air Quality Index"]);
    }

    sheet.appendRow(row);
    Logger.log(`Logged → Temp: ${temp}, Humidity: ${humidity}, Altitude: ${altitude}, Pressure: ${pressure}, AirQuality: ${airqual}`);
  }
}

function getFeedValue(feedName) {
  var url = `https://io.adafruit.com/api/v2/${AIO_USERNAME}/feeds/${feedName}/data/last`;
  var options = {
    headers: { "X-AIO-Key": AIO_KEY },
    muteHttpExceptions: true,
    fetchTimeoutSeconds: 60
  };
  var response = UrlFetchApp.fetch(url, options);
  var data     = JSON.parse(response.getContentText());
  return data.value;
}