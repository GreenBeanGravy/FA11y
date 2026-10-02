"""OCR manager tests against the real RapidOCR engine."""
import cv2
import numpy as np
import pytest

pytest.importorskip("rapidocr")

from lib.managers.ocr_manager import get_ocr_manager


def _render(text, scale=1.4):
    """White text on black, thresholded and upscaled like FA11y's HUD crops."""
    (w, h), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_DUPLEX, scale, 2)
    img = np.zeros((h + 24, w + 24), np.uint8)
    cv2.putText(img, text, (12, h + 12), cv2.FONT_HERSHEY_DUPLEX, scale, 255, 2)
    return cv2.resize(img, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)


@pytest.fixture(scope="module")
def ocr():
    manager = get_ocr_manager()
    assert manager.is_ready(timeout=60), "RapidOCR failed to load"
    return manager


def test_read_numbers_returns_digits_only(ocr):
    results = ocr.read_numbers(_render("247"), allowlist="0123456789")
    assert len(results) == 1
    box, text, confidence = results[0]
    assert text == "247"
    assert len(box) == 4 and 0 <= confidence <= 1
    assert ocr.read_numbers(_render("247"), detail=0) == ["247"]


def test_read_text_returns_boxes_and_text(ocr):
    results = ocr.read_text(_render("Pump Shotgun"), paragraph=False, min_size=5)
    assert " ".join(r[1] for r in results).lower() == "pump shotgun"
    assert all(len(r[0]) == 4 for r in results)


def test_read_text_after_read_numbers_still_detects(ocr):
    # RapidOCR keeps per-call stage flags; text reading must not inherit
    # read_numbers' recognition-only mode.
    ocr.read_numbers(_render("12"))
    assert ocr.read_text(_render("Med Kit"), detail=0)


def test_blank_image_reads_nothing(ocr):
    blank = np.zeros((60, 240), np.uint8)
    assert ocr.read_text(blank) == []
    assert ocr.read_numbers(blank) == []
