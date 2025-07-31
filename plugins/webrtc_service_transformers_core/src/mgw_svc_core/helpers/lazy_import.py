import importlib

class LazyImport:
    def __init__(self, module_name):
        self.module_name = module_name
        self._module = None

    @property
    def module(self):
        if self._module is None:
            self._module = importlib.import_module(self.module_name)
        return self._module