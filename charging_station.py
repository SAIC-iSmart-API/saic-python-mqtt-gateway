class ChargingStation:
    def __init__(self, vin: str, charge_state_topic: str, charging_value: str, soc_topic: str | None = None):
        self.vin: str = vin
        self.charge_state_topic: str = charge_state_topic
        self.charging_value: str = charging_value
        self.soc_topic: str | None = soc_topic
        self.range_topic: str | None = None
        self.connected_topic: str | None = None
        self.connected_value: str | None = None
