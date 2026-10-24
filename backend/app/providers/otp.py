from typing import Protocol
import importlib

from app.core.config import settings
from app.db.base import OtpChannel


class OtpDelivery(Protocol):
    async def send(self, destination: str, channel: OtpChannel, code: str) -> None: ...


_provider: OtpDelivery | None = None


def register_otp_delivery(provider: OtpDelivery) -> None:
    global _provider
    _provider = provider


class ConsoleOtpDelivery:
    """Development-only adapter. Production must inject a real provider."""

    async def send(self, destination: str, channel: OtpChannel, code: str) -> None:
        if settings.environment != "development":
            raise RuntimeError("Console OTP delivery is disabled outside development")
        print(f"[DEV OTP] {channel.value} to {destination}: {code}")


def get_otp_delivery() -> OtpDelivery:
    if _provider is not None:
        return _provider
    if settings.otp_delivery == "console" and settings.environment == "development":
        return ConsoleOtpDelivery()
    if ":" in settings.otp_delivery:
        module_path, class_name = settings.otp_delivery.split(":", 1)
        provider_type = getattr(importlib.import_module(module_path), class_name)
        return provider_type()
    raise RuntimeError("Set OTP_DELIVERY to a provider class path or register a provider")