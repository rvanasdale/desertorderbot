import time
import random
import numpy as np
import cv2
import pyautogui
from tensorflow.keras.models import load_model
import requests
import winsound  

MODEL_PATH = "keras_modelv3.1.h5" 

# Coordinates of your "build" button
BUTTON_X = 1029  # <-- CHANGE THIS
BUTTON_Y = 620   # <-- CHANGE THIS

# Screen region (necessary for accurate image classification. use screenborder.py to find these numbers.)
# Format: (left, top, width, height)
SCREEN_REGION = (2, 80, 1512, 895)

# Confidence thresholds
PUZZLE_THRESHOLD = 0.8
NOT_BUILDING_THRESHOLD = 0.7

# Minimum time between clicks (s)
CLICK_COOLDOWN = 5

# Discord webhook (optional, leave empty "" to disable)
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1487864780801966172/v8lNtY_ZtUwABqOlAJ2MfZ8ynqkmWDtBVZZVh1cjpTdR22OY9p26_lu_b2KzOBooNKIz"  

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

#otherwise build menu closes eventually, this slightly moves your mouse to keep it open
def wiggle_mouse(x, y, amplitude=30):
    pyautogui.moveTo(x, y - amplitude, duration=0.5)
    pyautogui.moveTo(x, y + amplitude, duration=0.5)
    pyautogui.moveTo(x, y, duration=0.05)

#message to discord
def alert_discord(message):
    if DISCORD_WEBHOOK_URL:
        try:
            payload = {"content": f"@everyone {message}"}
            requests.post(DISCORD_WEBHOOK_URL, json=payload)
        except Exception as e:
            print(f"Discord notification failed: {e}")

def play_chime(frequency=1000, duration=300):
    winsound.Beep(frequency, duration)


print("Starting bot in 3 seconds...")
time.sleep(3)

try:
    while True:
        screen = get_screen()
        pred = predict(screen)

        building, not_building, puzzle = pred
        print(f"Predictions → building: {building:.2f}, not_building: {not_building:.2f}, puzzle: {puzzle:.2f}")

       
        if puzzle > PUZZLE_THRESHOLD:
            print("Captcha DETECTED! Pausing bot.")
            
            
            play_chime()
            
            
            alert_discord("Captcha detected in game!")

            
            response = pyautogui.confirm(
                text='Captcha detected!',
                title='Captcha Detected',
                buttons=['Continue', 'End']
            )

            if response == 'End':
                print("Ending bot as requested.")
                break
            else:
                print("Resuming bot in 5 seconds...")
                time.sleep(5)

        elif not_building > NOT_BUILDING_THRESHOLD:
            if time.time() - last_click_time > CLICK_COOLDOWN:
                print("Clicking build button...")
                wiggle_mouse(BUTTON_X, BUTTON_Y)
                pyautogui.click(BUTTON_X, BUTTON_Y)
                last_click_time = time.time()
        else:
            print("Currently building...")

        # Random delay to look human (s), adjustable
        time.sleep(random.uniform(0.4, 1.2))

except KeyboardInterrupt:
    print("Bot stopped manually.")
