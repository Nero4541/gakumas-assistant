import colorsys
import math
from typing import Tuple, Optional
from PIL import Image, ImageDraw, ImageFont

import cv2
import numpy as np

from src.entity.GeneralResult import GeneralResult__Threshold
from src.utils.logger import logger


def gen_color_mask(img, lower_color, upper_color):
    hsv_img = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv_img, lower_color, upper_color)
    return mask

def get_mask_contours(img, lower_color, upper_color, ksize: Tuple[int, int] = (3,3), iterations=1):
    """从图像中提取指定颜色范围的轮廓"""
    mask = gen_color_mask(img, lower_color, upper_color)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, ksize)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    mask = cv2.dilate(mask, kernel, iterations=iterations)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    return contours

def get_max_contour(contours):
    """返回最大轮廓和其边界框"""
    max_area = 0
    max_contour = None
    for contour in contours:
        area = cv2.contourArea(contour)
        if area > max_area:
            max_area = area
            max_contour = contour
    return max_contour

def extract_roi_from_mask(img, lower_color, upper_color):
    """提取最大轮廓的ROI"""
    contours = get_mask_contours(img, lower_color, upper_color, ksize=(15, 15))
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
    # cv2.waitKey(0)

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
    # logger.debug((cv2.countNonZero(mask)/total_pixels * 100))
    value = cv2.countNonZero(mask)/total_pixels * 100
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

def letterbox(img, new_shape: Tuple[int, int]=(640, 640), color: Tuple[int,int,int]=(114, 114, 114)):
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
        max_width=200, padding_x=5,
        line_spacing=2):
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
    """
    image_pil = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(image_pil)
    font = ImageFont.truetype(font_path, font_size)

    # 自动换行（按像素宽度）
    lines = []
    line = ""
    for char in text:
        w = draw.textbbox((0, 0), line + char, font=font)[2]  # 宽度
        if w <= max_width - 2 * padding_x:
            line += char
        else:
            lines.append(line)
            line = char
    if line:
        lines.append(line)

    x, y = position
    for line in lines:
        draw.text((x + padding_x, y), line, font=font, fill=color)
        y += font_size + line_spacing

    # 转回 OpenCV BGR
    return cv2.cvtColor(np.array(image_pil), cv2.COLOR_RGB2BGR)

def get_black_image(size: Tuple[int, int]) -> bytes:
    img_black = np.zeros((size[0], size[1], 3), dtype=np.uint8)
    _, encoded_image = cv2.imencode('.jpg', img_black)
    return encoded_image.tobytes()