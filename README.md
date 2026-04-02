# SubAlign — AI 字幕自动对齐工具

将已有字幕文本通过语音识别自动匹配到视频时间轴，输出可在 Aegisub 中编辑的 ASS 文件。

## 功能总览

| 场景 | 命令 | 说明 |
|------|------|------|
| S2 | `subalign sync` | 有时间轴但偏移 → 音频指纹快速校正 |
| S3 | `subalign align` | 无时间轴/部分时间轴 → ASR 全量对齐 |
| S4 | `subalign snap` | OP/ED → 帧级对齐到关键帧/节拍 |
| S5 | `subalign bilingual` | 双语字幕 → 主语言打轴 + 副语言继承 |
| S6 | `subalign split-bd` | BD 多集视频 → 自动检测集边界 + 字幕拼接 |
| 自动 | `subalign auto` | 自动检测场景并选择对应流程 |

---

## 安装

### 环境要求

- Python 3.10+
- ffmpeg + ffprobe（必须在 PATH 中）
- 可选：NVIDIA GPU + CUDA（加速 ASR）

### 安装步骤

```bash
# 克隆项目
git clone <repo-url> subalign
cd subalign

# 基础安装（ffsubsync + faster-whisper）
pip install -e .

# 完整安装（含 WhisperX + librosa + silero-vad）
pip install -e ".[full]"

# 开发安装
pip install -e ".[full,dev]"
```

### 验证安装

```bash
subalign --help
```

### ffmpeg 安装

Windows:
```bash
# 使用 scoop
scoop install ffmpeg

# 或使用 chocolatey
choco install ffmpeg
```

Linux / macOS:
```bash
# Ubuntu/Debian
sudo apt install ffmpeg

# macOS
brew install ffmpeg
```

---

## 快速开始

### 最简单的用法：自动模式

```bash
subalign auto video.mkv subtitle.srt -o aligned.ass
```

工具会自动检测字幕状态（有无时间轴、是否偏移），选择最合适的对齐策略。

---

## 使用指南

### 场景 S2：字幕时间轴偏移/不准

**适用情况**：字幕有时间码但与视频不同步（如整体偏移、帧率不匹配）。

```bash
# 基础用法 - 使用 ffsubsync 音频指纹校正
subalign sync video.mkv subtitle.srt -o aligned.ass

# 使用 alass 引擎（更擅长处理广告分割）
subalign sync video.mkv subtitle.srt -o aligned.ass --backend alass

# 有参考字幕时（极快，<1秒）
subalign sync video.mkv bad_timing.srt -o aligned.ass --reference good_timing.srt

# 校正后再用 ASR 微调（更精确但更慢）
subalign sync video.mkv subtitle.srt -o aligned.ass --refine
```

**工作原理**：
1. ffsubsync 提取视频音频的语音活动指纹
2. 提取字幕的语音时间分布
3. FFT 交叉相关找到最佳时间偏移
4. 可选：WhisperX 逐句验证并微调

---

### 场景 S3：纯文本或缺失时间轴

**适用情况**：有字幕文本但没有时间码（如翻译文稿），或部分字幕缺失。

```bash
# 基础用法 - 指定语言
subalign align video.mkv script.txt --lang ja -o aligned.ass

# 自动检测语言
subalign align video.mkv subtitle.srt -o aligned.ass

# 检测缺失段落（ASR 有内容但字幕无对应 → 标记为 Comment）
subalign align video.mkv partial.srt -o aligned.ass --detect-missing

# 导出对齐报告
subalign align video.mkv script.txt -o aligned.ass --report report.json

# 使用小模型加速（精度降低）
subalign align video.mkv script.txt -o aligned.ass --model tiny

# 使用大模型提高精度
subalign align video.mkv script.txt -o aligned.ass --model large-v3
```

**Whisper 模型选择**：

| 模型 | 大小 | 速度 | 精度 | 推荐场景 |
|------|------|------|------|----------|
| `tiny` | ~75MB | 极快 | 低 | 快速预览/测试 |
| `base` | ~150MB | 快 | 中低 | 简单对白 |
| `small` | ~500MB | 中 | 中 | 日常使用 |
| `medium` | ~1.5GB | 较慢 | 高 | **默认推荐** |
| `large-v3` | ~3GB | 慢 | 最高 | 复杂场景/多语言 |

**对齐报告 (report.json) 说明**：

```json
{
  "total_alignments": 350,
  "matched": 320,           // 成功匹配
  "low_confidence": 15,     // 低置信度（ASS 中标蓝色）
  "missing_in_subtitle": 10,// ASR 检测到但字幕缺失
  "missing_in_asr": 5,      // 字幕有但 ASR 未识别
  "average_confidence": 0.87
}
```

**输出 ASS 中的特殊标记**：
- `{\\c&H0000FF&}[?]` — 低置信度行，建议人工检查
- `{\\c&H00FF00&}[ASR]` — ASR 检测到的缺失段落（Comment 行）

---

### 场景 S4：OP/ED 帧级对齐

**适用情况**：OP/ED 字幕需要与画面帧精确对齐（如特效字幕、卡拉 OK 字幕）。

```bash
# 基础用法 - 自动 snap 到关键帧 + 音频节拍
subalign snap video.mkv oped.ass -o snapped.ass

# 仅关键帧对齐（不用音频节拍）
subalign snap video.mkv oped.ass -o snapped.ass --no-beats

# 调整 snap 容差（默认 80ms）
subalign snap video.mkv oped.ass -o snapped.ass --tolerance 0.05
```

**工作原理**：
1. ffmpeg 提取视频场景切换点（优先级最高）
2. ffprobe 提取关键帧列表
3. librosa 检测音频节拍/重音点（需安装 `[full]`）
4. 每条字幕的起止时间 snap 到最近的参考点
5. 保证最小显示时长 ≥ 500ms

---

### 场景 S5：双语字幕

**适用情况**：需要同时显示两种语言（如日语 + 中文翻译）。

```bash
# 基础用法 - 分离样式（默认）
subalign bilingual video.mkv \
  --primary ja_sub.srt \
  --secondary cn_sub.txt \
  --primary-lang ja \
  --secondary-lang zh \
  -o bilingual.ass

# 双行合并模式（一条字幕包含两种语言）
subalign bilingual video.mkv \
  --primary ja_sub.srt \
  --secondary cn_sub.txt \
  --bilingual-style merged \
  -o bilingual.ass

# 副语言作为 Comment（不显示但可在 Aegisub 中查看）
subalign bilingual video.mkv \
  --primary ja_sub.srt \
  --secondary cn_sub.txt \
  --bilingual-style comment \
  -o bilingual.ass
```

**三种输出样式**：

| 样式 | `--bilingual-style` | 效果 |
|------|---------------------|------|
| 分离 | `split`（默认） | 主语言 Style `JP`（上方）+ 副语言 Style `CN`（下方），独立样式 |
| 合并 | `merged` | 单条字幕用 `\N` 换行：上方主语言/下方副语言 |
| 注释 | `comment` | 副语言为 Comment 行（不显示，Aegisub 中可查阅） |

**对齐策略**（自动选择）：
1. 行数一致 → 直接 1:1 映射
2. 两份都有时间码 → 时间重叠锚点对齐
3. 行数不一致 → 比例分配 + 标记 `[REVIEW]`

**注意**：副语言不依赖 ASR（翻译文本与原声不同），而是继承主语言的时间轴。

---

### 场景 S6：BD 多集视频分割

**适用情况**：Blu-ray 光盘通常将多集编码为单个视频文件，需要自动识别集边界。

```bash
# 步骤 1：仅检测集边界（不拼接，先确认准确度）
subalign split-bd bd_disc.mkv --detect-only
```

输出示例：
```
Total duration: 4420.0s (73.7min)
Detected episodes: 3

  EP01: 0.0s - 1478.5s (24.6min) [silence, black] confidence=90.0%
  EP02: 1481.2s - 2958.8s (24.6min) [silence, black] confidence=90.0%
  EP03: 2961.5s - 4420.0s (24.3min) [duration] confidence=80.0%
```

```bash
# 步骤 2：确认后，提供字幕文件拼接
subalign split-bd bd_disc.mkv \
  --subs ep01.srt ep02.srt ep03.srt \
  -o merged.ass

# 自定义集时长范围（如 OVA 可能更长）
subalign split-bd bd_disc.mkv \
  --subs ep01.srt ep02.srt \
  --ep-min 1500 --ep-max 2400 \
  -o merged.ass
```

**检测原理**（多信号融合）：
1. **静音检测**：ffmpeg `silencedetect`，找 >3s 的静音段
2. **黑场检测**：ffmpeg `blackdetect`，找 >1s 的黑屏
3. **交叉验证**：静音+黑场同时出现 = 高置信度边界
4. **时长约束**：过滤不合理的候选（每集 20-30 分钟）

---

## 全局选项

所有子命令共享以下全局选项：

```bash
subalign [全局选项] <子命令> [子命令选项]

# 全局选项
--lang TEXT          语言代码 (ja/en/zh/auto)，默认 auto
--model TEXT         Whisper 模型 (tiny/base/small/medium/large-v3)，默认 medium
--device TEXT        计算设备 (auto/cuda/cpu)，默认 auto
--confidence-threshold FLOAT  置信度阈值，默认 0.7
--output-format TEXT 输出格式 (ass/srt)，默认 ass
--audio-track INT    音频轨道索引（多音轨视频时指定）
```

**指定音频轨道**（多音轨视频）：

```bash
# 查看视频中的音频轨道（用 ffprobe）
ffprobe -v quiet -print_format json -show_streams -select_streams a video.mkv

# 使用第2条音频轨道（如日语原声在第2轨）
subalign align video.mkv script.txt -o aligned.ass --audio-track 1
```

---

## Aegisub 插件使用

### 安装

将 `src/subalign/plugins/aegisub/subalign.lua` 复制到 Aegisub 的自动加载目录：

**Windows**：
```
%APPDATA%\Aegisub\automation\autoload\subalign.lua
```

**macOS**：
```
~/Library/Application Support/Aegisub/automation/autoload/subalign.lua
```

**Linux**：
```
~/.aegisub/automation/autoload/subalign.lua
```

### 前提

- `subalign` CLI 必须已安装且在系统 PATH 中
- ffmpeg / ffprobe 在 PATH 中

### 菜单项

安装后重启 Aegisub，在 **Automation** 菜单下会出现：

| 菜单项 | 对应场景 |
|--------|----------|
| SubAlign > Re-align timing (S2) | 快速重对齐 |
| SubAlign > Full ASR alignment (S3) | ASR 全量对齐 |
| SubAlign > OP/ED frame snap (S4) | 帧级对齐 |
| SubAlign > Detect BD episodes (S6) | BD 集边界检测 |

### 使用流程

1. 在 Aegisub 中打开视频和字幕文件
2. 从 Automation > SubAlign 选择对应功能
3. 在弹出对话框中配置参数（语言、模型等）
4. 等待处理完成（进度条显示在 Aegisub 底部）
5. 结果自动应用到当前字幕，支持 Ctrl+Z 撤销

---

## 推荐工作流

### 典型动画字幕制作流程

```
1. 获取视频 + 翻译文稿（纯文本）
       ↓
2. subalign align video.mkv script.txt --lang ja -o rough.ass
       ↓ (ASR 自动打轴)
3. Aegisub 打开 rough.ass，检查蓝色标记行 [?]
       ↓ (人工修正低置信度行)
4. subalign snap video.mkv rough.ass -o oped.ass
       ↓ (OP/ED 帧对齐)
5. 完成
```

### BD 多集 + 双语工作流

```
1. subalign split-bd bd.mkv --detect-only
       ↓ (确认集边界)
2. subalign split-bd bd.mkv --subs ep01.srt ep02.srt ep03.srt -o merged_ja.ass
       ↓ (日语字幕拼接)
3. subalign bilingual bd.mkv --primary merged_ja.ass --secondary cn_all.txt -o final.ass
       ↓ (双语对齐)
4. Aegisub 打开 final.ass 精修
```

---

## 故障排除

### 常见问题

**Q: `subalign: command not found`**

确保已安装并在 PATH 中：
```bash
pip install -e .
# 或确认 Python Scripts 目录在 PATH 中
python -m subalign.cli --help
```

**Q: ffmpeg/ffprobe not found**

安装 ffmpeg 并确认在 PATH 中：
```bash
ffmpeg -version
ffprobe -version
```

**Q: CUDA out of memory**

使用更小的模型或强制 CPU：
```bash
subalign align video.mkv sub.txt -o out.ass --model small --device cpu
```

**Q: WhisperX 安装失败**

WhisperX 依赖 PyTorch，确保先安装正确版本：
```bash
# CUDA 11.8
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu118

# CPU only
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu

# 然后安装 WhisperX
pip install whisperx
```
如果 WhisperX 不可用，工具会自动回退到 faster-whisper（仍支持 word-level 时间戳）。

**Q: BD 集边界检测不准**

- 检查 `--detect-only` 输出，确认时长是否合理
- 调整 `--ep-min` / `--ep-max` 适配非标准时长（如 OVA、特番）
- 极端情况下，可手动指定边界时间点（未来版本支持）

**Q: 双语行数不匹配怎么办**

工具会自动使用比例分配策略，不匹配的行会标记 `[REVIEW]`。在 Aegisub 中搜索 `REVIEW` 即可定位需要人工检查的行。

---

## 开发

```bash
# 安装开发依赖
pip install -e ".[full,dev]"

# 运行测试
pytest

# 类型检查（可选）
mypy src/subalign/
```

## License

MIT
