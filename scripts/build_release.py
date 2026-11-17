"""Build a deterministic, self-contained source/install archive; publish nothing."""

import argparse
import gzip
import hashlib
import io
import runpy
import tarfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def build(output):
    version = runpy.run_path(str(ROOT / "src" / "task_manager" / "__init__.py"))["__version__"]
    files = [ROOT / "README.md", ROOT / "LICENSE", ROOT / "install.py"]
    for directory in ("src/task_manager", "systemd", "packaging", "scripts", "tests", "docs"):
        files.extend(path for path in (ROOT / directory).rglob("*")
                     if path.is_file() and "__pycache__" not in path.parts
                     and path.suffix in (".py", ".png", ".txt", ".md", ".desktop", ".service", ".timer"))
    archive_name = f"genxtask-v{version}"
    output.mkdir(parents=True, exist_ok=True)
    destination = output / f"{archive_name}.tar.gz"
    with destination.open("wb") as raw:
        with gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as archive:
                for path in sorted(files, key=lambda path: str(path.relative_to(ROOT))):
                    if path.is_symlink():
                        raise ValueError(f"Release files must not be symlinks: {path}")
                    content = path.read_bytes()
                    info = tarfile.TarInfo(f"{archive_name}/{path.relative_to(ROOT).as_posix()}")
                    info.size = len(content)
                    info.mode = 0o644
                    info.mtime = 0
                    archive.addfile(info, io.BytesIO(content))
    digest = hashlib.sha256(destination.read_bytes()).hexdigest()
    destination.with_suffix(destination.suffix + ".sha256").write_text(f"{digest}  {destination.name}\n")
    (output / "genxtask.png").write_bytes((ROOT / "packaging" / "genxtask.png").read_bytes())
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "dist")
    print(build(parser.parse_args().output_dir))
