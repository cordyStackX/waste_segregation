/*
  Waste segregation controller

  The Python brain sends one text command per line over USB serial (9600 baud):

    PING            -> PONG
    ITEM            -> ITEM:1 (item present) or ITEM:0   (needs the ultrasonic sensor)
    SORT:BIO        -> OK   (biodegradable bin)
    SORT:NONBIO     -> OK   (non-biodegradable bin)
    SORT:RESIDUAL   -> OK   (residual / special waste bin)

  Errors: ERR:BAD_CMD, ERR:NO_ITEM, ERR:TOO_LONG

  Hardware (see README for wiring):
    - Sorter servo: swings the chute to the right bin
    - Gate servo:   opens a trapdoor to drop the item
    - HC-SR04 (optional): detects that an item is waiting
*/

#include <Servo.h>

// ---------- Pins ----------
const uint8_t PIN_SORT_SERVO = 9;
const uint8_t PIN_GATE_SERVO = 10;
const uint8_t PIN_TRIG = 7;
const uint8_t PIN_ECHO = 8;

// ---------- Calibrate these for your build ----------
const int ANGLE_BIO      = 30;
const int ANGLE_NONBIO   = 90;
const int ANGLE_RESIDUAL = 150;
const int GATE_CLOSED    = 0;
const int GATE_OPEN      = 90;

const unsigned long MOVE_MS = 700;   // time for the sorter servo to reach the bin
const unsigned long DROP_MS = 900;   // how long the gate stays open

// Set to true if an HC-SR04 is wired up
const bool USE_SENSOR = false;
const int ITEM_MAX_CM = 15;          // item counts as present if closer than this

// ---------- State ----------
Servo sorter;
Servo gate;
char buf[32];
uint8_t len = 0;

// ---------- Helpers ----------
long readDistanceCm() {
  digitalWrite(PIN_TRIG, LOW);
  delayMicroseconds(2);
  digitalWrite(PIN_TRIG, HIGH);
  delayMicroseconds(10);
  digitalWrite(PIN_TRIG, LOW);
  unsigned long us = pulseIn(PIN_ECHO, HIGH, 30000UL);  // 30 ms timeout
  if (us == 0) return -1;                                // nothing in range
  return us / 58;
}

bool itemPresent() {
  long d = readDistanceCm();
  return d > 0 && d < ITEM_MAX_CM;
}

void sortTo(int angle) {
  sorter.write(angle);
  delay(MOVE_MS);
  gate.write(GATE_OPEN);
  delay(DROP_MS);
  gate.write(GATE_CLOSED);
  delay(MOVE_MS / 2);
}

void handleCommand(const char *cmd) {
  if (strcmp(cmd, "PING") == 0) {
    Serial.println("PONG");
    return;
  }

  if (strcmp(cmd, "ITEM") == 0) {
    if (USE_SENSOR) {
      Serial.println(itemPresent() ? "ITEM:1" : "ITEM:0");
    } else {
      Serial.println("ITEM:1");  // no sensor, assume an item is there
    }
    return;
  }

  int angle = -1;
  if (strcmp(cmd, "SORT:BIO") == 0)           angle = ANGLE_BIO;
  else if (strcmp(cmd, "SORT:NONBIO") == 0)   angle = ANGLE_NONBIO;
  else if (strcmp(cmd, "SORT:RESIDUAL") == 0) angle = ANGLE_RESIDUAL;

  if (angle < 0) {
    Serial.println("ERR:BAD_CMD");
    return;
  }

  if (USE_SENSOR && !itemPresent()) {
    Serial.println("ERR:NO_ITEM");
    return;
  }

  sortTo(angle);
  Serial.println("OK");
}

// ---------- Arduino entry points ----------
void setup() {
  Serial.begin(9600);
  pinMode(PIN_TRIG, OUTPUT);
  pinMode(PIN_ECHO, INPUT);

  sorter.attach(PIN_SORT_SERVO);
  gate.attach(PIN_GATE_SERVO);
  gate.write(GATE_CLOSED);
  sorter.write(ANGLE_NONBIO);  // start in the middle
  delay(500);

  Serial.println("READY");
}

void loop() {
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
