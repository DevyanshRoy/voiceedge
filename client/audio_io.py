# client/audio_io.py
"""Sounddevice-backed audio tracks for VoiceEdge."""

import asyncio
import queue
import threading

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
        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="int16",
            blocksize=FRAME_SAMPLES,
            device=device,
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
        frame.time_base = av.Rational(1, SAMPLE_RATE)
        self._pts += samples
        return frame

    def stop(self):
        if self._stream:
            self._stream.stop()
            self._stream.close()
        super().stop()


class SpeakerOutput:
    def __init__(self, device=None):
        self._queue = asyncio.Queue(maxsize=30)
        self._stream = sd.OutputStream(
            samplerate=SAMPLE_RATE, channels=CHANNELS, dtype="int16", device=device
        )
        self._stream.start()
        self._task = None

    def start(self, track):
        self._task = asyncio.create_task(self._consume(track))

    async def _consume(self, track):
        try:
            while True:
                frame = await track.recv()
                samples = frame.to_ndarray().astype(np.int16).reshape(-1, CHANNELS)
                try:
                    self._queue.put_nowait(samples)
                except asyncio.QueueFull:
                    await self._queue.get()
                    await self._queue.put(samples)
                await asyncio.sleep(0)
                self._stream.write(samples)
        except asyncio.CancelledError:
            raise
        except (MediaStreamError, OSError, RuntimeError):
            return

    def stop(self):
        if self._task:
            self._task.cancel()
        self._stream.stop()
        self._stream.close()
