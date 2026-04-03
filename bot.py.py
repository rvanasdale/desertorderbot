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
MINIMAP_ALERT_SETTLE_DELAY = 5
MINIMAP_ALERT_COOLDOWN = 90
BASE_ALERT_PING_COOLDOWN = 20 * 60
BOTTOM_MASK_HEIGHT = 200
YELLOW_FLASH_CONFIRMATIONS = 10
MIN_FLASH_CONTOUR_AREA = 125

MODE_REGULAR = "regular"
MODE_OVERSEER = "overseer"

last_click_time = 0
click_count = 0
last_base_alert_ping_time = 0
pause_event = threading.Event()


# ---------------- UI ----------------
def show_popup(message, duration=2):
    def popup():
        root = tk.Tk()
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.geometry("+0+0")

        label = tk.Label(
            root,
            text=message,
            font=("Arial", 12),
            bg="black",
            fg="white",
            padx=10,
            pady=5,
        )
        label.pack()

        root.after(int(duration * 1000), root.destroy)
        root.mainloop()

    threading.Thread(target=popup, daemon=True).start()


def notify(message, duration=2, freq=1200):
    winsound.Beep(freq, 200)
    show_popup(message, duration)
    time.sleep(duration)


def choose_mode():
    choice = pyautogui.confirm(
        text="Choose bot mode.",
        title="Tempbot Mode",
        buttons=["Regular", "Overseer"],
    )

    if choice == "Overseer":
        print("Overseer mode selected.")
        return MODE_OVERSEER

    print("Regular mode selected.")
    return MODE_REGULAR


def calibrate_point(prompt):
    notify(f"{prompt}\nHold cursor steady...", duration=2)
    winsound.Beep(800, 150)
    return pyautogui.position()


def calibrate_region(name):
    notify(f"Calibrating {name}", 4)

    notify("TOP LEFT corner\nHold...", 4)
    x1, y1 = pyautogui.position()
    winsound.Beep(900, 100)

    notify("BOTTOM RIGHT corner\nHold...", 4)
    x2, y2 = pyautogui.position()
    winsound.Beep(900, 100)

    left = min(x1, x2)
    top = min(y1, y2)
    width = abs(x2 - x1)
    height = abs(y2 - y1)

    notify(f"{name} complete", 1.5)
    return (left, top, width, height)


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


def format_webhook_content(message, mention_everyone=False):
    return f"@attacknotify {message}" if mention_everyone else message


def send_webhook(url, message, mention_everyone=False):
    if not url:
        return

    try:
        payload = {"content": format_webhook_content(message, mention_everyone)}
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Webhook failed: {e}")


def send_webhook_with_image_np(url, message, img_np, mention_everyone=False):
    if not url:
        return

    try:
        data = {"content": format_webhook_content(message, mention_everyone)}
        pil_img = Image.fromarray(img_np)

        buffer = io.BytesIO()
        pil_img.save(buffer, format="PNG")
        buffer.seek(0)

        files = {"file": ("screenshot.png", buffer, "image/png")}

        requests.post(url, data=data, files=files, timeout=15)
    except Exception as e:
        print(f"Webhook image failed: {e}")


def send_base_alert_webhook_with_image(url, message, img_np):
    global last_base_alert_ping_time

    now = time.time()
    should_ping = (now - last_base_alert_ping_time) >= BASE_ALERT_PING_COOLDOWN

    send_webhook_with_image_np(
        url,
        message,
        img_np,
        mention_everyone=should_ping,
    )

    if should_ping:
        last_base_alert_ping_time = now
        print("Base alert sent with @attacknotify ping.")
    else:
        remaining = int(BASE_ALERT_PING_COOLDOWN - (now - last_base_alert_ping_time))
        print(f"Base alert sent without ping. Ping cooldown remaining: {remaining}s")


def play_chime(frequency=1000, duration=300):
    winsound.Beep(frequency, duration)


def get_blue_mask(img):
    hsv = cv2.cvtColor(img, cv2.COLOR_RGB2HSV)

    lower_blue = np.array([90, 95, 100])
    upper_blue = np.array([140, 255, 255])

    blue_mask = cv2.inRange(hsv, lower_blue, upper_blue)

    kernel = np.ones((3, 12), np.uint8)
    blue_mask = cv2.dilate(blue_mask, kernel, iterations=2)

    return blue_mask


def detect_blue_text(img):
    blue_mask = get_blue_mask(img)
    contours, _ = cv2.findContours(blue_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    best = None
    best_score = 0

    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        aspect = w / float(h)

        if h < 30 or aspect < 0 or w < 100:
            continue

        roi_blue = blue_mask[y : y + h, x : x + w]
        blue = np.sum(roi_blue > 0)

        if blue < 50:
            continue

        score = blue * 3 + w * 2 - h * 2

        if score > best_score:
            best_score = score
            best = (x, y, w, h, blue)

    return best


def obscure_region_in_image(img, source_region, target_region):
    source_left, source_top, source_width, source_height = source_region
    target_left, target_top, target_width, target_height = target_region

    overlap_left = max(source_left, target_left)
    overlap_top = max(source_top, target_top)
    overlap_right = min(source_left + source_width, target_left + target_width)
    overlap_bottom = min(source_top + source_height, target_top + target_height)

    if overlap_left >= overlap_right or overlap_top >= overlap_bottom:
        return

    x1 = overlap_left - source_left
    y1 = overlap_top - source_top
    x2 = overlap_right - source_left
    y2 = overlap_bottom - source_top

    img[y1:y2, x1:x2] = 0


def prepare_base_detection_image(full_img):
    masked_img = full_img.copy()
    obscure_region_in_image(masked_img, FULL_SCREEN_REGION, MINIMAP_REGION)

    bottom_start = max(masked_img.shape[0] - BOTTOM_MASK_HEIGHT, 0)
    masked_img[bottom_start:, :] = 0

    return masked_img


def detect_blue_base_name(full_img):
    masked_img = prepare_base_detection_image(full_img)
    best = detect_blue_text(masked_img)
    return best is not None, best


# ---------------- SETUP ----------------
BOT_MODE = choose_mode()

model = None
if BOT_MODE == MODE_REGULAR:
    print("Loading model...")
    model = load_model(MODEL_PATH)
    print("Model loaded!")
else:
    print("Skipping model load in overseer mode.")

notify("Calibration starting...", 3)

BASE_X, BASE_Y = calibrate_point("Place cursor on your BASE on the minimap")
BUTTON_X, BUTTON_Y = calibrate_point("Place cursor in CENTER of build button")
BUILD_REGION = calibrate_region("Build Button Bounding Box")
MINIMAP_REGION = calibrate_region("Minimap Bounding Box")

notify("Calibration complete. Starting bot...", 2)


# ---------------- MINIMAP DETECTION ----------------
def detect_yellow_flash_and_centroid(img):
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

    if cv2.contourArea(largest) < MIN_FLASH_CONTOUR_AREA:
        return False, None

    moments = cv2.moments(largest)
    if moments["m00"] == 0:
        return False, None

    cx = int(moments["m10"] / moments["m00"])
    cy = int(moments["m01"] / moments["m00"])

    return True, (cx, cy)


def minimap_watcher():
    print("Minimap thread started.")
    detection_history = deque(maxlen=40)
    last_centroid = None

    while True:
        if pause_event.is_set():
            time.sleep(1)
            continue

        img = get_screen(MINIMAP_REGION)
        detected, centroid = detect_yellow_flash_and_centroid(img)

        if detected:
            last_centroid = centroid

        detection_history.append(1 if detected else 0)

        if sum(detection_history) >= YELLOW_FLASH_CONFIRMATIONS:
            target_centroid = centroid if centroid is not None else last_centroid

            if target_centroid is None:
                print("Stable flash detected, but no centroid was available.")
                detection_history.clear()
                time.sleep(0.1)
                continue

            print("Stable yellow flash detected!")
            pause_event.set()

            try:
                local_x, local_y = target_centroid
                screen_x = MINIMAP_REGION[0] + local_x
                screen_y = MINIMAP_REGION[1] + local_y

                print(f"Clicking flash at: ({screen_x}, {screen_y})")
                pyautogui.click(screen_x, screen_y)

                time.sleep(MINIMAP_ALERT_SETTLE_DELAY)

                full_img = get_screen(FULL_SCREEN_REGION)
                blue_base_detected, blue_text_box = detect_blue_base_name(full_img)

                if blue_base_detected:
                    x, y, w, h, _ = blue_text_box
                    print(f"Blue base name detected at ({x}, {y}, {w}, {h}).")
                    alert_message = "Minimap alert triggered! Attack on friendly base detected. Screenshot attached."
                    send_base_alert_webhook_with_image(
                        MINIMAP_ALERT_DISCORD_WEBHOOK_URL,
                        alert_message,
                        full_img,
                    )
                else:
                    print("No blue base name detected.")
                    alert_message = "Minimap alert triggered! No friendly base detected. Screenshot attached."
                    # send_webhook_with_image_np(
                    #     MINIMAP_ALERT_DISCORD_WEBHOOK_URL,
                    #     alert_message,
                    #     full_img,
                    #     mention_everyone=False,
                    # )

                print(f"Returning to base at: ({BASE_X}, {BASE_Y})")
                pyautogui.click(BASE_X, BASE_Y)

                play_chime()
                print(f"Cooldown started for {MINIMAP_ALERT_COOLDOWN} seconds.")
                time.sleep(MINIMAP_ALERT_COOLDOWN)
            finally:
                detection_history.clear()
                last_centroid = None
                pause_event.clear()

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

        small_idle_wiggle(BUTTON_X, BUTTON_Y)

        if BOT_MODE == MODE_OVERSEER:
            print("Overseer mode active: idle wiggle only, minimap watcher still running.")
            time.sleep(random.uniform(0.8, 1.5))
            continue

        screen = get_screen(BUILD_REGION)
        pred = predict(screen, model)

        building, not_building, puzzle = pred

        print(
            f"Predictions -> building: {building:.2f}, "
            f"not_building: {not_building:.2f}, puzzle: {puzzle:.2f}"
        )

        if puzzle > PUZZLE_THRESHOLD:
            print("Captcha DETECTED! Pausing bot.")
            play_chime()
            send_webhook(BUILD_QUEUE_DISCORD_WEBHOOK_URL, "Captcha detected in game!")

            response = pyautogui.confirm(
                text="Captcha detected!",
                title="Captcha Detected",
                buttons=["Continue", "End"],
            )

            if response == "End":
                break

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

