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
from collections import deque
import io
from PIL import Image

MODEL_PATH = "keras_modelv4.h5"

# -----------USER CONFIG-----------
PUZZLE_THRESHOLD = 0.7
NOT_BUILDING_THRESHOLD = 0.7
CLICK_COOLDOWN = 3
CLICKS_BEFORE_PAUSE = 10
PAUSE_DURATION = 240
CLOSE_POPUP_CLICK_X = 1180
CLOSE_POPUP_CLICK_Y = 966

# Webhooks
BUILD_QUEUE_DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1487864780801966172/v8lNtY_ZtUwABqOlAJ2MfZ8ynqkmWDtBVZZVh1cjpTdR22OY9p26_lu_b2KzOBooNKIz"
MINIMAP_ALERT_DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1488478164740079736/bZF97zsHd_WBz1kzG1NxEVUSVaeq6wiQTA3TxaygcEiZBTiwgkhYguv69j7IjcPz0pJF"

FULL_SCREEN_REGION = (2, 80, 1512, 895)

# -----------LOAD MODEL-----------
print("Loading model...")
model = load_model(MODEL_PATH)
print("Model loaded!")

last_click_time = 0
click_count = 0

pause_event = threading.Event()

# ---------------- UI ----------------
def show_popup(message, duration=2):
    def popup():
        root = tk.Tk()
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.geometry("+0+0")

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
    notify(f"{prompt}\nHold cursor steady...", duration=2)
    winsound.Beep(800, 150)
    return pyautogui.position()

def calibrate_region(name):
    notify(f"Calibrating {name}", 2)

    notify("TOP LEFT corner\nHold...", 2)
    x1, y1 = pyautogui.position()
    winsound.Beep(900, 100)

    notify("BOTTOM RIGHT corner\nHold...", 2)
    x2, y2 = pyautogui.position()
    winsound.Beep(900, 100)

    left = min(x1, x2)
    top = min(y1, y2)
    width = abs(x2 - x1)
    height = abs(y2 - y1)

    notify(f"{name} complete", 1.5)
    return (left, top, width, height)

notify("Calibration starting...", 2)

BUTTON_X, BUTTON_Y = calibrate_point("Place cursor in CENTER of build button")
BUILD_REGION = calibrate_region("Build Button Bounding Box")
MINIMAP_REGION = calibrate_region("Minimap Bounding Box")

notify("Calibration complete. Starting bot...", 2)

# ---------------- FUNCTIONS ----------------
def get_screen(region):
    screenshot = pyautogui.screenshot(region=region)
    return np.array(screenshot)

def predict(img, model_ref):
    img = cv2.resize(img, (224, 224))
    img = img / 255.0
    img = np.expand_dims(img, axis=0)
    prediction = model_ref.predict(img, verbose=0)[0]
    return prediction

def small_idle_wiggle(x, y, amplitude=8):
    offset_x = random.randint(-amplitude, amplitude)
    offset_y = random.randint(-amplitude, amplitude)
    pyautogui.moveTo(x + offset_x, y + offset_y, duration=0.5)

def send_webhook(url, message):
    if url:
        try:
            payload = {"content": f"@everyone {message}"}
            requests.post(url, json=payload)
        except Exception as e:
            print(f"Webhook failed: {e}")

def send_webhook_with_image_np(url, message, img_np):
    try:
        data = {"content": f"@everyone {message}"}

        # pyautogui screenshots are RGB, no need to convert
        pil_img = Image.fromarray(img_np)

        buffer = io.BytesIO()
        pil_img.save(buffer, format="PNG")
        buffer.seek(0)

        files = {"file": ("screenshot.png", buffer, "image/png")}

        requests.post(url, data=data, files=files)

    except Exception as e:
        print(f"Webhook image failed: {e}")

def play_chime(frequency=1000, duration=300):
    winsound.Beep(frequency, duration)

# ---------------- MINIMAP DETECTION ----------------
def detect_yellow_flash_and_centroid(img):
    # Convert RGB → HSV correctly
    hsv = cv2.cvtColor(img, cv2.COLOR_RGB2HSV)

    lower_yellow = np.array([20, 150, 150])
    upper_yellow = np.array([35, 255, 255])

    mask = cv2.inRange(hsv, lower_yellow, upper_yellow)

    kernel = np.ones((3, 3), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_DILATE, kernel, iterations=2)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if not contours:
        return False, None

    largest = max(contours, key=cv2.contourArea)

    if cv2.contourArea(largest) < 20:
        return False, None

    M = cv2.moments(largest)
    if M["m00"] == 0:
        return False, None

    cx = int(M["m10"] / M["m00"])
    cy = int(M["m01"] / M["m00"])

    return True, (cx, cy)

def minimap_watcher():
    print("Minimap thread started.")
    detection_history = deque(maxlen=40)

    while True:
        if pause_event.is_set():
            time.sleep(1)
            continue

        img = get_screen(MINIMAP_REGION)
        detected, centroid = detect_yellow_flash_and_centroid(img)

        detection_history.append(1 if detected else 0)

        if sum(detection_history) >= 10:
            print("⚠ Stable yellow flash detected!")
            pause_event.set()

            local_x, local_y = centroid
            screen_x = MINIMAP_REGION[0] + local_x
            screen_y = MINIMAP_REGION[1] + local_y

            print(f"Clicking flash at: ({screen_x}, {screen_y})")
            pyautogui.click(screen_x, screen_y)

            # small delay to let UI update after click
            time.sleep(0.25)

            # TAKE FULL SCREEN SCREENSHOT
            full_img = get_screen(FULL_SCREEN_REGION)

            # SEND TO MINIMAP ALERT WEBHOOK
            send_webhook_with_image_np(
                MINIMAP_ALERT_DISCORD_WEBHOOK_URL,
                "Minimap alert triggered! Screenshot attached.",
                full_img
            )

            play_chime()
            detection_history.clear()

        time.sleep(0.1)

# -------- START THREAD --------
threading.Thread(target=minimap_watcher, daemon=True).start()

# ---------------- MAIN ----------------
print("Starting bot in 3 seconds...")
time.sleep(3)

try:
    while True:

        if pause_event.is_set():
            print("Bot paused due to minimap event.")
            time.sleep(1)
            continue

        screen = get_screen(BUILD_REGION)
        pred = predict(screen, model)

        building, not_building, puzzle = pred

        small_idle_wiggle(BUTTON_X, BUTTON_Y)

        print(f"Predictions → building: {building:.2f}, not_building: {not_building:.2f}, puzzle: {puzzle:.2f}")

        if puzzle > PUZZLE_THRESHOLD:
            print("Captcha DETECTED! Pausing bot.")
            play_chime()
            send_webhook(BUILD_QUEUE_DISCORD_WEBHOOK_URL, "Captcha detected in game!")

            response = pyautogui.confirm(
                text='Captcha detected!',
                title='Captcha Detected',
                buttons=['Continue', 'End']
            )

            if response == 'End':
                break
            else:
                time.sleep(5)

        elif not_building > NOT_BUILDING_THRESHOLD:
            if time.time() - last_click_time > CLICK_COOLDOWN:
                print("Clicking build button...")
                pyautogui.click(BUTTON_X, BUTTON_Y)

                last_click_time = time.time()
                click_count += 1

                if click_count >= CLICKS_BEFORE_PAUSE:
                    notify("Pausing 4 minutes...", 2)
                    time.sleep(PAUSE_DURATION)

                    notify("Clicking alternate location", 2)
                    pyautogui.click(CLOSE_POPUP_CLICK_X, CLOSE_POPUP_CLICK_Y)

                    click_count = 0

        else:
            print("Currently building...")

        time.sleep(random.uniform(0.4, 1.2))

except KeyboardInterrupt:
    print("Bot stopped manually.")