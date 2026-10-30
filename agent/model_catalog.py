"""Public OpenRouter coding recommendations; never sends user credentials."""
from dataclasses import dataclass
from datetime import datetime, timezone, date
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import re

import httpx

MODELS_URL = "https://openrouter.ai/api/v1/models"
KEYS_URL = "https://openrouter.ai/settings/keys"
MODELS_PAGE = "https://openrouter.ai/models?fmt=cards&supported_parameters=tools"

# Tool capability does not guarantee access for a standalone app. These free
# endpoints are limited to agentic harnesses; Small rejected TukiCode with 403
# (verified 2026-10-30). Paid variants are not excluded.
# Sources: https://openrouter.ai/thinkingmachines/inkling-small:free
#          https://openrouter.ai/thinkingmachines/inkling:free
RESTRICTED_APP_MODELS = {
    "thinkingmachines/inkling-small:free",
    "thinkingmachines/inkling:free",
}


@dataclass(frozen=True)
class CodingModel:
    id: str
    context: int
    input_price: Decimal | None
    output_price: Decimal | None

    @property
    def free(self):
        return self.input_price == 0 and self.output_price == 0

    @property
    def price_label(self):
        if self.free:
            return "Free"
        def price(value):
            return "?" if value is None else f"${value * 1_000_000:,.2f}"
        return f"{price(self.input_price)} / {price(self.output_price)}"


@dataclass(frozen=True)
class CodingCatalog:
    models: tuple[CodingModel, ...]
    fetched_at: str
    cached: bool = False

    def recommendations(self):
        # Keep the upstream coding order, adding affordable alternatives explicitly.
        top = list(self.models[:6])
        for model in [m for m in self.models if m.free][:3]:
            if model not in top:
                top.append(model)
        return top


def _price(value):
    try:
        result = Decimal(str(value))
        return result if result.is_finite() and result >= 0 else None
    except (InvalidOperation, ValueError):
        return None


def _parse_models(data):
    if not isinstance(data, list):
        raise ValueError("Invalid catalog")
    models, seen = [], set()
    for item in data:
        if not isinstance(item, dict):
            continue
        model_id = item.get("id", "")
        if not isinstance(model_id, str) or not re.fullmatch(r"[\w.-]+/[\w./:+-]+", model_id):
            continue
        if model_id in seen or model_id.endswith(":batch") or model_id.startswith("openrouter/"):
            continue
        if model_id in RESTRICTED_APP_MODELS:
            continue
        supported = item.get("supported_parameters")
        if not isinstance(supported, list) or "tools" not in supported:
            continue
        architecture = item.get("architecture") or {}
        if not isinstance(architecture, dict):
            continue
        if "text" not in architecture.get("output_modalities", ["text"]):
            continue
        endpoints = item.get("endpoints")
        if endpoints is not None and (not isinstance(endpoints, list) or "/api/v1/chat/completions" not in endpoints):
            continue
        try:
            if item.get("expiration_date") and date.fromisoformat(item["expiration_date"]) < datetime.now(timezone.utc).date():
                continue
            context = int(item.get("context_length", 0))
            if context <= 0:
                continue
        except (ValueError, TypeError):
            continue
        pricing = item.get("pricing") or {}
        if not isinstance(pricing, dict):
            continue
        models.append(CodingModel(model_id, context, _price(pricing.get("prompt")), _price(pricing.get("completion"))))
        seen.add(model_id)
    if not models:
        raise ValueError("No tool-capable chat models found")
    return tuple(models)


def fetch_coding_catalog(cache_path: Path) -> CodingCatalog:
    """Request benchmark ordering, not popularity or release-date ordering.

    Unscored entries are placed last by OpenRouter. This is an upstream
    recommendation signal, not a guarantee of performance on a user's task.
    """
    try:
        with httpx.Client(timeout=10, follow_redirects=False) as client:
            response = client.get(MODELS_URL, params={
                "sort": "coding-high-to-low", "supported_parameters": "tools",
            })
            response.raise_for_status()
            data = response.json()["data"]
        models = _parse_models(data)
        fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as error:
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            if cached["sort"] != "coding-high-to-low":
                raise ValueError("Unknown cached ordering")
            return CodingCatalog(_parse_models(cached["data"]), cached["fetched_at"], True)
        except (OSError, ValueError, KeyError, TypeError):
            raise RuntimeError("OpenRouter catalog unavailable; no usable cached catalog.") from None
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = cache_path.with_suffix(".tmp")
        temporary.write_text(json.dumps({"sort": "coding-high-to-low", "fetched_at": fetched_at, "data": data}), encoding="utf-8")
        temporary.replace(cache_path)
    except OSError:
        pass  # A read-only cache must not discard a successful online result.
    return CodingCatalog(models, fetched_at)


def choose_coding_model(console, current_model, cache_path, excluded_models=()):
    import typer
    from rich.table import Table
    from rich.text import Text

    console.print("Fetching current OpenRouter coding models...")
    try:
        catalog = fetch_coding_catalog(cache_path)
    except RuntimeError:
        console.print("[yellow]Catalog unavailable. Tool support could not be checked; enter a model ID manually.[/yellow]")
        console.print(f"Browse tool-capable models: [link={MODELS_PAGE}]{MODELS_PAGE}[/link]")
        return typer.prompt("OpenRouter model ID", default=current_model or None).strip()

    state = "CACHED (online lookup failed)" if catalog.cached else "LIVE"
    catalog = CodingCatalog(tuple(m for m in catalog.models if m.id not in excluded_models), catalog.fetched_at, catalog.cached)
    if not catalog.models:
        console.print("[yellow]No untried compatible models remain. Configuration was not changed.[/yellow]")
        raise typer.Abort()
    console.print(Text(f"{state} | Catalog fetched: {catalog.fetched_at}"))
    console.print("Order: OpenRouter coding index (Artificial Analysis). Unscored models appear last.")
    console.print("Listed models advertise tools; known app-restricted endpoints are excluded. Account access may vary.")
    choices = catalog.recommendations()
    table = Table(title="Coding models + free alternatives")
    for heading in ("#", "Model ID", "Context", "USD / 1M tokens (in / out)"):
        table.add_column(heading)
    for index, model in enumerate(choices, 1):
        table.add_row(str(index), Text(model.id), f"{model.context:,}", model.price_label)
    console.print(table)
    console.print("Free models may have stricter limits. Token prices exclude other charges or pricing tiers.")
    available = {model.id for model in catalog.models}
    default = current_model if current_model in available else None
    while True:
        answer = typer.prompt("Choose a number or enter a model ID", default=default).strip()
        if answer.isdecimal():
            number = int(answer)
            if 1 <= number <= len(choices):
                return choices[number - 1].id
        elif answer in available:
            return answer
        console.print("[yellow]Choose a listed number or a tool-capable model ID from this catalog.[/yellow]")
