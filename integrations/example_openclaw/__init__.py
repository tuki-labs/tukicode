from typing import List
from ..base_integration import BaseIntegration
from ...tools.base import tool, ToolResult, RiskLevel

# Tools ficticias
@tool("read_emails", "Lee los últimos N correos no leídos", RiskLevel.LOW)
def read_emails(limit: int = 5) -> ToolResult:
    """Implementación ficticia que leería correos de una bandeja de entrada."""
    return ToolResult(success=True, output=f"Se simula la lectura de {limit} correos.")

@tool("send_email", "Envía un correo electrónico", RiskLevel.HIGH)
def send_email(to: str, subject: str, body: str) -> ToolResult:
    """Implementación ficticia que enviaría un correo."""
    return ToolResult(success=True, output=f"Simulación: correo enviado a {to} con asunto '{subject}'.")

@tool("search_emails", "Busca correos por palabra clave", RiskLevel.LOW)
def search_emails(query: str) -> ToolResult:
    """Implementación ficticia que buscaría correos."""
    return ToolResult(success=True, output=f"Simulación: buscando correos con '{query}'.")

class OpenClawIntegration(BaseIntegration):
    @property
    def name(self) -> str:
        return "openclaw"

    @property
    def description(self) -> str:
        return "Integración de ejemplo para gestionar correos electrónicos."

    @property
    def required_config_keys(self) -> List[str]:
        return [] # Ejemplo sin config obligatoria

    def setup(self, tool_registry) -> None:
        tool_registry.register(read_emails)
        tool_registry.register(send_email)
        tool_registry.register(search_emails)

    def teardown(self) -> None:
        pass
