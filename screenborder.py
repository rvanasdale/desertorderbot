import pyautogui
import time

print("Move your mouse to the top-left corner of the region and wait 3 seconds...")
time.sleep(3)
x1, y1 = pyautogui.position()
print("Top-left:", x1, y1)

print("Move your mouse to the bottom-right corner of the region and wait 3 seconds...")
time.sleep(3)
x2, y2 = pyautogui.position()
print("Bottom-right:", x2, y2)

width = x2 - x1
height = y2 - y1
print(f"Region: (x={x1}, y={y1}, width={width}, height={height})")