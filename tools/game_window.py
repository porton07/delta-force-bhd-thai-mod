"""Capture/control only the selected BHD game window on Windows."""
import argparse
import ctypes as C
from ctypes import wintypes as W
from pathlib import Path
import subprocess
import time
from PIL import Image, ImageGrab

ROOT = Path(__file__).resolve().parents[2]
U = C.WinDLL('user32', use_last_error=True)
G = C.WinDLL('gdi32', use_last_error=True)
U.SetProcessDPIAware()
U.GetDC.restype = W.HDC
G.CreateCompatibleDC.argtypes = [W.HDC]
G.CreateCompatibleDC.restype = W.HDC
G.CreateCompatibleBitmap.argtypes = [W.HDC, C.c_int, C.c_int]
G.CreateCompatibleBitmap.restype = W.HBITMAP
G.SelectObject.argtypes = [W.HDC, W.HANDLE]
G.SelectObject.restype = W.HANDLE
G.DeleteObject.argtypes = [W.HANDLE]
G.DeleteDC.argtypes = [W.HDC]
U.PrintWindow.argtypes = [W.HWND, W.HDC, W.UINT]
U.GetDC.argtypes = [W.HWND]
U.ReleaseDC.argtypes = [W.HWND, W.HDC]


def windows(pid=None):
    result = []
    callback = C.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
    def visit(hwnd, _):
        process = W.DWORD()
        U.GetWindowThreadProcessId(hwnd, C.byref(process))
        text = C.create_unicode_buffer(512)
        U.GetWindowTextW(hwnd, text, 512)
        if U.IsWindowVisible(hwnd) and ((pid and process.value == pid) or
                                       (not pid and 'Delta Force' in text.value)):
            rect = W.RECT()
            U.GetWindowRect(hwnd, C.byref(rect))
            result.append((hwnd, process.value, text.value,
                           (rect.left, rect.top, rect.right, rect.bottom)))
        return True
    U.EnumWindows(callback(visit), 0)
    return result


def capture(hwnd, path):
    rect = W.RECT()
    U.GetClientRect(hwnd, C.byref(rect))
    width, height = rect.right, rect.bottom
    if width < 2 or height < 2:
        raise RuntimeError('Game client has no drawable area')
    dc = U.GetDC(hwnd)
    memory = G.CreateCompatibleDC(dc)
    bitmap = G.CreateCompatibleBitmap(dc, width, height)
    old = G.SelectObject(memory, bitmap)
    try:
        ok = U.PrintWindow(hwnd, memory, 3)
        # A top-down 32-bit DIB.
        info = C.create_string_buffer(40)
        import struct
        info.raw = struct.pack('<IiiHHIIiiII', 40, width, -height, 1, 32,
                               0, width * height * 4, 0, 0, 0, 0)
        pixels = C.create_string_buffer(width * height * 4)
        G.GetDIBits.argtypes = [W.HDC, W.HBITMAP, W.UINT, W.UINT,
                               C.c_void_p, C.c_void_p, W.UINT]
        G.SelectObject(memory, old)
        got = G.GetDIBits(memory, bitmap, 0, height, pixels, info, 0)
        picture = Image.frombytes('RGB', (width, height), pixels.raw, 'raw', 'BGRX')
        if not ok or not got or max(picture.convert('L').getextrema()) < 8:
            U.SetForegroundWindow(hwnd)
            time.sleep(.3)
            point = W.POINT(0, 0)
            U.ClientToScreen(hwnd, C.byref(point))
            picture = ImageGrab.grab(bbox=(point.x, point.y, point.x + width, point.y + height))
        picture.save(path)
        print('captured', path, picture.size)
    finally:
        G.DeleteObject(bitmap)
        G.DeleteDC(memory)
        U.ReleaseDC(hwnd, dc)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('action', choices=['launch', 'list', 'capture', 'key', 'click', 'close'])
    ap.add_argument('--pid', type=int)
    ap.add_argument('--output', default='ThaiPatch/evidence/game-menu.png')
    ap.add_argument('--key', type=int, default=27)
    ap.add_argument('--x', type=int, default=0)
    ap.add_argument('--y', type=int, default=0)
    args = ap.parse_args()
    if args.action == 'launch':
        p = subprocess.Popen([str(ROOT / 'dfbhd.exe')], cwd=ROOT)
        (ROOT / 'ThaiPatch/evidence/game-pid.txt').write_text(str(p.pid))
        print('launched', p.pid)
        return
    targets = windows(args.pid)
    print(targets)
    if args.action == 'list':
        return
    if not targets:
        raise RuntimeError('No matching visible BHD window')
    hwnd = max(targets, key=lambda v: (v[3][2]-v[3][0])*(v[3][3]-v[3][1]))[0]
    if args.action == 'capture':
        capture(hwnd, str(ROOT / args.output))
    elif args.action == 'key':
        U.SetForegroundWindow(hwnd)
        U.PostMessageW(hwnd, 0x100, args.key, 0)
        U.PostMessageW(hwnd, 0x101, args.key, 0)
    elif args.action == 'click':
        U.SetForegroundWindow(hwnd)
        point = W.POINT(args.x, args.y)
        U.ClientToScreen(hwnd, C.byref(point))
        U.SetCursorPos(point.x, point.y)
        U.mouse_event(2, 0, 0, 0, 0)
        U.mouse_event(4, 0, 0, 0, 0)
    elif args.action == 'close':
        U.PostMessageW(hwnd, 0x10, 0, 0)


if __name__ == '__main__':
    main()
