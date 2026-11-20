"""시리얼 연결. 한 줄 = 한 메시지 (docs/spec/protocol.md 2·4절).

실제 연결(SerialLink)과 모의 연결(FakeLink)이 같은 메서드를 가진다:
  send(text)       : 한 줄 보내기 (끝에 \\n 포함)
  read_lines()     : 지금까지 받은 줄 목록 (막히지 않음)
"""
from __future__ import annotations

from collections import deque


class SerialLink:
    def __init__(self, port: str, baud: int = 115200):
        import serial  # pyserial, 사용할 때만 import

        self.ser = serial.Serial(port, baud, timeout=0)
        self._buf = b""

    def send(self, text: str) -> None:
        self.ser.write(text.encode("ascii"))

    def read_lines(self) -> list[str]:
        self._buf += self.ser.read(self.ser.in_waiting or 0)
        *lines, self._buf = self._buf.split(b"\n")
        return [ln.decode("ascii", "ignore").strip() for ln in lines if ln.strip()]


class FakeLink:
    """하드웨어 없이 시험·모의 실행용. inject()로 받은 줄을 흉내 내고, sent에 보낸 줄이 쌓인다."""

    def __init__(self):
        self.sent: list[str] = []
        self._incoming: deque[str] = deque()

    def inject(self, line: str) -> None:
        self._incoming.append(line)

    def send(self, text: str) -> None:
        self.sent.append(text.strip())

    def read_lines(self) -> list[str]:
        out = list(self._incoming)
        self._incoming.clear()
        return out
