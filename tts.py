from __future__ import annotations
import hashlib
import json
import os
import pathlib
import re
import struct
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from PySide6.QtCore import QObject, QUrl, QTimer, Signal
from PySide6.QtMultimedia import QSoundEffect
ROOT = pathlib.Path(__file__).resolve().parent
URL = "wss://openspeech.bytedance.com/api/v3/tts/bidirection"
EV_START_CONN, EV_FINISH_CONN, EV_CONN_FAILED = 1, 2, 51
EV_START_SESSION, EV_FINISH_SESSION = 100, 102
EV_SESSION_STARTED, EV_SESSION_FINISHED, EV_SESSION_FAILED = 150, 152, 153
EV_TASK_REQUEST, EV_TTS_RESPONSE = 200, 352
FULL, WITH_EVENT, SER_JSON = 0b0001, 0b0100, 0b0001
ERROR_INFO = 0b1111
CACHE = ROOT / "data" / "tts"
PLAY_DIR = CACHE / "play"
TAIL_SEC = 0.1
def _play_wav(wav_path: str, rate: int) -> tuple[str, float]:
    src = pathlib.Path(wav_path)
    dst = PLAY_DIR / f"{src.stem}_t{int(TAIL_SEC * 1000)}.wav"
    if not dst.exists():
        PLAY_DIR.mkdir(parents=True, exist_ok=True)
        pcm = src.read_bytes()[44:]
        pcm += b"\x00" * int(rate * TAIL_SEC) * 2
        h = b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVE" + b"fmt "
        h += struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16)
        dst.write_bytes(h + b"data" + struct.pack("<I", len(pcm)) + pcm)
    return str(dst), (dst.stat().st_size - 44) / (rate * 2)
def _diag(msg: str) -> None:
    try:
        p = CACHE / "diag.log"
        if p.exists() and p.stat().st_size > 512 * 1024:
            p.unlink()
        line = f"{time.strftime('%H:%M:%S')} {time.time() * 1000 % 100000:.0f} {msg}\n"
        with open(p, "a", encoding="utf-8") as f:
            f.write(line)
    except OSError:
        pass
def speakable(text: str) -> str:
    s = str(text or "")
    s = re.sub(r"[、，,]\s*_{2,}\s*[、，,]", "、", s)
    s = re.sub(r"_{2,}", "、", s)
    s = re.sub(r"[×✕✖*]", "乘", s)
    s = re.sub(r"[÷／/]", "除以", s)
    s = re.sub(r"[＋+]", "加", s)
    s = re.sub(r"[−–—－]", "减", s)
    s = s.replace("-", "减")
    s = re.sub(r"[＝=]\s*[?？]", "等于几", s)
    s = re.sub(r"[＝=]", "等于", s)
    s = re.sub(r"[＞>]", "大于", s)
    s = re.sub(r"[＜<]", "小于", s)
    s = re.sub(r"[?？]", "", s)
    return re.sub(r"\s+", " ", s).strip()
def load_config() -> dict | None:
    vals: dict[str, str] = {}
    env_file = os.environ.get("XINGYUE_TTS_ENV_FILE")
    if env_file:
        path = pathlib.Path(env_file)
    else:
        path = ROOT / ".env.tts"
        if not path.exists():
            path = ROOT.parent / "xingyue-formal" / ".env.tts"
    try:
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    vals[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    key = (os.environ.get("XINGYUE_TTS_KEY") or vals.get("XINGYUE_TTS_KEY") or "").strip()
    if not key:
        return None
    num = lambda name, default: float(vals.get(name, default))
    return {
        "key": key,
        "resource": (os.environ.get("XINGYUE_TTS_RESOURCE") or vals.get("XINGYUE_TTS_RESOURCE") or "seed-tts-2.0").strip(),
        "speaker": (os.environ.get("XINGYUE_TTS_SPEAKER") or vals.get("XINGYUE_TTS_SPEAKER") or "zh_female_vv_uranus_bigtts").strip(),
        "rate": int(num("XINGYUE_TTS_SAMPLE_RATE", 24000)),
        "speech_rate": int(num("XINGYUE_TTS_SPEECH_RATE", -10)),
        "loudness_rate": int(num("XINGYUE_TTS_LOUDNESS_RATE", 0)),
        "timeout": num("XINGYUE_TTS_TIMEOUT_MS", 30000) / 1000.0,
    }
def _frame(event: int, sid: str | None = None, payload: bytes = b"{}") -> bytes:
    out = bytearray([0x11, (FULL << 4) | WITH_EVENT, SER_JSON << 4, 0x00])
    out += struct.pack(">i", event)
    if sid is not None:
        b = sid.encode("utf-8")
        out += struct.pack(">I", len(b)) + b
    out += struct.pack(">I", len(payload)) + payload
    return bytes(out)
def _parse(data: bytes) -> dict:
    info: dict = {"type": 0, "event": None, "code": None, "sid": None, "payload": b""}
    if len(data) < 4:
        return info
    mtype, flags = data[1] >> 4, data[1] & 0x0F
    info["type"] = mtype
    if mtype == ERROR_INFO:
        if len(data) >= 8:
            info["code"] = struct.unpack(">i", data[4:8])[0]
        if len(data) >= 12:
            n = struct.unpack(">I", data[8:12])[0]
            info["payload"] = data[12 : 12 + n]
        return info
    cur = 4
    if flags & WITH_EVENT and cur + 4 <= len(data):
        info["event"] = struct.unpack(">i", data[cur : cur + 4])[0]
        cur += 4
    if cur + 4 <= len(data):
        n = struct.unpack(">I", data[cur : cur + 4])[0]
        if 0 < n <= 64 and cur + 4 + n + 4 <= len(data):
            info["sid"] = data[cur + 4 : cur + 4 + n].decode("utf-8", "replace")
            cur += 4 + n
    if cur + 4 <= len(data):
        n = struct.unpack(">I", data[cur : cur + 4])[0]
        cur += 4
        info["payload"] = data[cur : cur + n]
    return info
def _as_bytes(msg) -> bytes:
    return msg.encode("utf-8") if isinstance(msg, str) else bytes(msg)
class DoubaoTTS:
    def __init__(self, cfg: dict, cache_dir: pathlib.Path, timeout: float = 8.0):
        self.key = cfg["key"]
        self.resource = cfg["resource"]
        self.speaker = cfg["speaker"]
        self.rate = int(cfg["rate"])
        self.speech_rate = int(cfg["speech_rate"])
        self.loudness = int(cfg["loudness_rate"])
        self.cache_dir = cache_dir
        self.timeout = timeout
        self._ws = None
        self._lock = threading.RLock()
        self._stop = threading.Event()
        cache_dir.mkdir(parents=True, exist_ok=True)
    @property
    def enabled(self) -> bool:
        return bool(self.key)
    def _cache_path(self, text: str) -> pathlib.Path:
        voice = f"{self.resource}|{self.speaker}|{self.rate}|{self.speech_rate}|{self.loudness}"
        h = hashlib.sha1(f"{voice}|{text}".encode("utf-8")).hexdigest()[:16]
        return self.cache_dir / f"{h}.wav"
    def _wav(self, pcm: bytes) -> bytes:
        h = b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVE" + b"fmt "
        h += struct.pack("<IHHIIHH", 16, 1, 1, self.rate, self.rate * 2, 2, 16)
        return h + b"data" + struct.pack("<I", len(pcm)) + pcm
    def _connect(self):
        from websockets.sync.client import connect
        ws = connect(
            URL,
            additional_headers={
                "X-Api-Key": self.key,
                "X-Api-Resource-Id": self.resource,
                "X-Api-Connect-Id": str(uuid.uuid4()),
            },
            open_timeout=self.timeout,
            max_size=None,
            compression=None,
        )
        ws.send(_frame(EV_START_CONN))
        info = _parse(_as_bytes(ws.recv(timeout=self.timeout)))
        if info["type"] == ERROR_INFO or info["event"] == EV_CONN_FAILED:
            ws.close()
            raise RuntimeError("tts-connect-failed")
        return ws
    def warm(self) -> None:
        if not self.enabled:
            return
        try:
            with self._lock:
                if self._ws is None:
                    self._ws = self._connect()
        except Exception:
            pass
    def keepalive(self, every: float = 30.0) -> None:
        def loop() -> None:
            while not self._stop.wait(every):
                try:
                    with self._lock:
                        if self._ws is not None:
                            try:
                                self._ws.ping().wait(5)
                                continue
                            except Exception:
                                try:
                                    self._ws.close()
                                except Exception:
                                    pass
                                self._ws = None
                        self._ws = self._connect()
                except Exception:
                    pass
        threading.Thread(target=loop, name="doubao-tts-keepalive", daemon=True).start()
    def close(self) -> None:
        self._stop.set()
        with self._lock:
            if self._ws is not None:
                try:
                    self._ws.send(_frame(EV_FINISH_CONN))
                    self._ws.close()
                except Exception:
                    pass
                self._ws = None
    def _session(self, ws, text: str):
        sid = str(uuid.uuid4())
        meta = {
            "user": {"uid": "xingyue"},
            "event": EV_START_SESSION,
            "namespace": "BidirectionalTTS",
            "req_params": {
                "speaker": self.speaker,
                "audio_params": {
                    "format": "pcm",
                    "sample_rate": self.rate,
                    "speech_rate": self.speech_rate,
                    "loudness_rate": self.loudness,
                    "enable_subtitle": False,
                },
                "additions": json.dumps({"disable_markdown_filter": True, "max_length_to_filter_parenthesis": 0}),
            },
        }
        ws.send(_frame(EV_START_SESSION, sid, json.dumps(meta, ensure_ascii=False).encode()))
        ws.send(_frame(EV_TASK_REQUEST, sid, json.dumps({"req_params": {"text": text}}, ensure_ascii=False).encode()))
        ws.send(_frame(EV_FINISH_SESSION, sid, b"{}"))
        while True:
            info = _parse(_as_bytes(ws.recv(timeout=self.timeout)))
            if info["type"] == ERROR_INFO:
                raise RuntimeError(f"tts-error-{info['code']}")
            if info["sid"] and info["sid"] != sid:
                continue
            if info["event"] == EV_SESSION_FAILED:
                raise RuntimeError("tts-session-failed")
            if info["event"] == EV_TTS_RESPONSE and info["payload"]:
                yield info["payload"]
            if info["event"] == EV_SESSION_FINISHED:
                return
    def _live(self, text: str):
        with self._lock:
            for attempt in (0, 1):
                got = False
                try:
                    if self._ws is None:
                        self._ws = self._connect()
                    for chunk in self._session(self._ws, text):
                        got = True
                        yield chunk
                    return
                except Exception:
                    try:
                        if self._ws is not None:
                            self._ws.close()
                    except Exception:
                        pass
                    self._ws = None
                    if got or attempt == 1:
                        raise
    def synthesize_wav(self, text: str) -> str:
        text = speakable(text)
        if not text:
            raise ValueError("empty-text")
        path = self._cache_path(text)
        if path.exists():
            return str(path)
        pcm = b"".join(self._live(text))
        if not pcm:
            raise RuntimeError("tts-empty-audio")
        tmp = path.with_suffix(".wav.tmp")
        tmp.write_bytes(self._wav(pcm))
        tmp.replace(path)
        return str(path)
class Speaker(QObject):
    segment_bright = Signal(int)
    ended = Signal()
    failed = Signal(str)
    _seg_ready = Signal(int, str, float, int)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.cfg = load_config()
        self.tts = DoubaoTTS(self.cfg, CACHE) if self.cfg else None
        self.pool = ThreadPoolExecutor(max_workers=1)
        self._rate = self.cfg["rate"] if self.cfg else 24000
        self._gen = 0
        self._seg_ready.connect(self._on_seg_ready)
        self._effect = QSoundEffect(self)
        self._effect.setVolume(1.0)
        self._effect.statusChanged.connect(self._on_status)
        self._effect.playingChanged.connect(self._on_playing_changed)
        self._parts: list[str] = []
        self._files: dict[int, tuple[str, float]] = {}
        self._current = -1
        self._awaiting = False
        self._started = False
        self._pending_bright = False
        self._manual_stop = False
        if self.tts and self.tts.enabled:
            threading.Thread(target=self.tts.warm, name="doubao-tts-warm", daemon=True).start()
            self.tts.keepalive()
    def stop(self) -> None:
        self._gen += 1
        self._manual_stop = True
        self._effect.stop()
        self._manual_stop = False
        self._files.clear()
        self._current = -1
        self._awaiting = False
        self._started = False
        self._pending_bright = False
    def speak_parts(self, parts: list[str]) -> None:
        self.stop()
        if not self.tts or not self.tts.enabled:
            QTimer.singleShot(0, lambda: self.failed.emit("tts-disabled"))
            return
        parts = [p for p in parts if p]
        if not parts:
            QTimer.singleShot(0, lambda: self.failed.emit("empty-parts"))
            return
        self._gen += 1
        self._parts = parts
        _diag(f"speak gen={self._gen} segs={len(parts)}: {[(p[:12] + '…') if len(p) > 12 else p for p in parts]}")
        self.pool.submit(self._work, parts, self._gen)
    def _work(self, parts: list[str], gen: int) -> None:
        try:
            for i, part in enumerate(parts):
                if gen != self._gen:
                    return
                wav = self.tts.synthesize_wav(part)
                if gen != self._gen:
                    return
                path, dur = _play_wav(wav, self._rate)
                if gen != self._gen:
                    return
                self._seg_ready.emit(i, path, dur, gen)
        except Exception as exc:
            if gen == self._gen:
                _diag(f"failed gen={gen}: {exc}")
                self.failed.emit(str(exc))
    def _on_seg_ready(self, seg: int, path: str, dur: float, gen: int) -> None:
        if gen != self._gen:
            _diag(f"stale seg={seg} gen={gen}!={self._gen}")
            return
        self._files[seg] = (path, dur)
        _diag(f"ready seg={seg} {pathlib.Path(path).name} {dur:.2f}s")
        if seg == 0 and self._current < 0:
            self._play(0)
        elif self._awaiting and seg == self._current + 1:
            self._awaiting = False
            self._play(seg)
    def _play(self, seg: int) -> None:
        _path, dur = self._files[seg]
        self._current = seg
        self._started = False
        self._pending_bright = seg > 0
        self._manual_stop = True
        try:
            self._effect.stop()
            self._effect.setSource(QUrl.fromLocalFile(_path))
            self._effect.play()
        finally:
            self._manual_stop = False
        _diag(f"play seg={seg} {dur:.2f}s")
    def _on_playing_changed(self) -> None:
        if self._effect.isPlaying():
            if self._manual_stop:
                return
            self._started = True
            if self._pending_bright:
                self._pending_bright = False
                _diag(f"bright seg={self._current}")
                self.segment_bright.emit(self._current)
            return
        if self._manual_stop or not self._started or self._current < 0:
            return
        self._started = False
        _diag(f"finished seg={self._current}")
        nxt = self._current + 1
        if nxt >= len(self._parts):
            self.ended.emit()
            _diag("all ended")
            return
        if nxt in self._files:
            self._play(nxt)
        else:
            self._awaiting = True
            _diag(f"await seg={nxt}")
    def _on_status(self) -> None:
        if self._effect.status() == QSoundEffect.Status.Error:
            self.failed.emit("soundeffect-error")
    def close(self) -> None:
        self.stop()
        if self.tts:
            self.tts.close()
        self.pool.shutdown(wait=False)
