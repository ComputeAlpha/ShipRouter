/*
 * ShipRouter - Hardware Configuration
 * 
 * Modify these values based on your hardware setup.
 * Include this file in your main sketch if you prefer separate config.
 */

#ifndef SHIPROUTER_CONFIG_H
#define SHIPROUTER_CONFIG_H

// =============================================================================
// Pin Configuration
// =============================================================================

// Fuel Sensor Pin (DFRobot Capacitive Sensor)
// Change this based on your wiring
#define FUEL_SENSOR_PIN     2

// Status LED (use built-in LED or external)
#define LED_STATUS_PIN      LED_BUILTIN

// GPS Serial Selection
// For Arduino Nano R4:
//   - Serial1: Hardware UART (recommended)
//   - Use SoftwareSerial if Serial1 is unavailable
#define USE_HARDWARE_SERIAL 1

#if !USE_HARDWARE_SERIAL
    #include <SoftwareSerial.h>
    #define GPS_RX_PIN      4
    #define GPS_TX_PIN      5
#endif

// =============================================================================
// Serial Baud Rates
// =============================================================================

// USB Serial to Raspberry Pi
#define USB_BAUD_RATE       115200

// GPS Module Baud Rate
// Common values: 4800, 9600, 38400, 115200
// Check your GPS module datasheet
#define GPS_BAUD_RATE       115200

// =============================================================================
// Timing Configuration
// =============================================================================

// Data transmission interval (milliseconds)
// 200ms = 5Hz update rate
#define SEND_INTERVAL_MS    200

// GPS read timeout (milliseconds)
#define GPS_TIMEOUT_MS      100

// =============================================================================
// Sensor Logic Configuration
// =============================================================================

// Fuel sensor logic level
// Set to 1 if HIGH = fuel present
// Set to 0 if LOW = fuel present (inverted)
#define FUEL_SENSOR_ACTIVE_HIGH  1

// =============================================================================
// Debug Options
// =============================================================================

// Enable debug output (disable in production)
#define DEBUG_ENABLED       0

#if DEBUG_ENABLED
    #define DEBUG_PRINT(x)    Serial.print(x)
    #define DEBUG_PRINTLN(x)  Serial.println(x)
#else
    #define DEBUG_PRINT(x)
    #define DEBUG_PRINTLN(x)
#endif

#endif // SHIPROUTER_CONFIG_H
