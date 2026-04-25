from nvr_common.pipeline import PipelineStageResult


class MetadataStage:
    def __init__(self, config):
        self.config = config

    def process(self, context):
        return PipelineStageResult(
            metadata_updates={
                self.config["key"]: self.config["value"],
                "existing": context.metadata.get("existing"),
            }
        )
