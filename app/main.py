"""노트북 통합 실행 — 라인 + 대시보드를 한 프로그램으로 (도커 없이).

    python -m app --mock              # 웹캠·벨트 없이 가짜 화면으로 전체 흐름 (대시보드 http://localhost:8000)
    python -m app                     # 웹캠 + YOLO. 우노 포트가 없으면 가상 벨트로 시험
    python -m app --video test.mp4    # 웹캠 대신 녹화 영상
    python -m app --phone             # 웹캠 대신 휴대폰 카메라 (대시보드의 QR로 접속)
    python -m app --no-web            # 대시보드 없이 (도커 simulator 등)

역할: 웹캠·우노·게이트웨이를 상태 머신에 연결하고, 기록은 SQLite(app.record: local) 또는 MQTT(mqtt)로 보낸다.
정지 경로에 끼지 않는다 (docs/spec/safety_rules.md). 이 프로그램이 죽어도 벨트는 우노가 멈춘다.
"""
from __future__ import annotations

import argparse
import logging
import os
import threading

from app.controller import LineController
from app.line import LineRunner, LocalRecorder
from common.config import ROOT, load_settings

log = logging.getLogger("app")
MOCK_DIR = "data/mock"          # 모의 실행 기록·사진 (실제 기록과 분리)


def _path(value: str) -> str:
    """settings.yaml의 상대 경로는 저장소 맨 위 기준."""
    return value if os.path.isabs(value) else str(ROOT / value)


def build(cfg: dict, mock: bool, video: str | None = None, web: bool = True,
          phone: bool = False) -> tuple[LineRunner, object]:
    vcfg, acfg, scfg = cfg["vision"], cfg["app"], cfg["serial"]
    ctl = LineController(ack_timeout_ms=acfg["ack_timeout_ms"], settle_ms=acfg.get("settle_ms", 400),
                         resume_delay_ms=acfg.get("resume_delay_ms", 2000), sorting=bool(acfg.get("sorting")),
                         stop_to_judge=bool(acfg.get("stop_to_judge", False)), flow=acfg.get("flow"))
    if ctl.sorting and not ctl.stop_to_judge and not ctl.flow_ready():
        log.warning("app.flow 실측값이 비어 있어 판정을 바로 보냅니다. 병 간격을 넓게 두세요 (app/README.md)")
    capture_dir = _path(vcfg.get("capture_dir", "data/captures"))
    db_path = _path(cfg["dashboard"]["db_path"])
    if mock:   # 가짜 사진·기록이 실제 벨트 사진(재학습용)과 섞이지 않게 따로 둔다
        capture_dir, db_path = _path(MOCK_DIR + "/captures"), _path(MOCK_DIR + "/pet.db")
    helpers: list = []

    # 벨트: 우노 포트가 있으면 실제 우노, 없으면 가상 벨트 (대시보드 시험 버튼으로 조작)
    if scfg.get("arduino_port") and not mock:
        from communication.serial_bridge.links import SerialLink

        belt = SerialLink(scfg["arduino_port"], scfg["baud"])
    else:
        from app.sim_belt import SimBelt

        belt = SimBelt()
        if not mock:
            log.warning("우노 포트가 없어 가상 벨트로 실행합니다 (대시보드 '시험' 버튼으로 조작)")

    # 게이트웨이: 포트가 있으면 연결해 손 3 모드·위험·도움 요청을 기록. 판정은 sorting일 때만 보냄
    gateway = None
    if mock:
        if ctl.sorting:
            from app.mock import MockGateway

            gw = MockGateway()
            gateway = gw.link
            helpers.append(gw)
    elif scfg.get("gateway_port"):
        from communication.serial_bridge.links import SerialLink

        gateway = SerialLink(scfg["gateway_port"], scfg["baud"])

    # 영상
    if mock:
        from app.mock import MockOperator, MockVision

        vision = MockVision(belt, vcfg)
        helpers.append(MockOperator(belt))
    elif phone:
        from vision.bottle.phone import PhoneFeed, PhoneVision

        vision = PhoneVision(vcfg, PhoneFeed(int(cfg.get("phone", {}).get("timeout_ms", 2000))))
    else:
        from vision.bottle.pipeline import CameraVision

        vision = CameraVision(vcfg, video)

    # 기록
    dash = None
    if acfg.get("record", "local") == "mqtt":
        from communication.serial_bridge.mqtt_pub import MqttPublisher

        mcfg = cfg["mqtt"]
        publisher = MqttPublisher(mcfg["host"], int(mcfg["port"]))
    else:
        import dashboard.app.main as dash

        dash.init(db_path, capture_dir)
        publisher = LocalRecorder(dash.handle_message)

    runner = LineRunner(cfg, vision, belt, ctl, publisher, gateway, capture_dir, helpers)
    if dash is not None and web:
        dash.attach_line(runner)
    return runner, dash


def start_web(dash, host: str, port: int):
    import uvicorn

    server = uvicorn.Server(uvicorn.Config(dash.app, host=host, port=port, log_level="warning"))
    threading.Thread(target=server.run, name="dashboard", daemon=True).start()
    return server


def run(mock: bool, duration_s: float | None = None, video: str | None = None, web: bool = True,
        phone: bool = False) -> None:
    cfg = load_settings()
    runner, dash = build(cfg, mock, video, web, phone)
    server = phone_server = None
    feed = getattr(runner.vision, "feed", None)
    if feed is not None:
        from app.phone_server import start_phone_server

        phone_server = start_phone_server(feed, cfg.get("phone", {}))
    if web and dash is not None:
        dcfg = cfg["dashboard"]
        server = start_web(dash, dcfg["host"], int(dcfg["port"]))
        log.info("대시보드: http://%s:%s", "localhost" if dcfg["host"] in ("127.0.0.1", "0.0.0.0") else dcfg["host"],
                 dcfg["port"])
    log.info("시작 (mock=%s)", mock)
    try:
        runner.run(duration_s)
    except KeyboardInterrupt:
        log.info("종료")
    finally:
        for srv in (server, phone_server):
            if srv is not None:
                srv.should_exit = True
        runner.vision.close()


def cli() -> None:
    ap = argparse.ArgumentParser(description="페트병 선별 라인 노트북 통합 실행 (라인 + 대시보드)")
    ap.add_argument("--mock", action="store_true", help="웹캠·벨트 없이 가짜 화면으로 실행")
    ap.add_argument("--video", default=None, help="웹캠 대신 녹화 영상 파일로 시험")
    ap.add_argument("--phone", action="store_true", help="웹캠 대신 휴대폰 카메라 (대시보드의 QR로 접속)")
    ap.add_argument("--no-web", action="store_true", help="대시보드 웹 서버를 켜지 않음")
    ap.add_argument("--duration", type=float, default=None, help="초 단위 실행 시간 (시험용)")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    if args.phone and (args.mock or args.video):
        ap.error("--phone은 --mock·--video와 같이 쓸 수 없습니다")
    run(args.mock, args.duration, args.video, not args.no_web, args.phone)


if __name__ == "__main__":
    cli()
