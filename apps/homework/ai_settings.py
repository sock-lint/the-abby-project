"""Family planning configuration and domain-separated key encryption.

The homework settings endpoint and storage also serve project AI planning.
Their names and encryption domain stay stable for existing connections.
"""
import base64

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from django.conf import settings
from django.db import transaction
from django.views.decorators.debug import sensitive_variables

from apps.families.models import Family
from config.llm import LLMUnavailable

from .models import HomeworkAISettings


class AISettingsError(ValueError):
    """A safe configuration failure suitable for a user-facing message."""


@sensitive_variables()
def _fernet():
    # SECRET_KEY rotation requires re-entering saved keys, matching the
    # existing encrypted Google credentials policy with a distinct domain.
    derived = HKDF(
        algorithm=hashes.SHA256(), length=32, salt=None,
        info=b"HomeworkAISettings.encrypted_api_key",
    ).derive(settings.SECRET_KEY.encode("utf-8"))
    return Fernet(base64.urlsafe_b64encode(derived))


def settings_response(config=None):
    return {
        "provider": config.provider if config else "default",
        "model": config.model if config else "",
        "has_api_key": bool(config and config.encrypted_api_key),
    }


@transaction.atomic
@sensitive_variables()
def update_settings(family, *, provider, model, api_key=""):
    # Lock the always-present household row, including first-time saves.
    Family.objects.select_for_update().get(pk=family.pk)
    config = HomeworkAISettings.objects.filter(family=family).first()
    if provider == "default":
        if config:
            config.delete()
        return None
    if not api_key and (not config or config.provider != provider or not config.encrypted_api_key):
        raise AISettingsError("Enter an API key for the selected provider.")
    encrypted = _fernet().encrypt(api_key.encode("utf-8")) if api_key else config.encrypted_api_key
    config, _ = HomeworkAISettings.objects.update_or_create(
        family=family,
        defaults={"provider": provider, "model": model, "encrypted_api_key": encrypted},
    )
    return config


@sensitive_variables()
def planner_options(family):
    config = HomeworkAISettings.objects.filter(family=family).first()
    if not config:
        raise LLMUnavailable("No family planning AI connection configured.")
    try:
        plaintext = _fernet().decrypt(bytes(config.encrypted_api_key)).decode("utf-8")
    except (InvalidToken, ValueError, UnicodeDecodeError, TypeError):
        raise AISettingsError("Saved AI credentials could not be read.") from None
    if not plaintext:
        raise AISettingsError("Saved AI credentials could not be read.")
    return {"backend": config.provider, "model": config.model, "api_key": plaintext}
