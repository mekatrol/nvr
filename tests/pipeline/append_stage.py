from nvr_common.pipeline import PipelineStageResult


class AppendStage:
    def __init__(self, config):
        self.config = config

    def process(self, context):
        return PipelineStageResult(
            output_image=f"{context.current_image}{self.config['suffix']}",
            metadata_updates={context.stage_id: context.current_image},
        )
