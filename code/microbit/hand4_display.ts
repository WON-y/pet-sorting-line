// =====================================================================
//  신호 손 (원격 표시) - 손 4
//  - 라인에서 떨어진 관리자 쪽에서, 라디오로 받은 모드·위험 상태를
//    손가락, LED, 소리로 보여 준다. 센서 입력 없음.
//  - 도움 요청(카드 5)이면 이 손만 파랑 + 호출음 + 손가락 흔들기
//  필요한 확장: https://github.com/Hiwonder/StartbitV2
// =====================================================================

// ---------------- 설정 (★ 표시는 실물에 맞춰 꼭 확인) ----------------
const RADIO_GROUP = 73       // ★ 손 4대 + 게이트웨이 모두 같은 값
const LINK_TIMEOUT_MS = 2000 // 신호 손(3) 신호가 이 시간 끊기면 "?" 표시

const WRIST_CENTER = 90
const WRIST_LOCK = 170       // ★ 점검 잠금 표시용 손목 각도 (손 3과 같게)
const WAVE = 30
const OPEN_THUMB = 50
const CLOSE_THUMB = 130
const OPEN_FINGER = 130
const CLOSE_FINGER = 50

// ---------------- 상태 ----------------
let mode = 3
let help = false
let danger = 0
let linkOk = false
let lastLinkMs = 0
let posedKey = -1
let waveLeft = false
let wiggleStep = 0
let blinkOn = false
let lastCallMs = 0

// ---------------- 시작 (라디오 수신보다 먼저) ----------------
StartbitV2.startbit_Init()
radio.setGroup(RADIO_GROUP)
updateLed()
basic.showString("?")

// ---------------- 서보·자세 ----------------
function servo(index: number, angle: number, ms: number) {
    StartbitV2.setPwmServo(StartbitV2.startbit_servorange.range1, index, angle, ms)
}

function fingers(t: boolean, i: boolean, m: boolean, r: boolean, p: boolean, ms: number) {
    servo(1, t ? OPEN_THUMB : CLOSE_THUMB, ms)
    servo(2, i ? OPEN_FINGER : CLOSE_FINGER, ms)
    servo(3, m ? OPEN_FINGER : CLOSE_FINGER, ms)
    servo(4, r ? OPEN_FINGER : CLOSE_FINGER, ms)
    servo(5, p ? OPEN_FINGER : CLOSE_FINGER, ms)
}

function poseForMode(m: number) {
    if (m == 1) fingers(true, true, true, true, true, 400)
    else if (m == 2) fingers(false, true, true, false, false, 400)
    else fingers(false, false, false, false, false, 400)
    servo(6, m == 4 ? WRIST_LOCK : WRIST_CENTER, 500)
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
    if (!linkOk) setColor(80, 0, 80, StartbitRGBColors.Violet)
    else if (help) setColor(0, 0, 255, StartbitRGBColors.Blue)
    else if (mode == 1) setColor(0, 255, 0, StartbitRGBColors.Green)
    else if (mode == 2) setColor(255, 160, 0, StartbitRGBColors.Yellow)
    else setColor(255, 0, 0, StartbitRGBColors.Red)
}

function beep(freq: number, ms: number) {
    control.inBackground(function () {
        music.playTone(freq, ms)
    })
}

function showState() {
    if (!linkOk) basic.showString("?")
    else if (help) basic.showString("H")
    else if (danger == 2) basic.showIcon(IconNames.No)
    else if (danger == 1) basic.showString("!")
    else basic.showNumber(mode)
}

// ---------------- 라디오 ----------------
radio.onReceivedValue(function (name: string, value: number) {
    let changed = false
    if (name == "mode") {
        lastLinkMs = control.millis()
        if (!linkOk) { linkOk = true; changed = true }
        if (value >= 1 && value <= 4 && value != mode) { mode = value; changed = true }
    } else if (name == "help") {
        let h = value == 1
        if (h != help) { help = h; changed = true }
    } else if (name == "dng") {
        if (value != danger) {
            if (value == 2) beep(1200, 600)       // 정지 거리 진입 경고
            danger = value
            changed = true
        }
    }
    if (changed) {
        updateLed()
        showState()
    }
})

// ---------------- 신호 감시 + 잠금 깜빡임 ----------------
basic.forever(function () {
    if (linkOk && control.millis() - lastLinkMs > LINK_TIMEOUT_MS) {
        linkOk = false
        updateLed()
        showState()
        beep(330, 400)
    }
    if (linkOk && !help && mode == 4) {
        blinkOn = !blinkOn
        if (blinkOn) setColor(255, 0, 0, StartbitRGBColors.Red)
        else ledOff()
    }
    basic.pause(400)
})

// ---------------- 손 동작 루프 (서보는 이 루프만 움직임) ----------------
basic.forever(function () {
    if (linkOk && help) {
        // 도움 요청: 손가락을 하나씩 굽혔다 펴며 흔들기 + 2초마다 호출음
        if (posedKey != 200) {
            fingers(true, true, true, true, true, 300)
            servo(6, WRIST_CENTER, 300)
            posedKey = 200
        }
        let f = wiggleStep % 5 + 1
        let bent = Math.idiv(wiggleStep, 5) % 2 == 0
        if (f == 1) servo(1, bent ? CLOSE_THUMB : OPEN_THUMB, 150)
        else servo(f, bent ? CLOSE_FINGER : OPEN_FINGER, 150)
        wiggleStep = (wiggleStep + 1) % 10
        if (control.millis() - lastCallMs > 2000) {
            lastCallMs = control.millis()
            beep(988, 200)
            control.inBackground(function () {
                basic.pause(250)
                music.playTone(784, 300)
            })
        }
        basic.pause(180)
    } else if (linkOk && danger == 1) {
        // 주의: "멈춰" 손짓
        if (posedKey != 100) {
            fingers(true, true, true, true, true, 300)
            posedKey = 100
        }
        waveLeft = !waveLeft
        servo(6, WRIST_CENTER + (waveLeft ? -WAVE : WAVE), 350)
        beep(880, 100)
        basic.pause(400)
    } else {
        // 평소: 모드 자세 (신호 끊김이면 주먹)
        let key = linkOk ? mode : 3
        if (posedKey != key) {
            poseForMode(key)
            posedKey = key
        }
        basic.pause(100)
    }
})
