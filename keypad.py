from __future__ import annotations
import os
import sys
import threading
import time
from PySide6.QtCore import QObject, Signal
VID, PID = 0x10C4, 0xEA60
BAUD = 115200
LINE_MAX = 48
OPEN_SETTLE_S = 0.2
PING_INTERVAL_S = 1.0
SILENCE_TIMEOUT_S = 3.0
RETRY_S = 1.0
RETRY_LOG_S = 30.0
KEYS = ("A", "B", "C", "D", "N")
LED_MAX = {"A": 1, "B": 1, "C": 1, "D": 1, "N": 2}
_ALLOWED_TX = {"HELLO?", "STATE?", "PING", "CELEBRATE", "LED"}
def find_cp210x_port() -> str | None:
    try:
        from serial.tools import list_ports
        for p in list_ports.comports():
            if p.vid == VID and p.pid == PID:
                return p.device
    except Exception:
        pass
    return None
def open_serial(port: str):
    import serial
    ser = serial.Serial()
    ser.port = port
    ser.baudrate = BAUD
    ser.bytesize = serial.EIGHTBITS
    ser.parity = serial.PARITY_NONE
    ser.stopbits = serial.STOPBITS_ONE
    ser.timeout = 0.05
    ser.write_timeout = 0.5
    ser.xonxoff = False
    ser.rtscts = False
    ser.dsrdtr = False
    ser.dtr = False
    ser.rts = False
    ser.open()
    try:
        ser.dtr = False
        ser.rts = False
    except Exception:
        pass
    time.sleep(OPEN_SETTLE_S)
    try:
        ser.reset_input_buffer()
    except Exception:
        pass
    return ser
class _LineBuffer:
    def __init__(self):
        self._buf = b""
    def feed(self, data: bytes) -> list[str]:
        if not data:
            return []
        self._buf += data
        if len(self._buf) > LINE_MAX * 4:
            i = self._buf.rfind(b"\n")
            self._buf = self._buf[i + 1:] if i >= 0 else self._buf[-LINE_MAX:]
        lines = []
        while True:
            i = self._buf.find(b"\n")
            if i < 0:
                break
            raw, self._buf = self._buf[:i], self._buf[i + 1:]
            raw = raw.replace(b"\r", b"")
            if len(raw) > LINE_MAX:
                continue
            text = raw.decode("utf-8", "replace").strip()
            if text:
                lines.append(text)
        return lines
def _parse(line: str):
    parts = line.split(" ")
    if not parts:
        return "ignore", None
    head = parts[0]
    if head == "PONG":
        return "pong", None
    if head == "BTN" and len(parts) == 3 and parts[2] in ("0", "1"):
        return "btn", {"key": parts[1], "down": parts[2] == "1"}
    if head == "HELLO":
        return "hello", line
    if head == "STATE":
        state = {}
        for tok in parts[1:]:
            if "=" in tok:
                k, v = tok.split("=", 1)
                try:
                    state[k] = int(v)
                except ValueError:
                    continue
        return "state", state
    if head == "OK":
        return "ok", parts[1:]
    if head == "ERR":
        return "err", " ".join(parts[1:])
    return "ignore", line
class Keypad(QObject):
    btn = Signal(str, bool)
    def __init__(self, parent=None):
        super().__init__(parent)
        self._spec = (os.environ.get("XINGYUE_KEYPAD") or "auto").strip()
        self._stop = threading.Event()
        self._ser = None
        self._ser_lock = threading.Lock()
        self._out: list[str] = []
        self._out_lock = threading.Lock()
        self._intent: dict[str, int] = {}
        self._intent_lock = threading.Lock()
        self._need_sync = False
        self._thread: threading.Thread | None = None
        self._last_retry_log = 0.0
    @property
    def enabled(self) -> bool:
        return self._spec.lower() not in ("off", "0", "false")
    def start(self) -> None:
        if not self.enabled:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="keypad", daemon=True)
        self._thread.start()
    def stop(self) -> None:
        self._stop.set()
        self._close()
        if self._thread:
            self._thread.join(timeout=2)
    def set_led(self, key: str, value: int) -> None:
        if key not in LED_MAX:
            return
        v = max(0, min(LED_MAX[key], int(value)))
        with self._intent_lock:
            self._intent[key] = v
        with self._out_lock:
            self._out.append(f"LED {key} {v}")
    def celebrate(self) -> None:
        with self._out_lock:
            self._out.append("CELEBRATE")
    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                port = self._resolve_port()
                if not port:
                    self._retry("keypad: 等待 CP210x (10c4:ea60)")
                    continue
                try:
                    ser = open_serial(port)
                except Exception as exc:
                    self._retry(f"keypad: 打开 {port} 失败: {exc}")
                    continue
                with self._ser_lock:
                    self._ser = ser
                self._session(ser)
            except Exception as exc:
                self._retry(f"keypad: {exc}")
            finally:
                self._close()
    def _resolve_port(self) -> str | None:
        if self._spec in ("", "auto"):
            return find_cp210x_port()
        return self._spec
    def _retry(self, msg: str) -> None:
        now = time.monotonic()
        if now - self._last_retry_log >= RETRY_LOG_S:
            print(msg, file=sys.stderr, flush=True)
            self._last_retry_log = now
        self._stop.wait(RETRY_S)
    def _session(self, ser) -> None:
        buf = _LineBuffer()
        self._need_sync = True
        last_rx = time.monotonic()
        last_ping = 0.0
        heard = False
        self._write("HELLO?")
        self._write("STATE?")
        while not self._stop.is_set():
            now = time.monotonic()
            if now - last_rx >= SILENCE_TIMEOUT_S:
                print("keypad: 3s 无板子报文，重连", file=sys.stderr, flush=True)
                return
            if now - last_ping >= PING_INTERVAL_S:
                self._write("PING")
                last_ping = now
            self._flush()
            try:
                n = getattr(ser, "in_waiting", 0) or 0
                chunk = ser.read(n) if n else ser.read(64)
            except Exception:
                return
            lines = buf.feed(chunk)
            if not lines:
                continue
            last_rx = time.monotonic()
            if not heard:
                heard = True
                print(f"keypad: 已连接 {ser.port}", file=sys.stderr, flush=True)
            for line in lines:
                self._on_line(line)
    def _on_line(self, line: str) -> None:
        kind, payload = _parse(line)
        if kind == "btn":
            if payload["key"] in KEYS:
                self.btn.emit(payload["key"], payload["down"])
        elif kind == "hello":
            self._need_sync = True
            self._write("STATE?")
        elif kind == "state":
            self._sync(payload)
    def _sync(self, board: dict) -> None:
        if not self._need_sync:
            return
        with self._intent_lock:
            for k, v in board.items():
                if k not in self._intent:
                    self._intent[k] = v
            pending = [(k, v) for k, v in self._intent.items() if k in board and board[k] != v]
        self._need_sync = False
        for k, v in pending:
            self._write(f"LED {k} {v}")
    def _write(self, cmd: str) -> bool:
        if cmd.split(" ", 1)[0] not in _ALLOWED_TX:
            return False
        with self._ser_lock:
            ser = self._ser
        if ser is None:
            return False
        try:
            ser.write((cmd + "\n").encode("ascii"))
            return True
        except Exception:
            return False
    def _flush(self) -> None:
        with self._out_lock:
            batch, self._out = self._out, []
        for cmd in batch:
            self._write(cmd)
    def _close(self) -> None:
        with self._ser_lock:
            ser, self._ser = self._ser, None
        if ser is not None:
            try:
                ser.close()
            except Exception:
                pass
