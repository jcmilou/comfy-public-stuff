"""Check the RunPod hook offline, without installing packages or fetching URLs."""
import io
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from http.client import IncompleteRead
from pathlib import Path
from urllib.error import HTTPError, URLError
from unittest.mock import patch

BASE = Path(__file__).parent
PUBLIC_BASE = "https://raw.githubusercontent.com/jcmilou/comfy-public-stuff/main/"
HELPER_BASE = PUBLIC_BASE + "custom_nodes/ComfyUI-PromptHelper/"
FILES = {
    "__init__.py": b"WEB_DIRECTORY = './web'\n",
    "web/extension.js": b"// test extension\n",
    "web/primitive-inputs.js": b"// test resolver\n",
}


class HookTests(unittest.TestCase):
    def setUp(self):
        script = (BASE / "runpod-minimax-extras.sh").read_text(encoding="utf-8")
        self.code = script.split("python3 - <<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]
        self.urls = []
        self.downloads = {HELPER_BASE + name: source for name, source in FILES.items()}
        manifest = (BASE / "runpod-node-snapshots.json").read_bytes()
        self.downloads[PUBLIC_BASE + "runpod-node-snapshots.json"] = manifest
        for name, snapshot in json.loads(manifest).items():
            for relative in snapshot["files"]:
                self.downloads[PUBLIC_BASE + f"custom_nodes/{name}/{relative}"] = (
                    BASE / "custom_nodes" / name / relative).read_bytes()

    def download(self, url, timeout):
        self.assertTrue(url.startswith(PUBLIC_BASE))
        self.assertEqual(timeout, 60)
        self.urls.append(url)
        return io.BytesIO(self.downloads[url])

    def hook_code(self, destination):
        return self.code.replace('Path("/ComfyUI/custom_nodes")',
                                 f"Path({str(destination)!r})")

    def prepare_template(self, root):
        (root / "src").mkdir()
        template = {"flags": {"download_minimax_h3": {"folders": ["MiniMax H3"]}},
                    "custom_nodes": {"target": "image", "repos": ["existing-node"]}}
        (root / "template.json").write_text(json.dumps(template), encoding="utf-8")
        (root / "src/models_registry.json").write_text(
            '{"existing-model": {"subdir": "vae"}}', encoding="utf-8")
        return template

    def execute(self, root, code=None):
        with patch("urllib.request.urlopen", side_effect=self.download), \
             patch("subprocess.run") as pip, \
             patch("time.sleep") as sleep, \
             patch.dict(os.environ, {"TEMPLATE_DIR": str(root)}, clear=True), \
             redirect_stdout(io.StringIO()):
            self.pip = pip
            self.sleep = sleep
            exec(code or self.hook_code(root / "custom_nodes"), {})
        return pip

    def test_all_downloaded_files_exist_at_their_public_repository_paths(self):
        package = BASE / "custom_nodes" / "ComfyUI-PromptHelper"
        for name in FILES:
            self.assertTrue((package / name).is_file(), name)
        compile((package / "__init__.py").read_text(encoding="utf-8"), "__init__.py", "exec")

    def test_installs_helper_and_exact_snapshots_with_requirements_only_for_openrouter(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.prepare_template(root)
            destination = root / "custom_nodes"
            pip = self.execute(root)
            for name, source in FILES.items():
                self.assertEqual((destination / "ComfyUI-PromptHelper" / name).read_bytes(), source)
            manifest = json.loads((BASE / "runpod-node-snapshots.json").read_bytes())
            self.assertEqual({n: s["version"] for n, s in manifest.items()},
                             {"openrouter_node": "1.0.2", "derfuu_comfyui_moddednodes": "1.0.1"})
            for name, snapshot in manifest.items():
                for relative, digest in snapshot["files"].items():
                    content = (destination / name / relative).read_bytes()
                    self.assertEqual(hashlib.sha256(content).hexdigest(), digest)
            node_dir = destination / "openrouter_node"
            pip.assert_called_once_with(
                [sys.executable, "-m", "pip", "install", "-r", str(node_dir / "requirements.txt")],
                cwd=str(node_dir), check=True)
            self.assertEqual(len(self.urls), len(self.downloads))

    def test_preserves_existing_models_flags_and_nodes_without_duplicate_entries(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            original = self.prepare_template(root)
            code = self.hook_code(root / "custom_nodes")
            code = code.replace('EXTRA_CUSTOM_NODES = [', 'EXTRA_CUSTOM_NODES = ["https://example.com/custom.git",', 1)
            self.execute(root, code)
            first = (root / "template.json").read_text()
            self.execute(root, code)
            self.assertEqual((root / "template.json").read_text(), first)
            configured = json.loads(first)
            self.assertEqual(configured["flags"]["download_minimax_h3"], original["flags"]["download_minimax_h3"])
            self.assertEqual(configured["custom_nodes"]["repos"], ["existing-node", "https://example.com/custom.git"])
            expected_folders = {
                "qwen_image_2.1_int8_convrot.safetensors": "diffusion_models",
                "qwen3vl_8b_int8_convrot.safetensors": "text_encoders",
                "qwen_image_2.1_vae_bf16.safetensors": "vae",
                "H3_Motion_BoosterV2.safetensors": "loras",
                "minimax_music3_dit_fp16.safetensors": "diffusion_models",
                "minimax_music3_text_encoder_pruned_int8_convrot.safetensors": "text_encoders",
                "minimax_music3_dav.safetensors": "vae",
                "qwen3vl_8b_bf16.safetensors": "text_encoders",
            }
            extras = configured["flags"]["download_personal_extras"]
            self.assertTrue(extras["default"])
            self.assertEqual(set(extras["extra_models"]), set(expected_folders))
            self.assertEqual(len(extras["extra_models"]), 8)
            registry = json.loads((root / "src/models_registry.json").read_text())
            self.assertEqual(registry["existing-model"], {"subdir": "vae"})
            self.assertEqual({n: registry[n]["subdir"] for n in expected_folders}, expected_folders)
            for filename in expected_folders:
                self.assertTrue(registry[filename]["url"].endswith("/" + filename))
            self.assertEqual(registry["qwen3vl_8b_int8_convrot.safetensors"]["url"],
                "https://huggingface.co/Comfy-Org/Qwen3-VL/resolve/main/text_encoders/qwen3vl_8b_int8_convrot.safetensors")

    def test_download_failure_does_not_replace_the_installed_package(self):
        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder) / "ComfyUI-PromptHelper"
            destination.mkdir()
            existing = destination / "__init__.py"
            existing.write_bytes(b"# existing installed package\n")
            def fail(url, timeout):
                if url.endswith("extension.js"):
                    raise OSError("simulated download failure")
                return self.download(url, timeout)
            with patch("urllib.request.urlopen", side_effect=fail), patch("time.sleep"):
                with self.assertRaisesRegex(OSError, "simulated download failure"):
                    exec(self.hook_code(Path(folder)), {})
            self.assertEqual(existing.read_bytes(), b"# existing installed package\n")
            self.assertFalse((destination / "web").exists())

    def test_retries_connection_and_interrupted_read_for_each_download_stage(self):
        original_download = self.download
        for target in (HELPER_BASE + "web/extension.js",
                       PUBLIC_BASE + "runpod-node-snapshots.json",
                       PUBLIC_BASE + "custom_nodes/openrouter_node/node.py"):
            with self.subTest(url=target), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                self.prepare_template(root)
                attempts = []
                class InterruptedResponse(io.BytesIO):
                    def read(self):
                        raise IncompleteRead(b"partial", 100)
                def flaky(url, timeout):
                    if url == target:
                        attempts.append(url)
                        if len(attempts) == 1:
                            raise URLError("simulated connection failure")
                        if len(attempts) == 2:
                            return InterruptedResponse()
                    return original_download(url, timeout)
                with patch.object(self, "download", side_effect=flaky):
                    self.execute(root)
                self.assertEqual(len(attempts), 3)
                self.assertEqual([c.args for c in self.sleep.call_args_list], [(5,), (10,)])
                self.assertIn("download_personal_extras",
                              json.loads((root / "template.json").read_text())["flags"])

    def test_stops_after_five_failed_attempts_and_preserves_installed_snapshot(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            original = self.prepare_template(root)
            existing = root / "custom_nodes/openrouter_node/node.py"
            existing.parent.mkdir(parents=True)
            existing.write_bytes(b"# installed version\n")
            original_download = self.download
            attempts = []
            def unavailable(url, timeout):
                if url.endswith("openrouter_node/node.py"):
                    attempts.append(url)
                    raise HTTPError(url, 503, "Service Unavailable", {}, None)
                return original_download(url, timeout)
            with patch.object(self, "download", side_effect=unavailable):
                with self.assertRaises(HTTPError):
                    self.execute(root)
            self.assertEqual(len(attempts), 5)
            self.assertEqual([c.args for c in self.sleep.call_args_list],
                             [(5,), (10,), (15,), (20,)])
            self.pip.assert_not_called()
            self.assertEqual(existing.read_bytes(), b"# installed version\n")
            self.assertEqual(json.loads((root / "template.json").read_text()), original)

    def test_does_not_retry_permanent_http_errors(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.prepare_template(root)
            original_download = self.download
            attempts = []
            def missing(url, timeout):
                if url.endswith("runpod-node-snapshots.json"):
                    attempts.append(url)
                    raise HTTPError(url, 404, "Not Found", {}, None)
                return original_download(url, timeout)
            with patch.object(self, "download", side_effect=missing):
                with self.assertRaises(HTTPError):
                    self.execute(root)
            self.assertEqual(len(attempts), 1)
            self.sleep.assert_not_called()
            self.pip.assert_not_called()

    def test_snapshot_checksum_failure_does_not_overwrite_nodes_or_run_pip(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.prepare_template(root)
            existing = root / "custom_nodes/openrouter_node/node.py"
            existing.parent.mkdir(parents=True)
            existing.write_bytes(b"# installed version\n")
            self.downloads[PUBLIC_BASE + "custom_nodes/openrouter_node/node.py"] = b"# corrupted\n"
            with self.assertRaisesRegex(RuntimeError, "SHA256 mismatch: openrouter_node/node.py"):
                self.execute(root)
            self.pip.assert_not_called()
            self.assertEqual(existing.read_bytes(), b"# installed version\n")
            self.assertFalse((existing.parent / "__init__.py").exists())

    def test_manifest_change_is_rejected_before_installing_snapshots(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.prepare_template(root)
            self.downloads[PUBLIC_BASE + "runpod-node-snapshots.json"] = b"{}"
            with self.assertRaisesRegex(RuntimeError, "manifest SHA256 mismatch"):
                self.execute(root)
            self.assertFalse((root / "custom_nodes/openrouter_node").exists())

    def test_restart_reuses_verified_files_and_preserves_user_configuration(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.prepare_template(root)
            self.execute(root)
            node_dir = root / "custom_nodes/openrouter_node"
            config = node_dir / "openrouter_api_key.json"
            config.write_bytes(b'{"api_key": "test-placeholder"}')
            chats = node_dir / "chats"
            chats.mkdir()
            (chats / "existing.json").write_bytes(b"{}")
            self.urls.clear()
            self.execute(root)
            self.assertEqual(self.urls, [HELPER_BASE + n for n in FILES] +
                             [PUBLIC_BASE + "runpod-node-snapshots.json"])
            self.assertEqual(config.read_bytes(), b'{"api_key": "test-placeholder"}')
            self.assertTrue((chats / "existing.json").is_file())

    def test_pip_failure_is_reported_and_does_not_claim_success(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            original = self.prepare_template(root)
            output = io.StringIO()
            with patch("urllib.request.urlopen", side_effect=self.download), \
                 patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "pip")), \
                 patch.dict(os.environ, {"TEMPLATE_DIR": str(root)}, clear=True), \
                 redirect_stdout(output):
                with self.assertRaises(subprocess.CalledProcessError):
                    exec(self.hook_code(root / "custom_nodes"), {})
            self.assertNotIn("Installed snapshot openrouter_node", output.getvalue())
            self.assertEqual(json.loads((root / "template.json").read_text()), original)


if __name__ == "__main__":
    unittest.main()
