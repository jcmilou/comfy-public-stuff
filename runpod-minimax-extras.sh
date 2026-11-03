#!/usr/bin/env bash
# RunPod / Hearmeman MiniMax: extra models and custom nodes.
# Run by the author's runtime as /workspace/additional_params.sh.
# Install our helper and fixed node snapshots, then register extra downloads.
set -euo pipefail

python3 - <<'PY'
import json
import hashlib
import os
import subprocess
import sys
import time
from http.client import IncompleteRead
from pathlib import Path, PurePosixPath
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import urlopen

EXTRA_MODELS = {
    "qwen_image_2.1_int8_convrot.safetensors": {
        "url": "https://huggingface.co/Comfy-Org/Qwen-Image-2.1/resolve/main/diffusion_models/qwen_image_2.1_int8_convrot.safetensors",
        "subdir": "diffusion_models",
    },
    "qwen3vl_8b_int8_convrot.safetensors": {
        "url": "https://huggingface.co/Comfy-Org/Qwen3-VL/resolve/main/text_encoders/qwen3vl_8b_int8_convrot.safetensors",
        "subdir": "text_encoders",
    },
    "qwen_image_2.1_vae_bf16.safetensors": {
        "url": "https://huggingface.co/Comfy-Org/Qwen-Image-2.1/resolve/main/vae/qwen_image_2.1_vae_bf16.safetensors",
        "subdir": "vae",
    },
    "H3_Motion_BoosterV2.safetensors": {
        "url": "https://huggingface.co/bilmemne13/1/resolve/main/H3_Motion_BoosterV2.safetensors",
        "subdir": "loras",
    },
    "minimax_music3_dit_fp16.safetensors": {
        "url": "https://huggingface.co/Comfy-Org/MiniMax-Music-3/resolve/main/diffusion_models/minimax_music3_dit_fp16.safetensors",
        "subdir": "diffusion_models",
    },
    "minimax_music3_text_encoder_pruned_int8_convrot.safetensors": {
        "url": "https://huggingface.co/Comfy-Org/MiniMax-Music-3/resolve/main/text_encoders/minimax_music3_text_encoder_pruned_int8_convrot.safetensors",
        "subdir": "text_encoders",
    },
    "minimax_music3_dav.safetensors": {
        "url": "https://huggingface.co/Comfy-Org/MiniMax-Music-3/resolve/main/vae/minimax_music3_dav.safetensors",
        "subdir": "vae",
    },
    "qwen3vl_8b_bf16.safetensors": {
        "url": "https://huggingface.co/Comfy-Org/Qwen-Image-2.1/resolve/main/text_encoders/qwen3vl_8b_bf16.safetensors",
        "subdir": "text_encoders",
    },
}

EXTRA_CUSTOM_NODES = [
    # "https://github.com/OWNER/ComfyUI-MyNode.git",
    # Optional pinned revision: "https://github.com/OWNER/ComfyUI-MyNode.git|COMMIT_SHA",
]

CUSTOM_NODES_ROOT = Path("/ComfyUI/custom_nodes")
PUBLIC_BASE = "https://raw.githubusercontent.com/jcmilou/comfy-public-stuff/main/"
SNAPSHOT_MANIFEST_SHA256 = "9e364f428212e2bbd98c25c148c9deb8440c982e9f62f56115a727ca9c4b4123"
SNAPSHOT_VERSIONS = {"openrouter_node": "1.0.2", "derfuu_comfyui_moddednodes": "1.0.1"}

def download_bytes(url):
    for attempt in range(1, 6):
        try:
            with urlopen(url, timeout=60) as response:
                return response.read()
        except HTTPError as error:
            if error.code not in (408, 429) and not 500 <= error.code < 600:
                raise
            if attempt == 5:
                raise
        except (OSError, IncompleteRead):
            if attempt == 5:
                raise
        delay = attempt * 5
        print(f"[personal-extras] Download {url.rsplit('/', 1)[-1]} failed "
              f"(attempt {attempt}/5); retrying in {delay}s.", flush=True)
        time.sleep(delay)


# The helper includes its browser extension; installing only __init__.py would
# omit the fix for Primitive inputs connected through subgraphs.
HELPER_BASE = "https://raw.githubusercontent.com/jcmilou/comfy-public-stuff/main/custom_nodes/ComfyUI-PromptHelper/"
helper_files = {}
for relative in ("__init__.py", "web/extension.js", "web/primitive-inputs.js"):
    helper_files[relative] = download_bytes(HELPER_BASE + relative)
compile(helper_files["__init__.py"].decode("utf-8"), "ComfyUI-PromptHelper/__init__.py", "exec")
# Fetch the complete package before replacing anything in the installed copy.
node_dir = CUSTOM_NODES_ROOT / "ComfyUI-PromptHelper"
for relative, source in helper_files.items():
    target = node_dir / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    pending = target.with_name(target.name + ".pending")
    pending.write_bytes(source)
    pending.replace(target)
print("[personal-extras] Installed ComfyUI-PromptHelper (OpenRouter / Local).")

# Only our repository is contacted for the snapshots, never the upstream repos
# or registry. The manifest and every file are fixed by SHA256, not by 'latest'.
manifest_bytes = download_bytes(PUBLIC_BASE + "runpod-node-snapshots.json")
if hashlib.sha256(manifest_bytes).hexdigest() != SNAPSHOT_MANIFEST_SHA256:
    raise RuntimeError("[personal-extras] Node snapshot manifest SHA256 mismatch.")
snapshots = json.loads(manifest_bytes)
if {name: item["version"] for name, item in snapshots.items()} != SNAPSHOT_VERSIONS:
    raise RuntimeError("[personal-extras] Unexpected custom node versions.")

# Verify all files before replacing installed copies. Reuse unchanged local
# files; preserve user configuration and chats, which are not in the manifest.
snapshot_files = {}
for name, snapshot in snapshots.items():
    for relative, expected_hash in snapshot["files"].items():
        path = PurePosixPath(relative)
        if path.is_absolute() or ".." in path.parts or "\\" in relative:
            raise ValueError(f"Invalid snapshot path: {relative}")
        target = CUSTOM_NODES_ROOT / name / relative
        source = target.read_bytes() if target.is_file() else b""
        if hashlib.sha256(source).hexdigest() != expected_hash:
            source = download_bytes(PUBLIC_BASE + quote(f"custom_nodes/{name}/{relative}"))
        if hashlib.sha256(source).hexdigest() != expected_hash:
            raise RuntimeError(f"[personal-extras] SHA256 mismatch: {name}/{relative}")
        if relative.endswith(".py"):
            compile(source, f"{name}/{relative}", "exec")
        snapshot_files[target] = source

for target, source in snapshot_files.items():
    if target.is_file() and target.read_bytes() == source:
        continue
    target.parent.mkdir(parents=True, exist_ok=True)
    pending = target.with_name(target.name + ".pending")
    pending.write_bytes(source)
    pending.replace(target)

for name, version in SNAPSHOT_VERSIONS.items():
    node_dir = CUSTOM_NODES_ROOT / name
    requirements = node_dir / "requirements.txt"
    # Only run the requirements shipped in the verified snapshot. pip uses the
    # same Python as this hook and respects the image's PIP_CONSTRAINT.
    if "requirements.txt" in snapshots[name]["files"]:
        print(f"[personal-extras] Installing {name} {version} requirements...", flush=True)
        subprocess.run([sys.executable, "-m", "pip", "install", "-r", str(requirements)],
                       cwd=str(node_dir), check=True)
    else:
        print(f"[personal-extras] {name} {version}: no requirements.txt.")
    print(f"[personal-extras] Installed snapshot {name} {version}.")

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
