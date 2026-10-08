import hashlib
import os
import platform
import socket
import uuid
import winreg
import tkinter as tk
from tkinter import messagebox


APP_TITLE = "Overseer Fingerprint Collector"


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


def build_fingerprint():
    source = build_fingerprint_source()
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest().upper()
    return "-".join(digest[i : i + 8] for i in range(0, 32, 8))


def copy_to_clipboard(root, value):
    root.clipboard_clear()
    root.clipboard_append(value)
    root.update()


def main():
    fingerprint = build_fingerprint()

    root = tk.Tk()
    root.title(APP_TITLE)
    root.resizable(False, False)
    root.geometry("520x210")

    frame = tk.Frame(root, padx=18, pady=18)
    frame.pack(fill="both", expand=True)

    tk.Label(
        frame,
        text="Send this device fingerprint to the seller:",
        font=("Segoe UI", 11, "bold"),
        anchor="w",
    ).pack(fill="x", pady=(0, 10))

    value_var = tk.StringVar(value=fingerprint)
    entry = tk.Entry(
        frame,
        textvariable=value_var,
        font=("Consolas", 14),
        justify="center",
        width=40,
        state="readonly",
        readonlybackground="white",
    )
    entry.pack(fill="x", pady=(0, 14))

    def handle_copy():
        copy_to_clipboard(root, fingerprint)
        messagebox.showinfo(
            APP_TITLE,
            "Fingerprint copied to clipboard.",
        )

    def handle_close():
        root.destroy()

    tk.Button(
        frame,
        text="Copy Fingerprint",
        command=handle_copy,
        width=18,
    ).pack(pady=(0, 8))

    tk.Label(
        frame,
        text="This code is specific to this PC.",
        font=("Segoe UI", 9),
        fg="#444444",
    ).pack()

    root.protocol("WM_DELETE_WINDOW", handle_close)
    root.mainloop()


if __name__ == "__main__":
    main()
