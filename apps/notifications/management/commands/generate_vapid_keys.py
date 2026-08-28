"""Print a VAPID keypair for Web Push.

Run once per deployment, then put both halves in the environment:

    python manage.py generate_vapid_keys

The private key must stay secret — anyone holding it can send push
notifications that appear to come from this app. The public key is handed to
browsers by ``/api/push/config/`` and is not sensitive.
"""
import base64

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Generate a VAPID keypair for Web Push (prints env-var lines)."

    def handle(self, *args, **options):
        try:
            from cryptography.hazmat.primitives import serialization
            from cryptography.hazmat.primitives.asymmetric import ec
        except ImportError:
            self.stderr.write(
                "cryptography is required — install requirements.txt first."
            )
            return

        private_key = ec.generate_private_key(ec.SECP256R1())

        # pywebpush wants the private key as a base64url-encoded raw scalar.
        private_value = private_key.private_numbers().private_value
        private_bytes = private_value.to_bytes(32, byteorder="big")
        private_b64 = _b64(private_bytes)

        # The public half is the uncompressed EC point (0x04 || X || Y), which
        # is exactly what pushManager.subscribe expects.
        public_bytes = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.X962,
            format=serialization.PublicFormat.UncompressedPoint,
        )
        public_b64 = _b64(public_bytes)

        self.stdout.write("# Add these to your environment (.env):")
        self.stdout.write(f"VAPID_PUBLIC_KEY={public_b64}")
        self.stdout.write(f"VAPID_PRIVATE_KEY={private_b64}")
        self.stdout.write("VAPID_SUBJECT=mailto:you@example.com")
        self.stdout.write("")
        self.stdout.write(
            "Keep VAPID_PRIVATE_KEY secret. Changing the keypair later "
            "invalidates every existing subscription — devices must re-opt-in."
        )


def _b64(raw: bytes) -> str:
    """base64url without padding, per RFC 8292."""
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
