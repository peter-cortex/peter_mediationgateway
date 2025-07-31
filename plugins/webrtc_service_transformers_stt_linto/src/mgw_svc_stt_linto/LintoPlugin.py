from mgw_svc_core.helpers.lazy_import import LazyImport


AudioTransformModule = LazyImport('mgw_svc_core.transformers_core.audio.AudioTransform')
AudioTransform = AudioTransformModule.module.AudioTransform

from mgw_svc_core.transformers_core.WebrtcServicePluginInterface import (
    WebRTCServicePluginInterface,
)

from mgw_svc_core.transformers_core.targets.DataTarget import (
    DataTarget,
)
from .audio.AudioLintotoDataTransformChannel import AudioLintotoDataTransformChannel


class LintoPlugin(WebRTCServicePluginInterface):
    def Register(self, data):
        AudioTransform.register_transformer(
            "linto",
            {
                "title": "Linto",
                "description": "",
                "channel": ("linto", AudioLintotoDataTransformChannel),
                "target": ("data", DataTarget),
            },
        )
