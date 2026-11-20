# 통신

| 폴더 | 실행 위치 | 역할 |
| --- | --- | --- |
| `gateway_microbit` | 게이트웨이 micro:bit (노트북 USB에 꽂음) | 라디오 ↔ 노트북 시리얼, 아두이노 핀 신호(P0·P1·P2) |
| `serial_bridge` | 노트북 (Python) | 게이트웨이·우노 시리얼 연결, MQTT 발행 |

규격은 전부 `docs/spec/protocol.md`. 메시지를 바꾸면 규격 → `common/protocol.py` → `tests/test_protocol.py` 순서로.
