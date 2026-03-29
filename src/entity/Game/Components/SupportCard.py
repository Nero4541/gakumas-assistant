from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:  # pragma: no cover - Pillow is optional for this component.
    Image = None
    ImageDraw = None
    ImageFont = None

from src.constants.yolo.labels.baseUI_Labels import BaseUILabels
from src.core.inference.ocr_engine import OCRService
from src.entity.Yolo import Yolo_Box, Yolo_Results
from src.utils.debug_tools import DebugTools
from src.utils.opencv_tools import (
    ConnectedComponentBox,
    count_binary_holes,
    extract_connected_component_boxes,
    normalize_binary_mask,
)
from src.utils.string_tools import MatchConfig, string_match

ocr_service = OCRService()
debug_tools = DebugTools()

REPO_ROOT = Path(__file__).resolve().parents[4]
FONT_PATH = REPO_ROOT / "assets" / "NotoSerifCJKsc-Medium.otf"
NORMALIZED_DIGIT_SIZE = (32, 24)
SYNTHETIC_DIGIT_CANVAS = (72, 56)
LIMIT_BREAK_KEYWORDS = ["上限解放", "解放可能"]


@dataclass
class SupportCard:
    index: int
    box: Yolo_Box
    level: int | None
    stars: int | None
    confidence: float
    limit_break: bool = False
    occluded: bool = False

    @classmethod
    def from_yolo_box(
        cls,
        yolo_box: Yolo_Box,
        index: int = 0,
        classifier: tuple[tuple[int, np.ndarray, np.ndarray, float], ...] | None = None,
    ) -> "SupportCard":
        return SupportCardParser(yolo_box, index=index, classifier=classifier).parse()


@dataclass
class SupportCardList:
    cards: list[SupportCard] = field(default_factory=list)
    source_frame: np.ndarray | None = field(default=None, repr=False)

    @classmethod
    def from_yolo_results(cls, yolo_result: Yolo_Results) -> "SupportCardList":
        return SupportCardListParser(yolo_result).parse()

    def __iter__(self):
        return iter(self.cards)

    def __bool__(self) -> bool:
        return bool(self.cards)

    def __len__(self) -> int:
        return len(self.cards)

    def draw_debug(self, image: np.ndarray | None = None) -> np.ndarray:
        frame = image if image is not None else self.source_frame
        if frame is None or frame.size == 0:
            raise ValueError("Support card debug image requires a source frame")

        debug_tools.clear_all()
        try:
            for item in self.cards:
                level_text = "?" if item.level is None else str(item.level)
                stars_text = "?" if item.stars is None else str(item.stars)
                limit_break_text = " LB" if item.limit_break else ""
                label = f"Lv{level_text} ★{stars_text}{limit_break_text}"
                if item.limit_break:
                    color = (0, 128, 255)
                elif item.level is not None:
                    color = (0, 200, 255)
                else:
                    color = (0, 80, 180)
                debug_tools.add_box(
                    int(item.box.x),
                    int(item.box.y),
                    int(item.box.w),
                    int(item.box.h),
                    label=label,
                    color=color,
                    duration=300,
                )
            return debug_tools.draw_boxes(frame.copy())
        finally:
            debug_tools.clear_all()


class SupportCardParser:
    def __init__(
        self,
        yolo_box: Yolo_Box,
        index: int = 0,
        classifier: tuple[tuple[int, np.ndarray, np.ndarray, float], ...] | None = None,
    ):
        self.yolo_box = yolo_box
        self.index = index
        self.classifier = classifier if classifier is not None else _build_digit_classifier()

    def parse(self) -> SupportCard:
        card_height, card_width = self.yolo_box.frame.shape[:2]
        aspect = card_height / max(1, card_width)
        if card_height < 100 or aspect < 0.45 or _is_info_band_occluded(self.yolo_box.frame):
            return SupportCard(
                index=self.index,
                box=self.yolo_box,
                level=None,
                stars=None,
                confidence=0.0,
                limit_break=False,
                occluded=True,
            )

        band, mask, _, band_height = _extract_info_band(self.yolo_box.frame)
        band_width = mask.shape[1]
        components = extract_connected_component_boxes(
            mask,
            min_area_ratio=0.003,
            min_height_ratio=0.18,
            left_edge_noise_width=3,
        )
        level, confidence, digit_end_x, _ = _extract_level_digits(
            band,
            mask,
            components,
            band_height,
            band_width,
            self.classifier,
        )

        stars = None
        limit_break = False
        if level is not None and confidence >= 0.70:
            star_count, _ = _count_stars(components, band_height, band_width, digit_end_x)
            stars = star_count
            limit_break = _detect_limit_break(self.yolo_box.frame)
        else:
            level = None

        return SupportCard(
            index=self.index,
            box=self.yolo_box,
            level=level,
            stars=stars,
            confidence=confidence,
            limit_break=limit_break,
        )


class SupportCardListParser:
    def __init__(self, yolo_result: Yolo_Results):
        self.yolo_result = yolo_result
        self.frame = yolo_result.frame

    def parse(self) -> SupportCardList:
        cards = list(self.yolo_result.filter_by_label(BaseUILabels.SUPPORT_CARD).boxes)
        if not cards:
            return SupportCardList(source_frame=self.frame.copy() if self.frame is not None else None)

        classifier = _adapt_classifier(cards, _build_digit_classifier())
        parsed_cards: list[SupportCard] = []
        for index, card in enumerate(cards):
            parsed_card = SupportCard.from_yolo_box(card, index=index, classifier=classifier)
            if parsed_card.occluded:
                continue
            parsed_cards.append(parsed_card)

        return SupportCardList(parsed_cards, self.frame.copy() if self.frame is not None else None)

    def draw_debug(self, cards: SupportCardList | None = None) -> np.ndarray:
        parsed_cards = cards if cards is not None else self.parse()
        return parsed_cards.draw_debug(self.frame)


SupportCardLevelStarInfo = SupportCard
SupportCardLevelStars = SupportCardList
SupportCardLevelStarsParser = SupportCardListParser


def _detect_limit_break(card_frame: np.ndarray) -> bool:
    big_frame = cv2.resize(card_frame, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    result = ocr_service.ocr(big_frame)
    if not result or not result.results:
        return False
    for ocr_item in result.results:
        for keyword in LIMIT_BREAK_KEYWORDS:
            if keyword in ocr_item.text:
                return True
            if string_match(ocr_item.text, keyword, MatchConfig(use_fuzz=True, fuzz_threshold=60)):
                return True
    return False


def _extract_info_band(card_frame: np.ndarray) -> tuple[np.ndarray, np.ndarray, int, int]:
    height, _ = card_frame.shape[:2]
    y_start = int(height * 0.72)
    y_end = int(height * 0.98)
    band = card_frame[y_start:y_end, :]
    band_height, _ = band.shape[:2]

    gray = cv2.cvtColor(band, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(band, cv2.COLOR_BGR2HSV)

    _, bright_mask = cv2.threshold(gray, 180, 255, cv2.THRESH_BINARY)
    hsv_mask = ((hsv[:, :, 2] > 170) & (hsv[:, :, 1] < 100)).astype(np.uint8) * 255

    enhanced = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(4, 4)).apply(gray)
    adaptive = cv2.adaptiveThreshold(
        enhanced,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        15,
        -5,
    )

    mask = cv2.bitwise_and(bright_mask, cv2.bitwise_or(hsv_mask, adaptive))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    return band, mask, y_start, band_height


def _count_stars(
    components: list[ConnectedComponentBox],
    band_height: int,
    band_width: int,
    digit_end_x: int,
) -> tuple[int, list[ConnectedComponentBox]]:
    star_min_size = band_height * 0.48
    star_max_size = band_height * 0.80
    attribute_x_threshold = band_width * 0.78

    star_candidates: list[ConnectedComponentBox] = []
    for component in components:
        if component.x < digit_end_x + 5:
            continue
        if component.x > attribute_x_threshold:
            continue
        if not (0.80 <= component.aspect <= 1.25):
            continue
        if not (star_min_size <= component.h <= star_max_size):
            continue
        if not (star_min_size <= component.w <= star_max_size):
            continue
        star_candidates.append(component)

    if len(star_candidates) > 1:
        mean_height = float(np.mean([component.h for component in star_candidates]))
        star_candidates = [
            component for component in star_candidates if abs(component.h - mean_height) < mean_height * 0.25
        ]
    if len(star_candidates) > 4:
        star_candidates = star_candidates[:4]

    return len(star_candidates), star_candidates


def _feature_vector(image: np.ndarray) -> np.ndarray:
    image = (image > 0).astype(np.uint8) * 255
    features: list[float] = []

    for y in range(0, NORMALIZED_DIGIT_SIZE[0], 8):
        for x in range(0, NORMALIZED_DIGIT_SIZE[1], 6):
            cell = image[y:y + 8, x:x + 6]
            features.append(float((cell > 0).mean()))

    grad_x = cv2.Sobel(image, cv2.CV_32F, 1, 0, ksize=3)
    grad_y = cv2.Sobel(image, cv2.CV_32F, 0, 1, ksize=3)
    magnitude, angle = cv2.cartToPolar(grad_x, grad_y)
    bins = np.int32(8 * angle / (2 * np.pi)) % 8
    for y in range(0, NORMALIZED_DIGIT_SIZE[0], 8):
        for x in range(0, NORMALIZED_DIGIT_SIZE[1], 6):
            hist = np.bincount(
                bins[y:y + 8, x:x + 6].ravel(),
                weights=magnitude[y:y + 8, x:x + 6].ravel(),
                minlength=8,
            )
            features.extend(hist.tolist())

    row_projection = (image > 0).mean(axis=1).astype(np.float32)
    col_projection = (image > 0).mean(axis=0).astype(np.float32)
    features.extend(
        np.interp(
            np.linspace(0, len(row_projection) - 1, 12),
            np.arange(len(row_projection)),
            row_projection,
        ).tolist()
    )
    features.extend(
        np.interp(
            np.linspace(0, len(col_projection) - 1, 8),
            np.arange(len(col_projection)),
            col_projection,
        ).tolist()
    )

    ys, xs = np.where(image > 0)
    if len(xs) == 0:
        features.extend([0.0, 0.0, 0.0])
    else:
        features.append(float((image > 0).mean()))
        features.append(float((xs.max() - xs.min() + 1) / max(1, ys.max() - ys.min() + 1)))
        features.append(float(count_binary_holes(image)) * 0.5)

    vector = np.asarray(features, dtype=np.float32)
    return vector / (np.linalg.norm(vector) + 1e-6)


def _augment_digit(image: np.ndarray) -> list[np.ndarray]:
    augmented: list[np.ndarray] = []
    seen: set[bytes] = set()
    for blur in (0, 1):
        for operation in ("orig", "dilate", "erode"):
            for quality in (100, 72, 48):
                candidate = image.copy()
                if operation == "dilate":
                    candidate = cv2.dilate(candidate, np.ones((2, 2), np.uint8), iterations=1)
                elif operation == "erode":
                    candidate = cv2.erode(candidate, np.ones((2, 2), np.uint8), iterations=1)
                if blur:
                    candidate = cv2.GaussianBlur(candidate, (3, 3), 0)
                if quality < 100:
                    ok, encoded = cv2.imencode(".jpg", candidate, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
                    if ok:
                        candidate = cv2.imdecode(encoded, cv2.IMREAD_GRAYSCALE)
                _, candidate = cv2.threshold(candidate, 96, 255, cv2.THRESH_BINARY)
                normalized = normalize_binary_mask(candidate, canvas_size=NORMALIZED_DIGIT_SIZE)
                signature = normalized.tobytes()
                if signature in seen:
                    continue
                seen.add(signature)
                augmented.append(normalized)
    return augmented


def _make_sample(digit: int, image: np.ndarray) -> tuple[int, np.ndarray, np.ndarray, float]:
    binary = (image > 0).astype(np.uint8)
    return digit, _feature_vector(image), binary, float(binary.sum())


@lru_cache(maxsize=1)
def _build_digit_classifier() -> tuple[tuple[int, np.ndarray, np.ndarray, float], ...]:
    samples: list[tuple[int, np.ndarray, np.ndarray, float]] = []
    canvas_height, canvas_width = SYNTHETIC_DIGIT_CANVAS
    pil_sizes = (34, 38, 42, 46)
    pil_strokes = (0, 1, 2)
    offsets = (-3, 0, 3)
    cv_variants = (
        (cv2.FONT_HERSHEY_SIMPLEX, 1.00, 2),
        (cv2.FONT_HERSHEY_DUPLEX, 0.95, 2),
        (cv2.FONT_HERSHEY_COMPLEX, 0.90, 2),
        (cv2.FONT_HERSHEY_TRIPLEX, 0.88, 2),
    )

    for digit in range(10):
        text = str(digit)
        rendered: list[np.ndarray] = []

        if Image is not None and ImageFont is not None and FONT_PATH.exists():
            for font_size in pil_sizes:
                for stroke_width in pil_strokes:
                    for offset_x in offsets:
                        for offset_y in offsets:
                            font = ImageFont.truetype(str(FONT_PATH), font_size)
                            canvas = Image.new("L", (canvas_width, canvas_height), 0)
                            draw = ImageDraw.Draw(canvas)
                            bbox = draw.textbbox((0, 0), text, font=font, stroke_width=stroke_width)
                            pos_x = (canvas_width - (bbox[2] - bbox[0])) // 2 - bbox[0] + offset_x
                            pos_y = (canvas_height - (bbox[3] - bbox[1])) // 2 - bbox[1] + offset_y
                            draw.text(
                                (pos_x, pos_y),
                                text,
                                fill=255,
                                font=font,
                                stroke_width=stroke_width,
                                stroke_fill=255,
                            )
                            rendered.append(np.asarray(canvas, dtype=np.uint8))

        for font_face, font_scale, thickness in cv_variants:
            for offset_x in offsets:
                for offset_y in offsets:
                    canvas = np.zeros((canvas_height, canvas_width), dtype=np.uint8)
                    (text_width, text_height), baseline = cv2.getTextSize(text, font_face, font_scale, thickness)
                    pos_x = max(0, (canvas_width - text_width) // 2 + offset_x)
                    pos_y = max(text_height, (canvas_height + text_height) // 2 + offset_y - baseline)
                    cv2.putText(canvas, text, (pos_x, pos_y), font_face, font_scale, 255, thickness, cv2.LINE_AA)
                    rendered.append(canvas)

        seen: set[bytes] = set()
        for image in rendered:
            for augmented in _augment_digit(image):
                signature = augmented.tobytes()
                if signature in seen:
                    continue
                seen.add(signature)
                samples.append(_make_sample(digit, augmented))

    return tuple(samples)


def _predict_digit(
    digit_image: np.ndarray,
    classifier: tuple[tuple[int, np.ndarray, np.ndarray, float], ...],
) -> tuple[int, float]:
    ranked = _rank_digit_candidates(digit_image, classifier)
    return ranked[0][0], ranked[0][1]


def _rank_digit_candidates(
    digit_image: np.ndarray,
    classifier: tuple[tuple[int, np.ndarray, np.ndarray, float], ...],
) -> list[tuple[int, float]]:
    feature = _feature_vector(digit_image)
    binary = (digit_image > 0).astype(np.uint8)
    binary_sum = float(binary.sum())

    candidates_by_digit: dict[int, list[tuple[float, np.ndarray, float]]] = {digit: [] for digit in range(10)}
    for digit, sample_feature, sample_binary, sample_sum in classifier:
        score = float(np.dot(feature, sample_feature))
        candidates_by_digit[digit].append((score, sample_binary, sample_sum))

    scores: dict[int, float] = {}
    for digit, candidates in candidates_by_digit.items():
        top_candidates = sorted(candidates, key=lambda item: item[0], reverse=True)[:8]
        combined_scores = []
        for feature_score, sample_binary, sample_sum in top_candidates:
            overlap = float(np.logical_and(binary, sample_binary).sum())
            dice = (2.0 * overlap) / max(1.0, binary_sum + sample_sum)
            combined_scores.append(feature_score * 0.65 + dice * 0.35)
        scores[digit] = float(np.mean(combined_scores[:4])) if combined_scores else -1.0

    return sorted(scores.items(), key=lambda item: item[1], reverse=True)


def _extract_level_digits(
    band: np.ndarray,
    mask: np.ndarray,
    components: list[ConnectedComponentBox],
    band_height: int,
    band_width: int,
    classifier: tuple[tuple[int, np.ndarray, np.ndarray, float], ...],
) -> tuple[int | None, float, int, list[ConnectedComponentBox]]:
    max_digit_x = band_width * 0.22
    min_digit_h = band_height * 0.55
    max_digit_h = band_height * 0.90
    min_digit_w = band_width * 0.045
    max_digit_w = band_width * 0.12

    digit_candidates: list[ConnectedComponentBox] = []
    for component in components:
        if component.x > max_digit_x:
            continue
        if not (min_digit_h <= component.h <= max_digit_h):
            continue
        if not (min_digit_w <= component.w <= max_digit_w):
            continue
        if not (0.55 <= component.aspect <= 0.88):
            continue
        digit_candidates.append(component)

    if not digit_candidates:
        return None, 0.0, int(band_width * 0.25), []

    digit_candidates.sort(key=lambda component: component.x)

    best_pair: list[ConnectedComponentBox] | None = None
    best_pair_score = -1.0
    for index in range(len(digit_candidates)):
        for next_index in range(index + 1, len(digit_candidates)):
            first = digit_candidates[index]
            second = digit_candidates[next_index]
            gap = second.x - first.x2
            avg_width = (first.w + second.w) / 2
            height_diff = abs(first.h - second.h) / max(first.h, second.h)
            if gap < -3 or gap > avg_width * 0.8 or height_diff > 0.20:
                continue
            score = 1.0 - height_diff - abs(gap / max(1, avg_width) - 0.2) * 0.3
            if score > best_pair_score:
                best_pair_score = score
                best_pair = [first, second]

    if best_pair is not None:
        digit_candidates = best_pair
    else:
        digit_candidates.sort(key=lambda component: (component.h, component.area), reverse=True)
        digit_candidates = digit_candidates[:1]

    digits: list[int] = []
    confidences: list[float] = []
    for component in digit_candidates:
        normalized = normalize_binary_mask(
            mask[component.y:component.y2, component.x:component.x2],
            canvas_size=NORMALIZED_DIGIT_SIZE,
        )
        ranked_digits = _rank_digit_candidates(normalized, classifier)
        digit, confidence = ranked_digits[0]
        if len(digit_candidates) == 1 and digit != 1 and _is_double_stroke_one(normalized):
            digit = 1
            confidence = max(confidence, 0.78)
        digits.append(digit)
        confidences.append(confidence)

    if not digits:
        return None, 0.0, int(band_width * 0.25), []

    level = int("".join(str(digit) for digit in digits))
    avg_confidence = float(np.mean(confidences))
    digit_end_x = max(component.x2 for component in digit_candidates)
    return level, avg_confidence, digit_end_x, digit_candidates


def _adapt_classifier(
    cards: list[Yolo_Box],
    classifier: tuple[tuple[int, np.ndarray, np.ndarray, float], ...],
) -> tuple[tuple[int, np.ndarray, np.ndarray, float], ...]:
    adapted = list(classifier)
    seen: set[tuple[int, bytes]] = set()

    for card in cards:
        band, mask, _, band_height = _extract_info_band(card.frame)
        band_width = mask.shape[1]
        components = extract_connected_component_boxes(
            mask,
            min_area_ratio=0.003,
            min_height_ratio=0.18,
            left_edge_noise_width=3,
        )
        level, confidence, _, digit_components = _extract_level_digits(
            band,
            mask,
            components,
            band_height,
            band_width,
            classifier,
        )
        if level is None or confidence < 0.78 or not digit_components:
            continue

        level_str = str(level)
        for index, component in enumerate(digit_components):
            normalized = normalize_binary_mask(
                mask[component.y:component.y2, component.x:component.x2],
                canvas_size=NORMALIZED_DIGIT_SIZE,
            )
            digit = int(level_str[index])
            for augmented in _augment_digit(normalized):
                signature = (digit, augmented.tobytes())
                if signature in seen:
                    continue
                seen.add(signature)
                adapted.append(_make_sample(digit, augmented))

    return tuple(adapted)


def _is_double_stroke_one(image: np.ndarray) -> bool:
    projection = (image > 0).sum(axis=0).astype(np.float32)
    if projection.size < 20:
        return False
    peak = float(projection.max())
    if peak <= 0:
        return False

    search = projection[6:18]
    if search.size == 0:
        return False
    valley_offset = int(np.argmin(search))
    valley_index = 6 + valley_offset
    valley = float(search[valley_offset])
    left_peak = float(projection[:valley_index].max()) if valley_index > 0 else 0.0
    right_peak = float(projection[valley_index + 1:].max()) if valley_index + 1 < projection.size else 0.0

    if valley > peak * 0.22:
        return False
    if left_peak < peak * 0.65 or right_peak < peak * 0.65:
        return False

    left_strong = int((projection[:valley_index] >= peak * 0.65).sum())
    right_strong = int((projection[valley_index + 1:] >= peak * 0.65).sum())
    return left_strong >= 2 and right_strong >= 2


def _is_info_band_occluded(card_frame: np.ndarray) -> bool:
    height = card_frame.shape[0]
    band = card_frame[int(height * 0.72):]
    if band.size == 0:
        return False
    hsv = cv2.cvtColor(band, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (0, 0, 40), (179, 60, 190))
    ratio = cv2.countNonZero(mask) / float(mask.shape[0] * mask.shape[1])
    return ratio >= 0.55
