"""Compatibility shim — the primary UI is agent.main_window.MainWindow."""

from agent.main_window import AppController as SettingsController
from agent.main_window import MainWindow

__all__ = ["SettingsController", "MainWindow"]
