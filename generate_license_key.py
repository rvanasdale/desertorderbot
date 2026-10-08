import base64
import hashlib
import hmac
import os
from datetime import datetime, timezone


DEFAULT_SECRET = "TacoTakeover164SlimEcubE89!GreenBanana79!StrigoiZi0n8Gamer334Lizzya78"


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


def build_license_payload(fingerprint, expires_at):
    normalized = normalize_fingerprint(fingerprint)
    normalized_expiration = normalize_expiration_value(expires_at)
    return f"{normalized}|{normalized_expiration}"


def generate_license_key(fingerprint, secret, expires_at):
    payload = build_license_payload(fingerprint, expires_at)
    digest = hmac.new(
        secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    encoded = base64.b32encode(digest).decode("ascii").rstrip("=")
    return format_license_key(encoded)


def main():
    secret = os.environ.get("LICENSE_SECRET", DEFAULT_SECRET)
    fingerprint = input("Paste customer fingerprint: ").strip()

    if not fingerprint:
        raise SystemExit("No fingerprint provided.")

    if secret == DEFAULT_SECRET:
        print("Warning: using placeholder secret. Set LICENSE_SECRET for real use.")

    expires_at = input("Expiration date (YYYY-MM-DD, ISO UTC, or blank for never): ").strip()
    normalized_expiration = normalize_expiration_value(expires_at)
    license_key = generate_license_key(fingerprint, secret, normalized_expiration)

    print()
    print("Generated license key:")
    print(license_key)
    print()
    print("Paste these into overseer.py:")
    print(f'VALID_LICENSE_KEY = "{license_key}"')
    print(f'LICENSE_EXPIRES_AT = "{normalized_expiration}"')


if __name__ == "__main__":
    main()
