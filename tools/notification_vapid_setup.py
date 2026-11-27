"""Provision local VAPID credentials outside the repository. Never prints private key."""
import argparse
import base64
import os
from pathlib import Path

def provision(directory):
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import serialization
    directory = Path(directory).expanduser().resolve()
    if not directory.is_relative_to(Path.home().resolve()):
        raise ValueError("Use a private directory under your home directory")
    if any((p / ".git").exists() for p in (directory, *directory.parents)):
        raise ValueError("Do not store credentials inside a Git repository")
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    private = directory / "vapid-private.pem"
    public = directory / "vapid-public.txt"
    if private.exists() or public.exists():
        raise FileExistsError("Existing credentials preserved; do not rotate automatically")
    key = ec.generate_private_key(ec.SECP256R1())
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption())
    raw = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    encoded = base64.urlsafe_b64encode(raw).rstrip(b"=")
    fd = os.open(private, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(pem)
    with public.open("xb") as stream:
        stream.write(encoded + b"\n")
    return public

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", default=str(Path.home() / ".cyberbot-private" / "webpush"))
    args = parser.parse_args()
    if os.name == "nt":
        print("Windows: verify that the destination ACL permits only your account and trusted administrators.")
    print("Public key file:", provision(args.directory))
