from abc import abstractmethod

class WebRTCServicePluginInterface:
    @abstractmethod
    def Register(self, data):
        pass
