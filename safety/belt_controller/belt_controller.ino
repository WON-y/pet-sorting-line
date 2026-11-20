// 벨트·안전 제어 (아두이노 우노)
// 규격: docs/spec/safety_rules.md, docs/spec/protocol.md 3·4절, safety/README.md 핀 표
// 이 파일을 고치면 정지 시험 N1~N5를 다시 하고 docs/tests/kpi_log.md에 기록한다.
//
// 초안 상태: 핀 번호와 센서 극성(LOW/HIGH)은 실제 배선 후 확인해서 고친다.

// ---------- 설정 (settings.yaml과 같은 값) ----------
const unsigned long HEARTBEAT_TIMEOUT_MS = 1000;  // safety.heartbeat_timeout_ms
const unsigned long ARM_VALID_MS = 5000;          // safety.arm_valid_ms
const unsigned int STEP_US_NORMAL = 800;          // 보통 속도 펄스 간격 (실기로 조정)
const unsigned int STEP_US_SLOW = 1600;           // 저속
const unsigned long STATE_PERIOD_MS = 1000;

// ---------- 핀 ----------
const int PIN_DANGER = 2;      // 게이트웨이 P0, HIGH 또는 끊김 = 정지
const int PIN_HEARTBEAT = 3;   // 게이트웨이 P1, 바뀌어야 정상
const int PIN_STATE_OUT = 4;   // 게이트웨이 P2 (분압), HIGH = 정지 상태
const int PIN_IR_ARRIVE = 5;   // IR 도착 센서, LOW = 병 감지 (모듈 확인)
const int PIN_IR_CURTAIN = 6;  // IR 커튼, LOW = 손 감지
const int PIN_RESET_BTN = 7;   // 리셋 버튼, LOW = 눌림
const int PIN_ENA = 8;         // TB6600 ENA
const int PIN_PUL = 9;         // TB6600 PUL
const int PIN_DIR = 10;        // TB6600 DIR
const int PIN_RELAY = 11;      // 전원 릴레이, HIGH = 붙임 (모듈 확인)

// TB6600 ENA 극성은 배선 방식에 따라 다르다. 실기로 확인 후 바꾼다.
const int ENA_ON = LOW;
const int ENA_OFF = HIGH;

// ---------- 상태 ----------
enum RunState { STOPPED, RUNNING, PAUSED };  // PAUSED = 검사 자리에서 판정 대기
RunState runState = STOPPED;                  // 켜자마자 STOP (safety_rules.md 4절)
bool slow = false;
bool hold = false;                            // HOLD(점검 잠금 등) 받음
unsigned long lastHbChangeMs = 0;
int lastHbLevel = -1;
unsigned long armedAtMs = 0;
bool armed = false;
unsigned long lastStepUs = 0;
bool pulseLevel = false;
unsigned long lastStateMs = 0;
bool arriveLatched = false;
String rx = "";

void setOutputs(bool motorOn) {
  digitalWrite(PIN_ENA, motorOn ? ENA_ON : ENA_OFF);
  digitalWrite(PIN_RELAY, motorOn ? HIGH : LOW);
  digitalWrite(PIN_STATE_OUT, runState == STOPPED ? HIGH : LOW);
}

void stopBelt(const char* cause) {
  if (runState != STOPPED) {
    Serial.print("EVT,STOP,");
    Serial.println(cause);
  }
  runState = STOPPED;
  armed = false;
  setOutputs(false);
}

bool dangerActive() {
  unsigned long now = millis();
  if (digitalRead(PIN_IR_CURTAIN) == LOW) return true;
  if (digitalRead(PIN_DANGER) == HIGH) return true;
  if (now - lastHbChangeMs > HEARTBEAT_TIMEOUT_MS) return true;
  return false;
}

const char* dangerCause() {
  if (digitalRead(PIN_IR_CURTAIN) == LOW) return "IR";
  if (digitalRead(PIN_DANGER) == HIGH) return "DANGER";
  return "HB";
}

void handleCommand(const String& cmd) {
  if (cmd == "SPD,N") slow = false;
  else if (cmd == "SPD,S") slow = true;
  else if (cmd == "GO") {
    if (runState == PAUSED) runState = RUNNING;  // 병이 센서를 지나갈 때까지 arriveLatched 유지
  } else if (cmd == "HOLD") {
    hold = true;
    stopBelt("HOLD");
  } else if (cmd == "ARM") {
    armed = true;
    armedAtMs = millis();
    hold = false;
  } else if (cmd == "PING") Serial.println("PONG");
  // 모르는 명령은 무시
}

void readSerial() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n') {
      rx.trim();
      if (rx.length() > 0) handleCommand(rx);
      rx = "";
    } else if (rx.length() < 32) {
      rx += c;
    }
  }
}

void setup() {
  pinMode(PIN_DANGER, INPUT_PULLUP);
  pinMode(PIN_HEARTBEAT, INPUT_PULLUP);
  pinMode(PIN_IR_ARRIVE, INPUT_PULLUP);
  pinMode(PIN_IR_CURTAIN, INPUT_PULLUP);
  pinMode(PIN_RESET_BTN, INPUT_PULLUP);
  pinMode(PIN_STATE_OUT, OUTPUT);
  pinMode(PIN_ENA, OUTPUT);
  pinMode(PIN_PUL, OUTPUT);
  pinMode(PIN_DIR, OUTPUT);
  pinMode(PIN_RELAY, OUTPUT);
  digitalWrite(PIN_DIR, LOW);
  Serial.begin(115200);
  lastHbChangeMs = millis();
  setOutputs(false);
}

void loop() {
  unsigned long nowMs = millis();
  readSerial();

  // 하트비트: 핀 레벨이 바뀐 시각 기록
  int hb = digitalRead(PIN_HEARTBEAT);
  if (hb != lastHbLevel) { lastHbLevel = hb; lastHbChangeMs = nowMs; }

  // 1) 안전 검사가 가장 먼저
  if (dangerActive()) {
    stopBelt(dangerCause());
  }

  // 2) 재가동: ARM 후 유효 시간 안에 리셋 버튼, 위험 없음, HOLD 아님
  if (armed && nowMs - armedAtMs > ARM_VALID_MS) armed = false;
  if (runState == STOPPED && armed && !hold && !dangerActive() && digitalRead(PIN_RESET_BTN) == LOW) {
    runState = RUNNING;
    armed = false;
    arriveLatched = false;
    setOutputs(true);
    Serial.println("EVT,RUN");
  }

  // 3) 도착 센서: 병이 오면 검사 자리에서 일시 멈춤. 병이 센서를 벗어나야 다음 병을 받음
  if (arriveLatched && runState == RUNNING && digitalRead(PIN_IR_ARRIVE) == HIGH) arriveLatched = false;
  if (runState == RUNNING && !arriveLatched && digitalRead(PIN_IR_ARRIVE) == LOW) {
    arriveLatched = true;
    runState = PAUSED;
    Serial.println("EVT,ARRIVE");
  }

  // 4) 스텝 펄스 (비차단)
  if (runState == RUNNING) {
    setOutputs(true);
    unsigned long nowUs = micros();
    unsigned int period = slow ? STEP_US_SLOW : STEP_US_NORMAL;
    if (nowUs - lastStepUs >= period / 2) {
      lastStepUs = nowUs;
      pulseLevel = !pulseLevel;
      digitalWrite(PIN_PUL, pulseLevel ? HIGH : LOW);
    }
  } else if (runState == PAUSED) {
    digitalWrite(PIN_ENA, ENA_ON);   // 판정 대기: 전원은 유지, 펄스만 멈춤
    digitalWrite(PIN_STATE_OUT, LOW);
  }

  // 5) 주기 상태
  if (nowMs - lastStateMs >= STATE_PERIOD_MS) {
    lastStateMs = nowMs;
    Serial.print("STATE,");
    Serial.print(runState == RUNNING ? "RUN" : runState == PAUSED ? "PAUSE" : "STOP");
    Serial.print(",");
    Serial.println(slow ? "S" : "N");
  }
}
