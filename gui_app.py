# -*- coding: utf-8 -*-

"""
微信跳一跳 PC 端 — 可视化界面
═══════════════════════════════════════════════════════
窗口选择 → 参数调节 → 实时预览（标注识别结果）→ 一键启停

作者：大p3
"""

import math
import random
import sys
import os
import time
import json
import queue
import threading

from PIL import Image, ImageDraw, ImageTk
import tkinter as tk
from tkinter import ttk, messagebox

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common.pc_control import (
    capture_region, mouse_jump, get_screen_size,
    enum_visible_windows, get_window_client_rect, get_window_rect,
)

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
REGION_CONFIG_PATH = os.path.join(PROJECT_ROOT, 'config', 'pc_region.json')
PARAM_CONFIG_PATH = os.path.join(PROJECT_ROOT, 'pc_config.json')

DEFAULT_PARAMS = {
    "under_game_score_y": 300,
    "press_coefficient": 2.000,
    "piece_base_height_1_2": 20,
    "piece_body_width": 70,
    "head_diameter": None,
}
PARAMS = dict(DEFAULT_PARAMS)

AUTHOR = "大p3"


# ═══════════════════════════════════════════════════════════
#  图像识别（与 CLI 版本一致）
# ═══════════════════════════════════════════════════════════

def find_piece_and_board(im):
    w, h = im.size
    px = py = bx = by = 0
    piece_y_max = 0
    points = []
    scan_x_border = int(w / 8)
    scan_start_y = 0
    im_pixel = im.load()
    pbh = PARAMS['piece_base_height_1_2']
    pbw = PARAMS['piece_body_width']

    for i in range(int(h / 3), int(h * 2 / 3), 50):
        last_pixel = im_pixel[0, i]
        for j in range(1, w):
            if im_pixel[j, i] != last_pixel:
                scan_start_y = i - 50
                break
        if scan_start_y:
            break
    if scan_start_y == 0:
        return None

    for i in range(scan_start_y, int(h * 2 / 3)):
        for j in range(scan_x_border, w - scan_x_border):
            pixel = im_pixel[j, i]
            if (50 < pixel[0] < 60) and (53 < pixel[1] < 63) and (95 < pixel[2] < 110):
                points.append((j, i))
                piece_y_max = max(i, piece_y_max)

    bottom_x = [x for x, y in points if y == piece_y_max]
    if not bottom_x:
        return None
    px = int(sum(bottom_x) / len(bottom_x))
    py = piece_y_max - pbh

    if px < w / 2:
        bs, be = px, w
    else:
        bs, be = 0, px

    for i in range(int(h / 3), int(h * 2 / 3)):
        last_pixel = im_pixel[0, i]
        if bx or by:
            break
        bsum = bc = 0
        for j in range(int(bs), int(be)):
            pixel = im_pixel[j, i]
            if abs(j - px) < pbw:
                continue
            vp = im_pixel[j, i + 5] if i + 5 < h else pixel
            if (abs(pixel[0] - last_pixel[0]) + abs(pixel[1] - last_pixel[1]) +
                abs(pixel[2] - last_pixel[2]) > 10 and
                abs(vp[0] - last_pixel[0]) + abs(vp[1] - last_pixel[1]) +
                abs(vp[2] - last_pixel[2]) > 10):
                bsum += j
                bc += 1
        if bsum:
            bx = bsum / bc

    if not bx:
        return None

    cx = w / 2 + (24 / 1080) * w
    cy = h / 2 + (17 / 1920) * h
    if px > cx:
        by = round((25.5 / 43.5) * (bx - cx) + cy)
        delta = py - round((25.5 / 43.5) * (px - cx) + cy)
    else:
        by = round(-(25.5 / 43.5) * (bx - cx) + cy)
        delta = py - round(-(25.5 / 43.5) * (px - cx) + cy)

    return (px, py, bx, by, delta)


def calc_press_time(distance, head_diameter):
    scale = 0.945 * 2 / head_diameter
    actual = distance * scale * (math.sqrt(6) / 2)
    t = (-945 + math.sqrt(945 ** 2 + 4 * 105 * 36 * actual)) / (2 * 105) * 1000
    t *= PARAMS['press_coefficient']
    return max(int(t), 200)


def draw_debug_overlay(im, piece_x, piece_y, board_x, board_y):
    draw = ImageDraw.Draw(im)
    draw.line([(piece_x, 0), (piece_x, im.height)], fill=(255, 80, 80), width=2)
    draw.line([(0, piece_y), (im.width, piece_y)], fill=(255, 80, 80), width=2)
    draw.ellipse([piece_x - 10, piece_y - 10, piece_x + 10, piece_y + 10],
                 outline=(255, 80, 80), width=2)
    bx, by = int(board_x), int(board_y)
    draw.line([(bx, 0), (bx, im.height)], fill=(80, 140, 255), width=2)
    draw.line([(0, by), (im.width, by)], fill=(80, 140, 255), width=2)
    draw.ellipse([bx - 10, by - 10, bx + 10, by + 10],
                 outline=(80, 140, 255), width=2)
    draw.line([(piece_x, piece_y), (bx, by)], fill=(0, 220, 100), width=2)
    dist = math.sqrt((bx - piece_x) ** 2 + (by - piece_y) ** 2)
    mid_x = (piece_x + bx) // 2
    mid_y = (piece_y + by) // 2
    draw.text((mid_x + 5, mid_y - 10), f'd={dist:.0f}', fill=(0, 220, 100))
    del draw
    return im


# ═══════════════════════════════════════════════════════════
#  GUI 主类
# ═══════════════════════════════════════════════════════════

class JumpGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title(f'微信跳一跳 PC 辅助 — 作者：{AUTHOR}')
        self.root.geometry('1100x720')
        self.root.minsize(900, 550)
        self.root.configure(bg='#1e1e2e')
        self.root.protocol('WM_DELETE_WINDOW', self.on_close)

        self.running = False
        self.paused = False
        self.game_thread = None
        self.update_queue = queue.Queue()
        self.jump_count = 0
        self.game_region = None
        self._window_data = {}
        self._tk_img = None
        self._preview_image_id = None
        self.style = ttk.Style()
        self.style.theme_use('clam')
        self._setup_theme()
        self._build_ui()
        self._load_config()
        self._process_updates()
        self._log(f'微信跳一跳 PC 辅助 v2.2 — 作者：{AUTHOR}')

    def _setup_theme(self):
        BG = '#1e1e2e'
        FG = '#cdd6f4'
        ACCENT = '#89b4fa'
        BTN_BG = '#313244'
        self.root.configure(bg=BG)
        self.style.configure('.', background=BG, foreground=FG, font=('Microsoft YaHei UI', 9))
        self.style.configure('TFrame', background=BG)
        self.style.configure('TLabelframe', background=BG, foreground=ACCENT)
        self.style.configure('TLabelframe.Label', background=BG, foreground=ACCENT,
                             font=('Microsoft YaHei UI', 10, 'bold'))
        self.style.configure('TLabel', background=BG, foreground=FG)
        self.style.configure('TButton', background=BTN_BG, foreground=FG,
                             font=('Microsoft YaHei UI', 9))
        self.style.map('TButton', background=[('active', '#45475a')])
        self.style.configure('Start.TButton', background='#40a02b', foreground='white',
                             font=('Microsoft YaHei UI', 11, 'bold'), padding=8)
        self.style.configure('Stop.TButton', background='#d20f39', foreground='white',
                             font=('Microsoft YaHei UI', 11, 'bold'), padding=8)
        self.style.configure('TCombobox', fieldbackground='#313244', background='#313244',
                             foreground=FG)
        self.style.configure('TSpinbox', fieldbackground='#313244', background='#313244',
                             foreground=FG)
        self.style.configure('TScale', background=BG, troughcolor='#313244')

    # ── UI 构建 ────────────────────────────

    def _build_ui(self):
        # 主布局：左右分栏
        self.pw = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        self.pw.pack(fill=tk.BOTH, expand=True, padx=6, pady=(6, 0))

        # 左侧控制面板 — 固定宽度
        left_frame = ttk.Frame(self.pw, width=330)
        self.pw.add(left_frame, weight=0)
        left_frame.pack_propagate(False)

        # 右侧：预览 + 日志（上下分栏）
        right_frame = ttk.Frame(self.pw)
        self.pw.add(right_frame, weight=1)

        self._build_left_panel(left_frame)
        self._build_right_panel(right_frame)

        # 底部作者栏
        bar = tk.Frame(self.root, bg='#313244', height=22)
        bar.pack(fill=tk.X, side=tk.BOTTOM)
        bar.pack_propagate(False)
        tk.Label(bar, text=f'作者：{AUTHOR}    v2.2', bg='#313244', fg='#585b70',
                 font=('Microsoft YaHei UI', 8)).pack(side=tk.RIGHT, padx=10, pady=1)

    def _build_left_panel(self, parent):
        inner = ttk.Frame(parent)
        inner.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        # ── 窗口选择 ──
        frm = ttk.Labelframe(inner, text='游戏窗口', padding=6)
        frm.pack(fill=tk.X, pady=(0, 8))

        combo_row = ttk.Frame(frm)
        combo_row.pack(fill=tk.X)
        self.window_combo = ttk.Combobox(combo_row, state='readonly')
        self.window_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(combo_row, text='刷新', command=self._refresh_windows,
                   width=5).pack(side=tk.LEFT, padx=(4, 0))
        self.window_combo.bind('<<ComboboxSelected>>', self._on_window_selected)

        self.win_info_label = ttk.Label(frm, text='', font=('Microsoft YaHei UI', 7))
        self.win_info_label.pack(fill=tk.X, pady=(4, 0))

        # ── 跳跃参数（仅保留两个关键参数）──
        frm2 = ttk.Labelframe(inner, text='跳跃参数', padding=6)
        frm2.pack(fill=tk.X, pady=(0, 8))

        ttk.Label(frm2, text='按压系数 — 越大跳越远:').pack(anchor=tk.W)
        cf = ttk.Frame(frm2)
        cf.pack(fill=tk.X)
        self.coef_var = tk.DoubleVar(value=PARAMS['press_coefficient'])
        self.coef_scale = ttk.Scale(cf, from_=0.5, to=5.0, variable=self.coef_var,
                                     orient=tk.HORIZONTAL)
        self.coef_scale.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.coef_label = ttk.Label(cf, text=f'{PARAMS["press_coefficient"]:.3f}', width=6,
                                     font=('Consolas', 10, 'bold'),
                                     foreground='#a6e3a1')
        self.coef_label.pack(side=tk.LEFT, padx=4)
        self.coef_var.trace_add('write', lambda *a: self._on_coef_change())

        ttk.Label(frm2, text='棋子头部直径 (影响距离校准):').pack(anchor=tk.W, pady=(8, 0))
        hd_row = ttk.Frame(frm2)
        hd_row.pack(fill=tk.X)
        self.hd_var = tk.IntVar(value=60)
        ttk.Spinbox(hd_row, from_=20, to=300, textvariable=self.hd_var,
                    width=7, command=self._on_param_change).pack(side=tk.LEFT)
        ttk.Label(hd_row, text='px (自动估算，可微调)',
                  font=('Microsoft YaHei UI', 7)).pack(side=tk.LEFT, padx=4)

        # ── 控制按钮 ──
        frm3 = ttk.Frame(inner)
        frm3.pack(fill=tk.X, pady=(0, 8))

        self.start_btn = ttk.Button(frm3, text='▶  开始跳跃', style='Start.TButton',
                                     command=self.start_game)
        self.start_btn.pack(fill=tk.X, pady=1)

        self.stop_btn = ttk.Button(frm3, text='■  停止', style='Stop.TButton',
                                    command=self.stop_game, state=tk.DISABLED)
        self.stop_btn.pack(fill=tk.X, pady=1)

        self.pause_btn = ttk.Button(frm3, text='⏸  暂停', command=self.toggle_pause,
                                     state=tk.DISABLED)
        self.pause_btn.pack(fill=tk.X, pady=1)

        # ── 跳跃计数 ──
        self.jump_count_label = ttk.Label(inner, text='跳跃: 0 次',
                                          font=('Microsoft YaHei UI', 10, 'bold'),
                                          foreground='#a6e3a1')
        self.jump_count_label.pack(anchor=tk.W, pady=(0, 8))

        # ── 保存 / 重置 — 始终在底部 ──
        btn_row = ttk.Frame(inner)
        btn_row.pack(fill=tk.X, side=tk.BOTTOM)
        ttk.Button(btn_row, text='💾 保存配置',
                   command=self._save_params).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 3))
        ttk.Button(btn_row, text='↺ 重置默认',
                   command=self._reset_to_default).pack(side=tk.LEFT, padx=(3, 0))

    def _build_right_panel(self, parent):
        # 右侧上下分栏：预览 / 日志
        self.right_pw = ttk.PanedWindow(parent, orient=tk.VERTICAL)
        self.right_pw.pack(fill=tk.BOTH, expand=True)

        # 上半：画面预览
        preview_frame = ttk.Labelframe(self.right_pw, text='游戏画面预览', padding=4)
        self.right_pw.add(preview_frame, weight=3)

        self.preview_canvas = tk.Canvas(preview_frame, bg='#11111b', highlightthickness=0)
        self.preview_canvas.pack(fill=tk.BOTH, expand=True)

        self.preview_canvas.create_text(
            400, 200, text='选择游戏窗口后\n点击"开始跳跃"',
            fill='#585b70', font=('Microsoft YaHei UI', 16), anchor=tk.CENTER,
            tags='placeholder')
        self.preview_canvas.create_text(
            400, 260, text=f'作者：{AUTHOR}',
            fill='#45475a', font=('Microsoft YaHei UI', 10), anchor=tk.CENTER,
            tags='author_tag')
        self.preview_canvas.bind('<Configure>', self._center_placeholder)

        # 下半：运行日志
        log_frame = ttk.Labelframe(self.right_pw, text='运行日志', padding=4)
        self.right_pw.add(log_frame, weight=1)

        self.log_text = tk.Text(log_frame, bg='#11111b', fg='#a6e3a1',
                                 font=('Consolas', 9), relief=tk.FLAT,
                                 padx=6, pady=4, state=tk.DISABLED, wrap=tk.WORD)
        self.log_text.pack(fill=tk.BOTH, expand=True)

    def _center_placeholder(self, event=None):
        w = self.preview_canvas.winfo_width()
        h = self.preview_canvas.winfo_height()
        if w > 10 and h > 10:
            self.preview_canvas.coords('placeholder', w // 2, h // 2 - 30)
            self.preview_canvas.coords('author_tag', w // 2, h // 2 + 30)
        if self._preview_image_id:
            self.preview_canvas.coords(self._preview_image_id, w // 2, h // 2)

    # ── 配置加载 / 保存 ──────────────────────

    def _load_config(self):
        # 1. 加载参数
        if os.path.exists(PARAM_CONFIG_PATH):
            try:
                with open(PARAM_CONFIG_PATH) as f:
                    data = json.load(f)
                PARAMS.update(data)
                self.coef_var.set(PARAMS['press_coefficient'])
            except Exception:
                pass

        # 2. 加载区域配置（先于窗口枚举，避免被覆盖）
        if os.path.exists(REGION_CONFIG_PATH):
            try:
                with open(REGION_CONFIG_PATH) as f:
                    r = json.load(f)
                self.game_region = (r['left'], r['top'], r['right'], r['bottom'])
            except Exception:
                pass

        # 3. 枚举窗口（已有区域则只展示不覆盖）
        self._refresh_windows()

    def _save_params(self):
        PARAMS['press_coefficient'] = self.coef_var.get()
        PARAMS['head_diameter'] = self.hd_var.get()
        try:
            os.makedirs(os.path.dirname(PARAM_CONFIG_PATH), exist_ok=True)
            with open(PARAM_CONFIG_PATH, 'w') as f:
                json.dump(PARAMS, f, indent=4, ensure_ascii=False)
            self._log('✅ 配置已保存')
        except Exception as e:
            self._log(f'保存失败: {e}')

    def _reset_to_default(self):
        if not messagebox.askyesno('确认重置', '将恢复所有参数为默认值，确定？'):
            return
        PARAMS.update(DEFAULT_PARAMS)
        self.coef_var.set(DEFAULT_PARAMS['press_coefficient'])
        if self.game_region:
            gw = self.game_region[2] - self.game_region[0]
            self.hd_var.set(int(gw / 8))
        else:
            self.hd_var.set(60)
        os.makedirs(os.path.dirname(PARAM_CONFIG_PATH), exist_ok=True)
        PARAMS['head_diameter'] = None
        with open(PARAM_CONFIG_PATH, 'w') as f:
            json.dump(DEFAULT_PARAMS, f, indent=4, ensure_ascii=False)
        self._log('✅ 已恢复默认配置')

    # ── 窗口选择 ──────────────────────────

    def _refresh_windows(self):
        try:
            windows = enum_visible_windows()
        except Exception as e:
            self._log(f'枚举窗口失败: {e}')
            return

        self._window_data = {}
        items = []
        wechat_first = []

        for hwnd, title, left, top, right, bottom in windows:
            w, h = right - left, bottom - top
            key = f'{title}  ({w}x{h})'
            self._window_data[key] = (hwnd, left, top, right, bottom)
            is_wx = any(k in title.lower() for k in
                        ['微信', 'wechat', '跳一跳', '小程序', 'mini'])
            if is_wx:
                wechat_first.append(key)
            else:
                items.append(key)

        display_items = wechat_first + items
        self.window_combo['values'] = display_items
        if display_items and not self.game_region:
            self.window_combo.current(0)
            self._on_window_selected()

    def _on_window_selected(self, event=None):
        key = self.window_combo.get()
        if not key or key not in self._window_data:
            return
        hwnd, left, top, right, bottom = self._window_data[key]

        try:
            cr = get_window_client_rect(hwnd)
            self.game_region = cr
            info = f'客户区: ({cr[0]},{cr[1]}) {cr[2]-cr[0]}x{cr[3]-cr[1]}'
        except Exception:
            self.game_region = (left, top, right, bottom)
            w, h = right - left, bottom - top
            info = f'窗口: ({left},{top}) {w}x{h}'

        self.win_info_label.configure(text=info)

        gw = self.game_region[2] - self.game_region[0]
        if PARAMS.get('head_diameter') is None:
            self.hd_var.set(int(gw / 8))
        else:
            self.hd_var.set(PARAMS['head_diameter'])

        # 仅用户主动切换窗口时才保存区域配置
        if event is not None:
            r = self.game_region
            os.makedirs(os.path.dirname(REGION_CONFIG_PATH), exist_ok=True)
            with open(REGION_CONFIG_PATH, 'w') as f:
                json.dump({
                    'left': r[0], 'top': r[1], 'right': r[2], 'bottom': r[3],
                    'width': r[2] - r[0], 'height': r[3] - r[1],
                }, f, indent=4)
            self._log(f'已选择: {key.split("  ")[0]} — {info}')

        self._capture_and_show()

    # ── 画面预览 ──────────────────────────

    def _capture_and_show(self):
        if not self.game_region:
            return
        try:
            img = capture_region(*self.game_region)
            self._display_image(img)
        except Exception as e:
            self.update_queue.put(('log', f'截图失败: {e}'))

    def _display_image(self, img):
        cw = self.preview_canvas.winfo_width()
        ch = self.preview_canvas.winfo_height()
        if cw < 50 or ch < 50:
            return

        iw, ih = img.size
        scale = min(cw / iw, ch / ih, 1.0)
        dw, dh = int(iw * scale), int(ih * scale)

        display = img.resize((dw, dh), Image.BILINEAR)
        self._tk_img = ImageTk.PhotoImage(display)

        self.preview_canvas.delete('placeholder')
        if self._preview_image_id:
            self.preview_canvas.delete(self._preview_image_id)
        self._preview_image_id = self.preview_canvas.create_image(
            cw // 2, ch // 2, image=self._tk_img, anchor=tk.CENTER)

    # ── 游戏控制 ──────────────────────────

    def start_game(self):
        if self.running:
            return
        if not self.game_region:
            messagebox.showwarning('提示', '请先选择游戏窗口')
            return

        PARAMS['press_coefficient'] = self.coef_var.get()
        PARAMS['head_diameter'] = self.hd_var.get()

        self.running = True
        self.paused = False
        self.jump_count = 0

        self.start_btn.configure(state=tk.DISABLED)
        self.stop_btn.configure(state=tk.NORMAL)
        self.pause_btn.configure(state=tk.NORMAL, text='⏸  暂停')

        self._log('=== 开始自动跳跃 ===')

        self.game_thread = threading.Thread(target=self._game_loop, daemon=True)
        self.game_thread.start()

    def stop_game(self):
        self.running = False
        self.paused = False
        self.start_btn.configure(state=tk.NORMAL)
        self.stop_btn.configure(state=tk.DISABLED)
        self.pause_btn.configure(state=tk.DISABLED, text='⏸  暂停')
        self._log(f'=== 停止，共跳跃 {self.jump_count} 次 ===')

    def toggle_pause(self):
        if not self.running:
            return
        self.paused = not self.paused
        if self.paused:
            self.pause_btn.configure(text='▶  继续')
            self._log('⏸ 已暂停')
        else:
            self.pause_btn.configure(text='⏸  暂停')
            self._log('▶ 继续')

    def on_close(self):
        self.running = False
        self.root.destroy()

    # ── 游戏主循环（后台线程）────────────────

    def _game_loop(self):
        region = self.game_region
        left, top, right, bottom = region
        gw = right - left
        gh = bottom - top

        rest_counter = 0
        rest_threshold = random.randrange(5, 15)
        rest_seconds = random.randrange(5, 10)

        while self.running:
            if self.paused:
                time.sleep(0.3)
                continue

            try:
                im = capture_region(left, top, right, bottom)

                result = find_piece_and_board(im)
                if result is None:
                    self.update_queue.put(('log', '⚠ 未能识别，重试…'))
                    im.close()
                    time.sleep(1.0)
                    continue

                px, py, bx, by, _delta = result
                distance = math.sqrt((bx - px) ** 2 + (by - py) ** 2)

                hd = PARAMS.get('head_diameter') or (gw / 8)
                press_time = calc_press_time(distance, hd)

                annotated = draw_debug_overlay(im.copy(), px, py, bx, by)
                self.update_queue.put(('frame', annotated))
                self.update_queue.put(('log', f'#{self.jump_count + 1} 距离:{distance:.0f}px '
                                        f'按压:{press_time}ms'))

                im.close()

                jx = random.uniform(gw * 0.3, gw * 0.7)
                jy = random.uniform(gh * 0.5, gh * 0.8)
                sx, sy = left + int(jx), top + int(jy)

                if self.running and not self.paused:
                    mouse_jump(sx, sy, press_time)
                    self.jump_count += 1
                    self.update_queue.put(('count', self.jump_count))

                rest_counter += 1
                if rest_counter >= rest_threshold:
                    self.update_queue.put(('log',
                        f'💤 已连续 {rest_threshold} 次，休息 {rest_seconds} 秒…'))
                    for s in range(rest_seconds):
                        if not self.running:
                            break
                        time.sleep(1)
                    rest_counter = 0
                    rest_threshold = random.randrange(30, 100)
                    rest_seconds = random.randrange(10, 60)

                if self.running:
                    time.sleep(random.uniform(1.2, 1.4))

            except Exception as e:
                self.update_queue.put(('log', f'错误: {e}'))
                time.sleep(2.0)

    # ── UI 更新轮询（低频，减负）───────────

    def _process_updates(self):
        try:
            # 批量处理队列中的消息
            while True:
                msg_type, data = self.update_queue.get_nowait()
                if msg_type == 'frame':
                    self._display_image(data)
                elif msg_type == 'log':
                    self._log(data)
                elif msg_type == 'count':
                    self.jump_count_label.configure(text=f'跳跃: {data} 次')
        except queue.Empty:
            pass
        self.root.after(120, self._process_updates)

    # ── 辅助 ──────────────────────────────

    def _log(self, msg):
        self.log_text.configure(state=tk.NORMAL)
        ts = time.strftime('%H:%M:%S')
        self.log_text.insert(tk.END, f'[{ts}] {msg}\n')
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _on_coef_change(self):
        v = self.coef_var.get()
        self.coef_label.configure(text=f'{v:.3f}')
        PARAMS['press_coefficient'] = v

    def _on_param_change(self):
        PARAMS['head_diameter'] = self.hd_var.get()

    def run(self):
        self._refresh_windows()
        self.root.mainloop()


if __name__ == '__main__':
    JumpGUI().run()
