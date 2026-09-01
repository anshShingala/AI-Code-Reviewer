import json
from typing import Any
from cryptography.fernet import Fernet, InvalidToken
from app.core.config import settings


def get_fernet(key: str | None = None) -> Fernet:
    """Return a Fernet cipher instance using the configured or provided key."""
    fernet_key = key if key is not None else settings.GITHUB_TOKEN_ENCRYPTION_KEY
    if not fernet_key:
        raise ValueError("GITHUB_TOKEN_ENCRYPTION_KEY configuration is missing.")
    try:
        return Fernet(fernet_key.encode("utf-8") if isinstance(fernet_key, str) else fernet_key)
    except Exception as exc:
        raise ValueError("Invalid GITHUB_TOKEN_ENCRYPTION_KEY configuration.") from exc


def encrypt_credential_payload(
    payload: str | dict[str, Any],
    secret_key: str | None = None,
) -> str:
    """Encrypt token or token JSON payload using Fernet symmetric encryption."""
    fernet = get_fernet(secret_key)
    if isinstance(payload, dict):
        raw_data = json.dumps(payload).encode("utf-8")
    else:
        raw_data = payload.encode("utf-8")

    encrypted_bytes = fernet.encrypt(raw_data)
    return encrypted_bytes.decode("utf-8")


def decrypt_credential_payload(
    encrypted_token: str,
    secret_key: str | None = None,
) -> dict[str, Any] | str | None:
    """Decrypt Fernet encrypted token payload back to JSON dict or string."""
    try:
        fernet = get_fernet(secret_key)
        decrypted_bytes = fernet.decrypt(encrypted_token.encode("utf-8"))
        decrypted_text = decrypted_bytes.decode("utf-8")

        # Attempt JSON parsing if payload was serialized dict
        try:
            parsed = json.loads(decrypted_text)
            if isinstance(parsed, (dict, list)):
                return parsed
        except json.JSONDecodeError:
            pass

        return decrypted_text
    except (ValueError, InvalidToken):
        return None
