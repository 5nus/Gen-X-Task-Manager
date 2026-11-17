import hashlib
import importlib.util
import json
import os
import shutil
import sqlite3
import struct
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime, timedelta, timezone
from pathlib import Path

from task_manager.database import Database
from task_manager.models import Task
from task_manager.repository import TaskRepository


ROOT = Path(__file__).resolve().parents[1]
SIZES = (16, 24, 32, 48, 64, 128, 256)


class InstallationEnvironment:
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="genx install ")
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)
        self.home = self.directory / "Fresh User"
        self.data = self.home / "Application Data"
        self.config = self.home / "User Config"
        self.bin = self.home / ".local" / "bin"
        self.app = self.data / "genx.tasks"
        self.environment = dict(os.environ)
        self.environment.pop("PYTHONPATH", None)
        self.environment.pop("TASK_MANAGER_DATABASE", None)
        self.environment.pop("DBUS_SESSION_BUS_ADDRESS", None)
        self.environment.update(HOME=str(self.home), XDG_DATA_HOME=str(self.data),
                                XDG_CONFIG_HOME=str(self.config),
                                XDG_RUNTIME_DIR=str(self.home / "runtime"))
        self.cwd = self.directory / "Unrelated Directory"
        self.cwd.mkdir()

    def run_command(self, *arguments):
        result = subprocess.run(arguments, env=self.environment, cwd=self.cwd,
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def install(self, source=ROOT):
        return self.run_command(sys.executable, str(source / "install.py"), "--no-systemd")



class InstallationTests(InstallationEnvironment, unittest.TestCase):
    def test_fresh_user_installation_has_all_resources_and_no_source_dependencies(self):
        self.install()
        for name in ("genxtask", "genxtask-reminder", "genxtask-uninstall"):
            self.assertTrue(os.access(self.bin / name, os.X_OK))
        self.assertTrue((self.app / "lib" / "task_manager" / "assets" / "harold.png").is_file())
        self.assertEqual((self.app / "LICENSE").read_bytes(), (ROOT / "LICENSE").read_bytes())
        self.assertEqual((self.app / "lib" / "task_manager" / "assets" / "harold.png").read_bytes(),
                         (ROOT / "src" / "task_manager" / "assets" / "harold.png").read_bytes())
        for size in SIZES:
            path = self.data / "icons" / "hicolor" / f"{size}x{size}" / "apps" / "genxtask.png"
            header = path.read_bytes()
            self.assertEqual(header[:8], b"\x89PNG\r\n\x1a\n")
            self.assertEqual(struct.unpack(">II", header[16:24]), (size, size))
        launcher = self.data / "applications" / "genxtask.desktop"
        text = launcher.read_text()
        self.assertIn("Name=genxtask\n", text)
        self.assertIn("Icon=genxtask\n", text)
        self.assertIn("Categories=Office;Utility;", text)
        self.assertIn("Terminal=false", text)
        if shutil.which("desktop-file-validate"):
            self.run_command("desktop-file-validate", str(launcher))
        self.assertIn("genxtask", self.run_command(str(self.bin / "genxtask"), "--help").stdout)
        self.assertEqual(self.run_command(str(self.bin / "genxtask"), "--version").stdout.strip(),
                         "genxtask v1.0.0")
        service = self.config / "systemd" / "user" / "gen-x-task-reminder.service"
        self.assertIn(str(self.bin / "genxtask-reminder"), service.read_text())
        self.assertNotIn(str(ROOT), service.read_text())
        self.assertNotIn("PYTHONPATH=", service.read_text())
        self.assertFalse((self.config / "autostart" / "gen-x-task-reminder.desktop").exists())

    @unittest.skipUnless(shutil.which("systemd-analyze"), "systemd validator is not installed")
    def test_installed_user_units_validate_with_space_containing_paths(self):
        self.install()
        directory = self.config / "systemd" / "user"
        result = subprocess.run(["systemd-analyze", "--user", "verify",
                                 str(directory / "gen-x-task-reminder.service"),
                                 str(directory / "gen-x-task-reminder.timer")],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_installed_reminder_uses_database_and_mock_notification_tool(self):
        self.install()
        database_path = self.data / "task-manager" / "tasks.sqlite3"
        database_path.parent.mkdir(parents=True)
        with Database(database_path) as database:
            task = TaskRepository(database).create(Task(
                title="Installed reminder", priority=1,
                remind_at=datetime.now(timezone.utc) - timedelta(minutes=1),
            ))
        tools = self.directory / "Mock Tools"
        tools.mkdir()
        record = self.directory / "notification.json"
        notifier = tools / "notify-send"
        notifier.write_text("#!/usr/bin/python3\nimport json, sys\nfrom pathlib import Path\n"
                            f"Path({str(record)!r}).write_text(json.dumps(sys.argv[1:]))\n")
        notifier.chmod(0o755)
        self.environment.update(PATH=str(tools) + os.pathsep + os.environ.get("PATH", ""),
                                DISPLAY=":test", DBUS_SESSION_BUS_ADDRESS="unix:path=/mock/bus")
        self.run_command(str(self.bin / "genxtask-reminder"))
        self.assertEqual(json.loads(record.read_text())[-2:], ["Task Reminder", task.title])
        with Database(database_path) as database:
            self.assertTrue(TaskRepository(database).get(task.id).reminder_sent)
        custom = self.directory / "Custom DB" / "tasks.sqlite3"
        custom.parent.mkdir()
        with Database(custom):
            pass
        result = self.run_command(str(self.bin / "genxtask-reminder"), "--database", str(custom))
        self.assertIn(str(custom), result.stderr)

    def test_reinstall_and_uninstall_preserve_databases_configuration_and_unknown_files(self):
        database_path = self.data / "task-manager" / "tasks.sqlite3"
        database_path.parent.mkdir(parents=True)
        with Database(database_path) as database:
            task = TaskRepository(database).create(Task(title="Keep this", priority=2))
        config = self.config / "gen-x-task-manager" / "reminder.env"
        config.parent.mkdir(parents=True)
        config.write_text(f'TASK_MANAGER_DATABASE="{database_path}"\n')
        self.install()
        unknown = self.app / "personal-notes.sqlite3"
        unknown.write_bytes(b"user file, never an installation artifact")
        self.install()
        self.assertTrue((self.app / "lib" / "task_manager" / "gui.py").exists())
        self.run_command(str(self.bin / "genxtask-uninstall"), "--no-systemd")
        with Database(database_path) as database:
            self.assertEqual(TaskRepository(database).get(task.id), task)
        self.assertIn(str(database_path), config.read_text())
        self.assertEqual(unknown.read_bytes(), b"user file, never an installation artifact")
        self.assertFalse((self.data / "applications" / "genxtask.desktop").exists())
        self.assertFalse((self.bin / "genxtask").exists())
        self.assertFalse((self.config / "systemd" / "user" / "gen-x-task-reminder.timer").exists())
        self.run_command(sys.executable, str(ROOT / "install.py"), "--uninstall", "--no-systemd")

    def test_uninstaller_stops_reminders_and_removes_optional_autostart(self):
        self.install()
        autostart = self.config / "autostart" / "gen-x-task-reminder.desktop"
        autostart.parent.mkdir(parents=True)
        shutil.copyfile(self.app / "integration" / autostart.name, autostart)
        specification = importlib.util.spec_from_file_location("genx_installer", ROOT / "install.py")
        installer = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(installer)
        with patch.dict(os.environ, self.environment, clear=True):
            with patch.object(installer, "run_tool", return_value=True) as tool:
                installer.uninstall()
        commands = [call.args[0] for call in tool.call_args_list]
        self.assertIn(["systemctl", "--user", "disable", "--now", "gen-x-task-reminder.timer"], commands)
        self.assertIn(["systemctl", "--user", "stop", "gen-x-task-reminder.service"], commands)
        self.assertEqual(commands[-1], ["systemctl", "--user", "daemon-reload"])
        self.assertFalse(autostart.exists())

    def test_release_is_reproducible_installable_and_download_can_be_deleted(self):
        first = self.directory / "Release One"
        second = self.directory / "Release Two"
        for destination in (first, second):
            self.run_command(sys.executable, str(ROOT / "scripts" / "build_release.py"),
                             "--output-dir", str(destination))
        archive = next(first.glob("*.tar.gz"))
        other = second / archive.name
        self.assertEqual(archive.read_bytes(), other.read_bytes())
        self.assertEqual((first / "genxtask.png").read_bytes(),
                         (ROOT / "src" / "task_manager" / "assets" / "icons" / "genxtask-256.png").read_bytes())
        self.assertIn(hashlib.sha256(archive.read_bytes()).hexdigest(),
                      archive.with_suffix(".gz.sha256").read_text())
        extracted = self.directory / "Removed Download"
        with tarfile.open(archive) as release:
            self.assertTrue(any(member.name.endswith("/LICENSE") for member in release))
            self.assertTrue(all(not member.issym() and not member.islnk() for member in release))
            self.assertFalse(any(".git/" in member.name or "__pycache__" in member.name for member in release))
            release.extractall(extracted, filter="data") if sys.version_info >= (3, 12) else release.extractall(extracted)
        source = next(extracted.iterdir())
        self.install(source)
        shutil.rmtree(extracted)
        self.assertIn("genxtask", self.run_command(str(self.bin / "genxtask"), "--help").stdout)
        self.run_command(str(self.bin / "genxtask-reminder"), "--database", str(self.directory / "missing.sqlite3"))

    def test_previous_genx_tasks_launchers_are_replaced_during_upgrade(self):
        self.install()
        manifest_path = self.app / "install-manifest.json"
        manifest = json.loads(manifest_path.read_text())
        legacy_files = []
        for name in manifest["files"]:
            legacy = name.replace("genxtask", "genx.tasks")
            if legacy != name:
                Path(name).rename(legacy)
            legacy_files.append(legacy)
        manifest["files"] = legacy_files
        manifest_path.write_text(json.dumps(manifest))
        self.assertTrue((self.bin / "genx.tasks").exists())
        self.install()
        self.assertFalse((self.bin / "genx.tasks").exists())
        self.assertFalse((self.data / "applications" / "genx.tasks.desktop").exists())
        self.assertTrue((self.bin / "genxtask").exists())
        self.assertTrue((self.data / "applications" / "genxtask.desktop").exists())

    @unittest.skipUnless(shutil.which("gio"), "GIO desktop launcher is not installed")
    def test_desktop_exec_is_resolved_by_gio_with_paths_containing_spaces(self):
        self.install()
        # The application itself is exercised separately under Xvfb. A short
        # installed entry point records what GIO actually executes and exits.
        record = self.directory / "desktop-started.json"
        entry = self.app / "lib" / "task_manager" / "__main__.py"
        entry.write_text("import json, sys\nfrom pathlib import Path\n"
                         "def main():\n"
                         f"    Path({str(record)!r}).write_text(json.dumps(sys.argv))\n"
                         "    return 0\n")
        launcher = self.data / "applications" / "genxtask.desktop"
        self.run_command("gio", "launch", str(launcher))
        import time
        deadline = time.monotonic() + 5
        while not record.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertTrue(record.exists())
        self.assertEqual(json.loads(record.read_text())[0], str(self.bin / "genxtask"))


@unittest.skipUnless(os.environ.get("DISPLAY"), "GUI tests require a display or xvfb-run")
class InstalledGuiTests(InstallationEnvironment, unittest.TestCase):
    def test_icons_match_existing_avatar_by_nearest_neighbor(self):
        import tkinter as tk
        root = tk.Tk()
        self.addCleanup(root.destroy)
        assets = ROOT / "src" / "task_manager" / "assets"
        source = tk.PhotoImage(master=root, file=str(assets / "harold.png"))
        self.assertEqual((source.width(), source.height()), (63, 63))
        for size in SIZES:
            with self.subTest(size=size):
                icon = tk.PhotoImage(master=root, file=str(assets / "icons" / f"genxtask-{size}.png"))
                self.assertEqual((icon.width(), icon.height()), (size, size))
                points = range(size) if size == 16 else (0, size // 4, size // 2, 3 * size // 4, size - 1)
                for y in points:
                    for x in points:
                        self.assertEqual(icon.get(x, y), source.get(x * 63 // size, y * 63 // size))

    def test_installed_gui_starts_from_unrelated_directory_without_pythonpath(self):
        self.install()
        self.environment["DISPLAY"] = os.environ["DISPLAY"]
        process = subprocess.Popen([str(self.bin / "genxtask")], cwd=self.cwd,
                                   env=self.environment, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True)
        try:
            import time
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    self.fail(process.communicate()[1])
                windows = subprocess.run(["xwininfo", "-root", "-tree"], env=self.environment,
                                         capture_output=True, text=True, check=True)
                lines = [line for line in windows.stdout.splitlines() if '"genxtask"' in line]
                if lines:
                    window_id = lines[0].strip().split()[0]
                    properties = subprocess.run(["xprop", "-id", window_id, "WM_CLASS", "_NET_WM_ICON"],
                                                env=self.environment, capture_output=True, text=True, check=True)
                    self.assertIn('"genxtask"', properties.stdout)
                    self.assertIn("_NET_WM_ICON", properties.stdout)
                    self.assertNotIn("not found", properties.stdout)
                    break
                time.sleep(0.05)
            else:
                self.fail("Installed GUI did not create a window")
            path = self.data / "task-manager" / "tasks.sqlite3"
            with sqlite3.connect(path) as database:
                self.assertEqual(database.execute("SELECT COUNT(*) FROM tasks").fetchone()[0], 0)
        finally:
            process.terminate()
            process.communicate(timeout=5)


if __name__ == "__main__":
    unittest.main()
