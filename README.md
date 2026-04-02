# SubAlign — AI 字幕自动对齐工具

有视频、有字幕文本，但是时间轴对不上？这个工具帮你自动搞定。

---

## 能做什么

简单说就是六件事：

```
你有什么                    → SubAlign 帮你做什么
─────────────────────────────────────────────────
字幕时间轴和视频对不上        → 自动校正（几秒钟搞定）
字幕只有文本没有时间轴        → AI 语音识别自动打轴
字幕缺了几句                → 自动找出缺失的地方
OP/ED 字幕要卡帧            → 自动吸附到关键帧
日语+中文要做双语字幕         → 自动对齐合并
BD光盘多集连在一起           → 自动识别每集开头结尾
```

---

## 第一步：安装

### 方法 A：一键安装（推荐）

1. 双击项目里的 **`install.bat`**
2. 它会自动检查 Python 和 ffmpeg，缺什么提示你装什么
3. 装完就能用了

### 方法 B：手动安装

如果一键脚本不好使，按这个顺序来：

**① 装 Python**（已经有的跳过）

去 https://www.python.org/downloads/ 下载安装，**安装时一定勾选 "Add Python to PATH"**。

装完打开命令提示符（Win+R 输入 cmd），输入：
```
python --version
```
能看到版本号就 OK。

**② 装 ffmpeg**（已经有的跳过）

最简单的方法 — 打开命令提示符输入：
```
winget install ffmpeg
```
或者去 https://www.gyan.dev/ffmpeg/builds/ 下载 `ffmpeg-release-essentials.zip`，解压后把里面 `bin` 文件夹的路径加到系统环境变量 PATH 里。

验证：
```
ffmpeg -version
```

**③ 装 SubAlign**

打开命令提示符，cd 到项目目录，然后：
```
cd D:\projects\subalign
pip install -e .
```

验证：
```
subalign --help
```

**④ 可选：装 GPU 加速**（有 NVIDIA 显卡才需要）

没装也能用，就是 AI 识别会慢一些（用 CPU 跑）。有显卡的话：
```
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu118
pip install whisperx
```

---

## 第二步：使用

### 用法 A：图形界面（推荐）

双击 **`start_gui.bat`** 打开界面：

```
┌─ SubAlign - 字幕自动对齐工具 ─────────────────────────┐
│                                                        │
│  视频文件:  [________________________] [浏览...]       │
│  字幕文件:  [________________________] [浏览...]       │
│  输出文件:  [________________________] [浏览...]       │
│                                                        │
│  选择操作:                                             │
│  ● 自动检测 — 让工具自己判断（推荐）                     │
│  ○ 重新对齐 — 字幕有时间轴但对不上                      │
│  ○ 全量打轴 — 字幕只有文本没时间轴                      │
│  ○ 帧对齐   — OP/ED 卡画面帧                          │
│  ○ 双语对齐 — 两种语言合在一起                          │
│  ○ BD分集   — 多集BD自动识别集数                       │
│                                                        │
│  语言: [auto ▼]  模型: [medium ▼]  设备: [auto ▼]     │
│                                                        │
│  [▶ 开始执行]                    [📂 打开输出目录]      │
│                                                        │
│  ┌─ 运行日志 ──────────────────────────────────────┐  │
│  │ >>> subalign auto video.mkv sub.srt -o out.ass  │  │
│  │ ...                                              │  │
│  └──────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────┘
```

**操作步骤**：
1. 点"浏览"选视频文件
2. 点"浏览"选字幕文件
3. 选一个操作（不确定选哪个就选"自动检测"）
4. 点"开始执行"
5. 等它跑完，会弹窗问你要不要用 Aegisub 打开结果

### 用法 B：Aegisub 插件

**安装插件**：

把项目里的这个文件：
```
D:\projects\subalign\src\subalign\plugins\aegisub\subalign.lua
```
复制到（Windows 按 Win+R，粘贴这个路径回车就能打开）：
```
%APPDATA%\Aegisub\automation\autoload\
```

重启 Aegisub 后，菜单栏多了一个 **Automation > SubAlign**，里面有：
- **Re-align timing** — 重新对齐（时间轴不准时用）
- **Full ASR alignment** — AI 打轴（没有时间轴时用）
- **OP/ED frame snap** — 卡帧对齐
- **Detect BD episodes** — BD 分集检测

**使用**：在 Aegisub 里打开视频和字幕，然后从菜单选对应功能就行。

### 用法 C：命令行

如果你熟悉命令行，这几个命令够用了：

```bash
# 不知道该用啥？自动模式！
subalign auto 视频.mkv 字幕.srt -o 输出.ass

# 字幕时间轴和视频对不上
subalign sync 视频.mkv 字幕.srt -o 输出.ass

# 字幕只有文本没时间轴（指定语言为日语）
subalign align 视频.mkv 字幕.txt --lang ja -o 输出.ass

# OP/ED 卡帧
subalign snap 视频.mkv oped.ass -o 输出.ass

# 双语（日语+中文）
subalign bilingual 视频.mkv --primary 日语.srt --secondary 中文.txt -o 双语.ass

# BD 多集：先看看分集对不对
subalign split-bd BD光盘.mkv --detect-only

# BD 多集：确认后拼字幕
subalign split-bd BD光盘.mkv --subs ep01.srt ep02.srt ep03.srt -o 合并.ass
```

---

## 实际工作流示例

### 例1：拿到一个番的翻译稿，要做字幕

```
① 你有：视频文件 + 翻译好的文本文件（没有时间轴）
   ↓
② 运行：subalign align 视频.mkv 翻译.txt --lang ja -o 初版.ass
   （AI 会听视频里的对白，自动给每句话打上时间）
   ↓
③ 用 Aegisub 打开 初版.ass，检查标蓝色的行（那些是 AI 不太确定的）
   ↓
④ 手动修正几处后，完成！
```

### 例2：有别人的字幕但和我的视频版本对不上

```
① 你有：你的视频 + 别人的字幕（时间轴和你的视频对不上）
   ↓
② 运行：subalign sync 视频.mkv 别人的字幕.srt -o 对齐后.ass
   （几秒钟搞定，不需要 AI，纯音频指纹匹配）
   ↓
③ 完成！
```

### 例3：BD 光盘多集 + 要做日中双语

```
① 你有：BD 视频（3集连在一起）+ 3个日语字幕 + 1个中文翻译

② 先检测集边界：
   subalign split-bd BD.mkv --detect-only
   →  EP01: 0s-1480s   EP02: 1483s-2960s   EP03: 2963s-4440s
   看着对就继续

③ 拼接日语字幕：
   subalign split-bd BD.mkv --subs ep01.srt ep02.srt ep03.srt -o 日语合并.ass

④ 合并双语：
   subalign bilingual BD.mkv --primary 日语合并.ass --secondary 中文翻译.txt -o 双语.ass

⑤ Aegisub 打开 双语.ass 精修
```

---

## 参数说明（只列常用的）

| 参数 | 意思 | 默认值 | 什么时候要改 |
|------|------|--------|------------|
| `--lang` | 视频里说的什么语言 | `auto`（自动识别） | 自动识别不准时手动指定 `ja`/`en`/`zh` |
| `--model` | AI 模型大小 | `medium` | 想快就用 `tiny`，想准就用 `large-v3` |
| `--device` | 用 CPU 还是 GPU | `auto` | 显存不够就改成 `cpu` |
| `-o` | 输出文件路径 | 无（必填） | — |

不确定填什么？**全都不填用默认值就行**，只需要给 `-o 输出文件名`。

---

## 常见问题

**Q: 双击 install.bat 说找不到 Python**
→ 去 https://www.python.org/downloads/ 下载安装，**一定勾选 "Add Python to PATH"**

**Q: 说找不到 ffmpeg**
→ 命令提示符输入 `winget install ffmpeg`，或手动下载添加到 PATH

**Q: AI 打轴特别慢**
→ 没有 GPU 的话 AI 用 CPU 跑确实慢，可以：
  - 用小模型：加 `--model tiny`（快但不太准）
  - 如果只是时间轴偏移，用 `sync` 而不是 `align`（不需要 AI，秒完成）

**Q: 打出来的轴不准**
→ 正常，AI 不是万能的。工具会把不确定的行标蓝色 `[?]`，你在 Aegisub 里重点检查这些行就好

**Q: 双语字幕行数对不上**
→ 工具会尽力自动匹配，对不上的标 `[REVIEW]`。在 Aegisub 里 Ctrl+H 搜 REVIEW 就能找到

---

## 开发者信息

```bash
# 安装开发依赖
pip install -e ".[full,dev]"

# 运行测试
pytest

# 完整的技术文档见 CLAUDE.md
```

## License

MIT
