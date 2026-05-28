# -*- coding: utf-8 -*-
"""
游戏区域选择工具 — 作者：大p3
支持两种模式：
  1. 窗口模式 — 自动识别微信小程序窗口
  2. 手动模式 — 在截图上拖拽框选游戏画面区域
"""

import os
import sys
import json
import tkinter as tk
from PIL import Image, ImageTk

# 必须在导入 pc_control 之前，确保路径正确
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common.pc_control import (
    enum_visible_windows, capture_region,
    get_window_rect, get_window_client_rect, get_screen_size,
)


def show_preview(img, title="预览"):
    """在缩放的窗口中展示截图，返回 True=确认, False=取消"""
    orig_w, orig_h = img.size
    root = tk.Tk()
    root.title(title)
    root.attributes('-topmost', True)

    screen_w = root.winfo_screenwidth()
    screen_h = root.winfo_screenheight()
    scale = min(screen_w * 0.85 / orig_w, screen_h * 0.85 / orig_h, 1.0)
    dw, dh = int(orig_w * scale), int(orig_h * scale)

    display = img.resize((dw, dh), Image.LANCZOS)
    tk_img = ImageTk.PhotoImage(display)

    root.geometry(f'{dw}x{dh}+{(screen_w - dw)//2}+{(screen_h - dh)//2}')
    canvas = tk.Canvas(root, width=dw, height=dh)
    canvas.pack()
    canvas.create_image(0, 0, image=tk_img, anchor=tk.NW)

    result = [None]

    def on_yes():
        result[0] = True
        root.destroy()

    def on_no():
        result[0] = False
        root.destroy()

    btn_frame = tk.Frame(root)
    btn_frame.pack(pady=5)
    tk.Button(btn_frame, text='✓ 确认 — 就是这个窗口', command=on_yes,
              bg='#4CAF50', fg='white', font=('', 11, 'bold'), padx=20).pack(side=tk.LEFT, padx=10)
    tk.Button(btn_frame, text='✗ 不对，换一个', command=on_no,
              bg='#f44336', fg='white', font=('', 11), padx=20).pack(side=tk.LEFT, padx=10)
    root.bind('<Return>', lambda e: on_yes())
    root.bind('<Escape>', lambda e: on_no())
    # 点 × 关闭窗口 = 确认
    root.protocol('WM_DELETE_WINDOW', on_yes)

    root.mainloop()
    return result[0]


def manual_region_select():
    """手动全屏截图 → 缩放显示 → 拖拽框选"""
    print('正在截取全屏...')
    img = capture_region(0, 0, *get_screen_size())
    orig_w, orig_h = img.size

    root = tk.Tk()
    root.title('拖拽框选游戏画面区域')
    root.attributes('-topmost', True)

    screen_w = root.winfo_screenwidth()
    screen_h = root.winfo_screenheight()
    scale = min(screen_w * 0.9 / orig_w, screen_h * 0.9 / orig_h, 1.0)
    dw, dh = int(orig_w * scale), int(orig_h * scale)

    display = img.resize((dw, dh), Image.LANCZOS)
    tk_img = ImageTk.PhotoImage(display)

    root.geometry(f'{dw}x{dh}+{(screen_w - dw)//2}+{(screen_h - dh)//2}')
    canvas = tk.Canvas(root, width=dw, height=dh, cursor='crosshair')
    canvas.pack()
    canvas.create_image(0, 0, image=tk_img, anchor=tk.NW)

    state = {'sx': None, 'sy': None, 'rect': None, 'region': None}

    def on_press(e):
        state['sx'], state['sy'] = e.x, e.y
        if state['rect']:
            canvas.delete(state['rect'])
        state['rect'] = canvas.create_rectangle(
            e.x, e.y, e.x, e.y, outline='red', width=2)

    def on_drag(e):
        canvas.coords(state['rect'], state['sx'], state['sy'], e.x, e.y)

    def on_release(e):
        x1 = int(min(state['sx'], e.x) / scale)
        y1 = int(min(state['sy'], e.y) / scale)
        x2 = int(max(state['sx'], e.x) / scale)
        y2 = int(max(state['sy'], e.y) / scale)
        state['region'] = (x1, y1, x2, y2)
        print(f'已选择: ({x1},{y1})-({x2},{y2})  尺寸:{x2-x1}x{y2-y1}')
        root.destroy()

    canvas.bind('<ButtonPress-1>', on_press)
    canvas.bind('<B1-Motion>', on_drag)
    canvas.bind('<ButtonRelease-1>', on_release)
    root.bind('<Escape>', lambda e: root.destroy())

    print('请在窗口内拖拽框选游戏画面，按 ESC 取消')
    root.mainloop()
    return state['region']


def save_config(region):
    """保存区域配置"""
    config_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config')
    os.makedirs(config_dir, exist_ok=True)
    data = {
        'left': region[0],
        'top': region[1],
        'right': region[2],
        'bottom': region[3],
        'width': region[2] - region[0],
        'height': region[3] - region[1],
    }
    path = os.path.join(config_dir, 'pc_region.json')
    with open(path, 'w') as f:
        json.dump(data, f, indent=4)
    print(f'✅ 区域配置已保存: {path}')


def main():
    print('=' * 55)
    print('  微信跳一跳 — 游戏区域选择工具')
    print('  作者：大p3')
    print('=' * 55)

    # 列出所有窗口
    windows = enum_visible_windows()
    print(f'\n发现 {len(windows)} 个可见窗口:\n')
    for i, (hwnd, title, left, top, right, bottom) in enumerate(windows):
        w, h = right - left, bottom - top
        # 标记可能是微信小程序的窗口
        tag = ' 👈' if any(k in title for k in ['微信', '跳一跳', '小程序', 'WeChat']) else ''
        print(f'  [{i:2d}] {title[:50]:50s}  ({left},{top}) {w}x{h}{tag}')

    print(f'\n  [ M ] 手动框选（如果游戏窗口不在列表中）')
    print(f'  [ Q ] 退出')

    choice = input('\n请选择窗口编号 [M/Q]: ').strip()

    if choice.upper() == 'Q':
        return
    if choice.upper() == 'M':
        region = manual_region_select()
        if region:
            save_config(region)
        return

    try:
        idx = int(choice)
        hwnd, title, left, top, right, bottom = windows[idx]
    except (ValueError, IndexError):
        print('无效选择')
        return

    print(f'\n已选择: {title}')

    # 尝试两种截图方式：客户区 vs 整个窗口
    try:
        client_rect = get_window_client_rect(hwnd)
        img = capture_region(*client_rect)
        print(f'客户区: ({client_rect[0]},{client_rect[1]})-({client_rect[2]},{client_rect[3]}) '
              f'{img.size[0]}x{img.size[1]}')
    except Exception:
        client_rect = None

    window_rect = get_window_rect(hwnd)
    img_full = capture_region(*window_rect)
    print(f'完整窗口: ({window_rect[0]},{window_rect[1]})-({window_rect[2]},{window_rect[3]}) '
          f'{img_full.size[0]}x{img_full.size[1]}')

    # 默认使用客户区（不含标题栏），如果失败则用整个窗口
    use_rect = client_rect if client_rect else window_rect
    preview_img = img if client_rect else img_full

    # 让用户确认
    print()
    if show_preview(preview_img, f'确认窗口: {title[:30]}'):
        save_config(use_rect)
        print('✅ 设置完成！现在可以运行 wechat_jump_auto_pc.py')
    else:
        print('已取消，请重新运行选择其他窗口')


if __name__ == '__main__':
    main()
