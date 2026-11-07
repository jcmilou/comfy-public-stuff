#!/usr/bin/env bash
# Bootstrap for the Hearmeman MiniMax image; never create /workspace.
set -euo pipefail

stage_dir="$(mktemp -d /tmp/personal-extras.XXXXXXXX)"
hook="$stage_dir/additional_params.sh"
curl -fsSL --retry 4 --retry-delay 5 --retry-all-errors \
    https://raw.githubusercontent.com/jcmilou/comfy-public-stuff/main/runpod-minimax-extras.sh \
    -o "$hook"
if [ ! -s "$hook" ]; then
    echo '[personal-extras] Downloaded hook is empty; refusing to start.' >&2
    exit 1
fi
bash -n "$hook"

if [ -d /workspace ]; then
    echo '[personal-extras] /workspace already exists; using the original runtime hook.'
    # Download and validate first, then publish on the same filesystem.
    pending="$(mktemp /workspace/.additional_params.XXXXXXXX)"
    cp "$hook" "$pending"
    mv -f "$pending" /workspace/additional_params.sh
    exec bash /start_script.sh
fi

echo '[personal-extras] /workspace is absent; preserving the original disk-only startup.'
# The original runtime only looks for /workspace/additional_params.sh. Without
# /workspace, run our hook after the entrypoint's TWO git syncs instead. Change
# only the final handoff in a temporary copy; do not edit the image entrypoint,
# template repository, runtime, storage selection, or ComfyUI save paths.
python3 - /start_script.sh "$stage_dir/start_script.sh" "$hook" <<'PY'
import shlex
import sys
from pathlib import Path

original, destination, hook = map(Path, sys.argv[1:])
source = original.read_text(encoding="utf-8")
handoff = "exec bash /comfyui-runtime/src/start.sh /comfyui-minimax"
lines = source.splitlines(keepends=True)
matches = [i for i, line in enumerate(lines) if line.strip() == handoff]
if len(matches) != 1 or any(line.strip() for line in lines[matches[0] + 1:]):
    raise SystemExit(
        "[personal-extras] Unsupported /start_script.sh; refusing to change startup. "
        "Expected the Hearmeman MiniMax runtime handoff as its final command."
    )
index = matches[0]
lines[index] = (
    'TEMPLATE_DIR=/comfyui-minimax bash ' + shlex.quote(str(hook)) + ' || exit $?\n'
    + lines[index]
)
destination.write_text("".join(lines), encoding="utf-8")
PY
bash -n "$stage_dir/start_script.sh"
exec bash "$stage_dir/start_script.sh"
