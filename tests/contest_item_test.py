import cv2
import numpy as np
from src.utils.opencv_tools import *

# 读取图像
img = cv2.imread(r"E:\Projects\gkmas-auto\logs\debug\images\NotEnoughContests\contest_area__0.png")

# d = 9  # 滤波窗口大小
# sigma_color = 75  # 控制颜色平滑度
# sigma_space = 75  # 控制空间平滑度
# img = cv2.bilateralFilter(img, d, sigma_color, sigma_space)

height, width, _ = img.shape

def _get_contest_items():
    lower1 = (0,0,75)
    upper1 = (179,75,140)
    lower2 = (0,0,235)
    upper2 = (179,15,255)
    # cut_mask_lower = (0,0,40)
    # cut_mask_upper = (179,255,73)
    # cut_mask = cv2.inRange(img, cut_mask_lower, cut_mask_upper)
    mask1 = gen_color_mask(img, lower1, upper1)
    mask2 = gen_color_mask(img, lower2, upper2)
    mask = cv2.bitwise_or(mask1, mask2)
    cv2.imshow('mask1', mask)
    # mask = cv2.bitwise_and(mask, cv2.bitwise_not(cut_mask))
    # cv2.imshow('mask2', mask)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3,3))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    # mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.dilate(mask, kernel, iterations=2)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    result = img.copy()
    cv2.drawContours(result, contours, -1, (255, 0, 0), 2)
    cv2.imshow("Contours Result", result)
    total_pixels = height * width  # 总像素数
    # contours = filter_by_rectangle_shape(contours, total_pixels // 4, threshold=0.6)
    print(contours)
    # 依次提取每个区域
    for index, cnt in enumerate(contours):
        x, y, w, h = cv2.boundingRect(cnt)

        # 筛选条件 宽度必须大于帧宽度的一半
        if w > width // 2 and h > height // 4:
            print(x, y, w, h)
            roi = img[y:y+h, x:x+w]
            # self._append_contest(x, box_y := self._start_y+y, x+w, box_y+h, roi)
            cv2.drawContours(result, [cnt], -1, (0, 255, 0), 2)
            continue
        cv2.drawContours(result, [cnt], -1, (0, 0+index*10, 255), 2)
    cv2.imshow("Contours - Filtered", result)
    cv2.waitKey(0)


_get_contest_items()