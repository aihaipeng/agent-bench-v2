import ctypes
import os
import time
from ctypes import wintypes


class ClipboardUnavailableError(RuntimeError):
    pass


def copy_text_to_system_clipboard(text: str) -> None:
    if os.name != "nt":
        raise ClipboardUnavailableError("系统剪贴板回退当前仅支持 Windows")

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    user32 = ctypes.WinDLL("user32", use_last_error=True)

    kernel32.GlobalAlloc.argtypes = (wintypes.UINT, ctypes.c_size_t)
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalLock.argtypes = (wintypes.HGLOBAL,)
    kernel32.GlobalLock.restype = wintypes.LPVOID
    kernel32.GlobalUnlock.argtypes = (wintypes.HGLOBAL,)
    kernel32.GlobalUnlock.restype = wintypes.BOOL
    kernel32.GlobalFree.argtypes = (wintypes.HGLOBAL,)
    kernel32.GlobalFree.restype = wintypes.HGLOBAL
    user32.OpenClipboard.argtypes = (wintypes.HWND,)
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.CloseClipboard.restype = wintypes.BOOL
    user32.EmptyClipboard.restype = wintypes.BOOL
    user32.SetClipboardData.argtypes = (wintypes.UINT, wintypes.HANDLE)
    user32.SetClipboardData.restype = wintypes.HANDLE

    encoded = (text + "\0").encode("utf-16-le")
    memory = kernel32.GlobalAlloc(0x0002, len(encoded))
    if not memory:
        raise ClipboardUnavailableError("无法分配系统剪贴板内存")

    clipboard_open = False
    ownership_transferred = False
    try:
        pointer = kernel32.GlobalLock(memory)
        if not pointer:
            raise ClipboardUnavailableError("无法写入系统剪贴板内存")
        try:
            ctypes.memmove(pointer, encoded, len(encoded))
        finally:
            kernel32.GlobalUnlock(memory)

        for _ in range(10):
            if user32.OpenClipboard(None):
                clipboard_open = True
                break
            time.sleep(0.01)
        if not clipboard_open:
            raise ClipboardUnavailableError("系统剪贴板正被其他程序占用")
        if not user32.EmptyClipboard():
            raise ClipboardUnavailableError("无法清空系统剪贴板")
        if not user32.SetClipboardData(13, memory):
            raise ClipboardUnavailableError("无法设置系统剪贴板内容")
        ownership_transferred = True
    finally:
        if clipboard_open:
            user32.CloseClipboard()
        if not ownership_transferred:
            kernel32.GlobalFree(memory)
