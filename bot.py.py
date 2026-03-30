#should be good to run, just need to update main model and model path
import time
import random
import numpy as np
import cv2
import pyautogui
from tensorflow.keras.models import load_model
import requests
import winsound
import tkinter as tk
import threading

#!!!NEED TO TRAIN NEW MODEL!!!! 
MODEL_PATH = "keras_modelv4.h5"     

# -----------USER CONFIG-----------
PUZZLE_THRESHOLD = 0.7  #How certain does model have to be of captcha? max of 0.99
NOT_BUILDING_THRESHOLD = 0.7 #How certain does model have to be of building? 
CLICK_COOLDOWN = 3 #minimum time between clicks (s)
CLICKS_BEFORE_PAUSE = 10 #amount of clicks before pause (preset for polu)
CLOSE_POPUP_CLICK_X = 1180  # <-- SET 
CLOSE_POPUP_CLICK_Y = 966  # <-- SET
BUILD_QUEUE_DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1487864780801966172/v8lNtY_ZtUwABqOlAJ2MfZ8ynqkmWDtBVZZVh1cjpTdR22OY9p26_lu_b2KzOBooNKIz"  

#---------BETA CONFIG (UNUSED) -----------
MINIMAP_ALERT_DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/..."
FULL_SCREEN_REGION = (2, 80, 1512, 895)


#-------INITIALIZE-------
print("Loading model...")
model = load_model(MODEL_PATH)
print("Model loaded!")
last_click_time = 0
click_count = 0

# ---------------- GUIDED CALIBRATION ----------------
def show_popup(message, duration=2):
    def popup():
        root = tk.Tk()
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.geometry("+0+0")  # top-left

        label = tk.Label(root, text=message, font=("Arial", 12),
                         bg="black", fg="white", padx=10, pady=5)
        label.pack()

        root.after(int(duration * 1000), root.destroy)
        root.mainloop()

    threading.Thread(target=popup, daemon=True).start()

def notify(message, duration=2, freq=1200):
    winsound.Beep(freq, 200)
    show_popup(message, duration)
    time.sleep(duration)

def calibrate_point(prompt):
    notify(f"{prompt}\nHold cursor steady...", duration=4)
    winsound.Beep(800, 150)
    return pyautogui.position()

def calibrate_region(name):
    notify(f"Calibrating {name}", 4)

    notify("TOP LEFT corner\nHold...", 4)
    x1, y1 = pyautogui.position()
    winsound.Beep(500, 100)

    notify("BOTTOM RIGHT corner\nHold...", 4)
    x2, y2 = pyautogui.position()
    winsound.Beep(500, 100)

    left = min(x1, x2)
    top = min(y1, y2)
    width = abs(x2 - x1)
    height = abs(y2 - y1)

    notify(f"{name} complete", 1.5)

    return (left, top, width, height)

notify("Calibration starting...", 4)

BUTTON_X, BUTTON_Y = calibrate_point("Place cursor in CENTER of build button")
BUILD_REGION = calibrate_region("Build Button Bounding Box")
MINIMAP_REGION = calibrate_region("Minimap Bounding Box")

notify("Calibration complete. Starting bot...", 2)

# ---------------- FUNCTIONS ----------------

def get_screen():
    screenshot = pyautogui.screenshot(region=BUILD_REGION)
    return np.array(screenshot)

def predict(img):
    img = cv2.resize(img, (224, 224))
    img = img / 255.0
    img = np.expand_dims(img, axis=0)
    prediction = model.predict(img, verbose=0)[0]
    return prediction

def small_idle_wiggle(x, y, amplitude=8):
    offset_x = random.randint(-amplitude, amplitude)
    offset_y = random.randint(-amplitude, amplitude)
    pyautogui.moveTo(x + offset_x, y + offset_y, duration=0.5)

def alert_discord(message):
    if BUILD_QUEUE_DISCORD_WEBHOOK_URL:
        try:
            payload = {"content": f"@everyone {message}"}
            requests.post(BUILD_QUEUE_DISCORD_WEBHOOK_URL, json=payload)
        except Exception as e:
            print(f"Discord notification failed: {e}")

def play_chime(frequency=1000, duration=300):
    winsound.Beep(frequency, duration)

# ---------------- MAIN ----------------
print("Starting bot in 2 seconds...")
time.sleep(2)

try:
    while True:
        screen = get_screen()
        pred = predict(screen)

        building, not_building, puzzle = pred

        small_idle_wiggle(BUTTON_X, BUTTON_Y)

        # DEBUG
        print(f"Predictions → building: {building:.2f}, not_building: {not_building:.2f}, puzzle: {puzzle:.2f}")

        # -------- CAPTCHA --------
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
                print("Resuming bot in 4 seconds...")
                time.sleep(4)

        # -------- BUILD --------
        elif not_building > NOT_BUILDING_THRESHOLD:
            if time.time() - last_click_time > CLICK_COOLDOWN:
                print("Clicking build button...")
                pyautogui.click(BUTTON_X, BUTTON_Y)

                last_click_time = time.time()
                click_count += 1

                if click_count >= CLICKS_BEFORE_PAUSE:
                    print("Reached 10 clicks. Waiting until not building...")
                    while True:
                        screen = get_screen()
                        pred = predict(screen)
                        building, not_building, puzzle = pred

                        print(f"[WAIT] building: {building:.2f}, not_building: {not_building:.2f}")

                        if not_building > NOT_BUILDING_THRESHOLD:
                            break

                        time.sleep(1)

                    pyautogui.click(CLOSE_POPUP_CLICK_X, CLOSE_POPUP_CLICK_Y)

                    click_count = 0

        else:
            print("Currently building...")

        time.sleep(random.uniform(0.4, 1.2))

except KeyboardInterrupt:
    print("Bot stopped manually.")



