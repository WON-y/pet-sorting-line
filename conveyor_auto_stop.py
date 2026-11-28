"""
병이 판정 구역에 완전히 들어오면 '자동으로' 정지 신호('s')를 보내고,
병 부분만 잘라서 best.pt로 판정해 화면에 표시하는 코드.

- 저장소(pet-sorting-line) 맨 위 폴더에서 실행:  py conveyor_auto_stop.py
- DRY_RUN = True  : 아두이노 없이 실행 (보낼 신호는 터미널에만 출력)
- SOURCE          : 웹캠 번호(0, 1...) 또는 영상 파일 경로 r"C:\\...\\test.mp4"

사용 순서 (영상 창 'conveyor'를 클릭한 상태에서, 영어 입력):
  1) o : 판정 구역 드래그 후 Enter
  2) b : 빈 벨트 기준 사진 저장 (병·손 없을 때)  → 이때부터 자동 감지 시작
  3) r : 벨트 출발 (실제 연결 시 첫 출발은 사람이 직접)
  이후 병이 들어오면 자동 정지 → 판정 → (AUTO_RESUME이면 자동 재출발)
  → 병이 구역을 빠져나가면 다음 병 감지
  s = 수동 정지, q = 종료, 스페이스 = 영상 일시정지(영상 파일일 때)
"""

import os
import time

import cv2
import numpy as np
from PIL import Image
from ultralytics import YOLO

# ===== 설정 =====
DRY_RUN = True
SOURCE = r"C:\Users\chaew\Downloads\1126_test_3.mp4"
BAUD = 9600
WEIGHTS = "training/weights/best.pt"
ROI = None                       # 판정 구역 [x1, y1, x2, y2]. 실행 중 o 키로 지정
IMGSZ = 224
LETTERBOX_COLOR = (114, 114, 114)
CAM_SIZE = (1920, 1080)          # 웹캠 해상도 요청 (지원 안 하면 무시됨)

DIFF_THRESH = 40                 # 기준 사진과 밝기 차이가 이 값 이상이면 '변한 픽셀'
MIN_AREA_FRAC = 0.03             # 구역 대비 이 비율 이상 크기의 덩어리만 물체로 봄
EDGE_MARGIN = 10                 # 물체가 구역 가장자리에서 이 픽셀 이상 떨어져야 '완전히 들어옴'
STABLE_FRAMES = 5                # 완전히 들어온 상태가 연속 몇 프레임이면 정지할지
CLEAR_FRAMES = 10                # 판정 후 구역이 이 프레임 동안 비어야 다음 병 감지

SETTLE_SEC = 0.4                 # 정지 후 판정 사진을 찍기까지 기다리는 시간 (흔들림 방지)
CROP_MARGIN = 0.20               # 병 박스 주변 여백 (AI Hub 자르기와 비슷하게, 투명 병은 넉넉히)
AUTO_RESUME = False              # True: 판정 후 RESUME_DELAY 초 뒤 자동으로 벨트 재출발
RESUME_DELAY = 2.0
SAVE_DIR = "captures"            # 판정한 사진 저장 폴더 (원본 + 잘라낸 사진). None이면 저장 안 함
# ================

ser = None
if not DRY_RUN:
    import serial
    import serial.tools.list_ports

    def find_port():
        for p in serial.tools.list_ports.comports():
            d = (p.description or "") + " " + (p.manufacturer or "")
            if p.device.startswith("COM") and ("Arduino" in d or "CH340" in d or "USB" in d):
                return p.device                                   # Windows
            if p.device.startswith("/dev/cu.") and ("usbmodem" in p.device or "usbserial" in p.device):
                return p.device                                   # macOS
            if p.device.startswith(("/dev/ttyACM", "/dev/ttyUSB")):
                return p.device                                   # Linux
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
    raise RuntimeError(f"영상을 열 수 없습니다: {SOURCE}")
IS_FILE = isinstance(SOURCE, str)
if not IS_FILE:
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAM_SIZE[0])
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAM_SIZE[1])
    print("웹캠 해상도:", int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), "x", int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
WAIT_MS = 30 if IS_FILE else 1
if SAVE_DIR:
    os.makedirs(SAVE_DIR, exist_ok=True)


def to_gray_blur(img_bgr):
    return cv2.GaussianBlur(cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY), (9, 9), 0)


def roi_crop(frame):
    if ROI is None:
        return frame
    x1, y1, x2, y2 = ROI
    return frame[y1:y2, x1:x2]


def analyze(region, baseline):
    """반환: (완전히 들어왔는가, 마스크, 물체 박스(구역 좌표) 또는 None, 상태 글자)"""
    g = to_gray_blur(region).astype(np.int16)
    g += int(baseline.mean() - g.mean())                     # 자동 노출로 전체 밝기 변하는 것 보정
    diff = np.abs(g - baseline.astype(np.int16))
    mask = (diff > DIFF_THRESH).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    mask = cv2.dilate(mask, np.ones((21, 21), np.uint8))     # 투명 병 조각 합치기
    h, w = mask.shape
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    big = [c for c in contours if cv2.contourArea(c) >= MIN_AREA_FRAC * w * h]
    if not big:
        return False, mask, None, "no object"
    box = cv2.boundingRect(np.vstack(big))                   # 조각들을 모두 감싸는 박스 = 병 전체
    x, y, bw, bh = box
    if x <= EDGE_MARGIN or y <= EDGE_MARGIN or x + bw >= w - EDGE_MARGIN or y + bh >= h - EDGE_MARGIN:
        return False, mask, box, "touching edge"
    return True, mask, box, "FULLY INSIDE"


def letterbox(img, size=IMGSZ, color=LETTERBOX_COLOR):
    w, h = img.size
    s = size / max(w, h)
    nw, nh = max(1, round(w * s)), max(1, round(h * s))
    canvas = Image.new("RGB", (size, size), color)
    canvas.paste(img.resize((nw, nh), Image.BILINEAR), ((size - nw) // 2, (size - nh) // 2))
    return canvas


def crop_bottle(frame_bgr, box_in_frame):
    """병 박스 + 여백의 정사각형으로 잘라 224 레터박스 (AI Hub 자르기와 같은 방식)."""
    H, W = frame_bgr.shape[:2]
    x, y, bw, bh = box_in_frame
    side = max(bw, bh) * (1 + 2 * CROP_MARGIN)
    cx, cy = x + bw / 2, y + bh / 2
    x1, y1 = int(max(0, cx - side / 2)), int(max(0, cy - side / 2))
    x2, y2 = int(min(W, cx + side / 2)), int(min(H, cy + side / 2))
    rgb = cv2.cvtColor(frame_bgr[y1:y2, x1:x2], cv2.COLOR_BGR2RGB)
    return letterbox(Image.fromarray(rgb))


def classify(frame_bgr, box_in_frame):
    if box_in_frame is not None:
        img = crop_bottle(frame_bgr, box_in_frame)
    else:                                                    # 박스를 못 찾으면 구역 전체로 판정
        img = letterbox(Image.fromarray(cv2.cvtColor(roi_crop(frame_bgr), cv2.COLOR_BGR2RGB)))
    r = model.predict(img, imgsz=IMGSZ, verbose=False)[0]
    return model.names[int(r.probs.top1)], float(r.probs.top1conf), img


# 상태: IDLE(기준 사진 없음) → ARMED(감지 중) → SETTLING(정지 후 대기) → JUDGED(판정 끝, 병 나가길 기다림)
state = "IDLE"
belt_running = False
hit_count = clear_count = 0
settle_at = resume_at = None
last_result = ""
baseline = None
paused = False
frame = None

print("o: 구역 선택 / b: 빈 벨트 기준 저장(자동 감지 시작) / r: 벨트 출발 / s: 정지 / q: 종료")

while True:
    if not paused or frame is None:
        ok, frame = cap.read()
        if not ok:
            if IS_FILE:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                continue
            print("웹캠 영상을 읽지 못해 종료합니다.")
            break

    region = roi_crop(frame)
    show = frame.copy()
    ox, oy = (ROI[0], ROI[1]) if ROI is not None else (0, 0)
    if ROI is not None:
        cv2.rectangle(show, (ROI[0], ROI[1]), (ROI[2], ROI[3]), (255, 255, 0), 2)

    detect_text, box_f = "", None
    if baseline is not None and baseline.shape == to_gray_blur(region).shape:
        inside, mask, box, detect_text = analyze(region, baseline)
        cv2.imshow("mask", mask)
        if box is not None:
            x, y, bw, bh = box
            box_f = (ox + x, oy + y, bw, bh)
            cv2.rectangle(show, (ox + x, oy + y), (ox + x + bw, oy + y + bh), (0, 255, 255), 2)

        if state == "ARMED":
            hit_count = hit_count + 1 if inside else 0
            if hit_count >= STABLE_FRAMES:
                send("s")
                belt_running = False
                hit_count = 0
                state, settle_at = "SETTLING", time.time() + SETTLE_SEC
                print("물체 감지 -> 자동 정지")

        elif state == "SETTLING" and time.time() >= settle_at:
            name, conf, crop = classify(frame, box_f)
            last_result = f"{name} ({conf:.2f})"
            print("판정:", last_result)
            cv2.imshow("crop", cv2.cvtColor(np.array(crop), cv2.COLOR_RGB2BGR))
            if SAVE_DIR:
                stamp = time.strftime("%Y%m%d_%H%M%S")
                cv2.imwrite(f"{SAVE_DIR}/{stamp}_full.jpg", frame)
                crop.save(f"{SAVE_DIR}/{stamp}_crop_{name}.jpg")
            state, clear_count = "JUDGED", 0
            resume_at = time.time() + RESUME_DELAY if AUTO_RESUME else None

        elif state == "JUDGED":
            # 판정한 병이 구역을 빠져나갈 때까지 다음 감지를 하지 않음
            clear_count = clear_count + 1 if detect_text == "no object" else 0
            if clear_count >= CLEAR_FRAMES:
                state, hit_count = "ARMED", 0
                print("구역 비었음 → 다음 병 감지 시작")

    if resume_at is not None and time.time() >= resume_at:
        send("r")
        belt_running, resume_at = True, None
        print("자동 재출발")

    label = {"IDLE": "PRESS o then b (empty belt)", "ARMED": "ARMED (auto stop on)",
             "SETTLING": "STOPPING...", "JUDGED": "JUDGED - waiting bottle to leave"}[state]
    color = {"IDLE": (0, 165, 255), "ARMED": (0, 255, 0), "SETTLING": (0, 0, 255), "JUDGED": (255, 0, 255)}[state]
    belt = "BELT ON" if belt_running else "BELT OFF"
    cv2.putText(show, f"{label} | {belt}" + ("  [DRY RUN]" if DRY_RUN else ""), (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
    if detect_text:
        cv2.putText(show, f"{detect_text}  hit {hit_count}/{STABLE_FRAMES}", (10, 65),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 0), 2)
    if last_result:
        cv2.putText(show, last_result, (10, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
    cv2.imshow("conveyor", show)

    key = cv2.waitKey(WAIT_MS) & 0xFF
    if key == ord("o"):
        send("s")
        belt_running, resume_at = False, None
        sel = cv2.selectROI("conveyor", frame, showCrosshair=False)
        if sel[2] > 0 and sel[3] > 0:
            ROI = [int(sel[0]), int(sel[1]), int(sel[0] + sel[2]), int(sel[1] + sel[3])]
            baseline, state = None, "IDLE"
            try:
                cv2.destroyWindow("mask")
            except cv2.error:
                pass
            print("구역:", ROI, "-> 빈 벨트가 보일 때 b를 누르세요.")
    elif key == ord("b"):
        baseline = to_gray_blur(region)
        state, hit_count = "ARMED", 0
        print("기준 사진 저장 → 자동 감지 시작")
    elif key == ord("r"):
        send("r")
        belt_running, resume_at = True, None
        if state == "JUDGED":
            print("벨트 출발 (판정한 병이 나가면 다음 감지)")
        else:
            print("벨트 출발")
    elif key == ord("s"):
        send("s")
        belt_running, resume_at = False, None
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
