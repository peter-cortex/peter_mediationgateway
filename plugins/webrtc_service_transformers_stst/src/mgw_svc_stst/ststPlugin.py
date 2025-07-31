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
from mgw_svc_stst.targets.STSTTarget import STSTTarget


class STSTPlugin(WebRTCServicePluginInterface):
    def Register(self, data):

        AudioTransform.register_transformer(
            "stst-whisper",
            {
                "title": "STST with Whisper and OpenAI",
                "description": "",
                "channel": ("stst-whisper", AudioWhispertoDataTransformChannel),
                "target": ("stst", STSTTarget),
            },
        )
        AudioTransform.register_transformer(
            "PETER",
            {
                "title": "stst with PETER",
                "description": "",
                "channel": ("stst-whisper", AudioPETERtoDataTransformChannel),
                "target": ("stst", PETERTarget),
            },
        )
        AudioTransform.register_transformer(
            "stst-faster-whisper",
            {
                "title": "STST with FasterWhisper and OpenAI",
                "description": "",
                "channel": ("stst-faster-whisper", AudioFasterWhisperToDataTransformChannel),
                "target": ("stst", STSTTarget),
            },
        )
        AudioTransform.register_transformer(
            "stst-whisper-live",
            {
                "title": "STST with WhisperLive and OpenAI",
                "description": "",
                "channel": (
                    "stst-whisper-live",
                    AudioWhisperLiveToDataTransformChannel,
                ),
                "target": ("stst", STSTTarget),
            },
        )
