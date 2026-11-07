"""Execute the bootstrap in Bash against an isolated image/runtime fixture."""
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


BASE = Path(__file__).parent
BASH = shutil.which("bash")
if os.name == "nt":
    git_bash = Path("C:/Program Files/Git/bin/bash.exe")
    BASH = str(git_bash) if git_bash.is_file() else None


@unittest.skipUnless(BASH, "Bash is required for bootstrap integration tests")
class StartupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix=".runpod-start-test-", dir=BASE)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.workspace = self.root / "workspace"
        self.comfy = self.root / "ComfyUI"
        self.template = self.root / "comfyui-minimax"
        self.runtime = self.root / "comfyui-runtime"
        self.entrypoint = self.root / "start_script.sh"
        self.trace = self.root / "trace"
        self.bin = self.root / "bin"
        self.bin.mkdir()
        (self.root / "tmp").mkdir()
        (self.runtime / "src").mkdir(parents=True)
        self.hook = self.root / "hook.sh"
        self.hook.write_text(
            '#!/usr/bin/env bash\nset -eu\n'
            'test -f "$TEMPLATE_DIR/synced"\n'
            'printf "extras\\n" >> "$TEST_TRACE"\n'
            'exit "${TEST_HOOK_STATUS:-0}"\n', encoding="utf-8")
        # Network is replaced at the executable boundary; Bash still executes
        # the real bootstrap, temp entrypoint, hook and simulated runtime.
        self.write_executable("curl", '''#!/usr/bin/env bash
if [ "${TEST_DOWNLOAD_FAIL:-0}" = 1 ]; then exit 22; fi
while [ "$#" -gt 0 ]; do
    if [ "$1" = -o ]; then cp "$TEST_HOOK" "$2"; exit; fi
    shift
done
exit 2
''')
        self.write_executable("python3", '#!/usr/bin/env bash\nexec "'
                              + Path(sys.executable).as_posix() + '" "$@"\n')
        self.original = (
            '#!/usr/bin/env bash\nset -e\n'
            f'mkdir -p "{self.template.as_posix()}"\n'
            f'touch "{self.template.as_posix()}/synced"\n'
            'printf "sync-template\\nsync-runtime\\n" >> "$TEST_TRACE"\n'
            f'exec bash {self.runtime.as_posix()}/src/start.sh {self.template.as_posix()}\n'
        )
        self.entrypoint.write_text(self.original, encoding="utf-8")
        (self.runtime / "src/start.sh").write_text(f'''#!/usr/bin/env bash
export TEMPLATE_DIR="$1"
if [ -f "{self.workspace.as_posix()}/additional_params.sh" ]; then
    bash "{self.workspace.as_posix()}/additional_params.sh"
fi
if [ -d "{self.workspace.as_posix()}" ]; then
    output="{self.workspace.as_posix()}/ComfyUI/output"
else
    output="{self.comfy.as_posix()}/output"
fi
mkdir -p "$output"
printf 'runtime:%s\\n' "$output" >> "$TEST_TRACE"
''', encoding="utf-8")
        source = (BASE / "runpod-start.sh").read_text(encoding="utf-8")
        for original, target in (
            ("/tmp/personal-extras", self.root / "tmp/personal-extras"),
            ("/start_script.sh", self.entrypoint),
            ("/comfyui-runtime", self.runtime),
            ("/comfyui-minimax", self.template),
            ("/workspace", self.workspace),
        ):
            # /start_script.sh also occurs after $stage_dir: only replace the
            # absolute entrypoint argument, not that temp filename suffix.
            if original == "/start_script.sh":
                source = source.replace("bash /start_script.sh", f"bash {target.as_posix()}")
                source = source.replace("python3 - /start_script.sh", f"python3 - {target.as_posix()}")
            else:
                source = source.replace(original, target.as_posix())
        self.bootstrap = self.root / "bootstrap.sh"
        self.bootstrap.write_text(source, encoding="utf-8")
        bin_path = self.bin.as_posix()
        if os.name == "nt":
            bin_path = "/" + bin_path[0].lower() + bin_path[2:]
        self.env = dict(os.environ, TEST_TRACE=self.trace.as_posix(),
                        TEST_HOOK=self.hook.as_posix(),
                        TEST_BIN=bin_path)

    def write_executable(self, name, content):
        path = self.bin / name
        path.write_text(content, encoding="utf-8")
        path.chmod(0o755)

    def run_bootstrap(self, **env):
        return self.run_command('exec bash "$1"', self.bootstrap.as_posix(), **env)

    def run_command(self, command, *args, **env):
        # Git Bash prepends its own tools to the inherited Windows PATH.
        # Prepend the fixture tools inside Bash to prevent real network access.
        return subprocess.run([BASH, "-c", 'export PATH="$TEST_BIN:$PATH"; ' + command,
                               "bootstrap-test", *args],
                              env=dict(self.env, **env),
                              capture_output=True, text=True, timeout=30)

    def test_empty_hook_stops_before_replacing_or_executing_anything(self):
        self.hook.write_bytes(b"")
        for volume in (False, True):
            with self.subTest(volume=volume):
                if volume:
                    self.workspace.mkdir()
                    (self.workspace / "additional_params.sh").write_bytes(b"old hook")
                result = self.run_bootstrap()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("empty", result.stderr)
                self.assertFalse(self.trace.exists())
                self.assertEqual(self.workspace.exists(), volume)
                if volume:
                    self.assertEqual((self.workspace / "additional_params.sh").read_bytes(),
                                     b"old hook")

    def test_invalid_shell_hook_stops_before_replacing_or_executing_anything(self):
        self.hook.write_text("if then\n", encoding="utf-8")
        self.workspace.mkdir()
        installed = self.workspace / "additional_params.sh"
        installed.write_bytes(b"old hook")
        result = self.run_bootstrap()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.trace.exists())
        self.assertEqual(installed.read_bytes(), b"old hook")

    def test_sync_failure_never_executes_extras_or_runtime(self):
        self.entrypoint.write_text(self.original.replace('set -e\n', 'set -e\nexit 23\n'),
                                   encoding="utf-8")
        result = self.run_bootstrap()
        self.assertEqual(result.returncode, 23, result.stderr)
        self.assertFalse(self.trace.exists())
        self.assertFalse(self.workspace.exists())

    def test_missing_entrypoint_does_not_create_workspace(self):
        self.entrypoint.unlink()
        result = self.run_bootstrap()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.trace.exists())
        self.assertFalse(self.workspace.exists())

    def test_actual_upstream_entrypoint_and_volume_selection(self):
        # Upstream source retrieved on 2026-11-07; only absolute filesystem
        # roots are relocated into this fixture. git is replaced so no repo is
        # fetched/reset and the author's complete boot/sync control flow runs.
        # https://github.com/Hearmeman24/comfyui-minimax/blob/master/src/start_script.sh
        # https://github.com/Hearmeman24/comfyui-runtime/blob/stable/src/start.sh#L103-L118
        source = (BASE / "test_fixtures/hearmeman-minimax-start_script.sh").read_text(encoding="utf-8")
        source = source.replace("TEMPLATE_DIR=/comfyui-minimax",
                                "TEMPLATE_DIR=" + self.template.as_posix())
        source = source.replace("RUNTIME_DIR=/comfyui-runtime",
                                "RUNTIME_DIR=" + self.runtime.as_posix())
        source = source.replace("exec bash /comfyui-runtime/src/start.sh /comfyui-minimax",
                                f"exec bash {self.runtime.as_posix()}/src/start.sh "
                                + self.template.as_posix())
        self.entrypoint.write_text(source, encoding="utf-8")
        self.template.mkdir()
        for repository in (self.template, self.runtime):
            (repository / ".git").mkdir()
        (self.template / "pins.json").write_text('{"runtime_ref":"stable"}')
        self.write_executable("git", '''#!/usr/bin/env bash
test "$1" = -C || exit 9
if [ "$3" = reset ]; then
    if [ "$2" = "$TEST_TEMPLATE" ]; then
        touch "$2/synced"
        printf 'sync-template\\n' >> "$TEST_TRACE"
    else
        printf 'sync-runtime\\n' >> "$TEST_TRACE"
    fi
fi
''')
        self.env["TEST_TEMPLATE"] = self.template.as_posix()
        selection = (BASE / "test_fixtures/hearmeman-volume-selection.sh").read_text(encoding="utf-8")
        selection = selection.replace("/workspace", self.workspace.as_posix())
        # Relocate the no-volume '/' root; keep $NETWORK_VOLUME/ComfyUI intact.
        selection = selection.replace('NETWORK_VOLUME="/"',
                                      f'NETWORK_VOLUME="{self.root.as_posix()}"')
        selection = selection.replace('COMFYUI_DIR="/ComfyUI"',
                                      f'COMFYUI_DIR="{self.comfy.as_posix()}"')
        (self.runtime / "src/start.sh").write_text(
            '#!/usr/bin/env bash\nexport TEMPLATE_DIR="$1"\n' + selection
            + 'printf "runtime:%s/output\\n" "$PERSIST_ROOT" >> "$TEST_TRACE"\n',
            encoding="utf-8")
        for volume in (False, True):
            with self.subTest(volume=volume):
                if volume:
                    self.workspace.mkdir()
                self.trace.unlink(missing_ok=True)
                for _ in range(2):
                    result = self.run_bootstrap()
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(self.entrypoint.read_text(encoding="utf-8"), source)
                    self.assertEqual(self.workspace.exists(), volume)
                output = self.workspace / "ComfyUI/output" if volume else self.comfy / "output"
                self.assertEqual(self.trace.read_text().splitlines(),
                                 ["sync-template", "sync-runtime", "extras",
                                  f"runtime:{output.as_posix()}"] * 2)

    def http_command(self, failures=None):
        # Execute the README's actual bash -c command and real curl. Only URL
        # origins and absolute image paths are relocated into a local fixture.
        curl = "curl"
        if os.name == "nt":
            curl = "C:/Program Files/Git/mingw64/bin/curl.exe"
        else:
            curl = shutil.which("curl")
            if not curl:
                self.skipTest("curl is required for HTTP integration tests")
        self.write_executable("curl", "#!/usr/bin/env bash\nexec "
                              + shlex.quote(curl) + ' "$@"\n')
        self.requests = []
        payloads = {}
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                fixture.requests.append(self.path)
                if failures and self.path in failures and failures[self.path] > 0:
                    failures[self.path] -= 1
                    self.send_error(503)
                    return
                if self.path not in payloads:
                    self.send_error(404)
                    return
                body = payloads[self.path]
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(thread.join, 5)
        self.addCleanup(server.shutdown)
        local = f"http://127.0.0.1:{server.server_port}/"
        public = "https://raw.githubusercontent.com/jcmilou/comfy-public-stuff/main/"
        payloads["/runpod-start.sh"] = self.bootstrap.read_text().replace(public, local).encode()
        payloads["/runpod-minimax-extras.sh"] = self.hook.read_bytes()
        command = re.search(r"```bash\n(.*?)\n```", (BASE / "README.md").read_text(),
                            re.DOTALL).group(1)
        destination = self.root / "tmp/runpod-start.sh"
        command = command.replace(public, local).replace("/tmp/runpod-start.sh",
                                                         destination.as_posix())
        return command, payloads, destination

    def test_entire_start_command_over_http_and_restarts(self):
        command, payloads, downloaded = self.http_command()
        for volume in (False, True):
            with self.subTest(volume=volume):
                output = self.workspace / "ComfyUI/output" if volume else self.comfy / "output"
                output.mkdir(parents=True, exist_ok=True)
                generation = output / "existing_00042.png"
                generation.write_bytes(b"existing generation")
                self.trace.unlink(missing_ok=True)
                for _ in range(2):
                    result = self.run_command(command)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(downloaded.read_bytes(), payloads["/runpod-start.sh"])
                    self.assertEqual(self.workspace.exists(), volume)
                    self.assertEqual(generation.read_bytes(), b"existing generation")
                self.assertEqual(self.trace.read_text().splitlines(),
                                 ["sync-template", "sync-runtime", "extras",
                                  f"runtime:{output.as_posix()}"] * 2)
        self.assertEqual(self.requests, ["/runpod-start.sh", "/runpod-minimax-extras.sh"] * 4)

    def test_http_404_never_executes_a_stale_bootstrap(self):
        command, payloads, downloaded = self.http_command()
        del payloads["/runpod-start.sh"]
        downloaded.write_text(f'echo stale > "{self.trace.as_posix()}"\n')
        result = self.run_command(command)
        self.assertEqual(result.returncode, 22, result.stderr)
        self.assertFalse(self.trace.exists())
        self.assertFalse(self.workspace.exists())
        self.assertEqual(self.requests, ["/runpod-start.sh"] * 5)

    def test_http_transient_errors_retry_both_downloads_then_boot_once(self):
        failures = {"/runpod-start.sh": 1, "/runpod-minimax-extras.sh": 1}
        command, payloads, downloaded = self.http_command(failures)
        result = self.run_command(command)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.trace.read_text().splitlines(),
                         ["sync-template", "sync-runtime", "extras",
                          f"runtime:{self.comfy.as_posix()}/output"])
        self.assertEqual(self.requests, ["/runpod-start.sh"] * 2
                         + ["/runpod-minimax-extras.sh"] * 2)

    def test_both_storage_modes_and_restart_preserve_existing_generations(self):
        for volume in (False, True):
            with self.subTest(volume=volume):
                output = (self.workspace / "ComfyUI/output" if volume
                          else self.comfy / "output")
                output.mkdir(parents=True, exist_ok=True)
                generation = output / "existing_00042.png"
                generation.write_bytes(b"existing generation")
                self.trace.unlink(missing_ok=True)
                for _ in range(2):
                    result = self.run_bootstrap()
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(self.workspace.is_dir(), volume)
                    self.assertEqual(generation.read_bytes(), b"existing generation")
                    self.assertEqual(self.entrypoint.read_text(), self.original)
                self.assertEqual(self.trace.read_text().splitlines(),
                                 ["sync-template", "sync-runtime", "extras",
                                  f"runtime:{output.as_posix()}"] * 2)

    def test_download_failure_never_starts_or_creates_workspace(self):
        result = self.run_bootstrap(TEST_DOWNLOAD_FAIL="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.trace.exists())
        self.assertFalse(self.workspace.exists())

    def test_download_failure_preserves_existing_volume_hook(self):
        self.workspace.mkdir()
        installed = self.workspace / "additional_params.sh"
        installed.write_bytes(b"existing hook")
        result = self.run_bootstrap(TEST_DOWNLOAD_FAIL="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(installed.read_bytes(), b"existing hook")
        self.assertFalse(self.trace.exists())

    def test_unrecognized_entrypoint_stops_before_sync_or_install(self):
        for source in ("echo unexpected\n", self.original + "echo after-handoff\n",
                       self.original + self.original):
            with self.subTest(source=source):
                self.entrypoint.write_text(source, encoding="utf-8")
                result = self.run_bootstrap()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Unsupported", result.stderr)
                self.assertFalse(self.trace.exists())
                self.assertFalse(self.workspace.exists())

    def test_hook_failure_without_volume_stops_before_runtime(self):
        result = self.run_bootstrap(TEST_HOOK_STATUS="17")
        self.assertEqual(result.returncode, 17, result.stderr)
        self.assertEqual(self.trace.read_text().splitlines(),
                         ["sync-template", "sync-runtime", "extras"])
        self.assertFalse(self.workspace.exists())
        self.assertFalse(self.comfy.exists())

    def test_volume_retains_original_runtime_hook_failure_behavior(self):
        self.workspace.mkdir()
        result = self.run_bootstrap(TEST_HOOK_STATUS="17")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.trace.read_text().splitlines(),
                         ["sync-template", "sync-runtime", "extras",
                          f"runtime:{self.workspace.as_posix()}/ComfyUI/output"])


if __name__ == "__main__":
    unittest.main()
