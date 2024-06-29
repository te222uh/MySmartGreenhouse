

######################################################
# MQTT client running on Raspberry Pi Pico W
# with attached sensors for measuring temperature,
# humidity, light and soil moisture. 
#
# Client runs in a loop continusly sending
# sensor data to its MQTT broker and
# checking for commands from it to execute on device.
#
# Tomas Eriksson, 2024/06/24
# Code free for anyone to use and modifiy.

# Required imports 

import network
import time
import json
import random
import ubinascii
import ssl
import utime
import sys
from umqtt.simple import MQTTClient
import config # separate config file containing more sensitive configuration like passwords.
import dht
import ntptime

# Functions

# Make log entry with timestamp to log file
def Log(message, level="INFO", filePath="log.txt"):
    if logLevels[level] >= currentLogLevel:
        timeStamp = utime.localtime()
        formattedTime = "{:02d}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}".format(
            timeStamp[0], timeStamp[1], timeStamp[2], timeStamp[3], timeStamp[4], timeStamp[5]
        )
        logMessage = "[{}] {}: {}\n".format(formattedTime, level, message)
        with open(filePath, "a") as logFile:
            logFile.write(logMessage)

# Format exeption in a nice way
def FormatException(e):
    return "{}: {}".format(type(e).__name__, e)
    

# Connect to Wi-Fi
def ConnectWifi():
    sta_if = network.WLAN(network.STA_IF)
    sta_if.active(True)
    sta_if.connect(ssid, password)
    while not sta_if.isconnected():
        pass
    print("Connected to Wi-Fi")

# Read certificates
def ReadPem(file):
    with open(file, "r") as input:
        text = input.read().strip()
        split_text = text.split("\n")
        base64_text = "".join(split_text[1:-1])
        return ubinascii.a2b_base64(base64_text)

# Publish sensor data to topic in MQTT broker
def PublishData():
    #
    # DHT11 sensor
    #
    dhtSensor.measure()
    # Measure temperature
    temperature = dhtSensor.temperature()
    # Measure humidiy
    humidity = dhtSensor.humidity()
    
    # Measure moisture level and calculate percentage
    # 65535 is the max value delivered by the sensor
    
    #
    # Moisture sensor
    #
    powerPin.value(1)  # Turn on the sensor
    time.sleep(1)      # Wait for the sensor to stabilize
    # Convert measurement from moisture sensor in to percentage
    soilMoisture = 100 - ((soilMoistureSensor.read_u16() / 65535) * 100)
    powerPin.value(0)  # Turn off the sensor
    
    #
    # Photoresistor sensor
    #
    # Convert measurement from photoresistor in to precent
    lightLevel = 100 - ((photoResistorSensor.read_u16() / 1500) * 100)
    
    # Avoid negative values from photresistor 
    if lightLevel < 0:
        lightLevel = 0
    
    # Prepare json for MQTT message
    data = {
        "temperature": round(temperature),
        "humidity": round(humidity),
        "moisture": round(soilMoisture),
        "light": round(lightLevel)
    }
    payload = json.dumps(data)
    print(f"Publishing data to topic {mqttTopicSensorData}: {payload}")
    # Publish the sensor data to AWS IoT Core
    client.publish(mqttTopicSensorData, payload)

# Publish device states to topic in MQTT broker
def PublishMqtt(key, value, topic):
    data = {
        key: value
    }
    payload = json.dumps(data)
    client.publish(topic, payload)

# Callback function to handle received messages
def OnActionMessage(topic, msg):
    print((topic, msg))
        
    if msg == b"turn on led1":
        led.value(1)
        PublishMqtt("led1","On",mqttTopicState)
    elif msg == b"turn off led1":
        led.value(0)
        PublishMqtt("led1","Off",mqttTopicState)
    else:
        print("Unknown message");
        
# Flash led        
def FlashLed(noOfTimes):
    led.value(0) # Make sure led is off
    for i in range(noOfTimes,0,-1): 
        led.value(1)
        time.sleep(1)
        led.value(0)
        time.sleep(1)
    time.sleep(1)
        
#
# Global variables
#

# Log levels
logLevels = {
    "DEBUG": 10,
    "INFO": 20,
    "WARNING": 30,
    "ERROR": 40,
    "CRITICAL": 50,
}

# Set log level to INFO
currentLogLevel = logLevels["INFO"]

# WiFi
ssid = config.ssid # Store sensitive configuration in separate config file
password = config.password

# MQTT 
mqttHost = "a2ua3ctopteqfq-ats.iot.eu-central-1.amazonaws.com"
mqttPort = 8883
mqttTopicSensorData = "device/pico1/data"
mqttTopicTask = "device/pico1/task"
mqttTopicState = "device/pico1/state"
clientId = ubinascii.hexlify("SmartGreenHouse")

# Certificate files
caCert = ReadPem("/custom/certs/AmazonRootCA1.pem")
clientCert = ReadPem("/custom/certs/certificate.pem.crt")
clientKey = ReadPem("/custom/certs/private.pem.key")

# Led
led = machine.Pin(17, machine.Pin.OUT)
led.value(0) # Make sure led is off from start

# Log that we are starting program and flash led once
Log("Pico is starting...")
FlashLed(1)

# Connect to the wifi network and flash led two times when done
ConnectWifi()
FlashLed(2)

# Update Pico with the current time from Internet (NTP) 
ntptime.settime()
Log(utime.localtime(), "DEBUG") # Some extra debug logging if DEBUG enabled.
    
# Use GP28 for controlling power
powerPin = machine.Pin(28, machine.Pin.OUT)  

#
# Sensors
#

Log("Init dht", "DEBUG")
# Initialize the DHT11 sensor on GPIO 1
dhtSensor = dht.DHT11(machine.Pin(1))

Log("Init soil", "DEBUG")
# Initialize the soil moisture sensor on GPIO 26 (ADC0)
soilMoistureSensor = machine.ADC(machine.Pin(26))

Log("Init photo", "DEBUG")
# Initialize the photoresistor sensor on GPIO 27 (ADC1)
photoResistorSensor = machine.ADC(machine.Pin(27))

time.sleep(2) # give sensors some extra time to initialize
    
# Create MQTT client 
client = MQTTClient(
    clientId,
    mqttHost,
    port=mqttPort,
    keepalive=60,
    ssl=True,
    ssl_params={
        "key": clientKey,
        "cert": clientCert,
        "server_hostname": mqttHost,
        "cert_reqs": ssl.CERT_REQUIRED,
        "cadata": caCert,
    }
)

# Call function if there are messages in subscribed topics in MQTT broker to check
client.set_callback(OnActionMessage)

# Connect to MQTT broker and flash led three times if successful
print(f"Connecting to MQTT broker at {mqttHost}:{mqttPort}")
Log("Connect to mqtt", "DEBUG")
try:
    client.connect()
    print("Connected to MQTT broker")
    FlashLed(3)
except Exception as e:
        errorMessage = FormatException(e)
        Log("Error in client.connect(): {}".format(errorMessage), "ERROR")

# Subscribe to the example topic to control LED
client.subscribe(mqttTopicTask)

Log("Finnished", "DEBUG")

# Publish data and check for messages every 10 seconds
try:
    while True:
        client.check_msg()
        PublishData()
        time.sleep(10)
# Catch critical errors not handled within above code and log them, and restart Pico 60 seconds later.
except Exception as e:
    errorMessage = FormatException(e)
    Log("Unhandled exception: {}".format(errorMessage), "CRITICAL")
    time.sleep(60)   # Wait 60 seconds before restarting
    machine.reset()  # Restart the Pico
# When using Thonny we want to be able to stop and disconnect using CTRL+C
except KeyboardInterrupt:
    print("Disconnecting from MQTT broker...")
    client.disconnect()





