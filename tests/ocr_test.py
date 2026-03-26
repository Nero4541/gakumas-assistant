# import cv2
# import numpy as np
#
from copy import copy

from src.core.inference.ocr_engine import OCRService

# 创建 OCR 服务实例
ocr_service = OCRService()
#
# # 读取图像
# img = cv2.imread('tabbar2.png')
#
# hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
# mask_orange = cv2.inRange(hsv, (5,80,255), (18,255,255))
# mask_gary = cv2.inRange(hsv, (0,0,0), (0,0,180))
# mask_delimiter = cv2.inRange(hsv, (0,0,186), (0,0,236))
# black = np.array([0, 0, 0])  # BGR格式
# white = np.array([255, 255, 255])
#
# mask_combined = cv2.bitwise_or(mask_orange, mask_gary)
# img[mask_combined > 0] = black
# img[~(mask_orange > 0) & ~(mask_gary > 0)] = white
#
# # 获取 OCR 识别结果
# ocr_results = ocr_service.ocr(img)
#
# # 遍历识别结果，画框
# for result in ocr_results.results:
#     x, y, w, h = int(result.x), int(result.y), int(result.w), int(result.h)
#
#     # 在原图上画矩形框
#     cv2.rectangle(img, (x, y), (x + w, y + h), (0, 255, 0), 2)  # 绿色框，线宽 2
#
# # 显示图像
# cv2.imshow('OCR Result', img)
# print(ocr_results)
#
# # 等待按键关闭图像窗口
# cv2.waitKey(0)
# cv2.destroyAllWindows()


import cv2
import numpy as np

# 1. 读取图像
img = cv2.imread('../tabbar.jpg')
if img is None:
    print("Error: Image not found.")
    exit()

# 获取图像尺寸
height, width, _ = img.shape
hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
mask_orange = cv2.inRange(hsv, (0, 50, 0), (179, 255, 255))
mask_gray = cv2.inRange(hsv, (0, 0, 0), (0, 0, 190))
mask_combined = cv2.bitwise_or(mask_orange, mask_gray)
processed_img = np.full(img.shape, 255, dtype=np.uint8)
processed_img[mask_combined > 0] = [0, 0, 0] # 目标区域变黑
gray = cv2.cvtColor(processed_img, cv2.COLOR_BGR2GRAY)
_, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 3))
morphed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
contours, _ = cv2.findContours(morphed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

show_image = img.copy()
word_boxes = []
y_offset_limit = height // 6
for cnt in contours:
    x, y, w, h = cv2.boundingRect(cnt)
    if w > 20:
        current_center_y = y + h / 2
        offset = abs(current_center_y - height // 2)
        if offset > y_offset_limit:
            continue
        offset = 5
        new_x = max(x-offset, 0)
        new_y = max(y-offset, 0)
        new_w = min((x + w)+offset, width)
        new_h = min((y + h)+offset, height)
        cv2.rectangle(show_image, (new_x, new_y), (new_w, new_h), (0, 255, 0), 2)

        word_boxes.append((new_x, new_y, new_w, new_h))

# 按 x 坐标排序 (从左到右)
word_boxes = sorted(word_boxes, key=lambda b: b[0])

# 显示结果
print(f"检测到 {len(word_boxes)} 个文本块: {word_boxes}")
cv2.imshow('Processed Mask', morphed) # 查看二值化形态学处理后的结果
cv2.imshow('Result Boxes', show_image) # 查看最终方框
cv2.waitKey(0)
cv2.destroyAllWindows()
