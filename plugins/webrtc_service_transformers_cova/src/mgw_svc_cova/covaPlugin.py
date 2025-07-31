from mgw_svc_core.helpers.lazy_import import LazyImport

AudioTransformModule = LazyImport('mgw_svc_core.transformers_core.audio.AudioTransform')
AudioTransform = AudioTransformModule.module.AudioTransform


from mgw_svc_core.transformers_core.WebrtcServicePluginInterface import (
    WebRTCServicePluginInterface,
)

from mgw_svc_stt_linto.audio.AudioLintotoDataTransformChannel import (
    AudioLintotoDataTransformChannel,
)
from mgw_svc_stt_whisper.audio.AudioWhispertoDataTransformChannel import (
    AudioWhispertoDataTransformChannel,
)
from mgw_svc_stt_whisper_live.audio.AudioFasterWhisperToDataTransformChannel import (
    AudioFasterWhisperToDataTransformChannel,
)
from mgw_svc_stt_whisper_live.audio.AudioWhisperLiveToDataTransformChannel import (
    AudioWhisperLiveToDataTransformChannel,
)
from mgw_svc_cova.targets.CovaTarget import CovaTarget


class CovaPlugin(WebRTCServicePluginInterface):
    def Register(self, data):
        AudioTransform.register_transformer(
            "cova-linto",
            {
                "title": "CoVA with Linto",
                "description": "",
                "channel": ("cova-linto", AudioLintotoDataTransformChannel),
                "target": ("cova", CovaTarget),
            },
        )

        AudioTransform.register_transformer(
            "cova-whisper",
            {
                "title": "CoVA with Whisper",
                "description": "",
                "channel": ("cova-whisper", AudioWhispertoDataTransformChannel),
                "target": ("cova", CovaTarget),
            },
        )
        AudioTransform.register_transformer(
            "cova-faster-whisper",
            {
                "title": "CoVA with FasterWhisper",
                "description": "",
                "channel": ("cova-faster-whisper", AudioFasterWhisperToDataTransformChannel),
                "target": ("cova", CovaTarget),
            },
        )
        AudioTransform.register_transformer(
            "cova-whisper-live",
            {
                "title": "CoVA with WhisperLive",
                "description": "",
                "channel": (
                    "cova-whisper-live",
                    AudioWhisperLiveToDataTransformChannel,
                ),
                "target": ("cova", CovaTarget),
            },
        )
