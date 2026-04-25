from dataclasses import dataclass


@dataclass(frozen=True)
class PipelineEdge:
    source: str
    target: str
