from prompt_toolkit import PromptSession
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.styles import Style
from typing import Tuple, Optional

COMMANDS = {
    "/clear": "Clears the current context",
    "/model": "Changes the active model",
    "/risk": "Changes the risk level",
    "/history": "Shows the history",
    "/exit": "Exits TukiCode"
}

class TukiInput:
    def __init__(self):
        self.history = InMemoryHistory()
        self.session = PromptSession(history=self.history)
        self.style = Style.from_dict({
            'prompt': 'ansicyan bold',
        })

    def get_input(self, session_history=None) -> Optional[str]:
        try:
            # Multiline se puede habilitar si se desea, por ahora single line
            text = self.session.prompt([('class:prompt', 'tuki > ')], style=self.style)
            return text.strip()
        except KeyboardInterrupt:
            return None
        except EOFError:
            return None

    def is_command(self, text: str) -> Tuple[bool, str, str]:
        text = text.strip()
        if text.startswith("/"):
            parts = text.split(" ", 1)
            cmd = parts[0]
            args = parts[1] if len(parts) > 1 else ""
            return True, cmd, args
        return False, "", ""
