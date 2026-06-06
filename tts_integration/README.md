# MirrorView-TTS — Voice Integration

> Upgrade MirrorView from text-only mock interviews to a **real-time voice interaction** platform.<br/>
> 将 MirrorView 从纯文本面试升级为**实时语音交互**平台。

<div align="center">

[English](#english) | [中文](#中文)

</div>

---

<span id="english"></span>

## 🇬🇧 English

### 🎯 What's New

| Feature | Description |
|---------|-------------|
| 🎙️ **Voice Mode** | Brand-new split-screen UI — camera on the left, AI interviewer on the right |
| 🔊 **TTS (Text-to-Speech)** | Boson.ai Higgs Audio v3 — 100+ languages, low-latency PCM streaming |
| 🎤 **STT (Speech-to-Text)** | Hold to speak, release to send. Google STT + PocketSphinx offline fallback |
| 🤖 **AI Avatar Animation** | Pulsing glow ring, waveform animation, typewriter subtitles — state-aware |
| 📊 **Mic Level Meter** | Real-time VU bar with peak-hold, green→red gradient, recording indicator |
| 🤖 **DeepSeek-V3 LLM** | Replaces Alibaba DashScope qwen3-max. 20× cheaper, OpenAI-compatible |
| 🧠 **Free Local Embeddings** | HuggingFace all-MiniLM-L6-v2 — no paid embedding API needed |
| 🎛️ **Mode Selector** | Choose between **Classic** (text chat) or **Voice** (speech) on interview start |

### 🏗 Architecture

```
┌──────────────────────────────────────────────────┐
│                 PyQt5 Client                      │
│  ┌─────────┐  ┌───────────┐  ┌────────────────┐ │
│  │ Camera  │  │ AI Avatar │  │ Mic Level Bar  │ │
│  │ 15fps   │  │ (animated)│  │ (real-time VU) │ │
│  └─────────┘  └───────────┘  └────────────────┘ │
│  ┌─────────┐  ┌───────────┐  ┌────────────────┐ │
│  │ STT     │  │ Audio     │  │ TTS Client     │ │
│  │ Worker  │  │ Player    │  │ (HTTP stream)  │ │
│  └────┬────┘  └─────┬─────┘  └───────┬────────┘ │
└───────┼─────────────┼───────────────┼───────────┘
        │             │               │
   Google STT    sounddevice    HTTP streaming
        │         24kHz PCM         │
        │             │               │
┌───────┼─────────────┼───────────────┼───────────┐
│       │       Flask Server         │            │
│  ┌────┴─────────────┴──────────────┴──────────┐ │
│  │              API Routes                     │ │
│  │  /api/tts/synthesize  (PCM streaming)       │ │
│  │  /api/tts/health      (service status)      │ │
│  │  /api/tts/voices      (preset list)         │ │
│  └─────────────────────────────────────────────┘ │
│  ┌──────────┐  ┌───────────┐  ┌──────────────┐ │
│  │ DeepSeek │  │ HuggingFace│  │ Boson Higgs   │ │
│  │ (LLM)    │  │ (Embedding)│  │ Audio v3 (TTS)│ │
│  │ V3, ¥1/M│  │ free local │  │ free preview  │ │
│  └──────────┘  └───────────┘  └──────────────┘ │
└─────────────────────────────────────────────────┘
```

### 📁 File Structure

```
tts_integration/
├── README.md                          # ← you are here
├── __init__.py
├── run_demo.py                        # one-click demo
├── server/
│   ├── tts_service.py                 # Higgs Audio v3 wrapper
│   ├── routes_tts.py                  # Flask TTS endpoints (3 routes)
│   └── factories/
│       └── llm_factory.py             # LLM factory (DeepSeek/DashScope/Ollama)
├── client/
│   ├── audio_player.py                # PCM streaming player (sounddevice)
│   ├── tts_client.py                  # TTS HTTP streaming client
│   └── voice_integration.py           # voice integration helpers
├── tests/
│   ├── test_tts_service.py            # TTS unit + live API tests
│   ├── test_audio_player.py           # audio player tests
│   └── test_integration.py            # end-to-end pipeline tests
└── docs/
    ├── API.md                         # API reference
    ├── INTEGRATION_GUIDE.md           # step-by-step integration guide
    └── TEST_PLAN.md                   # test strategy & cases
```

**Files modified in the main project:**

| File | Action | Purpose |
|------|--------|---------|
| `client/ui/voice_interview_window.py` | **New** | Voice interview window (light theme) |
| `client/ui/ai_avatar_widget.py` | **New** | Animated AI interviewer avatar |
| `client/ui/mic_level_widget.py` | **New** | Real-time microphone VU meter |
| `client/ui/main_window.py` | **Modified** | Added `ModeSelectDialog` |
| `client/core/audio_player.py` | **New** | PCM audio playback |
| `client/core/tts_client.py` | **New** | TTS HTTP client |
| `client/core/voice_integration.py` | **New** | Voice integration utilities |
| `server/factories/llm_factory.py` | **New** | LLM factory with DeepSeek support |
| `server/services/tts_service.py` | **New** | Higgs Audio v3 service wrapper |
| `server/services/resume_service.py` | **Modified** | Switched to free local embeddings |
| `server/services/ai_service.py` | **Modified** | Switched to `deepseek-chat` |
| `server/config.py` | **Modified** | Added `DEEPSEEK_API_KEY` config |
| `server/app.py` | **Modified** | Registered TTS routes, disabled debug mode |
| `start.sh` | **New** | One-click launcher |

### 🚀 Quick Start

**Prerequisites**

- macOS (Python 3.14 via Homebrew)
- Microphone + webcam
- DeepSeek API Key ([get one](https://platform.deepseek.com/api_keys))
- Boson.ai API Key ([get one](https://workspace.boson.ai))

**One-click:**

```bash
cd MirrorView-TTS
./start.sh
```

**Manual:**

```bash
export DEEPSEEK_API_KEY="sk-xxx"
export BOSON_API_KEY="bai-xxx"
export PYTHONPATH="$PWD"

# Terminal 1 — server
/opt/homebrew/bin/python3.14 server/app.py

# Terminal 2 — client
/opt/homebrew/bin/python3.14 client/main.py
```

**Usage Flow**

1. Launch client → register (any username/password)
2. Login → click **Start New Interview**
3. Mode selector appears:
   - **💬 Classic Mode** — traditional text chat
   - **🎙️ Voice Mode** — speech interaction (recommended)
4. Pick Voice Mode → hear the AI interviewer's spoken greeting
5. **Hold 🎤 button to speak** → release to transcribe & send
6. DeepSeek replies → TTS reads it aloud + avatar animates
7. End interview → view detailed feedback

### 🔑 API Keys

| Variable | Service | Purpose | Get it at |
|----------|---------|---------|-----------|
| `DEEPSEEK_API_KEY` | DeepSeek | LLM chat | https://platform.deepseek.com/api_keys |
| `BOSON_API_KEY` | Boson.ai | TTS voice | https://workspace.boson.ai |

Keys can be placed in `~/.zshrc`, `export`ed in shell, or written to `.env_tts`.

### 🧪 Run Tests

```bash
cd MirrorView-TTS
export BOSON_API_KEY="bai-xxx"

# All tests
/opt/homebrew/bin/python3.14 -m pytest tts_integration/tests/ -v

# Individual
/opt/homebrew/bin/python3.14 tts_integration/tests/test_tts_service.py
/opt/homebrew/bin/python3.14 tts_integration/tests/test_audio_player.py
/opt/homebrew/bin/python3.14 tts_integration/tests/test_integration.py

# Full demo
/opt/homebrew/bin/python3.14 tts_integration/run_demo.py
```

### 📊 Cost Comparison

| Model | Price (per 1M tokens) | Quality |
|-------|:---:|---------|
| DeepSeek-V3 | **≈ ¥1** | GPT-4 comparable |
| DashScope qwen3-max | ≈ ¥20 | GPT-4 comparable |
| Ollama (local) | Free | depends on model |

### 🔮 Roadmap

- [ ] Digital human avatar (D-ID / HeyGen cloud API)
- [ ] Streaming TTS latency optimization
- [ ] Interviewer voice selection
- [ ] Interview recording & playback
- [ ] Docker deployment

### 📄 License

MIT — same as MirrorView main project.

---

<span id="中文"></span>

## 🇨🇳 中文

### 🎯 新增功能

| 功能 | 说明 |
|------|------|
| 🎙️ **语音模式** | 全新分屏界面，左摄像头右 AI 面试官 |
| 🔊 **TTS 语音合成** | Boson.ai Higgs Audio v3，100+ 语言，低延迟流式 PCM 输出 |
| 🎤 **STT 语音输入** | 按住说话松手发送，Google STT + PocketSphinx 离线兜底 |
| 🤖 **AI 面试官动画** | 脉动光环 + 波形动效 + 打字机字幕，状态联动 |
| 📊 **麦克风电平表** | 实时 VU 表，峰值保持，绿→红渐变色，录音指示灯 |
| 🤖 **DeepSeek-V3** | 替代阿里百炼 qwen3-max，便宜 20 倍，OpenAI 兼容 API |
| 🧠 **免费本地 Embedding** | HuggingFace all-MiniLM-L6-v2，无需付费 Embedding API |
| 🎛️ **模式选择** | 开始面试时可选 Classic（文字）或 Voice（语音）模式 |

### 🏗 架构

```
┌──────────────────────────────────────────────────┐
│                 PyQt5 客户端                       │
│  ┌─────────┐  ┌───────────┐  ┌────────────────┐ │
│  │ 摄像头  │  │ AI 头像   │  │  麦克风电平表   │ │
│  │ 15fps   │  │ (动画)    │  │  (实时 VU)     │ │
│  └─────────┘  └───────────┘  └────────────────┘ │
│  ┌─────────┐  ┌───────────┐  ┌────────────────┐ │
│  │ STT     │  │ 音频播放  │  │  TTS 客户端     │ │
│  │ 工作线程 │  │ 器        │  │  (HTTP 流)     │ │
│  └────┬────┘  └─────┬─────┘  └───────┬────────┘ │
└───────┼─────────────┼───────────────┼───────────┘
        │             │               │
   Google 语音    sounddevice    HTTP 流式传输
        │         24kHz PCM         │
        │             │               │
┌───────┼─────────────┼───────────────┼───────────┐
│       │       Flask 服务端          │            │
│  ┌────┴─────────────┴──────────────┴──────────┐ │
│  │              API 路由                        │ │
│  │  /api/tts/synthesize  (PCM 流)              │ │
│  │  /api/tts/health      (服务状态)             │ │
│  │  /api/tts/voices      (音色列表)             │ │
│  └─────────────────────────────────────────────┘ │
│  ┌──────────┐  ┌───────────┐  ┌──────────────┐ │
│  │ DeepSeek │  │ HuggingFace│  │ Boson Higgs   │ │
│  │ (大模型) │  │ (向量嵌入) │  │ Audio v3 (TTS)│ │
│  │ V3 ¥1/M │  │ 免费本地   │  │ 公测免费      │ │
│  └──────────┘  └───────────┘  └──────────────┘ │
└─────────────────────────────────────────────────┘
```

### 📁 文件结构

```
tts_integration/
├── README.md                          # ← 你正在看
├── __init__.py
├── run_demo.py                        # 一键演示脚本
├── server/
│   ├── tts_service.py                 # Higgs Audio v3 封装
│   ├── routes_tts.py                  # Flask TTS 端点（3 个路由）
│   └── factories/
│       └── llm_factory.py             # LLM 工厂（DeepSeek/百炼/Ollama）
├── client/
│   ├── audio_player.py                # PCM 流式播放器
│   ├── tts_client.py                  # TTS HTTP 流式客户端
│   └── voice_integration.py           # 语音集成辅助
├── tests/
│   ├── test_tts_service.py            # TTS 单元测试 + 真实 API 测试
│   ├── test_audio_player.py           # 音频播放器测试
│   └── test_integration.py            # 端到端管道测试
└── docs/
    ├── API.md                         # API 参考文档
    ├── INTEGRATION_GUIDE.md           # 接入指南
    └── TEST_PLAN.md                   # 测试策略
```

**主项目修改的文件：**

| 文件 | 操作 | 说明 |
|------|------|------|
| `client/ui/voice_interview_window.py` | **新增** | 语音面试窗口（浅色主题） |
| `client/ui/ai_avatar_widget.py` | **新增** | AI 面试官动画头像 |
| `client/ui/mic_level_widget.py` | **新增** | 麦克风实时电平表 |
| `client/ui/main_window.py` | **修改** | 新增 `ModeSelectDialog` 模式选择 |
| `client/core/audio_player.py` | **新增** | PCM 音频播放器 |
| `client/core/tts_client.py` | **新增** | TTS HTTP 客户端 |
| `client/core/voice_integration.py` | **新增** | 语音集成工具类 |
| `server/factories/llm_factory.py` | **新增** | LLM 工厂（支持 DeepSeek） |
| `server/services/tts_service.py` | **新增** | Higgs Audio v3 服务封装 |
| `server/services/resume_service.py` | **修改** | 改用免费本地 Embedding |
| `server/services/ai_service.py` | **修改** | 切换为 `deepseek-chat` |
| `server/config.py` | **修改** | 新增 `DEEPSEEK_API_KEY` 等配置 |
| `server/app.py` | **修改** | 注册 TTS 路由，关闭 debug 模式 |
| `start.sh` | **新增** | 一键启动脚本 |

### 🚀 快速启动

**前置条件**

- macOS（Homebrew 安装的 Python 3.14）
- 麦克风和摄像头
- DeepSeek API Key（[申请](https://platform.deepseek.com/api_keys)）
- Boson.ai API Key（[申请](https://workspace.boson.ai)）

**一键启动：**

```bash
cd MirrorView-TTS
./start.sh
```

**手动启动：**

```bash
export DEEPSEEK_API_KEY="sk-xxx"
export BOSON_API_KEY="bai-xxx"
export PYTHONPATH="$PWD"

# 终端 1 — 服务端
/opt/homebrew/bin/python3.14 server/app.py

# 终端 2 — 客户端
/opt/homebrew/bin/python3.14 client/main.py
```

**使用流程**

1. 启动客户端 → 注册账号（任意用户名/密码）
2. 登录 → 点击 **Start New Interview**
3. 弹出模式选择：
   - **💬 Classic Mode** — 传统文字聊天面试
   - **🎙️ Voice Mode** — 语音交互面试（推荐）
4. 选择 Voice Mode → 听到 AI 面试官语音问候
5. **按住 🎤 按钮说话** → 松手自动识别并发送
6. DeepSeek 生成回复 → TTS 朗读 + 头像动画
7. 结束面试 → 查看 Feedback 评分与建议

### 🔑 API Key 配置

| 环境变量 | 服务 | 用途 | 获取地址 |
|----------|------|------|----------|
| `DEEPSEEK_API_KEY` | DeepSeek | 大模型对话 | https://platform.deepseek.com/api_keys |
| `BOSON_API_KEY` | Boson.ai | TTS 语音合成 | https://workspace.boson.ai |

Key 可写入 `~/.zshrc`、直接 `export`，或放在项目根目录的 `.env_tts` 文件中。

### 🧪 运行测试

```bash
cd MirrorView-TTS
export BOSON_API_KEY="bai-xxx"

# 全部测试
/opt/homebrew/bin/python3.14 -m pytest tts_integration/tests/ -v

# 单独运行
/opt/homebrew/bin/python3.14 tts_integration/tests/test_tts_service.py
/opt/homebrew/bin/python3.14 tts_integration/tests/test_audio_player.py
/opt/homebrew/bin/python3.14 tts_integration/tests/test_integration.py

# 完整演示
/opt/homebrew/bin/python3.14 tts_integration/run_demo.py
```

### 📊 成本对比

| 模型 | 价格（每百万 token） | 质量 |
|------|:---:|------|
| DeepSeek-V3 | **≈ ¥1** | 接近 GPT-4 |
| 百炼 qwen3-max | ≈ ¥20 | 接近 GPT-4 |
| Ollama 本地 | 免费 | 取决于模型 |

### 🔮 后续计划

- [ ] 数字人（D-ID / HeyGen 云端 API 接入）
- [ ] 流式 TTS 低延迟优化
- [ ] 面试官音色选择
- [ ] 面试录音回放
- [ ] Docker 一键部署

### 📄 许可证

MIT — 与 MirrorView 主项目一致。
