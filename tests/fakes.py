from app.integrations.email import EmailDeliveryError, EmailMessage, SendResult
from app.integrations.storage import StorageError


class InMemoryStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.fail = False

    def put(self, key: str, data: bytes, content_type: str) -> None:
        if self.fail:
            raise StorageError("boom")
        self.objects[key] = data

    def delete(self, key: str) -> None:
        self.objects.pop(key, None)

    def exists(self, key: str) -> bool:
        return key in self.objects

    def get(self, key: str) -> bytes:
        if self.fail or key not in self.objects:
            raise StorageError("boom")
        return self.objects[key]


class RecordingEmail:
    def __init__(self) -> None:
        self.sent: list[EmailMessage] = []
        self.fail = False
        self.delivered = True

    def send(self, message: EmailMessage) -> SendResult:
        if self.fail:
            raise EmailDeliveryError("provider down")
        self.sent.append(message)
        return SendResult(provider_reference=f"fake-{len(self.sent)}", delivered=self.delivered)
