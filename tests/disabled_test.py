import os.path
from time import sleep

import cv2
import numpy as np

import matplotlib.pyplot as plt

from src.utils.opencv_tools import *
#
# white_target_upper = np.array([255,255,255])
# white_target_lower = np.array([183,185,185])
# white_lower, white_upper = rgb_to_hsv_range(white_target_upper, white_target_lower)
# hsv_range_to_image_cv(white_lower, white_upper)
#
# cyan_target_upper = np.array([98,222,229])
# cyan_target_lower = np.array([78,136,160])
# cyan_lower, cyan_upper = rgb_to_hsv_range(cyan_target_upper, cyan_target_lower, 3)
# hsv_range_to_image_cv(cyan_lower, cyan_upper)
#
# orange_target_upper = np.array([243,167,66])
# orange_target_lower = np.array([175,103,83])
# orange_lower, orange_upper = rgb_to_hsv_range(orange_target_upper, orange_target_lower, 3)
# hsv_range_to_image_cv(orange_lower, orange_upper)

def is_disabled(image):
    h, w = image.shape[:2]
    total_pixels = h * w  # 总像素数
    img_hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)

    # 颜色范围定义
    color_rules = {
        'white': {
            'upper': np.array([155, 30, 255]),
            'lower': np.array([0, 0, 120]),
            'disabled_upper': np.array([106, 24, 193]),
            'disabled_lower': np.array([65, 0, 140])
        },
        'cyan': {
            'upper': np.array([98,255,255]),
            'lower': np.array([86,61,0]),
            'disabled_upper': np.array([97,169,191]),
            'disabled_lower': np.array([86,109,101])
        },
        'orange': {
            'upper': np.array([17, 255, 255]),
            'lower': np.array([0, 113, 130]),
            'disabled_upper': np.array([22, 178, 196]),
            'disabled_lower': np.array([0, 138, 176])
        },
        'transparent-grey1': {
            'upper': np.array([122, 120, 180]),
            'lower': np.array([0, 0, 90]),
            'disabled_upper': np.array([68,90,120]),
            'disabled_lower': np.array([9,0,95])
        },
        # 'grey1': {
        #     'upper': np.array([179, 90, 160]),
        #     'lower': np.array([0, 0, 108]),
        #     'disabled_upper': np.array([108, 39, 111]),
        #     'disabled_lower': np.array([16, 5, 51])
        # }
    }

    # 按顺序检查每种颜色
    for rule_name, rule in color_rules.items():
        button_mask = cv2.inRange(img_hsv, rule['lower'], rule['upper'])

        # 小于 60% 判定不是这个颜色规则所属范围
        if cv2.countNonZero(button_mask) < total_pixels * 0.50:
            continue

        print(f"rule: {rule_name}")

        mask_disabled = cv2.inRange(img_hsv, rule['disabled_lower'], rule['disabled_upper'])
        print(f"mask disabled: {(cv2.countNonZero(mask_disabled)/total_pixels)*100:.2f}%")
        if cv2.countNonZero(mask_disabled) > cv2.countNonZero(button_mask) * 0.50:
            return True
        return False

    return False


# 读取抠图后的按钮图像
base_path = os.path.join(os.getcwd(), "button_disabled_test")
for filename in os.listdir(base_path):
    if filename.endswith(".png"):
        image = cv2.imread(os.path.join(base_path, filename))
        print(filename)
        print(is_disabled(image))
        print()
        # sleep(3)
