from __future__ import annotations

import ctypes
from ctypes import wintypes

from PIL import Image


class BitmapInfoHeader(ctypes.Structure):
    _fields_ = [
        ("size", wintypes.DWORD), ("width", wintypes.LONG), ("height", wintypes.LONG),
        ("planes", wintypes.WORD), ("bits", wintypes.WORD),
        ("compression", wintypes.DWORD), ("image_size", wintypes.DWORD),
        ("x_resolution", wintypes.LONG), ("y_resolution", wintypes.LONG),
        ("colors_used", wintypes.DWORD), ("colors_important", wintypes.DWORD),
    ]


class BitmapInfo(ctypes.Structure):
    _fields_ = [("header", BitmapInfoHeader), ("colors", wintypes.DWORD * 1)]


class BlendFunction(ctypes.Structure):
    _fields_ = [("operation", ctypes.c_ubyte), ("flags", ctypes.c_ubyte),
                ("alpha", ctypes.c_ubyte), ("format", ctypes.c_ubyte)]


class LayeredWindow:
    """Present premultiplied RGBA through Windows, with Tk retaining input and menus."""

    def __init__(self, root) -> None:
        self.root = root
        self.user = ctypes.WinDLL("user32", use_last_error=True)
        self.gdi = ctypes.WinDLL("gdi32", use_last_error=True)
        self.user.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
        self.user.GetAncestor.restype = wintypes.HWND
        self.user.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
        self.user.GetWindowLongPtrW.restype = ctypes.c_ssize_t
        self.user.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
        self.user.SetWindowLongPtrW.restype = ctypes.c_ssize_t
        self.user.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        self.user.GetWindowRect.restype = wintypes.BOOL
        self.user.GetDC.argtypes = [wintypes.HWND]
        self.user.GetDC.restype = wintypes.HDC
        self.user.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
        self.user.ReleaseDC.restype = ctypes.c_int
        self.user.UpdateLayeredWindow.argtypes = [
            wintypes.HWND, wintypes.HDC, ctypes.POINTER(wintypes.POINT),
            ctypes.POINTER(wintypes.SIZE), wintypes.HDC, ctypes.POINTER(wintypes.POINT),
            wintypes.DWORD, ctypes.POINTER(BlendFunction), wintypes.DWORD,
        ]
        self.user.UpdateLayeredWindow.restype = wintypes.BOOL
        self.gdi.CreateCompatibleDC.argtypes = [wintypes.HDC]
        self.gdi.CreateCompatibleDC.restype = wintypes.HDC
        self.gdi.CreateDIBSection.argtypes = [
            wintypes.HDC, ctypes.POINTER(BitmapInfo), wintypes.UINT,
            ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD,
        ]
        self.gdi.CreateDIBSection.restype = wintypes.HBITMAP
        self.gdi.SelectObject.argtypes = [wintypes.HDC, wintypes.HANDLE]
        self.gdi.SelectObject.restype = wintypes.HANDLE
        self.gdi.DeleteObject.argtypes = [wintypes.HANDLE]
        self.gdi.DeleteObject.restype = wintypes.BOOL
        self.gdi.DeleteDC.argtypes = [wintypes.HDC]
        self.gdi.DeleteDC.restype = wintypes.BOOL
        root.update_idletasks()
        self.hwnd = self.user.GetAncestor(root.winfo_id(), 2)
        style = self.user.GetWindowLongPtrW(self.hwnd, -20)
        self.user.SetWindowLongPtrW(self.hwnd, -20, style | 0x00080000)

    def present(self, frame: Image.Image) -> None:
        width, height = frame.size
        # UpdateLayeredWindow expects premultiplied BGRA, unlike Pillow's straight RGBA.
        pixels = bytearray(frame.tobytes("raw", "BGRA"))
        for index in range(0, len(pixels), 4):
            alpha = pixels[index + 3]
            if alpha < 255:
                for channel in range(3):
                    pixels[index + channel] = (pixels[index + channel] * alpha + 127) // 255
        info = BitmapInfo()
        info.header = BitmapInfoHeader(
            ctypes.sizeof(BitmapInfoHeader), width, -height, 1, 32, 0, 0, 0, 0, 0, 0
        )
        screen_dc = self.user.GetDC(None)
        memory_dc = self.gdi.CreateCompatibleDC(screen_dc)
        bitmap = None
        previous = None
        try:
            address = ctypes.c_void_p()
            bitmap = self.gdi.CreateDIBSection(memory_dc, ctypes.byref(info), 0,
                                              ctypes.byref(address), None, 0)
            if not bitmap:
                raise ctypes.WinError(ctypes.get_last_error())
            ctypes.memmove(address, bytes(pixels), len(pixels))
            previous = self.gdi.SelectObject(memory_dc, bitmap)
            rect = wintypes.RECT()
            if not self.user.GetWindowRect(self.hwnd, ctypes.byref(rect)):
                raise ctypes.WinError(ctypes.get_last_error())
            destination = wintypes.POINT(rect.left, rect.top)
            source = wintypes.POINT(0, 0)
            size = wintypes.SIZE(width, height)
            blend = BlendFunction(0, 0, 255, 1)
            if not self.user.UpdateLayeredWindow(
                self.hwnd, screen_dc, ctypes.byref(destination), ctypes.byref(size),
                memory_dc, ctypes.byref(source), 0, ctypes.byref(blend), 2,
            ):
                raise ctypes.WinError(ctypes.get_last_error())
        finally:
            if previous:
                self.gdi.SelectObject(memory_dc, previous)
            if bitmap:
                self.gdi.DeleteObject(bitmap)
            if memory_dc:
                self.gdi.DeleteDC(memory_dc)
            if screen_dc:
                self.user.ReleaseDC(None, screen_dc)
