/*
  BinThere three-bin lid controller (three SG90 servo motors)

  Serial, 9600 baud, one command per line:

    PING                 -> PONG
    OPEN:BIO             -> open biodegradable lid; OK:OPEN:BIO
    OPEN:NONBIO          -> open non-biodegradable lid; OK:OPEN:NONBIO
    OPEN:RESIDUAL        -> open residual/special-waste lid; OK:OPEN:RESIDUAL
    CLOSE:BIO/NONBIO/RESIDUAL -> close that lid; OK:CLOSE:<BIN>
    CLOSE:ALL or OFF     -> close all lids; OK:CLOSE:ALL

  Wiring:
    BIO SG90 signal (orange/yellow)      -> D9
    NONBIO SG90 signal (orange/yellow)   -> D10
    RESIDUAL SG90 signal (orange/yellow)-> D11
    Servo red wires                      -> regulated external 5 V supply
    Servo brown/black wires              -> supply GND and Arduino GND

  Do not power three servos from the Arduino Uno 5 V pin. Use a regulated
  supply rated for the combined stall current. Adjust angle/duration values
  below to match the lid linkages.
*/

#include <Servo.h>
#include <string.h>

const uint8_t SERVO_PINS[] = {9, 10, 11};
const char *BIN_CODES[] = {"BIO", "NONBIO", "RESIDUAL"};
const uint8_t BIN_COUNT = sizeof(SERVO_PINS) / sizeof(SERVO_PINS[0]);

const uint8_t SERVO_CLOSED_ANGLE = 0;
const uint8_t SERVO_OPEN_ANGLE = 90;
const unsigned long SERVO_OPEN_MS = 1800;

char buf[40];
uint8_t len = 0;
Servo lids[BIN_COUNT];
bool lidOpen[BIN_COUNT] = {false, false, false};
unsigned long closeAt[BIN_COUNT] = {0, 0, 0};

int binIndex(const char *code) {
  for (uint8_t i = 0; i < BIN_COUNT; i++) {
    if (strcmp(code, BIN_CODES[i]) == 0) return i;
  }
  return -1;
}

void closeLid(uint8_t index) {
  lids[index].write(SERVO_CLOSED_ANGLE);
  lidOpen[index] = false;
}

void openLid(uint8_t index) {
  lids[index].write(SERVO_OPEN_ANGLE);
  lidOpen[index] = true;
  closeAt[index] = millis() + SERVO_OPEN_MS;
}

void closeAllLids() {
  for (uint8_t i = 0; i < BIN_COUNT; i++) closeLid(i);
  Serial.println("OK:CLOSE:ALL");
}

void handleCommand(const char *cmd) {
  if (strcmp(cmd, "PING") == 0) {
    Serial.println("PONG");
  } else if (strcmp(cmd, "OFF") == 0 || strcmp(cmd, "CLOSE:ALL") == 0) {
    closeAllLids();
  } else if (strncmp(cmd, "OPEN:", 5) == 0) {
    int index = binIndex(cmd + 5);
    if (index < 0) {
      Serial.println("ERR:BAD_BIN");
      return;
    }
    openLid((uint8_t)index);
    Serial.print("OK:OPEN:");
    Serial.println(BIN_CODES[index]);
  } else if (strncmp(cmd, "CLOSE:", 6) == 0) {
    int index = binIndex(cmd + 6);
    if (index < 0) {
      Serial.println("ERR:BAD_BIN");
      return;
    }
    closeLid((uint8_t)index);
    Serial.print("OK:CLOSE:");
    Serial.println(BIN_CODES[index]);
  } else {
    Serial.println("ERR:BAD_CMD");
  }
}

void setup() {
  Serial.begin(9600);
  for (uint8_t i = 0; i < BIN_COUNT; i++) {
    lids[i].attach(SERVO_PINS[i]);
    closeLid(i);
  }
  Serial.println("READY");
}

void loop() {
  for (uint8_t i = 0; i < BIN_COUNT; i++) {
    if (lidOpen[i] && (long)(millis() - closeAt[i]) >= 0) closeLid(i);
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
