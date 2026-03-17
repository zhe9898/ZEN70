import base64
import os

from cryptography.hazmat.primitives.asymmetric import ec


def run():
    # Generate P-256 (prime256v1) key pair
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key()

    # Extract raw bytes
    priv_bytes = private_key.private_numbers().private_value.to_bytes(32, byteorder="big")
    pub_x = public_key.public_numbers().x.to_bytes(32, byteorder="big")
    pub_y = public_key.public_numbers().y.to_bytes(32, byteorder="big")
    pub_bytes = b"\x04" + pub_x + pub_y

    # VAPID requires URL-safe base64 without padding
    priv_b64 = base64.urlsafe_b64encode(priv_bytes).decode("utf-8").strip("=")
    pub_b64 = base64.urlsafe_b64encode(pub_bytes).decode("utf-8").strip("=")

    env_path = r"e:\ZEN70\backend\.env"
    with open(env_path, "a", encoding="utf-8") as f:
        f.write(f"\n# VAPID Web Push Keys\n")
        f.write(f"VAPID_PRIVATE_KEY={priv_b64}\n")
        f.write(f"VAPID_PUBLIC_KEY={pub_b64}\n")
        f.write(f"VAPID_CLAIMS_EMAIL=admin@zen70.local\n")
    print("VAPID Keys generated and appended to .env")


if __name__ == "__main__":
    run()
