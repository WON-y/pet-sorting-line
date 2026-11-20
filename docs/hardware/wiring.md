# 배선

> 배선을 확정하면 사진과 함께 이 문서를 채운다. 핀 배치 초안: `safety/README.md`

## 전원 (safety_rules.md 3절)

```
12V 5A 어댑터(5.5×2.1, 센터 +) → DC 잭 단자(WS6) → 비상정지 HX19-B6(b접점, 직렬) → 릴레이(NO) → TB6600 VCC / GND
```

## 신호

```
게이트웨이 micro:bit P0 ─────────────────▶ 우노 D2 (DANGER)
게이트웨이 micro:bit P1 ─────────────────▶ 우노 D3 (HEARTBEAT)
게이트웨이 micro:bit P2 ◀──┬── 1kΩ ────── 우노 D4 (STATE, 5V)
                           │
                          2kΩ
                           │
                          GND
micro:bit GND ◀──────────────────────────▶ 우노 GND
```

분압: 5V × 2kΩ / (1kΩ + 2kΩ) ≈ 3.3V가 micro:bit P2로 들어간다.

## 확인 목록

- [ ] HX19-B6가 b접점인지
- [ ] 어댑터 극성(센터 +)과 DC 잭 단자 +/− 연결
- [ ] TB6600 딥스위치 전류 = 모터 정격 이하
- [ ] 우노와 micro:bit GND 공통
