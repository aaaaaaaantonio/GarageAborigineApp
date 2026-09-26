"""Compact UUID encoding for callback_data (Telegram limit: 64 bytes).

A UUID is 36 chars as text but 22 as unpadded urlsafe base64.
"""
import base64
import uuid as uuid_lib


def encode_id(raw_id: str) -> str:
    return base64.urlsafe_b64encode(uuid_lib.UUID(str(raw_id)).bytes).rstrip(b"=").decode()


def decode_id(encoded: str) -> str:
    padded = encoded + "=" * (-len(encoded) % 4)
    return str(uuid_lib.UUID(bytes=base64.urlsafe_b64decode(padded)))
