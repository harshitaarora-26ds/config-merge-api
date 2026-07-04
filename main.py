import os
from typing import Any, Dict

import yaml
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DEFAULTS: Dict[str, Any] = {
    "port": 8000,
    "workers": 1,
    "debug": False,
    "log_level": "info",
    "api_key": "default-secret-000",
}

APP_ENV = os.environ.get("APP_ENV", "development")
YAML_PATH = os.path.join(BASE_DIR, f"config.{APP_ENV}.yaml")
DOTENV_PATH = os.path.join(BASE_DIR, ".env")


def resolve_alias(key: str) -> str:
    """NUM_WORKERS is a special alias for the 'workers' key."""
    if key.strip().upper() == "NUM_WORKERS":
        return "workers"
    return key


def strip_app_prefix(key: str) -> str:
    if key.upper().startswith("APP_"):
        return key[4:].lower()
    return key.lower()


def load_yaml_layer() -> Dict[str, Any]:
    if os.path.exists(YAML_PATH):
        with open(YAML_PATH, "r") as f:
            data = yaml.safe_load(f) or {}
        return {str(k).lower(): v for k, v in data.items()}
    return {}


def parse_dotenv_file(path: str) -> Dict[str, str]:
    result: Dict[str, str] = {}
    if not os.path.exists(path):
        return result
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            k, v = line.split("=", 1)
            result[k.strip()] = v.strip().strip('"').strip("'")
    return result


def load_dotenv_layer() -> Dict[str, Any]:
    layer: Dict[str, Any] = {}
    raw = parse_dotenv_file(DOTENV_PATH)
    for k, v in raw.items():
        canon = resolve_alias(k)
        if canon != "workers":
            canon = strip_app_prefix(k)
        layer[canon] = v
    return layer


def load_os_env_layer() -> Dict[str, Any]:
    layer: Dict[str, Any] = {}
    for k, v in os.environ.items():
        if k.upper() == "NUM_WORKERS":
            layer["workers"] = v
        elif k.upper().startswith("APP_"):
            layer[strip_app_prefix(k)] = v
    return layer


def coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes", "on"}


def coerce_value(key: str, value: Any) -> Any:
    if key == "port":
        return int(value)
    if key == "workers":
        return int(value)
    if key == "debug":
        return coerce_bool(value)
    return str(value)


@app.get("/effective-config")
async def effective_config(request: Request):
    merged: Dict[str, Any] = dict(DEFAULTS)

    for layer in (load_yaml_layer(), load_dotenv_layer(), load_os_env_layer()):
        for k, v in layer.items():
            merged[k] = v

    # CLI overrides: repeated ?set=key=value query params, highest precedence
    for name, val in request.query_params.multi_items():
        if name != "set" or "=" not in val:
            continue
        raw_key, raw_val = val.split("=", 1)
        raw_key = raw_key.strip()
        canon_key = resolve_alias(raw_key)
        if canon_key != "workers":
            canon_key = canon_key.lower()
        merged[canon_key] = raw_val

    result: Dict[str, Any] = {}
    for k, v in merged.items():
        if k == "api_key":
            continue
        result[k] = coerce_value(k, v)

    result["api_key"] = "****"

    return result


@app.get("/")
async def root():
    return {"status": "ok", "service": "effective-config"}
