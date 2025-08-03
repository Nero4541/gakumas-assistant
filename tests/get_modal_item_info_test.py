from src.utils.game_tools import modal_body_extract_item_info
import cv2

img = cv2.imread("Trade Confirm Modal Body.png")

item, item_info = modal_body_extract_item_info(img)

cv2.imshow("img", img)
cv2.imshow("item", item)
cv2.imshow("item_info", item_info)

cv2.waitKey(0)