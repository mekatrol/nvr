from __future__ import annotations

from typing import Any

from nvr_common.pipeline import PipelineContext, PipelineStageResult
from nvr_common.pipeline.pipeline_stage import PipelineStage


class ApproachDirectionStage(PipelineStage):
    def __init__(self, config: dict[str, Any]) -> None:
        self.direction = config.get("direction", "down")
        self.min_delta = float(config.get("min_delta", 1.0))
        self.event_key = config.get("event_key", "person_approaching")
        if self.direction not in {"up", "down", "left", "right"}:
            raise ValueError("approach direction must be up, down, left, or right")
        if not isinstance(self.event_key, str) or not self.event_key:
            raise ValueError("approach direction config 'event_key' must be a string")

    def process(self, context: PipelineContext) -> PipelineStageResult:
        tracks = context.metadata.get("tracks", [])
        if not isinstance(tracks, list):
            raise ValueError("tracks metadata must be a list")

        matching_tracks = []
        for track in tracks:
            if not isinstance(track, dict):
                continue
            movement = track.get("movement", {})
            if not isinstance(movement, dict):
                continue
            if self._matches(movement):
                matching_tracks.append(track)

        event = {
            "type": self.event_key,
            "active": bool(matching_tracks),
            "track_ids": tuple(track["track_id"] for track in matching_tracks),
            "direction": self.direction,
        }
        return PipelineStageResult(
            metadata_updates={self.event_key: event},
            events=(event,) if event["active"] else (),
        )

    def _matches(self, movement: dict[str, Any]) -> bool:
        dx = float(movement.get("dx", 0.0))
        dy = float(movement.get("dy", 0.0))
        if self.direction == "up":
            return dy <= -self.min_delta
        if self.direction == "down":
            return dy >= self.min_delta
        if self.direction == "left":
            return dx <= -self.min_delta
        return dx >= self.min_delta
