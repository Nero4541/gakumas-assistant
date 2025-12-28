from src.utils.game_tools import modal_body_extract_item_info
from src.utils.opencv_tools import *
import cv2

img = cv2.imread(r"E:\Projects\gkmas-auto\logs\debug\images\UnknownItem\modal_body_image_9.png")

item_lower: tuple[int, int, int] = (0,0,0)
item_upper: tuple[int, int, int] = (179,90,120)
min_area: int = 50


contours = get_mask_contours(img, item_lower, item_upper, iterations=2)

contour_img = img.copy()

cv2.drawContours(contour_img, contours, -1, (0, 255, 0), 2)

cv2.imshow("Contours Result", contour_img)

def filter_by_rectangle_shape(contours, min_area, epsilon_factor=0.04):
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
        if len(approx) == 4:
            # 规整度检查：轮廓面积与外接矩形面积的比值
            x, y, w, h = cv2.boundingRect(contour)
            bounding_rect_area = w * h

            # 形状相似度检查：比值接近 1.0 代表轮廓和它的外接矩形非常接近
            if area / bounding_rect_area > 0.8:
                rect_contours.append(contour)

    return rect_contours

contours = filter_by_rectangle_shape(contours, min_area)

# 找出面积最大的轮廓
largest_contour = max(contours, key=cv2.contourArea)
# 步骤 3：获取最大轮廓的外接矩形信息
x, y, w, h = cv2.boundingRect(largest_contour)
# 最大的矩形轮廓的坐标和尺寸
print(f"最大矩形的左上角坐标: ({x}, {y})")
print(f"最大矩形的尺寸: 宽度 {w}, 高度 {h}")
# （可选）将这个最大的矩形画出来进行可视化验证
cv2.rectangle(contour_img, (x, y), (x + w, y + h), (255, 0, 0), 2)
cv2.imshow("Largest Rectangle", contour_img)
cv2.waitKey(0)
cv2.destroyAllWindows()

item, item_info = modal_body_extract_item_info(img, item_lower=item_lower, item_upper=item_upper)

cv2.imshow("img", img)
cv2.imshow("item", item)
cv2.imshow("item_info", item_info)

cv2.waitKey(0)