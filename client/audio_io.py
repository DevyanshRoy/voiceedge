# client/audio_io.py
"""Sounddevice-backed audio tracks for VoiceEdge."""

import asyncio
from fractions import Fraction
import logging
import queue
import threading

log = logging.getLogger("voiceedge.audio")

import av
import numpy as np
import sounddevice as sd
from aiortc.mediastreams import AudioStreamTrack, MediaStreamError

SAMPLE_RATE = 48000
CHANNELS = 1
FRAME_SAMPLES = 960


class MicrophoneAudioTrack(AudioStreamTrack):
    kind = "audio"

    def __init__(self, device=None):
        super().__init__()
        self.muted = False
        self._queue = queue.Queue(maxsize=20)
        self._pts = 0
        try:
            self._stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype="int16",
                blocksize=FRAME_SAMPLES,
                device=device,
                callback=self._callback,
            )
        except Exception:
            self._stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype="int16",
                blocksize=FRAME_SAMPLES,
                device=None,
                callback=self._callback,
            )
        self._stream.start()

    def _callback(self, data, _frames, _time, _status):
        try:
            self._queue.put_nowait(np.asarray(data, dtype=np.int16).copy())
        except queue.Full:
            try:
                self._queue.get_nowait()
                self._queue.put_nowait(np.asarray(data, dtype=np.int16).copy())
            except queue.Empty:
                pass

    async def recv(self):
        data = await asyncio.to_thread(self._queue.get)
        if self.muted:
            data.fill(0)
        samples = data.shape[0]
        frame = av.AudioFrame.from_ndarray(data.T, format="s16", layout="mono")
        frame.sample_rate = SAMPLE_RATE
        frame.pts = self._pts
        frame.time_base = Fraction(1, SAMPLE_RATE)
        self._pts += samples
        return frame

    def stop(self):
        if self._stream:
            self._stream.stop()
            self._stream.close()
        super().stop()


class AudioBuffer:
    def __init__(self):
        self._lock = threading.Lock()
        self._buffer = bytearray()

    def write(self, data: bytes):
        with self._lock:
            max_bytes = int(SAMPLE_RATE * 2 * 2 * 0.25)
            if len(self._buffer) > max_bytes:
                del self._buffer[:len(self._buffer) - max_bytes]
            self._buffer.extend(data)

    def read(self, num_bytes: int) -> bytes:
        with self._lock:
            available = len(self._buffer)
            if available >= num_bytes:
                chunk = bytes(self._buffer[:num_bytes])
                del self._buffer[:num_bytes]
                return chunk
            elif available > 0:
                chunk = bytes(self._buffer) + b"\x00" * (num_bytes - available)
                self._buffer.clear()
                return chunk
            else:
                return b"\x00" * num_bytes


class SpeakerOutput:
    def __init__(self, device=None):
        self._buf = AudioBuffer()
        self.channels = 2
        self._task = None
        self._stream = None

        for ch in (2, 1):
            try:
                self.channels = ch
                self._stream = sd.OutputStream(
                    samplerate=SAMPLE_RATE,
                    channels=self.channels,
                    dtype="int16",
                    blocksize=FRAME_SAMPLES,
                    device=device,
                    callback=self._callback,
                )
                break
            except Exception:
                continue

        if not self._stream:
            self.channels = 2
            self._stream = sd.OutputStream(
                samplerate=SAMPLE_RATE,
                channels=self.channels,
                dtype="int16",
                blocksize=FRAME_SAMPLES,
                device=None,
                callback=self._callback,
            )
        self._stream.start()

    def _callback(self, outdata, frames, time_info, status):
        try:
            raw = self._buf.read(outdata.nbytes)
            outdata[:] = np.frombuffer(raw, dtype=np.int16).reshape(outdata.shape)
        except Exception:
            outdata.fill(0)

    def start(self, track):
        self._task = asyncio.create_task(self._consume(track))

    async def _consume(self, track):
        try:
            while True:
                frame = await track.recv()
                data = frame.to_ndarray().astype(np.int16)
                if data.ndim == 2:
                    if self.channels == 2:
                        samples = data.T.copy() if data.shape[0] == 2 else np.repeat(data.T, 2, axis=1)
                    else:
                        samples = data.mean(axis=0, dtype=np.int16).reshape(-1, 1)
                else:
                    samples = data.reshape(-1, self.channels)

                self._buf.write(samples.tobytes())
        except asyncio.CancelledError:
            raise
        except (MediaStreamError, OSError, RuntimeError) as exc:
            log.info("Audio stream ended: %s", exc)
            return
        except Exception:
            log.exception("Unexpected error in SpeakerOutput consumer")
            return

    def stop(self):
        if self._task:
            self._task.cancel()
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
