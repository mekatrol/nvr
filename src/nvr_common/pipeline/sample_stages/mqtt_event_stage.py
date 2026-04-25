from __future__ import annotations

import json
import time
from typing import Any

from nvr_common.pipeline import PipelineContext, PipelineStageResult


class MqttEventStage:
    def __init__(self, config: dict[str, Any]) -> None:
        self.topic = self._required_string(config, "topic")
        self.host = self._required_string(config, "host")
        self.port = int(config.get("port", 1883))
        self.event_key = self._required_string(config, "event_key")
        self.cooldown_seconds = float(config.get("cooldown_seconds", 30.0))
        self.username = config.get("username")
        self.password = config.get("password")
        self.tls = bool(config.get("tls", False))
        self.payload_template = config.get("payload", {})
        self.client_factory = config.get("client_factory")
        self._last_publish_seconds = 0.0

    def process(self, context: PipelineContext) -> PipelineStageResult:
        event = context.metadata.get(self.event_key)
        if not isinstance(event, dict) or not event.get("active"):
            return PipelineStageResult()

        now = time.monotonic()
        if now - self._last_publish_seconds < self.cooldown_seconds:
            return PipelineStageResult(
                metadata_updates={"mqtt": {"published": False, "reason": "cooldown"}}
            )

        payload = self._payload(context, event)
        client = self._create_client()
        if self.username:
            client.username_pw_set(self.username, self.password)
        if self.tls:
            client.tls_set()
        client.connect(self.host, self.port)
        client.publish(self.topic, json.dumps(payload), qos=1)
        client.disconnect()
        self._last_publish_seconds = now

        return PipelineStageResult(
            metadata_updates={
                "mqtt": {
                    "published": True,
                    "topic": self.topic,
                    "host": self.host,
                    "port": self.port,
                }
            },
            events=({"type": "mqtt", "topic": self.topic, "payload": payload},),
        )

    def _create_client(self) -> Any:
        if self.client_factory:
            return self.client_factory()

        import paho.mqtt.client as mqtt

        return mqtt.Client()

    def _payload(self, context: PipelineContext, event: dict[str, Any]) -> dict[str, Any]:
        payload = dict(self.payload_template)
        payload.update(
            {
                "camera_id": context.camera_id,
                "frame_id": context.frame_id,
                "event": event,
            }
        )
        return payload

    @staticmethod
    def _required_string(config: dict[str, Any], key: str) -> str:
        value = config.get(key)
        if not isinstance(value, str) or not value:
            raise ValueError(f"mqtt event config '{key}' must be a non-empty string")
        return value
