import threading


class Singleton:
    _instance_lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        # Each subclass gets its own instance
        if not hasattr(cls, "_instance"):
            with cls._instance_lock:
                if not hasattr(cls, "_instance"):
                    cls._instance = super().__new__(cls)
        return cls._instance
