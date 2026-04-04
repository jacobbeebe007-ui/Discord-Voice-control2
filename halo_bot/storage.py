"""JSON persistence for bot state (paths, load/save, in-memory stores)."""
import json
import logging
import os
import tempfile

log = logging.getLogger(__name__)

MMR_FILE = "mmr_data.json"
PRESETS_FILE = "presets.json"
TEAM_HISTORY_FILE = "team_history.json"
RECALL_FILE = "recall_channels.json"
ORBITAL_FILE = "orbital_jump.json"


def load_json(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        log.error("Invalid JSON in %s: %s", path, e)
        return {}
    except OSError as e:
        log.error("Could not read %s: %s", path, e)
        return {}


def save_json(path: str, data) -> None:
    abs_path = os.path.abspath(path)
    directory = os.path.dirname(abs_path) or "."
    fd, tmp_path = tempfile.mkstemp(dir=directory, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, abs_path)
    except OSError:
        log.exception("Failed to save JSON to %s", path)
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


mmr_data: dict = load_json(MMR_FILE)
presets: dict = load_json(PRESETS_FILE)
team_history: dict = load_json(TEAM_HISTORY_FILE)
recall_channels: dict = load_json(RECALL_FILE)
orbital_jump_data: dict = load_json(ORBITAL_FILE)
team_storage: dict = {}
