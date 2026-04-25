from abc import ABC, abstractmethod
from typing import List, Dict, Any

class BaseIntegration(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        pass

    @property
    @abstractmethod
    def required_config_keys(self) -> List[str]:
        pass

    def validate_config(self, config: Dict[str, Any]) -> bool:
        for key in self.required_config_keys:
            if key not in config:
                print(f"Falta configuración '{key}' para la integración {self.name}.")
                return False
        return True

    @abstractmethod
    def setup(self, tool_registry) -> None:
        pass

    @abstractmethod
    def teardown(self) -> None:
        pass
