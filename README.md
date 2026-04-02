# AstrBot VTuber Plugin

AstrBot VTuber 虚拟形象插件，支持 Live2D 模型显示、表情系统、TTS 语音合成、口型同步等功能。

## 架构概述

```
AstrBot 核心
    │
    ▼
┌─────────────────────────────────────────┐
│  astrbot_plugin_vtuber (Python 后端)    │
├─────────────────────────────────────────┤
│  - 消息监听 (AstrBot 事件)              │
│  - 情感分析 (LLM/关键词)                │
│  - TTS 集成 (通过 AstrBot)              │
│  - WebSocket 服务器 (端口 6191)         │
└────────────────────┬────────────────────┘
                     │ WebSocket
                     ▼
         ┌───────────────────────┐
         │  Electron 桌面客户端   │
         │  - Live2D 渲染         │
         │  - 音频播放            │
         │  - 口型同步            │
         │  - 表情切换            │
         └───────────────────────┘
```

## 快速开始

### 1. 安装插件

将插件放置在 AstrBot 的 `data/plugins/` 目录下。

### 2. 安装 Python 依赖

```bash
pip install -r requirements.txt
```

### 3. 启动 AstrBot

```bash
uv run main.py
```

### 4. 启动桌面客户端

配套桌面客户端：[AstrBot VTuber Desktop Client](https://github.com/soiwm/astrbot_plugin_vtuber_client)

**方式一：双击启动脚本（推荐）**

- Windows: 双击 `desktop_client/start.bat`
- Linux/Mac: 运行 `./desktop_client/start.sh`

首次运行会自动安装依赖。

**方式二：命令行启动**

```bash
cd desktop_client
pnpm install  # 首次需要
pnpm dev
```

## 配置说明

| 配置项 | 说明 | 默认值 |
|-------|------|--------|
| `ws_host` | WebSocket 监听地址 | `0.0.0.0` |
| `ws_port` | WebSocket 监听端口 | `6191` |
| `live2d_model` | 默认 Live2D 模型名称 | `mao_pro` |
| `model_dict_path` | Live2D 模型文件夹路径 | 空（使用内置路径） |

### 模型路径配置

插件支持两种方式配置 Live2D 模型路径：

**方式一：通过 AstrBot 管理面板配置（推荐）**

在 AstrBot 插件配置页面的 `Live2D Models Path` 项中填写模型文件夹的绝对路径，例如：
- Windows: `D:/live2d-models`
- Linux/Mac: `/home/user/live2d-models`

配置后，桌面客户端会自动使用该路径加载模型。

**方式二：使用内置路径**

如果不配置 `model_dict_path`，插件会按以下顺序查找模型：
1. 插件目录下的 `live2d-models` 文件夹
2. 桌面客户端目录下的 `desktop_client/live2d-models` 文件夹


## 内置的 Live2D 模型

路径均位于桌面客户端目录下的 `desktop_client/live2d-models` 文件夹

| 模型名称 |
|---------|
| `mao_pro` |
| `yachiyo` |
| `shizuku` |

## 功能特性

- **Live2D 渲染**：支持 Cubism 4 模型
- **表情系统**：基于情感分析自动切换表情
- **TTS 语音**：支持 AstrBot 的 TTS 集成
- **口型同步**：基于音频音量的实时口型同步
- **桌面客户端**：Electron 桌面应用，支持托盘控制

## 桌面客户端功能

- 系统托盘图标
- 窗口穿透模式
- 调整大小模式
- 设置面板（字幕、模型偏移、语音开关等）
- 全局鼠标跟踪（模型视线跟随）

## 核心文件说明

| 文件/目录 | 说明 |
|----------|------|
| `main.py` | 插件主类 |
| `vtuber_ws/` | WebSocket 服务器 |
| `core/` | 核心服务上下文和 Live2D 模型 |
| `utils/` | 工具类（情感分析、句子分割等） |
| `desktop_client/` | Electron 桌面客户端 |
| `desktop_client/live2d-models/` | Live2D 模型资源 |

## 系统要求

- Python 3.9+
- Node.js 18+ (用于桌面客户端)
- AstrBot 3.0+

## 许可证

MIT License
