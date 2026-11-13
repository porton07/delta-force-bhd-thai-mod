"""Create and launch a side-by-side full-game Thai test copy.

The installed game and existing RunMenuTest process are never changed. Files
that are identical are hard-linked; the three patched PFF archives, runtime
proxy, and glyph map are independent files in FullGameTest.
"""
import hashlib
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / "ThaiPatch"
SOURCE = PATCH / "RunMenuTest"
BUILD = PATCH / "build-full-thai"
RUN = PATCH / "FullGameTest"
ARCHIVES = ("localres.pff", "EXP1.pff", "resource.pff")


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def safe_link(src, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        return
    # Keep test saves and game settings isolated from the existing test copy.
    if src.suffix.lower() in {".sav", ".cfg", ".ini"}:
        shutil.copy2(src, dst)
        return
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def prepare():
    running = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq dfbhd.exe", "/FO", "CSV", "/NH"],
        capture_output=True, text=True, check=False,
    )
    if "dfbhd.exe" in running.stdout.casefold():
        raise SystemExit("Close every running Delta Force window before starting the full Thai test.")
    if not (BUILD / "manifest.json").is_file() or not (BUILD / "d3d8.dll").is_file():
        raise SystemExit("Build the full Thai patch and runtime DLL first.")
    RUN.mkdir(exist_ok=True)
    for src in SOURCE.rglob("*"):
        if not src.is_file():
            continue
        rel = src.relative_to(SOURCE)
        if rel.name.lower() in {x.lower() for x in ARCHIVES} or (rel.parent == Path(".") and rel.name.lower() == "d3d8.dll"):
            continue
        safe_link(src, RUN / rel)
    for name in ARCHIVES:
        shutil.copy2(BUILD / name, RUN / name)
    shutil.copy2(BUILD / "d3d8.dll", RUN / "d3d8.dll")
    shutil.copy2(BUILD / "thai_glyph_map.bin", RUN / "thai_glyph_map.bin")
    for name in ARCHIVES:
        if sha(RUN / name) != sha(BUILD / name):
            raise SystemExit(f"Archive copy verification failed: {name}")
    # Do not leave diagnostics from an earlier launch that could be mistaken
    # for a failure in this run. These files live only in the isolated test copy.
    for name in ("SYSDUMP.TXT", "_iberr.txt", "thai_runtime.log"):
        stale = RUN / name
        if stale.exists():
            stale.unlink()
    return RUN / "dfbhd.exe"


if __name__ == "__main__":
    exe = prepare()
    proc = subprocess.Popen([str(exe)], cwd=RUN)
    print("Started isolated full-game Thai test, PID", proc.pid)
    print("Game files are under ThaiPatch/FullGameTest; installed archives were not replaced.")
