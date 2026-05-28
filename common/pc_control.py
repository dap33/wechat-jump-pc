# -*- coding: utf-8 -*-
"""
PC 端控制模块 — Windows 截图 + 鼠标模拟 + 窗口查找
所有坐标均为屏幕物理像素（通过 SetProcessDPIAware 保证一致性）
作者：大p3

使用方法：
    # 枚举窗口
    windows = enum_visible_windows()
    for hwnd, title, left, top, right, bottom in windows:
        print(f"{title} → ({left},{top})-({right},{bottom})")

    # 截取窗口/区域
    img = capture_region(left, top, right, bottom)  # 或 capture_window(hwnd)

    # 模拟鼠标点击（在区域内）
    mouse_jump(x, y, duration_ms)
"""

import ctypes
import time
from PIL import ImageGrab

# ═══════════════════════════════════════════
# DPI 感知 — 必须在任何其他 Windows API 之前调用
# 确保 GetSystemMetrics / SetCursorPos / ImageGrab 使用同一套物理像素坐标
# ═══════════════════════════════════════════
ctypes.windll.user32.SetProcessDPIAware()
try:
    # Windows 10+ 推荐使用 PerMonitorV2
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass

# ── Windows API 结构体 ────────────────────

class RECT(ctypes.Structure):
    _fields_ = [
        ("left",   ctypes.c_long),
        ("top",    ctypes.c_long),
        ("right",  ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]

class POINT(ctypes.Structure):
    _fields_ = [
        ("x", ctypes.c_long),
        ("y", ctypes.c_long),
    ]

class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx",          ctypes.c_long),
        ("dy",          ctypes.c_long),
        ("mouseData",   ctypes.c_ulong),
        ("dwFlags",     ctypes.c_ulong),
        ("time",        ctypes.c_ulong),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]

class INPUT_STRUCT(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_ulong),
        ("mi",   MOUSEINPUT),
    ]

INPUT_MOUSE           = 0
MOUSEEVENTF_LEFTDOWN  = 0x0002
MOUSEEVENTF_LEFTUP    = 0x0004


# ── 屏幕信息 ──────────────────────────────

def get_screen_size():
    """获取屏幕物理分辨率 (宽, 高)"""
    return (
        ctypes.windll.user32.GetSystemMetrics(0),
        ctypes.windll.user32.GetSystemMetrics(1),
    )


# ── 窗口枚举 ──────────────────────────────

def enum_visible_windows():
    """枚举所有可见窗口，返回 [(hwnd, 标题, left, top, right, bottom), ...]"""
    results = []
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_long, ctypes.c_long)

    def callback(hwnd, _lparam):
        if not ctypes.windll.user32.IsWindowVisible(hwnd):
            return True
        length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value.strip()
        if not title:
            return True
        rect = RECT()
        ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
        w = rect.right - rect.left
        h = rect.bottom - rect.top
        if w >= 100 and h >= 150:  # 过滤过小的窗口
            results.append((hwnd, title, rect.left, rect.top, rect.right, rect.bottom))
        return True

    ctypes.windll.user32.EnumWindows(WNDENUMPROC(callback), 0)
    return results


def get_window_client_rect(hwnd):
    """获取窗口客户区在屏幕上的坐标 (left, top, right, bottom)"""
    crect = RECT()
    ctypes.windll.user32.GetClientRect(hwnd, ctypes.byref(crect))
    pt_tl = POINT(0, 0)
    ctypes.windll.user32.ClientToScreen(hwnd, ctypes.byref(pt_tl))
    pt_br = POINT(crect.right, crect.bottom)
    ctypes.windll.user32.ClientToScreen(hwnd, ctypes.byref(pt_br))
    return (pt_tl.x, pt_tl.y, pt_br.x, pt_br.y)


def get_window_rect(hwnd):
    """获取窗口在屏幕上的坐标 (left, top, right, bottom) — 含标题栏"""
    rect = RECT()
    ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return (rect.left, rect.top, rect.right, rect.bottom)


def set_foreground(hwnd):
    """将窗口设为前台"""
    ctypes.windll.user32.SetForegroundWindow(hwnd)
    time.sleep(0.1)


# ── 截图 ──────────────────────────────────

def capture_region(left, top, right, bottom):
    """截取指定屏幕区域 (物理像素坐标)"""
    return ImageGrab.grab(bbox=(left, top, right, bottom))


def capture_window(hwnd):
    """截取整个窗口（含标题栏）"""
    r = get_window_rect(hwnd)
    return capture_region(*r)


def capture_window_client(hwnd):
    """截取窗口客户区（不含标题栏）"""
    r = get_window_client_rect(hwnd)
    return capture_region(*r)


# ── 鼠标模拟 ──────────────────────────────

def _send_mouse_input(x, y, flags):
    """发送鼠标事件到指定屏幕坐标"""
    ctypes.windll.user32.SetCursorPos(x, y)
    time.sleep(0.02)
    inp = INPUT_STRUCT()
    inp.type = INPUT_MOUSE
    inp.mi.dwFlags = flags
    ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))


def mouse_down(x, y):
    """在屏幕坐标 (x, y) 按下左键"""
    _send_mouse_input(x, y, MOUSEEVENTF_LEFTDOWN)


def mouse_up(x, y):
    """在屏幕坐标 (x, y) 释放左键"""
    _send_mouse_input(x, y, MOUSEEVENTF_LEFTUP)


def mouse_jump(x, y, duration_ms):
    """
    模拟跳跃：在 (x,y) 按下鼠标，保持 duration_ms 毫秒后释放
    (x,y) 为屏幕物理像素坐标
    返回实际按压时长
    """
    duration_ms = max(duration_ms, 50)
    _send_mouse_input(x, y, MOUSEEVENTF_LEFTDOWN)
    time.sleep(duration_ms / 1000.0)
    _send_mouse_input(x, y, MOUSEEVENTF_LEFTUP)
    return duration_ms
