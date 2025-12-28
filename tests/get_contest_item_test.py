import cv2
import numpy as np

# 加载图像
img = cv2.imread(r"E:\Projects\gkmas-auto\logs\debug\images\NotEnoughContests\contest_area__0.png")
hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

# HSV颜色范围（你提供的）
lower_hsv = np.array([90, 10, 120])
upper_hsv = np.array([104, 64, 142])

# 颜色提取
mask = cv2.inRange(hsv, lower_hsv, upper_hsv)

# 闭运算连接碎块
kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

# 膨胀扩大连通区域（可选）
mask = cv2.dilate(mask, kernel, iterations=1)

# 查找轮廓
contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

# 创建一个空白图用于显示有效轮廓
result = img.copy()

# 筛选并绘制较大的轮廓（去除噪点）
for cnt in contours:
    area = cv2.contourArea(cnt)
    if area > 200:  # 面积阈值，根据你图像调节
        cv2.drawContours(result, [cnt], -1, (0, 255, 0), 2)

# 显示结果
cv2.imshow("Original", img)
cv2.imshow("Mask", mask)
cv2.imshow("Contours - Filtered", result)
cv2.waitKey(0)
cv2.destroyAllWindows()
