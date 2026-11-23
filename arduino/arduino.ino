/*
  Waste segregation controller (LED indicators + biodegradable servo)

  Each bin has an LED indicator. A stable, high-confidence biodegradable
  prediction opens the servo-operated bin lid.

  Serial, 9600 baud, one command per line:

    PING            -> PONG
    TEST            -> blinks every LED once, then OK
    OFF             -> all LEDs off, OK
    SORT:BIO        -> green LED on,  OK   (biodegradable)
    SORT:NONBIO     -> blue LED on,   OK   (non-biodegradable)
    SORT:RESIDUAL   -> red LED on,    OK   (residual / special waste)
    OPEN:BIO        -> move biodegradable lid open, OK:OPEN:BIO
    CLOSE:BIO       -> close biodegradable lid, OK:CLOSE:BIO

  Errors: ERR:BAD_CMD, ERR:TOO_LONG

  Wiring (one per LED):
    Arduino pin -> 220 ohm resistor -> LED long leg (+), short leg (-) -> GND

  Servo signal connects to D9. Power the servo from a separate regulated 5 V
  supply and connect that supply's GND to Arduino GND.
*/

#include <Servo.h>

// ---------- Pins ----------
const uint8_t PIN_BIO      = 2;   // green
const uint8_t PIN_NONBIO   = 3;   // blue
const uint8_t PIN_RESIDUAL = 4;   // red
const uint8_t PIN_BIO_SERVO = 9;  // biodegradable bin lid servo signal

const uint8_t BIO_CLOSED_ANGLE = 0;  // adjust to match your linkage
const uint8_t BIO_OPEN_ANGLE = 90;   // adjust to match your linkage
const unsigned long BIO_OPEN_MS = 1800;

const uint8_t LEDS[] = {PIN_BIO, PIN_NONBIO, PIN_RESIDUAL};
const uint8_t NUM_LEDS = sizeof(LEDS) / sizeof(LEDS[0]);

const unsigned long LIGHT_MS = 2000;  // how long a LED stays on after SORT

// ---------- State ----------
char buf[32];
uint8_t len = 0;
int activePin = -1;
unsigned long offAt = 0;
Servo bioServo;
bool bioServoOpen = false;
unsigned long bioServoCloseAt = 0;

// ---------- Helpers ----------
void allOff() {
  for (uint8_t i = 0; i < NUM_LEDS; i++) {
    digitalWrite(LEDS[i], LOW);
  }
  activePin = -1;
}

void closeBioLid() {
  bioServo.write(BIO_CLOSED_ANGLE);
  bioServoOpen = false;
}

void openBioLid() {
  bioServo.write(BIO_OPEN_ANGLE);
  bioServoOpen = true;
  bioServoCloseAt = millis() + BIO_OPEN_MS;
}

void lightOnly(uint8_t pin) {
  allOff();
  digitalWrite(pin, HIGH);
  activePin = pin;
  offAt = millis() + LIGHT_MS;
}

void selfTest() {
  allOff();
  for (uint8_t i = 0; i < NUM_LEDS; i++) {
    digitalWrite(LEDS[i], HIGH);
    delay(250);
    digitalWrite(LEDS[i], LOW);
  }
}

void handleCommand(const char *cmd) {
  if (strcmp(cmd, "PING") == 0) {
    Serial.println("PONG");
  } else if (strcmp(cmd, "TEST") == 0) {
    selfTest();
    Serial.println("OK");
  } else if (strcmp(cmd, "OFF") == 0) {
    allOff();
    Serial.println("OK");
  } else if (strcmp(cmd, "SORT:BIO") == 0) {
    lightOnly(PIN_BIO);
    Serial.println("OK");
  } else if (strcmp(cmd, "SORT:NONBIO") == 0) {
    lightOnly(PIN_NONBIO);
    Serial.println("OK");
  } else if (strcmp(cmd, "SORT:RESIDUAL") == 0) {
    lightOnly(PIN_RESIDUAL);
    Serial.println("OK");
  } else if (strcmp(cmd, "OPEN:BIO") == 0) {
    openBioLid();
    Serial.println("OK:OPEN:BIO");
  } else if (strcmp(cmd, "CLOSE:BIO") == 0) {
    closeBioLid();
    Serial.println("OK:CLOSE:BIO");
  } else {
    Serial.println("ERR:BAD_CMD");
  }
}

// ---------- Arduino entry points ----------
void setup() {
  Serial.begin(9600);
  for (uint8_t i = 0; i < NUM_LEDS; i++) {
    pinMode(LEDS[i], OUTPUT);
  }
  bioServo.attach(PIN_BIO_SERVO);
  closeBioLid();
  allOff();
  selfTest();          // quick power-on check
  Serial.println("READY");
}

void loop() {
  // turn the active LED off after LIGHT_MS (no blocking delay)
  if (activePin >= 0 && (long)(millis() - offAt) >= 0) {
    allOff();
  }
  if (bioServoOpen && (long)(millis() - bioServoCloseAt) >= 0) {
    closeBioLid();
  }

  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      if (len > 0) {
        buf[len] = '\0';
        handleCommand(buf);
        len = 0;
      }
    } else if (len < sizeof(buf) - 1) {
      buf[len++] = c;
    } else {
      len = 0;
      Serial.println("ERR:TOO_LONG");
    }
  }
}
