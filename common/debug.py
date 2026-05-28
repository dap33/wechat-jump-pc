# -*- coding: utf-8 -*-
"""
调试模块 — 作者：大p3
开启 DEBUG_SWITCH 时将识别结果存为本地图片，方便排查
"""
import os
import sys
import math
from PIL import ImageDraw

SCREENSHOT_BACKUP_DIR = 'screenshot_backups'


def make_debug_dir(backup_dir):
    if not os.path.isdir(backup_dir):
        os.makedirs(backup_dir, exist_ok=True)


def save_debug_screenshot(ts, im, piece_x, piece_y, board_x, board_y):
    """保存带标注的调试截图"""
    make_debug_dir(SCREENSHOT_BACKUP_DIR)
    draw = ImageDraw.Draw(im)
    draw.line([(piece_x, piece_y), (board_x, board_y)], fill=2, width=3)
    draw.line([(piece_x, 0), (piece_x, im.size[1])], fill=(255, 0, 0))
    draw.line([(0, piece_y), (im.size[0], piece_y)], fill=(255, 0, 0))
    draw.line([(board_x, 0), (board_x, im.size[1])], fill=(0, 0, 255))
    draw.line([(0, board_y), (im.size[0], board_y)], fill=(0, 0, 255))
    draw.ellipse([piece_x - 10, piece_y - 10, piece_x + 10, piece_y + 10], fill=(255, 0, 0))
    draw.ellipse([board_x - 10, board_y - 10, board_x + 10, board_y + 10], fill=(0, 0, 255))
    del draw
    im.save(os.path.join(SCREENSHOT_BACKUP_DIR, f'#{ts}.png'))


def dump_device_info():
    """显示当前系统信息"""
    import ctypes
    w = ctypes.windll.user32.GetSystemMetrics(0)
    h = ctypes.windll.user32.GetSystemMetrics(1)
    print(f"""**********
Screen: {w}x{h} (PC)
Host OS: {sys.platform}
Python: {sys.version}
**********""")
