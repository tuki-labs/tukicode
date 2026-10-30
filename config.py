import tomllib
import json
import os
import tempfile
import shutil
from pathlib import Path
from dataclasses import asdict, dataclass, field
from typing import List, Optional
import sys

# Config for CLI
def get_app_dir() -> Path:
    frozen = getattr(sys, 'frozen', False)
    legacy = Path(sys.executable if frozen else __file__).parent.absolute()
    # Preserve existing installations and editable source checkouts.
    if (legacy / "tukicode.toml").exists() or (not frozen and (legacy / ".git").is_dir()):
        return legacy
    # Installed packages/binaries may live in read-only directories.
    if sys.platform == "win32":
        root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "TukiCode"
    else:
        root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "tukicode"
    root.mkdir(parents=True, exist_ok=True)
    return root

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
    setup_completed: bool = False

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
        openrouter=_dict_to_dataclass(OpenRouterConfig, data.get("openrouter", {})),
        gemini=_dict_to_dataclass(GeminiConfig, data.get("gemini", {})),
        anthropic=_dict_to_dataclass(AnthropicConfig, data.get("anthropic", {})),
        setup_completed=data.get("setup_completed") is True,
    )
    return _config_instance

def _dump_toml(data: dict) -> str:
    """Serialize configuration values with TOML-compatible string escaping."""
    lines = []
    def write_table(values, path=()):
        if path:
            lines.append("[" + ".".join(path) + "]")
        for key, value in values.items():
            if not isinstance(value, dict):
                encoded = json.dumps(value, ensure_ascii=False, allow_nan=False).replace("\x7f", "\\u007f")
                lines.append(f"{key} = {encoded}")
        lines.append("")
        for key, value in values.items():
            if isinstance(value, dict):
                write_table(value, path + (key,))
    write_table(data)
    text = "\n".join(lines)
    tomllib.loads(text)  # Never replace a working config with invalid TOML.
    return text


def save_config(config: Config):
    """Atomically save all providers, escaping paths, quotes and control characters."""
    config_path = get_app_dir() / "tukicode.toml"
    text = _dump_toml(asdict(config))
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=config_path.parent,
                                         prefix=".tukicode-", suffix=".tmp", delete=False) as output:
            temporary_path = Path(output.name)
            output.write(text)
        os.replace(temporary_path, config_path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
