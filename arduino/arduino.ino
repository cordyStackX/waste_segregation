/*
  BinThere biodegradable-bin lid controller (SG90 servo)

  Serial, 9600 baud, one command per line:

    PING       -> PONG
    TEST       -> open the lid, then auto-close; OK:OPEN:BIO
    OPEN:BIO   -> open the lid, then auto-close; OK:OPEN:BIO
    CLOSE:BIO  -> close the lid; OK:CLOSE:BIO

  Wiring:
    SG90 signal (orange/yellow) -> D9
    SG90 power (red)            -> regulated 5 V supply
    SG90 ground (brown/black)   -> supply GND and Arduino GND

  Do not power the servo from the Arduino Uno 5 V pin. Adjust the angles and
  open duration below to match the lid linkage.
*/

#include <Servo.h>

const uint8_t PIN_BIO_SERVO = 9;
const uint8_t BIO_CLOSED_ANGLE = 0;
const uint8_t BIO_OPEN_ANGLE = 90;
const unsigned long BIO_OPEN_MS = 1800;

char buf[32];
uint8_t len = 0;
Servo bioServo;
bool bioServoOpen = false;
unsigned long bioServoCloseAt = 0;

void closeBioLid() {
  bioServo.write(BIO_CLOSED_ANGLE);
  bioServoOpen = false;
}

void openBioLid() {
  bioServo.write(BIO_OPEN_ANGLE);
  bioServoOpen = true;
  bioServoCloseAt = millis() + BIO_OPEN_MS;
}

void handleCommand(const char *cmd) {
  if (strcmp(cmd, "PING") == 0) {
    Serial.println("PONG");
  } else if (strcmp(cmd, "TEST") == 0 || strcmp(cmd, "OPEN:BIO") == 0) {
    openBioLid();
    Serial.println("OK:OPEN:BIO");
  } else if (strcmp(cmd, "CLOSE:BIO") == 0 || strcmp(cmd, "OFF") == 0) {
    closeBioLid();
    Serial.println("OK:CLOSE:BIO");
  } else {
    Serial.println("ERR:BAD_CMD");
  }
}

void setup() {
  Serial.begin(9600);
  bioServo.attach(PIN_BIO_SERVO);
  closeBioLid();
  Serial.println("READY");
}

void loop() {
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
