"""Prepare exact-size nearest-neighbor icons from the unchanged Harold avatar.

Uses Tkinter only. Run under a desktop or xvfb-run; release builds use the
checked-in output and do not require a display or image library.
"""

import tkinter as tk
from pathlib import Path


SIZES = (16, 24, 32, 48, 64, 128, 256)


def main():
    assets = Path(__file__).resolve().parents[1] / "src" / "task_manager" / "assets"
    output = assets / "icons"
    output.mkdir(exist_ok=True)
    root = tk.Tk()
    root.withdraw()
    try:
        source = tk.PhotoImage(master=root, file=str(assets / "harold.png"))
        width, height = source.width(), source.height()
        pixels = [["#%02x%02x%02x" % source.get(x, y) for x in range(width)]
                  for y in range(height)]
        for size in SIZES:
            image = tk.PhotoImage(master=root, width=size, height=size)
            rows = ["{" + " ".join(pixels[y * height // size][x * width // size]
                                     for x in range(size)) + "}" for y in range(size)]
            image.put(" ".join(rows))
            image.write(str(output / f"genxtask-{size}.png"), format="png")
            print(f"Prepared {size} x {size} Harold icon")
    finally:
        root.destroy()


if __name__ == "__main__":
    main()
