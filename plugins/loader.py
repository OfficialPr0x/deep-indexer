import importlib
import pkgutil
import os
from plugins.base_plugin import AnalysisPlugin

def discover_plugins(plugin_dir="plugins"):
    plugins = []
    for finder, name, ispkg in pkgutil.iter_modules([plugin_dir]):
        if name in ("base_plugin", "loader") or name.startswith("_"):
            continue
        module = importlib.import_module(f"plugins.{name}")
        for attr in dir(module):
            obj = getattr(module, attr)
            if isinstance(obj, type) and issubclass(obj, AnalysisPlugin) and obj is not AnalysisPlugin:
                plugin_instance = obj()
                plugins.append(plugin_instance)
    return plugins 