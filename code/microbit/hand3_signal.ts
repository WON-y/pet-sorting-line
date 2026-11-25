// =====================================================================
//  신호 손 (지시) - 손 3
//  - WonderCam 특징 학습으로 작업자 수신호를 읽어 모드를 정하고 라디오로 전송
//    (aihand-factory T7 v3 수신호 인식을 옮겨 옴, 2026-11-25)
//  - 숫자 카드 인식으로 바꿔 쓸 수 있음 (로고 길게 누르기). 카드 5 = 도움 요청
//  - 손가락으로 모드를 복창(사람 수신호를 그대로 따라 함), 초음파로 작업자 접근 감지
//  - 이 손이 모드의 "기준"이다. 0.3초마다 모드를 다시 보내고(살아 있음 신호),
//    이 신호가 끊기면 다른 손과 벨트는 스스로 멈춘다.
//  필요한 확장: https://github.com/Hiwonder/StartbitV2
//              https://github.com/Hiwonder/WonderCam
// =====================================================================
//
//  WonderCam 특징 학습(본체에서 미리 학습, 카메라 높이·거리를 시연 때와 같게):
//    ID 1 = OK 사인        → 1 자동
//    ID 2 = 손가락 2개(V)  → 2 저속
//    ID 3 = 주먹           → 3 일시 정지
//    ID 4 = 손바닥 활짝    → 4 점검 잠금
//    ID 5 = 빈 배경, ID 6·7 = 사람만 서 있음(선택) → "없음"으로 처리
//  카메라는 작업대(화이트보드)를 내려다보게 고정해 몸이 화면에 안 들어오게 한다.
//
//  올라가기(→ 자동·저속, 정지에서 출발 또는 저속 → 자동):
//    ① 같은 수신호를 3초 유지, 그 동안 프레임 80% 이상 → ② 접근 위험이 없을 때만
//    → ③ 재가동 예고 3초 (노랑, LED 3·2·1, 손가락 3→2→1개, 삐) → 모드 변경·전송
//    ①·③ 중 주먹·활짝·A 버튼·사람 접근이면 바로 취소
//  내려가기(자동 → 저속), 일시 정지: 약 0.5초 연속이면 즉시. 점검 잠금: 약 1초 연속.

// ---------------- 설정 (★ 표시는 실물에 맞춰 꼭 확인) ----------------
const RADIO_GROUP = 73       // ★ 손 4대 + 게이트웨이 모두 같은 값

// 접근 거리 (mm). 초음파 시험 뒤 확정
const WARN_MM = 400          // ★ 주의: "멈춰" 손짓 + 경고음
const STOP_MM = 200          // ★ 정지: 일시 정지(모드 3)로 전환
const WARN_CONFIRM = 3       // 주의는 연속 n번 감지해야 인정 (오경보 필터)
                             // 정지는 1번만 감지해도 즉시 멈춤

// 인식 (T7 v3 값)
const CONF = 0.5             // ★ 이 신뢰도 이상만 인정 (T7: 틀릴 때도 0.8~0.9라 이것만으로는 못 거름)
const NEED = 5               // 같은 번호 연속 n프레임이면 확정 (약 0.5초)
const LOCK_NEED = 10         // 점검 잠금(4)은 오인식 대비 더 길게 (약 1초)
const PERIOD = 80            // 읽기 간격 ms (읽기 자체 시간 포함 약 0.1초)
const EMPTY_ID = 5           // 특징 학습에서 "빈 배경"으로 학습한 ID (6·7도 "없음")
const HOLD_MS = 3000         // 올라가기 유지 시간
const HOLD_PCT = 80          // 유지 시간 동안 같은 수신호 프레임 비율(%) 기준
const COUNT_MS = 3000        // 재가동 예고(카운트다운) 시간

// 손 자세
const WRIST_CENTER = 90
const WRIST_LOCK = 170       // ★ 점검 잠금 표시용 손목 각도 (손 4와 같게)
const WAVE = 30              // "멈춰" 손짓 좌우 흔들기 폭
const OPEN_THUMB = 50
const CLOSE_THUMB = 130
const OPEN_FINGER = 130
const CLOSE_FINGER = 50

// ---------------- 약속 (모든 프로그램 공통) ----------------
// 모드: 1 자동, 2 저속, 3 일시 정지, 4 점검 잠금
// 도움 요청은 모드와 별개 (카드 5 또는 로고 터치, 벨트·작업 손은 그대로)
// 라디오: "mode"=1~4, "help"=0/1, "dng"=0 정상/1 주의/2 정지거리

// ---------------- 상태 ----------------
let mode = 3                 // 켜지면 일시 정지로 시작 → 수신호 1·2로 출발
let help = false
let danger = 0
let src = 0                  // 0 = 수신호(특징 학습), 1 = 숫자 카드
let warnHits = 0
let posedKey = -1
let waveLeft = false
let blinkOn = false

let cand = 0                 // 지금 연속으로 보이는 번호 (0 = 없음)
let candN = 0
let candStart = 0
let last = 0                 // 마지막으로 확정한 번호 (계속 보여 줘도 한 번만 반응)
let hold = 0                 // 3초 유지 확인 중인 목표 모드 (1·2), 0이면 없음
let holdStart = 0
let holdHit = 0
let holdTotal = 0
let holdCol = 0
let count = 0                // 재가동 예고 중인 목표 모드 (1·2), 0이면 없음
let countStart = 0
let countN = 0               // 예고 남은 초 (3·2·1), 손 동작 루프가 손가락으로 보여 줌

// ---------------- 시작 (라디오·버튼 처리보다 먼저) ----------------
StartbitV2.startbit_Init()
wondercam.wondercam_init(wondercam.DEV_ADDR.x32)   // 카메라가 없으면 "E"를 띄우며 기다림
setSrc(0)
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

// 사람 수신호를 그대로 따라 함 (손 4도 같은 자세)
function poseForMode(m: number) {
    if (m == 1) fingers(false, false, true, true, true, 400)        // OK 사인 (엄지·검지 접고 3·4·5 폄)
    else if (m == 2) fingers(false, true, true, false, false, 400)  // 손가락 2개 (V)
    else if (m == 4) fingers(true, true, true, true, true, 400)     // 손바닥 활짝
    else fingers(false, false, false, false, false, 400)            // 주먹 (3)
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
    if (count != 0) setColor(255, 160, 0, StartbitRGBColors.Yellow)  // 재가동 예고
    else if (mode == 1) setColor(0, 255, 0, StartbitRGBColors.Green)
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

// 모드를 바꾸면 진행 중인 올라가기(유지 확인·예고)는 끝낸다
function setMode(m: number) {
    hold = 0
    count = 0
    if (m == mode) { updateLed(); basic.showNumber(mode); return }
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

// 3초 유지·재가동 예고를 그만둠 (모드는 그대로)
function cancelUp() {
    if (hold == 0 && count == 0) return
    hold = 0
    count = 0
    updateLed()
    reject()
}

// ---------------- 입력 바꾸기 (수신호 ↔ 숫자 카드) ----------------
function setSrc(s: number) {
    src = s
    wondercam.ChangeFunc(src == 0 ? wondercam.Functions.FeatureLearning : wondercam.Functions.NumberRecognition)
    cand = 0; candN = 0; last = 0
    hold = 0; count = 0
}

// 한 프레임 읽기 → 번호 1~5 (0 = 없음)
function readOnce(): number {
    wondercam.UpdateResult()
    let id = 0
    let conf = 0
    if (src == 0) {
        id = wondercam.FlMaxConfidenceID()
        conf = wondercam.FlMaxConfidence()
        if (id == EMPTY_ID || id > 5) id = 0       // 빈 배경·사람만 서 있음·쓰지 않는 ID
    } else {
        id = wondercam.NumberWithMaxConfidence()
        conf = wondercam.MaxConfidenceOfNumber()
        if (id < 1 || id > 5) id = 0
    }
    return conf >= CONF ? id : 0
}

// ---------------- 확정된 번호 처리 ----------------
function onCommand(c: number) {
    if (c == 5) {                              // 도움 요청 (카드 5): 잠금 중에도 가능
        setHelp(true)
        beep(988, 150)
        return
    }
    if (mode == 4) { reject(); return }        // 점검 잠금 중에는 수신호·카드로 못 바꿈 (A+B로 해제)
    if (c == 3 || c == 4) {                    // 일시 정지·점검 잠금: 즉시
        setHelp(false)
        setMode(c)
        beep(c == 3 ? 523 : 330, 600)
        return
    }
    // c == 1 또는 2
    if (c == 2 && mode == 1) {                 // 내려가기 = 즉시
        setHelp(false)
        setMode(2)
        beep(880, 120)
        return
    }
    if (c == mode || c == count || c == hold) return
    if (danger != 0) { reject(); return }      // 사람이 가까이 있으면 출발 금지
    // 올라가기 = 3초 유지 확인 시작. 이미 연속으로 본 NEED 프레임도 셈
    hold = c; holdStart = candStart; holdHit = NEED; holdTotal = NEED; holdCol = 0
    count = 0
    basic.clearScreen()
}

// ---------------- 인식 루프 ----------------
basic.forever(function () {
    let id = readOnce()
    let now = control.millis()
    if (id == cand) candN++
    else { cand = id; candN = 1; candStart = now }

    // ① 3초 유지 확인 (LED 막대가 0.6초마다 한 칸씩 참)
    if (hold != 0) {
        holdTotal++
        if (id == hold) holdHit++
        let el = now - holdStart
        let col = Math.min(5, Math.idiv(el * 5, HOLD_MS))
        while (holdCol < col) {
            for (let y = 0; y < 5; y++) led.plot(holdCol, y)
            holdCol++
            beep(880, 40)
        }
        if (el >= HOLD_MS) {
            let pct = Math.idiv(holdHit * 100, holdTotal)
            let h = hold
            hold = 0
            if (pct >= HOLD_PCT && danger == 0) {
                count = h; countStart = now; countN = 0     // ③ 재가동 예고 시작
                updateLed()
            } else {
                reject()                                    // 80% 못 넘음 또는 사람 접근
                last = 0; cand = 0; candN = 0               // 계속 보이고 있으면 처음부터 다시 셈
            }
        }
    }

    // ③ 재가동 예고: 1초마다 3·2·1, 끝나면 모드 변경. 사람이 오면 취소
    if (count != 0) {
        let n = Math.idiv(COUNT_MS, 1000) - Math.idiv(now - countStart, 1000)
        if (danger != 0) {
            cancelUp()
        } else if (n <= 0) {
            let m = count
            setHelp(false)
            setMode(m)
            beep(880, 120)
        } else if (n != countN) {
            countN = n
            basic.showNumber(n)
            beep(988, 80)
        }
    }

    // 확정: 같은 번호가 NEED(잠금은 LOCK_NEED)프레임 연속
    let need = cand == 4 ? LOCK_NEED : NEED
    if (candN == need) {
        if (cand == 0) last = 0                   // 치웠음 → 같은 번호를 다시 보이면 다시 반응
        else if (cand != last) { last = cand; onCommand(cand) }
    }
    basic.pause(PERIOD)
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
    if (newDanger == 2) {
        hold = 0
        count = 0
        if (mode != 4 && mode != 3) {
            setMode(3)                  // 정지: 사람이 물러나도 스스로 다시 돌지 않음
            beep(1200, 600)
        }
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
    } else if (count != 0 && countN > 0) {
        // 재가동 예고: 손가락 3→2→1개
        let key = 300 + countN
        if (posedKey != key) {
            fingers(false, true, countN >= 2, countN >= 3, false, 200)
            servo(6, WRIST_CENTER, 300)
            posedKey = key
        }
        basic.pause(100)
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
// A: 즉시 일시 정지 (수신호 없이 급히 멈출 때). 올라가기·예고 중이면 취소
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
// A+B: 점검 잠금 해제 → 일시 정지(3). 출발은 다시 수신호 1·2로
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
// 로고 길게 누르기: 입력 바꾸기 (수신호 F ↔ 숫자 카드 N). 바꾸면 진행 중인 올라가기는 취소
input.onLogoEvent(TouchButtonEvent.LongPressed, function () {
    setSrc(1 - src)
    basic.showString(src == 0 ? "F" : "N")
    updateLed()
    basic.showNumber(mode)
})
