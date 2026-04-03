"""SubAlign GUI - 简易图形界面启动器。

基于 tkinter，无需额外依赖。
用法：python -m subalign.gui 或双击 start_gui.bat
"""

from __future__ import annotations

import json
import subprocess
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk


LANG_TO_CODE = {"自动检测": "auto", "日语": "ja", "英语": "en", "中文": "zh", "韩语": "ko"}
CODE_TO_LANG = {v: k for k, v in LANG_TO_CODE.items()}
MODEL_TO_CODE = {
    "极速 (tiny)": "tiny", "基础 (base)": "base", "标准 (small)": "small",
    "推荐 (medium)": "medium", "最佳 (large-v3)": "large-v3",
}
DEVICE_TO_CODE = {"自动": "auto", "显卡 (CUDA)": "cuda", "CPU": "cpu"}
STYLE_TO_CODE = {"分离显示": "split", "合并双行": "merged", "仅注释": "comment"}
BACKEND_TO_CODE = {"本地模型": "local", "OpenAI API": "openai"}
CODE_TO_BACKEND = {v: k for k, v in BACKEND_TO_CODE.items()}


# ── 设置弹窗 ────────────────────────────────────────────

class SettingsDialog:
    """API Key 和偏好设置弹窗。"""

    def __init__(self, parent):
        self.win = tk.Toplevel(parent)
        self.win.title("设置 - API 配置")
        self.win.geometry("520x420")
        self.win.resizable(False, False)
        self.win.grab_set()

        self._load_config()
        self._build_ui()

    def _load_config(self):
        try:
            from subalign.models.config import load_user_config
            self.cfg = load_user_config()
        except Exception:
            self.cfg = {
                "asr_backend": "local",
                "openai_api_key": "", "openai_base_url": "", "openai_model": "whisper-1",
                "local_model": "medium", "local_device": "auto", "default_language": None,
            }

    def _build_ui(self):
        pad = {"padx": 10, "pady": 3}
        f = self.win

        # ── AI 引擎 ──
        ttk.Label(f, text="AI 语音识别引擎", font=("", 10, "bold")).pack(anchor="w", **pad)

        engine_frame = ttk.Frame(f)
        engine_frame.pack(fill="x", **pad)
        ttk.Label(engine_frame, text="引擎:").pack(side="left")
        self.backend_var = tk.StringVar(value=CODE_TO_BACKEND.get(self.cfg["asr_backend"], "本地模型"))
        ttk.Combobox(engine_frame, textvariable=self.backend_var, width=15,
                     values=list(BACKEND_TO_CODE.keys()), state="readonly").pack(side="left", padx=5)

        # ── OpenAI 设置 ──
        ttk.Separator(f, orient="horizontal").pack(fill="x", pady=5, padx=10)
        ttk.Label(f, text="OpenAI API 设置", font=("", 10, "bold")).pack(anchor="w", **pad)

        key_frame = ttk.Frame(f)
        key_frame.pack(fill="x", **pad)
        ttk.Label(key_frame, text="API Key:").pack(side="left")
        self.apikey_var = tk.StringVar(value=self.cfg.get("openai_api_key", ""))
        self.apikey_entry = ttk.Entry(key_frame, textvariable=self.apikey_var, width=45, show="*")
        self.apikey_entry.pack(side="left", padx=5)
        self.show_key = tk.BooleanVar(value=False)
        ttk.Checkbutton(key_frame, text="显示", variable=self.show_key,
                        command=self._toggle_key_visibility).pack(side="left")

        url_frame = ttk.Frame(f)
        url_frame.pack(fill="x", **pad)
        ttk.Label(url_frame, text="API 地址:").pack(side="left")
        self.baseurl_var = tk.StringVar(value=self.cfg.get("openai_base_url", ""))
        ttk.Entry(url_frame, textvariable=self.baseurl_var, width=45).pack(side="left", padx=5)

        ttk.Label(f, text="  留空=OpenAI官方，填自定义地址可兼容其他服务商",
                  foreground="gray").pack(anchor="w", padx=10)

        model_frame = ttk.Frame(f)
        model_frame.pack(fill="x", **pad)
        ttk.Label(model_frame, text="模型名:").pack(side="left")
        self.api_model_var = tk.StringVar(value=self.cfg.get("openai_model", "whisper-1"))
        ttk.Entry(model_frame, textvariable=self.api_model_var, width=20).pack(side="left", padx=5)

        # ── 默认偏好 ──
        ttk.Separator(f, orient="horizontal").pack(fill="x", pady=5, padx=10)
        ttk.Label(f, text="默认偏好", font=("", 10, "bold")).pack(anchor="w", **pad)

        pref_frame = ttk.Frame(f)
        pref_frame.pack(fill="x", **pad)
        ttk.Label(pref_frame, text="默认语言:").pack(side="left")
        cur_lang = CODE_TO_LANG.get(self.cfg.get("default_language") or "auto", "自动检测")
        self.def_lang_var = tk.StringVar(value=cur_lang)
        ttk.Combobox(pref_frame, textvariable=self.def_lang_var, width=10,
                     values=list(LANG_TO_CODE.keys()), state="readonly").pack(side="left", padx=5)

        # ── 按钮 ──
        btn_frame = ttk.Frame(f)
        btn_frame.pack(fill="x", padx=10, pady=15)
        ttk.Button(btn_frame, text="保存", command=self._save).pack(side="right", padx=5)
        ttk.Button(btn_frame, text="取消", command=self.win.destroy).pack(side="right")
        ttk.Button(btn_frame, text="测试连接", command=self._test_api).pack(side="left")

    def _toggle_key_visibility(self):
        self.apikey_entry.configure(show="" if self.show_key.get() else "*")

    def _test_api(self):
        key = self.apikey_var.get().strip()
        if not key:
            messagebox.showwarning("提示", "请先填写 API Key", parent=self.win)
            return
        try:
            from openai import OpenAI
            kwargs = {"api_key": key}
            url = self.baseurl_var.get().strip()
            if url:
                kwargs["base_url"] = url
            client = OpenAI(**kwargs)
            client.models.list()
            messagebox.showinfo("成功", "API 连接成功！", parent=self.win)
        except ImportError:
            messagebox.showerror("错误", "未安装 openai 库。\n请运行: pip install openai", parent=self.win)
        except Exception as e:
            messagebox.showerror("连接失败", f"API 连接失败:\n{e}", parent=self.win)

    def _save(self):
        try:
            from subalign.models.config import save_user_config
        except ImportError:
            messagebox.showerror("错误", "无法导入配置模块", parent=self.win)
            return

        self.cfg["asr_backend"] = BACKEND_TO_CODE.get(self.backend_var.get(), "local")
        self.cfg["openai_api_key"] = self.apikey_var.get().strip()
        self.cfg["openai_base_url"] = self.baseurl_var.get().strip()
        self.cfg["openai_model"] = self.api_model_var.get().strip() or "whisper-1"
        lang_code = LANG_TO_CODE.get(self.def_lang_var.get(), "auto")
        self.cfg["default_language"] = None if lang_code == "auto" else lang_code

        save_user_config(self.cfg)
        messagebox.showinfo("保存成功", "配置已保存", parent=self.win)
        self.win.destroy()


# ── 主界面 ──────────────────────────────────────────────

class SubAlignGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("SubAlign - 字幕自动对齐工具 v0.2")
        self.root.geometry("800x780")
        self.root.resizable(True, True)

        self._build_ui()

    def _build_ui(self):
        # ── 文件选择区 ──
        file_frame = ttk.LabelFrame(self.root, text="文件选择", padding=10)
        file_frame.pack(fill="x", padx=10, pady=(10, 5))
        file_frame.columnconfigure(1, weight=1)

        ttk.Label(file_frame, text="视频文件:").grid(row=0, column=0, sticky="w")
        self.video_var = tk.StringVar()
        ttk.Entry(file_frame, textvariable=self.video_var).grid(row=0, column=1, padx=5, sticky="ew")
        ttk.Button(file_frame, text="浏览...", command=self._browse_video).grid(row=0, column=2)

        ttk.Label(file_frame, text="字幕文件:").grid(row=1, column=0, sticky="w", pady=(5, 0))
        self.sub_var = tk.StringVar()
        ttk.Entry(file_frame, textvariable=self.sub_var).grid(row=1, column=1, padx=5, sticky="ew", pady=(5, 0))
        ttk.Button(file_frame, text="浏览...", command=self._browse_sub).grid(row=1, column=2, pady=(5, 0))

        ttk.Label(file_frame, text="副语言字幕:").grid(row=2, column=0, sticky="w", pady=(5, 0))
        self.sub2_var = tk.StringVar()
        ttk.Entry(file_frame, textvariable=self.sub2_var).grid(row=2, column=1, padx=5, sticky="ew", pady=(5, 0))
        ttk.Button(file_frame, text="浏览...", command=self._browse_sub2).grid(row=2, column=2, pady=(5, 0))

        ttk.Label(file_frame, text="输出文件:").grid(row=3, column=0, sticky="w", pady=(5, 0))
        self.out_var = tk.StringVar()
        ttk.Entry(file_frame, textvariable=self.out_var).grid(row=3, column=1, padx=5, sticky="ew", pady=(5, 0))
        ttk.Button(file_frame, text="浏览...", command=self._browse_output).grid(row=3, column=2, pady=(5, 0))

        # ── 场景选择区 ──
        mode_frame = ttk.LabelFrame(self.root, text="选择操作", padding=10)
        mode_frame.pack(fill="x", padx=10, pady=5)

        self.mode_var = tk.StringVar(value="auto")
        modes = [
            ("auto",      "自动检测 — 让工具自己判断（推荐）"),
            ("sync",      "重新对齐 — 字幕有时间轴但和视频对不上"),
            ("align",     "全量打轴 — 字幕只有文本没时间轴，或缺了一部分"),
            ("snap",      "帧对齐   — OP/ED 字幕要卡画面帧"),
            ("bilingual", "双语对齐 — 两种语言的字幕合在一起"),
            ("split-bd",  "BD 分集  — 多集 BD 视频自动识别集数"),
        ]
        for i, (val, text) in enumerate(modes):
            ttk.Radiobutton(mode_frame, text=text, variable=self.mode_var, value=val).grid(
                row=i, column=0, sticky="w", pady=1)

        # ── 参数设置区（两列布局）──
        param_frame = ttk.LabelFrame(self.root, text="参数设置", padding=10)
        param_frame.pack(fill="x", padx=10, pady=5)

        # Row 0: AI 引擎 + 语言
        r = 0
        ttk.Label(param_frame, text="AI 引擎:").grid(row=r, column=0, sticky="w")
        self.backend_var = tk.StringVar(value="本地模型")
        ttk.Combobox(param_frame, textvariable=self.backend_var, width=14,
                     values=list(BACKEND_TO_CODE.keys()), state="readonly"
                     ).grid(row=r, column=1, padx=5, sticky="w")
        ttk.Label(param_frame, text="语言:").grid(row=r, column=2, padx=(15, 0), sticky="w")
        self.lang_var = tk.StringVar(value="自动检测")
        ttk.Combobox(param_frame, textvariable=self.lang_var, width=10,
                     values=list(LANG_TO_CODE.keys()), state="readonly"
                     ).grid(row=r, column=3, padx=5, sticky="w")
        ttk.Button(param_frame, text="API 设置...", command=self._open_settings
                   ).grid(row=r, column=4, padx=(15, 0), sticky="e")

        # Row 1: 模型 + 设备
        r = 1
        ttk.Label(param_frame, text="模型:").grid(row=r, column=0, sticky="w", pady=(5, 0))
        self.model_var = tk.StringVar(value="推荐 (medium)")
        ttk.Combobox(param_frame, textvariable=self.model_var, width=14,
                     values=list(MODEL_TO_CODE.keys()), state="readonly"
                     ).grid(row=r, column=1, padx=5, sticky="w", pady=(5, 0))
        ttk.Label(param_frame, text="设备:").grid(row=r, column=2, padx=(15, 0), sticky="w", pady=(5, 0))
        self.device_var = tk.StringVar(value="自动")
        ttk.Combobox(param_frame, textvariable=self.device_var, width=10,
                     values=list(DEVICE_TO_CODE.keys()), state="readonly"
                     ).grid(row=r, column=3, padx=5, sticky="w", pady=(5, 0))

        # Row 2: 检测缺失
        r = 2
        self.detect_missing_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(param_frame, text="检测缺失字幕段落（全量打轴时，标记 ASR 发现但字幕缺少的部分）",
                        variable=self.detect_missing_var
                        ).grid(row=r, column=0, columnspan=5, sticky="w", pady=(8, 0))

        # Row 3: separator
        ttk.Separator(param_frame, orient="horizontal").grid(
            row=3, column=0, columnspan=5, sticky="ew", pady=8)

        # Row 4-5: 双语设置
        r = 4
        ttk.Label(param_frame, text="双语样式:").grid(row=r, column=0, sticky="w")
        self.bilingual_style_var = tk.StringVar(value="分离显示")
        ttk.Combobox(param_frame, textvariable=self.bilingual_style_var, width=14,
                     values=list(STYLE_TO_CODE.keys()), state="readonly"
                     ).grid(row=r, column=1, padx=5, sticky="w")
        ttk.Label(param_frame, text="主语言:").grid(row=r, column=2, padx=(15, 0), sticky="w")
        self.pri_lang_var = tk.StringVar(value="日语")
        ttk.Combobox(param_frame, textvariable=self.pri_lang_var, width=10,
                     values=["日语", "英语", "中文", "韩语"], state="readonly"
                     ).grid(row=r, column=3, padx=5, sticky="w")

        r = 5
        ttk.Label(param_frame, text="副语言:").grid(row=r, column=0, sticky="w", pady=(5, 0))
        self.sec_lang_var = tk.StringVar(value="中文")
        ttk.Combobox(param_frame, textvariable=self.sec_lang_var, width=14,
                     values=["中文", "日语", "英语", "韩语"], state="readonly"
                     ).grid(row=r, column=1, padx=5, sticky="w", pady=(5, 0))

        # ── 执行按钮 ──
        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(fill="x", padx=10, pady=5)

        self.run_btn = ttk.Button(btn_frame, text="  开始执行  ", command=self._run)
        self.run_btn.pack(side="left", padx=(0, 10))

        ttk.Button(btn_frame, text="打开输出目录", command=self._open_output_dir).pack(side="left")

        self.progress = ttk.Progressbar(btn_frame, mode="indeterminate", length=200)
        self.progress.pack(side="right")

        # ── 日志区 ──
        log_frame = ttk.LabelFrame(self.root, text="运行日志", padding=5)
        log_frame.pack(fill="both", expand=True, padx=10, pady=(5, 10))

        self.log_text = scrolledtext.ScrolledText(log_frame, height=10, font=("Consolas", 9))
        self.log_text.pack(fill="both", expand=True)

    # ── 设置弹窗 ──

    def _open_settings(self):
        SettingsDialog(self.root)

    # ── 文件浏览 ──

    def _browse_video(self):
        path = filedialog.askopenfilename(
            title="选择视频文件",
            filetypes=[("视频文件", "*.mkv *.mp4 *.m2ts *.avi *.webm"), ("所有文件", "*.*")])
        if path:
            self.video_var.set(path)
            if not self.out_var.get():
                self.out_var.set(str(Path(path).with_suffix(".aligned.ass")))

    def _browse_sub(self):
        path = filedialog.askopenfilename(
            title="选择字幕文件",
            filetypes=[("字幕文件", "*.ass *.ssa *.srt *.vtt *.txt"), ("所有文件", "*.*")])
        if path:
            self.sub_var.set(path)

    def _browse_sub2(self):
        path = filedialog.askopenfilename(
            title="选择副语言字幕文件",
            filetypes=[("字幕文件", "*.ass *.ssa *.srt *.vtt *.txt"), ("所有文件", "*.*")])
        if path:
            self.sub2_var.set(path)

    def _browse_output(self):
        path = filedialog.asksaveasfilename(
            title="保存输出文件", defaultextension=".ass",
            filetypes=[("ASS 字幕", "*.ass"), ("SRT 字幕", "*.srt")])
        if path:
            self.out_var.set(path)

    def _open_output_dir(self):
        out = self.out_var.get()
        if out:
            subprocess.Popen(["explorer", str(Path(out).parent)])

    # ── 构建命令 ──

    def _log(self, msg: str):
        self.log_text.insert("end", msg + "\n")
        self.log_text.see("end")

    def _build_command(self) -> list[str]:
        mode = self.mode_var.get()
        video = self.video_var.get()
        sub = self.sub_var.get()
        out = self.out_var.get()

        lang = LANG_TO_CODE.get(self.lang_var.get(), self.lang_var.get())
        model = MODEL_TO_CODE.get(self.model_var.get(), self.model_var.get())
        device = DEVICE_TO_CODE.get(self.device_var.get(), self.device_var.get())

        if not video:
            raise ValueError("请选择视频文件")
        if not out:
            raise ValueError("请指定输出文件路径")

        cmd = ["subalign"]
        if lang != "auto":
            cmd.extend(["--lang", lang])
        cmd.extend(["--model", model, "--device", device])

        if mode == "auto":
            if not sub: raise ValueError("请选择字幕文件")
            cmd.extend(["auto", video, sub, "-o", out])

        elif mode == "sync":
            if not sub: raise ValueError("请选择字幕文件")
            cmd.extend(["sync", video, sub, "-o", out])

        elif mode == "align":
            if not sub: raise ValueError("请选择字幕文件")
            cmd.extend(["align", video, sub, "-o", out])
            if self.detect_missing_var.get():
                cmd.append("--detect-missing")

        elif mode == "snap":
            if not sub: raise ValueError("请选择字幕文件")
            cmd.extend(["snap", video, sub, "-o", out])

        elif mode == "bilingual":
            sub2 = self.sub2_var.get()
            if not sub: raise ValueError("请选择主语言字幕文件")
            if not sub2: raise ValueError("请选择副语言字幕文件")
            cmd.extend([
                "bilingual", video,
                "--primary", sub, "--secondary", sub2,
                "--primary-lang", LANG_TO_CODE.get(self.pri_lang_var.get(), "ja"),
                "--secondary-lang", LANG_TO_CODE.get(self.sec_lang_var.get(), "zh"),
                "--bilingual-style", STYLE_TO_CODE.get(self.bilingual_style_var.get(), "split"),
                "-o", out,
            ])

        elif mode == "split-bd":
            cmd.extend(["split-bd", video, "--detect-only"])

        return cmd

    # ── 执行 ──

    def _run(self):
        try:
            cmd = self._build_command()
        except ValueError as e:
            messagebox.showerror("参数错误", str(e))
            return

        self.log_text.delete("1.0", "end")
        self._log(f">>> {' '.join(cmd)}\n")

        self.run_btn.configure(state="disabled")
        self.progress.start(10)

        def worker():
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
                self.root.after(0, lambda: self._on_done(result))
            except subprocess.TimeoutExpired:
                self.root.after(0, lambda: self._on_error("执行超时（超过1小时）"))
            except FileNotFoundError:
                self.root.after(0, lambda: self._on_error("找不到 subalign 命令。\n请先运行 install.bat 安装。"))
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
            self._log("\n--- 完成 ---")
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
            self._log(f"\n--- 执行失败 (退出码 {result.returncode}) ---")

    def _on_error(self, msg: str):
        self.progress.stop()
        self.run_btn.configure(state="normal")
        self._log(f"\n错误: {msg}")
        messagebox.showerror("错误", msg)

    def run(self):
        self.root.mainloop()


def main():
    app = SubAlignGUI()
    app.run()


if __name__ == "__main__":
    main()
