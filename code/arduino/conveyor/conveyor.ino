/*
 * 컨베이어 벨트 제어 (아두이노 우노 + TB6600 스텝모터 드라이버)
 *
 * - 게이트웨이 micro:bit가 보내는 모드(2비트)대로 벨트 속도를 바꾼다.
 *     자동 = 보통 속도, 저속 = 느리게, 일시 정지 = 멈춤, 점검 잠금 = 멈춤
 * - 안전: 아래 경우에는 멈추고 "잠김" 상태가 된다. 리셋 버튼을 눌러야만 다시 돈다.
 *     1) 전원을 켰을 때   2) micro:bit 살아 있음 신호가 끊겼을 때
 *     3) 비상정지 버튼이 눌렸을 때 (감지 배선을 했을 때만)
 *   비상정지 버튼은 이 프로그램과 상관없이 드라이버 전원을 직접 끊도록 배선한다.
 *
 * 배선
 *   TB6600 PUL+ → D3,  DIR+ → D4,  ENA+ → D5,  PUL-/DIR-/ENA- → GND
 *   micro:bit P0 → D6, P1 → D7, P2 → D8, micro:bit GND → GND
 *   리셋 버튼: D10 ↔ GND (누르면 LOW)
 *   (선택) 비상정지 감지: 비상정지 버튼의 보조 접점 D11 ↔ GND (평소 닫힘=LOW, 눌림=HIGH)
 *   (선택) 릴레이 모듈 IN → D12 (드라이버 전원 차단용)
 *
 * 시리얼 모니터 (115200bps, 줄 끝: 새 줄)
 *   ?        현재 상태 출력
 *   N800     자동 속도를 800 스텝/초로     S300  저속 속도를 300 스텝/초로
 *   A1500    가속도 (스텝/초²)             D     회전 방향 반대로
 *   T        시험 모드 켜기/끄기 (micro:bit 없이 시리얼로 1~4 입력해 모드 지정)
 *   1~4      (시험 모드에서만) 모드 지정     R     (시험 모드에서만) 잠김 해제
 *   ※ 속도 값을 정하면 아래 NORMAL_SPS / SLOW_SPS에 적어 두기 (전원 끄면 초기화됨)
 */

// ---------------- 핀 ----------------
const uint8_t PIN_PUL = 3;
const uint8_t PIN_DIR = 4;
const uint8_t PIN_ENA = 5;
const uint8_t PIN_MODE_B0 = 6;
const uint8_t PIN_MODE_B1 = 7;
const uint8_t PIN_HEARTBEAT = 8;
const uint8_t PIN_RESET_BTN = 10;
const uint8_t PIN_ESTOP_SENSE = 11;
const uint8_t PIN_RELAY = 12;

// ---------------- 설정 (★ 실물에 맞춰 조정) ----------------
float NORMAL_SPS = 800;           // ★ 자동 속도 (스텝/초). TB6600 마이크로스텝 설정에 따라 달라짐
float SLOW_SPS = 300;             // ★ 저속 속도
float ACCEL_SPS2 = 1500;          // 가속도. 출발할 때 탈조(헛돎)하면 낮추기
bool DIR_FORWARD = true;          // ★ 벨트가 반대로 돌면 false (또는 시리얼 D)
const float MIN_SPS = 50;         // 이보다 느리면 정지로 봄

const bool USE_ESTOP_SENSE = false;   // 비상정지 보조 접점을 D11에 연결했으면 true
const bool USE_RELAY = false;         // 릴레이로 드라이버 전원을 끊으면 true
const bool RELAY_ACTIVE_HIGH = true;  // ★ 릴레이 모듈이 HIGH에서 붙으면 true
const uint8_t ENA_ENABLE_LEVEL = LOW; // TB6600은 보통 ENA+가 LOW(또는 미연결)일 때 동작

const unsigned long HEARTBEAT_TIMEOUT_MS = 600;  // micro:bit는 0.1초마다 토글
const unsigned long PULSE_US = 10;               // 스텝 펄스 폭

// ---------------- 상태 ----------------
enum Mode { M_STOP = 0, M_NORMAL = 1, M_SLOW = 2, M_LOCK = 3 };
enum Latch { L_NONE = 0, L_POWERON, L_HEARTBEAT, L_ESTOP };

Mode mode = M_STOP;
Latch latch = L_POWERON;
bool testMode = false;
Mode testCmd = M_STOP;

float currentSps = 0;
float targetSps = 0;
unsigned long lastStepUs = 0;
unsigned long lastRampUs = 0;

int lastHb = -1;
unsigned long lastHbChangeMs = 0;
bool hbOk = false;               // 매 루프 갱신되는 살아 있음 신호 상태

bool btnStable = HIGH;
bool btnLastRead = HIGH;
unsigned long btnChangeMs = 0;

String rxLine = "";

const char *modeName(Mode m) {
  switch (m) {
    case M_NORMAL: return "NORMAL";
    case M_SLOW:   return "SLOW";
    case M_LOCK:   return "LOCK";
    default:       return "STOP";
  }
}

const char *latchName(Latch l) {
  switch (l) {
    case L_POWERON:   return "POWERON";
    case L_HEARTBEAT: return "HEARTBEAT_LOST";
    case L_ESTOP:     return "ESTOP";
    default:          return "NONE";
  }
}

void printStatus() {
  Serial.print(F("BELT,mode="));   Serial.print(modeName(mode));
  Serial.print(F(",latch="));      Serial.print(latchName(latch));
  Serial.print(F(",sps="));        Serial.print((int)currentSps);
  Serial.print(F(",target="));     Serial.print((int)targetSps);
  Serial.print(F(",normal="));     Serial.print((int)NORMAL_SPS);
  Serial.print(F(",slow="));       Serial.print((int)SLOW_SPS);
  Serial.print(F(",test="));       Serial.println(testMode ? 1 : 0);
}

void setDriverPower(bool on) {
  if (!USE_RELAY) return;
  digitalWrite(PIN_RELAY, (on == RELAY_ACTIVE_HIGH) ? HIGH : LOW);
}

void setLatch(Latch l) {
  if (latch == l) return;
  latch = l;
  if (l != L_NONE) {
    currentSps = 0;          // 안전 정지는 감속 없이 즉시
    targetSps = 0;
    setDriverPower(false);
    Serial.print(F("LATCH,")); Serial.println(latchName(l));
  } else {
    setDriverPower(true);
    Serial.println(F("LATCH,CLEARED"));
  }
  printStatus();
}

// ---------------- 입력 읽기 ----------------
Mode readModePins() {
  // INPUT_PULLUP: micro:bit가 빠지면 11(점검 잠금)이 되어 멈춤
  int b0 = digitalRead(PIN_MODE_B0);
  int b1 = digitalRead(PIN_MODE_B1);
  return (Mode)((b1 << 1) | b0);
}

bool heartbeatAlive() {
  int hb = digitalRead(PIN_HEARTBEAT);
  unsigned long now = millis();
  if (hb != lastHb) {
    lastHb = hb;
    lastHbChangeMs = now;
  }
  return (now - lastHbChangeMs) < HEARTBEAT_TIMEOUT_MS;
}

bool estopPressed() {
  if (!USE_ESTOP_SENSE) return false;
  return digitalRead(PIN_ESTOP_SENSE) == HIGH;   // 보조 접점이 열림 = 눌림
}

// 리셋 버튼이 새로 눌렸으면 true (50ms 디바운스)
bool resetPressedEdge() {
  bool r = digitalRead(PIN_RESET_BTN);
  unsigned long now = millis();
  if (r != btnLastRead) {
    btnLastRead = r;
    btnChangeMs = now;
  }
  if ((now - btnChangeMs) > 50 && r != btnStable) {
    btnStable = r;
    if (btnStable == LOW) return true;
  }
  return false;
}

void tryClearLatch(const __FlashStringHelper *by) {
  if (latch == L_NONE) return;
  bool alive = testMode || hbOk;
  if (!alive)        { Serial.println(F("RESET,REFUSED,no heartbeat")); return; }
  if (estopPressed()) { Serial.println(F("RESET,REFUSED,estop pressed")); return; }
  Serial.print(F("RESET,OK,")); Serial.println(by);
  setLatch(L_NONE);
}

// ---------------- 시리얼 명령 ----------------
void handleCommand(String cmd) {
  cmd.trim();
  if (cmd.length() == 0) return;
  char c = toupper(cmd.charAt(0));
  long v = cmd.substring(1).toInt();

  if (c == '?') { printStatus(); return; }
  if (c == 'N' && v > 0) { NORMAL_SPS = v; Serial.print(F("SET,normal=")); Serial.println(v); return; }
  if (c == 'S' && v > 0) { SLOW_SPS = v;   Serial.print(F("SET,slow="));   Serial.println(v); return; }
  if (c == 'A' && v > 0) { ACCEL_SPS2 = v; Serial.print(F("SET,accel="));  Serial.println(v); return; }
  if (c == 'D') {
    DIR_FORWARD = !DIR_FORWARD;
    currentSps = 0;                       // 방향 바꿀 때는 멈췄다가 다시 가속
    digitalWrite(PIN_DIR, DIR_FORWARD ? HIGH : LOW);
    Serial.print(F("SET,dir=")); Serial.println(DIR_FORWARD ? F("FWD") : F("REV"));
    return;
  }
  if (c == 'T') {
    testMode = !testMode;
    testCmd = M_STOP;
    Serial.print(F("TEST,")); Serial.println(testMode ? F("ON (micro:bit ignored)") : F("OFF"));
    if (!testMode) setLatch(L_POWERON);   // 시험 끝나면 다시 리셋 버튼 필요
    return;
  }
  if (testMode && c >= '1' && c <= '4') {
    const Mode map[] = { M_NORMAL, M_SLOW, M_STOP, M_LOCK };   // 카드 번호와 같은 의미
    testCmd = map[c - '1'];
    Serial.print(F("TEST,mode=")); Serial.println(modeName(testCmd));
    return;
  }
  if (testMode && c == 'R') { tryClearLatch(F("serial")); return; }
  Serial.print(F("ERR,")); Serial.println(cmd);
}

void readSerial() {
  while (Serial.available()) {
    char ch = Serial.read();
    if (ch == '\n' || ch == '\r') {
      if (rxLine.length() > 0) handleCommand(rxLine);
      rxLine = "";
    } else if (rxLine.length() < 20) {
      rxLine += ch;
    }
  }
}

// ---------------- 모터 ----------------
void updateTarget() {
  if (latch != L_NONE) { targetSps = 0; return; }
  switch (mode) {
    case M_NORMAL: targetSps = NORMAL_SPS; break;
    case M_SLOW:   targetSps = SLOW_SPS;   break;
    default:       targetSps = 0;          break;   // 일시 정지, 점검 잠금
  }
  // 멈춤은 감속 없이 즉시 (사람 접근 정지가 늦어지지 않게)
  if (targetSps == 0) currentSps = 0;
}

void rampSpeed() {
  unsigned long now = micros();
  unsigned long dtUs = now - lastRampUs;
  if (dtUs < 5000) return;              // 5ms마다 속도 갱신
  lastRampUs = now;
  float dv = ACCEL_SPS2 * (dtUs / 1000000.0);
  if (currentSps < targetSps) {
    if (currentSps < MIN_SPS) currentSps = MIN_SPS;
    currentSps = min(targetSps, currentSps + dv);
  } else if (currentSps > targetSps) {
    currentSps = max(targetSps, currentSps - dv);   // 자동 → 저속은 부드럽게 감속
    if (currentSps < MIN_SPS) currentSps = 0;
  }
}

void stepMotor() {
  if (currentSps < MIN_SPS) return;
  unsigned long now = micros();
  unsigned long interval = (unsigned long)(1000000.0 / currentSps);
  if (now - lastStepUs >= interval) {
    lastStepUs = now;
    digitalWrite(PIN_PUL, HIGH);
    delayMicroseconds(PULSE_US);
    digitalWrite(PIN_PUL, LOW);
  }
}

// ---------------- 메인 ----------------
void setup() {
  Serial.begin(115200);
  pinMode(PIN_PUL, OUTPUT);
  pinMode(PIN_DIR, OUTPUT);
  pinMode(PIN_ENA, OUTPUT);
  pinMode(PIN_MODE_B0, INPUT_PULLUP);
  pinMode(PIN_MODE_B1, INPUT_PULLUP);
  pinMode(PIN_HEARTBEAT, INPUT_PULLUP);
  pinMode(PIN_RESET_BTN, INPUT_PULLUP);
  if (USE_ESTOP_SENSE) pinMode(PIN_ESTOP_SENSE, INPUT_PULLUP);
  if (USE_RELAY) pinMode(PIN_RELAY, OUTPUT);

  digitalWrite(PIN_PUL, LOW);
  digitalWrite(PIN_DIR, DIR_FORWARD ? HIGH : LOW);
  digitalWrite(PIN_ENA, ENA_ENABLE_LEVEL);
  setDriverPower(false);

  lastHbChangeMs = millis();
  Serial.println(F("CONVEYOR,READY - press reset button to start"));
  printStatus();
}

void loop() {
  readSerial();

  // 1) 안전 확인
  hbOk = heartbeatAlive();
  if (estopPressed()) setLatch(L_ESTOP);
  if (!testMode && latch == L_NONE && !hbOk) setLatch(L_HEARTBEAT);
  if (resetPressedEdge()) tryClearLatch(F("button"));

  // 2) 모드 읽기
  Mode m = testMode ? testCmd : readModePins();
  if (m != mode) {
    mode = m;
    Serial.print(F("MODE,")); Serial.println(modeName(mode));
  }

  // 3) 속도 결정 → 가속 → 스텝
  updateTarget();
  rampSpeed();
  stepMotor();
}
