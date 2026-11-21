# 비전

| 폴더 | 기능 | 실행 위치 | 언어 | 정지에 쓰나 |
| --- | --- | --- | --- | --- |
| `bottle` | 페트병 판정 (YOLO 분류, R4) | 노트북 | Python | 아니오 |
| `card` | 숫자 카드 인식 (R6) | 손 3 micro:bit + WonderCam | MakeCode | 아니오 |
| `gesture` | 손짓 인식 (R6, MediaPipe) | 노트북 | Python | **아니오** |
| `webtest` | 휴대폰·웹캠 사진 인식 웹 테스트 (R4 시험용, `python -m vision.webtest`) | 노트북 | Python + HTML | 아니오 |

카드와 손짓은 같은 모드 번호(1·2·4)를 만든다. 둘 다 "일부러 내리는 지시"에만 쓰고, 정지는 센서로만 한다 (`docs/spec/safety_rules.md`).
