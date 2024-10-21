// Uncomment these lines and specify your Blynk template ID and name if you're using templates
#define BLYNK_TEMPLATE_ID "TMPL2mR8NIXn1"  // Replace with your template ID
#define BLYNK_TEMPLATE_NAME "Fire Detection and Suppression System"  // Replace with your template name

#include <WiFi.h>
#include <BlynkSimpleEsp32.h>
#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <DHT.h>

// Blynk Authentication & Wi-Fi Credentials
char auth[] = "";   // Blynk token
char ssid[] = "";                             // WiFi SSID
char pass[] = "";                        // WiFi Password

// Pin Definitions for ESP32
#define MQ2_PIN 33
#define DHT_PIN 23
#define FLAME_SENSOR_PIN 27
#define BUZZER_PIN 14
#define BUTTON_PIN 13
#define WATER_PUMP_PIN 12
#define CO2_LED_PIN 5
#define HVAC_LED_PIN 0
#define SPEAKER_PIN 25  // Speaker will remain unused

// Thresholds
#define THRESHOLD_MQ2 4000
#define THRESHOLD_TEMP 30
#define THRESHOLD_HUMIDITY 100

// DHT Sensor
DHT dht(DHT_PIN, DHT11);
LiquidCrystal_I2C lcd(0x3F, 16, 2);  // Initialize LCD display with address 0x3F
BlynkTimer timer;                     // Blynk timer to handle periodic tasks
bool flameDetected = false;            // Indicates if a flame is detected
bool warningActive = false;            // Indicates when gas/temp/humidity exceeds threshold
bool manualPumpControl = false;        // Tracks if the pump is manually controlled
bool manualCO2Control = false;
bool manualHVACControl = false;

// SIM800L Serial Communication
#define SIM800_RX_PIN 16  // Connect SIM800 TXD to ESP32 GPIO 16
#define SIM800_TX_PIN 17  // Connect SIM800 RXD to ESP32 GPIO 17

// Create a HardwareSerial object for SIM800L
HardwareSerial sim800(1); // Using UART1 for SIM800L

// Timing variables for the serial monitor
unsigned long lastSerialPrint = 0; // Last time the serial monitor was updated
const unsigned long serialInterval = 5000; // Interval for serial monitor updates (5 seconds)

// Timing variables for buzzer control
unsigned long lastBuzzerTime = 0; // Last time the buzzer state was changed
const unsigned long buzzerInterval = 50; // Buzzer interval (1 second)

void setup() {
    Serial.begin(115200); // Initialize Serial Monitor
    pinMode(MQ2_PIN, INPUT);
    pinMode(FLAME_SENSOR_PIN, INPUT);
    pinMode(BUZZER_PIN, OUTPUT);
    pinMode(WATER_PUMP_PIN, OUTPUT);
    pinMode(CO2_LED_PIN, OUTPUT);
    pinMode(HVAC_LED_PIN, OUTPUT);
    pinMode(SPEAKER_PIN, OUTPUT);  // Unused, but can remain as output
    pinMode(BUTTON_PIN, INPUT_PULLUP);

    lcd.init();  // Initialize LCD with I2C address
    lcd.backlight();
    dht.begin();
    Blynk.begin(auth, ssid, pass);  // Initialize Blynk for ESP32
    sim800.begin(9600, SERIAL_8N1, SIM800_RX_PIN, SIM800_TX_PIN); // Initialize SIM800L serial communication

    // Setup a timer to check sensors every 2 seconds
    timer.setInterval(2000L, sensorCheck);
    timer.setInterval(1000L, buzzerControl);  // Control buzzer every second
}

void loop() {
    Blynk.run();  // Let Blynk handle connection and commands
    timer.run();  // Handle timed functions

    // Print sensor values to Serial Monitor at defined intervals
    unsigned long currentMillis = millis();
    if (currentMillis - lastSerialPrint >= serialInterval) {
        lastSerialPrint = currentMillis; // Update the last print time
        printSensorValues();
    }
}

// Function to debounce flame detection
bool isFlameDetected() {
    int count = 0;
    for (int i = 0; i < 5; i++) {
        if (digitalRead(FLAME_SENSOR_PIN) == LOW) {  // Adjust this logic based on sensor
            count++;
        }
        delay(50);  // Small delay between checks
    }
    return count >= 3;  // True if flame is detected 3 out of 5 times
}

// Function to check sensors and trigger alerts
void sensorCheck() {
    // Take 10 readings from the gas sensor and calculate the average
    int gasTotal = 0;
    int readings = 10;  // Number of samples to take for averaging
    for (int i = 0; i < readings; i++) {
        gasTotal += analogRead(MQ2_PIN);  // Sum the readings
        delay(50);  // Small delay between readings to allow stabilization
    }
    int gasLevel = gasTotal / readings;  // Calculate the average gas level

    float temp = dht.readTemperature();     // Read temperature
    float humidity = dht.readHumidity();    // Read humidity
    flameDetected = isFlameDetected();      // Check flame with debounce

    // Clear the LCD before displaying new readings
    lcd.clear();

    // Display sensor readings on the LCD
    lcd.setCursor(0, 0);
    lcd.print("T:");
    lcd.print(temp);
    lcd.setCursor(8, 0);
    lcd.print("H:");
    lcd.print(humidity);
    lcd.setCursor(0, 1);
    lcd.print("G:");
    lcd.print(gasLevel);

    // Determine if any thresholds have been surpassed
    bool gasWarning = gasLevel > THRESHOLD_MQ2;
    bool tempWarning = temp > THRESHOLD_TEMP;
    bool humidityWarning = humidity > THRESHOLD_HUMIDITY;

    // If any threshold is surpassed
    if (gasWarning || tempWarning || humidityWarning && !manualHVACControl) {
        digitalWrite(HVAC_LED_PIN, HIGH);  // Turn on HVAC system
        Blynk.virtualWrite(V1, HIGH);      // Update HVAC status on Blynk app
        lcd.setCursor(8, 1);
        lcd.print("Warning!");

        warningActive = true;   // Indicate that a warning condition is active
        activateAlert("WARNING");  // Trigger alert for gas/temp/humidity warning
        
        // Trigger notifications for gas/temp/humidity warnings
        if (gasWarning) {
            Blynk.logEvent("gas_warning", "Gas levels exceeded threshold");
        }
        if (tempWarning) {
            Blynk.logEvent("temp_warning", "Temperature exceeded threshold!");
        }
        if (humidityWarning) {
            Blynk.logEvent("humidity_warning", "Humidity exceeded threshold!");
        }
        
    } else if(!manualHVACControl) {
        warningActive = false;  // Reset warning if thresholds are normal
        digitalWrite(HVAC_LED_PIN, LOW);   // Turn off HVAC if no warning
    }

    // If flame is detected and manual control is off
    if (flameDetected && !manualPumpControl && !manualCO2Control) {
        digitalWrite(WATER_PUMP_PIN, HIGH);  // Turn on water pump
        digitalWrite(CO2_LED_PIN, HIGH);     // Turn on CO2 system
        Blynk.virtualWrite(V2, HIGH);        // Update CO2 status on Blynk app
        lcd.setCursor(0, 1);
        lcd.print("FIRE Detected!");

        activateAlert("FIRE");  // Trigger alert for fire detection
        Blynk.logEvent("fire_alert", "Fire detected! Immediate action required!");
        
    } else if (!manualPumpControl && !manualCO2Control) {
        digitalWrite(WATER_PUMP_PIN, LOW);   // Turn off water pump if no flame and no manual control
        digitalWrite(CO2_LED_PIN, LOW);      // Turn off CO2 system
    }
}

// Function to manually control the HVAC using Blynk Button Widget
BLYNK_WRITE(V1) {
    int hvacControl = param.asInt();  // Read button state from Blynk app
    if (hvacControl == 1) {
      manualHVACControl = true;
        digitalWrite(HVAC_LED_PIN, HIGH);  // Turn on HVAC system
    } else {
        manualHVACControl = false;
        digitalWrite(HVAC_LED_PIN, LOW);   // Turn off HVAC system
    }
}

// Function to manually control the LED using Blynk Button Widget
BLYNK_WRITE(V2) {
    int ledControl = param.asInt();  // Read button state from Blynk app
    if (ledControl == 1) {
        manualCO2Control = true;
        digitalWrite(CO2_LED_PIN, HIGH);  // Turn on LED
    } else {
        manualCO2Control = false;
        digitalWrite(CO2_LED_PIN, LOW);   // Turn off LED
    }
}

// Function to manually control the water pump using Blynk Button Widget
BLYNK_WRITE(V3) {
    int pumpControl = param.asInt();  // Read button state from Blynk app
    if (pumpControl == 1) {
        manualPumpControl = true;         // Enable manual pump control
        digitalWrite(WATER_PUMP_PIN, HIGH);  // Turn on water pump manually
    } else {
        manualPumpControl = false;        // Disable manual pump control
        digitalWrite(WATER_PUMP_PIN, LOW);  // Turn off water pump manually
    }
}

// Function to control the buzzer based on hazard levels
void buzzerControl() {
    unsigned long currentMillis = millis(); // Get the current time

    // Continuous beep for flammable hazards
    if (flameDetected) {
        digitalWrite(BUZZER_PIN, HIGH);
    } 
    // Intermittent beep for non-flammable hazards
    else if (warningActive) {
        if (currentMillis - lastBuzzerTime >= buzzerInterval) {
            lastBuzzerTime = currentMillis; // Update the last buzzer time
            digitalWrite(BUZZER_PIN, !digitalRead(BUZZER_PIN)); // Toggle buzzer state
        }
    } 
    // Turn off the buzzer if no hazards
    else {
        digitalWrite(BUZZER_PIN, LOW);
    }
}

// Function to trigger an alert through SIM800L
void activateAlert(String alertType) {
    // Send SMS notification through SIM800L
    sim800.print("AT+CMGF=1\r");  // Set SMS mode to text
    delay(100);
    sim800.print("AT+CMGS=\"+1234567890\"\r");  // Replace with recipient's phone number
    delay(100);
    sim800.print(alertType + " detected! Take action immediately.\r");  // Send the alert message
    delay(100);
    sim800.write(26);  // Send Ctrl+Z to finish SMS
    delay(100);
}

// Function to print sensor values to Serial Monitor
void printSensorValues() {
    // Reading sensors and printing to Serial Monitor
    int gasLevel = analogRead(MQ2_PIN);
    float temp = dht.readTemperature();
    float humidity = dht.readHumidity();
    bool flame = isFlameDetected();

    Serial.println("Sensor Values:");
    Serial.print("Gas Level: ");
    Serial.println(gasLevel);
    Serial.print("Temperature: ");
    Serial.println(temp);
    Serial.print("Humidity: ");
    Serial.println(humidity);
    Serial.print("Flame Detected: ");
    Serial.println(flame ? "Yes" : "No");
}
