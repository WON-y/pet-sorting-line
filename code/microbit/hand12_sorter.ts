// =====================================================================
//  작업 손 (분기 1 / 분기 2) - 날개판으로 병 분기
//  - 손 1: 유색·불투명 병을 벨트 밖으로 분기
//  - 손 2: 부적합(내용물 남음·라벨 있음·재검사) 병을 부적합 통으로 분기
//  - 날개판은 손목 부분에 장치로 고정되어 있다. 손목(6번 서보)을 돌려
//    날개판 각도를 바꾸고, 손가락은 쉬는 자세로 둔 채 움직이지 않는다.
//  필요한 확장: https://github.com/Hiwonder/StartbitV2
//  사용법: MakeCode 새 프로젝트 → 확장 추가 → JavaScript 탭에 전체 붙여넣기
// =====================================================================

// ---------------- 설정 (★ 표시는 실물에 맞춰 꼭 확인) ----------------
const HAND_ID = 1            // ★ 손 1이면 1, 손 2면 2
const RADIO_GROUP = 73       // ★ 손 4대 + 게이트웨이 모두 같은 값

// 손목(6번 서보) = 날개판 각도
const WRIST_PARALLEL = 90    // ★ 날개판이 벨트와 나란히 (병이 그냥 지나감)
const WRIST_DIVERT = 50      // ★ 날개판이 벨트 위로 30~45° 비스듬히 (병을 분기)
const WRIST_MOVE_MS = 400    // 날개판 회전 시간 (천천히 = 안전)

// 손가락 쉬는 자세 (1번=엄지는 2~5번과 방향이 반대)
// ★ 손목에 단 고정 장치와 부딪히지 않는 각도로 맞출 것
const REST_THUMB = 50
const REST_FINGER = 130

const LINK_TIMEOUT_MS = 2000 // 신호 손(3) 신호가 이 시간 끊기면 그 자리 멈춤

// ---------------- 약속 (모든 프로그램 공통) ----------------
// 모드: 1 자동, 2 저속, 3 일시 정지, 4 점검 잠금
// 판정: 0 재검사, 1 투명 적합, 2 내용물 남음, 3 라벨 있음, 4 유색·불투명
// 라디오: "mode"=모드, "help"=도움 요청(0/1), "dng"=접근 위험(0/1/2),
//         "jdg"=순번*10+판정 (게이트웨이가 3번 반복 전송, 순번으로 중복 제거)

// ---------------- 상태 ----------------
let mode = 3                 // 신호가 오기 전에는 멈춤으로 시작
let linkOk = false
let lastLinkMs = 0
let wristNow = -1
let pendingTarget = -1       // 멈춤 중에 받은 판정 (재개하면 적용)
let lastSeq = -1
let blinkOn = false

// ---------------- 시작 (라디오 수신보다 먼저) ----------------
StartbitV2.startbit_Init()
radio.setGroup(RADIO_GROUP)
radio.setTransmitPower(7)
restFingers()
moveWrist(WRIST_PARALLEL)
updateLed()
basic.showNumber(HAND_ID)

// ---------------- 서보 ----------------
function servo(index: number, angle: number, ms: number) {
    StartbitV2.setPwmServo(StartbitV2.startbit_servorange.range1, index, angle, ms)
}

function restFingers() {
    servo(1, REST_THUMB, 600)
    for (let i = 2; i <= 5; i++) servo(i, REST_FINGER, 600)
}

function moveWrist(angle: number) {
    if (angle == wristNow) return
    servo(6, angle, WRIST_MOVE_MS)
    wristNow = angle
}

// ---------------- LED ----------------
function setColor(r: number, g: number, b: number, board: StartbitRGBColors) {
    RGBSonar.SETRGB(RGBSonar.RGBMode.rgb, RGBSonar.RGBNum.all, r, g, b)  // 초음파 센서 LED
    StartbitV2.startbit_setPixelRGB(StartbitLights.All, board)            // 확장보드 LED
    StartbitV2.startbit_showLight()
}

function ledOff() {
    RGBSonar.SETRGB(RGBSonar.RGBMode.rgb, RGBSonar.RGBNum.all, 0, 0, 0)
    StartbitV2.startbit_clearLight()
}

function updateLed() {
    if (!linkOk) setColor(80, 0, 80, StartbitRGBColors.Violet)      // 신호 끊김
    else if (mode == 1) setColor(0, 255, 0, StartbitRGBColors.Green)
    else if (mode == 2) setColor(255, 160, 0, StartbitRGBColors.Yellow)
    else setColor(255, 0, 0, StartbitRGBColors.Red)                  // 3, 4(깜빡임은 아래 루프)
}

// ---------------- 동작 규칙 ----------------
function shouldDivert(cls: number): boolean {
    if (HAND_ID == 1) return cls == 4                       // 유색·불투명
    return cls == 0 || cls == 2 || cls == 3                 // 재검사·내용물·라벨
}

function canMove(): boolean {
    return linkOk && (mode == 1 || mode == 2)
}

function applyPending() {
    if (pendingTarget >= 0 && canMove()) {
        moveWrist(pendingTarget)
        pendingTarget = -1
    }
}

function onModeChange(m: number) {
    mode = m
    updateLed()
    if (m == 4) {
        // 점검 잠금: 날개판을 벨트와 나란히 접고 멈춤, 대기 판정 버림
        pendingTarget = -1
        moveWrist(WRIST_PARALLEL)
    } else if (m == 1 || m == 2) {
        applyPending()
    }
    // m == 3 (일시 정지): 그 자리 멈춤 → 아무것도 하지 않음
}

function onJudgement(cls: number) {
    if (mode != 4) {
        let target = shouldDivert(cls) ? WRIST_DIVERT : WRIST_PARALLEL
        if (canMove()) moveWrist(target)
        else pendingTarget = target  // 멈춤·신호 끊김 중이면 재개 후 적용
    }
    basic.showNumber(cls)            // 화면 표시는 날개판을 움직인 뒤에
}

// ---------------- 라디오 ----------------
radio.onReceivedValue(function (name: string, value: number) {
    if (name == "mode") {
        lastLinkMs = control.millis()
        if (!linkOk) {
            linkOk = true
            updateLed()
            basic.clearScreen()
        }
        if (value >= 1 && value <= 4 && value != mode) onModeChange(value)
        else applyPending()
    } else if (name == "jdg") {
        let seq = Math.idiv(value, 10)
        if (seq == lastSeq) return   // 반복 전송된 같은 판정
        lastSeq = seq
        onJudgement(value % 10)
    }
})

// ---------------- 버튼: 날개판 각도 확인용 ----------------
// 움직이는 중(자동·저속)에는 무시. 일시 정지·잠금·신호 끊김일 때만 동작
// 각도를 맞출 때 쓰고, 시험이 끝나면 B로 나란히 위치에 돌려 둘 것
input.onButtonPressed(Button.A, function () {
    if (canMove()) return
    moveWrist(WRIST_DIVERT)          // 비스듬히 (분기 위치)
    basic.showArrow(ArrowNames.NorthEast)
})
input.onButtonPressed(Button.B, function () {
    if (canMove()) return
    moveWrist(WRIST_PARALLEL)        // 나란히 (통과 위치)
    basic.showArrow(ArrowNames.North)
})

// ---------------- 신호 감시 + 잠금 깜빡임 ----------------
basic.forever(function () {
    if (linkOk && control.millis() - lastLinkMs > LINK_TIMEOUT_MS) {
        linkOk = false               // 신호 끊김 = 그 자리 멈춤 (canMove()가 false가 됨)
        updateLed()
        basic.showString("?")
    }
    if (linkOk && mode == 4) {
        blinkOn = !blinkOn
        if (blinkOn) setColor(255, 0, 0, StartbitRGBColors.Red)
        else ledOff()
    }
    basic.pause(400)
})
