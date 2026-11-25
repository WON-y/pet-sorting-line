// =====================================================================
//  신호 손 (지시) - 손 3
//  - WonderCam으로 숫자 카드(1~5)를 읽어 모드를 정하고 라디오로 전송
//  - 손가락으로 모드를 복창, 초음파로 작업자 접근 감지
//  - 이 손이 모드의 "기준"이다. 0.3초마다 모드를 다시 보내고(살아 있음 신호),
//    이 신호가 끊기면 다른 손과 벨트는 스스로 멈춘다.
//  필요한 확장: https://github.com/Hiwonder/StartbitV2
//              https://github.com/Hiwonder/WonderCam
// =====================================================================

// ---------------- 설정 (★ 표시는 실물에 맞춰 꼭 확인) ----------------
const RADIO_GROUP = 73       // ★ 손 4대 + 게이트웨이 모두 같은 값

// 접근 거리 (mm). 초음파 시험 뒤 확정
const WARN_MM = 400          // ★ 주의: "멈춰" 손짓 + 경고음
const STOP_MM = 200          // ★ 정지: 일시 정지(모드 3)로 전환
const WARN_CONFIRM = 3       // 주의는 연속 n번 감지해야 인정 (오경보 필터)
                             // 정지는 1번만 감지해도 즉시 멈춤

// 카드 인식
const CARD_CONF = 0.6        // 이 신뢰도 이상만 인정
const CARD_FRAMES = 3        // 같은 숫자가 연속 n번 보여야 확정
const REARM_FRAMES = 8       // 카드가 n번 연속 안 보여야 다음 카드를 받음

// 손 자세
const WRIST_CENTER = 90
const WRIST_LOCK = 170       // ★ 점검 잠금 표시용 손목 각도
const WAVE = 30              // "멈춰" 손짓 좌우 흔들기 폭
const OPEN_THUMB = 50
const CLOSE_THUMB = 130
const OPEN_FINGER = 130
const CLOSE_FINGER = 50

// ---------------- 약속 (모든 프로그램 공통) ----------------
// 모드: 1 자동, 2 저속, 3 일시 정지, 4 점검 잠금
// 카드 5 = 도움 요청 (모드와 별개로 켜짐, 벨트·작업 손은 그대로)
// 라디오: "mode"=1~4, "help"=0/1, "dng"=0 정상/1 주의/2 정지거리

// ---------------- 상태 ----------------
let mode = 3                 // 켜지면 일시 정지로 시작 → 카드 1·2로 출발
let help = false
let danger = 0
let candidate = 0
let streak = 0
let noCard = 0
let armed = true
let warnHits = 0
let posedKey = -1
let waveLeft = false
let blinkOn = false

// ---------------- 시작 (라디오·버튼 처리보다 먼저) ----------------
StartbitV2.startbit_Init()
wondercam.wondercam_init(wondercam.DEV_ADDR.x32)   // 카메라가 없으면 "E"를 띄우며 기다림
wondercam.ChangeFunc(wondercam.Functions.NumberRecognition)
radio.setGroup(RADIO_GROUP)
radio.setTransmitPower(7)
updateLed()
basic.showNumber(mode)

// ---------------- 서보·자세 ----------------
function servo(index: number, angle: number, ms: number) {
    StartbitV2.setPwmServo(StartbitV2.startbit_servorange.range1, index, angle, ms)
}

// open: 엄지, 검지, 중지, 약지, 새끼 순서로 편 상태면 true
function fingers(t: boolean, i: boolean, m: boolean, r: boolean, p: boolean, ms: number) {
    servo(1, t ? OPEN_THUMB : CLOSE_THUMB, ms)
    servo(2, i ? OPEN_FINGER : CLOSE_FINGER, ms)
    servo(3, m ? OPEN_FINGER : CLOSE_FINGER, ms)
    servo(4, r ? OPEN_FINGER : CLOSE_FINGER, ms)
    servo(5, p ? OPEN_FINGER : CLOSE_FINGER, ms)
}

function poseForMode(m: number) {
    if (m == 1) fingers(true, true, true, true, true, 400)          // 활짝 폄
    else if (m == 2) fingers(false, true, true, false, false, 400)  // 2개만 폄
    else fingers(false, false, false, false, false, 400)            // 주먹 (3, 4)
    servo(6, m == 4 ? WRIST_LOCK : WRIST_CENTER, 500)                // 4는 손목 돌려 표시
}

// ---------------- LED·소리 ----------------
function setColor(r: number, g: number, b: number, board: StartbitRGBColors) {
    RGBSonar.SETRGB(RGBSonar.RGBMode.rgb, RGBSonar.RGBNum.all, r, g, b)
    StartbitV2.startbit_setPixelRGB(StartbitLights.All, board)
    StartbitV2.startbit_showLight()
}

function ledOff() {
    RGBSonar.SETRGB(RGBSonar.RGBMode.rgb, RGBSonar.RGBNum.all, 0, 0, 0)
    StartbitV2.startbit_clearLight()
}

function updateLed() {
    if (mode == 1) setColor(0, 255, 0, StartbitRGBColors.Green)
    else if (mode == 2) setColor(255, 160, 0, StartbitRGBColors.Yellow)
    else setColor(255, 0, 0, StartbitRGBColors.Red)
}

function beep(freq: number, ms: number) {
    control.inBackground(function () {
        music.playTone(freq, ms)
    })
}

// ---------------- 모드 바꾸기 + 전송 ----------------
function broadcast() {
    radio.sendValue("mode", mode)
    radio.sendValue("help", help ? 1 : 0)
    radio.sendValue("dng", danger)
}

function setMode(m: number) {
    if (m == mode) return
    mode = m
    updateLed()
    basic.showNumber(mode)
    broadcast()
}

function setHelp(on: boolean) {
    if (on == help) return
    help = on
    if (help) basic.showString("H")
    else basic.showNumber(mode)
    broadcast()
}

function reject() {
    beep(220, 300)
    basic.showIcon(IconNames.No)
    basic.pause(300)
    basic.showNumber(mode)
}

function handleCard(n: number) {
    if (n == 5) {                              // 도움 요청: 잠금 중에도 가능
        setHelp(true)
        beep(988, 150)
        return
    }
    if (mode == 4) { reject(); return }        // 점검 잠금 중에는 카드로 못 바꿈
    if ((n == 1 || n == 2) && danger == 2) {   // 사람이 정지 거리 안에 있으면 출발 금지
        reject()
        return
    }
    setHelp(false)
    setMode(n)
    beep(880, 120)
}

// ---------------- 카드 인식 루프 ----------------
basic.forever(function () {
    wondercam.UpdateResult()
    let n = wondercam.NumberWithMaxConfidence()
    let c = wondercam.MaxConfidenceOfNumber()
    if (n >= 1 && n <= 5 && c >= CARD_CONF) {
        noCard = 0
        if (n == candidate) streak++
        else { candidate = n; streak = 1 }
        // 카드를 계속 들고 있어도 한 번만 처리 (내렸다 다시 보여야 다음 카드)
        if (armed && streak >= CARD_FRAMES) {
            armed = false
            handleCard(candidate)
        }
    } else {
        streak = 0
        candidate = 0
        noCard++
        if (noCard >= REARM_FRAMES) armed = true
    }
    basic.pause(50)
})

// ---------------- 접근 감지 루프 ----------------
basic.forever(function () {
    let d = RGBSonar.GETDISTANCE()      // mm, 0 = 측정 실패(무시)
    let newDanger = 0
    if (d > 0 && d < STOP_MM) {
        newDanger = 2
        warnHits = WARN_CONFIRM
    } else if (d > 0 && d < WARN_MM) {
        warnHits++
        if (warnHits >= WARN_CONFIRM) newDanger = 1
    } else {
        warnHits = 0
    }
    if (newDanger == 2 && mode != 4 && mode != 3) {
        setMode(3)                      // 정지: 사람이 물러나도 스스로 다시 돌지 않음
        beep(1200, 600)
    }
    if (newDanger != danger) {
        danger = newDanger
        broadcast()
    }
    basic.pause(60)
})

// ---------------- 손 동작 루프 (서보는 이 루프만 움직임) ----------------
basic.forever(function () {
    if (danger == 1) {
        // 주의: 손바닥 펴고 좌우로 흔드는 "멈춰" 손짓 + 경고음
        if (posedKey != 100) {
            fingers(true, true, true, true, true, 300)
            posedKey = 100
        }
        waveLeft = !waveLeft
        servo(6, WRIST_CENTER + (waveLeft ? -WAVE : WAVE), 350)
        beep(880, 100)
        basic.pause(400)
    } else {
        if (posedKey != mode) {
            poseForMode(mode)
            posedKey = mode
        }
        basic.pause(100)
    }
})

// ---------------- 살아 있음 신호 + 잠금 깜빡임 ----------------
basic.forever(function () {
    broadcast()
    if (mode == 4) {
        blinkOn = !blinkOn
        if (blinkOn) setColor(255, 0, 0, StartbitRGBColors.Red)
        else ledOff()
    }
    basic.pause(300)
})

// ---------------- 버튼·터치 ----------------
// A: 즉시 일시 정지 (카드 없이 급히 멈출 때)
input.onButtonPressed(Button.A, function () {
    if (mode != 4) {
        setMode(3)
        beep(660, 200)
    }
})
// B: 도움 요청 끄기 (작업자가 왔을 때)
input.onButtonPressed(Button.B, function () {
    setHelp(false)
})
// A+B: 점검 잠금 해제 → 일시 정지(3). 출발은 다시 카드 1·2로
input.onButtonPressed(Button.AB, function () {
    if (mode == 4) {
        setMode(3)
        beep(523, 150)
        beep(784, 150)
    }
})
// 로고 터치: 도움 요청 켜기
input.onLogoEvent(TouchButtonEvent.Pressed, function () {
    setHelp(true)
    beep(988, 150)
})
