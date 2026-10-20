from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path


SERVICE_ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = SERVICE_ROOT / "configs" / "china_fridge_catalog_v1.json"
METADATA_PATH = SERVICE_ROOT / "configs" / "fridge_metadata_v1.json"


@lru_cache(maxsize=1)
def load_catalog() -> dict:
    base = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    defaults = metadata.get("category_defaults", {})
    overrides = metadata.get("overrides", {})

    classes = []
    for item in [*base["classes"], *metadata.get("additional_classes", [])]:
        category_defaults = defaults.get(item["category"], {})
        merged = {
            **category_defaults,
            **item,
            **overrides.get(item["id"], {}),
        }
        aliases_zh = list(dict.fromkeys(merged.get("aliases_zh", [])))
        merged["aliases_zh"] = aliases_zh
        merged["display_name"] = merged["name_zh"]
        merged["search_terms"] = list(
            dict.fromkeys(
                [
                    merged["id"],
                    merged["name_zh"],
                    merged["name_en"],
                    *aliases_zh,
                    *merged.get("model_labels", []),
                    merged.get("prompt", ""),
                ]
            )
        )
        classes.append(merged)

    return {
        "version": base["version"],
        "description": base["description"],
        "classes": classes,
    }


@lru_cache(maxsize=1)
def label_index() -> dict[str, dict]:
    index = {}
    for item in load_catalog()["classes"]:
        labels = [
            item["id"],
            item["name_zh"],
            item["name_en"],
            *item.get("model_labels", []),
        ]
        for label in labels:
            index[label.casefold()] = item
    return index


def find_class(label: str) -> dict | None:
    return label_index().get(label.strip().casefold())


def display_name(label: str, fallback: str = "") -> str:
    item = find_class(label)
    if item:
        return item["name_zh"]
    return fallback or "未知食材"


def is_fridge_candidate(label: str) -> bool:
    return find_class(label) is not None


def world_vocabulary() -> tuple[list[str], dict[str, str]]:
    prompts = []
    label_map = {}
    for item in load_catalog()["classes"]:
        prompt = item["prompt"]
        prompts.append(prompt)
        label_map[prompt] = item["id"]
    return prompts, label_map


def export_catalog() -> dict:
    return load_catalog()
