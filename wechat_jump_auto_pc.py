# -*- coding: utf-8 -*-

"""
=== 微信跳一跳 PC 端自动辅助 ===
在电脑端微信小程序中运行，通过截取游戏画面 + 模拟鼠标长按来自动跳跃。

作者：大p3

使用方法：
  1. 电脑微信中打开「跳一跳」小程序，进入游戏
  2. 运行本脚本，自动列出窗口 → 选择游戏窗口 → 开始跳跃
  3. 按 Ctrl+C 停止

首次使用会要求选择窗口，之后自动记住配置。
如需重新选择窗口：删除 config/pc_region.json 后重新运行。
"""

import math
import random
import sys
import time
import json
import os

from PIL import Image

if sys.version_info.major != 3:
    print('请使用Python3')
    exit(1)

# 确保能找到 common 模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common.pc_control import (
    capture_region, mouse_jump, get_screen_size,
    enum_visible_windows, get_window_client_rect, get_window_rect,
)
from common import debug

VERSION = "2.0.0"
DEBUG_SWITCH = False

# ── 配置路径 ──────────────────────────────
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
REGION_CONFIG_PATH = os.path.join(PROJECT_ROOT, 'config', 'pc_region.json')
PARAM_CONFIG_PATH = os.path.join(PROJECT_ROOT, 'pc_config.json')


def load_param_config():
    """加载游戏参数配置"""
    if os.path.exists(PARAM_CONFIG_PATH):
        with open(PARAM_CONFIG_PATH, 'r') as f:
            return json.load(f)
    return {
        "under_game_score_y": 300,
        "press_coefficient": 2.000,
        "piece_base_height_1_2": 20,
        "piece_body_width": 70,
        "head_diameter": None,
    }


def load_region_config():
    """加载游戏区域配置"""
    if os.path.exists(REGION_CONFIG_PATH):
        with open(REGION_CONFIG_PATH, 'r') as f:
            return json.load(f)
    return None


def interactive_choose_window():
    """交互式选择游戏窗口"""
    print('\n正在枚举窗口...')
    windows = enum_visible_windows()

    # 优先显示可能是微信小程序的窗口
    wechat_candidates = []
    other_candidates = []
    for w in windows:
        hwnd, title, left, top, right, bottom = w
        ww, wh = right - left, bottom - top
        is_wechat = any(k in title.lower() for k in
                        ['微信', 'wechat', '跳一跳', '小程序', 'mini'])
        entry = (hwnd, title, left, top, right, bottom, ww, wh)
        if is_wechat:
            wechat_candidates.append(entry)
        else:
            other_candidates.append(entry)

    all_candidates = wechat_candidates + other_candidates

    print(f'\n{"="*60}')
    print(f'找到以下窗口 ({len(all_candidates)} 个):')
    print(f'{"="*60}')
    for i, (hwnd, title, left, top, right, bottom, ww, wh) in enumerate(all_candidates):
        tag = ' ★ 疑似微信' if i < len(wechat_candidates) else ''
        print(f'  [{i:2d}] {title[:45]:45s} ({left},{top}) {ww}x{wh}{tag}')

    print(f'\n  [  M ] 手动全屏框选')
    print(f'  [  Q ] 退出')

    choice = input('\n请选择窗口编号: ').strip()

    if choice.upper() == 'Q':
        sys.exit(0)
    if choice.upper() == 'M':
        return manual_select_region()

    try:
        idx = int(choice)
        hwnd, title, left, top, right, bottom, ww, wh = all_candidates[idx]
    except (ValueError, IndexError):
        print('无效选择')
        sys.exit(1)

    # 优先尝试客户区（不含标题栏），失败则用整个窗口
    try:
        rect = get_window_client_rect(hwnd)
        print(f'使用窗口客户区: ({rect[0]},{rect[1]})-({rect[2]},{rect[3]}) '
              f'{rect[2]-rect[0]}x{rect[3]-rect[1]}')
    except Exception:
        rect = get_window_rect(hwnd)
        print(f'使用完整窗口: ({rect[0]},{rect[1]})-({rect[2]},{rect[3]}) '
              f'{rect[2]-rect[0]}x{rect[3]-rect[1]}')

    return {
        "left": rect[0], "top": rect[1],
        "right": rect[2], "bottom": rect[3],
        "width": rect[2] - rect[0], "height": rect[3] - rect[1],
    }


def manual_select_region():
    """手动框选 — 用 Tkinter 实现"""
    import tkinter as tk
    from PIL import ImageTk

    img = capture_region(0, 0, *get_screen_size())
    orig_w, orig_h = img.size

    root = tk.Tk()
    root.title('拖拽框选游戏画面区域 — 然后按回车确认')
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
        if e is None:
            return
        x1 = int(min(state['sx'], e.x) / scale)
        y1 = int(min(state['sy'], e.y) / scale)
        x2 = int(max(state['sx'], e.x) / scale)
        y2 = int(max(state['sy'], e.y) / scale)
        state['region'] = {
            "left": x1, "top": y1,
            "right": x2, "bottom": y2,
            "width": x2 - x1, "height": y2 - y1,
        }
        print(f'手动选择: ({x1},{y1})-({x2},{y2}) {x2-x1}x{y2-y1}')
        root.destroy()

    canvas.bind('<ButtonPress-1>', on_press)
    canvas.bind('<B1-Motion>', on_drag)
    canvas.bind('<ButtonRelease-1>', on_release)
    root.bind('<Escape>', lambda e: root.destroy())
    root.bind('<Return>', lambda e: on_release(None) if state['sx'] else None)

    print('拖拽框选游戏画面，松开鼠标即确认，ESC 取消')
    root.mainloop()
    return state['region']


def save_region_config(region):
    """保存区域配置到文件"""
    os.makedirs(os.path.dirname(REGION_CONFIG_PATH), exist_ok=True)
    with open(REGION_CONFIG_PATH, 'w') as f:
        json.dump(region, f, indent=4)
    print(f'区域配置已保存: {REGION_CONFIG_PATH}')


# ── 图像识别与跳跃逻辑 ────────────────────

def find_piece_and_board(im):
    """寻找棋子和目标块的关键坐标"""
    w, h = im.size
    points = []
    piece_y_max = 0
    board_x = 0
    board_y = 0
    scan_x_border = int(w / 8)
    scan_start_y = 0
    im_pixel = im.load()
    piece_base_height_1_2 = PARAMS['piece_base_height_1_2']
    piece_body_width = PARAMS['piece_body_width']

    # 探测扫描起始 Y 坐标
    for i in range(int(h / 3), int(h * 2 / 3), 50):
        last_pixel = im_pixel[0, i]
        for j in range(1, w):
            pixel = im_pixel[j, i]
            if pixel != last_pixel:
                scan_start_y = i - 50
                break
        if scan_start_y:
            break
    print(f'扫描起始 Y: {scan_start_y}')

    # 扫描棋子
    for i in range(scan_start_y, int(h * 2 / 3)):
        for j in range(scan_x_border, w - scan_x_border):
            pixel = im_pixel[j, i]
            if (50 < pixel[0] < 60) \
                    and (53 < pixel[1] < 63) \
                    and (95 < pixel[2] < 110):
                points.append((j, i))
                piece_y_max = max(i, piece_y_max)

    bottom_x = [x for x, y in points if y == piece_y_max]
    if not bottom_x:
        return 0, 0, 0, 0, 0

    piece_x = int(sum(bottom_x) / len(bottom_x))
    piece_y = piece_y_max - piece_base_height_1_2

    # 扫描棋盘目标块
    if piece_x < w / 2:
        board_x_start = piece_x
        board_x_end = w
    else:
        board_x_start = 0
        board_x_end = piece_x

    for i in range(int(h / 3), int(h * 2 / 3)):
        last_pixel = im_pixel[0, i]
        if board_x or board_y:
            break
        board_x_sum = 0
        board_x_c = 0
        for j in range(int(board_x_start), int(board_x_end)):
            pixel = im_pixel[j, i]
            if abs(j - piece_x) < piece_body_width:
                continue
            ver_pixel = im_pixel[j, i + 5] if i + 5 < h else pixel
            if abs(pixel[0] - last_pixel[0]) \
                    + abs(pixel[1] - last_pixel[1]) \
                    + abs(pixel[2] - last_pixel[2]) > 10 \
                    and abs(ver_pixel[0] - last_pixel[0]) \
                    + abs(ver_pixel[1] - last_pixel[1]) \
                    + abs(ver_pixel[2] - last_pixel[2]) > 10:
                board_x_sum += j
                board_x_c += 1
        if board_x_sum:
            board_x = board_x_sum / board_x_c

    if not board_x:
        return 0, 0, 0, 0, 0

    # 通过对称中心计算目标 Y 坐标
    center_x = w / 2 + (24 / 1080) * w
    center_y = h / 2 + (17 / 1920) * h
    if piece_x > center_x:
        board_y = round((25.5 / 43.5) * (board_x - center_x) + center_y)
        delta_piece_y = piece_y - round((25.5 / 43.5) * (piece_x - center_x) + center_y)
    else:
        board_y = round(-(25.5 / 43.5) * (board_x - center_x) + center_y)
        delta_piece_y = piece_y - round(-(25.5 / 43.5) * (piece_x - center_x) + center_y)

    if not all((board_x, board_y)):
        return 0, 0, 0, 0, 0
    return piece_x, piece_y, board_x, board_y, delta_piece_y


def do_jump(distance):
    """根据距离计算按压时间并执行鼠标跳跃"""
    scale = 0.945 * 2 / HEAD_DIAMETER
    actual_distance = distance * scale * (math.sqrt(6) / 2)
    press_time = (-945 + math.sqrt(945 ** 2 + 4 * 105 *
                                   36 * actual_distance)) / (2 * 105) * 1000
    press_time *= PARAMS['press_coefficient']
    press_time = max(press_time, 200)
    press_time = int(press_time)

    # 在游戏区域内随机位置按下鼠标（防检测）
    jx = random.uniform(GAME_W * 0.3, GAME_W * 0.7)
    jy = random.uniform(GAME_H * 0.5, GAME_H * 0.8)
    sx = GAME_LEFT + int(jx)
    sy = GAME_TOP + int(jy)

    print(f'跳跃: 屏幕({sx},{sy}) 按压{press_time}ms')
    mouse_jump(sx, sy, press_time)
    return press_time


# ── 主函数 ────────────────────────────────

def main():
    global GAME_LEFT, GAME_TOP, GAME_RIGHT, GAME_BOTTOM, GAME_W, GAME_H
    global PARAMS, HEAD_DIAMETER

    print('=' * 60)
    print(f'  微信跳一跳 PC 端自动辅助 v{VERSION}')
    print(f'  作者：大p3')
    print('=' * 60)
    debug.dump_device_info()

    # 1. 加载参数配置
    PARAMS = load_param_config()

    # 2. 加载或选择游戏区域
    region = load_region_config()
    if region is None:
        print('\n未找到游戏区域配置，请选择游戏窗口…')
        region = interactive_choose_window()
        if region is None:
            print('未选择窗口，退出')
            return
        save_region_config(region)

    GAME_LEFT, GAME_TOP = region['left'], region['top']
    GAME_RIGHT, GAME_BOTTOM = region['right'], region['bottom']
    GAME_W, GAME_H = region['width'], region['height']

    print(f'\n游戏区域: ({GAME_LEFT},{GAME_TOP})-({GAME_RIGHT},{GAME_BOTTOM}) '
          f'{GAME_W}x{GAME_H}')

    # 3. head_diameter
    HEAD_DIAMETER = PARAMS.get('head_diameter')
    if HEAD_DIAMETER is None:
        HEAD_DIAMETER = GAME_W / 8
        print(f'head_diameter 未配置，按区域宽度估算: {HEAD_DIAMETER:.0f}')

    # 4. 确认开始
    print('\n请确保:')
    print('  1. 微信「跳一跳」已打开且游戏已开始')
    print('  2. 游戏窗口未被遮挡')

    input('\n准备好后按 Enter 开始…')
    print('\n开始自动跳跃！按 Ctrl+C 停止\n')

    i, next_rest, next_rest_time = (0, random.randrange(5, 15),
                                    random.randrange(5, 10))

    while True:
        # 截取游戏区域
        im = capture_region(GAME_LEFT, GAME_TOP, GAME_RIGHT, GAME_BOTTOM)

        # 识别棋子和目标
        piece_x, piece_y, board_x, board_y, delta_piece_y = find_piece_and_board(im)
        ts = int(time.time())
        print(f'[{ts}] 棋子:({piece_x},{piece_y}) 目标:({board_x},{board_y})')

        if piece_x == 0 and board_x == 0:
            print('  ⚠ 未能识别棋子或目标，可能是画面变化，继续尝试...')
            im.close()
            time.sleep(1.0)
            continue

        distance = math.sqrt((board_x - piece_x) ** 2 + (board_y - piece_y) ** 2)
        do_jump(distance)

        if DEBUG_SWITCH:
            debug.save_debug_screenshot(ts, im, piece_x, piece_y, board_x, board_y)
        im.close()

        i += 1
        if i == next_rest:
            print(f'已连续跳跃 {i} 次，休息 {next_rest_time} 秒...')
            for j in range(next_rest_time):
                sys.stdout.write(f'\r  {next_rest_time - j} 秒后继续...')
                sys.stdout.flush()
                time.sleep(1)
            print('\n继续')
            i, next_rest, next_rest_time = (0, random.randrange(30, 100),
                                            random.randrange(10, 60))

        # 等待棋子落稳
        time.sleep(random.uniform(1.2, 1.4))


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\n已退出')
