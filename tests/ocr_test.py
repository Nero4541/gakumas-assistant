# import cv2
# import numpy as np
#
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
import matplotlib.pyplot as plt

# 1. 读取图像
img = cv2.imread('tabbar.png')
target_x, target_y, _ = img.shape

hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
# 取色 抠图
mask_orange = cv2.inRange(hsv, (5,85,250), (18,255,255))
mask_gary = cv2.inRange(hsv, (0,0,0), (0,0,185))
black = np.array([0, 0, 0])  # BGR格式
white = np.array([255, 255, 255])
mask_combined = cv2.bitwise_or(mask_orange, mask_gary)
img[mask_combined > 0] = black
img[~(mask_orange > 0) & ~(mask_gary > 0)] = white

gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

_, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

# 膨胀，使同一词内字符连接
kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 5))  # 横向拉长
dilated = cv2.dilate(binary, kernel, iterations=1)

# 查找词块轮廓
contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

# 提取词块并排序
word_boxes = []
for cnt in contours:
    x, y, w, h = cv2.boundingRect(cnt)
    if w > 20 and h > 10:  # 过滤噪声
        word_boxes.append((x, y, w, h))
word_boxes = sorted(word_boxes, key=lambda b: b[0])  # 按x排序
print(f"word_boxes={word_boxes}")
fig, axs = plt.subplots(1, len(word_boxes), figsize=(15, 3))
if len(word_boxes) == 1:
    axs = [axs]
if len(word_boxes) <= 2:
    print(ocr_service.ocr(img))
else:
    for i, (x, y, w, h) in enumerate(word_boxes):
        cropped = img[y:y+h, x:x+w]
        cv2.imshow(f'cropped_{i}', cropped)
        print(ocr_service.ocr(cropped))

cv2.waitKey(0)
cv2.destroyAllWindows()
