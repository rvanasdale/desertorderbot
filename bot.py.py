import time
import random
import numpy as np
import cv2
import pyautogui
from tensorflow.keras.models import load_model

MODEL_PATH = "keras_modelv2.h5" 

# Coordinates of your "build" button
BUTTON_X = 1029  # <-- CHANGE THIS
BUTTON_Y = 620  # <-- CHANGE THIS

# Screen region (necessary for accurate image classification. use screenborder.py to find these numbers.)
# Format: (left, top, width, height)
SCREEN_REGION = (2, 80, 1512, 895)

# Confidence thresholds
PUZZLE_THRESHOLD = 0.90
NOT_BUILDING_THRESHOLD = 0.85

# Minimum time between clicks (s)
CLICK_COOLDOWN = 5

print("Loading model...")
model = load_model(MODEL_PATH)
print("Model loaded!")

last_click_time = 0

def get_screen():
    screenshot = pyautogui.screenshot(region=SCREEN_REGION)
    return np.array(screenshot)


def predict(img):
    img = cv2.resize(img, (224, 224)) 
    img = img / 255.0
    img = np.expand_dims(img, axis=0)

    prediction = model.predict(img, verbose=0)[0]
    return prediction


print("Starting bot in 3 seconds... ")
time.sleep(3)

try:
    while True:
        screen = get_screen()
        pred = predict(screen)

        
        building, not_building, puzzle = pred

        print(f"Predictions → building: {building:.2f}, not_building: {not_building:.2f}, puzzle: {puzzle:.2f}")

        
        if puzzle > PUZZLE_THRESHOLD:
            print("PUZZLE DETECTED! Stopping bot.")
            pyautogui.alert("Puzzle reward detected!")
            break

        
        elif not_building > NOT_BUILDING_THRESHOLD:
            if time.time() - last_click_time > CLICK_COOLDOWN:
                print("Clicking build button...")
                pyautogui.click(BUTTON_X, BUTTON_Y)
                last_click_time = time.time()

        else:
            print("Currently building...")

        # Random delay to look human (s), adjustable
        time.sleep(random.uniform(0.4, 1.6))

except KeyboardInterrupt:
    print("Bot stopped manually.")