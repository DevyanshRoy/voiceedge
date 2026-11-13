# gateway/plugins/plugin_base.py
"""Semester 1 plugin interface; processing is intentionally a passthrough."""

from abc import ABC, abstractmethod


class Plugin(ABC):
    @abstractmethod
    def process(self, audio):
        """Return processed audio."""


class PluginManager:
    def __init__(self, plugin=None):
        self.plugin = plugin

    def process(self, audio):
        if not self.plugin:
            return audio
        try:
            return self.plugin.process(audio)
        except Exception:
            return audio