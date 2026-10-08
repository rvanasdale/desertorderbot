import time
import random
import base64
import hashlib
import hmac
import os
import ctypes
import numpy as np
import cv2
import pyautogui
import requests
import winsound
import tkinter as tk
import threading
from collections import deque
import io
import platform
import socket
from datetime import datetime, timezone
from PIL import Image
import uuid
import winreg

# Webhooks
FULL_SCREEN_REGION = (2, 80, 1512, 895)
MINIMAP_ALERT_SETTLE_DELAY = 5
MINIMAP_ALERT_COOLDOWN = 90
BASE_ALERT_PING_COOLDOWN = 20 * 60
BOTTOM_MASK_HEIGHT = 200
YELLOW_FLASH_CONFIRMATIONS = 10
DEFAULT_MIN_FLASH_CONTOUR_AREA = 125
LICENSE_SECRET = "TacoTakeover164SlimEcubE89!GreenBanana79!StrigoiZi0n8Gamer334Lizzya78"
VALID_LICENSE_KEY = "TGXER-HLDV2-J32LN-452G6-IUZUR"
LICENSE_EXPIRES_AT = "2026-04-21T23:59:59Z"
STOP_HOTKEY_VK = 0x1B

last_base_alert_ping_time = 0
pause_event = threading.Event()
stop_event = threading.Event()
MINIMAP_ALERT_DISCORD_WEBHOOK_URL = None
MIN_FLASH_CONTOUR_AREA = DEFAULT_MIN_FLASH_CONTOUR_AREA
ALERT_MODE = "defense"


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


def normalize_license_key(license_key):
    return "".join(ch for ch in license_key.upper() if ch.isalnum())


def normalize_fingerprint(value):
    return "".join(ch for ch in value.upper() if ch.isalnum())


def format_license_key(raw_value):
    raw_value = raw_value[:25]
    return "-".join(raw_value[i : i + 5] for i in range(0, len(raw_value), 5))


def normalize_expiration_value(value):
    value = str(value or "").strip()
    if not value or value.upper() == "NEVER":
        return "NEVER"

    if len(value) == 10:
        dt = datetime.fromisoformat(value).replace(
            hour=23,
            minute=59,
            second=59,
            tzinfo=timezone.utc,
        )
    else:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        dt = dt.replace(microsecond=0)

    return dt.isoformat().replace("+00:00", "Z")


def read_machine_guid():
    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Cryptography",
        ) as key:
            value, _ = winreg.QueryValueEx(key, "MachineGuid")
            return str(value).strip()
    except OSError:
        return "unknown-machine-guid"


def get_mac_address():
    mac_int = uuid.getnode()
    return f"{mac_int:012X}"


def build_fingerprint_source():
    parts = [
        read_machine_guid(),
        socket.gethostname(),
        platform.machine(),
        platform.system(),
        platform.release(),
        get_mac_address(),
        os.environ.get("PROCESSOR_IDENTIFIER", "unknown-processor"),
    ]
    return "|".join(part.strip().upper() for part in parts)


def build_device_fingerprint():
    source = build_fingerprint_source()
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest().upper()
    return "-".join(digest[i : i + 8] for i in range(0, 32, 8))


def build_license_payload(fingerprint, expires_at):
    normalized_fingerprint = normalize_fingerprint(fingerprint)
    normalized_expiration = normalize_expiration_value(expires_at)
    return f"{normalized_fingerprint}|{normalized_expiration}"


def generate_license_key(fingerprint, secret, expires_at):
    payload = build_license_payload(fingerprint, expires_at)
    digest = hmac.new(
        secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    encoded = base64.b32encode(digest).decode("ascii").rstrip("=")
    return format_license_key(encoded)


def license_is_expired(expires_at):
    normalized = normalize_expiration_value(expires_at)
    if normalized == "NEVER":
        return False

    expires_at_dt = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    return datetime.now(timezone.utc) > expires_at_dt


def require_embedded_license():
    if VALID_LICENSE_KEY.startswith("REPLACE-"):
        raise SystemExit("Set VALID_LICENSE_KEY before packaging this build.")

    try:
        generated_key = generate_license_key(
            build_device_fingerprint(),
            LICENSE_SECRET,
            LICENSE_EXPIRES_AT,
        )
    except Exception as e:
        notify("License check failed. Exiting.", duration=2)
        raise SystemExit(f"License generation failed: {e}")

    if not hmac.compare_digest(
        normalize_license_key(generated_key),
        normalize_license_key(VALID_LICENSE_KEY),
    ):
        notify("This copy is not licensed for this PC. Exiting.", duration=2)
        raise SystemExit("License does not match this device.")

    if license_is_expired(LICENSE_EXPIRES_AT):
        notify("This license has expired. Exiting.", duration=2)
        raise SystemExit("License expired.")

    print("License accepted.")


def stop_hotkey_pressed():
    return bool(ctypes.windll.user32.GetAsyncKeyState(STOP_HOTKEY_VK) & 0x8000)


def check_for_stop_request():
    if stop_event.is_set():
        return True

    if stop_hotkey_pressed():
        stop_event.set()
        print("ESC detected. Stopping bot.")
        return True

    return False


def prompt_for_webhook():
    webhook_url = pyautogui.prompt(
        text="Paste your Discord webhook URL for minimap alerts.",
        title="Discord Webhook",
        default="",
    )

    if not webhook_url:
        notify("Webhook entry cancelled. Exiting.", duration=2)
        raise SystemExit("Webhook entry cancelled.")

    webhook_url = webhook_url.strip()
    if not webhook_url.startswith("https://discord.com/api/webhooks/"):
        notify("Invalid Discord webhook URL. Exiting.", duration=2)
        raise SystemExit("Invalid Discord webhook URL.")

    return webhook_url


def prompt_for_sensitivity():
    selection = pyautogui.confirm(
        text=(
            "Choose minimap sensitivity.\n\n"
            "Regular keeps the current mutli-group treshold.\n"
            "High triggers bot on single group attacks."
        ),
        title="Sensitivity",
        buttons=["Regular", "High"],
    )

    if not selection:
        notify("Sensitivity selection cancelled. Exiting.", duration=2)
        raise SystemExit("Sensitivity selection cancelled.")

    return selection.lower()


def get_min_flash_contour_area(sensitivity_mode):
    if sensitivity_mode == "high":
        return DEFAULT_MIN_FLASH_CONTOUR_AREA / 6
    return DEFAULT_MIN_FLASH_CONTOUR_AREA


def prompt_for_alert_mode():
    selection = pyautogui.confirm(
        text=(
            "Choose alert mode.\n\n"
            "Attack + Defense alerts for any battles.\n"
            "Defense only alerts if an attack on ally base is detected."
        ),
        title="Alert Mode",
        buttons=["Attack + Defense", "Defense"],
    )

    if not selection:
        notify("Alert mode selection cancelled. Exiting.", duration=2)
        raise SystemExit("Alert mode selection cancelled.")

    if selection == "Attack + Defense":
        return "attack_defense"
    return "defense"


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


def small_idle_wiggle(x, y, amplitude=8):
    offset_x = random.randint(-amplitude, amplitude)
    offset_y = random.randint(-amplitude, amplitude)
    pyautogui.moveTo(x + offset_x, y + offset_y, duration=0.5)


def format_webhook_content(message, mention_everyone=False):
    return f"@everyone {message}" if mention_everyone else message


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
        print("Base alert sent with @everyone ping.")
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
require_embedded_license()
MINIMAP_ALERT_DISCORD_WEBHOOK_URL = prompt_for_webhook()
sensitivity_mode = prompt_for_sensitivity()
MIN_FLASH_CONTOUR_AREA = get_min_flash_contour_area(sensitivity_mode)
ALERT_MODE = prompt_for_alert_mode()

print(
    f"Sensitivity: {sensitivity_mode.title()} "
    f"(yellow contour area threshold: {MIN_FLASH_CONTOUR_AREA})."
)
print(f"Alert mode: {'Attack + Defense' if ALERT_MODE == 'attack_defense' else 'Defense'}.")

notify("Calibration starting...", 3)

BASE_X, BASE_Y = calibrate_point("Place cursor on your BASE on the minimap")
MINIMAP_REGION = calibrate_region("Minimap Bounding Box")

notify("Calibration complete. Starting bot...", 2)
print("Press ESC at any time to stop the bot.")


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
        if check_for_stop_request():
            break

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
                if ALERT_MODE == "attack_defense":
                    alert_message = "Minimap alert triggered in Attack + Defense mode. Screenshot attached."
                    send_base_alert_webhook_with_image(
                        MINIMAP_ALERT_DISCORD_WEBHOOK_URL,
                        alert_message,
                        full_img,
                    )
                    print("Attack + Defense mode active. Screenshot sent without blue base validation.")
                else:
                    blue_base_detected, blue_text_box = detect_blue_base_name(full_img)

                    if blue_base_detected:
                        x, y, w, h, _ = blue_text_box
                        print(f"Blue base name detected at ({x}, {y}, {w}, {h}).")
                        alert_message = "Minimap alert triggered! Friendly base defense detected. Screenshot attached."
                        send_base_alert_webhook_with_image(
                            MINIMAP_ALERT_DISCORD_WEBHOOK_URL,
                            alert_message,
                            full_img,
                        )
                    else:
                        print("Defense mode active. No blue base name detected, so no webhook was sent.")

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
        if check_for_stop_request():
            break

        if pause_event.is_set():
            print("Bot paused due to minimap event.")
            time.sleep(1)
            continue

        small_idle_wiggle(BASE_X, BASE_Y)
        print("Idle wiggle active. Watching minimap for flash/attack alerts.")
        time.sleep(random.uniform(0.8, 1.5))

except KeyboardInterrupt:
    print("Bot stopped manually.")
finally:
    stop_event.set()
    print("Bot stopped.")
