import base64
import ctypes
import hashlib
import hmac
import os
import platform
import random
import socket
import threading
import time
import tkinter as tk
import sys
import uuid
import winreg
from datetime import datetime, timezone

import cv2
import numpy as np
import pyautogui
import requests
import winsound
from tensorflow.keras.models import load_model

BASE_DIR = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
MODEL_PATH = os.path.join(BASE_DIR, "keras_modelv4.h5")

PUZZLE_THRESHOLD = 0.7
NOT_BUILDING_THRESHOLD = 0.7
CLICK_COOLDOWN = 3
CALIBRATION_EXTRA_SECONDS = 2
STARTUP_WEBHOOK_PREFIXES = (
    "https://discord.com/api/webhooks/",
    "https://canary.discord.com/api/webhooks/",
    "https://ptb.discord.com/api/webhooks/",
)
STOP_HOTKEY_VK = 0x1B

LICENSE_SECRET = (
    "TacoTakeover164SlimEcubE89!GreenBanana79!StrigoiZi0n8Gamer334Lizzya78"
)
VALID_LICENSE_KEY = "RBDFJ-N6W5V-A7JCB-C3DA4-U3TSO"
LICENSE_EXPIRES_AT = "2026-04-09T23:59:59Z"

stop_event = threading.Event()


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


def wait_with_stop(seconds, step=0.1):
    end_time = time.time() + max(0, seconds)

    while time.time() < end_time:
        if check_for_stop_request():
            return True

        remaining = end_time - time.time()
        time.sleep(min(step, max(remaining, 0)))

    return check_for_stop_request()


def notify(message, duration=2, freq=1200):
    winsound.Beep(freq, 200)
    show_popup(message, duration)
    return wait_with_stop(duration)


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
    except Exception as exc:
        notify("License check failed. Exiting.", duration=2)
        raise SystemExit(f"License generation failed: {exc}") from exc

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


def is_valid_discord_webhook(webhook_url):
    return webhook_url.startswith(STARTUP_WEBHOOK_PREFIXES)


def prompt_for_webhook():
    result = {"webhook": None}

    root = tk.Tk()
    root.title("Builder Bot")
    root.attributes("-topmost", True)
    root.resizable(False, False)
    root.configure(bg="#f2f4f7")

    container = tk.Frame(root, bg="#f2f4f7", padx=18, pady=18)
    container.pack(fill="both", expand=True)

    title = tk.Label(
        container,
        text="Builder Bot",
        font=("Segoe UI", 15, "bold"),
        bg="#f2f4f7",
        fg="#111827",
    )
    title.pack(anchor="w")

    description = tk.Label(
        container,
        text=(
            "Paste your Discord webhook for captcha alerts, then click Start Bot.\n"
            "Press ESC at any time while the bot is running to stop it."
        ),
        justify="left",
        font=("Segoe UI", 10),
        bg="#f2f4f7",
        fg="#374151",
        pady=10,
    )
    description.pack(anchor="w")

    entry = tk.Entry(container, width=62, font=("Segoe UI", 10))
    entry.pack(fill="x")
    entry.focus_set()

    error_label = tk.Label(
        container,
        text="",
        justify="left",
        font=("Segoe UI", 9),
        bg="#f2f4f7",
        fg="#b91c1c",
        pady=8,
    )
    error_label.pack(anchor="w")

    button_row = tk.Frame(container, bg="#f2f4f7")
    button_row.pack(fill="x", pady=(6, 0))

    def close_window():
        root.destroy()

    def start_bot():
        webhook_url = entry.get().strip()

        if not webhook_url:
            error_label.config(text="Enter a Discord webhook URL before starting.")
            return

        if not is_valid_discord_webhook(webhook_url):
            error_label.config(text="Enter a valid Discord webhook URL.")
            return

        result["webhook"] = webhook_url
        close_window()

    start_button = tk.Button(
        button_row,
        text="Start Bot",
        command=start_bot,
        font=("Segoe UI", 10, "bold"),
        bg="#2563eb",
        fg="white",
        activebackground="#1d4ed8",
        activeforeground="white",
        padx=18,
        pady=8,
        bd=0,
        cursor="hand2",
    )
    start_button.pack(side="left")

    cancel_button = tk.Button(
        button_row,
        text="Cancel",
        command=close_window,
        font=("Segoe UI", 10),
        bg="#e5e7eb",
        fg="#111827",
        activebackground="#d1d5db",
        padx=18,
        pady=8,
        bd=0,
        cursor="hand2",
    )
    cancel_button.pack(side="left", padx=(8, 0))

    def monitor_stop():
        if not root.winfo_exists():
            return

        if stop_hotkey_pressed():
            stop_event.set()
            close_window()
            return

        root.after(100, monitor_stop)

    entry.bind("<Return>", lambda _event: start_bot())
    root.protocol("WM_DELETE_WINDOW", close_window)
    root.after(100, monitor_stop)
    root.mainloop()

    if check_for_stop_request():
        raise SystemExit("Startup cancelled with ESC.")

    if not result["webhook"]:
        notify("Startup cancelled. Exiting.", duration=2)
        raise SystemExit("Startup cancelled.")

    return result["webhook"]


def calibrate_wait(message, duration, freq=1200):
    if notify(message, duration + CALIBRATION_EXTRA_SECONDS, freq=freq):
        raise SystemExit("Bot stopped during calibration.")


def calibrate_point(prompt):
    calibrate_wait(f"{prompt}\nHold cursor steady...", duration=2)
    winsound.Beep(800, 150)
    return pyautogui.position()


def calibrate_region(name):
    calibrate_wait(f"Calibrating {name}", duration=4)

    calibrate_wait("TOP LEFT corner\nHold...", duration=4)
    x1, y1 = pyautogui.position()
    winsound.Beep(900, 100)

    calibrate_wait("BOTTOM RIGHT corner\nHold...", duration=4)
    x2, y2 = pyautogui.position()
    winsound.Beep(900, 100)

    left = min(x1, x2)
    top = min(y1, y2)
    width = abs(x2 - x1)
    height = abs(y2 - y1)

    calibrate_wait(f"{name} complete", duration=1.5)
    return (left, top, width, height)


def get_screen(region):
    screenshot = pyautogui.screenshot(region=region)
    return np.array(screenshot)


def predict(img, model_ref):
    img = cv2.resize(img, (224, 224))
    img = img / 255.0
    img = np.expand_dims(img, axis=0)
    return model_ref.predict(img, verbose=0)[0]


def small_idle_wiggle(x, y, amplitude=8):
    offset_x = random.randint(-amplitude, amplitude)
    offset_y = random.randint(-amplitude, amplitude)
    pyautogui.moveTo(x + offset_x, y + offset_y, duration=0.5)


def send_webhook(url, message, mention_everyone=False):
    try:
        payload = {"content": f"@everyone {message}" if mention_everyone else message}
        if mention_everyone:
            payload["allowed_mentions"] = {"parse": ["everyone"]}
        requests.post(url, json=payload, timeout=10)
    except Exception as exc:
        print(f"Webhook failed: {exc}")


def play_chime(frequency=1000, duration=300):
    winsound.Beep(frequency, duration)


def prompt_captcha_action():
    result = {"action": "End"}

    root = tk.Tk()
    root.title("Captcha Detected")
    root.attributes("-topmost", True)
    root.resizable(False, False)
    root.configure(bg="#fff7ed")

    container = tk.Frame(root, bg="#fff7ed", padx=18, pady=18)
    container.pack(fill="both", expand=True)

    title = tk.Label(
        container,
        text="Captcha Detected",
        font=("Segoe UI", 14, "bold"),
        bg="#fff7ed",
        fg="#9a3412",
    )
    title.pack(anchor="w")

    message = tk.Label(
        container,
        text=(
            "Solve the captcha in game, then click Continue.\n"
            "Click Stop Bot or press ESC to end the run."
        ),
        justify="left",
        font=("Segoe UI", 10),
        bg="#fff7ed",
        fg="#7c2d12",
        pady=10,
    )
    message.pack(anchor="w")

    button_row = tk.Frame(container, bg="#fff7ed")
    button_row.pack(fill="x")

    def close_window():
        root.destroy()

    def continue_run():
        result["action"] = "Continue"
        close_window()

    def stop_run():
        result["action"] = "End"
        close_window()

    continue_button = tk.Button(
        button_row,
        text="Continue",
        command=continue_run,
        font=("Segoe UI", 10, "bold"),
        bg="#16a34a",
        fg="white",
        activebackground="#15803d",
        activeforeground="white",
        padx=18,
        pady=8,
        bd=0,
        cursor="hand2",
    )
    continue_button.pack(side="left")

    stop_button = tk.Button(
        button_row,
        text="Stop Bot",
        command=stop_run,
        font=("Segoe UI", 10),
        bg="#dc2626",
        fg="white",
        activebackground="#b91c1c",
        activeforeground="white",
        padx=18,
        pady=8,
        bd=0,
        cursor="hand2",
    )
    stop_button.pack(side="left", padx=(8, 0))

    def monitor_stop():
        if not root.winfo_exists():
            return

        if stop_hotkey_pressed():
            stop_event.set()
            close_window()
            return

        root.after(100, monitor_stop)

    root.protocol("WM_DELETE_WINDOW", stop_run)
    root.after(100, monitor_stop)
    root.mainloop()

    if check_for_stop_request():
        return "End"

    return result["action"]


def run_bot(model, webhook_url, button_x, button_y, build_region):
    last_click_time = 0

    print("Press ESC at any time to stop the bot.")
    print("Starting bot in 3 seconds...")
    if wait_with_stop(3):
        return

    while True:
        if check_for_stop_request():
            break

        small_idle_wiggle(button_x, button_y)

        screen = get_screen(build_region)
        building, not_building, puzzle = predict(screen, model)

        print(
            f"Predictions -> building: {building:.2f}, "
            f"not_building: {not_building:.2f}, puzzle: {puzzle:.2f}"
        )

        if puzzle > PUZZLE_THRESHOLD:
            print("Captcha detected. Pausing bot.")
            play_chime()
            send_webhook(
                webhook_url,
                "Captcha detected in game!",
                mention_everyone=True,
            )

            if prompt_captcha_action() != "Continue":
                break

            if wait_with_stop(5):
                break
            continue

        if not_building > NOT_BUILDING_THRESHOLD:
            if time.time() - last_click_time > CLICK_COOLDOWN:
                print("Clicking build button...")
                pyautogui.click(button_x, button_y)
                last_click_time = time.time()
        else:
            print("Currently building...")

        if wait_with_stop(random.uniform(0.4, 1.2)):
            break


def setup_bot():
    require_embedded_license()
    webhook_url = prompt_for_webhook()

    if notify("Loading model...", duration=2, freq=900):
        raise SystemExit("Bot stopped while loading the model.")

    print("Loading model...")
    model = load_model(MODEL_PATH)
    print("Model loaded.")

    calibrate_wait("Calibration starting...", duration=3)
    button_x, button_y = calibrate_point("Place cursor in CENTER of build button")
    build_region = calibrate_region("Build Button Bounding Box")
    calibrate_wait("Calibration complete. Starting bot...", duration=2)

    return model, webhook_url, button_x, button_y, build_region


def main():
    pyautogui.FAILSAFE = True

    try:
        model, webhook_url, button_x, button_y, build_region = setup_bot()
        run_bot(model, webhook_url, button_x, button_y, build_region)
    except SystemExit as exc:
        print(exc)
    except KeyboardInterrupt:
        print("Bot stopped manually.")
    except pyautogui.FailSafeException:
        print("PyAutoGUI failsafe triggered. Bot stopped.")
        show_popup("Failsafe triggered. Bot stopped.", duration=2)
    finally:
        stop_event.set()
        print("Bot stopped.")
        show_popup("Bot stopped.", duration=1.5)


if __name__ == "__main__":
    main()
