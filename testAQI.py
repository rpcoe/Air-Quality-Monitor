# Test AQI calculation with various gas and humidity levels
gas_baseline = 200000  # Example baseline for gas resistance (in ohms)
hum_baseline = 40     # Example baseline for humidity (%)
def calculate_aqi(gas, hum):
    hum_weighting = 25
    gas_weight = 100-hum_weighting
    
    # Humidity offset (ideal is 40%)
    gas_offset = gas_baseline-gas
    hum_offset = hum - hum_baseline
    # Score humidity
    if hum_offset > 0:
        #hum_score = (100 - hum_baseline - hum_offset) / (100 - hum_baseline) * (hum_weighting )
        hum_score = ((100 - hum) / (100 - hum_baseline)) * (hum_weighting)

    else:
        hum_score = ((hum) / hum_baseline) * (hum_weighting )

    # Score gas
    
    gas_score = (gas / gas_baseline) * (gas_weight )
    iaq_score = gas_score + hum_score
    if iaq_score > 300:    # TODO delete this after testing, just to see the raw scores for gas and humidity before the AQI calculation clamps it to 500
        print(f"Gas Score: {gas_score:.1f}, Humidity Score: {hum_score:.1f}")
        #f.write(f"{now}, {gas_score:.1f}, Humidity Score: {hum_score:.1f}, {hum:.1f},{iaq_score:.0f}, \n")  

    return min(max(iaq_score, 0), 500)  # clamp to 0–500

resistance = 200000
hum = 20
while True:
    #resistance += 10000
    hum +=5
    aqi = calculate_aqi(resistance, hum)
    print(f"Resistance: {resistance}, Humidity: {hum}, Calculated AQI: {aqi:.0f}")
    if resistance > 300000 or hum > 100:
        break