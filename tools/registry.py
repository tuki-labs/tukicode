import inspect
from typing import Dict, Any, Callable, List
from .base import BaseTool, ToolResult, RiskLevel, ToolExecutionError

class ToolPermissionError(Exception):
    pass

class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, Any] = {}

    def register(self, tool_obj: Any):
        """Registra una instancia de BaseTool o una función decorada con @tool."""
        if isinstance(tool_obj, BaseTool):
            self._tools[tool_obj.name] = tool_obj
        elif callable(tool_obj) and hasattr(tool_obj, "__tool_name__"):
            self._tools[tool_obj.__tool_name__] = tool_obj
        else:
            raise ValueError(f"Objeto no es una tool válida: {tool_obj}")

    def execute(self, tool_name: str, args: dict, risk_level_str: str) -> ToolResult:
        """Ejecuta una herramienta verificando los permisos."""
        if tool_name not in self._tools:
            return ToolResult(success=False, output="", error=f"Herramienta '{tool_name}' no encontrada.")
        
        tool_item = self._tools[tool_name]
        
        tool_risk = tool_item.risk_level if isinstance(tool_item, BaseTool) else getattr(tool_item, "__tool_risk__")
        config_risk = RiskLevel.from_string(risk_level_str)
        
        if tool_risk.value > config_risk.value:
            raise ToolPermissionError(f"Permiso denegado. La herramienta '{tool_name}' requiere risk {tool_risk.name}, nivel actual {config_risk.name}")
        
        try:
            if isinstance(tool_item, BaseTool):
                return tool_item.execute(args)
            else:
                # Es una función
                return tool_item(**args)
        except TypeError as e:
            return ToolResult(success=False, output="", error=f"Argumentos inválidos para {tool_name}: {str(e)}")
        except Exception as e:
            return ToolResult(success=False, output="", error=f"Error ejecutando {tool_name}: {str(e)}")

    def get_schema(self) -> List[dict]:
        """Obtiene el esquema de todas las tools para el prompt."""
        schema = []
        for name, tool_item in self._tools.items():
            if isinstance(tool_item, BaseTool):
                desc = tool_item.description
                # Para simplificar, extraemos los argumentos dinámicamente si es posible
            else:
                desc = getattr(tool_item, "__tool_description__")
                sig = inspect.signature(tool_item)
                args_schema = {}
                for param_name, param in sig.parameters.items():
                    args_schema[param_name] = str(param.annotation.__name__) if hasattr(param.annotation, "__name__") else "any"
                
                schema.append({
                    "name": name,
                    "description": desc,
                    "args": args_schema
                })
        return schema

registry = ToolRegistry()

# Auto-registro
from . import file_tools
from . import shell_tools
from . import search_tools
