"""Loader de integraciones."""
import importlib
from typing import List
from config import Config

def load_integrations(config: Config, tool_registry) -> List[str]:
    loaded = []
    # Usamos getattr en caso de que config.integrations no sea un dict real
    if not hasattr(config, "integrations"):
        return []
        
    try:
        # Integración de ejemplo
        if hasattr(config.integrations, "openclaw") and config.integrations.openclaw.enabled:
            mod = importlib.import_module("tuki.integrations.example_openclaw")
            if hasattr(mod, "OpenClawIntegration"):
                integration = mod.OpenClawIntegration()
                # Dummy config
                if integration.validate_config({}):
                    integration.setup(tool_registry)
                    loaded.append(integration.name)
    except Exception as e:
        print(f"Warning: Error cargando integración: {e}")
        
    return loaded
