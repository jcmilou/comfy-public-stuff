#!/usr/bin/env bash
# RunPod / Hearmeman MiniMax: extra models and custom nodes.
# Run by the author's runtime as /workspace/additional_params.sh.
# This only extends its configuration; the original installer does the work.
set -euo pipefail

python3 - <<'PY'
import json
import os
from pathlib import Path

# Add actual entries here. The commented examples are NOT enabled.
EXTRA_MODELS = {
    # "my-text-encoder.safetensors": {
    #     "url": "https://huggingface.co/OWNER/REPO/resolve/main/my-text-encoder.safetensors",
    #     "subdir": "text_encoders",
    # },
    # Other subdir examples: diffusion_models, vae, loras.
}

EXTRA_CUSTOM_NODES = [
    # "https://github.com/OWNER/ComfyUI-MyNode.git",
    # Optional pinned revision: "https://github.com/OWNER/ComfyUI-MyNode.git|COMMIT_SHA",
]

if not EXTRA_MODELS and not EXTRA_CUSTOM_NODES:
    print("[personal-extras] Example loaded; no extra models or nodes configured.")
    raise SystemExit(0)

# TEMPLATE_DIR is exported by the author's runtime before executing this hook.
root = Path(os.environ["TEMPLATE_DIR"])
template_path = root / "template.json"
registry_path = root / "src" / "models_registry.json"
template = json.loads(template_path.read_text(encoding="utf-8"))
registry = json.loads(registry_path.read_text(encoding="utf-8"))

# Keep the author's existing models, flags and nodes.
registry.update(EXTRA_MODELS)
if EXTRA_MODELS:
    extras = template.setdefault("flags", {}).setdefault(
        "download_personal_extras", {"default": True, "folders": [], "extra_models": []}
    )
    for filename in EXTRA_MODELS:
        if filename not in extras["extra_models"]:
            extras["extra_models"].append(filename)

if EXTRA_CUSTOM_NODES:
    repos = template.setdefault("custom_nodes", {}).setdefault("repos", [])
    for repo in EXTRA_CUSTOM_NODES:
        if repo not in repos:
            repos.append(repo)

registry_path.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")
template_path.write_text(json.dumps(template, indent=2) + "\n", encoding="utf-8")
print(f"[personal-extras] Registered {len(EXTRA_MODELS)} extra models and "
      f"{len(EXTRA_CUSTOM_NODES)} custom nodes for the original installer.")
PY
