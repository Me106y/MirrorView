# MirrorView 🪞

<div align="center">

[![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![PyQt5](https://img.shields.io/badge/PyQt-5-41CD52?style=for-the-badge&logo=qt&logoColor=white)](https://pypi.org/project/PyQt5/)
[![Flask](https://img.shields.io/badge/Flask-2.0-000000?style=for-the-badge&logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](LICENSE)

**一个支持实时旁听和AI反馈的智能模拟面试平台**

[English](README.md) | [中文](README_CN.md)

</div>

---

## 📖 项目简介

**MirrorView** 是一款旨在帮助求职者通过真实模拟和AI驱动反馈来提升面试技巧的智能应用。它结合了桌面客户端（PyQt5）和强大的后端服务器（Flask），为用户提供无缝的面试体验。

核心功能包括 **AI 面试官互动**、**实时视频流传输** 以及独特的 **观察者模式**（Observer Mode），允许导师或同行实时观看面试过程并提供指导。

## ✨ 核心功能

### 🤖 AI 模拟面试
- **个性化提问**：基于您的求职意向和简历生成定制化的面试问题。
- **语音交互**：支持语音转文字输入（具备离线兜底方案），还原自然对话场景。
- **智能反馈**：每场面试结束后，AI 将提供全面的分析、评分及改进建议。

### 👀 观察者模式 (Mirror View)
- **实时直播**：通过 RTMP 协议将您的面试画面直播给授权的观察者。
- **实时记录**：观察者可以看到与面试进程同步的对话记录。
- **邀请码加入**：导师通过简单的邀请码即可安全加入面试旁听。

### 👤 用户档案
- **简历解析**：自动从上传的简历中提取技能和项目经验。
- **求职意向管理**：灵活设置和更新您的目标职位及经验水平。
- **面试历史**：随时回顾过往表现、分数及详细的面试评价。

## 🛠️ 技术栈

- **客户端**: Python, PyQt5, OpenCV, SpeechRecognition, PyAudio
- **服务端**: Flask, SQLAlchemy, OpenAI/LangChain (AI逻辑)
- **流媒体**: RTMP (Real-Time Messaging Protocol), FFmpeg
- **数据库**: SQLite (默认), 可扩展至 PostgreSQL/MySQL

## 🚀 快速开始

### 前置要求
- Python 3.8+
- FFmpeg (用于视频流处理)

### 安装步骤

1. **克隆仓库**
   ```bash
   git clone https://github.com/yourusername/MirrorView.git
   cd MirrorView
   ```

2. **安装依赖**
   ```bash
   pip install -r requirements.txt
   ```

### 运行应用

1. **启动服务端**
   ```bash
   python server/main.py
   ```
   服务将在 `http://localhost:5001` 启动。

2. **启动客户端**
   ```bash
   python client/main.py
   ```

## 📸 界面截图

<img src="assets/image-20260313190052517.png" alt="image-20260313190052517" style="zoom:50%;" />

<img src="assets/image-20260313190125373.png" alt="image-20260313190125373" style="zoom:50%;" />

<img src="assets/image-20260313190303870.png" alt="image-20260313190303870" style="zoom:50%;" />

## 🤝 贡献指南

欢迎提交 Pull Request 或 Issue 来帮助改进这个项目！

## 📄 许可证

本项目采用 MIT 许可证 - 详情请参阅 [LICENSE](LICENSE) 文件。

