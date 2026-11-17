#!/usr/bin/python3
"""Install or uninstall genxtask for the current Linux user, without pip."""

import argparse
import json
import os
import runpy
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SIZES = (16, 24, 32, 48, 64, 128, 256)
MANIFEST = "install-manifest.json"


def desktop_argument(value):
    """Desktop Entry string escaping followed by Exec argument escaping."""
    value = str(value).replace("%", "%%")
    quoted = '"' + "".join("\\" + char if char in '"`$\\' else char for char in value) + '"'
    return quoted.replace("\\", "\\\\")


def unit_argument(value):
    value = str(value).replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%")
    return '"' + value + '"'


def run_tool(arguments):
    try:
        result = subprocess.run(arguments, capture_output=True, text=True, timeout=15)
        if result.returncode == 0:
            return True
    except (OSError, subprocess.TimeoutExpired):
        pass
    print(f"Could not run {arguments[0]} successfully; check desktop integration manually.", file=sys.stderr)
    return False


def refresh_caches(data_home):
    if shutil.which("update-desktop-database"):
        run_tool(["update-desktop-database", str(data_home / "applications")])
    if shutil.which("gtk-update-icon-cache"):
        run_tool(["gtk-update-icon-cache", "--force", "--ignore-theme-index",
                  str(data_home / "icons" / "hicolor")])


def layout():
    home = Path.home().resolve()
    data = Path(os.environ.get("XDG_DATA_HOME") or home / ".local" / "share").expanduser().resolve()
    config = Path(os.environ.get("XDG_CONFIG_HOME") or home / ".config").expanduser().resolve()
    for path in (home, data, config):
        if "\n" in str(path) or "\r" in str(path):
            raise ValueError("Installation paths must not contain newlines")
    return home / ".local" / "bin", data, config


def install(no_systemd=False):
    if sys.version_info < (3, 9):
        raise ValueError("Python 3.9 or newer is required")
    import tkinter  # Verify the required standard-library module without opening a window.

    source = ROOT / "src" / "task_manager"
    version = runpy.run_path(str(source / "__init__.py"))["__version__"]
    for size in SIZES:
        if not (source / "assets" / "icons" / f"genxtask-{size}.png").is_file():
            raise ValueError("App icons are missing; generate them before building the release")
    bin_dir, data, config = layout()
    app = data / "genx.tasks"
    if app.is_symlink():
        raise ValueError("The installation directory must not be a symlink")
    old = json.loads((app / MANIFEST).read_text()) if (app / MANIFEST).exists() else None
    files = []

    def write(path, content, executable=False):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        path.chmod(0o755 if executable else 0o644)
        files.append(str(path))

    def copy(origin, destination):
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(origin, destination)
        destination.chmod(0o644)
        files.append(str(destination))

    library = app / "lib"
    for path in sorted(source.rglob("*")):
        if (not path.is_file() or "__pycache__" in path.parts or
                path.suffix not in (".py", ".png", ".txt")):
            continue
        if path.is_symlink():
            raise ValueError(f"Package files must not be symlinks: {path}")
        copy(path, library / "task_manager" / path.relative_to(source))

    prelude = ("#!/usr/bin/python3\n# Installed by genxtask\n"
               "import os\nimport sys\n"
               f"os.environ['XDG_DATA_HOME'] = {str(data)!r}\n"
               f"sys.path.insert(0, {str(library)!r})\n")
    write(bin_dir / "genxtask", prelude +
          "from task_manager.__main__ import main\nraise SystemExit(main())\n", True)
    write(bin_dir / "genxtask-reminder", prelude +
          "from task_manager.reminder import main\nraise SystemExit(main())\n", True)
    copy(ROOT / "install.py", app / "uninstall.py")
    copy(ROOT / "README.md", app / "README.md")
    copy(ROOT / "LICENSE", app / "LICENSE")
    write(bin_dir / "genxtask-uninstall", "#!/usr/bin/python3\n# Installed by genxtask\n"
          "import runpy\nimport sys\n"
          f"sys.argv = [{str(app / 'uninstall.py')!r}, '--uninstall', *sys.argv[1:]]\n"
          f"runpy.run_path({str(app / 'uninstall.py')!r}, run_name='__main__')\n", True)

    launcher = (ROOT / "packaging" / "genxtask.desktop").read_text()
    launcher = launcher.replace("Exec=genxtask\n",
                                "Exec=/usr/bin/python3 " + desktop_argument(bin_dir / "genxtask") + "\n")
    write(data / "applications" / "genxtask.desktop", launcher)
    for size in SIZES:
        copy(source / "assets" / "icons" / f"genxtask-{size}.png",
             data / "icons" / "hicolor" / f"{size}x{size}" / "apps" / "genxtask.png")

    unit_dir = config / "systemd" / "user"
    service = (ROOT / "systemd" / "gen-x-task-reminder.service").read_text()
    service = "\n".join(
        "ExecStart=/usr/bin/python3 " + unit_argument(bin_dir / "genxtask-reminder").replace("$", "$$")
        if line.startswith("ExecStart=") else
        "EnvironmentFile=-" + unit_argument(config / "gen-x-task-manager" / "reminder.env")
        if line.startswith("EnvironmentFile=") else line
        for line in service.splitlines()
    ) + "\n"
    write(unit_dir / "gen-x-task-reminder.service", service)
    copy(ROOT / "systemd" / "gen-x-task-reminder.timer", unit_dir / "gen-x-task-reminder.timer")
    copy(ROOT / "systemd" / "gen-x-task-reminder.desktop", app / "integration" / "gen-x-task-reminder.desktop")
    # Remove only obsolete files from a previous installation, never user data.
    if old:
        for name in set(old["files"]) - set(files):
            Path(name).unlink(missing_ok=True)
    write(app / MANIFEST, json.dumps({"application": "genx.tasks", "version": version,
          "data_home": str(data), "config_home": str(config), "files": files}, indent=2) + "\n")
    refresh_caches(data)
    if not no_systemd:
        run_tool(["systemctl", "--user", "daemon-reload"])
    print(f"Installed genxtask v{version}: {app}")
    print(f"Start from your application menu or run: {bin_dir / 'genxtask'}")
    print(f"Uninstall: {bin_dir / 'genxtask-uninstall'}")
    print("Reminder units installed; not enabled automatically. See README for session setup.")
    if not shutil.which("notify-send"):
        print("Reminders also need notify-send (libnotify-bin on Debian/Ubuntu).")


def uninstall(no_systemd=False):
    _, data, config = layout()
    app = ROOT if (ROOT / MANIFEST).is_file() else data / "genx.tasks"
    manifest = app / MANIFEST
    if not manifest.is_file():
        print("genxtask is not installed in this user directory.")
        return
    if app.is_symlink():
        raise ValueError("The installation directory must not be a symlink")
    installed = json.loads(manifest.read_text())
    if installed.get("application") != "genx.tasks":
        raise ValueError("Invalid installation manifest")
    data, config = Path(installed["data_home"]), Path(installed["config_home"])
    if not no_systemd:
        run_tool(["systemctl", "--user", "disable", "--now", "gen-x-task-reminder.timer"])
        run_tool(["systemctl", "--user", "stop", "gen-x-task-reminder.service"])
    (config / "autostart" / "gen-x-task-reminder.desktop").unlink(missing_ok=True)
    for name in installed["files"]:
        Path(name).unlink(missing_ok=True)
    manifest.unlink(missing_ok=True)
    # Python creates these files at runtime; leave unknown files, including any
    # SQLite databases a user deliberately placed here, untouched.
    for path in app.rglob("*.pyc"):
        if "__pycache__" in path.parts:
            path.unlink()
    directories = [path for path in app.rglob("*") if path.is_dir() and not path.is_symlink()]
    for path in sorted(directories, key=lambda path: len(path.parts), reverse=True) + [app]:
        try:
            path.rmdir()
        except OSError:
            pass
    refresh_caches(data)
    if not no_systemd:
        run_tool(["systemctl", "--user", "daemon-reload"])
    print("genxtask uninstalled. Task databases and reminder configuration were preserved.")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Install genxtask for the current Linux user")
    parser.add_argument("--uninstall", action="store_true")
    parser.add_argument("--no-systemd", action="store_true", help="Do not contact systemd (offline staging/tests)")
    args = parser.parse_args(argv)
    try:
        if args.uninstall:
            uninstall(args.no_systemd)
        else:
            install(args.no_systemd)
    except (OSError, ValueError, ImportError) as error:
        print(f"Installation error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
