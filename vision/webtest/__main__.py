"""카메라 인식 웹 테스트 실행.

    python -m vision.webtest            # 노트북 브라우저: http://localhost:<port>
    python -m vision.webtest --https    # 휴대폰 실시간 카메라용 (자체 서명 인증서)

설명: vision/webtest/README.md
"""
from __future__ import annotations

import argparse
import socket
from pathlib import Path

from common.config import ROOT, load_settings

CERT_DIR = ROOT / "data" / "certs"  # .gitignore 대상


def lan_addresses() -> list[str]:
    """같은 와이파이의 휴대폰에서 접속할 주소 후보 (외부로 아무것도 보내지 않음)."""
    try:
        _, _, ips = socket.gethostbyname_ex(socket.gethostname())
    except OSError:
        return []
    return [ip for ip in ips if not ip.startswith("127.")]


def ensure_self_signed_cert(ips: list[str]) -> tuple[Path, Path]:
    """휴대폰 브라우저는 https에서만 실시간 카메라를 허용한다. 시험용 자체 서명 인증서를 만든다."""
    import datetime
    import ipaddress

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    cert_path, key_path = CERT_DIR / "webtest.crt", CERT_DIR / "webtest.key"
    if cert_path.exists() and key_path.exists():
        return cert_path, key_path
    CERT_DIR.mkdir(parents=True, exist_ok=True)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "pet-webtest")])
    alt = [x509.DNSName("localhost"), x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]
    alt += [x509.IPAddress(ipaddress.ip_address(ip)) for ip in ips]
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name).issuer_name(name).public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now).not_valid_after(now + datetime.timedelta(days=365))
        .add_extension(x509.SubjectAlternativeName(alt), critical=False)
        .sign(key, hashes.SHA256())
    )
    key_path.write_bytes(key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption()))
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return cert_path, key_path


def main() -> None:
    settings = load_settings()
    cfg = settings["webtest"]
    p = argparse.ArgumentParser(description="휴대폰·웹캠 사진 인식 웹 테스트")
    p.add_argument("--port", type=int, default=cfg["port"])
    p.add_argument("--host", default="0.0.0.0", help="0.0.0.0이면 같은 와이파이의 휴대폰에서도 접속")
    p.add_argument("--model", default=None,
                   help="가중치 직접 지정 (기본: vision.weights, 없으면 webtest.fallback_model)")
    p.add_argument("--https", action="store_true", help="자체 서명 인증서로 https 실행 (휴대폰 실시간 카메라용)")
    args = p.parse_args()

    import uvicorn

    from .recognizer import load_recognizer
    from .server import create_app

    print("모델을 여는 중...")
    rec = load_recognizer(settings, ROOT, args.model)
    kind = "학습한 4클래스 모델 (판정 코드 표시)" if rec.custom else "기본 모델 (카메라 연결 시험용, 판정 코드 없음)"
    print(f"모델: {rec.model_name} — {kind}")

    ips = lan_addresses()
    ssl = {}
    if args.https:
        cert, key = ensure_self_signed_cert(ips)
        ssl = {"ssl_certfile": str(cert), "ssl_keyfile": str(key)}
    scheme = "https" if args.https else "http"
    print(f"\n  노트북:  {scheme}://localhost:{args.port}")
    for ip in ips:
        print(f"  휴대폰:  {scheme}://{ip}:{args.port}   (같은 와이파이)")
    if not args.https:
        print("  ※ 휴대폰에서 실시간 카메라를 쓰려면 --https 로 실행하세요. http에서는 '사진 찍어 올리기'만 됩니다.")
    print()
    app = create_app(rec, int(cfg["interval_ms"]), camera_index=int(settings["vision"]["camera_index"]))
    uvicorn.run(app, host=args.host, port=args.port, **ssl)


if __name__ == "__main__":
    main()
