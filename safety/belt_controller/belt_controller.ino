/*
 * 벨트·안전 제어 (아두이노 우노 + TB6600 스텝모터 드라이버) — 통합본
 *
 * code/arduino/conveyor/conveyor.ino의 구동 부분(모드 2비트 핀, 가감속, 시리얼 조정·시험 모드)을 바탕으로
 * safety 규격(docs/spec/safety_rules.md)의 안전 기능을 합쳤다.
 * 규격: docs/spec/safety_rules.md, docs/spec/protocol.md 3·4절, 핀 표: safety/README.md
 * ★ 이 파일을 고치면 정지 시험 N1~N5를 다시 하고 docs/tests/kpi_log.md에 기록한다.
 *
 * 하는 일
 * - 게이트웨이 micro:bit가 보내는 모드(2비트)대로 벨트 속도를 바꾼다. 자동 = 보통, 저속 = 느리게.
 * - 노트북(웹캠 판정)이 PAUSE를 보내면 검사 자리에서 잠깐 멈추고, GO를 받으면 다시 간다 (검사용 멈춤, 잠기지 않음).
 * - (선택) IR 도착 센서가 병을 보면 스스로 검사 멈춤을 하고 EVT,ARRIVE를 보낸다. 웹캠 감지의 보조.
 *
 * 안전: 아래 경우에는 즉시(감속 없이) 멈추고 "잠김" 상태가 된다.
 *   1) 전원을 켰을 때                     2) micro:bit 살아 있음 신호(하트비트)가 끊겼을 때
 *   3) 모드 핀이 정지(00)·점검 잠금(11)일 때 — 손 3의 정지 거리 감지·주먹 수신호·잠금, 선 빠짐(11) 포함
 *   4) 비상정지 버튼 (감지 배선을 했을 때)   5) 노트북 HOLD 명령   6) (선택) IR 커튼
 *   잠김은 "모드 핀이 자동(01)·저속(10)" + "하트비트 정상" + "리셋 버튼"이 모두 맞아야만 풀린다.
 *   노트북·시리얼로는 풀 수 없다. 비상정지 버튼은 이 프로그램과 상관없이 12V 전원을 직접 끊도록 배선한다.
 *
 * 배선 (safety/README.md 핀 표와 같게)
 *   TB6600 PUL+ → D3,  DIR+ → D4,  ENA+ → D5,  PUL-/DIR-/ENA- → GND
 *   게이트웨이 micro:bit P0 → D6 (모드 비트 0), P1 → D7 (모드 비트 1), P2 → D8 (하트비트), GND → GND
 *   리셋 버튼: D10 ↔ GND (누르면 LOW)
 *   전원 릴레이 IN → D12 (잠김이 아닐 때만 붙음)
 *   (선택) IR 도착 센서 OUT → D2 (병 감지 = LOW)
 *   (선택) IR 커튼 OUT → D9 (손 감지 = LOW)
 *   (선택) 비상정지 보조 접점: D11 ↔ GND (평소 닫힘 = LOW, 눌림 = HIGH)
 *
 * 시리얼 (115200bps, 줄 끝: 새 줄)
 *   노트북 → 우노:  PAUSE  GO  HOLD  PING                       (protocol.md 4절)
 *   우노 → 노트북:  EVT,STOP,<원인>  EVT,RUN  EVT,PAUSE  EVT,ARRIVE  STATE,<RUN|PAUSE|STOP>,<N|S>  PONG
 *   사람용 조정:    ?  상태 출력      N800  자동 속도(스텝/초)   S300  저속 속도   A1500  가속도
 *                   D  방향 반대로    T  시험 모드 켜기/끄기   1~4  (시험 모드에서만) 모드 지정
 *   ※ 시험 모드는 micro:bit 없이 속도·방향을 맞추는 용도다. 하트비트 검사를 건너뛰므로 사람이 옆에 있을 때만 쓴다.
 *     시험 모드에서도 재가동은 리셋 버튼으로만 한다.
 *   ※ 속도 값을 정하면 아래 NORMAL_SPS / SLOW_SPS에 적어 두기 (전원 끄면 초기화됨)
 */

// ---------------- 핀 ----------------
const uint8_t PIN_IR_ARRIVE = 2;
const uint8_t PIN_PUL = 3;
const uint8_t PIN_DIR = 4;
const uint8_t PIN_ENA = 5;
const uint8_t PIN_MODE_B0 = 6;
const uint8_t PIN_MODE_B1 = 7;
const uint8_t PIN_HEARTBEAT = 8;
const uint8_t PIN_IR_CURTAIN = 9;
const uint8_t PIN_RESET_BTN = 10;
const uint8_t PIN_ESTOP_SENSE = 11;
const uint8_t PIN_RELAY = 12;

// ---------------- 설정 (★ 실물에 맞춰 조정) ----------------
float NORMAL_SPS = 800;           // ★ 자동 속도 (스텝/초). TB6600 마이크로스텝 설정에 따라 달라짐
float SLOW_SPS = 300;             // ★ 저속 속도
float ACCEL_SPS2 = 1500;          // 가속도. 출발할 때 탈조(헛돎)하면 낮추기
bool DIR_FORWARD = true;          // ★ 벨트가 반대로 돌면 false (또는 시리얼 D)
const float MIN_SPS = 50;         // 이보다 느리면 정지로 봄

const bool USE_IR_ARRIVE = false;     // IR 도착 센서를 D2에 연결했으면 true (웹캠 감지의 보조)
const bool USE_IR_CURTAIN = false;    // IR 커튼을 D9에 연결했으면 true (지금은 쓰지 않음)
const bool USE_ESTOP_SENSE = false;   // 비상정지 보조 접점을 D11에 연결했으면 true
const bool USE_RELAY = true;          // 전원 릴레이 (safety_rules.md 3절). 안 달았으면 출력만 나가고 영향 없음
const bool RELAY_ACTIVE_HIGH = true;  // ★ 릴레이 모듈이 HIGH에서 붙으면 true
const uint8_t ENA_ENABLE_LEVEL = LOW; // ★ TB6600은 보통 ENA+가 LOW(또는 미연결)일 때 동작
const uint8_t ENA_DISABLE_LEVEL = HIGH;

const unsigned long HEARTBEAT_TIMEOUT_MS = 600;  // settings.yaml: safety.heartbeat_timeout_ms (게이트웨이 0.1초 토글)
const unsigned long ARRIVE_DEBOUNCE_MS = 20;     // IR 도착 센서가 이 시간 이상 감지해야 병으로 봄
const unsigned long STATE_PERIOD_MS = 1000;      // STATE 주기 출력
const unsigned long PULSE_US = 10;               // 스텝 펄스 폭

// ---------------- 상태 ----------------
enum Mode { M_STOP = 0, M_NORMAL = 1, M_SLOW = 2, M_LOCK = 3 };   // 핀 값 (P1,P0)
enum Latch { L_NONE = 0, L_POWERON, L_HEARTBEAT, L_MODE, L_ESTOP, L_HOLD, L_IR };

Mode mode = M_STOP;
Latch latch = L_POWERON;          // 켜자마자 잠김 (safety_rules.md 4절)
bool paused = false;              // 검사용 멈춤 (PAUSE 또는 IR 도착). 잠김과 다름
bool arriveLatched = false;       // 도착 센서를 지나간 병이 빠질 때까지 다시 멈추지 않음
unsigned long arriveSinceMs = 0;
bool testMode = false;
Mode testCmd = M_STOP;

float currentSps = 0;
float targetSps = 0;
unsigned long lastStepUs = 0;
unsigned long lastRampUs = 0;
unsigned long lastStateMs = 0;

int lastHb = -1;
unsigned long lastHbChangeMs = 0;
bool hbOk = false;

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

// EVT,STOP,<원인> 에 쓰는 이름 (protocol.md 4절 STOP_CAUSES)
const char *latchName(Latch l) {
  switch (l) {
    case L_POWERON:   return "POWERON";
    case L_HEARTBEAT: return "HB";
    case L_MODE:      return "MODE";
    case L_ESTOP:     return "ESTOP";
    case L_HOLD:      return "HOLD";
    case L_IR:        return "IR";
    default:          return "NONE";
  }
}

const char *runName() {
  if (latch != L_NONE) return "STOP";
  return paused ? "PAUSE" : "RUN";
}

void printStatus() {
  Serial.print(F("BELT,run="));    Serial.print(runName());
  Serial.print(F(",mode="));       Serial.print(modeName(mode));
  Serial.print(F(",latch="));      Serial.print(latchName(latch));
  Serial.print(F(",sps="));        Serial.print((int)currentSps);
  Serial.print(F(",normal="));     Serial.print((int)NORMAL_SPS);
  Serial.print(F(",slow="));       Serial.print((int)SLOW_SPS);
  Serial.print(F(",hb="));         Serial.print(hbOk ? 1 : 0);
  Serial.print(F(",test="));       Serial.println(testMode ? 1 : 0);
}

void printState() {
  Serial.print(F("STATE,"));
  Serial.print(runName());
  Serial.print(F(","));
  Serial.println(mode == M_SLOW ? "S" : "N");
}

// 출력: 잠김이면 드라이버 끔(ENA) + 전원 릴레이 개방 (이중). 검사 멈춤은 토크 유지
void applyOutputs() {
  bool powerOn = (latch == L_NONE);
  digitalWrite(PIN_ENA, powerOn ? ENA_ENABLE_LEVEL : ENA_DISABLE_LEVEL);
  if (USE_RELAY) digitalWrite(PIN_RELAY, (powerOn == RELAY_ACTIVE_HIGH) ? HIGH : LOW);
}

void setLatch(Latch l) {
  if (latch != L_NONE || l == L_NONE) return;   // 이미 잠겼으면 첫 원인을 유지
  latch = l;
  paused = false;
  currentSps = 0;          // 안전 정지는 감속 없이 즉시
  targetSps = 0;
  applyOutputs();
  Serial.print(F("EVT,STOP,")); Serial.println(latchName(l));
}

// ---------------- 입력 읽기 ----------------
Mode readModePins() {
  // INPUT_PULLUP: micro:bit 선이 빠지면 11(점검 잠금)이 되어 멈춘다
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

bool curtainBlocked() {
  if (!USE_IR_CURTAIN) return false;
  return digitalRead(PIN_IR_CURTAIN) == LOW;
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

// 재가동: 리셋 버튼으로만. 모드 핀이 자동·저속(카드·수신호 1 또는 2), 하트비트 정상, 위험 없음일 때만
void tryClearLatch() {
  if (latch == L_NONE) return;
  if (!testMode && !hbOk)                  { Serial.println(F("RESET,REFUSED,no heartbeat")); return; }
  if (estopPressed())                      { Serial.println(F("RESET,REFUSED,estop pressed")); return; }
  if (curtainBlocked())                    { Serial.println(F("RESET,REFUSED,ir curtain")); return; }
  if (mode != M_NORMAL && mode != M_SLOW)  { Serial.println(F("RESET,REFUSED,mode not 1 or 2")); return; }
  latch = L_NONE;
  paused = false;
  arriveLatched = false;
  applyOutputs();
  Serial.println(F("EVT,RUN"));
}

// ---------------- 시리얼 명령 ----------------
void handleCommand(String cmd) {
  cmd.trim();
  if (cmd.length() == 0) return;

  // 노트북 명령 (protocol.md 4절). 재가동 명령은 없다
  if (cmd == "PAUSE") {
    if (latch == L_NONE && !paused) {
      paused = true;
      currentSps = 0;
      Serial.println(F("EVT,PAUSE"));
    }
    return;
  }
  if (cmd == "GO")   { if (latch == L_NONE) paused = false; return; }   // 잠김이면 무시
  if (cmd == "HOLD") { setLatch(L_HOLD); return; }
  if (cmd == "PING") { Serial.println(F("PONG")); return; }

  // 사람용 조정 명령
  char c = toupper(cmd.charAt(0));
  long v = cmd.substring(1).toInt();
  if (c == '?') { printStatus(); return; }
  if (c == 'N' && v > 0) { NORMAL_SPS = v; Serial.print(F("SET,normal=")); Serial.println(v); return; }
  if (c == 'S' && v > 0) { SLOW_SPS = v;   Serial.print(F("SET,slow="));   Serial.println(v); return; }
  if (c == 'A' && v > 0) { ACCEL_SPS2 = v; Serial.print(F("SET,accel="));  Serial.println(v); return; }
  if (c == 'D' && cmd.length() == 1) {
    DIR_FORWARD = !DIR_FORWARD;
    currentSps = 0;                       // 방향 바꿀 때는 멈췄다가 다시 가속
    digitalWrite(PIN_DIR, DIR_FORWARD ? HIGH : LOW);
    Serial.print(F("SET,dir=")); Serial.println(DIR_FORWARD ? F("FWD") : F("REV"));
    return;
  }
  if (c == 'T' && cmd.length() == 1) {
    testMode = !testMode;
    testCmd = M_STOP;                     // 켜고 끌 때 모두 정지 모드 → 잠김 → 리셋 버튼 필요
    Serial.print(F("TEST,")); Serial.println(testMode ? F("ON (micro:bit ignored)") : F("OFF"));
    return;
  }
  if (testMode && cmd.length() == 1 && c >= '1' && c <= '4') {
    const Mode map[] = { M_NORMAL, M_SLOW, M_STOP, M_LOCK };   // 카드 번호와 같은 의미
    testCmd = map[c - '1'];
    Serial.print(F("TEST,mode=")); Serial.println(modeName(testCmd));
    return;
  }
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

// ---------------- 도착 센서 (선택) ----------------
void checkArrive() {
  if (!USE_IR_ARRIVE) return;
  bool seen = digitalRead(PIN_IR_ARRIVE) == LOW;
  unsigned long now = millis();
  if (!seen) {
    arriveSinceMs = now;
    if (!paused) arriveLatched = false;   // 병이 센서를 벗어남 → 다음 병을 받을 준비
    return;
  }
  if (latch == L_NONE && !paused && !arriveLatched && now - arriveSinceMs >= ARRIVE_DEBOUNCE_MS) {
    arriveLatched = true;
    paused = true;
    currentSps = 0;
    Serial.println(F("EVT,ARRIVE"));
  }
}

// ---------------- 모터 ----------------
void updateTarget() {
  if (latch != L_NONE || paused) { targetSps = 0; currentSps = 0; return; }   // 멈춤은 감속 없이 즉시
  switch (mode) {
    case M_NORMAL: targetSps = NORMAL_SPS; break;
    case M_SLOW:   targetSps = SLOW_SPS;   break;
    default:       targetSps = 0; currentSps = 0; break;
  }
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
  if (USE_IR_ARRIVE) pinMode(PIN_IR_ARRIVE, INPUT_PULLUP);
  if (USE_IR_CURTAIN) pinMode(PIN_IR_CURTAIN, INPUT_PULLUP);
  if (USE_ESTOP_SENSE) pinMode(PIN_ESTOP_SENSE, INPUT_PULLUP);
  if (USE_RELAY) pinMode(PIN_RELAY, OUTPUT);

  digitalWrite(PIN_PUL, LOW);
  digitalWrite(PIN_DIR, DIR_FORWARD ? HIGH : LOW);
  applyOutputs();                       // latch = POWERON → 드라이버 끔, 릴레이 개방

  lastHbChangeMs = millis();
  Serial.println(F("EVT,STOP,POWERON"));
  printStatus();
}

void loop() {
  unsigned long nowMs = millis();
  readSerial();

  // 1) 입력
  hbOk = heartbeatAlive();
  Mode m = testMode ? testCmd : readModePins();
  if (m != mode) {
    mode = m;
    Serial.print(F("MODE,")); Serial.println(modeName(mode));
  }

  // 2) 안전 검사가 가장 먼저 (원인이 여러 개면 처음 것을 기록)
  if (estopPressed()) setLatch(L_ESTOP);
  if (curtainBlocked()) setLatch(L_IR);
  if (!testMode && !hbOk) setLatch(L_HEARTBEAT);
  if (mode == M_STOP || mode == M_LOCK) setLatch(L_MODE);

  // 3) 재가동: 리셋 버튼으로만
  if (resetPressedEdge()) tryClearLatch();

  // 4) 도착 센서 (선택)
  checkArrive();

  // 5) 속도 결정 → 가속 → 스텝
  updateTarget();
  rampSpeed();
  stepMotor();

  // 6) 주기 상태
  if (nowMs - lastStateMs >= STATE_PERIOD_MS) {
    lastStateMs = nowMs;
    printState();
  }
}
