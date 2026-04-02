# AstrBot VTuber 桌面客户端 - 独立部署说明

## 概述

从现在开始，desktop_client 可以独立部署在任意文件夹下运行，不再需要依赖插件目录结构。

## 修改内容

### 1. WebSocket 配置化
- 之前：硬编码 `ws://127.0.0.1:6191/client-ws`
- 现在：可在设置面板中配置完整的 WebSocket 地址

### 2. Live2D 模型路径配置化
- 之前：固定从插件目录的 `live2d-models` 加载
- 现在：可在设置面板中选择模型路径，支持向后兼容

### 3. 新增配置 UI
在设置面板中新增"连接设置"部分：
- **WebSocket 地址**：输入完整的 WebSocket 服务器地址
- **模型路径**：选择 Live2D 模型所在的文件夹

## 独立部署步骤

### 方法一：完整复制（推荐）

1. **复制 desktop_client 文件夹**
   ```
   原位置: data/plugins/astrbot_plugin_vtuber/desktop_client/
   新位置: [任意文件夹]/astrbot_vtuber_client/
   ```

2. **复制 live2d-models 文件夹**
   ```
   原位置: data/plugins/astrbot_plugin_vtuber/live2d-models/
   新位置: [任意文件夹]/astrbot_vtuber_client/live2d-models/
   ```

3. **确保以下文件存在**：
   ```
   astrbot_vtuber_client/
   ├── main.js
   ├── desktopSuite.js
   ├── preload.js
   ├── trayController.js
   ├── index.html
   ├── chat.html
   ├── package.json
   ├── model_dict.json          (新增)
   ├── start.bat / start.sh
   ├── node_modules/             (需要保留)
   ├── public/                   (需要保留)
   └── live2d-models/            (需要复制)
       ├── mao_pro/
       ├── yachiyo/
       └── ...
   ```

4. **启动客户端**
   - Windows: 双击 `start.bat`
   - Linux/Mac: 运行 `./start.sh`

5. **配置连接**
   - 右键点击 Live2D 模型打开菜单
   - 选择"设置"
   - 在"连接设置"中配置：
     - WebSocket 地址：`ws://localhost:6191/client-ws`（如果 AstrBot 在本机运行）
     - 模型路径：留空（使用默认位置）或选择自定义位置

### 方法二：自定义模型路径

如果你想把模型放在其他位置：

1. 按照方法一的步骤 1-4 操作
2. 在设置面板的"模型路径"中点击"选择"按钮
3. 选择你的 live2d-models 文件夹
4. 重启客户端

## 文件说明

### 新增/修改的文件

| 文件 | 变更 | 说明 |
|------|------|------|
| `desktop_client/main.js` | 修改 | 支持自定义模型路径，向后兼容 |
| `desktop_client/desktopSuite.js` | 修改 | 支持完整 WebSocket URL 配置 |
| `desktop_client/preload.js` | 修改 | 暴露 getSettings/setSettings API |
| `desktop_client/index.html` | 修改 | 添加连接设置 UI，从配置读取 WebSocket |
| `desktop_client/model_dict.json` | 新增 | 模型配置文件副本 |

## 配置项说明

### WebSocket 地址格式

```
ws://[host]:[port]/client-ws
```

示例：
- 本机：`ws://localhost:6191/client-ws`
- 局域网：`ws://192.168.1.100:6191/client-ws`
- 远程服务器：`ws://example.com:6191/client-ws`

### 模型路径要求

模型路径应指向包含以下结构的文件夹：
```
live2d-models/
├── mao_pro/
│   └── runtime/
│       ├── mao_pro.model3.json
│       ├── mao_pro.moc3
│       └── ...
└── yachiyo/
    └── yachiyo.model3.json
    └── ...
```

## 向后兼容

所有修改都保持向后兼容：

1. **不修改配置时**：行为与之前完全一致
2. **在原位置运行**：自动使用原有的路径查找逻辑
3. **配置持久化**：使用 electron-store 保存配置，重启后自动加载

## 常见问题

### Q: 启动后提示找不到模型？
A: 请确保：
   - `live2d-models` 文件夹在正确位置
   - 或在设置中配置了正确的模型路径

### Q: WebSocket 连接失败？
A: 请检查：
   - AstrBot 的 vtuber 插件已启动
   - WebSocket 地址配置正确
   - 端口 6191 没有被防火墙阻止

### Q: 如何恢复默认设置？
A: 删除以下文件：
   - Windows: `%APPDATA%\astrbot-vtuber-desktop\config.json`
   - 或在设置中手动改回默认值

### Q: 可以同时运行多个独立客户端吗？
A: 可以！每个客户端会作为独立的连接连接到 AstrBot。
