
# astrbot_plugin_vtuber 桌面客户端独立化计划

## 上下文

当前 astrbot_plugin_vtuber 插件的 desktop_client 与插件代码耦合在一起，通过硬编码的相对路径来查找 Live2D 模型文件和连接 WebSocket 服务器。为了让桌面客户端可以独立部署在不同文件夹下，需要进行解耦改造。

## 目标

让 desktop_client 能够：
1. 独立存放在任意文件夹下运行
2. 可配置 WebSocket 连接地址
3. 可配置 Live2D 模型存储位置
4. 保持与现有功能完全兼容

## 关键发现

### 当前架构分析

1. **WebSocket 通信**：
   - 后端 WebSocket 服务器：`main.py:316-512` 的 `VTuberWebSocketServer` 类
   - 默认监听：`0.0.0.0:6191`
   - 端点：`/client-ws`
   - 前端连接：`index.html:748` 硬编码 `ws://127.0.0.1:6191/client-ws`

2. **路径解析**：
   - `main.js:8-25` 的 `resolveDesktopPathRoots()` 函数
   - 硬编码相对路径向上查找插件根目录：`path.join(projectRoot, '..')`
   - 模型路径：`pluginRoot/live2d-models`

3. **模型加载**：
   - `desktopSuite.js:105-154` 的 `startModelServer()` 启动本地 HTTP 服务器
   - `index.html:624-643` 构建模型 URL

4. **配置存储**：
   - 使用 `electron-store` 存储设置（`desktopSuite.js:168`）
   - 默认设置包含服务器 URL 和端口（`desktopSuite.js:180-198`）

## 实施方案

### 1. WebSocket 配置改造

**需要修改的文件**：

| 文件 | 修改内容 |
|------|----------|
| `desktop_client/desktopSuite.js` | 增强默认设置，支持完整 WebSocket URL 配置 |
| `desktop_client/index.html` | 从设置读取 WebSocket URL 而非硬编码 |

**具体改动**：

- `desktopSuite.js:180-198`：修改默认设置
  ```javascript
  const defaultSettings = {
    server: {
      url: 'ws://localhost:6191/client-ws',  // 完整 URL
      autoConnect: true
    },
    // ... 其他配置保持不变
  };
  ```

- `index.html:747-778`：修改 `connectWebSocket()` 函数
  ```javascript
  async function connectWebSocket() {
    // 从 electronAPI 获取设置
    const settings = await electronAPI.getSettings();
    const wsUrl = settings?.server?.url || 'ws://127.0.0.1:6191/client-ws';
    // ... 其余保持不变
  }
  ```

### 2. 模型存储位置配置

**需要修改的文件**：

| 文件 | 修改内容 |
|------|----------|
| `desktop_client/main.js` | 修改路径解析逻辑，支持配置模型路径 |
| `desktop_client/desktopSuite.js` | 从设置读取模型路径，添加模型路径选择 UI |
| `desktop_client/index.html` | 模型加载逻辑适配 |

**具体改动**：

- `main.js:8-25`：修改 `resolveDesktopPathRoots()`
  ```javascript
  function resolveDesktopPathRoots({ isPackaged, appPath, customModelsPath }) {
    const projectRoot = isPackaged ? path.dirname(appPath) : __dirname;
    const assetRoot = projectRoot;
    
    // 如果提供了自定义模型路径，使用它
    if (customModelsPath &amp;&amp; fs.existsSync(customModelsPath)) {
      return {
        projectRoot,
        assetRoot,
        modelsRoot: customModelsPath,
        isStandalone: true
      };
    }
    
    // 否则尝试原有的相对路径方式（向后兼容）
    try {
      const pluginRoot = path.join(projectRoot, '..');
      const workspaceRoot = path.join(projectRoot, '..', '..', '..', '..');
      return {
        projectRoot,
        assetRoot,
        workspaceRoot,
        pluginRoot,
        modelsRoot: path.join(pluginRoot, 'live2d-models'),
        isStandalone: false
      };
    } catch {
      // 回退到使用当前目录下的 live2d-models
      return {
        projectRoot,
        assetRoot,
        modelsRoot: path.join(projectRoot, 'live2d-models'),
        isStandalone: true
      };
    }
  }
  ```

- `desktopSuite.js:168-172`：修改启动逻辑
  ```javascript
  const store = new Store();
  const settings = getSettings();
  
  // 获取模型路径：使用配置的路径，或默认使用当前目录下的 live2d-models
  let modelsPath = settings?.models?.path;
  if (!modelsPath || !fs.existsSync(modelsPath)) {
    modelsPath = path.join(assetRoot, 'live2d-models');
  }
  
  const { server, url: modelServerUrl, port: modelServerPort } = await startModelServer(modelsPath, logger);
  ```

- `desktopSuite.js:180-198`：添加模型路径配置
  ```javascript
  const defaultSettings = {
    server: {
      url: 'ws://localhost:6191/client-ws',
      autoConnect: true
    },
    models: {
      path: '',  // 空字符串表示使用默认位置
    },
    window: { /* ... */ },
    general: { /* ... */ }
  };
  ```

### 3. 模型配置文件 (model_dict.json) 处理

**需要修改的文件**：

| 文件 | 修改内容 |
|------|----------|
| `desktop_client/desktopSuite.js` | 支持从模型路径加载 model_dict.json |

- 在独立模式下，将 `model_dict.json` 复制到模型目录中，或提供默认配置

### 4. 新增配置 UI

在设置面板中添加：
- WebSocket 服务器地址输入框
- 模型路径选择按钮（使用 Electron 的对话框）

**需要修改的文件**：
- `desktop_client/index.html`：添加配置 UI 元素
- `desktop_client/desktopSuite.js`：添加 IPC 处理程序打开文件夹选择对话框

### 5. 向后兼容保证

- 如果没有配置自定义路径，继续使用原有相对路径查找方式
- 如果找不到插件目录，回退到使用当前目录下的 `live2d-models`
- WebSocket 默认值保持为 `ws://localhost:6191/client-ws`

## 实施步骤

### 阶段 1：WebSocket 配置化
1. 修改 `desktopSuite.js` 的默认设置
2. 修改 `index.html` 的 WebSocket 连接逻辑
3. 测试连接功能

### 阶段 2：模型路径配置化
1. 修改 `main.js` 的路径解析逻辑
2. 修改 `desktopSuite.js` 的模型服务器启动逻辑
3. 测试模型加载功能

### 阶段 3：配置 UI
1. 在设置面板添加 WebSocket 地址配置
2. 添加模型路径选择功能
3. 测试配置保存和加载

### 阶段 4：独立部署测试
1. 将 desktop_client 复制到独立文件夹
2. 复制 live2d-models 到相应位置
3. 验证完整功能

## 关键文件清单

| 文件路径 | 作用 |
|---------|------|
| `data/plugins/astrbot_plugin_vtuber/desktop_client/main.js` | Electron 主进程，路径解析 |
| `data/plugins/astrbot_plugin_vtuber/desktop_client/desktopSuite.js` | 桌面应用核心逻辑 |
| `data/plugins/astrbot_plugin_vtuber/desktop_client/index.html` | Live2D 渲染页面，WebSocket 连接 |
| `data/plugins/astrbot_plugin_vtuber/main.py` | 后端 WebSocket 服务器（无需修改） |

## 验证方法

1. **功能测试**：
   - 启动 AstrBot 和 vtuber 插件
   - 从独立文件夹启动 desktop_client
   - 配置 WebSocket 地址和模型路径
   - 验证对话、表情、TTS 功能正常

2. **向后兼容测试**：
   - 在原位置启动 desktop_client（不修改配置）
   - 验证所有功能正常工作

3. **配置持久化测试**：
   - 修改配置后重启客户端
   - 验证配置被正确保存和加载

## 总结

**是否需要为独立客户端配置 WebSocket？**  
✅ **需要** - 当前硬编码了 `ws://127.0.0.1:6191/client-ws`，需要让用户可配置。

**Live2D 模型需要修改存储位置吗？**  
✅ **需要** - 提供可配置的模型路径，但保持向后兼容（支持原有方式和新方式）。

**核心改动点**：
1. WebSocket URL 可配置（从设置读取）
2. 模型路径可配置（支持自定义路径 + 回退逻辑）
3. 添加相应的配置 UI
4. 保持向后兼容
