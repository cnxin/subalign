# SubAlign

- Python CLI 字幕自动对齐工具 + Aegisub 插件
- 技术栈: faster-whisper / WhisperX / ffsubsync / pysubs2 / click
- 入口: `subalign` CLI (pyproject.toml [project.scripts])
- 源码: `src/subalign/`，核心模块在 `src/subalign/core/`

## 模块结构

- `core/audio.py` — ffmpeg 调用: 音频提取, 静音/黑场/场景/关键帧检测
- `core/asr.py` — ASR 引擎: faster-whisper + WhisperX, word-level 时间戳
- `core/subtitle.py` — pysubs2 封装: ASS/SRT/VTT/TXT 解析, 双语样式
- `core/align.py` — S2 快速对齐: ffsubsync/alass + ASR 微调
- `core/matcher.py` — S3 全量对齐: DP 序列匹配 + 缺失检测
- `core/keyframe.py` — S4 帧对齐: 关键帧/节拍 snap
- `core/bilingual.py` — S5 双语: 行映射/锚点/比例 DP
- `core/splitter.py` — S6 BD分割: 静音+黑场交叉验证, 字幕拼接
- `cli.py` — CLI 子命令: sync / align / snap / bilingual / split-bd / auto
- `plugins/aegisub/subalign.lua` — Aegisub Lua 桥接插件

## 外部依赖

- ffmpeg / ffprobe 必须在 PATH 中
- GPU 加速需要 CUDA + PyTorch
- alass 为可选 Rust 二进制 (fallback)
