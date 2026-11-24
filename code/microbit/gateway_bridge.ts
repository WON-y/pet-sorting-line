// =====================================================================
//  게이트웨이 micro:bit (확장보드 없이 단독, 노트북 USB에 연결)
//  1) 라디오로 받은 모드 → 핀 P0·P1·P2 → 아두이노(컨베이어)
//  2) 노트북(YOLO)에서 USB 시리얼로 받은 판정 → 라디오로 작업 손 1·2에 전송
//  3) 라디오 상태 변화를 USB 시리얼로 노트북에 알림 (대시보드 기록용)
//  필요한 확장: 없음 (기본 radio만)
//
//  아두이노 배선 (악어클립 / 엣지 커넥터):
//    micro:bit P0  → 아두이노 D6  (모드 비트 0)
//    micro:bit P1  → 아두이노 D7  (모드 비트 1)
//    micro:bit P2  → 아두이노 D8  (살아 있음 신호, 0.1초마다 토글)
//    micro:bit GND → 아두이노 GND (반드시 연결)
//  모드 → (P1,P0): 자동 01, 저속 10, 일시 정지 00, 점검 잠금 11
//
//  노트북 → 게이트웨이 (115200bps, 한 줄씩):  J0 ~ J4
//    J0 재검사, J1 투명 적합, J2 내용물 남음, J3 라벨 있음, J4 유색·불투명
//  게이트웨이 → 노트북:  ACK,순번,판정 / MODE,n / HELP,0|1 / DNG,0|1|2 / LINK,OK|LOST
// =====================================================================

const RADIO_GROUP = 73       // ★ 손 4대와 같은 값
const LINK_TIMEOUT_MS = 1500 // 신호 손(3) 모드가 이 시간 안 오면 벨트 정지

let mode = 3
let help = 0
let danger = 0
let linkOk = false
let lastLinkMs = 0
let seq = randint(0, 998)    // 재부팅 뒤 첫 판정이 중복으로 버려지지 않게 무작위 시작
let hb = 0

// ---------------- 시작 ----------------
serial.redirectToUSB()
serial.setBaudRate(BaudRate.BaudRate115200)
radio.setGroup(RADIO_GROUP)
radio.setTransmitPower(7)
writeModePins(3)
basic.showString("?")

// ---------------- 아두이노로 모드 출력 ----------------
function writeModePins(m: number) {
    let b0 = 0
    let b1 = 0
    if (m == 1) { b0 = 1; b1 = 0 }        // 자동
    else if (m == 2) { b0 = 0; b1 = 1 }   // 저속
    else if (m == 4) { b0 = 1; b1 = 1 }   // 점검 잠금
    // 3 또는 그 밖: 00 = 정지
    pins.digitalWritePin(DigitalPin.P0, b0)
    pins.digitalWritePin(DigitalPin.P1, b1)
}

// 살아 있음 신호: 신호 손(3)과 연결돼 있을 때만 토글
basic.forever(function () {
    if (linkOk && control.millis() - lastLinkMs > LINK_TIMEOUT_MS) {
        linkOk = false
        writeModePins(3)
        serial.writeLine("LINK,LOST")
        basic.showString("?")
    }
    if (linkOk) {
        hb = 1 - hb
        pins.digitalWritePin(DigitalPin.P2, hb)
    }
    basic.pause(100)
})

// ---------------- 라디오 수신 ----------------
radio.onReceivedValue(function (name: string, value: number) {
    if (name == "mode") {
        lastLinkMs = control.millis()
        if (!linkOk) {
            linkOk = true
            serial.writeLine("LINK,OK")
            mode = -1                       // 아래에서 핀·화면 갱신
        }
        if (value >= 1 && value <= 4 && value != mode) {
            mode = value
            writeModePins(mode)
            serial.writeLine("MODE," + mode)
            basic.showNumber(mode)
        }
    } else if (name == "help") {
        if (value != help) {
            help = value
            serial.writeLine("HELP," + help)
        }
    } else if (name == "dng") {
        if (value != danger) {
            danger = value
            serial.writeLine("DNG," + danger)
        }
    }
})

// ---------------- 판정 보내기 ----------------
function sendJudgement(cls: number) {
    seq = seq % 999 + 1
    let v = seq * 10 + cls
    for (let k = 0; k < 3; k++) {          // 3번 반복 (손에서 순번으로 중복 제거)
        radio.sendValue("jdg", v)
        basic.pause(20)
    }
    serial.writeLine("ACK," + seq + "," + cls)
}

serial.onDataReceived(serial.delimiters(Delimiters.NewLine), function () {
    let line = serial.readUntil(serial.delimiters(Delimiters.NewLine)).trim()
    if (line.length == 2 && line.charAt(0) == "J") {
        let cls = parseInt(line.charAt(1))
        if (cls >= 0 && cls <= 4) {
            sendJudgement(cls)
            return
        }
    }
    serial.writeLine("ERR," + line)
})

// ---------------- 시험용 버튼 (노트북 없이 판정 흉내) ----------------
input.onButtonPressed(Button.A, function () { sendJudgement(4) })   // 유색 → 손 1 분기
input.onButtonPressed(Button.B, function () { sendJudgement(2) })   // 내용물 → 손 2 분기
input.onButtonPressed(Button.AB, function () { sendJudgement(1) })  // 적합 → 둘 다 통과
