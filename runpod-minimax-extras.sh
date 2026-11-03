#!/usr/bin/env bash
# RunPod / Hearmeman MiniMax: extra models and custom nodes.
# Run by the author's runtime as /workspace/additional_params.sh.
# Install our helper, then extend the original model/custom-node configuration.
set -euo pipefail

python3 - <<'PY'
import json
import os
from pathlib import Path
from urllib.request import urlopen

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

# The helper includes its browser extension; installing only __init__.py would
# omit the fix for Primitive inputs connected through subgraphs.
HELPER_BASE = "https://raw.githubusercontent.com/jcmilou/comfy-public-stuff/main/custom_nodes/ComfyUI-PromptHelper/"
helper_files = {}
for relative in ("__init__.py", "web/extension.js", "web/primitive-inputs.js"):
    with urlopen(HELPER_BASE + relative, timeout=60) as response:
        helper_files[relative] = response.read()
compile(helper_files["__init__.py"].decode("utf-8"), "ComfyUI-PromptHelper/__init__.py", "exec")
# Fetch the complete package before replacing anything in the installed copy.
node_dir = Path("/ComfyUI/custom_nodes/ComfyUI-PromptHelper")
for relative, source in helper_files.items():
    target = node_dir / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    pending = target.with_name(target.name + ".pending")
    pending.write_bytes(source)
    pending.replace(target)
print("[personal-extras] Installed ComfyUI-PromptHelper (OpenRouter / Local).")

if not EXTRA_MODELS and not EXTRA_CUSTOM_NODES:
    print("[personal-extras] No additional models or other custom nodes configured.")
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
