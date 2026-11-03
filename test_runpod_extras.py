"""Check the RunPod hook offline, without installing packages or fetching URLs."""
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

BASE = Path(__file__).parent
PUBLIC_BASE = "https://raw.githubusercontent.com/jcmilou/comfy-public-stuff/main/custom_nodes/ComfyUI-PromptHelper/"
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

    def download(self, url, timeout):
        self.assertTrue(url.startswith(PUBLIC_BASE))
        self.assertEqual(timeout, 60)
        self.urls.append(url)
        return io.BytesIO(FILES[url[len(PUBLIC_BASE):]])

    def hook_code(self, destination):
        return self.code.replace('Path("/ComfyUI/custom_nodes/ComfyUI-PromptHelper")',
                                 f"Path({str(destination)!r})")

    def test_all_downloaded_files_exist_at_their_public_repository_paths(self):
        package = BASE / "custom_nodes" / "ComfyUI-PromptHelper"
        for name in FILES:
            self.assertTrue((package / name).is_file(), name)
        compile((package / "__init__.py").read_text(encoding="utf-8"), "__init__.py", "exec")

    def test_installs_python_and_both_web_files_without_template_configuration(self):
        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder) / "ComfyUI-PromptHelper"
            with patch("urllib.request.urlopen", side_effect=self.download), patch.dict(os.environ, {}, clear=True):
                with self.assertRaises(SystemExit) as result:
                    exec(self.hook_code(destination), {})
            self.assertEqual(result.exception.code, 0)
            for name, source in FILES.items():
                self.assertEqual((destination / name).read_bytes(), source)
            self.assertEqual(self.urls, [PUBLIC_BASE + name for name in FILES])

    def test_preserves_existing_models_flags_and_nodes_without_duplicate_entries(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "src").mkdir()
            original = {"flags": {"download_minimax_h3": {"folders": ["MiniMax H3"]}},
                        "custom_nodes": {"target": "image", "repos": ["existing-node"]}}
            (root / "template.json").write_text(json.dumps(original), encoding="utf-8")
            (root / "src/models_registry.json").write_text('{"existing-model": {"subdir": "vae"}}', encoding="utf-8")
            code = self.hook_code(root / "custom_nodes/ComfyUI-PromptHelper")
            code = code.replace('EXTRA_CUSTOM_NODES = [', 'EXTRA_CUSTOM_NODES = ["https://example.com/custom.git",', 1)
            code = code.replace('EXTRA_MODELS = {', 'EXTRA_MODELS = {"extra.safetensors": {"url": "https://example.com/model", "subdir": "text_encoders"},', 1)
            with patch("urllib.request.urlopen", side_effect=self.download), patch.dict(os.environ, {"TEMPLATE_DIR": str(root)}):
                exec(code, {})
                first = (root / "template.json").read_text()
                exec(code, {})
            self.assertEqual((root / "template.json").read_text(), first)
            configured = json.loads(first)
            self.assertEqual(configured["flags"]["download_minimax_h3"], original["flags"]["download_minimax_h3"])
            self.assertEqual(configured["custom_nodes"]["repos"], ["existing-node", "https://example.com/custom.git"])
            self.assertEqual(configured["flags"]["download_personal_extras"]["extra_models"], ["extra.safetensors"])
            registry = json.loads((root / "src/models_registry.json").read_text())
            self.assertEqual(registry["existing-model"], {"subdir": "vae"})
            self.assertIn("extra.safetensors", registry)

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
            with patch("urllib.request.urlopen", side_effect=fail):
                with self.assertRaisesRegex(OSError, "simulated download failure"):
                    exec(self.hook_code(destination), {})
            self.assertEqual(existing.read_bytes(), b"# existing installed package\n")
            self.assertFalse((destination / "web").exists())


if __name__ == "__main__":
    unittest.main()
