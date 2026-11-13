"""Launch the campaign-screen experiment in the isolated test directory."""
from pathlib import Path
import os
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / "ThaiPatch" / "RunMenuTest"
BUILD_DIR = ROOT / "ThaiPatch" / "build-campaign-test"
ARCHIVES = ("localres.pff", "EXP1.pff")
EXE = RUN / "dfbhd.exe"

if not all((BUILD_DIR / name).is_file() for name in ARCHIVES) or not EXE.is_file():
    raise SystemExit("Build the campaign screen test first.")

# Copy both archives only into the isolated runtime. Never replace the
# installed archives here; those are backed up and installed separately.
for name in ARCHIVES:
    source, target = BUILD_DIR / name, RUN / name
    if target.exists():
        try:
            target.unlink()
        except PermissionError as exc:
            raise SystemExit(
                f"Cannot refresh RunMenuTest/{name} because it is in use. "
                "Close the running test game, then launch this script again."
            ) from exc
    shutil.copy2(source, target)
    if os.path.samefile(target, ROOT / name):
        raise SystemExit(f"Safety check failed: test archive {name} aliases the installed archive")

env = os.environ.copy()
env.pop("__COMPAT_LAYER", None)
proc = subprocess.Popen([str(EXE)], cwd=RUN, env=env)
print("Started isolated campaign screen test, PID", proc.pid)
print("This build translates campaign names, mission titles, and six campaign summaries.")
