import tomllib
import shutil
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional
import sys

# Config for CLI
def get_app_dir() -> Path:
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent.absolute()
    return Path(__file__).parent.absolute()

# Config for Ollama
@dataclass
class ModelConfig:
    name: str = "deepseek-coder:1.3b"
    provider: str = "ollama"
    temperature: float = 0.2
    max_tokens: int = 4096
    context_window: int = 32768

# Config for Agent autonomy
@dataclass
class AgentConfig:
    risk_level: str = "medium"
    autonomy_level: str = "low"
    language: str = "es"
    think_aloud: bool = True
    stream: bool = True

# Config for Search
@dataclass
class SearchConfig:
    use_ripgrep: bool = True
    max_depth: int = 8
    ignored_paths: List[str] = field(default_factory=lambda: ["node_modules", ".git", "__pycache__", ".venv", "venv", "dist", "build", ".next"])


@dataclass
class HistoryConfig:
    save_conversations: bool = True
    max_conversations: int = 100

@dataclass
class OpenClawConfig:
    enabled: bool = False

# Config for OpenRouter if want to use it OpenRouter instead of Ollama
@dataclass
class OpenRouterConfig:
    enabled: bool = False
    api_key: str = ""
    models: List[str] = field(default_factory=lambda: ["openai/gpt-4o", "anthropic/claude-3.5-sonnet"])
    model: str = "claude-3-5-sonnet-20240620"

@dataclass
class GeminiConfig:
    enabled: bool = False
    api_key: str = ""
    model: str = "gemini-1.5-pro"
    models: List[str] = field(default_factory=lambda: ["gemini-1.5-pro", "gemini-1.5-flash"])

@dataclass
class AnthropicConfig:
    enabled: bool = False
    api_key: str = ""
    model: str = "claude-3-5-sonnet-20240620"
    models: List[str] = field(default_factory=lambda: ["claude-3-5-sonnet-20240620", "claude-3-opus-20240229"])

# Config for Integrations
@dataclass
class IntegrationsConfig:
    openclaw: OpenClawConfig = field(default_factory=OpenClawConfig)


@dataclass
class Config:
    model: ModelConfig = field(default_factory=ModelConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    search: SearchConfig = field(default_factory=SearchConfig)
    history: HistoryConfig = field(default_factory=HistoryConfig)
    integrations: IntegrationsConfig = field(default_factory=IntegrationsConfig)
    openrouter: OpenRouterConfig = field(default_factory=OpenRouterConfig)
    gemini: GeminiConfig = field(default_factory=GeminiConfig)
    anthropic: AnthropicConfig = field(default_factory=AnthropicConfig)

    def save(self):
        save_config(self)

_config_instance: Optional[Config] = None

def _dict_to_dataclass(dc_type, data_dict):
    import dataclasses
    if not dataclasses.is_dataclass(dc_type):
        return data_dict
    
    fieldtypes = {f.name: f.type for f in dataclasses.fields(dc_type)}
    kwargs = {}
    for key, value in data_dict.items():
        if key in fieldtypes:
            ftype = fieldtypes[key]
            if dataclasses.is_dataclass(ftype):
                kwargs[key] = _dict_to_dataclass(ftype, value)
            else:
                kwargs[key] = value
    return dc_type(**kwargs)

def load_config() -> Config:
    """
    Carga y valida tukicode.toml. Si no existe, lo crea a partir del example.
    """
    global _config_instance
    if _config_instance is not None:
        return _config_instance

    base_dir = get_app_dir()
    config_path = base_dir / "tukicode.toml"
    example_path = base_dir / "tukicode.toml.example"

    if not config_path.exists():
        if example_path.exists():
            shutil.copy(example_path, config_path)
            print("⚠️ File 'tukicode.toml' not found. A new one has been created from the example.")
        else:
            print("⚠️ Neither 'tukicode.toml' nor 'tukicode.toml.example' found. Using default configuration.")
            _config_instance = Config()
            return _config_instance

    with open(config_path, "rb") as f:
        data = tomllib.load(f)

    model_cfg = _dict_to_dataclass(ModelConfig, data.get("model", {}))
    agent_cfg = _dict_to_dataclass(AgentConfig, data.get("agent", {}))
    search_cfg = _dict_to_dataclass(SearchConfig, data.get("search", {}))
    history_cfg = _dict_to_dataclass(HistoryConfig, data.get("history", {}))
    
    integ_data = data.get("integrations", {})
    openclaw_cfg = _dict_to_dataclass(OpenClawConfig, integ_data.get("openclaw", {}))
    integ_cfg = IntegrationsConfig(openclaw=openclaw_cfg)

    _config_instance = Config(
        model=model_cfg,
        agent=agent_cfg,
        search=search_cfg,
        history=history_cfg,
        integrations=integ_cfg,
        openrouter=_dict_to_dataclass(OpenRouterConfig, data.get("openrouter", {}))
    )
    return _config_instance

def save_config(config: Config):
    """
    Sobreescribe el toml con la configuración actual.
    """
    base_dir = get_app_dir()
    config_path = base_dir / "tukicode.toml"
    
    toml_str = f'''[model]
name = "{config.model.name}"
provider = "{config.model.provider}"
temperature = {config.model.temperature}
max_tokens = {config.model.max_tokens}
context_window = {config.model.context_window}

[agent]
risk_level = "{config.agent.risk_level}"
autonomy_level = "{config.agent.autonomy_level}"
language = "{config.agent.language}"
think_aloud = {"true" if config.agent.think_aloud else "false"}
stream = {"true" if config.agent.stream else "false"}

[search]
use_ripgrep = {"true" if config.search.use_ripgrep else "false"}
max_depth = {config.search.max_depth}
ignored_paths = {str(config.search.ignored_paths).replace("'", '"')}

[history]
save_conversations = {"true" if config.history.save_conversations else "false"}
max_conversations = {config.history.max_conversations}

[integrations.openclaw]
enabled = {"true" if config.integrations.openclaw.enabled else "false"}

[gemini]
enabled = {str(config.gemini.enabled).lower()}
model = "{config.gemini.model}"
api_key = "{config.gemini.api_key}"
models = {str(config.gemini.models).replace("'", '"')}

[anthropic]
enabled = {str(config.anthropic.enabled).lower()}
model = "{config.anthropic.model}"
api_key = "{config.anthropic.api_key}"
models = {str(config.anthropic.models).replace("'", '"')}

[openrouter]
enabled = {str(config.openrouter.enabled).lower()}
api_key = "{config.openrouter.api_key}"
models = {str(config.openrouter.models).replace("'", '"')}
'''
    with open(config_path, "w", encoding="utf-8") as f:
        f.write(toml_str)
