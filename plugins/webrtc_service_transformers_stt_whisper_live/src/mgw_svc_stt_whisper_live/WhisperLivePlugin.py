from mgw_svc_core.helpers.lazy_import import LazyImport


AudioTransformModule = LazyImport('mgw_svc_core.transformers_core.audio.AudioTransform')
AudioTransform = AudioTransformModule.module.AudioTransform

from mgw_svc_core.transformers_core.WebrtcServicePluginInterface import (
    WebRTCServicePluginInterface,
)

from mgw_svc_core.transformers_core.targets.DataTarget import (
    DataTarget,
)
from .audio.AudioFasterWhisperToDataTransformChannel import (
    AudioFasterWhisperToDataTransformChannel,
)
from .audio.AudioWhisperLiveToDataTransformChannel import (
    AudioWhisperLiveToDataTransformChannel,
)


class WhisperLivePlugin(WebRTCServicePluginInterface):
    def Register(self, data):
        AudioTransform.register_transformer(
            "whisper-live",
            {
                "title": "WhisperLive",
                "description": "",
                "channel": ("whisper-live", AudioFasterWhisperToDataTransformChannel),
                "target": ("data", DataTarget),
            },
        )
        AudioTransform.register_transformer(
            "faster-whisper",
            {
                "title": "FasterWhisper",
                "description": "",
                "channel": ("faster-whisper", AudioWhisperLiveToDataTransformChannel),
                "target": ("data", DataTarget),
            },
        )
