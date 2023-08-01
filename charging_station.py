class ChargingStation:
    def __init__(self, vin: str, charge_state_topic: str, charging_value: str, soc_topic: str):
        self.vin = vin
        self.charge_state_topic = charge_state_topic
        self.charging_value = charging_value
        self.soc_topic = soc_topic
        self.connected_topic = ''
        self.connected_value = ''
