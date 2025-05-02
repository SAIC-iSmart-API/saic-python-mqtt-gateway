from __future__ import annotations


class IntegrationException(Exception):
    def __init__(self, integration: str, msg: str) -> None:
        self.message = f"{integration}: {msg}"

    def __str__(self) -> str:
        return self.message
