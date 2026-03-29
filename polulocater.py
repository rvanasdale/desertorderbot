import pyautogui
import time

print("=== Simple Button Coordinate Finder ===")
print("Move your mouse to the button and wait 3 seconds...")


time.sleep(3)


x, y = pyautogui.position()
print(f"Polu Button coordinate: x={x}, y={y}")