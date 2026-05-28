"""
uriv-syncboard / backend / app / core / camera.py
──────────────────────────────────────────────────
Stream ingestion layer.

Supports three source types
  • WEBCAM  — live V4L2 / DirectShow device
  • VIDEO   — pre-recorded file (.mp4 / .avi / .mov …)
  • IMAGES  — ordered list of still images (batch processing)

The module is intentionally synchronous (OpenCV is not async-native).
Callers run it in a thread pool or a daemon thread.

Public API
  camera = CameraStream(source_type, source)
  camera.start()
  for frame in camera:
      ...                   # numpy (H, W, 3) BGR uint8
  camera.stop()
"""

from __future__ import annotations

import logging
import time
from enum import Enum, auto
from pathlib import Path
from threading import Event, Lock
from typing import Iterator, List, Optional, Union

import cv2
import numpy as np

log = logging.getLogger(__name__)


class SourceType(str, Enum):
    WEBCAM = "webcam"
    VIDEO  = "video"
    IMAGES = "images"


class CameraStream:
    """
    Unified frame iterator over webcam / video / image sources.

    Parameters
    ----------
    source_type : SourceType
    source      : int (webcam index) | str/Path (file) | list[str] (images)
    fps_cap     : max frames per second to emit
    """

    def __init__(
        self,
        source_type: SourceType,
        source: Union[int, str, Path, List[str]],
        fps_cap: int = 30,
    ):
        self.source_type = source_type
        self.source      = source
        self.fps_cap     = fps_cap

        self._cap:        Optional[cv2.VideoCapture] = None
        self._img_list:   List[np.ndarray] = []
        self._img_cursor: int = 0

        self._running = Event()
        self._lock    = Lock()

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> "CameraStream":
        self._running.set()

        if self.source_type == SourceType.WEBCAM:
            self._cap = cv2.VideoCapture(int(self.source))
            if not self._cap.isOpened():
                raise RuntimeError(f"Cannot open webcam index {self.source}")
            log.info("Webcam opened: index %s", self.source)

        elif self.source_type == SourceType.VIDEO:
            self._cap = cv2.VideoCapture(str(self.source))
            if not self._cap.isOpened():
                raise RuntimeError(f"Cannot open video: {self.source}")
            log.info("Video opened: %s", self.source)

        elif self.source_type == SourceType.IMAGES:
            paths = self.source if isinstance(self.source, list) else [self.source]
            loaded = []
            for p in paths:
                img = cv2.imread(str(p))
                if img is not None:
                    loaded.append(img)
                    log.debug("Loaded image: %s", p)
                else:
                    log.warning("Could not load image: %s", p)
            self._img_list   = loaded
            self._img_cursor = 0
            log.info("Image batch loaded: %d frames", len(loaded))

        return self

    def stop(self):
        self._running.clear()
        with self._lock:
            if self._cap:
                self._cap.release()
                self._cap = None
        log.info("CameraStream stopped.")

    @property
    def is_running(self) -> bool:
        return self._running.is_set()

    # ── Iterator ──────────────────────────────────────────────────────────────

    def __iter__(self) -> Iterator[np.ndarray]:
        interval = 1.0 / max(self.fps_cap, 1)

        while self._running.is_set():
            t_start = time.monotonic()

            frame = self._next_frame()
            if frame is None:
                break
            yield frame

            elapsed = time.monotonic() - t_start
            sleep   = interval - elapsed
            if sleep > 0:
                time.sleep(sleep)

    def _next_frame(self) -> Optional[np.ndarray]:
        if self.source_type in (SourceType.WEBCAM, SourceType.VIDEO):
            with self._lock:
                if self._cap is None:
                    return None
                ret, frame = self._cap.read()
            if not ret:
                log.info("Stream ended.")
                return None
            return frame

        elif self.source_type == SourceType.IMAGES:
            if self._img_cursor >= len(self._img_list):
                log.info("All images processed.")
                self._running.clear()
                return None
            frame = self._img_list[self._img_cursor]
            self._img_cursor += 1
            time.sleep(1.5)           # hold each image 1.5 s so OCR can run
            return frame

        return None

    # ── Metadata ──────────────────────────────────────────────────────────────

    @property
    def frame_dimensions(self) -> Optional[tuple[int, int]]:
        """(width, height) or None if unknown."""
        if self._cap and self._cap.isOpened():
            w = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            return w, h
        if self._img_list:
            h, w = self._img_list[0].shape[:2]
            return w, h
        return None

    @property
    def total_frames(self) -> Optional[int]:
        if self.source_type == SourceType.VIDEO and self._cap:
            n = int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT))
            return n if n > 0 else None
        if self.source_type == SourceType.IMAGES:
            return len(self._img_list)
        return None
