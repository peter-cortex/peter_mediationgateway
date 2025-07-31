import asyncio
from pathlib import Path
import logging.handlers
import logging

logger = logging.getLogger(__name__)


class DataListening():
    """
    A Data channel that only listen.
    """

    kind = "application"

    def __init__(self, track, channel, transform, event_emitter):
        self.transform = transform
        self.ee = event_emitter
        self.channel = channel

    @staticmethod
    def create_transformer(channel, transform, event_emitter):
        return DataListening(channel, transform, event_emitter)
