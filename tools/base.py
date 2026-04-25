from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, Callable
from abc import ABC, abstractmethod

class RiskLevel(Enum):
    NONE = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    
    @classmethod
    def from_string(cls, level_str: str) -> "RiskLevel":
        mapping = {
            "none": cls.NONE,
            "low": cls.LOW,
            "medium": cls.MEDIUM,
            "high": cls.HIGH
        }
        return mapping.get(level_str.lower(), cls.MEDIUM)

@dataclass
class ToolResult:
    success: bool
    output: str
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

class BaseTool(ABC):
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
    def risk_level(self) -> RiskLevel:
        pass

    @abstractmethod
    def execute(self, args: dict) -> ToolResult:
        pass

class ToolExecutionError(Exception):
    """Error lanzado cuando la ejecución de una tool falla."""
    pass

def tool(name: str, description: str, risk_level: RiskLevel):
    """Decorador para registrar functions simples como tools."""
    def decorator(func: Callable):
        func.__tool_name__ = name
        func.__tool_description__ = description
        func.__tool_risk__ = risk_level
        return func
    return decorator
