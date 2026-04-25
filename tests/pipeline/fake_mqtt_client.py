class FakeMqttClient:
    def __init__(self):
        self.published_topic = ""

    def username_pw_set(self, username, password=None):
        return

    def tls_set(self):
        return

    def connect(self, host, port):
        self.host = host
        self.port = port

    def publish(self, topic, payload, qos=0):
        self.published_topic = topic
        self.payload = payload
        self.qos = qos

    def disconnect(self):
        return
