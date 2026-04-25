import tomllib
import shutil
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional
import sys

def get_app_dir() -> Path:
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent.absolute()
    return Path(__file__).parent.absolute()

@dataclass
class ModelConfig:
    name: str = "deepseek-coder:1.3b"
    temperature: float = 0.2
    max_tokens: int = 4096
    context_window: int = 32768

@dataclass
class AgentConfig:
    risk_level: str = "medium"
    language: str = "es"
    think_aloud: bool = True
    stream: bool = True

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
        integrations=integ_cfg
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
temperature = {config.model.temperature}
max_tokens = {config.model.max_tokens}
context_window = {config.model.context_window}

[agent]
risk_level = "{config.agent.risk_level}"
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
'''
    with open(config_path, "w", encoding="utf-8") as f:
        f.write(toml_str)
