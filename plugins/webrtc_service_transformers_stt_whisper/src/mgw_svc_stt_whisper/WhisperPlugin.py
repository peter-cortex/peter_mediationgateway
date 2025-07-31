from mgw_svc_core.helpers.lazy_import import LazyImport


AudioTransformModule = LazyImport('mgw_svc_core.transformers_core.audio.AudioTransform')
AudioTransform = AudioTransformModule.module.AudioTransform

from mgw_svc_core.transformers_core.WebrtcServicePluginInterface import (
    WebRTCServicePluginInterface,
)

from mgw_svc_core.transformers_core.targets.DataTarget import (
    DataTarget,
)
from .audio.AudioWhispertoDataTransformChannel import AudioWhispertoDataTransformChannel


class WhisperPlugin(WebRTCServicePluginInterface):
    def Register(self, data):
        AudioTransform.register_transformer(
            "whisper",
            {
                "title": "Whisper",
                "description": "",
                "channel": ("whisper", AudioWhispertoDataTransformChannel),
                "target": ("data", DataTarget),
            },
        )
