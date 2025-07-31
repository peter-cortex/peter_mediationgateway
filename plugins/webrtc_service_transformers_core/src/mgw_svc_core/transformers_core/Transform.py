from mgw_svc_core.helpers.lazy_import import LazyImport

AudioTransformModule = LazyImport('mgw_svc_core.transformers_core.audio.AudioTransform')
AudioTransform = AudioTransformModule.module.AudioTransform

VideoTransformModule = LazyImport('mgw_svc_core.transformers_core.video.VideoTransform')
VideoTransform = VideoTransformModule.module.VideoTransform

DataTransformModule = LazyImport('mgw_svc_core.transformers_core.data.DataTransform')
DataTransform = DataTransformModule.module.DataTransform


class Transform():

    @staticmethod
    def extract_tranformers(options, websocket, callId, sid, peer_connection,
                            peer_connection__dict, event_emitter=None):
        transformers = set()

        if options is not None:
            if options.get('audio_transcript'):
                target = AudioTransform.create_audio_transformer(
                    options.get('audio_transcript'), websocket, callId, sid,
                    peer_connection, peer_connection__dict, event_emitter)
                if target:
                    transformers.add(target)

            if options.get('video_transform'):
                target = VideoTransform.create_video_transformer(
                    options.get('video_transform'), websocket, callId, sid,
                    peer_connection, peer_connection__dict, event_emitter)
                if target:
                    transformers.add(target)

            if options.get('data_transform'):
                target = DataTransform.create_data_transformer(
                    options.get('data_transform'), websocket, callId, sid,
                    peer_connection, peer_connection__dict, event_emitter)
                if target:
                    transformers.add(target)
        return transformers

    @staticmethod
    def get_capabilities():

        return {
            "audio": list(map(lambda t: {
                "type": t,
                "title": AudioTransform.transformers[t][2],
                "description": AudioTransform.transformers[t][3]
                }, AudioTransform.transformers.keys())),
            "video": list(map(lambda t: {
                "type": t,
                "title": VideoTransform.transformers[t][2],
                "description": VideoTransform.transformers[t][3]
                },  VideoTransform.transformers.keys())),
            "data": list(map(lambda t: {
                "type": t,
                "title": DataTransform.transformers[t][2],
                "description": DataTransform.transformers[t][3]
                },  DataTransform.transformers.keys())),
        }
