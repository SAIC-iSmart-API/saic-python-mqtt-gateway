from __future__ import annotations


class MqttGatewayException(Exception):
    def __init__(self, msg: str) -> None:
        self.message = msg

    def __str__(self) -> str:
        return self.message


class VehicleStatusDriftException(MqttGatewayException):
    """Raised when the vehicle status timestamp has drifted too far from the current time."""
