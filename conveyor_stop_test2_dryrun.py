"""
conveyor_stop_test2.py 의 '아두이노·컨베이어 없이' 시험용 버전.
병이 판정 구역에 완전히 들어오면 정지 신호('s')를 보낼 시점을 화면/터미널에 표시하고,
그 병을 best.pt(분류 모델)로 판정해서 화면에 표시한다.

- 저장소(pet-sorting-line) 맨 위 폴더에 넣고 그 폴더에서 실행:  python3 conveyor_stop_test2_dryrun.py
- DRY_RUN = True 이면 아두이노 없이 실행 (보낼 신호는 터미널에 출력만)
- SOURCE = 0(웹캠/휴대폰 웹캠 앱) 또는 "test.mp4"(휴대폰으로 찍은 영상)

컨베이어 없이 시험하는 방법:
  책상 위에 벨트 대신 색지를 깔고 카메라를 위에서 내려다보게 둔다.
  o(영역 선택) → b(빈 바닥 기준 저장) → r(시작)
  병을 자나 막대로 밀어서 구역 안에 넣고, 손·막대를 화면 밖으로 빼면
  5프레임 뒤 '[보낼 신호] s' 와 판정 결과가 나오면 정상.

키(영상 창 'conveyor'를 클릭한 상태에서, 영어 입력):
  o = 영역 드래그 후 Enter, b = 빈 바닥 기준 저장, r = 시작, s = 수동 정지, q = 종료
"""

import time

import cv2
import numpy as np
from PIL import Image
from ultralytics import YOLO

from vision.bottle.preprocess import prepare  # 학습 때와 같은 전처리 (회색 레터박스)

# ===== 설정 =====
DRY_RUN = True                         # True: 아두이노 없이 실행
SOURCE = r"C:\Users\chaew\Downloads\1126_test_3.mp4"                             # 웹캠 번호(0, 1, 2...) 또는 영상 파일 경로 "test.mp4"
BAUD = 9600
WEIGHTS = "training/weights/best.pt"
ROI = None                             # 판정 구역 [x1, y1, x2, y2]. 실행 중 o 키로 지정 가능
IMGSZ = 224
LETTERBOX_COLOR = (114, 114, 114)

DIFF_THRESH = 40
MIN_AREA_FRAC = 0.03
EDGE_MARGIN = 10
STABLE_FRAMES = 5
# ================

ser = None
if not DRY_RUN:
    import serial
    import serial.tools.list_ports

    def find_port():
        for p in serial.tools.list_ports.comports():
            if p.device.startswith("/dev/cu.") and ("usbmodem" in p.device or "usbserial" in p.device):
                return p.device
        raise RuntimeError("아두이노 포트를 찾을 수 없습니다. USB 연결을 확인하세요.")

    port = find_port()
    print("아두이노 포트:", port)
    ser = serial.Serial(port, BAUD, timeout=0.1)
    time.sleep(2)
else:
    print("DRY_RUN: 아두이노 없이 실행 (신호는 터미널에만 출력)")


def send(cmd):
    if ser is None:
        print("[보낼 신호]", cmd)
    else:
        ser.write(cmd.encode())


model = YOLO(WEIGHTS)
print("모델 클래스:", model.names)
cap = cv2.VideoCapture(SOURCE)
if not cap.isOpened():
    raise RuntimeError(f"영상을 열 수 없습니다: {SOURCE} (웹캠 번호·파일 경로·카메라 권한 확인)")
IS_FILE = isinstance(SOURCE, str)
WAIT_MS = 30 if IS_FILE else 1        # 영상 파일은 너무 빨리 지나가지 않게


def to_gray_blur(img_bgr):
    return cv2.GaussianBlur(cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY), (9, 9), 0)


def roi_crop(frame):
    if ROI is None:
        return frame
    x1, y1, x2, y2 = ROI
    return frame[y1:y2, x1:x2]


def analyze(region, baseline):
    g = to_gray_blur(region).astype(np.int16)
    g += int(baseline.mean() - g.mean())
    diff = np.abs(g - baseline.astype(np.int16))
    mask = (diff > DIFF_THRESH).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    mask = cv2.dilate(mask, np.ones((21, 21), np.uint8))
    h, w = mask.shape
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    big = [c for c in contours if cv2.contourArea(c) >= MIN_AREA_FRAC * w * h]
    if not big:
        return False, mask, None, "no object"
    largest = max(big, key=cv2.contourArea)
    box = cv2.boundingRect(largest)
    for c in big:
        x, y, bw, bh = cv2.boundingRect(c)
        if x <= EDGE_MARGIN or y <= EDGE_MARGIN or x + bw >= w - EDGE_MARGIN or y + bh >= h - EDGE_MARGIN:
            return False, mask, box, "touching edge"
    return True, mask, box, "FULLY INSIDE"


def classify(frame_bgr):
    rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    img = prepare(Image.fromarray(rgb), ROI, IMGSZ, LETTERBOX_COLOR)
    r = model.predict(img, imgsz=IMGSZ, verbose=False)[0]
    return model.names[int(r.probs.top1)], float(r.probs.top1conf)


baseline = None
running = False
hit_count = 0
last_result = ""
paused = False
frame = None

print("o: 영역 선택 / b: 빈 바닥 기준 저장 / r: 시작 / s: 정지 / q: 종료"
      + (" / 스페이스: 영상 일시정지" if IS_FILE else ""))

while True:
    if not paused or frame is None:
        ok, frame = cap.read()
        if not ok:
            if IS_FILE:
                print("영상 끝 → 처음부터 다시 재생")
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                continue
            print("웹캠 영상을 읽지 못해 종료합니다.")
            break

    region = roi_crop(frame)
    show = frame.copy()
    ox, oy = (ROI[0], ROI[1]) if ROI is not None else (0, 0)
    if ROI is not None:
        cv2.rectangle(show, (ROI[0], ROI[1]), (ROI[2], ROI[3]), (255, 255, 0), 2)

    detect_text = ""
    if baseline is not None and baseline.shape == to_gray_blur(region).shape:
        inside, mask, box, detect_text = analyze(region, baseline)
        cv2.imshow("mask", mask)
        if box is not None:
            x, y, bw, bh = box
            cv2.rectangle(show, (ox + x, oy + y), (ox + x + bw, oy + y + bh), (0, 255, 255), 2)
        if running:
            hit_count = hit_count + 1 if inside else 0
            if hit_count >= STABLE_FRAMES:
                send("s")
                running = False
                hit_count = 0
                name, conf = classify(frame)
                last_result = f"{name} ({conf:.2f})"
                print("물체 감지 -> 정지 / 판정:", last_result)

    if baseline is None:
        status, color = "PRESS o (select area) then b (empty)", (0, 165, 255)
    elif running:
        status, color = "RUNNING", (0, 255, 0)
    else:
        status, color = "STOPPED (press r)", (0, 0, 255)
    cv2.putText(show, status + ("  [DRY RUN]" if DRY_RUN else ""), (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.9, color, 2)
    if detect_text:
        cv2.putText(show, f"{detect_text}  hit {hit_count}/{STABLE_FRAMES}", (10, 65),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 0), 2)
    if last_result:
        cv2.putText(show, last_result, (10, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
    cv2.imshow("conveyor", show)

    key = cv2.waitKey(WAIT_MS) & 0xFF
    if key == ord("o"):
        send("s")
        running = False
        sel = cv2.selectROI("conveyor", frame, showCrosshair=False)
        if sel[2] > 0 and sel[3] > 0:
            ROI = [int(sel[0]), int(sel[1]), int(sel[0] + sel[2]), int(sel[1] + sel[3])]
            baseline = None
            try:
                cv2.destroyWindow("mask")
            except cv2.error:
                pass
            print("영역:", ROI, "-> 빈 바닥이 보일 때 b를 누르세요.")
    elif key == ord("b"):
        baseline = to_gray_blur(region)
        print("기준 사진 저장")
    elif key == ord("r"):
        if baseline is None:
            print("먼저 빈 바닥이 보일 때 b를 눌러 기준 사진을 저장하세요.")
        else:
            send("r")
            running = True
            hit_count = 0
            last_result = ""
            print("시작")
    elif key == ord("s"):
        send("s")
        running = False
        print("수동 정지")
    elif key == ord(" ") and IS_FILE:
        paused = not paused
    elif key == ord("q"):
        break

send("s")
cap.release()
cv2.destroyAllWindows()
if ser is not None:
    ser.close()
