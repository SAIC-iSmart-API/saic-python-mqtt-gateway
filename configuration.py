class Configuration:
    def __init__(self):
        self.saic_user = ''
        self.saic_password = ''
        self.saic_uri = ''
        self.saic_relogin_delay = 15 * 60  # in seconds
        self.abrp_token_map = {}
        self.abrp_api_key = ''
        self.mqtt_host = ''
        self.mqtt_port = -1
        self.mqtt_transport_protocol = ''
        self.mqtt_user = ''
        self.mqtt_password = ''
        self.mqtt_topic = ''
        self.open_wb_topic = 'openWB'
        self.open_wb_lp_map = {}
        self.anonymized_publishing = False
        self.inactive_vehicle_state_refresh_interval = 86400  # in seconds (Once a day to protect your 12V battery)
        self.messages_request_interval = 60  # in seconds
        # Switch this to true to check the car status for each message retrieved from the car, even if the message is
        # in the past
        self.ignore_vehicle_start_message_timestamp = False
