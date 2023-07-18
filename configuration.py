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
        self.messages_request_interval = 60  # in seconds
        self.ha_discovery_enabled = True
        self.ha_discovery_prefix = 'homeassistant'
