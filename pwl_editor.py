"""
PWL波形编辑器
用于创建和编辑PWL（Piecewise Linear）波形
"""

import customtkinter as ctk
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import pyperclip
import ctypes
import json
import math
import bisect
import time
import sys
import os
from PIL import Image

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

# Enable High DPI Scaling on Windows
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")
ctk.set_widget_scaling(1.0)  # Default widget scaling
ctk.set_window_scaling(1.0)  # Default window scaling

class PWLGraphCanvas(ctk.CTkCanvas):
    """
    High-performance Waveform Renderer based on native Tkinter Canvas.
    Replaces Matplotlib for 60FPS interaction and low CPU usage.
    """
    def __init__(self, master, formatter_func, **kwargs):
        super().__init__(master, background="#1e1e1e", highlightthickness=0, **kwargs)
        self.formatter_func = formatter_func
        
        # Viewport
        self.x_min = 0.0
        self.x_max = 10.0
        self.y_min = -1.0
        self.y_max = 1.0
        
        # Margins (pixels)
        self.margin_left = 60
        self.margin_right = 20
        self.margin_top = 20
        self.margin_bottom = 30
        
        # Colors
        self.colors = {
            'bg': '#1e1e1e',
            'grid': '#333333',
            'axis': '#888888',
            'text': '#cccccc',
            'line': '#4FC1FF',
            'point_fill': '#4FC1FF',
            'point_outline': 'white',
            'point_selected': 'yellow',
            'selection_box': '#4444aa'
        }
        
        self.last_draw_args = {}
        self.bind("<Configure>", self.on_resize)
        self._lod_pixel_step = 2
        self._max_preview_points = 3000
        self._stats_last_ms = 0.0
        self._stats_points_drawn = 0
        self._stats_preview_points = 0

        self._x_ticks_cache = (None, None, [])
        self._y_ticks_cache = (None, None, [])
        
    def on_resize(self, event):
        self.redraw(**self.last_draw_args)
        
    def world_to_screen(self, x, y):
        w = self.winfo_width()
        h = self.winfo_height()
        
        draw_w = w - self.margin_left - self.margin_right
        draw_h = h - self.margin_top - self.margin_bottom
        
        if draw_w <= 0 or draw_h <= 0: return 0, 0
        
        x_range = self.x_max - self.x_min
        y_range = self.y_max - self.y_min
        
        if x_range == 0: x_range = 1e-9
        if y_range == 0: y_range = 1e-9
        
        sx = self.margin_left + (x - self.x_min) / x_range * draw_w
        sy = self.margin_top + draw_h - (y - self.y_min) / y_range * draw_h
        
        return sx, sy
        
    def screen_to_world(self, sx, sy):
        w = self.winfo_width()
        h = self.winfo_height()
        
        draw_w = w - self.margin_left - self.margin_right
        draw_h = h - self.margin_top - self.margin_bottom
        
        if draw_w <= 0 or draw_h <= 0: return 0, 0
        
        x_range = self.x_max - self.x_min
        y_range = self.y_max - self.y_min
        
        x = self.x_min + (sx - self.margin_left) / draw_w * x_range
        y = self.y_min + (self.margin_top + draw_h - sy) / draw_h * y_range
        
        return x, y

    def _calc_ticks(self, v_min, v_max, n_ticks=8):
        if v_min >= v_max:
            return [v_min]
        
        span = v_max - v_min
        step = 10 ** math.floor(math.log10(span))
        
        best_step = step
        best_err = float('inf')
        
        for f in [0.1, 0.2, 0.5, 1, 2, 5, 10]:
            trial_step = step * f
            n = span / trial_step
            if abs(n - n_ticks) < best_err:
                best_err = abs(n - n_ticks)
                best_step = trial_step
                
        if best_step == 0: return [v_min]

        start = math.ceil(v_min / best_step) * best_step
        # Fix float precision issues for start
        if abs(start - v_min) < best_step * 1e-5:
            start = v_min
            
        ticks = []
        v = start
        while v <= v_max + best_step * 0.001:
            ticks.append(v)
            v += best_step
            
        return ticks

    def _get_x_ticks(self):
        m1, m2, ticks = self._x_ticks_cache
        if m1 == self.x_min and m2 == self.x_max and ticks:
            return ticks
        ticks = self._calc_ticks(self.x_min, self.x_max, n_ticks=10)
        self._x_ticks_cache = (self.x_min, self.x_max, ticks)
        return ticks

    def _get_y_ticks(self):
        m1, m2, ticks = self._y_ticks_cache
        if m1 == self.y_min and m2 == self.y_max and ticks:
            return ticks
        ticks = self._calc_ticks(self.y_min, self.y_max, n_ticks=8)
        self._y_ticks_cache = (self.y_min, self.y_max, ticks)
        return ticks

    def draw_grid(self):
        w = self.winfo_width()
        h = self.winfo_height()
        
        # Grid lines (labels are drawn later on top of covers)
        
        # X Ticks
        x_ticks = self._get_x_ticks()
        for val in x_ticks:
            sx, _ = self.world_to_screen(val, 0)
            if self.margin_left <= sx <= w - self.margin_right:
                self.create_line(sx, self.margin_top, sx, h - self.margin_bottom, fill=self.colors['grid'], dash=(2, 4))
                # Text moved to redraw end

        # Y Ticks
        y_ticks = self._get_y_ticks()
        for val in y_ticks:
            _, sy = self.world_to_screen(0, val)
            if self.margin_top <= sy <= h - self.margin_bottom:
                self.create_line(self.margin_left, sy, w - self.margin_right, sy, fill=self.colors['grid'], dash=(2, 4))
                # Text moved to redraw end
                
        # Axis Lines
        # Box around plot area
        # Moved to redraw end

    def update_cursor_only(self, placement_mode=False, placement_preview_line=[]):
        if 'placement_mode' in self.last_draw_args:
             self.last_draw_args['placement_mode'] = placement_mode
             self.last_draw_args['placement_preview_line'] = placement_preview_line

        self.delete("placement_preview")
        
        if placement_mode and placement_preview_line:
            self._stats_preview_points = len(placement_preview_line)
            step = max(1, self._lod_pixel_step)
            decimated = []
            last_sx = None
            for t, v in placement_preview_line:
                sx, sy = self.world_to_screen(t, v)
                if last_sx is None or abs(sx - last_sx) >= step:
                    decimated.append((t, v))
                    last_sx = sx
                if len(decimated) > self._max_preview_points:
                    break
            p_coords = []
            for t, v in decimated:
                sx, sy = self.world_to_screen(t, v)
                p_coords.extend([sx, sy])
            if len(p_coords) >= 4:
                self.create_line(p_coords, fill="green", dash=(4, 2), width=1, tags="placement_preview")
            if len(decimated) <= 500:
                for t, v in decimated:
                    sx, sy = self.world_to_screen(t, v)
                    if 0 <= sx <= self.winfo_width() and 0 <= sy <= self.winfo_height():
                        self.create_oval(sx-3, sy-3, sx+3, sy+3, fill="green", outline="green", tags="placement_preview")

    def redraw(self, points=[], selected_indices=set(), placement_mode=False, placement_preview_line=[], box_rect=None):
        self.last_draw_args = {
            'points': points,
            'selected_indices': selected_indices,
            'placement_mode': placement_mode,
            'placement_preview_line': placement_preview_line,
            'box_rect': box_rect
        }
        t_start = time.perf_counter()
        
        self.delete("all")
        
        self.draw_grid()
        
        # Draw Waveform
        if points:
            # Optimize: Only draw points within view + 1 extra on each side
            times = [p[0] for p in points]
            start_idx = bisect.bisect_left(times, self.x_min)
            end_idx = bisect.bisect_right(times, self.x_max)
            
            # Expand range by 1 to ensure lines connect out of view
            start_idx = max(0, start_idx - 1)
            end_idx = min(len(points), end_idx + 1)
            
            visible_points = points[start_idx:end_idx]
            
            # Add line from Y-axis (t=0) to the first point if the first point is not at 0
            # Only if this is the actual beginning of the waveform
            if start_idx == 0 and points and points[0][0] > 0:
                t0, v0 = points[0]
                # Draw a horizontal line from t=0 to t0 at v0
                sx0, sy0 = self.world_to_screen(0, v0)
                sx1, sy1 = self.world_to_screen(t0, v0)
                self.create_line(sx0, sy0, sx1, sy1, fill=self.colors['line'], width=2, capstyle="round", joinstyle="round")

            coords = []
            for i in range(len(visible_points) - 1):
                t0, v0 = visible_points[i]
                t1, v1 = visible_points[i + 1]
                sx0, sy0 = self.world_to_screen(t0, v0)
                sx1, sy1 = self.world_to_screen(t1, v1)
                self.create_line(sx0, sy0, sx1, sy1, fill=self.colors['line'], width=2, capstyle="round", joinstyle="round")
                
            # Draw Points
            r = 5
            # Performance optimization: if too many points, skip drawing unselected ones
            draw_all_points = len(visible_points) < 300 
            
            if draw_all_points:
                # Draw all visible points
                for i in range(start_idx, end_idx):
                    t, v = points[i]
                    sx, sy = self.world_to_screen(t, v)
                    
                    # Check bounds
                    if self.margin_left <= sx <= self.winfo_width() - self.margin_right and \
                       self.margin_top <= sy <= self.winfo_height() - self.margin_bottom:
                        
                        is_selected = i in selected_indices
                        fill = self.colors['point_selected'] if is_selected else self.colors['point_fill']
                        outline = self.colors['point_selected'] if is_selected else self.colors['point_outline']
                        radius = r + 2 if is_selected else r
                        
                        self.create_oval(sx-radius, sy-radius, sx+radius, sy+radius, fill=fill, outline=outline, width=1, tags=f"point_{i}")
            else:
                # Only draw selected points to maintain performance
                for i in selected_indices:
                    if start_idx <= i < end_idx:
                        t, v = points[i]
                        sx, sy = self.world_to_screen(t, v)
                        
                        if self.margin_left <= sx <= self.winfo_width() - self.margin_right and \
                           self.margin_top <= sy <= self.winfo_height() - self.margin_bottom:
                             
                            fill = self.colors['point_selected']
                            outline = self.colors['point_selected']
                            radius = r + 2
                            self.create_oval(sx-radius, sy-radius, sx+radius, sy+radius, fill=fill, outline=outline, width=1, tags=f"point_{i}")

        # Placement Preview
        if placement_mode and placement_preview_line:
            self._stats_preview_points = len(placement_preview_line)
            step = max(1, self._lod_pixel_step)
            decimated = []
            last_sx = None
            for t, v in placement_preview_line:
                sx, sy = self.world_to_screen(t, v)
                if last_sx is None or abs(sx - last_sx) >= step:
                    decimated.append((t, v))
                    last_sx = sx
                if len(decimated) > self._max_preview_points:
                    break
            p_coords = []
            for t, v in decimated:
                sx, sy = self.world_to_screen(t, v)
                p_coords.extend([sx, sy])
            if len(p_coords) >= 4:
                self.create_line(p_coords, fill="green", dash=(4, 2), width=1, tags="placement_preview")
            if len(decimated) <= 500:
                for t, v in decimated:
                    sx, sy = self.world_to_screen(t, v)
                    if 0 <= sx <= self.winfo_width() and 0 <= sy <= self.winfo_height():
                        self.create_oval(sx-3, sy-3, sx+3, sy+3, fill="green", outline="green", tags="placement_preview")
        
        # Cover Margins (Clipping Hack)
        w = self.winfo_width()
        h = self.winfo_height()
        bg = self.colors['bg']
        
        # Top
        self.create_rectangle(0, 0, w, self.margin_top, fill=bg, outline=bg)
        # Bottom
        self.create_rectangle(0, h - self.margin_bottom + 1, w, h, fill=bg, outline=bg)
        # Left
        self.create_rectangle(0, 0, self.margin_left, h, fill=bg, outline=bg)
        # Right
        self.create_rectangle(w - self.margin_right + 1, 0, w, h, fill=bg, outline=bg)
        
        # Redraw axes over the cover
        self.create_rectangle(self.margin_left, self.margin_top, w - self.margin_right, h - self.margin_bottom, outline=self.colors['axis'])
        
        # Re-draw Tick Labels (on top of cover)
        # X Ticks
        x_ticks = self._get_x_ticks()
        for val in x_ticks:
            sx, _ = self.world_to_screen(val, 0)
            if self.margin_left <= sx <= w - self.margin_right:
                 self.create_text(sx, h - self.margin_bottom + 5, text=self.formatter_func(val), anchor="n", fill=self.colors['text'], font=("Arial", 9))

        # Y Ticks
        y_ticks = self._get_y_ticks()
        for val in y_ticks:
            _, sy = self.world_to_screen(0, val)
            if self.margin_top <= sy <= h - self.margin_bottom:
                 self.create_text(self.margin_left - 5, sy, text=self.formatter_func(val), anchor="e", fill=self.colors['text'], font=("Arial", 9))

        # Box Selection (draw last to be on top?)
        if box_rect:
            x0, y0, x1, y1 = box_rect
            # Convert screen coords to ensure safe bounds?
            # box_rect is assumed to be in screen coords already from mouse events
            self.create_rectangle(x0, y0, x1, y1, fill=self.colors['selection_box'], outline=self.colors['point_selected'], stipple="gray25")
        t1 = time.perf_counter()
        self._stats_last_ms = (t1 - t_start) * 1000.0
        self._stats_points_drawn = len(points) if points else 0
        info = f"{self._stats_last_ms:.2f}ms | pts:{self._stats_points_drawn} | ghost:{self._stats_preview_points}"
        self.create_text(self.margin_left + 5, self.margin_top + 5, text=info, anchor="nw", fill=self.colors['text'], font=("Arial", 9))

class PWLEditor:
    """PWL波形编辑器主类"""
    
    # 工程计数前缀映射
    ENGINEERING_PREFIXES = {
        1e-12: 'p', 1e-9: 'n', 1e-6: 'u', 1e-3: 'm',
        1: '', 1e3: 'k', 1e6: 'M', 1e9: 'G'
    }
    
    # 前缀到数值的反向映射
    PREFIX_TO_VALUE = {
        'p': 1e-12, 'n': 1e-9, 'u': 1e-6, 'm': 1e-3,
        '': 1, 'k': 1e3, 'M': 1e6, 'G': 1e9
    }
    
    # 默认配置
    DEFAULT_WINDOW_SIZE = "1200x800"
    DEFAULT_DRAG_PRECISION = 1e-3
    TIME_MIN_PRECISION = 1e-12  # 时间最小精度为1ps
    ZOOM_FACTOR = 1.1  # 滚轮缩放因子
    POINT_CLICK_THRESHOLD = 0.0015  # 点击选中点的阈值
    
    # Theme Colors (VS Code Dark for Matplotlib)
    THEME = {
        'bg': '#1e1e1e',
        'fg': '#d4d4d4',
        'accent': '#007acc',
        'panel_bg': '#252526',
        'input_bg': '#3c3c3c',
        'input_fg': '#cccccc',
        'border': '#3e3e42',
        'plot_bg': '#1e1e1e',
        'grid': '#404040'
    }

    def __init__(self, root):
        self.root = root
        self.root.title("PWL波形编辑器")
        self.root.geometry(self.DEFAULT_WINDOW_SIZE)
        # self.root.resizable(True, True) # CTk windows are resizable by default
        
        # Set Window Icon
        try:
            icon_path = resource_path("app_icon.ico")
            if os.path.exists(icon_path):
                self.root.iconbitmap(icon_path)
        except Exception as e:
            print(f"Failed to set icon: {e}")

        # 初始化数据
        self._init_data()
        
        # 创建菜单栏
        self._create_menu()
        
        # 创建界面
        self._create_widgets()
        
        # 绑定快捷键
        self._bind_shortcuts()
        
        # Handle window closing to prevent "invalid command name" errors
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)
        
        # Force initial layout update to ensure plot is correctly sized
        # self.root.after(200, lambda: self._on_plot_resize(None))

    def _on_closing(self):
        """窗口关闭处理，释放资源并安全退出"""
        try:
            # Cancel all pending 'after' callbacks to prevent errors
            # check if root still exists
            if self.root:
                for after_id in self.root.tk.call('after', 'info'):
                    self.root.after_cancel(after_id)
                self.root.quit()
                self.root.destroy()
        except Exception:
            pass

    def _init_data(self):
        """初始化数据变量"""
        # 存储波形点 (time, value)
        self.points = []
        
        # 拖动相关变量
        self.dragging_indices = []  # 正在拖动的点索引列表
        self.drag_start = None      # 拖动起始坐标 (x, y)
        self.drag_original_data = {} # 拖动前的点数据 {index: (time, value)}
        
        # 拖动精度
        self.drag_precision = self.DEFAULT_DRAG_PRECISION
        
        # 波形缩放相关变量
        self.y_min = -1.0
        self.y_max = 1.0
        self.x_min = 0.0
        self.x_max = 10.0
        self.zoom_fixed = False
        
        # 选中点跟踪
        self.selected_indices = set() # 选中的点索引集合
        self.primary_selected_index = None # 主要选中的点（用于显示在输入框）
        
        # 鼠标位置跟踪
        self.current_cursor_pos = None
        
        # 框选相关变量
        self.box_mode = None # None, 'select', 'zoom'
        self.box_start = None
        self.box_patch = None # Unused in Canvas mode but kept for compat
        self.box_end = None # Added for Canvas mode
        
        # 拖拽视图 (Pan) 相关变量
        self.panning = False
        self.pan_start = None # (x, y) 像素坐标
        self.pan_start_xlim = None
        self.pan_start_ylim = None
        
        # 视图初始化标志
        self.view_initialized = True

        # 放置模式 (Placement Mode)
        self.placement_mode = False
        self.placement_data = [] # 要放置的波形数据 (relative time, value)
        self.clipboard_data = [] # 剪贴板数据
        self.tree_item_ids = [] # 缓存表格项ID，优化选择性能

    def _create_menu(self):
        """创建顶部菜单栏"""
        # 使用原生 tk.Menu，因为 CustomTkinter 尚未提供 Menu 组件
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        
        # --- 文件菜单 ---
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="文件(F)", menu=file_menu)
        file_menu.add_command(label="保存波形(S)", command=self._save_waveform_to_file)
        file_menu.add_command(label="载入波形(L)", command=self._load_waveform_from_file)
        file_menu.add_separator()
        file_menu.add_command(label="退出(X)", command=self._on_closing)
        
        # --- 编辑菜单 ---
        edit_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="编辑(E)", menu=edit_menu)
        edit_menu.add_command(label="复制选区(C)", command=self.copy_selection)
        edit_menu.add_command(label="粘贴(V)", command=self.paste_waveform)
        edit_menu.add_separator()
        edit_menu.add_command(label="删除选中(Del)", command=self.delete_point)
        edit_menu.add_command(label="清空所有", command=self.clear_points)

        # --- 波形菜单 ---
        wave_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="波形(W)", menu=wave_menu)
        wave_menu.add_command(label="生成正弦波...", command=lambda: self._open_wave_generator("sine"))
        wave_menu.add_command(label="生成方波...", command=lambda: self._open_wave_generator("square"))
        wave_menu.add_command(label="生成三角波...", command=lambda: self._open_wave_generator("triangle"))
        
        # --- 关于菜单 ---
        about_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="关于(A)", menu=about_menu)
        about_menu.add_command(label="快捷键列表", command=self._show_shortcuts)
        about_menu.add_command(label="关于本项目", command=self._show_about_info)

    def _save_waveform_to_file(self):
        """保存波形到文件"""
        if not self.points:
            messagebox.showwarning("警告", "当前没有波形数据可保存。")
            return

        file_path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")],
            title="保存波形"
        )
        
        if not file_path:
            return
            
        try:
            data = {
                "points": self.points,
                "version": "1.0",
                "type": "pwl_waveform"
            }
            with open(file_path, 'w') as f:
                json.dump(data, f, indent=4)
            messagebox.showinfo("成功", "波形已成功保存。")
        except Exception as e:
            messagebox.showerror("错误", f"保存文件时出错:\n{str(e)}")

    def _load_waveform_from_file(self):
        """从文件载入波形"""
        file_path = filedialog.askopenfilename(
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")],
            title="载入波形"
        )
        
        if not file_path:
            return
            
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
            
            if "points" not in data:
                raise ValueError("文件格式不正确：缺少 'points' 字段")
                
            self.points = [tuple(p) for p in data["points"]]
            self._refresh_all()
            self.zoom_to_all_points()
            messagebox.showinfo("成功", "波形已成功载入。")
        except Exception as e:
            messagebox.showerror("错误", f"载入文件时出错:\n{str(e)}")

    def _show_shortcuts(self):
        """显示快捷键列表"""
        shortcuts_text = (
            "快捷键列表:\n\n"
            "M: 在鼠标位置添加点\n"
            "Ctrl + C: 复制选中波形\n"
            "Ctrl + V: 粘贴波形 (跟随鼠标放置)\n"
            "Delete: 删除选中点\n"
            "Esc: 取消放置/操作\n"
            "F: 缩放至全部显示 (Fit All)\n"
            "鼠标左键拖动: (空白处) 框选点; (点上) 移动点\n"
            "鼠标右键拖动: 框选放大视图区域\n"
            "鼠标中键拖动: 平移视图\n"
            "Ctrl + Click: 多选/反选点\n"
            "Shift + Click: 范围选择点\n"
            "滚轮: 以指针为中心放大/缩小"
        )
        messagebox.showinfo("快捷键", shortcuts_text)

    def _show_about_info(self):
        """显示关于信息 (Custom Dialog with Avatar)"""
        about_window = ctk.CTkToplevel(self.root)
        about_window.title("关于")
        about_window.geometry("400x450")
        about_window.resizable(False, False)
        
        # Make it modal-like
        about_window.transient(self.root)
        about_window.grab_set()
        
        # 1. Avatar Image
        try:
            # Use icon.png as the avatar
            avatar_path = resource_path("icon.png")
            if os.path.exists(avatar_path):
                # Load image with PIL
                pil_img = Image.open(avatar_path)
                # Resize if needed (e.g. 100x100)
                pil_img = pil_img.resize((100, 100), Image.Resampling.LANCZOS)
                avatar_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(100, 100))
                
                avatar_label = ctk.CTkLabel(about_window, image=avatar_img, text="")
                avatar_label.pack(pady=(30, 10))
            else:
                ctk.CTkLabel(about_window, text="[Avatar Missing]").pack(pady=(30, 10))
        except Exception as e:
            print(f"Error loading avatar: {e}")
            ctk.CTkLabel(about_window, text="[Avatar Error]").pack(pady=(30, 10))

        # 2. Title and Version
        ctk.CTkLabel(about_window, text="PWL Editor", font=("Arial", 20, "bold")).pack(pady=5)
        ctk.CTkLabel(about_window, text="v1.0.0", font=("Arial", 12)).pack(pady=(0, 20))
        
        # 3. Description
        desc_text = (
            "一个用于 Virtuoso 仿真的现代化 PWL 编辑工具。\n"
            "支持工程计数法、波形生成、导出导入等功能。\n\n"
            "Created with Python + CustomTkinter"
        )
        ctk.CTkLabel(about_window, text=desc_text, font=("Arial", 12), justify="center").pack(pady=10)
        
        # 4. Close Button
        ctk.CTkButton(about_window, text="关闭", command=about_window.destroy, width=100).pack(pady=30)

    def _wave_params_to_points(self, wave_type, *, freq=None, period=None, amp=1.0, offset=0.0,
                                duration=0.01, duty=None, t_high=None, tr=None, tf=None,
                                rise_ratio=None, t_rise=None, ppc=50):
        """根据参数生成波形点(纯逻辑，可测试)。
        - 支持频率或周期输入(优先周期)
        - 方波支持占空比(%)或高电平时间(秒)
        - 三角波支持上升占比(%)或上升时间(秒)
        """
        pts = []
        # Resolve period
        if period is None or period <= 0:
            if freq is None or freq <= 0:
                freq = 1e-9
            period = 1.0 / freq
        # Defaults
        if amp is None: amp = 1.0
        if offset is None: offset = 0.0
        if duration is None or duration <= 0: duration = period
        if wave_type == "sine":
            if ppc is None or ppc < 4: ppc = 50
            dt = period / ppc
            t = 0.0
            while t <= duration + 1e-15:
                val = amp * math.sin(2 * math.pi * (1.0/period) * t) + offset
                pts.append((t, val))
                t += dt
        elif wave_type == "square":
            # Transition times
            if tr is None or tr <= 0: tr = period / 100.0
            if tf is None or tf <= 0: tf = period / 100.0
            if tr + tf >= period:
                tr = period / 20.0
                tf = period / 20.0
            # High duration from t_high or duty
            if t_high is not None and t_high > 0:
                t_high = min(t_high, max(1e-15, period - (tr + tf)))
            else:
                if duty is None:
                    duty = 0.5
                duty = max(0.0, min(1.0, duty))
                t_high = period * duty
            t = 0.0
            while t < duration - 1e-15:
                pts.append((t, offset - amp))
                pts.append((min(t + tr, duration), offset + amp))
                if t + t_high < duration:
                    pts.append((t + t_high, offset + amp))
                    pts.append((min(t + t_high + tf, duration), offset - amp))
                t += period
                if t < duration:
                    pts.append((t, offset - amp))
        elif wave_type == "triangle":
            # Rise time from t_rise or ratio
            if t_rise is not None and t_rise >= 0:
                t_rise = min(period, max(0.0, t_rise))
            else:
                if rise_ratio is None:
                    rise_ratio = 0.5
                rise_ratio = max(0.0, min(1.0, rise_ratio))
                t_rise = period * rise_ratio
            t = 0.0
            while t < duration - 1e-15:
                pts.append((t, offset - amp))
                peak_t = t + t_rise
                if peak_t <= duration:
                    pts.append((peak_t, offset + amp))
                end_t = t + period
                if end_t <= duration:
                    pts.append((end_t, offset - amp))
                t += period
        # Sort, normalize to start at 0
        pts.sort(key=lambda x: x[0])
        if pts:
            s0 = pts[0][0]
            pts = [(t - s0, v) for t, v in pts]
        return pts

    def _open_wave_generator(self, wave_type):
        """
        打开波形生成器对话框。
        
        这是一个包含 UI 构建、实时预览逻辑和生成逻辑的复杂函数。
        使用闭包 (Closure) 方式管理 entries 和 update_preview 回调，
        以便在用户输入时实时更新预览图表。
        """
        dialog = ctk.CTkToplevel(self.root)
        dialog.title("波形生成器")
        dialog.geometry("900x600") # 增加宽度以容纳左右布局
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Title
        type_names = {"sine": "正弦波", "square": "方波", "triangle": "三角波"}
        ctk.CTkLabel(dialog, text=f"生成 {type_names.get(wave_type, '波形')}", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=10)
        
        # --- Bottom: Action Buttons ---
        # Pack button frame first to ensure it's always visible at the bottom
        button_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        button_frame.pack(side=ctk.BOTTOM, fill=ctk.X, padx=20, pady=20)
        
        # Main Content Container (Side-by-Side Layout)
        content_frame = ctk.CTkFrame(dialog)
        content_frame.pack(side=ctk.TOP, fill=ctk.BOTH, expand=True, padx=10, pady=10)
        
        # --- Left: Input Fields Container ---
        # 使用 ScrollableFrame 防止输入项过多超出屏幕
        input_scroll_frame = ctk.CTkScrollableFrame(content_frame, width=320)
        input_scroll_frame.pack(side=ctk.LEFT, fill=ctk.Y, padx=(0, 10))
        
        # --- Right: Preview Plot ---
        preview_frame = ctk.CTkFrame(content_frame)
        preview_frame.pack(side=ctk.RIGHT, fill=ctk.BOTH, expand=True)
        
        # Use PWLGraphCanvas for preview
        canvas_preview = PWLGraphCanvas(preview_frame, formatter_func=self.engineering_format)
        canvas_preview.pack(fill=ctk.BOTH, expand=True)
        
        # Adjust margins for smaller preview
        canvas_preview.margin_left = 40
        canvas_preview.margin_right = 10
        canvas_preview.margin_top = 10
        canvas_preview.margin_bottom = 20
        
        entries = {}
        vars_map = {}
        
        def update_preview(*args):
            try:
                # 获取参数 (使用默认值以防解析错误)
                try: freq = self.parse_engineering_format(entries.get("freq").get())
                except: freq = 1000.0
                try: period = self.parse_engineering_format(entries.get("period").get())
                except: period = None
                
                try: amp = self.parse_engineering_format(entries.get("amp").get())
                except: amp = 1.0
                
                try: offset = self.parse_engineering_format(entries.get("offset").get())
                except: offset = 0.0
                
                if period is None or period <= 0:
                    if freq <= 0: freq = 1e-9
                    period = 1.0 / freq
                preview_points = []
                
                if wave_type == "sine":
                    try: ppc = int(entries.get("points_per_cycle").get())
                    except: ppc = 50
                    if ppc < 4: ppc = 4
                    
                    t = 0.0
                    dt = period / ppc
                    # Preview 1 cycle + a bit
                    while t <= period * 1.1:
                        val = amp * math.sin(2 * math.pi * freq * t) + offset
                        preview_points.append((t, val))
                        t += dt
                        
                elif wave_type == "square":
                    try: duty = float(entries.get("duty").get()) / 100.0
                    except: duty = 0.5
                    try: tr = self.parse_engineering_format(entries.get("tr").get())
                    except: tr = period / 100.0
                    
                    try: tf = self.parse_engineering_format(entries.get("tf").get())
                    except: tf = period / 100.0
                    try: t_high = self.parse_engineering_format(entries.get("t_high").get())
                    except: t_high = None
                    
                    if tr + tf >= period: 
                        tr = period / 20.0
                        tf = period / 20.0
                    
                    if t_high is None or t_high <= 0:
                        t_high = period * duty
                    
                    # 1 cycle for preview
                    t = 0.0
                    preview_points.append((t, offset - amp))
                    preview_points.append((t + tr, offset + amp))
                    
                    preview_points.append((t + t_high, offset + amp))
                    preview_points.append((t + t_high + tf, offset - amp))
                    preview_points.append((t + period, offset - amp))

                elif wave_type == "triangle":
                    try: rise_ratio = float(entries.get("rise_ratio").get()) / 100.0
                    except: rise_ratio = 0.5
                    try: t_rise = self.parse_engineering_format(entries.get("t_rise").get())
                    except: t_rise = None
                    
                    if rise_ratio < 0: rise_ratio = 0.0
                    if rise_ratio > 1: rise_ratio = 1.0
                    
                    if t_rise is None or t_rise < 0:
                        t_rise = period * rise_ratio
                    
                    # 1 cycle for preview
                    t = 0.0
                    preview_points.append((t, offset - amp))
                    
                    # Peak
                    if t_rise > 0 and t_rise < period:
                        preview_points.append((t + t_rise, offset + amp))
                    elif t_rise == 0:
                         preview_points.append((t, offset + amp)) # Instant rise
                    elif t_rise == period:
                         preview_points.append((t + period, offset + amp)) # Peak at end
                    
                    # End of cycle
                    preview_points.append((t + period, offset - amp))
                
                # Auto-scale Preview
                if preview_points:
                    times = [p[0] for p in preview_points]
                    values = [p[1] for p in preview_points]
                    
                    x_min, x_max = min(times), max(times)
                    y_min, y_max = min(values), max(values)
                    
                    x_range = x_max - x_min if x_max > x_min else 1e-9
                    y_range = y_max - y_min if y_max > y_min else 1.0
                    
                    canvas_preview.x_min = x_min - x_range * 0.1
                    canvas_preview.x_max = x_max + x_range * 0.1
                    canvas_preview.y_min = y_min - y_range * 0.1
                    canvas_preview.y_max = y_max + y_range * 0.1
                
                canvas_preview.redraw(points=preview_points)
                
            except Exception:
                pass # Ignore errors during live preview updates

        def add_input(label_text, key, default_val):
            row = len(entries)
            ctk.CTkLabel(input_scroll_frame, text=label_text).grid(row=row, column=0, sticky="w", padx=5, pady=5)
            
            # Use StringVar to trace changes
            var = tk.StringVar(value=default_val)
            var.trace_add("write", update_preview)
            vars_map[key] = var
            
            entry = ctk.CTkEntry(input_scroll_frame, textvariable=var)
            entry.grid(row=row, column=1, sticky="ew", padx=5, pady=5)
            entries[key] = entry
            
        input_scroll_frame.grid_columnconfigure(1, weight=1)
        
        add_input("频率 (Hz):", "freq", "1k")
        add_input("周期 (s):", "period", "1m")
        add_input("幅度 (V):", "amp", "1.0")
        add_input("偏移 (V):", "offset", "0.0")
        add_input("时长 (s):", "duration", "5m")
        
        if wave_type == "square":
            add_input("占空比 (%):", "duty", "50")
            add_input("上升时间 (s):", "tr", "1n")
            add_input("下降时间 (s):", "tf", "1n")
            add_input("高电平时间 (s):", "t_high", "500u")
        elif wave_type == "sine":
            add_input("每周期点数:", "points_per_cycle", "50")
        elif wave_type == "triangle":
            add_input("上升占比 (%):", "rise_ratio", "50")
            add_input("上升时间 (s):", "t_rise", "500u")
            
        syncing = {"fp": False, "sq": False, "tr": False}

        def _get_period_for_sync():
            try:
                p = self.parse_engineering_format(vars_map.get("period").get())
            except:
                p = None
            if p is None or p <= 0:
                try:
                    f = self.parse_engineering_format(vars_map.get("freq").get())
                except:
                    f = 0.0
                if f > 0:
                    return 1.0 / f
                return None
            return p

        def on_freq_change(*_):
            if syncing["fp"]:
                return
            try:
                f = self.parse_engineering_format(vars_map.get("freq").get())
                if f and f > 0:
                    syncing["fp"] = True
                    vars_map.get("period").set(self.engineering_format(1.0 / f))
            finally:
                syncing["fp"] = False

        def on_period_change(*_):
            if syncing["fp"]:
                return
            try:
                p = self.parse_engineering_format(vars_map.get("period").get())
                if p and p > 0:
                    syncing["fp"] = True
                    vars_map.get("freq").set(self.engineering_format(1.0 / p))
            finally:
                syncing["fp"] = False

        def on_duty_change(*_):
            if syncing["sq"]:
                return
            try:
                period = _get_period_for_sync()
                if period and period > 0:
                    try:
                        duty_pct = float(vars_map.get("duty").get())
                    except:
                        duty_pct = None
                    if duty_pct is not None:
                        syncing["sq"] = True
                        t_high = period * max(0.0, min(100.0, duty_pct)) / 100.0
                        vars_map.get("t_high").set(self.engineering_format(t_high))
            finally:
                syncing["sq"] = False

        def on_thigh_change(*_):
            if syncing["sq"]:
                return
            try:
                period = _get_period_for_sync()
                if period and period > 0:
                    try:
                        th = self.parse_engineering_format(vars_map.get("t_high").get())
                    except:
                        th = None
                    if th is not None:
                        syncing["sq"] = True
                        duty_pct = max(0.0, min(100.0, (th / period) * 100.0))
                        vars_map.get("duty").set(f"{round(duty_pct, 6)}")
            finally:
                syncing["sq"] = False

        def on_rise_ratio_change(*_):
            if syncing["tr"]:
                return
            try:
                period = _get_period_for_sync()
                if period and period > 0:
                    try:
                        rr = float(vars_map.get("rise_ratio").get())
                    except:
                        rr = None
                    if rr is not None:
                        syncing["tr"] = True
                        t_r = period * max(0.0, min(100.0, rr)) / 100.0
                        vars_map.get("t_rise").set(self.engineering_format(t_r))
            finally:
                syncing["tr"] = False

        def on_trise_change(*_):
            if syncing["tr"]:
                return
            try:
                period = _get_period_for_sync()
                if period and period > 0:
                    try:
                        t_r = self.parse_engineering_format(vars_map.get("t_rise").get())
                    except:
                        t_r = None
                    if t_r is not None:
                        syncing["tr"] = True
                        rr = max(0.0, min(100.0, (t_r / period) * 100.0))
                        vars_map.get("rise_ratio").set(f"{round(rr, 6)}")
            finally:
                syncing["tr"] = False

        vars_map.get("freq").trace_add("write", on_freq_change)
        vars_map.get("period").trace_add("write", on_period_change)
        if wave_type == "square":
            vars_map.get("duty").trace_add("write", on_duty_change)
            vars_map.get("t_high").trace_add("write", on_thigh_change)
        if wave_type == "triangle":
            vars_map.get("rise_ratio").trace_add("write", on_rise_ratio_change)
            vars_map.get("t_rise").trace_add("write", on_trise_change)

        update_preview()
            
        # Generate Button
        def on_generate():
            try:
                freq = self.parse_engineering_format(entries.get("freq").get())
                period = self.parse_engineering_format(entries.get("period").get())
                amp = self.parse_engineering_format(entries.get("amp").get())
                offset = self.parse_engineering_format(entries.get("offset").get())
                duration = self.parse_engineering_format(entries.get("duration").get())
                
                if freq <= 0 or duration <= 0:
                    raise ValueError("频率和时长必须大于0")
                
                new_points = self._wave_params_to_points(
                    wave_type,
                    freq=freq,
                    period=period,
                    amp=amp,
                    offset=offset,
                    duration=duration,
                    duty=(float(entries.get("duty").get())/100.0) if wave_type=="square" else None,
                    t_high=self.parse_engineering_format(entries.get("t_high").get()) if wave_type=="square" else None,
                    tr=self.parse_engineering_format(entries.get("tr").get()) if wave_type=="square" else None,
                    tf=self.parse_engineering_format(entries.get("tf").get()) if wave_type=="square" else None,
                    rise_ratio=(float(entries.get("rise_ratio").get())/100.0) if wave_type=="triangle" else None,
                    t_rise=self.parse_engineering_format(entries.get("t_rise").get()) if wave_type=="triangle" else None,
                    ppc=int(entries.get("points_per_cycle").get()) if wave_type=="sine" else 50
                )
                
                # Sort and deduplicate slightly
                new_points.sort(key=lambda x: x[0])
                
                # Normalize time (start from 0)
                if new_points:
                     start_t = new_points[0][0]
                     new_points = [(t - start_t, v) for t, v in new_points]
                
                dialog.destroy()
                
                # Start Placement Mode
                self._start_placement_mode(new_points)
                
            except ValueError as e:
                messagebox.showerror("输入错误", str(e))
            except Exception as e:
                messagebox.showerror("错误", f"生成波形时出错: {str(e)}")

        ctk.CTkButton(button_frame, text="生成波形", command=on_generate).pack(pady=0)
        
        # 强制初始重绘，解决显示不全问题
        def initial_resize():
            try:
                # 强制更新 Tk 任务，确保获取到准确的窗口尺寸
                dialog.update()
                
                # 再次强制 Configure (虽然 pack 应该自动处理，但保险起见)
                content_frame.pack_configure(fill=ctk.BOTH, expand=True)
                
                # 手动触发一次大小更新
                update_chart_size()
            except:
                pass
                
        # 使用多次延时确保在不同性能机器上都能正确刷新
        dialog.after(100, initial_resize)
        dialog.after(500, initial_resize)

    def _create_widgets(self):
        """创建所有界面组件"""
        # 创建主框架
        main_frame = ctk.CTkFrame(self.root)
        main_frame.pack(fill=ctk.BOTH, expand=True, padx=10, pady=10)
        
        # Create Vertical PanedWindow (Splitter)
        # Use tk.PanedWindow for resizing capability
        # Configure style to match dark theme
        self.paned_window = tk.PanedWindow(main_frame, orient=tk.VERTICAL, bg="#2B2B2B", sashwidth=4, sashrelief=tk.FLAT)
        self.paned_window.pack(fill=ctk.BOTH, expand=True)
        
        # 1. Top Pane: Waveform Display
        # Container for plot
        plot_container = ctk.CTkFrame(self.paned_window)
        self.paned_window.add(plot_container, stretch="always") # Height will be set later
        
        self._create_plot_area(plot_container)
        
        # 2. Bottom Pane: Operation Panel + Table/Text
        # Container for bottom content
        bottom_container = ctk.CTkFrame(self.paned_window)
        self.paned_window.add(bottom_container, stretch="always")
        
        # Configure grid for bottom container
        bottom_container.grid_columnconfigure(0, weight=1) # Table
        bottom_container.grid_columnconfigure(1, weight=0) # Controls (Fixed width)
        bottom_container.grid_columnconfigure(2, weight=1) # Text
        bottom_container.grid_rowconfigure(0, weight=1)
        
        # 2.1 Left: Table Area
        left_frame = ctk.CTkFrame(bottom_container)
        left_frame.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        self._create_table_area(left_frame)
        
        # 2.2 Center: Operation Controls
        center_frame = ctk.CTkFrame(bottom_container)
        center_frame.grid(row=0, column=1, sticky="ns", padx=5, pady=5)
        self._create_toolbar_area(center_frame)
        
        # 2.3 Right: PWL Output Area
        right_frame = ctk.CTkFrame(bottom_container)
        right_frame.grid(row=0, column=2, sticky="nsew", padx=5, pady=5)
        self._create_pwl_output_area(right_frame)
        
        # 初始化显示
        self._refresh_all()
        
        # 强制触发布局调整，解决缩放问题
        self.root.after(200, self._initial_layout_adjustment)

    def _initial_layout_adjustment(self):
        """初始布局调整，确保窗口分割比例正确且Matplotlib显示正常"""
        try:
            self.root.update_idletasks()
            
            # 设置 PanedWindow 分割线位置为窗口高度的 1/2
            # 注意：sash_place 需要像素坐标
            win_height = self.paned_window.winfo_height()
            if win_height > 100:
                self.paned_window.sash_place(0, 0, win_height // 2)
            
            # 强制重绘 Matplotlib 画布
            if hasattr(self, 'canvas'):
                self.canvas.draw()
                
        except Exception:
            pass
    
    def _create_plot_area(self, parent):
        """创建波形显示区域 (Canvas Version)"""
        self.plot_frame = ctk.CTkFrame(parent) 
        self.plot_frame.pack(fill=ctk.BOTH, expand=True, pady=(0, 0))
        
        # Instantiate Custom Canvas
        self.canvas = PWLGraphCanvas(self.plot_frame, formatter_func=self.engineering_format)
        self.canvas.pack(fill=ctk.BOTH, expand=True)
        
        # 绑定鼠标事件
        self.canvas.bind('<Button-1>', self._on_mouse_press)
        self.canvas.bind('<ButtonRelease-1>', self._on_mouse_release)
        self.canvas.bind('<B1-Motion>', self._on_mouse_motion)
        self.canvas.bind('<Button-3>', self._on_mouse_press) # Right click box zoom
        self.canvas.bind('<B3-Motion>', self._on_mouse_motion)
        self.canvas.bind('<ButtonRelease-3>', self._on_mouse_release)
        self.canvas.bind('<Button-2>', self._on_mouse_press) # Middle click pan
        self.canvas.bind('<B2-Motion>', self._on_mouse_motion)
        self.canvas.bind('<ButtonRelease-2>', self._on_mouse_release)
        self.canvas.bind('<Motion>', self._on_mouse_motion) # Track mouse hover for placement preview
        self.canvas.bind('<MouseWheel>', self._on_mouse_scroll)
        
        # For Linux
        self.canvas.bind('<Button-4>', self._on_mouse_scroll)
        self.canvas.bind('<Button-5>', self._on_mouse_scroll)
        
        # Initial View Setup
        self.canvas.x_min = 0.0
        self.canvas.x_max = 1e-3
        self.canvas.y_min = -1.5
        self.canvas.y_max = 1.5

    # _on_plot_resize removed (handled by Canvas class)
    # _on_draw removed
    # _draw_animated_artists removed

    def _create_toolbar_area(self, parent):
        """创建操作工具栏 (Vertical Layout for Center Panel)"""
        # Parent is the center_frame
        
        title_label = ctk.CTkLabel(parent, text="操作面板", font=ctk.CTkFont(size=14, weight="bold"))
        title_label.pack(pady=(5, 10))
        
        # --- Group 1: Point Edit ---
        g1 = ctk.CTkFrame(parent, fg_color="transparent")
        g1.pack(fill=ctk.X, padx=5, pady=2)
        
        # Time
        row_t = ctk.CTkFrame(g1, fg_color="transparent")
        row_t.pack(fill=ctk.X, pady=2)
        ctk.CTkLabel(row_t, text="时间:", width=40, anchor="w").pack(side=ctk.LEFT)
        self.time_entry = ctk.CTkEntry(row_t)
        self.time_entry.pack(side=ctk.LEFT, fill=ctk.X, expand=True, padx=(5,0))
        
        # Value
        row_v = ctk.CTkFrame(g1, fg_color="transparent")
        row_v.pack(fill=ctk.X, pady=2)
        ctk.CTkLabel(row_v, text="数值:", width=40, anchor="w").pack(side=ctk.LEFT)
        self.value_entry = ctk.CTkEntry(row_v)
        self.value_entry.pack(side=ctk.LEFT, fill=ctk.X, expand=True, padx=(5,0))
        
        # Add Button
        ctk.CTkButton(g1, text="添加/更新", command=self.add_or_update_point).pack(fill=ctk.X, pady=(5, 2))
        
        # Separator
        ctk.CTkFrame(parent, height=2, fg_color="#404040").pack(fill=ctk.X, padx=10, pady=10)

        # --- Group 2: Actions ---
        g2 = ctk.CTkFrame(parent, fg_color="transparent")
        g2.pack(fill=ctk.X, padx=5, pady=2)
        
        ctk.CTkButton(g2, text="快速添加(1m)", command=self.quick_add_point).pack(fill=ctk.X, pady=2)
        
        row_del = ctk.CTkFrame(g2, fg_color="transparent")
        row_del.pack(fill=ctk.X, pady=2)
        ctk.CTkButton(row_del, text="删除选中", command=self.delete_point, fg_color="red", hover_color="darkred").pack(side=ctk.LEFT, fill=ctk.X, expand=True, padx=(0,2))
        ctk.CTkButton(row_del, text="清空", command=self.clear_points, fg_color="red", hover_color="darkred", width=50).pack(side=ctk.RIGHT, padx=(2,0))

        # Separator
        ctk.CTkFrame(parent, height=2, fg_color="#404040").pack(fill=ctk.X, padx=10, pady=10)
        
        # --- Group 3: Settings ---
        g3 = ctk.CTkFrame(parent, fg_color="transparent")
        g3.pack(fill=ctk.X, padx=5, pady=2)
        
        ctk.CTkButton(g3, text="缩放全部(F)", command=self.zoom_to_all_points).pack(fill=ctk.X, pady=2)
        
        # Precision
        row_p = ctk.CTkFrame(g3, fg_color="transparent")
        row_p.pack(fill=ctk.X, pady=(5, 2))
        ctk.CTkLabel(row_p, text="拖动精度:", anchor="w").pack(side=ctk.LEFT)
        self.precision_var = ctk.StringVar(value="1m")
        precision_combo = ctk.CTkComboBox(
            row_p, variable=self.precision_var,
            values=["1", "0.1", "0.01", "1m"], state="readonly", width=100,
            command=self._on_precision_change_ctk
        )
        precision_combo.pack(side=ctk.RIGHT, padx=(5,0))
        
        # Y-Axis
        ctk.CTkLabel(g3, text="Y轴范围:", anchor="w").pack(fill=ctk.X, pady=(5,0))
        row_y = ctk.CTkFrame(g3, fg_color="transparent")
        row_y.pack(fill=ctk.X, pady=2)
        self.y_min_entry = ctk.CTkEntry(row_y, width=60)
        self.y_min_entry.pack(side=ctk.LEFT, fill=ctk.X, expand=True)
        ctk.CTkLabel(row_y, text="-").pack(side=ctk.LEFT, padx=2)
        self.y_max_entry = ctk.CTkEntry(row_y, width=60)
        self.y_max_entry.pack(side=ctk.LEFT, fill=ctk.X, expand=True)
        ctk.CTkButton(row_y, text="Set", width=40, command=self.set_y_axis).pack(side=ctk.RIGHT, padx=(5,0))

    def _on_precision_change_ctk(self, choice):
        """CTK Combobox callback"""
        self._on_precision_change(None)

    def _create_table_area(self, parent):
        """创建表格显示区域"""
        # Using ttk.Treeview because CTk doesn't have one yet, but wrapped in CTkFrame
        # Custom style for Treeview to match dark theme
        style = ttk.Style()
        style.theme_use("default")
        style.configure("Treeview", 
            background="#2b2b2b", 
            foreground="white", 
            fieldbackground="#2b2b2b", 
            borderwidth=0,
            rowheight=25
        )
        style.map('Treeview', background=[('selected', '#1f538d')])
        style.configure("Treeview.Heading",
            background="#3a3a3a",
            foreground="white",
            relief="flat"
        )
        style.map("Treeview.Heading",
            background=[('active', '#4a4a4a')]
        )
        
        title_label = ctk.CTkLabel(parent, text="波形点列表", font=ctk.CTkFont(size=14, weight="bold"))
        title_label.pack(anchor="w", padx=10, pady=5)

        # 创建表格
        self.tree = ttk.Treeview(parent, columns=("time", "value"), show="headings")
        self.tree.heading("time", text="时间")
        self.tree.heading("value", text="数值")
        self.tree.column("time", width=100)
        self.tree.column("value", width=100)
        
        # 添加滚动条
        # CTkScrollbar is better looking
        scrollbar = ctk.CTkScrollbar(parent, command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        
        # 布局
        self.tree.pack(side=ctk.LEFT, fill=ctk.BOTH, expand=True, padx=(5,0), pady=5)
        scrollbar.pack(side=ctk.RIGHT, fill=ctk.Y, padx=(0,5), pady=5)
        
        # 绑定事件
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        # 禁用双击编辑，保持只选中不修改
        self.tree.bind("<Double-1>", lambda e: None)
        
    def _create_pwl_output_area(self, parent):
        """创建PWL输出区域"""
        title_label = ctk.CTkLabel(parent, text="PWL文本输出", font=ctk.CTkFont(size=14, weight="bold"))
        title_label.pack(anchor="w", padx=10, pady=5)
        
        # 创建文本框
        self.pwl_text = ctk.CTkTextbox(parent, height=200, wrap="word")
        self.pwl_text.pack(fill=ctk.BOTH, expand=True, pady=(0, 5), padx=5)
        self.pwl_text.configure(state="disabled")
        
        # 创建按钮框架
        btn_frame = ctk.CTkFrame(parent, fg_color="transparent")
        btn_frame.pack(fill=ctk.X, padx=5, pady=5)
        
        # 按钮
        ctk.CTkButton(btn_frame, text="复制PWL文本", command=self.copy_pwl).pack(side=ctk.LEFT, padx=5)
        ctk.CTkButton(btn_frame, text="保存PWL文本", command=self.save_pwl).pack(side=ctk.LEFT, padx=5)
        ctk.CTkButton(btn_frame, text="生成示例波形", command=self.generate_example).pack(side=ctk.RIGHT, padx=5)
        
    def _bind_shortcuts(self):
        """绑定快捷键"""
        self.root.bind("<KeyPress-f>", self.zoom_to_all_points)
        self.root.bind("<KeyPress-F>", self.zoom_to_all_points)
        self.root.bind("<Delete>", lambda e: self.delete_point())
        self.root.bind("<Control-c>", lambda e: self.copy_selection())
        self.root.bind("<Control-v>", lambda e: self.paste_waveform())
        self.root.bind("<Escape>", lambda e: self._cancel_placement())
        self.root.bind("m", self._on_m_key)
        self.root.bind("M", self._on_m_key)

    def _on_m_key(self, event):
        """M键快捷添加点"""
        # Check if focus is on an input field
        focused_widget = self.root.focus_get()
        if isinstance(focused_widget, (tk.Entry, ttk.Entry, ctk.CTkEntry, tk.Text)):
             return
             
        if self.current_cursor_pos is None:
            # Try to get cursor position if not tracking
            try:
                px, py = self.root.winfo_pointerxy()
                cx = px - self.canvas.winfo_rootx()
                cy = py - self.canvas.winfo_rooty()
                self.current_cursor_pos = self.canvas.screen_to_world(cx, cy)
            except:
                return
            
        x, y = self.current_cursor_pos
        
        # Check bounds (optional, but good practice)
        if x < self.canvas.x_min - (self.canvas.x_max - self.canvas.x_min) or \
           x > self.canvas.x_max + (self.canvas.x_max - self.canvas.x_min):
             # Ignore if way out of bounds? No, user might want to add outside.
             pass

        # 应用精度
        time = max(0.0, x)
        time = round(time / self.TIME_MIN_PRECISION) * self.TIME_MIN_PRECISION
        value = round(y / self.drag_precision) * self.drag_precision
        
        if self._check_time_conflict(time):
            # If conflict, maybe user didn't move mouse enough.
            # We could try to nudge it? No, explicit is better.
            # Provide visual feedback?
            self.root.bell() 
            return
            
        self.points.append((time, value))
        self.points.sort()
        
        idx = self.points.index((time, value))
        self.selected_indices = {idx}
        self.primary_selected_index = idx
        
        self._refresh_all()

    def copy_selection(self):
        """复制选中波形"""
        if not self.selected_indices:
            return
            
        # 获取选中点
        selected_points = [self.points[i] for i in sorted(self.selected_indices) if i < len(self.points)]
        if not selected_points:
            return
            
        # 归一化时间（相对于第一个点）
        base_time = selected_points[0][0]
        self.clipboard_data = [(t - base_time, v) for t, v in selected_points]
        
        # 可选：显示状态提示
        # print(f"Copied {len(self.clipboard_data)} points")

    def paste_waveform(self):
        """粘贴波形（进入放置模式）"""
        if not self.clipboard_data:
            return
            
        self._start_placement_mode(self.clipboard_data)

    def _start_placement_mode(self, data):
        """启动放置模式"""
        self.placement_mode = True
        self.placement_data = data
        self.root.config(cursor="crosshair")
        
        # 初始预览位置（如果在图表内，则跟随鼠标；否则默认）
        if self.current_cursor_pos:
             self._update_placement_preview(self.current_cursor_pos)
        else:
             # Default to center of view or 0?
             # Wait for mouse motion
             pass

    def _cancel_placement(self):
        """取消放置模式"""
        if self.placement_mode:
            self.placement_mode = False
            self.placement_data = []
            self.root.config(cursor="")
            self._update_plot(fast_update=True) # Clear ghost

    def _update_placement_preview(self, cursor_pos):
        """更新放置预览"""
        if not self.placement_mode or not self.placement_data:
            return
            
        # Update current cursor pos just in case
        self.current_cursor_pos = cursor_pos
        
        # Trigger redraw via update_plot
        self._update_plot(fast_update=True)
        
    # ==================== 数据操作方法 ====================
    
    def _refresh_all(self):
        """刷新所有显示"""
        self._update_table()
        if self.selected_indices and hasattr(self, 'tree_item_ids') and self.tree_item_ids:
            sel = self.tree.selection()
            if sel:
                self.tree.selection_remove(sel)
            for idx in sorted(self.selected_indices):
                if 0 <= idx < len(self.tree_item_ids):
                    item_id = self.tree_item_ids[idx]
                    self.tree.selection_add(item_id)
                    self.tree.see(item_id)
        self._update_plot()
        self._update_pwl_text()
        
    def _clear_entries(self):
        """清空输入框"""
        self.time_entry.delete(0, tk.END)
        self.value_entry.delete(0, tk.END)
        
    def _set_entries(self, time, value):
        """设置输入框的值"""
        self._clear_entries()
        self.time_entry.insert(0, self.engineering_format(time))
        self.value_entry.insert(0, self.engineering_format(value))
        
    def _check_time_conflict(self, new_time, exclude_index=None):
        """
        检查时间是否与其他点冲突 (距离小于最小精度)。
        
        Args:
            new_time: 要检查的时间点
            exclude_index: 排除的索引 (用于更新点时忽略自身)
            
        Returns:
            bool: 如果存在冲突返回 True，否则 False
        """
        threshold = self.TIME_MIN_PRECISION * 2
        for i, (t, _) in enumerate(self.points):
            if exclude_index is not None and i == exclude_index:
                continue
            if abs(t - new_time) < threshold:
                return True
        return False
    
    def _ensure_min_spacing(self, points):
        if not points:
            return []
        pts = sorted(points, key=lambda x: x[0])
        result = []
        prev_t = None
        for t, v in pts:
            if prev_t is None:
                t = max(0.0, t)
                result.append((t, v))
                prev_t = t
            else:
                if t < prev_t + self.TIME_MIN_PRECISION:
                    t = prev_t + self.TIME_MIN_PRECISION
                result.append((t, v))
                prev_t = t
        return result

    def _enforce_min_dt_for_drag(self, dragged_indices):
        if not dragged_indices:
            return
        # Build non-drag neighbors sorted by time
        non_drag = [(t, v) for i, (t, v) in enumerate(self.points) if i not in dragged_indices]
        non_drag.sort(key=lambda x: x[0])
        non_times = [t for t, _ in non_drag]
        min_dt = self.TIME_MIN_PRECISION
        # Prepare dragged entries with corridors
        entries = []
        for i in dragged_indices:
            if 0 <= i < len(self.points):
                t, v = self.points[i]
                # Find previous and next non-drag neighbor
                import bisect as _bis
                pos = _bis.bisect_left(non_times, t)
                prev_time = non_times[pos-1] if pos-1 >= 0 else None
                next_time = non_times[pos] if pos < len(non_times) else None
                low = max(0.0, (prev_time + min_dt) if prev_time is not None else 0.0)
                high = (next_time - min_dt) if next_time is not None else float('inf')
                entries.append([i, t, v, low, high])
        # Sort dragged by original target time
        entries.sort(key=lambda e: e[1])
        prev_adj = None
        for k in range(len(entries)):
            i, t, v, low, high = entries[k]
            t_adj = max(t, low)
            if prev_adj is not None:
                t_adj = max(t_adj, prev_adj + min_dt)
            if t_adj > high:
                # Clamp to high; may violate prev spacing if corridor too tight
                t_adj = high if high != float('inf') else t_adj
                if prev_adj is not None and t_adj < prev_adj + min_dt:
                    t_adj = prev_adj + min_dt
            if t_adj < 0.0:
                t_adj = 0.0
            self.points[i] = (t_adj, v)
            prev_adj = t_adj

    def _enforce_negative_axis_limit(self):
        try:
            x_min = float(self.canvas.x_min)
            x_max = float(self.canvas.x_max)
            rng = x_max - x_min
            if rng <= 0:
                rng = 1e-12
                x_max = x_min + rng
            # Ensure x_max > tiny positive to make limit meaningful
            if x_max <= 1e-15:
                x_max = 1e-15
                self.canvas.x_max = x_max
                self.canvas.x_min = x_max - rng
                x_min = self.canvas.x_min
                rng = x_max - x_min
                if rng <= 0:
                    rng = 1e-12
                    self.canvas.x_min = x_max - rng
            # Clamp negative portion to <=5%
            if x_min < 0 and x_max > 0:
                limit_min = -(0.05 / 0.95) * x_max
                if x_min < limit_min:
                    self.canvas.x_min = limit_min
        except Exception:
            pass
        
    # ==================== 工程计数格式转换 ====================
    
    def engineering_format(self, value):
        """将数值格式化为工程计数（m, u, n等）"""
        if value == 0:
            return "0"
        
        abs_value = abs(value)
        
        # 找到合适的前缀
        for exp in sorted(self.ENGINEERING_PREFIXES.keys(), reverse=True):
            if abs_value >= exp:
                scaled_value = value / exp
                prefix = self.ENGINEERING_PREFIXES[exp]
                
                # 根据数值大小选择小数位数
                formatted_value = f"{scaled_value:.6f}".rstrip('0').rstrip('.')
                return f"{formatted_value}{prefix}"
        
        # 默认返回科学计数法
        return f"{value:.3e}"
    
    def parse_engineering_format(self, text):
        """解析工程计数格式为数值"""
        text = text.strip()
        
        if not text:
            raise ValueError("空字符串")
        
        # 检查是否有前缀
        for prefix, factor in self.PREFIX_TO_VALUE.items():
            if prefix and text.endswith(prefix):
                num_str = text[:-len(prefix)]
                return float(num_str) * factor
        
        # 如果没有前缀，直接转换
        return float(text)
    
    # ==================== 点操作方法 ====================
    
    def add_or_update_point(self):
        """添加或更新点"""
        if self.primary_selected_index is not None:
            self.update_point()
        else:
            self.add_point()

    def add_point(self):
        """添加新点"""
        try:
            time_str = self.time_entry.get()
            value_str = self.value_entry.get()
            
            if not time_str or not value_str:
                 messagebox.showwarning("提示", "请输入时间和数值！")
                 return

            time = self.parse_engineering_format(time_str)
            value = self.parse_engineering_format(value_str)
            
            if time < 0:
                messagebox.showerror("错误", "时间不能为负数！")
                return
            
            if self._check_time_conflict(time):
                messagebox.showerror("错误", "该时间点已存在！")
                return
            
            self.points.append((time, value))
            self.points.sort()
            
            # 选中新添加的点
            idx = self.points.index((time, value))
            self.primary_selected_index = idx
            self.selected_indices = {idx}
            
            self._refresh_all()
            # self._clear_entries() # 保持输入框内容，方便微调
            
        except ValueError:
            messagebox.showerror("错误", "请输入有效的数字！")
    
    def quick_add_point(self):
        """快速添加点"""
        if not self.points:
            time, value = 0.0, 0.0
        else:
            last_time, _ = self.points[-1]
            
            # 默认间隔 1ms
            time_diff = 1e-3
            
            time = last_time + time_diff
            value = 0.0
        
        self.points.append((time, value))
        self.points.sort()
        
        idx = self.points.index((time, value))
        self.primary_selected_index = idx
        self.selected_indices = {idx}
        
        self._refresh_all()
    
    def delete_point(self):
        """删除选中的点"""
        if not self.selected_indices:
            # 尝试从Treeview获取选择（兼容性）
            selected_items = self.tree.selection()
            if selected_items:
                self.selected_indices = {self.tree.index(item) for item in selected_items}
            else:
                messagebox.showwarning("警告", "请先选择点！")
                return
        
        # Sort indices in reverse order to delete safely
        for index in sorted(self.selected_indices, reverse=True):
            if 0 <= index < len(self.points):
                del self.points[index]
        
        self.selected_indices = set()
        self.primary_selected_index = None
        
        self._refresh_all()
        self._clear_entries()
    
    def clear_points(self):
        """清除所有点"""
        if messagebox.askyesno("确认", "确定要清除所有点吗？"):
            self.points = []
            self.selected_indices = set()
            self.primary_selected_index = None
            self._refresh_all()
            self._clear_entries()
    
    def update_point(self):
        """更新选中的点"""
        if self.primary_selected_index is None:
            messagebox.showwarning("警告", "请先选择一个点！")
            return
        
        try:
            new_time = self.parse_engineering_format(self.time_entry.get())
            new_value = self.parse_engineering_format(self.value_entry.get())
            
            if new_time < 0:
                messagebox.showerror("错误", "时间不能为负数！")
                return
            
            index = self.primary_selected_index
            if not (0 <= index < len(self.points)):
                return
                
            old_time = self.points[index][0]
            
            if new_time != old_time and self._check_time_conflict(new_time, index):
                messagebox.showerror("错误", "该时间点已存在！")
                return
            
            self.points[index] = (new_time, new_value)
            self.points.sort()
            
            # 更新选中点索引
            new_idx = self.points.index((new_time, new_value))
            self.primary_selected_index = new_idx
            self.selected_indices = {new_idx}
            
            self._refresh_all()
            
        except ValueError:
            messagebox.showerror("错误", "请输入有效的数字！")
    
    # ==================== 界面更新方法 ====================
    
    def _update_table(self):
        """更新表格显示"""
        # 清空表格
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        self.tree_item_ids = []
        
        # 添加所有点
        for time, value in self.points:
            item_id = self.tree.insert("", tk.END, values=(
                self.engineering_format(time),
                self.engineering_format(value)
            ))
            self.tree_item_ids.append(item_id)
    
    def _update_plot(self, fast_update=False, cursor_only=False):
        """更新波形图 (Canvas Version)"""
        # Determine if we need to autoscale (first load)
        if not self.view_initialized and self.points:
            self.view_initialized = True
            self.zoom_to_all_points()
            return

        # Prepare data for canvas
        placement_line = []
        if self.placement_mode and self.placement_data:
             # Use current_cursor_pos if available, otherwise try to get it
             if not self.current_cursor_pos:
                  try:
                      px, py = self.root.winfo_pointerxy()
                      cx = px - self.canvas.winfo_rootx()
                      cy = py - self.canvas.winfo_rooty()
                      self.current_cursor_pos = self.canvas.screen_to_world(cx, cy)
                  except:
                      pass
                      
             if self.current_cursor_pos:
                start_t = max(0.0, self.current_cursor_pos[0])
                placement_line = [(start_t + t, v) for t, v in self.placement_data]
        
        placement_line = self._ensure_min_spacing(placement_line)
        
        # Optimization: specific update for cursor movement
        if cursor_only and self.placement_mode:
            self.canvas.update_cursor_only(
                placement_mode=True,
                placement_preview_line=placement_line
            )
            return

        # Box rect (already in screen coords if tracked that way, 
        # but if we are tracking box_start in screen coords in the new mouse handler, we are good)
        box_rect = None
        if self.box_mode in ('select', 'zoom') and hasattr(self, 'box_rect_screen'):
             box_rect = self.box_rect_screen

        self.canvas.redraw(
            points=self.points,
            selected_indices=self.selected_indices,
            placement_mode=self.placement_mode,
            placement_preview_line=placement_line,
            box_rect=box_rect
        )

        # Update Y-axis entries from canvas view
        self.y_min_entry.delete(0, tk.END)
        self.y_min_entry.insert(0, f"{self.canvas.y_min:.4f}")
        self.y_max_entry.delete(0, tk.END)
        self.y_max_entry.insert(0, f"{self.canvas.y_max:.4f}")
        
    def zoom_to_all_points(self, event=None):
        """缩放到显示所有点"""
        if not self.points:
            return
        
        times = [p[0] for p in self.points]
        values = [p[1] for p in self.points]
        
        all_x = times + [0]
        x_min, x_max = min(all_x), max(all_x)
        y_min, y_max = min(values), max(values)
        
        x_range = x_max - x_min if x_max > x_min else max(abs(x_max), 1.0)
        y_range = y_max - y_min if y_max > y_min else max(abs(y_max), 1.0)
        
        x_padding = x_range * 0.05
        y_padding = y_range * 0.1
        
        self.canvas.x_min = x_min - x_padding
        self.canvas.x_max = x_max + x_padding
        self.canvas.y_min = y_min - y_padding
        self.canvas.y_max = y_max + y_padding
        self._enforce_negative_axis_limit()
        
        self._update_plot()

    def set_y_axis(self):
        """设置Y轴范围"""
        try:
            y_min = float(self.y_min_entry.get())
            y_max = float(self.y_max_entry.get())
            
            if y_min >= y_max:
                messagebox.showerror("错误", "Y轴最小值必须小于最大值！")
                return
            
            self.canvas.y_min = y_min
            self.canvas.y_max = y_max
            self.zoom_fixed = True
            self._update_plot()
            
        except ValueError:
            messagebox.showerror("错误", "请输入有效的数字！")
    
    def _update_pwl_text(self):
        """更新PWL文本输出"""
        if not hasattr(self, 'pwl_text'):
            return
        
        self.pwl_text.configure(state="normal")
        self.pwl_text.delete(1.0, tk.END)
        
        if self.points:
            lines = ["PWL("]
            for i, (time, value) in enumerate(self.points):
                time_str = self.engineering_format(time)
                value_str = self.engineering_format(value)
                separator = "," if i < len(self.points) - 1 else ""
                lines.append(f"    {time_str} {value_str}{separator}")
            lines.append(")")
            
            self.pwl_text.insert(1.0, "\n".join(lines))
        
        self.pwl_text.configure(state="disabled")
    
    # ==================== 事件处理方法 ====================
    
    def _on_tree_select(self, event):
        """表格选中事件"""
        selected_items = self.tree.selection()
        self.selected_indices = set()
        
        if selected_items:
            for item in selected_items:
                index = self.tree.index(item)
                self.selected_indices.add(index)
            
            # Use the last one as primary
            last_index = self.tree.index(selected_items[-1])
            self.primary_selected_index = last_index
            
            time, value = self.points[last_index]
            self._set_entries(time, value)
            self._update_plot()
        else:
            self.primary_selected_index = None
            self._update_plot()
    
    def _on_tree_double_click(self, event):
        """表格双击事件 - 内联编辑"""
        region = self.tree.identify("region", event.x, event.y)
        if region != "cell":
            return
            
        column = self.tree.identify_column(event.x)
        row_id = self.tree.identify_row(event.y)
        
        if not row_id:
            return
            
        # Get column index (1 for time, 2 for value)
        col_idx = int(column.replace('#', '')) - 1
        
        # Get current value
        values = self.tree.item(row_id, 'values')
        current_val = values[col_idx]
        
        # Get cell coordinates
        x, y, width, height = self.tree.bbox(row_id, column)
        
        # Create entry
        entry = ttk.Entry(self.tree, width=width)
        entry.place(x=x, y=y, width=width, height=height)
        entry.insert(0, current_val)
        entry.select_range(0, tk.END)
        entry.focus()
        
        def save_edit(event=None):
            try:
                new_text = entry.get()
                new_val = self.parse_engineering_format(new_text)
                
                # Get point index
                point_index = self.tree.index(row_id)
                
                time, value = self.points[point_index]
                
                if col_idx == 0: # Editing Time
                    if new_val < 0:
                        messagebox.showerror("错误", "时间不能为负数！")
                        entry.destroy()
                        return
                    if new_val != time:
                        if self._check_time_conflict(new_val, point_index):
                            messagebox.showerror("错误", "该时间点已存在！")
                            entry.destroy()
                            return
                        time = new_val
                else: # Editing Value
                    value = new_val
                
                self.points[point_index] = (time, value)
                self.points.sort()
                
                new_idx = self.points.index((time, value))
                self.primary_selected_index = new_idx
                self.selected_indices = {new_idx}
                
                self._refresh_all()
                entry.destroy()
                
            except ValueError:
                messagebox.showerror("错误", "无效的数值格式")
                entry.destroy()
                
        def cancel_edit(event=None):
            entry.destroy()
            
        entry.bind('<Return>', save_edit)
        entry.bind('<FocusOut>', cancel_edit)
        entry.bind('<Escape>', cancel_edit)

    def _on_precision_change(self, event):
        """精度选择变化事件"""
        try:
            val_str = self.precision_var.get()
            if val_str == "1m":
                self.drag_precision = 1e-3
            else:
                self.drag_precision = float(val_str)
        except ValueError:
            self.drag_precision = self.DEFAULT_DRAG_PRECISION
    
    def _on_mouse_press(self, event):
        """鼠标按下事件"""
        self.canvas.focus_set()  # Ensure canvas has focus for keyboard events
        
        # Event coordinates are screen coordinates (pixels) relative to canvas
        sx, sy = event.x, event.y
        x, y = self.canvas.screen_to_world(sx, sy)
        self.current_cursor_pos = (x, y)
        
        # 1. Handle Placement Mode Click (Commit)
        if self.placement_mode and event.num == 1:
            self._handle_placement_commit(x)
            return
        
        # 2. Left Click (Button 1)
        if event.num == 1:
            self._handle_left_click(sx, sy, x, y)

        # 3. Right Click (Button 3) -> Box Zoom
        elif event.num == 3:
            self.box_mode = 'zoom'
            self.box_start = (sx, sy)
            self.box_rect_screen = None
            
        # 4. Middle Click (Button 2) -> Pan View
        elif event.num == 2:
            self.panning = True
            self.pan_start = (sx, sy)
            self.pan_start_view = (self.canvas.x_min, self.canvas.x_max, self.canvas.y_min, self.canvas.y_max)
            self.root.config(cursor="fleur")

    def _handle_placement_commit(self, x):
        """处理放置模式下的点击确认"""
        if not self.placement_data:
            self._cancel_placement()
            return
            
        # Commit placement
        start_time = max(0.0, x)
        
        # Add points
        new_points = [(start_time + t, v) for t, v in self.placement_data]
        
        self.points.extend(new_points)
        self.points.sort()
        
        # Select new points
        self.selected_indices = set()
        for pt in new_points:
            try:
                idx = self.points.index(pt)
                self.selected_indices.add(idx)
            except:
                pass
        
        if self.selected_indices:
            self.primary_selected_index = list(self.selected_indices)[-1]
        
        self._cancel_placement() # Exit mode
        self._refresh_all()

    def _handle_left_click(self, sx, sy, wx, wy):
        """处理左键点击（选择/拖动/框选）"""
        # Check if clicking on a point
        closest_point = None
        pixel_threshold = 10 
        min_dist_sq = pixel_threshold ** 2
        
        if self.points:
            for i, (px, py) in enumerate(self.points):
                psx, psy = self.canvas.world_to_screen(px, py)
                dist_sq = (sx - psx)**2 + (sy - psy)**2
                
                if dist_sq < min_dist_sq:
                    min_dist_sq = dist_sq
                    closest_point = i
        
        if closest_point is not None:
            # Clicked on a point
            if closest_point not in self.selected_indices:
                    # If clicked point not in selection, select ONLY this point
                    self.selected_indices = {closest_point}
                    self.primary_selected_index = closest_point
                    
                    # Sync tree selection (optimized)
                    if self.tree_item_ids:
                        sel = self.tree.selection()
                        if sel:
                            self.tree.selection_remove(sel)
                        if closest_point < len(self.tree_item_ids):
                            item_id = self.tree_item_ids[closest_point]
                            self.tree.selection_set(item_id)
                            self.tree.see(item_id)

            # Initiate Drag for ALL selected points
            self.dragging_indices = list(self.selected_indices)
            self.drag_start = (wx, wy) # World coords
            self.drag_original_data = {i: self.points[i] for i in self.dragging_indices}
            
            # Update primary selected if needed
            self.primary_selected_index = closest_point
            time, value = self.points[closest_point]
            self._set_entries(time, value)
            
            self._update_plot(fast_update=True)
        else:
            # Clicked on empty space -> Start Box Select
            self.box_mode = 'select'
            self.box_start = (sx, sy) # Screen coords for box
            self.box_rect_screen = None
            
            # Clear selection
            self.selected_indices = set()
            self.primary_selected_index = None
            if self.tree.selection():
                self.tree.selection_remove(self.tree.selection())
                
            self._update_plot(fast_update=True)
    
    def _on_mouse_release(self, event):
        """鼠标释放事件"""
        # Handle Pan Release
        if self.panning:
            self.panning = False
            self.pan_start = None
            self.root.config(cursor="")
            
            # Sync Y-axis entries
            self.y_min_entry.delete(0, tk.END)
            self.y_min_entry.insert(0, f"{self.canvas.y_min:.4f}")
            self.y_max_entry.delete(0, tk.END)
            self.y_max_entry.insert(0, f"{self.canvas.y_max:.4f}")
            return

        # Handle Drag Release
        if self.dragging_indices:
            # Apply precision to all dragged points
            for i in self.dragging_indices:
                if 0 <= i < len(self.points):
                    time, value = self.points[i]
                    time = round(time / self.TIME_MIN_PRECISION) * self.TIME_MIN_PRECISION
                    time = max(0.0, time)
                    value = round(value / self.drag_precision) * self.drag_precision
                    self.points[i] = (time, value)
            # Enforce min dt for dragged points based on neighbors (do not move non-drag points)
            self._enforce_min_dt_for_drag(self.dragging_indices)
            
            # Get values of dragged points to re-find them
            dragged_values = [self.points[i] for i in self.dragging_indices if 0 <= i < len(self.points)]
            
            # Sort points
            self.points.sort()
            
            # Re-find indices
            self.selected_indices = set()
            for val in dragged_values:
                try:
                    idx = self.points.index(val)
                    self.selected_indices.add(idx)
                except ValueError:
                    pass
            
            if self.selected_indices:
                 self.primary_selected_index = list(self.selected_indices)[-1]
            else:
                 self.primary_selected_index = None
            
            self._refresh_all()
            self.dragging_indices = []
            self.drag_start = None
            self.drag_original_data = {}

        # Handle Box Selection/Zoom Release
        if self.box_mode == 'select':
             if self.box_start:
                 x0_s, y0_s = self.box_start
                 x1_s, y1_s = event.x, event.y
                 
                 # Convert screen box to world box for selection
                 wx0, wy0 = self.canvas.screen_to_world(x0_s, y0_s)
                 wx1, wy1 = self.canvas.screen_to_world(x1_s, y1_s)
                 
                 x_min, x_max = sorted([wx0, wx1])
                 y_min, y_max = sorted([wy0, wy1])
                 
                 self.selected_indices = set()
                 for i, (px, py) in enumerate(self.points):
                     if x_min <= px <= x_max and y_min <= py <= y_max:
                         self.selected_indices.add(i)
                 
                 if self.selected_indices:
                     self.primary_selected_index = list(self.selected_indices)[-1]
                     if self.tree.get_children():
                        for item in self.tree.selection():
                            self.tree.selection_remove(item)
                        for idx in self.selected_indices:
                            if idx < len(self.tree.get_children()):
                                self.tree.selection_add(self.tree.get_children()[idx])
                 
                 self.box_rect_screen = None
                 self._update_plot()
        
        elif self.box_mode == 'zoom':
             if self.box_start:
                 x0_s, y0_s = self.box_start
                 x1_s, y1_s = event.x, event.y
                 
                 if abs(x0_s - x1_s) > 5 and abs(y0_s - y1_s) > 5:
                     wx0, wy0 = self.canvas.screen_to_world(x0_s, y0_s)
                     wx1, wy1 = self.canvas.screen_to_world(x1_s, y1_s)
                     
                     self.canvas.x_min = min(wx0, wx1)
                     self.canvas.x_max = max(wx0, wx1)
                     self.canvas.y_min = min(wy0, wy1)
                     self.canvas.y_max = max(wy0, wy1)
                     self._enforce_negative_axis_limit()
                     
                     self.zoom_fixed = True
                     self.y_min_entry.delete(0, tk.END)
                     self.y_min_entry.insert(0, f"{self.canvas.y_min:.4f}")
                     self.y_max_entry.delete(0, tk.END)
                     self.y_max_entry.insert(0, f"{self.canvas.y_max:.4f}")
                 
                 self.box_rect_screen = None
                 self._update_plot()

        self.box_mode = None
        self.box_start = None
    
    def _on_mouse_motion(self, event):
        """鼠标移动事件"""
        # Track cursor
        sx, sy = event.x, event.y
        wx, wy = self.canvas.screen_to_world(sx, sy)
        self.current_cursor_pos = (wx, wy)
        
        # Handle Panning (Middle Click)
        if self.panning and self.pan_start:
             dx_pixels = sx - self.pan_start[0]
             dy_pixels = sy - self.pan_start[1]
             
             if dx_pixels == 0 and dy_pixels == 0:
                 return
             
             x_min_orig, x_max_orig, y_min_orig, y_max_orig = self.pan_start_view
             
             width_pixels = self.canvas.winfo_width()
             height_pixels = self.canvas.winfo_height()
             
             width_data = x_max_orig - x_min_orig
             height_data = y_max_orig - y_min_orig
             
             shift_x = -dx_pixels * (width_data / width_pixels)
             shift_y = dy_pixels * (height_data / height_pixels) # Inverted Y axis
             
             self.canvas.x_min = x_min_orig + shift_x
             self.canvas.x_max = x_max_orig + shift_x
             self.canvas.y_min = y_min_orig + shift_y
             self.canvas.y_max = y_max_orig + shift_y
             self._enforce_negative_axis_limit()
             
             self._update_plot(fast_update=True)
             return

        # Handle Dragging
        if self.dragging_indices:
            dx = wx - self.drag_start[0]
            dy = wy - self.drag_start[1]
            
            for i in self.dragging_indices:
                if i in self.drag_original_data:
                    orig_t, orig_v = self.drag_original_data[i]
                    new_t = max(0.0, orig_t + dx)
                    new_v = orig_v + dy
                    if 0 <= i < len(self.points):
                        self.points[i] = (new_t, new_v)
            
            self._update_plot(fast_update=True)
            return
            
        # Handle Placement Mode
        if self.placement_mode:
            self._update_plot(fast_update=True, cursor_only=True)
            return

        # Handle Box Selection/Zoom Drawing
        if self.box_mode in ('select', 'zoom') and self.box_start:
             x0, y0 = self.box_start
             x1, y1 = sx, sy
             self.box_rect_screen = (x0, y0, x1, y1)
             self._update_plot(fast_update=True)
    
    def _on_mouse_scroll(self, event):
        """鼠标滚轮事件"""
        # Event coordinates
        sx, sy = event.x, event.y
        wx, wy = self.canvas.screen_to_world(sx, sy)
        
        # Determine direction
        if event.num == 4 or (hasattr(event, 'delta') and event.delta > 0):
            scale = 1 / self.ZOOM_FACTOR
        else:
            scale = self.ZOOM_FACTOR
            
        # Zoom centered on mouse
        x_min, x_max = self.canvas.x_min, self.canvas.x_max
        y_min, y_max = self.canvas.y_min, self.canvas.y_max
        
        is_ctrl = (event.state & 0x4) != 0
        is_shift = (event.state & 0x1) != 0
        
        if is_ctrl: # Ctrl: Zoom XY
            new_x_min = wx - (wx - x_min) * scale
            new_x_max = wx + (x_max - wx) * scale
            new_y_min = wy - (wy - y_min) * scale
            new_y_max = wy + (y_max - wy) * scale
            
            self.canvas.x_min = new_x_min
            self.canvas.x_max = new_x_max
            self._enforce_negative_axis_limit()
            self.canvas.y_min = new_y_min
            self.canvas.y_max = new_y_max
            
        elif is_shift: # Shift: Zoom X
            new_x_min = wx - (wx - x_min) * scale
            new_x_max = wx + (x_max - wx) * scale
            self.canvas.x_min = new_x_min
            self.canvas.x_max = new_x_max
            self._enforce_negative_axis_limit()
            
        else: # Default: Zoom Y
            new_y_min = wy - (wy - y_min) * scale
            new_y_max = wy + (y_max - wy) * scale
            self.canvas.y_min = new_y_min
            self.canvas.y_max = new_y_max
        
        self.zoom_fixed = True
        self._update_plot(fast_update=True)
    
    # ==================== 其他功能方法 ====================
    
    def copy_pwl(self):
        """复制PWL文本到剪贴板"""
        pwl_content = self.pwl_text.get(1.0, tk.END)
        if pwl_content.strip():
            pyperclip.copy(pwl_content)
            messagebox.showinfo("成功", "PWL文本已复制到剪贴板！")
        else:
            messagebox.showwarning("警告", "没有可复制的PWL文本！")
    
    def save_pwl(self):
        """保存PWL文本到文件"""
        pwl_content = self.pwl_text.get(1.0, tk.END)
        if not pwl_content.strip():
            messagebox.showwarning("警告", "没有可保存的PWL文本！")
            return
        
        file_path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            title="保存PWL文本"
        )
        
        if file_path:
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(pwl_content)
                messagebox.showinfo("成功", f"PWL文本已保存到 {file_path}！")
            except Exception as e:
                messagebox.showerror("错误", f"保存文件时发生错误：{str(e)}")
    
    def generate_example(self):
        """生成示例波形"""
        self.points = [
            (0.0, 0.0),
            (1.0, 1.0),
            (2.0, 0.5),
            (3.0, 2.0),
            (4.0, 0.0)
        ]
        self.selected_indices = set()
        self.primary_selected_index = None
        self._refresh_all()
        self.zoom_to_all_points()


def main():
    """主函数"""
    root = ctk.CTk()
    app = PWLEditor(root)
    root.mainloop()


if __name__ == "__main__":
    main()
