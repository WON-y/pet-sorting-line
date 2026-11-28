"""app 상태 머신 (docs/spec/modes_and_states.md 3·5절)."""
from app.controller import LineController
from common import protocol as p


def kinds(acts, kind):
    return [a for a in acts if a[0] == kind]


def running(**kw) -> LineController:
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
    c = LineController(settle_ms=0)
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
