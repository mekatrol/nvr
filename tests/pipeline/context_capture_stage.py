from nvr_common.pipeline import PipelineStageResult


class ContextCaptureStage:
    def __init__(self, config):
        self.config = config

    def process(self, context):
        return PipelineStageResult(
            metadata_updates={
                "original": context.original_image,
                "current": context.current_image,
                "upstream_ids": tuple(sorted(context.upstream_inputs.keys())),
                "config_value": context.config.get("value"),
            }
        )
