"""app 상태 머신 (docs/spec/modes_and_states.md 3·5절).

앞부분은 예전 방식(stop_to_judge: true, 판정할 때 멈춤), 뒷부분은 기본 방식(멈추지 않음).
"""
from app.controller import LineController
from common import protocol as p


def kinds(acts, kind):
    return [a for a in acts if a[0] == kind]


def running(**kw) -> LineController:
    kw.setdefault("stop_to_judge", True)
    c = LineController(settle_ms=100, resume_delay_ms=500, **kw)
    c.on_arduino(("EVT", "RUN"), 0)
    return c


def judge(c, cls="clear_nolabel", code="OK", t=200):
    assert c.on_detect(0) == [("arduino", "PAUSE")]
    assert c.tick(50) == []                      # 멈춘 뒤 settle_ms 기다림
    assert c.tick(100) == [("capture", c.bottle_id)]
    return c.on_decision(cls, code, 0.95, 1, t, {"img": "a.jpg", "full": "b.jpg"})


def test_camera_detect_pauses_judges_and_auto_resumes():
    c = running()
    acts = judge(c)
    j = kinds(acts, "publish")[0]
    assert j[1] == "judgment" and j[2]["code"] == "OK" and j[2]["img"] == "a.jpg" and j[2]["trigger"] == "CAM"
    assert not kinds(acts, "gateway")            # 분기(sorting) 꺼짐: 손에 보내지 않음
    assert c.state == "RESUME_WAIT"
    assert c.tick(600) == []                     # resume_delay_ms 전
    assert c.tick(700) == [("arduino", "GO")]    # 자동 출발
    assert c.state == "LEAVE"
    assert c.on_detect(800) == []                # 같은 병이 아직 구역 안 → 다시 판정하지 않음
    c.on_clear(900)
    assert c.state == "IDLE"


def test_detect_ignored_unless_belt_running():
    c = LineController()
    assert c.on_detect(0) == []                  # 켜자마자는 STOP(잠김)
    c.on_arduino(("EVT", "RUN"), 0)
    c.on_arduino(("STATE", "PAUSE", "N"), 0)
    assert c.on_detect(0) == []


def test_manual_capture_works_when_stopped():
    c = LineController(settle_ms=0, stop_to_judge=True)
    assert c.on_manual(0) == []                  # 벨트가 멈춰 있으면 PAUSE 없이 바로 찍음
    assert c.tick(0) == [("capture", 0)]
    assert c.trigger == "MANUAL"


def test_ir_arrive_is_backup_trigger():
    c = running()
    c.on_arduino(("EVT", "ARRIVE"), 0)
    assert c.state == "SETTLE" and c.trigger == "IR" and c.belt == "PAUSE"


def gw(c, line, t=0):
    return c.on_gateway(p.parse_gateway_line(line), t)


def test_sorting_ng_sends_j3_and_resumes_after_gateway_ack():
    c = running(sorting=True)
    acts = judge(c, "clear_label", "NG")
    assert ("gateway", "J3") in acts and c.state == "WAIT_ACK"
    assert gw(c, "ACK,57,4", 300) == []          # 다른 판정 번호의 ACK는 무시
    acts = gw(c, "ACK,57,3", 300)
    sort = kinds(acts, "publish")[0]
    assert sort[1] == "sort" and sort[2]["result"] == "SENT" and sort[2]["hand"] == 2 and sort[2]["seq"] == 57
    assert c.state == "RESUME_WAIT"


def test_sorting_sends_ok_too():
    """손 1·2가 날개판을 나란히 돌려 놓아야 하므로 OK(J1)도 보낸다."""
    c = running(sorting=True)
    acts = judge(c, "clear_nolabel", "OK")
    assert ("gateway", "J1") in acts and c.state == "WAIT_ACK"


def test_sorting_no_ack_retries_once_then_holds():
    c = running(sorting=True, ack_timeout_ms=100)
    judge(c, "color_label", "CO", t=0)
    assert kinds(c.tick(150), "gateway")         # 한 번 다시 보냄
    acts = c.tick(300)
    assert ("arduino", "HOLD") in acts and c.state == "IDLE"


def test_stop_aborts_current_bottle():
    c = running()
    c.on_detect(0)
    acts = c.on_arduino(("EVT", "STOP", "MODE"), 50)
    assert c.state == "IDLE" and c.belt == "STOP" and c.stop_cause == "MODE"
    assert any(a[0] == "publish" and a[1] == "sort" and a[2]["result"] == "ABORTED" for a in acts)
    assert any(a[0] == "publish" and a[1] == "safety" and a[2]["cause"] == "MODE" for a in acts)


def test_gateway_mode_is_recorded_from_hand3():
    c = running()
    c.on_detect(0)
    acts = gw(c, "MODE,3", 10)                   # 손 3이 일시 정지 → 진행 중이던 병 중단
    assert c.mode == p.Mode.PAUSE and c.state == "IDLE"
    assert any(a[1] == "mode" and a[2] == {**a[2], "mode": 3, "by": "hand3"} for a in kinds(acts, "publish"))
    assert any(a[1] == "sort" and a[2]["result"] == "ABORTED" for a in kinds(acts, "publish"))
    assert gw(c, "MODE,3", 20) == []             # 같은 모드 반복은 기록하지 않음
    acts = gw(c, "MODE,4", 30)
    assert ("arduino", "HOLD") in acts and c.mode == p.Mode.LOCKOUT
    gw(c, "MODE,1", 40)                          # 잠금 해제는 손 3이 판단 (A+B). app은 따라 기록만
    assert c.mode == p.Mode.AUTO


def test_gateway_danger_help_link():
    c = LineController()
    acts = gw(c, "DNG,1")
    assert kinds(acts, "publish")[0][2]["event"] == "WARN" and c.danger == p.Danger.WARN
    assert gw(c, "DNG,1") == []
    assert kinds(gw(c, "HELP,1"), "publish")[0][2]["event"] == "HELP"
    assert kinds(gw(c, "HELP,0"), "publish")[0][2]["event"] == "HELP_END"
    assert gw(c, "LINK,OK") == [] and c.link is True
    acts = gw(c, "LINK,LOST")
    assert kinds(acts, "publish")[0][2]["cause"] == "LINK_LOST" and c.link is False
    st = c.state_payload()
    assert st["help"] == 0 and st["link"] is False and st["state"] == "WARN"


def test_controller_never_commands_restart():
    """재가동은 리셋 버튼으로만: 상태 머신은 우노에 PAUSE·GO·HOLD 말고는 보내지 않는다."""
    c = running(sorting=True)
    acts = judge(c, "clear_label", "NG")
    for line in ["MODE,1", "MODE,2", "MODE,3", "MODE,4", "DNG,0", "DNG,1", "DNG,2", "ACK,1,3", "LINK,LOST"]:
        acts += gw(c, line)
    acts += c.tick(10_000) + c.on_arduino(("EVT", "STOP", "HB"), 0) + c.on_arduino(("EVT", "RUN"), 0)
    for a in kinds(acts, "arduino"):
        assert a[1] in ("PAUSE", "GO", "HOLD")


# ---------------- 기본 방식: 벨트를 멈추지 않음 (stop_to_judge: false) ----------------
FLOW = {"speed_mm_s": {"N": 100, "S": 50}, "hand1_mm": 400, "hand2_mm": 700, "flap_mm": 100,
        "bottle_mm": 200, "flap_ms": 400, "margin_ms": 100}
# 속도 100mm/s → 날개판이 도는 동안(0.5초) 50mm. 감지 때 병 꼬리 = 판정 구역 들어오는 쪽 가장자리(pos)


def moving(**kw) -> LineController:
    c = LineController(stop_to_judge=False, **kw)
    c.on_arduino(("EVT", "RUN"), 0)
    c.tick(0)
    return c


def run_to(c, t):
    """t(ms)까지 20ms 간격으로 tick. 나온 할 일을 모두 돌려준다."""
    acts = []
    now = c._last_tick
    while now < t:
        now = min(t, now + 20)
        acts += c.tick(now)
    return acts


def judge_moving(c, code, t, cls=None):
    cls = cls or {"OK": "clear_nolabel", "NG": "clear_label", "CO": "color_nolabel", "RE": "clear_nolabel"}[code]
    run_to(c, t)
    assert c.on_detect(t) == [("capture", c.bottle_id)]   # PAUSE 없이 바로 촬영
    acts = c.on_decision(cls, code, 0.9, 1, t)
    c.on_clear(t)                                          # 병이 구역을 빠져나감 (시험에서는 바로)
    return acts


def test_moving_never_pauses_belt():
    c = moving()
    for i, code in enumerate(["OK", "NG", "CO", "RE"]):
        acts = judge_moving(c, code, 1000 * (i + 1))
        assert not kinds(acts, "arduino")
        assert kinds(acts, "publish")[0][1] == "judgment"
    assert c.state == "IDLE" and c.belt == "RUN"


def test_moving_manual_capture_does_not_pause():
    c = moving()
    assert c.on_manual(0) == [("capture", 0)]


def test_moving_ir_arrive_resumes_after_judgment():
    c = moving()
    assert c.on_arduino(("EVT", "ARRIVE"), 0) == [("capture", 0)]   # 우노가 스스로 멈춤
    acts = c.on_decision("clear_nolabel", "OK", 0.9, 1, 10)
    assert ("arduino", "GO") in acts


def test_position_counts_only_while_running_and_by_speed():
    c = moving(flow=FLOW)
    run_to(c, 1000)
    assert round(c.pos_mm) == 100
    c.on_arduino(("STATE", "PAUSE", "N"), 1000)
    run_to(c, 2000)
    assert round(c.pos_mm) == 100                 # 멈춘 동안은 그대로
    c.on_arduino(("STATE", "RUN", "S"), 2000)
    run_to(c, 3000)
    assert round(c.pos_mm) == 150                 # 저속 50mm/s


def test_moving_sorting_sends_immediately_when_flaps_free():
    c = moving(sorting=True, flow=FLOW)
    acts = judge_moving(c, "NG", 0)
    assert ("gateway", "J3") in acts
    acts = gw(c, "ACK,1,3")
    sort = kinds(acts, "publish")[0][2]
    assert sort["result"] == "SENT" and sort["hand"] == 2 and sort["late"] is False
    assert c.flaps == (False, True)


def test_moving_sorting_waits_until_previous_bottle_passes_hand2():
    """앞 병(NG, 손 2에서 빠짐)이 손 2를 다 지나기 전에 뒷 병(OK) 판정을 보내면 앞 병이 투명 통으로 간다."""
    c = moving(sorting=True, flow=FLOW)
    judge_moving(c, "NG", 0)                       # 앞 병 pos 0 → 손 2를 다 지나는 pos = 700 + 100 = 800
    gw(c, "ACK,1,3")
    acts = judge_moving(c, "OK", 3000)             # 뒷 병 pos 300. 손 2 날개판만 바뀜 → 늦어도 300+700-200-50 = 750
    assert not kinds(acts, "gateway")              # 앞 병이 아직 손 2 앞 (pos 300)
    acts = run_to(c, 7900)
    assert not kinds(acts, "gateway")              # pos 790
    acts = run_to(c, 8000)
    assert ("gateway", "J1") in acts               # pos 800: 앞 병이 다 지남 → 보냄
    acts = gw(c, "ACK,2,1")
    assert kinds(acts, "publish")[0][2]["late"] is True   # 750을 넘겨 늦음 (간격 부족)


def test_moving_sorting_warns_once_when_bottles_too_close():
    c = moving(sorting=True, flow=FLOW)
    judge_moving(c, "NG", 0)
    gw(c, "ACK,1,3")
    acts = judge_moving(c, "OK", 3000) + run_to(c, 5000)
    errors = [a for a in kinds(acts, "publish") if a[1] == "safety" and a[2]["cause"] == "TOO_CLOSE"]
    assert len(errors) == 1
    assert not kinds(acts, "arduino")              # 간격이 좁아도 벨트는 멈추지 않는다


def test_moving_sorting_enough_gap_is_on_time():
    c = moving(sorting=True, flow=FLOW)
    judge_moving(c, "NG", 0)
    gw(c, "ACK,1,3")
    judge_moving(c, "CO", 6000)                    # 뒷 병 pos 600. 손 1·2 모두 바뀜
    acts = run_to(c, 8000)                         # 앞 병이 손 2를 다 지나는 pos 800
    assert ("gateway", "J4") in acts
    # 뒷 병(CO)은 손 1에서 빠짐: 늦어도 600+400-200-50 = 750 → 800이면 늦음. 손 2 기준이면 안 늦음
    sort = kinds(gw(c, "ACK,2,4"), "publish")[0][2]
    assert sort["late"] is True
    c2 = moving(sorting=True, flow=FLOW)
    judge_moving(c2, "NG", 0)
    gw(c2, "ACK,1,3")
    judge_moving(c2, "CO", 7000)                   # pos 700 → 늦어도 850. 800에 보냄 → 제때
    run_to(c2, 8000)
    assert kinds(gw(c2, "ACK,2,4"), "publish")[0][2]["late"] is False


def test_moving_same_flaps_need_no_wait():
    c = moving(sorting=True, flow=FLOW)
    judge_moving(c, "NG", 0)
    gw(c, "ACK,1,3")
    acts = judge_moving(c, "RE", 1000)             # NG와 RE는 날개판이 같다 → 바로 보내도 앞 병에 영향 없음
    assert ("gateway", "J0") in acts


def test_moving_sorting_without_flow_sends_immediately():
    c = moving(sorting=True)                       # 실측값 없음
    judge_moving(c, "NG", 0)
    gw(c, "ACK,1,3")
    assert ("gateway", "J1") in judge_moving(c, "OK", 100)


def test_moving_no_ack_holds_and_aborts_queue():
    c = moving(sorting=True, flow=FLOW, ack_timeout_ms=100)
    judge_moving(c, "NG", 0)
    assert kinds(run_to(c, 200), "gateway")        # 한 번 다시 보냄
    acts = run_to(c, 400)
    assert ("arduino", "HOLD") in acts and c.sending is None


def test_moving_stop_aborts_unsent_bottles():
    c = moving(sorting=True, flow=FLOW)
    judge_moving(c, "NG", 0)
    gw(c, "ACK,1,3")
    judge_moving(c, "OK", 3000)                    # 보낼 차례 기다리는 중
    acts = c.on_arduino(("EVT", "STOP", "MODE"), 3100)
    aborted = [a[2]["id"] for a in kinds(acts, "publish") if a[1] == "sort" and a[2]["result"] == "ABORTED"]
    assert aborted == [1] and c.queue == [] and c.flight == []


def test_moving_lockout_folds_flaps():
    c = moving(sorting=True, flow=FLOW)
    judge_moving(c, "CO", 0)
    gw(c, "ACK,1,4")
    assert c.flaps == (True, False)
    gw(c, "MODE,4")
    assert c.flaps == (False, False)
