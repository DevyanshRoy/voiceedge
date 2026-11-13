# gateway/serial_bridge.py
"""
Serial bridge: VoiceEdge Gateway <-> Arduino Management Console (FR-6/7/8)

Protocol (115200 baud, newline-terminated, '|' separated)

  Gateway -> Arduino (every `interval` sec):
    M|<gw ON/OFF>|<calls>|<latency_ms>|<packets>|<plugin>|<mode NORMAL/MAINT>|<health OK/HIGHLAT/FAULT>

  Arduino -> Gateway (on button press):
    C|START | C|STOP | C|RESTART | C|MAINT
"""
import logging
import threading
import time

import serial
from serial.tools import list_ports

log = logging.getLogger("serial_bridge")

ARDUINO_VIDS = {0x2341, 0x2A03, 0x1A86, 0x10C4, 0x0403}  # Arduino, CH340, CP210x, FTDI
COMMANDS = {"START", "STOP", "RESTART", "MAINT"}


def format_metrics(snapshot):
    return "M|{gateway}|{calls}|{latency_ms}|{packets}|{plugin}|{mode}|{health}\n".format(**snapshot)


def parse_command(line):
    line = line.strip()
    if not line.startswith("C|"):
        return None
    command = line[2:]
    return command if command in COMMANDS else None


def find_arduino_port():
    for p in list_ports.comports():
        desc = (p.description or "").lower()
        if p.vid in ARDUINO_VIDS or "arduino" in desc or "ch340" in desc:
            return p.device
    return None


class SerialBridge:
    def __init__(self, snapshot_fn, on_command, port=None, baud=115200, interval=1.0):
        """
        snapshot_fn() -> dict with keys:
            gateway ('ON'/'OFF'), calls (int), latency_ms (int), packets (int),
            plugin (str), mode ('NORMAL'/'MAINT'), health ('OK'/'HIGHLAT'/'FAULT')
        on_command(cmd: str) -> called with 'START' | 'STOP' | 'RESTART' | 'MAINT'
        """
        self.snapshot_fn = snapshot_fn
        self.on_command = on_command
        self.port = port
        self.baud = baud
        self.interval = interval
        self._ser = None
        self._stop = threading.Event()
        self._threads = []

    # ---------- lifecycle ----------
    def start(self):
        self._stop.clear()
        t = threading.Thread(target=self._run, daemon=True, name="serial-bridge")
        t.start()
        self._threads.append(t)

    def stop(self):
        self._stop.set()
        if self._ser and self._ser.is_open:
            self._ser.close()

    # ---------- internals ----------
    def _connect(self):
        port = self.port or find_arduino_port()
        if not port:
            return False
        try:
            self._ser = serial.Serial(port, self.baud, timeout=0.2)
            time.sleep(2.0)  # Uno auto-resets when port opens
            log.info("Arduino connected on %s", port)
            return True
        except serial.SerialException as e:
            log.warning("Serial open failed: %s", e)
            return False

    def _run(self):
        while not self._stop.is_set():
            if not (self._ser and self._ser.is_open):
                if not self._connect():
                    time.sleep(2.0)
                    continue
            try:
                self._send_metrics()
                self._read_commands()
            except (serial.SerialException, OSError) as e:
                log.warning("Serial lost: %s", e)
                try:
                    self._ser.close()
                except Exception:
                    pass
                self._ser = None
                continue
            time.sleep(self.interval)

    def _send_metrics(self):
        s = self.snapshot_fn()
        line = format_metrics(s)
        self._ser.write(line.encode("ascii", "ignore"))

    def _read_commands(self):
        while self._ser.in_waiting:
            raw = self._ser.readline().decode("ascii", "ignore").strip()
            if raw.startswith("C|"):
                cmd = parse_command(raw)
                if not cmd:
                    continue
                log.info("Arduino command: %s", cmd)
                try:
                    self.on_command(cmd)
                except Exception:
                    log.exception("Command handler failed")


# ---------- standalone hardware test (no WebRTC needed) ----------
if __name__ == "__main__":
    import random

    logging.basicConfig(level=logging.INFO)
    state = {"gateway": "ON", "mode": "NORMAL"}

    def fake_snapshot():
        lat = random.randint(20, 220)
        return {
            "gateway": state["gateway"],
            "calls": random.randint(0, 2),
            "latency_ms": lat,
            "packets": random.randint(1000, 9999),
            "plugin": "NONE",
            "mode": state["mode"],
            "health": "HIGHLAT" if lat > 150 else "OK",
        }

    def handle(cmd):
        if cmd == "START":
            state["gateway"] = "ON"
        elif cmd == "STOP":
            state["gateway"] = "OFF"
        elif cmd == "RESTART":
            state["gateway"] = "OFF"
            time.sleep(1)
            state["gateway"] = "ON"
        elif cmd == "MAINT":
            state["mode"] = "MAINT" if state["mode"] == "NORMAL" else "NORMAL"

    b = SerialBridge(fake_snapshot, handle)
    b.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        b.stop()