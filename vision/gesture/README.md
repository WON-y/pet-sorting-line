# 비전: 손짓 인식 (R6, 노트북 MediaPipe)

- 실행 위치: 노트북 (판정용과 다른 웹캠, `settings.yaml: gesture.camera_index`)
- 켜기: `gesture.enabled: true`
- **정지에 쓰지 않는다.** 손짓은 저속·점검 잠금·재가동 확인 같은 일부러 내리는 지시에만.

## 규칙 (`gesture.py`)

| 펴진 손가락 | 모드 |
| --- | --- |
| 1 | 1 자동 (재가동 확인용, 리셋 버튼 필요) |
| 2 | 2 저속 |
| 4 | 4 점검 잠금 |
| 그 밖 | 무시 |

- 같은 손짓이 `gesture.confirm_frames`(10) 프레임 연속이어야 확정 (`GestureConfirmer`)
- 확정되면 app이 게이트웨이로 `M<n>`을 보내 손 3·4가 복창한다 (카드와 같은 경로).

## 개인정보

손·얼굴이 찍힌 사진·영상은 깃허브에 올리지 않는다 (`docs/spec/data_and_logging.md` 5절).

## 할 일

- [ ] `count_fingers`: 엄지 처리, 왼손/오른손 구분
- [ ] app 루프에 손짓 카메라 연결 (`app/main.py`, 지금은 TODO)
- [ ] 오인식 시험: 작업 중 손 움직임이 모드로 잘못 확정되는지
