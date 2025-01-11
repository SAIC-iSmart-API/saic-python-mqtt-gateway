class IntegrationException(Exception):
    def __init__(self, integration: str, msg: str):
        self.message = f'{integration}: {msg}'

    def __str__(self):
        return self.message
