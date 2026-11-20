## 무엇을 바꿨나요

<!-- 요구사항 ID를 꼭 적어 주세요 (예: R4, S8, N10) -->
- 관련 ID:
- 내용:

## 확인

- [ ] 규격(`docs/spec/`)과 맞다. 규격을 바꿨다면 같은 PR에서 문서 → `common/protocol.py` → 시험을 함께 고쳤다
- [ ] `ruff check .`, `pytest` 통과
- [ ] 바꾼 모듈의 `README.md` / `CONTAINER.md`를 고쳤다
- [ ] 개인정보·사진·영상·`.env`를 올리지 않았다

## 안전 체크리스트 (`safety/`, 정지·하트비트·핀 관련을 바꿨다면 모두 필수)

- [ ] `docs/spec/safety_rules.md`를 다시 읽었다
- [ ] 정지 경로에 노트북·도커·MQTT·YOLO·손짓이 들어가지 않는다
- [ ] 선이 빠지거나 신호가 끊기면 정지로 읽힌다
- [ ] 켜진 직후 상태가 STOP이다
- [ ] 실제 하드웨어로 정지 시험 N1~N5를 했고 `docs/tests/kpi_log.md`에 기록했다
