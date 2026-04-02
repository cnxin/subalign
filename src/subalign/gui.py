"""SubAlign GUI - 简易图形界面启动器。

基于 tkinter，无需额外依赖。
用法：python -m subalign.gui 或双击 start_gui.bat
"""

from __future__ import annotations

import subprocess
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk


class SubAlignGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("SubAlign - 字幕自动对齐工具 v0.1")
        self.root.geometry("780x700")
        self.root.resizable(True, True)

        self._build_ui()

    # ── UI 构建 ──────────────────────────────────────────────

    def _build_ui(self):
        # 文件选择区
        file_frame = ttk.LabelFrame(self.root, text="文件选择", padding=10)
        file_frame.pack(fill="x", padx=10, pady=(10, 5))

        # 视频
        ttk.Label(file_frame, text="视频文件:").grid(row=0, column=0, sticky="w")
        self.video_var = tk.StringVar()
        ttk.Entry(file_frame, textvariable=self.video_var, width=60).grid(row=0, column=1, padx=5)
        ttk.Button(file_frame, text="浏览...", command=self._browse_video).grid(row=0, column=2)

        # 主字幕
        ttk.Label(file_frame, text="字幕文件:").grid(row=1, column=0, sticky="w", pady=(5, 0))
        self.sub_var = tk.StringVar()
        ttk.Entry(file_frame, textvariable=self.sub_var, width=60).grid(row=1, column=1, padx=5, pady=(5, 0))
        ttk.Button(file_frame, text="浏览...", command=self._browse_sub).grid(row=1, column=2, pady=(5, 0))

        # 副语言字幕（双语用）
        ttk.Label(file_frame, text="副语言字幕:").grid(row=2, column=0, sticky="w", pady=(5, 0))
        self.sub2_var = tk.StringVar()
        ttk.Entry(file_frame, textvariable=self.sub2_var, width=60).grid(row=2, column=1, padx=5, pady=(5, 0))
        ttk.Button(file_frame, text="浏览...", command=self._browse_sub2).grid(row=2, column=2, pady=(5, 0))

        # 输出
        ttk.Label(file_frame, text="输出文件:").grid(row=3, column=0, sticky="w", pady=(5, 0))
        self.out_var = tk.StringVar()
        ttk.Entry(file_frame, textvariable=self.out_var, width=60).grid(row=3, column=1, padx=5, pady=(5, 0))
        ttk.Button(file_frame, text="浏览...", command=self._browse_output).grid(row=3, column=2, pady=(5, 0))

        # 场景选择区
        mode_frame = ttk.LabelFrame(self.root, text="选择操作", padding=10)
        mode_frame.pack(fill="x", padx=10, pady=5)

        self.mode_var = tk.StringVar(value="auto")
        modes = [
            ("auto", "自动检测 — 让工具自己判断该怎么做（推荐新手用这个）"),
            ("sync", "重新对齐 [S2] — 字幕有时间轴但和视频对不上"),
            ("align", "全量打轴 [S3] — 字幕只有文本没有时间轴，或缺了一部分"),
            ("snap", "帧对齐 [S4] — OP/ED 字幕要卡画面帧"),
            ("bilingual", "双语对齐 [S5] — 两种语言的字幕合在一起"),
            ("split-bd", "BD分集 [S6] — 多集 BD 视频自动识别集数"),
        ]
        for i, (val, text) in enumerate(modes):
            ttk.Radiobutton(mode_frame, text=text, variable=self.mode_var, value=val).grid(
                row=i, column=0, sticky="w", pady=1,
            )

        # 参数区
        param_frame = ttk.LabelFrame(self.root, text="参数设置", padding=10)
        param_frame.pack(fill="x", padx=10, pady=5)

        # 语言
        ttk.Label(param_frame, text="语言:").grid(row=0, column=0, sticky="w")
        self.lang_var = tk.StringVar(value="auto")
        lang_combo = ttk.Combobox(param_frame, textvariable=self.lang_var, width=10,
                                  values=["auto", "ja", "en", "zh"])
        lang_combo.grid(row=0, column=1, padx=5, sticky="w")

        # 模型
        ttk.Label(param_frame, text="模型:").grid(row=0, column=2, padx=(20, 0), sticky="w")
        self.model_var = tk.StringVar(value="medium")
        model_combo = ttk.Combobox(param_frame, textvariable=self.model_var, width=10,
                                   values=["tiny", "base", "small", "medium", "large-v3"])
        model_combo.grid(row=0, column=3, padx=5, sticky="w")

        # 设备
        ttk.Label(param_frame, text="设备:").grid(row=0, column=4, padx=(20, 0), sticky="w")
        self.device_var = tk.StringVar(value="auto")
        device_combo = ttk.Combobox(param_frame, textvariable=self.device_var, width=8,
                                    values=["auto", "cuda", "cpu"])
        device_combo.grid(row=0, column=5, padx=5, sticky="w")

        # 双语样式
        ttk.Label(param_frame, text="双语样式:").grid(row=1, column=0, sticky="w", pady=(5, 0))
        self.bilingual_style_var = tk.StringVar(value="split")
        bi_combo = ttk.Combobox(param_frame, textvariable=self.bilingual_style_var, width=10,
                                values=["split", "merged", "comment"])
        bi_combo.grid(row=1, column=1, padx=5, sticky="w", pady=(5, 0))

        ttk.Label(param_frame, text="主语言:").grid(row=1, column=2, padx=(20, 0), sticky="w", pady=(5, 0))
        self.pri_lang_var = tk.StringVar(value="ja")
        ttk.Entry(param_frame, textvariable=self.pri_lang_var, width=5).grid(row=1, column=3, sticky="w", pady=(5, 0))

        ttk.Label(param_frame, text="副语言:").grid(row=1, column=4, padx=(20, 0), sticky="w", pady=(5, 0))
        self.sec_lang_var = tk.StringVar(value="zh")
        ttk.Entry(param_frame, textvariable=self.sec_lang_var, width=5).grid(row=1, column=5, sticky="w", pady=(5, 0))

        # 检测缺失
        self.detect_missing_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(param_frame, text="检测缺失字幕段落", variable=self.detect_missing_var).grid(
            row=2, column=0, columnspan=3, sticky="w", pady=(5, 0),
        )

        # 执行按钮
        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(fill="x", padx=10, pady=5)

        self.run_btn = ttk.Button(btn_frame, text="▶  开始执行", command=self._run)
        self.run_btn.pack(side="left", padx=(0, 10))

        self.open_btn = ttk.Button(btn_frame, text="📂 打开输出目录", command=self._open_output_dir)
        self.open_btn.pack(side="left")

        self.progress = ttk.Progressbar(btn_frame, mode="indeterminate", length=200)
        self.progress.pack(side="right")

        # 日志区
        log_frame = ttk.LabelFrame(self.root, text="运行日志", padding=5)
        log_frame.pack(fill="both", expand=True, padx=10, pady=(5, 10))

        self.log_text = scrolledtext.ScrolledText(log_frame, height=12, font=("Consolas", 9))
        self.log_text.pack(fill="both", expand=True)

    # ── 文件浏览 ─────────────────────────────────────────────

    def _browse_video(self):
        path = filedialog.askopenfilename(
            title="选择视频文件",
            filetypes=[
                ("视频文件", "*.mkv *.mp4 *.m2ts *.avi *.webm"),
                ("所有文件", "*.*"),
            ],
        )
        if path:
            self.video_var.set(path)
            if not self.out_var.get():
                self.out_var.set(str(Path(path).with_suffix(".aligned.ass")))

    def _browse_sub(self):
        path = filedialog.askopenfilename(
            title="选择字幕文件",
            filetypes=[
                ("字幕文件", "*.ass *.ssa *.srt *.vtt *.txt"),
                ("所有文件", "*.*"),
            ],
        )
        if path:
            self.sub_var.set(path)

    def _browse_sub2(self):
        path = filedialog.askopenfilename(
            title="选择副语言字幕文件",
            filetypes=[
                ("字幕文件", "*.ass *.ssa *.srt *.vtt *.txt"),
                ("所有文件", "*.*"),
            ],
        )
        if path:
            self.sub2_var.set(path)

    def _browse_output(self):
        path = filedialog.asksaveasfilename(
            title="保存输出文件",
            defaultextension=".ass",
            filetypes=[("ASS 字幕", "*.ass"), ("SRT 字幕", "*.srt")],
        )
        if path:
            self.out_var.set(path)

    def _open_output_dir(self):
        out = self.out_var.get()
        if out:
            folder = str(Path(out).parent)
            subprocess.Popen(["explorer", folder])

    # ── 执行 ─────────────────────────────────────────────────

    def _log(self, msg: str):
        self.log_text.insert("end", msg + "\n")
        self.log_text.see("end")

    def _build_command(self) -> list[str]:
        mode = self.mode_var.get()
        video = self.video_var.get()
        sub = self.sub_var.get()
        out = self.out_var.get()
        lang = self.lang_var.get()
        model = self.model_var.get()
        device = self.device_var.get()

        if not video:
            raise ValueError("请选择视频文件")
        if not out:
            raise ValueError("请指定输出文件路径")

        # Global options
        cmd = ["subalign"]
        if lang != "auto":
            cmd.extend(["--lang", lang])
        cmd.extend(["--model", model, "--device", device])

        if mode == "auto":
            if not sub:
                raise ValueError("请选择字幕文件")
            cmd.extend(["auto", video, sub, "-o", out])

        elif mode == "sync":
            if not sub:
                raise ValueError("请选择字幕文件")
            cmd.extend(["sync", video, sub, "-o", out])

        elif mode == "align":
            if not sub:
                raise ValueError("请选择字幕文件")
            cmd.extend(["align", video, sub, "-o", out])
            if self.detect_missing_var.get():
                cmd.append("--detect-missing")

        elif mode == "snap":
            if not sub:
                raise ValueError("请选择字幕文件")
            cmd.extend(["snap", video, sub, "-o", out])

        elif mode == "bilingual":
            sub2 = self.sub2_var.get()
            if not sub:
                raise ValueError("请选择主语言字幕文件")
            if not sub2:
                raise ValueError("请选择副语言字幕文件")
            cmd.extend([
                "bilingual", video,
                "--primary", sub,
                "--secondary", sub2,
                "--primary-lang", self.pri_lang_var.get(),
                "--secondary-lang", self.sec_lang_var.get(),
                "--bilingual-style", self.bilingual_style_var.get(),
                "-o", out,
            ])

        elif mode == "split-bd":
            cmd.extend(["split-bd", video, "--detect-only"])

        return cmd

    def _run(self):
        try:
            cmd = self._build_command()
        except ValueError as e:
            messagebox.showerror("参数错误", str(e))
            return

        self.log_text.delete("1.0", "end")
        self._log(f">>> {' '.join(cmd)}")
        self._log("")

        self.run_btn.configure(state="disabled")
        self.progress.start(10)

        def worker():
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=3600,
                )
                self.root.after(0, lambda: self._on_done(result))
            except subprocess.TimeoutExpired:
                self.root.after(0, lambda: self._on_error("执行超时（超过1小时）"))
            except FileNotFoundError:
                self.root.after(0, lambda: self._on_error(
                    "找不到 subalign 命令。\n请先运行 install.bat 安装。"
                ))
            except Exception as e:
                self.root.after(0, lambda: self._on_error(str(e)))

        threading.Thread(target=worker, daemon=True).start()

    def _on_done(self, result: subprocess.CompletedProcess):
        self.progress.stop()
        self.run_btn.configure(state="normal")

        if result.stdout:
            self._log(result.stdout)
        if result.stderr:
            self._log(result.stderr)

        if result.returncode == 0:
            self._log("\n✓ 完成！")
            out = self.out_var.get()
            if out and Path(out).exists():
                self._log(f"输出文件: {out}")
                if messagebox.askyesno("完成", f"对齐完成！\n\n是否用 Aegisub 打开结果？\n{out}"):
                    try:
                        subprocess.Popen(["aegisub32", out])
                    except FileNotFoundError:
                        try:
                            subprocess.Popen(["aegisub", out])
                        except FileNotFoundError:
                            subprocess.Popen(["explorer", out])
        else:
            self._log(f"\n✗ 执行失败 (退出码 {result.returncode})")

    def _on_error(self, msg: str):
        self.progress.stop()
        self.run_btn.configure(state="normal")
        self._log(f"\n✗ 错误: {msg}")
        messagebox.showerror("错误", msg)

    # ── 启动 ─────────────────────────────────────────────────

    def run(self):
        self.root.mainloop()


def main():
    app = SubAlignGUI()
    app.run()


if __name__ == "__main__":
    main()
