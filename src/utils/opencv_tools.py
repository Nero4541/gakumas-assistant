import colorsys
import math
from dataclasses import dataclass
from typing import Tuple, Optional
from PIL import Image, ImageDraw, ImageFont

import cv2
import numpy as np

from src.entity.GeneralResult import GeneralResult__Threshold
from src.utils.logger import logger


@dataclass
class ConnectedComponentBox:
    x: int
    y: int
    w: int
    h: int

    @property
    def x2(self) -> int:
        return self.x + self.w

    @property
    def y2(self) -> int:
        return self.y + self.h

    @property
    def aspect(self) -> float:
        return self.w / max(1, self.h)

    @property
    def area(self) -> int:
        return self.w * self.h


def compute_ssim_score(first: np.ndarray, second: np.ndarray) -> float:
    """
    使用 OpenCV/Numpy 计算灰度 SSIM，避免引入 skimage/scipy 体积。
    """
    if first is None or second is None:
        return 0.0
    if first.size == 0 or second.size == 0:
        return 0.0
    if first.shape != second.shape:
        return 0.0

    if first.ndim == 3:
        first = cv2.cvtColor(first, cv2.COLOR_BGR2GRAY)
    if second.ndim == 3:
        second = cv2.cvtColor(second, cv2.COLOR_BGR2GRAY)

    first = first.astype(np.float64)
    second = second.astype(np.float64)

    c1 = (0.01 * 255) ** 2
    c2 = (0.03 * 255) ** 2

    mu1 = cv2.GaussianBlur(first, (11, 11), 1.5, borderType=cv2.BORDER_REFLECT)
    mu2 = cv2.GaussianBlur(second, (11, 11), 1.5, borderType=cv2.BORDER_REFLECT)

    mu1_sq = mu1 * mu1
    mu2_sq = mu2 * mu2
    mu1_mu2 = mu1 * mu2

    sigma1_sq = cv2.GaussianBlur(first * first, (11, 11), 1.5, borderType=cv2.BORDER_REFLECT) - mu1_sq
    sigma2_sq = cv2.GaussianBlur(second * second, (11, 11), 1.5, borderType=cv2.BORDER_REFLECT) - mu2_sq
    sigma12 = cv2.GaussianBlur(first * second, (11, 11), 1.5, borderType=cv2.BORDER_REFLECT) - mu1_mu2

    numerator = (2 * mu1_mu2 + c1) * (2 * sigma12 + c2)
    denominator = (mu1_sq + mu2_sq + c1) * (sigma1_sq + sigma2_sq + c2)
    denominator = np.where(denominator == 0, 1e-12, denominator)

    return float((numerator / denominator).mean())


def gen_color_mask(img, lower_color, upper_color):
    hsv_img = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv_img, lower_color, upper_color)
    return mask


def get_mask_contours(img, lower_color, upper_color, ksize: Tuple[int, int] = (3, 3), iterations=1, morph_open: bool = False, morph_close: bool = True):
    """从图像中提取指定颜色范围的轮廓"""
    mask = gen_color_mask(img, lower_color, upper_color)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, ksize)
    if morph_open: mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    if morph_close: mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    mask = cv2.dilate(mask, kernel, iterations=iterations)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    return contours


def extract_connected_component_boxes(
        mask: np.ndarray,
        min_area_ratio: float = 0.0,
        min_height_ratio: float = 0.0,
        left_edge_noise_width: int = 0,
        connectivity: int = 8,
) -> list[ConnectedComponentBox]:
    """从二值掩码中提取连通分量边界框。"""
    if mask is None or mask.size == 0:
        return []

    height, width = mask.shape[:2]
    num_labels, _, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=connectivity)
    min_area = height * width * min_area_ratio
    min_height = height * min_height_ratio
    components: list[ConnectedComponentBox] = []
    for label_idx in range(1, num_labels):
        x = int(stats[label_idx, cv2.CC_STAT_LEFT])
        y = int(stats[label_idx, cv2.CC_STAT_TOP])
        w = int(stats[label_idx, cv2.CC_STAT_WIDTH])
        h = int(stats[label_idx, cv2.CC_STAT_HEIGHT])
        area = int(stats[label_idx, cv2.CC_STAT_AREA])
        if area < min_area or h < min_height:
            continue
        if left_edge_noise_width > 0 and x == 0 and w <= left_edge_noise_width:
            continue
        components.append(ConnectedComponentBox(x, y, w, h))
    components.sort(key=lambda component: component.x)
    return components


def remove_small_connected_components(image: np.ndarray, min_ratio: float = 0.15) -> np.ndarray:
    """移除面积明显小于主体的二值连通分量。"""
    binary = (image > 0).astype(np.uint8)
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
    if num_labels <= 1:
        return image

    max_area = float(stats[1:, cv2.CC_STAT_AREA].max())
    area_threshold = max_area * min_ratio
    result = np.zeros_like(image)
    for label_idx in range(1, num_labels):
        if stats[label_idx, cv2.CC_STAT_AREA] >= area_threshold:
            result[labels == label_idx] = 255
    return result


def normalize_binary_mask(
        image: np.ndarray,
        canvas_size: tuple[int, int] = (32, 24),
        max_content_size: tuple[int, int] = (20, 28),
        denoise_ratio: float = 0.15,
) -> np.ndarray:
    """将二值图像规范化到固定画布尺寸。"""
    canvas_h, canvas_w = canvas_size
    fit_w, fit_h = max_content_size
    binary = (image > 0).astype(np.uint8) * 255
    binary = remove_small_connected_components(binary, min_ratio=denoise_ratio)
    ys, xs = np.where(binary > 0)
    if len(xs) == 0:
        return np.zeros((canvas_h, canvas_w), dtype=np.uint8)

    crop = binary[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    scale = min(fit_w / max(1, crop.shape[1]), fit_h / max(1, crop.shape[0]))
    resized = cv2.resize(
        crop,
        (max(1, int(round(crop.shape[1] * scale))), max(1, int(round(crop.shape[0] * scale)))),
        interpolation=cv2.INTER_NEAREST,
    )
    canvas = np.zeros((canvas_h, canvas_w), dtype=np.uint8)
    offset_y = (canvas_h - resized.shape[0]) // 2
    offset_x = (canvas_w - resized.shape[1]) // 2
    canvas[offset_y:offset_y + resized.shape[0], offset_x:offset_x + resized.shape[1]] = resized
    return canvas


def count_binary_holes(image: np.ndarray) -> int:
    """统计二值图像内部孔洞数量。"""
    binary = (image > 0).astype(np.uint8)
    padded = np.pad(binary, 1, mode="constant", constant_values=0)
    inverted = 1 - padded
    num_labels, _, stats, _ = cv2.connectedComponentsWithStats(inverted, connectivity=8)
    holes = 0
    max_y, max_x = inverted.shape
    for label_idx in range(1, num_labels):
        x, y, w, h, _ = stats[label_idx]
        if x == 0 or y == 0 or x + w >= max_x or y + h >= max_y:
            continue
        holes += 1
    return holes


def get_max_contour(contours):
    """返回最大轮廓和其边界框"""
    return max(contours, key=cv2.contourArea)


def extract_roi_from_mask(img, lower_color, upper_color, ksize: Tuple[int, int] = (15, 15), iterations=1):
    """提取最大轮廓的ROI"""
    contours = get_mask_contours(img, lower_color, upper_color, ksize=ksize, iterations=iterations)
    max_contour = get_max_contour(contours)

    if max_contour is not None:
        x, y, w, h = cv2.boundingRect(max_contour)
        logger.debug(f"max_contour: x={x}, y={y}, w={w}, h={h}")
        return x, y, w, h
    return None


def get_mark_y_position(img, lower_color, upper_color, roi_y, roi_h):
    """提取mark区域的Y位置"""
    contours = get_mask_contours(img[roi_y + roi_h:], lower_color, upper_color)
    mark_y = 0
    for contour in contours:
        _x, _y, _w, _h = cv2.boundingRect(contour)
        if _h > 5 and _w > 5:
            mark_y = min(_y, mark_y)
    return mark_y


def filter_by_rectangle_shape(contours, min_area, vertices: int = 4,epsilon_factor=0.04, threshold=0.8):
    """根据面积和矩形程度筛选轮廓"""
    rect_contours = []

    for contour in contours:
        # 面积筛选（初步去噪点）
        area = cv2.contourArea(contour)
        if area < min_area:
            continue

        # 形状近似
        perimeter = cv2.arcLength(contour, True)
        epsilon = epsilon_factor * perimeter
        approx = cv2.approxPolyDP(contour, epsilon, True)

        # 顶点数量检查（矩形特征）
        if len(approx) == vertices:
            # 规整度检查：轮廓面积与外接矩形面积的比值
            x, y, w, h = cv2.boundingRect(contour)
            bounding_rect_area = w * h

            # 形状相似度检查：比值接近 1.0 代表轮廓和它的外接矩形非常接近
            if area / bounding_rect_area > threshold:
                rect_contours.append(contour)

    return rect_contours


def hsv_range_to_image_cv(lower, upper, height=50, width=300):
    """
    用 OpenCV HSV 范围的 lower 和 upper 生成一张条形图，表示色调范围。
    """
    h_vals = np.linspace(lower[0], upper[0], width)
    s_val = (lower[1] + upper[1]) / 2
    v_val = (lower[2] + upper[2]) / 2

    img = np.zeros((height, width, 3), dtype=np.uint8)

    for i, h in enumerate(h_vals):
        h_norm = h / 179
        s_norm = s_val / 255
        v_norm = v_val / 255
        r, g, b = colorsys.hsv_to_rgb(h_norm, s_norm, v_norm)
        img[:, i, 0] = int(b * 255)
        img[:, i, 1] = int(g * 255)
        img[:, i, 2] = int(r * 255)

    cv2.imshow(f"HSV Range {upper} - {lower}", img)


def check_color(
        frame: np.ndarray,
        lower_color: Tuple[int, int, int],
        upper_color: Tuple[int, int, int],
        threshold=1
) -> GeneralResult__Threshold:
    if frame.size == 0:
        return GeneralResult__Threshold(status=False, threshold=threshold, value=0)
    hsv_roi = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv_roi, lower_color, upper_color)
    total_pixels = frame.size // frame.shape[2]
    value = cv2.countNonZero(mask) / total_pixels * 100
    return GeneralResult__Threshold(
        status=value >= threshold,
        threshold=threshold,
        value=value
    )


def check_color_in_region(
        frame: np.ndarray,
        lower_color: Tuple[int, int, int],
        upper_color: Tuple[int, int, int],
        region: Tuple[int, int, int, int],
        threshold=1
) -> GeneralResult__Threshold:
    """
    检查图像某区域是否存在指定范围的颜色
    """
    if frame.size == 0:
        return GeneralResult__Threshold(status=False, threshold=threshold, value=0)
    x, y, w, h = map(int, region)
    roi = frame[y:y + h, x:x + w]
    if roi.size == 0:
        return GeneralResult__Threshold(status=False, threshold=threshold, value=0)
    return check_color(roi, lower_color, upper_color, threshold)


def check_status_detection(
        frame: np.ndarray,
        threshold=0.15,
        upper_color: Tuple[int, int, int] = (22, 255, 255),
        lower_color: Tuple[int, int, int] = (8, 100, 100),
        background_upper_color: Optional[Tuple[int, int, int]] = None,
        background_lower_color: Optional[Tuple[int, int, int]] = None,
        black_background_threshold=0.3  # 黑色背景占比阈值
) -> GeneralResult__Threshold:
    """
    选中状态检测：默认屏蔽白色背景，黑色背景占比大时屏蔽黑色背景，
    可选屏蔽指定背景颜色（HSV范围）。
    :param frame: 帧
    :param threshold: 阈值
    :param upper_color: HSV颜色上阈值
    :param lower_color: HSV颜色下阈值
    :param background_upper_color: HSV背景颜色上阈值
    :param background_lower_color: HSV背景颜色下阈值
    :param black_background_threshold: 大于阈值，将背景识别为黑色处理
    :return:
    """
    if frame.size == 0:
        return GeneralResult__Threshold(status=False, threshold=threshold, value=0)

    lower_color = np.array(lower_color)
    upper_color = np.array(upper_color)

    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    height, width = gray.shape[:2]
    total_area = height * width

    # 白色背景掩码
    white_mask = cv2.inRange(gray, 220, 255)
    # 黑色背景掩码
    black_mask = cv2.inRange(gray, 0, 30)

    # 自定义背景掩码（若提供）
    custom_bg_mask = None
    if background_lower_color and background_upper_color:
        background_lower_color = np.array(background_lower_color)
        background_upper_color = np.array(background_upper_color)
        custom_bg_mask = cv2.inRange(hsv, background_lower_color, background_upper_color)

    black_ratio = cv2.countNonZero(black_mask) / total_area

    if black_ratio > black_background_threshold:
        mask = cv2.inRange(hsv, lower_color, upper_color)
        non_black_mask = cv2.bitwise_not(black_mask)

        # 若有自定义背景屏蔽色，也排除
        if custom_bg_mask is not None:
            non_black_mask = cv2.bitwise_and(non_black_mask, cv2.bitwise_not(custom_bg_mask))

        combined_mask = cv2.bitwise_and(mask, non_black_mask)
        non_black_area = cv2.countNonZero(non_black_mask)
        if non_black_area == 0:
            return GeneralResult__Threshold(status=False, threshold=threshold, value=0)
        orange_ratio = cv2.countNonZero(combined_mask) / non_black_area
        return GeneralResult__Threshold(
            status=orange_ratio > threshold,
            threshold=threshold,
            value=orange_ratio
        )
    else:
        mask = cv2.inRange(hsv, lower_color, upper_color)
        non_white_mask = cv2.bitwise_not(white_mask)

        # 若有自定义背景屏蔽色，也排除
        if custom_bg_mask is not None:
            non_white_mask = cv2.bitwise_and(non_white_mask, cv2.bitwise_not(custom_bg_mask))

        combined_mask = cv2.bitwise_and(mask, non_white_mask)
        non_white_area = cv2.countNonZero(non_white_mask)
        if non_white_area == 0:
            return GeneralResult__Threshold(status=False, threshold=threshold, value=0)
        orange_ratio = cv2.countNonZero(combined_mask) / non_white_area
        return GeneralResult__Threshold(
            status=orange_ratio > threshold,
            threshold=threshold,
            value=orange_ratio
        )


def letterbox(img, new_shape: Tuple[int, int] = (640, 640), color: Tuple[int, int, int] = (114, 114, 114)):
    x, y = img.shape[:2]  # current shape [height, width]
    r = min(new_shape[0] / x, new_shape[1] / y)
    new_unpad = (int(round(y * r)), int(round(x * r)))
    dw, dh = new_shape[1] - new_unpad[0], new_shape[0] - new_unpad[1]  # padding
    dw /= 2  # divide padding into 2 sides
    dh /= 2

    img = cv2.resize(img, new_unpad, interpolation=cv2.INTER_LINEAR)
    left = int(math.floor(dw))
    right = int(math.ceil(dw))
    top = int(math.floor(dh))
    bottom = int(math.ceil(dh))
    img = cv2.copyMakeBorder(img, top, bottom, left, right, cv2.BORDER_CONSTANT, value=color)
    return img, r, (dw, dh)


def center_crop(image: np.ndarray, size: int = 224) -> np.ndarray:
    """中心裁切"""
    h, w = image.shape[:2]
    start_y = (h - size) // 2
    start_x = (w - size) // 2
    cropped = image[start_y:start_y + size, start_x:start_x + size]
    assert cropped.shape[0] == size and cropped.shape[1] == size, f"Cropped shape error: {cropped.shape}"
    return cropped


def intersection_area(a_x, a_y, a_w, a_h, b_x, b_y, b_w, b_h) -> float:
    """
    计算坐标交叉区域
    :param a_x: abox x
    :param a_y: abox y
    :param a_w: abox w
    :param a_h: abox h
    :param b_x: bbox x
    :param b_y: bbox y
    :param b_w: bbox w
    :param b_h: bbox h
    :return:
    """
    x1 = max(a_x, b_x)
    y1 = max(a_y, b_y)
    x2 = min(a_x + a_w, b_x + b_w)
    y2 = min(a_y + a_h, b_y + b_h)
    iw = max(0.0, x2 - x1)
    ih = max(0.0, y2 - y1)
    return iw * ih


def draw_text(
        image: np.ndarray,
        text: str, position,
        font_path,
        font_size=20,
        color=(255, 255, 255),
        max_width=200,
        padding_x=5,
        line_spacing=2,
        center: bool = False
):
    """
    在图像上绘制支持中文/日文并自动换行的文字
    :param image: OpenCV 图像 (BGR)
    :param text: 文字
    :param position: 左上角坐标 (x, y)
    :param font_path: 字体路径
    :param font_size: 字号
    :param color: 文字颜色 (RGB)
    :param max_width: 最大行宽（像素）
    :param padding_x: 左右边距
    :param line_spacing: 行间距（像素）
    :param center: 是否让文字居中
    """
    if max_width <= padding_x * 2:
        max_width = padding_x * 2 + 1

    image_pil = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(image_pil)

    try:
        font = ImageFont.truetype(font_path, font_size)
    except IOError:
        # 如果字体加载失败，回退到默认字体（不支持中文，但防止崩溃）
        logger.warning(f"Font not found at {font_path}, utilizing default.")
        font = ImageFont.load_default()

    # 自动换行（按像素宽度）
    lines = []

    for raw_line in text.splitlines() or [""]:
        line = ""
        for char in raw_line:
            bbox = draw.textbbox((0, 0), line + char, font=font)
            w = bbox[2] - bbox[0]
            if w <= max_width - 2 * padding_x:
                line += char
            else:
                if line:
                    lines.append(line)
                    line = char
                else:
                    # 单字符就超宽，强行放入
                    lines.append(char)
                    line = ""
        if line:
            lines.append(line)

    base_x, y = position

    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        line_width = bbox[2] - bbox[0]
        line_height = bbox[3] - bbox[1]

        if center:
            # 在 max_width 范围内居中
            x = base_x + (max_width - line_width) // 2
        else:
            x = base_x + padding_x

        draw.text((x, y), line, font=font, fill=color)
        y += line_height + line_spacing
    # 转回 OpenCV BGR
    return cv2.cvtColor(np.array(image_pil), cv2.COLOR_RGB2BGR)


def get_black_image(size: Tuple[int, int]) -> bytes:
    img_black = np.zeros((size[0], size[1], 3), dtype=np.uint8)
    _, encoded_image = cv2.imencode('.png', img_black)
    return encoded_image.tobytes()


def is_white_screen(image, brightness=250):
    """
    判断截图是否是白屏
    :param image: 输入的屏幕截图（OpenCV格式）
    :param brightness: 目标亮度
    :return: 是否为白屏
    """
    # 转换为灰度图像
    gray_image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    # 计算图像的平均亮度
    avg_brightness = np.mean(gray_image)
    # 如果平均亮度接近255，表示是白屏
    return avg_brightness > brightness  # 你可以根据需要调整这个阈值


def check_frame_change(prev: np.ndarray, curr: np.ndarray, threshold: float = 0.9) -> bool:
    """
    检查帧是否变化
    :param prev: 上一帧
    :param curr: 当前帧
    :param threshold: 阈值
    :return:
    """
    score = compute_ssim_score(prev, curr)
    return score > threshold
