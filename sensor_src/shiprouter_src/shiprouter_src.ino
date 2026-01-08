/*
 * ============================================================================
 * ShipRouter - Arduino Nano R4 Firmware (v2.0)
 * ============================================================================
 * 
 * Combines GPS NMEA data and fuel sensor status into JSON packets
 * for transmission to Raspberry Pi via USB Serial.
 * 
 * Hardware:
 *   - Arduino Nano R4 (Renesas MCU with isolated USB/UART)
 *   - SkyTraq GNSS Module (Serial1, Pins 0/1, 115200 baud)
 *   - DFRobot Capacitive Liquid Level Sensor (Pin 8 input, Pin 9 mode)
 *   - Onboard RGB LED (LEDR, LEDG, LEDB) for status indication
 * 
 * Output Format (USB Serial @ 115200):
 *   {"fuel":1,"nmea":"$GPGGA,123519,1054.248,N,07700.750,E,1,16,1.1,383.2,M,..."}
 * 
 * RGB LED Indicators (blinks on data transmit):
 *   GREEN  : GPS Fix + Fuel OK
 *   YELLOW : No GPS Fix + Fuel OK
 *   RED    : No GPS Fix + Fuel LOW
 *   PURPLE : GPS Fix + Fuel LOW
 * 
 * Fuel Sensor Logic (DFRobot, mode=0):
 *   Sensor reads 1 (HIGH) → Liquid detected (LED ON) → Fuel OK (output fuel:1)
 *   Sensor reads 0 (LOW)  → No liquid (LED OFF)      → Fuel LOW (output fuel:0)
 * 
 * Author: ShipRouter Project
 * License: MIT
 * ============================================================================
 */

// =============================================================================
// Configuration
// =============================================================================

// Serial baud rates
#define USB_BAUD        115200    // USB Serial to Raspberry Pi
#define GPS_BAUD        115200    // GPS Module (SkyTraq default)

// Fuel Sensor Pins (DFRobot Capacitive Liquid Level Sensor)
#define FUEL_SENSOR_PIN 8         // D8 - Sensor signal input
#define FUEL_MODE_PIN   9         // D9 - Sensor mode control

// Fuel sensor mode (0 = liquid detected outputs HIGH, no liquid outputs LOW)
#define FUEL_MODE_VALUE LOW

// RGB LED Pins for Nano R4
// Nano R4 has onboard RGB LED using LEDR, LEDG, LEDB macros
// LEDs are active LOW (LOW = ON, HIGH = OFF)
#define LED_RGB_R   LEDR
#define LED_RGB_G   LEDG
#define LED_RGB_B   LEDB
#define LED_ON      LOW     // Active LOW - LOW turns ON
#define LED_OFF     HIGH    // HIGH turns OFF

// NMEA buffer size (max NMEA sentence ~82 chars, use 128 for safety)
#define NMEA_BUFFER_SIZE 128

// Output rate control (milliseconds between JSON packets)
#define OUTPUT_INTERVAL_MS 200    // 5 Hz output rate

// LED blink duration (milliseconds)
#define LED_BLINK_DURATION_MS 50

// GPS fix detection (look for 'A' status in RMC or fix quality > 0 in GGA)
#define GPS_FIX_TIMEOUT_MS 3000   // Consider no fix if no valid sentence for 3s

// =============================================================================
// Global Variables
// =============================================================================

// NMEA sentence buffer
char nmeaBuffer[NMEA_BUFFER_SIZE];
uint8_t nmeaIndex = 0;
bool nmeaReady = false;

// Timing
unsigned long lastOutputTime = 0;
unsigned long lastGpsFixTime = 0;
unsigned long ledOffTime = 0;

// Status tracking
bool hasGpsFix = false;
int fuelStatus = 1;  // 1 = OK, 0 = LOW

// =============================================================================
// Setup
// =============================================================================

void setup() {
  // Initialize USB Serial (to Raspberry Pi)
  Serial.begin(USB_BAUD);
  while (!Serial) {
    delay(10); // Wait for USB Serial to connect
  }
  
  // Initialize GPS Serial (Serial1 on Pins 0/1)
  Serial1.begin(GPS_BAUD);
  
  // Initialize fuel sensor pins
  pinMode(FUEL_MODE_PIN, OUTPUT);
  digitalWrite(FUEL_MODE_PIN, FUEL_MODE_VALUE);  // Set mode
  pinMode(FUEL_SENSOR_PIN, INPUT);
  
  // Initialize RGB LED
  initLED();
  
  // Startup message (will be ignored by JSON parser on Pi)
  Serial.println();
  Serial.println(F("# ShipRouter Firmware v2.0 (Nano R4)"));
  Serial.println(F("# GPS: Serial1 @ 115200 (SkyTraq GN/GP)"));
  Serial.println(F("# Fuel: D8 input, D9 mode"));
  Serial.println(F("# LED: LEDR/LEDG/LEDB (active LOW)"));
  Serial.println(F("# Output: JSON @ 5Hz"));
  Serial.println(F("# -------------------------"));
  
  // Clear NMEA buffer
  clearNmeaBuffer();
  
  // Initial LED test - flash all colors
  testLED();
}

// =============================================================================
// Main Loop
// =============================================================================

void loop() {
  unsigned long currentTime = millis();
  
  // Read fuel sensor status
  // DFRobot sensor (mode=0): HIGH = liquid present (LED ON), LOW = no liquid (LED OFF)
  int rawSensor = digitalRead(FUEL_SENSOR_PIN);
  fuelStatus = rawSensor;  // HIGH(1) = OK, LOW(0) = LOW fuel
  
  // Process incoming GPS data (read all available)
  while (Serial1.available() > 0) {
    char c = Serial1.read();
    processNmeaChar(c);
    
    // If we got a complete sentence, check for GPS fix
    if (nmeaReady) {
      checkGpsFix();
    }
  }
  
  // Check GPS fix timeout
  if (currentTime - lastGpsFixTime > GPS_FIX_TIMEOUT_MS) {
    hasGpsFix = false;
  }
  
  // Output JSON if we have a complete NMEA sentence and interval has passed
  if (nmeaReady && (currentTime - lastOutputTime >= OUTPUT_INTERVAL_MS)) {
    outputJson();
    blinkStatusLED();
    lastOutputTime = currentTime;
    clearNmeaBuffer();
  } else if (nmeaReady) {
    // Clear buffer if not outputting (rate limited)
    clearNmeaBuffer();
  }
  
  // Turn off LED after blink duration
  if (ledOffTime > 0 && currentTime >= ledOffTime) {
    setLEDOff();
    ledOffTime = 0;
  }
}

// =============================================================================
// NMEA Processing
// =============================================================================

/**
 * Process a single character from GPS module
 * Buffers characters until a complete NMEA sentence is received
 */
void processNmeaChar(char c) {
  // Start of new NMEA sentence
  if (c == '$') {
    nmeaIndex = 0;
    nmeaReady = false;
  }
  
  // Add character to buffer (if within bounds)
  if (nmeaIndex < NMEA_BUFFER_SIZE - 1) {
    // Don't store CR/LF in buffer
    if (c != '\r' && c != '\n') {
      nmeaBuffer[nmeaIndex++] = c;
      nmeaBuffer[nmeaIndex] = '\0';  // Null-terminate
    }
  }
  
  // End of NMEA sentence (CR or LF)
  if (c == '\n') {
    // Only mark as ready if we have a valid sentence (starts with $)
    if (nmeaIndex > 6 && nmeaBuffer[0] == '$') {
      nmeaReady = true;
    } else {
      clearNmeaBuffer();
    }
  }
}

/**
 * Check if current NMEA sentence indicates GPS fix
 * Handles both GP (GPS only) and GN (multi-constellation) prefixes
 */
void checkGpsFix() {
  // Check for GGA sentence (position fix)
  // $GPGGA or $GNGGA - field 6 is fix quality (0 = no fix, 1+ = fix)
  if (strstr(nmeaBuffer, "GGA") != NULL) {
    // Find fix quality field (6th field after $xxGGA)
    int commaCount = 0;
    for (int i = 0; i < nmeaIndex && commaCount < 6; i++) {
      if (nmeaBuffer[i] == ',') {
        commaCount++;
        if (commaCount == 6) {
          // Next char is fix quality
          char fixQuality = nmeaBuffer[i + 1];
          if (fixQuality >= '1' && fixQuality <= '9') {
            hasGpsFix = true;
            lastGpsFixTime = millis();
          }
        }
      }
    }
  }
  
  // Check for RMC sentence (recommended minimum)
  // $GPRMC or $GNRMC - field 2 is status (A = active/valid, V = void)
  else if (strstr(nmeaBuffer, "RMC") != NULL) {
    // Find status field (2nd field)
    int commaCount = 0;
    for (int i = 0; i < nmeaIndex && commaCount < 2; i++) {
      if (nmeaBuffer[i] == ',') {
        commaCount++;
        if (commaCount == 2) {
          // Next char is status
          char status = nmeaBuffer[i + 1];
          if (status == 'A') {
            hasGpsFix = true;
            lastGpsFixTime = millis();
          }
        }
      }
    }
  }
}

/**
 * Clear NMEA buffer
 */
void clearNmeaBuffer() {
  nmeaIndex = 0;
  nmeaBuffer[0] = '\0';
  nmeaReady = false;
}

// =============================================================================
// JSON Output
// =============================================================================

/**
 * Output JSON packet to USB Serial
 * Format: {"fuel":1,"nmea":"$GPGGA,..."}
 */
void outputJson() {
  // Only output if we have valid NMEA data
  if (nmeaBuffer[0] != '$') {
    return;
  }
  
  // Build JSON manually (avoids ArduinoJson dependency)
  Serial.print(F("{\"fuel\":"));
  Serial.print(fuelStatus);
  Serial.print(F(",\"nmea\":\""));
  
  // Print NMEA sentence (already cleaned of CR/LF)
  printEscapedString(nmeaBuffer);
  
  Serial.println(F("\"}"));
}

/**
 * Print string with JSON escaping
 */
void printEscapedString(const char* str) {
  while (*str) {
    char c = *str++;
    switch (c) {
      case '"':  Serial.print(F("\\\"")); break;
      case '\\': Serial.print(F("\\\\")); break;
      default:   Serial.print(c); break;
    }
  }
}

// =============================================================================
// RGB LED Control
// =============================================================================

/**
 * Initialize LED pins
 */
void initLED() {
  pinMode(LED_RGB_R, OUTPUT);
  pinMode(LED_RGB_G, OUTPUT);
  pinMode(LED_RGB_B, OUTPUT);
  setLEDOff();
}

/**
 * Test LED - flash through colors on startup
 */
void testLED() {
  // Red
  setLEDColor(true, false, false);
  delay(200);
  // Green
  setLEDColor(false, true, false);
  delay(200);
  // Blue
  setLEDColor(false, false, true);
  delay(200);
  // Yellow
  setLEDColor(true, true, false);
  delay(200);
  // Purple
  setLEDColor(true, false, true);
  delay(200);
  // Off
  setLEDOff();
}

/**
 * Set RGB LED color
 */
void setLEDColor(bool red, bool green, bool blue) {
  digitalWrite(LED_RGB_R, red ? LED_ON : LED_OFF);
  digitalWrite(LED_RGB_G, green ? LED_ON : LED_OFF);
  digitalWrite(LED_RGB_B, blue ? LED_ON : LED_OFF);
}

/**
 * Turn off all LEDs
 */
void setLEDOff() {
  digitalWrite(LED_RGB_R, LED_OFF);
  digitalWrite(LED_RGB_G, LED_OFF);
  digitalWrite(LED_RGB_B, LED_OFF);
}

/**
 * Blink status LED based on current GPS and fuel status
 * 
 * GREEN  : GPS Fix + Fuel OK
 * YELLOW : No GPS Fix + Fuel OK (Red + Green)
 * RED    : No GPS Fix + Fuel LOW
 * PURPLE : GPS Fix + Fuel LOW (Red + Blue)
 */
void blinkStatusLED() {
  if (hasGpsFix && fuelStatus == 1) {
    // GREEN: All good
    setLEDColor(false, true, false);
  } 
  else if (!hasGpsFix && fuelStatus == 1) {
    // YELLOW: No GPS but fuel OK
    setLEDColor(true, true, false);
  }
  else if (!hasGpsFix && fuelStatus == 0) {
    // RED: No GPS and fuel LOW - worst case
    setLEDColor(true, false, false);
  }
  else if (hasGpsFix && fuelStatus == 0) {
    // PURPLE/MAGENTA: GPS OK but fuel LOW
    setLEDColor(true, false, true);
  }
  
  // Schedule LED off
  ledOffTime = millis() + LED_BLINK_DURATION_MS;
}

// =============================================================================
// Debug/Utility Functions (optional, can be removed for production)
// =============================================================================

/**
 * Print debug status (call from loop if needed)
 */
void printDebugStatus() {
  Serial.print(F("# DEBUG - GPS Fix: "));
  Serial.print(hasGpsFix ? "YES" : "NO");
  Serial.print(F(" | Fuel: "));
  Serial.print(fuelStatus ? "OK" : "LOW");
  Serial.print(F(" | Raw Sensor: "));
  Serial.println(digitalRead(FUEL_SENSOR_PIN));
}
