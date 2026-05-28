"""
uriv-syncboard / backend / app / core / processor.py
─────────────────────────────────────────────────────
OCR + image-enhancement pipeline.

Primary engine  : PaddleOCR  (set OCR_ENGINE=paddle — needs ~2 GB download)
Default engine  : Tesseract  (install: brew/apt install tesseract)

FIX: cv2 import is now guarded; OCR engines lazy-load inside methods.
     Module-level imports of heavy libs caused startup crashes.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from app.core.config import settings

log = logging.getLogger(__name__)


# ── Data models ───────────────────────────────────────────────────────────────

@dataclass
class OcrLine:
    text:       str
    confidence: float
    bbox:       Optional[List] = None


@dataclass
class OcrResult:
    text:       str
    confidence: float
    lines:      List[OcrLine] = field(default_factory=list)
    latency_ms: float = 0.0

    @property
    def is_empty(self) -> bool:
        return not self.text.strip()


# ── OCR engine adapters ───────────────────────────────────────────────────────

class _PaddleAdapter:
    """Wraps PaddleOCR; lazy-loads model on first use."""

    def __init__(self):
        self._ocr = None

    def _load(self):
        if self._ocr is None:
            try:
                from paddleocr import PaddleOCR  # type: ignore
                self._ocr = PaddleOCR(
                    use_angle_cls=True,
                    lang="en",
                    show_log=False,
                    use_gpu=False,
                )
                log.info("PaddleOCR model loaded.")
            except Exception as exc:
                log.error("PaddleOCR failed to load: %s — switching to Tesseract.", exc)
                raise

    def run(self, image, min_conf: int) -> OcrResult:
        self._load()
        import numpy as np
        t0     = time.monotonic()
        result = self._ocr.ocr(image, cls=True)
        ms     = (time.monotonic() - t0) * 1000

        lines, confs = [], []
        if result and result[0]:
            for item in result[0]:
                bbox, (text, conf) = item
                c = float(conf) * 100
                if c >= min_conf and text.strip():
                    lines.append(OcrLine(text=text, confidence=c, bbox=bbox))
                    confs.append(c)

        avg_conf = sum(confs) / len(confs) if confs else 0.0
        return OcrResult(
            text=" ".join(l.text for l in lines),
            confidence=avg_conf, lines=lines, latency_ms=ms
        )


class _TesseractAdapter:
    """Wraps pytesseract — needs Tesseract binary installed on the system."""

    def run(self, image, min_conf: int) -> OcrResult:
        try:
            import pytesseract  # type: ignore
        except ImportError:
            log.error("pytesseract not installed. Run: pip install pytesseract")
            return OcrResult(text="", confidence=0.0)

        t0  = time.monotonic()
        cfg = r"--oem 3 --psm 6 -c preserve_interword_spaces=1"
        try:
            data = pytesseract.image_to_data(
                image, config=cfg,
                output_type=pytesseract.Output.DICT,
            )
        except Exception as exc:
            log.error("Tesseract error: %s — is Tesseract installed?", exc)
            return OcrResult(text="", confidence=0.0)

        ms = (time.monotonic() - t0) * 1000

        lines, confs = [], []
        for word, conf in zip(data["text"], data["conf"]):
            c = int(conf)
            if c >= min_conf and word.strip():
                lines.append(OcrLine(text=word, confidence=float(c)))
                confs.append(c)

        avg_conf = sum(confs) / len(confs) if confs else 0.0
        return OcrResult(
            text=" ".join(l.text for l in lines),
            confidence=avg_conf, lines=lines, latency_ms=ms
        )


# ── Image preprocessor ────────────────────────────────────────────────────────

class Preprocessor:
    """All OpenCV transforms applied before OCR."""

    def __init__(self):
        self.roi: Optional[Tuple[int, int, int, int]] = None

    def set_roi(self, x: int, y: int, w: int, h: int):
        self.roi = (x, y, w, h)

    def clear_roi(self):
        self.roi = None

    def apply(self, frame) -> Optional:
        """
        Returns preprocessed numpy array, or None if cv2 unavailable.
        """
        try:
            import cv2
            import numpy as np
        except ImportError:
            log.error("opencv-python not installed. Run: pip install opencv-python")
            return None

        img = self._crop(frame)
        img = self._resize(img)
        img = self._deskew(img)
        img = self._binarize(img)
        img = self._denoise(img)
        return img

    def _crop(self, frame):
        if self.roi is None:
            return frame
        x, y, w, h = self.roi
        fh, fw = frame.shape[:2]
        return frame[max(y,0):min(y+h,fh), max(x,0):min(x+w,fw)]

    def _resize(self, img):
        import cv2
        target_w = settings.ocr_width
        h, w     = img.shape[:2]
        if w == 0:
            return img
        return cv2.resize(img, (target_w, int(h * target_w / w)),
                          interpolation=cv2.INTER_LANCZOS4)

    def _deskew(self, img):
        import cv2
        import numpy as np
        try:
            gray  = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
            edges = cv2.Canny(gray, 50, 150, apertureSize=3)
            lines = cv2.HoughLines(edges, 1, np.pi / 180, threshold=100)
            if lines is None:
                return img
            angles = [np.degrees(t[0][1]) - 90 for t in lines if abs(np.degrees(t[0][1]) - 90) < 10]
            if not angles:
                return img
            angle = float(np.median(angles))
            if abs(angle) < 0.5:
                return img
            h, w = img.shape[:2]
            M = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
            return cv2.warpAffine(img, M, (w, h),
                                  flags=cv2.INTER_LANCZOS4,
                                  borderMode=cv2.BORDER_REPLICATE)
        except Exception:
            return img

    def _binarize(self, img):
        import cv2
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
        return cv2.adaptiveThreshold(
            gray, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            blockSize=settings.block_size,
            C=settings.block_c,
        )

    def _denoise(self, img):
        import cv2
        return cv2.fastNlMeansDenoising(img, h=10)


# ── Public Processor ──────────────────────────────────────────────────────────

class FrameProcessor:
    """Orchestrates preprocessing → OCR."""

    def __init__(self):
        self.preprocessor = Preprocessor()
        self._engine      = self._init_engine()

    @staticmethod
    def _init_engine():
        engine = settings.ocr_engine.lower()
        if engine == "paddle":
            try:
                return _PaddleAdapter()
            except Exception:
                log.warning("PaddleOCR unavailable — falling back to Tesseract.")
                return _TesseractAdapter()
        return _TesseractAdapter()

    def set_roi(self, x: int, y: int, w: int, h: int):
        self.preprocessor.set_roi(x, y, w, h)

    def clear_roi(self):
        self.preprocessor.clear_roi()

    def run(self, frame) -> OcrResult:
        enhanced = self.preprocessor.apply(frame)
        if enhanced is None:
            return OcrResult(text="", confidence=0.0)
        result = self._engine.run(enhanced, settings.min_confidence)
        log.debug("OCR: %d words  conf=%.1f  latency=%.0fms",
                  len(result.lines), result.confidence, result.latency_ms)
        return result
