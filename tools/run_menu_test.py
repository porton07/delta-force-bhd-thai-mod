"""Launch the isolated IME-fixed game copy with the current root resource files."""
from pathlib import Path
import os
import shutil
import subprocess

root = Path(__file__).resolve().parents[2]
run = root / 'ThaiPatch/RunMenuTest'
exe = run / 'dfbhd.exe'
if not exe.is_file():
    raise SystemExit('Missing isolated test executable. Run build_ime_test.py first.')
wrapper = run / 'wrappers/dgVoodoo/D3D8.dll'
for name in ('localres.pff', 'dplayx.dll', 'dpnhpast.dll'):
    source, target = root / name, run / name
    if not source.is_file():
        raise SystemExit('Missing runtime file: ' + name)
    if target.exists() and os.path.samefile(source, target):
        continue
    if target.exists():
        try:
            target.unlink()
        except PermissionError as exc:
            raise SystemExit(
                f'Cannot refresh RunMenuTest/{name} because it is in use. '
                'Close the running test game, then launch this script again.'
            ) from exc
    try:
        os.link(source, target)
    except OSError as exc:
        raise SystemExit(f'Cannot link the current runtime file {name}: {exc}') from exc

# Optional Direct3D 8 wrapper for this isolated test copy only. Keeping it in a
# separate drop folder prevents accidentally replacing the installed game DLL.
target = run / 'd3d8.dll'
if wrapper.is_file():
    # Windows refuses to delete a DLL while the running game has it loaded.
    # Avoid touching an already-correct wrapper; if it differs, copy over it
    # directly and give a useful message if the game still has it locked.
    if not (target.is_file() and target.read_bytes() == wrapper.read_bytes()):
        try:
            shutil.copy2(wrapper, target)
        except PermissionError as exc:
            raise SystemExit(
                'Cannot update RunMenuTest/d3d8.dll because it is in use. '
                'Close the running test game, then launch this script again.'
            ) from exc
else:
    source = root / 'd3d8.dll'
    if not source.is_file():
        raise SystemExit('Missing runtime file: d3d8.dll')
    if not (target.exists() and os.path.samefile(source, target)):
        if target.exists():
            target.unlink()
        os.link(source, target)
env = os.environ.copy()
env.pop('__COMPAT_LAYER', None)
process = subprocess.Popen([str(exe)], cwd=run, env=env)
print('Started isolated Thai menu test, PID', process.pid)
