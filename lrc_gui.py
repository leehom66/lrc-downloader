#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
歌词批量下载器 - Windows 图形界面
=================================
选择音乐文件夹后，自动扫描其中（含所有子目录）的音乐文件，
批量搜索并下载同名 .lrc 歌词。

依赖: 仅 Python 标准库（tkinter）
运行: python lrc_gui.py
"""

import os
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from download_lrc import (download_for_file, iter_music_files,
                          FUZZY_THRESHOLD, MUSIC_EXTS)

APP_TITLE = "歌词批量下载器"
APP_VER = "v1.0"

# 配色（深色主题）
BG = "#1e1f22"
PANEL = "#2b2d31"
PANEL_HOVER = "#3a3d42"
FG = "#e6e6e6"
FG_DIM = "#9aa0a6"
ACCENT = "#3b82f6"
ACCENT_HOVER = "#2f6fd0"
OK_COLOR = "#4ade80"
FAIL_COLOR = "#f87171"
PURE_COLOR = "#60a5fa"
WARN_COLOR = "#fbbf24"

UI_FONT = ("Microsoft YaHei UI", 9)
LOG_FONT = ("Microsoft YaHei UI", 9)


class LrcDownloaderApp:
    def __init__(self, root):
        self.root = root
        self.folder = tk.StringVar()
        self.recursive = tk.BooleanVar(value=True)
        self.force = tk.BooleanVar(value=False)

        self.queue = queue.Queue()
        self.stop_event = threading.Event()
        self.worker = None
        self.stats = {"ok": 0, "instrumental": 0, "skip": 0, "fail": 0}
        self.total = 0

        self._setup_style()
        self._build_ui()
        self.root.after(100, self._poll_queue)

    # ------------------------------------------------------------ 界面构建
    def _setup_style(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(".", background=BG, foreground=FG, font=UI_FONT)
        style.configure("TFrame", background=BG)
        style.configure("Card.TFrame", background=PANEL)
        style.configure("TLabel", background=BG, foreground=FG, font=UI_FONT)
        style.configure("Dim.TLabel", background=BG, foreground=FG_DIM, font=UI_FONT)
        style.configure("Title.TLabel", background=BG, foreground=FG,
                        font=("Microsoft YaHei UI", 14, "bold"))
        style.configure("TCheckbutton", background=BG, foreground=FG, font=UI_FONT)
        style.map("TCheckbutton",
                  background=[("active", BG)],
                  foreground=[("active", FG)])
        style.configure("TButton", background=PANEL, foreground=FG, borderwidth=0,
                        padding=(12, 6), font=UI_FONT)
        style.map("TButton",
                  background=[("active", PANEL_HOVER), ("disabled", "#26282c")],
                  foreground=[("disabled", "#6b7076")])
        style.configure("Accent.TButton", background=ACCENT, foreground="#ffffff",
                        borderwidth=0, padding=(18, 7),
                        font=("Microsoft YaHei UI", 9, "bold"))
        style.map("Accent.TButton",
                  background=[("active", ACCENT_HOVER), ("disabled", "#34373c")],
                  foreground=[("disabled", "#7b8188")])
        style.configure("TEntry", fieldbackground=PANEL, foreground=FG,
                        insertcolor=FG, borderwidth=1, relief="flat")
        style.map("TEntry",
                  fieldbackground=[("readonly", PANEL)],
                  foreground=[("readonly", FG)])
        style.configure("Horizontal.TProgressbar", background=ACCENT,
                        troughcolor=PANEL, borderwidth=0, thickness=8)

    def _build_ui(self):
        root = self.root
        root.title(f"{APP_TITLE} {APP_VER}")
        root.geometry("860x620")
        root.minsize(720, 520)
        root.configure(bg=BG)

        pad = {"padx": 16}

        # ---- 标题区
        header = ttk.Frame(root)
        header.pack(fill="x", pady=(14, 8), **pad)
        ttk.Label(header, text=APP_TITLE, style="Title.TLabel").pack(side="left")
        ttk.Label(header, text="  批量搜索并下载音乐同名 .lrc 歌词（支持子目录）",
                  style="Dim.TLabel").pack(side="left", pady=(6, 0))

        # ---- 文件夹选择
        folder_box = ttk.Frame(root)
        folder_box.pack(fill="x", **pad)
        ttk.Label(folder_box, text="音乐文件夹").pack(side="left", padx=(0, 8))
        self.folder_entry = ttk.Entry(folder_box, textvariable=self.folder, state="readonly")
        self.folder_entry.pack(side="left", fill="x", expand=True, ipady=4)
        ttk.Button(folder_box, text="选择文件夹…", command=self.choose_folder).pack(
            side="left", padx=(8, 0))

        # ---- 选项
        opt = ttk.Frame(root)
        opt.pack(fill="x", pady=(10, 0), **pad)
        ttk.Checkbutton(opt, text="包含所有子文件夹", variable=self.recursive).pack(side="left")
        ttk.Checkbutton(opt, text="覆盖已存在的歌词", variable=self.force).pack(
            side="left", padx=(18, 0))
        ttk.Label(opt, text=f"模糊匹配阈值 {FUZZY_THRESHOLD}", style="Dim.TLabel").pack(
            side="right")

        # ---- 操作按钮
        actions = ttk.Frame(root)
        actions.pack(fill="x", pady=(12, 6), **pad)
        self.start_btn = ttk.Button(actions, text="开始下载", style="Accent.TButton",
                                    command=self.start)
        self.start_btn.pack(side="left")
        self.stop_btn = ttk.Button(actions, text="停止", command=self.stop, state="disabled")
        self.stop_btn.pack(side="left", padx=(8, 0))
        ttk.Button(actions, text="打开文件夹", command=self.open_folder).pack(
            side="left", padx=(8, 0))
        ttk.Button(actions, text="清空日志", command=self.clear_log).pack(side="left", padx=(8, 0))

        # ---- 进度
        prog = ttk.Frame(root)
        prog.pack(fill="x", pady=(2, 0), **pad)
        self.progress = ttk.Progressbar(prog, mode="determinate", maximum=100)
        self.progress.pack(fill="x", ipady=1)
        self.status_label = ttk.Label(
            prog, text="就绪 · 请选择音乐文件夹", style="Dim.TLabel")
        self.status_label.pack(anchor="w", pady=(6, 0))

        # ---- 日志区
        log_frame = ttk.Frame(root)
        log_frame.pack(fill="both", expand=True, pady=(8, 14), **pad)
        self.log = ScrolledText(
            log_frame, bg="#191a1d", fg="#d7d9dd", insertbackground=FG,
            relief="flat", borderwidth=0, font=LOG_FONT, wrap="word",
            padx=10, pady=8, spacing1=1, spacing3=2)
        self.log.pack(fill="both", expand=True)
        self.log.tag_config("ok", foreground=OK_COLOR)
        self.log.tag_config("okpath", foreground="#86efac")
        self.log.tag_config("fail", foreground=FAIL_COLOR)
        self.log.tag_config("pure", foreground=PURE_COLOR)
        self.log.tag_config("warn", foreground=WARN_COLOR)
        self.log.tag_config("dim", foreground="#7f858c")
        self.log.tag_config("head", foreground="#ffffff")
        self.log.tag_config("dir", foreground="#c084fc",
                            font=("Microsoft YaHei UI", 9, "bold"),
                            spacing1=6)
        self.log.tag_config("dirsum", foreground="#38bdf8")
        self.log.configure(state="disabled")

    # ------------------------------------------------------------ 交互动作
    def choose_folder(self):
        path = filedialog.askdirectory(title="选择包含音乐文件的文件夹")
        if path:
            self.folder.set(os.path.normpath(path))
            self._scan_preview()

    def open_folder(self):
        path = self.folder.get()
        if path and os.path.isdir(path):
            os.startfile(path)  # noqa: 仅 Windows
        else:
            messagebox.showinfo(APP_TITLE, "请先选择一个有效的文件夹。")

    def clear_log(self):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    def _scan_preview(self):
        path = self.folder.get()
        if not path:
            return
        try:
            n = len(iter_music_files(path, recursive=self.recursive.get()))
        except OSError as e:
            self.status_label.configure(text=f"扫描失败: {e}")
            return
        scope = "（含子目录）" if self.recursive.get() else "（不含子目录）"
        self.status_label.configure(text=f"已选择：找到 {n} 个音乐文件{scope}")
        self.progress.configure(value=0, maximum=max(n, 1))

    # ------------------------------------------------------------ 下载流程
    def start(self):
        path = self.folder.get()
        if not path or not os.path.isdir(path):
            messagebox.showwarning(APP_TITLE, "请先选择音乐文件夹。")
            return
        self.stats = {"ok": 0, "instrumental": 0, "skip": 0, "fail": 0}
        self.stop_event.clear()
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.progress.configure(value=0)
        self._log_line(f"开始处理：{path}", "head")
        self.status_label.configure(text="正在扫描文件…")

        self.worker = threading.Thread(
            target=self._run, args=(path, self.recursive.get(), self.force.get()),
            daemon=True)
        self.worker.start()

    def stop(self):
        self.stop_event.set()
        self.status_label.configure(text="正在停止…")
        self._log_line("已请求停止，当前文件完成后退出", "warn")

    def _run(self, path, recursive, force):
        """后台线程：扫描 + 按目录分组下载，实时把消息放进队列"""
        q = self.queue

        def emit(msg, tag=None):
            q.put(("log", msg, tag))

        # ---------- 1. 扫描（边扫边报进度） ----------
        files = []
        try:
            if os.path.isfile(path):
                files = [path]
            else:
                dirs_done = 0
                for root, dirs, names in os.walk(path):
                    if self.stop_event.is_set():
                        break
                    dirs[:] = sorted(d for d in dirs if not d.startswith("."))
                    dirs_done += 1
                    for n in sorted(names):
                        if os.path.splitext(n)[1].lower() in MUSIC_EXTS:
                            files.append(os.path.join(root, n))
                    if dirs_done % 20 == 0:
                        emit(f"  扫描中… 已遍历 {dirs_done} 个文件夹，找到 {len(files)} 个音乐文件", "dim")
                        q.put(("scan", len(files)))
                    if not recursive:
                        break
                if not recursive:
                    # 不递归时只取顶层目录
                    files = [f for f in files if os.path.dirname(f) == os.path.abspath(path)]
        except Exception as e:
            q.put(("done", {"error": str(e), "aborted": False}))
            return

        files = sorted(set(files))
        total = len(files)
        self.total = total
        q.put(("total", total))

        if self.stop_event.is_set():
            q.put(("log", "已停止（扫描阶段中断）", "warn"))
            q.put(("done", dict(self.stats, aborted=True)))
            return

        if total == 0:
            emit("未找到任何音乐文件", "warn")
            q.put(("done", dict(self.stats, aborted=False)))
            return

        scope = "（含子目录）" if recursive else "（不含子目录）"
        emit(f"扫描完成：共 {total} 个音乐文件{scope}", "head")

        # ---------- 2. 按目录分组 ----------
        groups = {}
        for f in files:
            groups.setdefault(os.path.dirname(f), []).append(f)
        dir_list = sorted(groups.keys())
        emit(f"共涉及 {len(dir_list)} 个文件夹，开始下载…", "head")
        emit("", "")

        done_count = 0
        for di, d in enumerate(dir_list, 1):
            if self.stop_event.is_set():
                break
            d_files = groups[d]
            emit(f"[目录 {di}/{len(dir_list)}] {d}（{len(d_files)} 首）", "dir")
            d_stats = {"ok": 0, "instrumental": 0, "skip": 0, "fail": 0}

            for f in d_files:
                if self.stop_event.is_set():
                    break
                done_count += 1
                name = os.path.splitext(os.path.basename(f))[0]
                q.put(("progress", (done_count - 1, total, name)))
                emit(f"  [{done_count}/{total}] {name}", "head")

                def log(msg, _q=q):
                    _q.put(("log", msg, None))

                try:
                    result = download_for_file(f, force=force, log=log)
                except Exception as e:
                    result = "fail"
                    emit(f"    ✗ 异常: {e}", "fail")

                d_stats[result] = d_stats.get(result, 0) + 1
                self.stats[result] = self.stats.get(result, 0) + 1
                q.put(("stats", dict(self.stats)))

                # 成功时明确输出歌词文件的完整路径
                if result == "ok":
                    lrc_path = os.path.splitext(f)[0] + ".lrc"
                    emit(f"    → 歌词文件：{lrc_path}", "okpath")
                elif result == "instrumental":
                    emit(f"    → 纯音乐，无歌词（{name}）", "pure")

            if self.stop_event.is_set() and done_count < total:
                emit(f"  （该目录未处理完：{d}）", "warn")
                break

            # 目录级汇总
            emit(f"  ── 本目录完成：成功 {d_stats['ok']} · 纯音乐 {d_stats['instrumental']}"
                 f" · 跳过 {d_stats['skip']} · 失败 {d_stats['fail']}", "dirsum")
            emit("", "")

        q.put(("progress", (done_count, total, "")))
        q.put(("done", dict(self.stats, aborted=self.stop_event.is_set(),
                            processed=done_count, total=total)))

    @staticmethod
    def _tag_of(msg):
        s = msg.strip()
        if s.startswith("✓"):
            return "ok"
        if s.startswith("✗"):
            return "fail"
        if s.startswith("○"):
            return "pure"
        if s.startswith("·"):
            return "dim"
        if s.startswith("→ 歌词文件"):
            return "okpath"
        if "已清理" in s:
            return "warn"
        return None

    # ------------------------------------------------------------ 队列轮询
    def _poll_queue(self):
        try:
            while True:
                item = self.queue.get_nowait()
                kind = item[0]
                payload = item[1] if len(item) > 1 else None
                if kind == "log":
                    tag = item[2] if len(item) > 2 and item[2] else (self._tag_of(payload) or "")
                    self._log_line(payload, tag)
                elif kind == "total":
                    self.progress.configure(maximum=max(payload, 1), value=0)
                elif kind == "scan":
                    self.status_label.configure(text=f"正在扫描子目录… 已找到 {payload} 个音乐文件")
                elif kind == "progress":
                    done, total, name = (list(payload) + ["", ""])[:3]
                    self.progress.configure(value=done, maximum=max(total, 1))
                    s = self.stats
                    self.status_label.configure(
                        text=(f"进度 {done}/{total} · 成功 {s['ok']} · 纯音乐 "
                              f"{s['instrumental']} · 跳过 {s['skip']} · 失败 {s['fail']}"
                              + (f" · 当前：{name}" if name else "")))
                elif kind == "stats":
                    self.stats = {**self.stats, **payload}
                elif kind == "done":
                    self._finish(payload)
        except queue.Empty:
            pass
        except Exception as e:  # 任何意外都不允许中断刷新循环
            self._log_line(f"[界面异常] {e}", "fail")

        # 让日志滚动到底部
        self.log.see("end")
        self.root.after(80, self._poll_queue)

    def _log_line(self, text, tag=""):
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n", tag)
        self.log.configure(state="disabled")
        self.log.see("end")

    def _finish(self, stats):
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        if "error" in stats:
            self.status_label.configure(text="扫描失败")
            messagebox.showerror(APP_TITLE, f"扫描文件夹失败：{stats['error']}")
            return

        aborted = stats.get("aborted")
        head = "已停止" if aborted else "全部完成"
        summary = (f"{head} · 成功 {stats.get('ok', 0)} · 纯音乐 {stats.get('instrumental', 0)}"
                   f" · 跳过 {stats.get('skip', 0)} · 失败 {stats.get('fail', 0)}")
        if "processed" in stats:
            summary += f" · 已处理 {stats.get('processed', 0)}/{stats.get('total', 0)}"

        self.status_label.configure(text=summary)
        self._log_line("═" * 46, "dim")
        self._log_line(("⏹ " if aborted else "✔ ") + summary, "head")
        if stats.get("instrumental"):
            self._log_line("（纯音乐没有歌词属正常情况，已自动跳过，不生成多余文件）", "pure")
        self.progress.configure(value=self.progress.cget("maximum"))

        body = summary.replace(" · ", "\n")
        if aborted:
            messagebox.showwarning(APP_TITLE, body)
        else:
            messagebox.showinfo(APP_TITLE, body)


def main():
    root = tk.Tk()
    try:
        # 高 DPI 适配，避免界面模糊
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    LrcDownloaderApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
