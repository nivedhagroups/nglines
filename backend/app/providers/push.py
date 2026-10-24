import asyncio
from typing import Protocol

from app.core.config import settings


class PushDelivery(Protocol):
    async def send(self, tokens: list[str], title: str, body: str, data: dict[str, str]) -> None: ...


class FirebaseAdminPushDelivery:
    async def send(self, tokens: list[str], title: str, body: str, data: dict[str, str]) -> None:
        if not tokens:
            return
        await asyncio.to_thread(self._send_sync, tokens, title, body, data)

    @staticmethod
    def _send_sync(tokens: list[str], title: str, body: str, data: dict[str, str]) -> None:
        import firebase_admin
        from firebase_admin import messaging

        try:
            app = firebase_admin.get_app()
        except ValueError:
            app = firebase_admin.initialize_app()
        message = messaging.MulticastMessage(
            tokens=tokens,
            notification=messaging.Notification(title=title, body=body),
            data=data,
        )
        messaging.send_each_for_multicast(message, app=app)


class DisabledPushDelivery:
    async def send(self, tokens: list[str], title: str, body: str, data: dict[str, str]) -> None:
        if settings.environment != "development":
            raise RuntimeError("Push delivery is not configured")


_provider: PushDelivery | None = None


def register_push_delivery(provider: PushDelivery) -> None:
    global _provider
    _provider = provider


def get_push_delivery() -> PushDelivery:
    if _provider is not None:
        return _provider
    if settings.push_delivery == "firebase":
        return FirebaseAdminPushDelivery()
    if settings.push_delivery == "disabled":
        return DisabledPushDelivery()
    raise RuntimeError("Unknown push delivery provider")