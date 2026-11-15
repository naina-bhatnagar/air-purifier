"""Pin numbers for the ESP32. These are placeholders: change them to match your wiring."""

# PMS5003 sensors (each on its own UART, 9600 baud). Sensor TX goes to the ESP32 RX pin.
BEFORE_UART, BEFORE_RX, BEFORE_TX = 1, 16, 17    # sensor before the filter
AFTER_UART, AFTER_RX, AFTER_TX = 2, 18, 19       # sensor after the filter

# DS3231 clock (I2C)
I2C_ID, I2C_SCL, I2C_SDA = 0, 22, 21

# Relay board: low, medium, high. Most cheap modules switch ON when the pin is LOW.
RELAY_PINS = (25, 26, 27)
RELAY_ACTIVE_LOW = True

# Status lights: green, yellow, orange, red (best, average, moderate, severe)
LED_PINS = (4, 5, 23, 15)

# Buttons to ground, using the internal pull-ups: start/stop, faster, slower, auto
BUTTON_PINS = (32, 33, 13, 14)
