const path = require('node:path');
const http = require('node:http');
const fs = require('node:fs');
const Store = require('electron-store');

const CHANNELS = Object.freeze({
  invoke: 'live2d:rpc:invoke',
  result: 'live2d:rpc:result',
  rendererReady: 'live2d:renderer:ready',
  rendererError: 'live2d:renderer:error',
  getRuntimeConfig: 'live2d:get-runtime-config',
  chatInputSubmit: 'live2d:chat:input:submit',
  chatPanelToggle: 'live2d:chat:panel-toggle',
  chatStateSync: 'live2d:chat:state-sync',
  chatStreamSync: 'live2d:chat:stream-sync',
  bubbleStateSync: 'live2d:bubble:state-sync',
  bubbleMetricsUpdate: 'live2d:bubble:metrics-update',
  modelBoundsUpdate: 'live2d:model:bounds-update',
  windowDrag: 'live2d:window:drag',
  windowControl: 'live2d:window:control',
  chatPanelVisibility: 'live2d:chat:panel-visibility',
  windowResizeRequest: 'live2d:window:resize-request',
  windowStateSync: 'live2d:window:state-sync',
  windowInteractivity: 'live2d:window:interactivity',
  toggleChatWindow: 'toggle-chat-window'
});

function normalizeWindowDragPayload(payload) {
  const action = String(payload?.action || '').trim().toLowerCase();
  if (!['start', 'move', 'end'].includes(action)) {
    return null;
  }

  const screenX = Number(payload?.screenX);
  const screenY = Number(payload?.screenY);
  if (!Number.isFinite(screenX) || !Number.isFinite(screenY)) {
    return null;
  }

  return {
    action,
    screenX: Math.round(screenX),
    screenY: Math.round(screenY)
  };
}

function createWindowDragListener({
  BrowserWindow,
  screen,
  margin = 8,
  maxOffscreenRatio = 0.8
} = {}) {
  const dragStates = new Map();
  return (event, payload) => {
    const normalized = normalizeWindowDragPayload(payload);
    if (!normalized) {
      return;
    }

    const sender = event?.sender;
    if (!sender || !BrowserWindow || typeof BrowserWindow.fromWebContents !== 'function') {
      return;
    }

    const win = BrowserWindow.fromWebContents(sender);
    if (!win || typeof win.getPosition !== 'function' || typeof win.setPosition !== 'function') {
      return;
    }

    const senderId = Number(sender.id);
    if (!Number.isFinite(senderId)) {
      return;
    }

    if (normalized.action === 'start') {
      const [windowX, windowY] = win.getPosition();
      dragStates.set(senderId, {
        cursorX: normalized.screenX,
        cursorY: normalized.screenY,
        windowX,
        windowY
      });
      return;
    }

    if (normalized.action === 'move') {
      const state = dragStates.get(senderId);
      if (!state) {
        return;
      }
      const nextX = Math.round(state.windowX + normalized.screenX - state.cursorX);
      const nextY = Math.round(state.windowY + normalized.screenY - state.cursorY);
      win.setPosition(nextX, nextY);
      return;
    }

    if (normalized.action === 'end') {
      dragStates.delete(senderId);
    }
  };
}

let modelServer = null;

function startModelServer(modelsPath, logger = console) {
  logger.log('Model server starting, models path:', modelsPath);
  return new Promise((resolve, reject) => {
    const server = http.createServer((req, res) => {
      // Decode URL to handle Chinese characters and other special characters
      const decodedUrl = decodeURIComponent(req.url);
      let filePath = path.join(modelsPath, decodedUrl);
      logger.log('Request:', req.url, '→ decoded:', decodedUrl, '→', filePath);

      fs.stat(filePath, (err, stat) => {
        if (err) {
          logger.log('404 Not Found:', filePath);
          res.writeHead(404);
          res.end('Not Found');
          return;
        }

        if (stat.isDirectory()) {
          res.writeHead(403);
          res.end('Directory listing not allowed');
          return;
        }

        const ext = path.extname(filePath);
        let contentType = 'application/octet-stream';

        switch (ext) {
          case '.json': contentType = 'application/json'; break;
          case '.png': contentType = 'image/png'; break;
          case '.jpg': contentType = 'image/jpeg'; break;
          case '.moc3': contentType = 'application/octet-stream'; break;
          case '.motion3.json': contentType = 'application/json'; break;
          case '.exp3.json': contentType = 'application/json'; break;
        }

        res.writeHead(200, { 'Content-Type': contentType });
        fs.createReadStream(filePath).pipe(res);
      });
    });

    server.on('error', reject);

    server.listen(0, '127.0.0.1', () => {
      const port = server.address().port;
      const url = `http://127.0.0.1:${port}`;
      logger.log(`Model server started on ${url}`);
      resolve({ server, url, port });
    });
  });
}

async function startDesktopSuite({
  app,
  BrowserWindow,
  ipcMain,
  screen,
  shell,
  dialog,
  assetRoot,
  workspaceRoot,
  pluginRoot,
  modelsRoot,
  onResizeModeChange,
  logger = console
} = {}) {
  const store = new Store();

  const defaultSettings = {
    server: {
      url: 'ws://localhost:6191/client-ws',
      autoConnect: true
    },
    models: {
      path: ''
    },
    window: {
      width: 600,
      height: 800,
      opacity: 1,
      clickThrough: false,
      alwaysOnTop: true,
      lockPosition: false
    },
    general: {
      autoStart: false,
      theme: 'auto'
    }
  };

  function getSettings() {
    const saved = store.get('settings', {});
    return {
      ...defaultSettings,
      ...saved,
      server: { ...defaultSettings.server, ...saved?.server },
      models: { ...defaultSettings.models, ...saved?.models },
      window: { ...defaultSettings.window, ...saved?.window },
      general: { ...defaultSettings.general, ...saved?.general }
    };
  }

  const settings = getSettings();
  let modelsPath = settings?.models?.path;
  if (!modelsPath || !fs.existsSync(modelsPath)) {
    if (modelsRoot && fs.existsSync(modelsRoot)) {
      modelsPath = modelsRoot;
    } else if (pluginRoot) {
      modelsPath = path.join(pluginRoot, 'live2d-models');
    } else {
      modelsPath = path.join(assetRoot, 'live2d-models');
    }
  }
  logger.log('Using models path:', modelsPath);
  const { server, url: modelServerUrl, port: modelServerPort } = await startModelServer(modelsPath, logger);
  modelServer = server;

  let window = null;
  let chatWindow = null;
  let resizeModeEnabled = false;
  let chatPanelVisible = false;
  let chatWindowPosition = 'right';

  function setSettings(key, value) {
    if (key) {
      store.set(`settings.${key}`, value);
    } else {
      store.set('settings', value);
    }
  }

  function createMainWindow() {
    const settings = getSettings();
    const savedBounds = store.get('window.bounds', {
      width: settings.window.width,
      height: settings.window.height,
      x: undefined,
      y: undefined
    });

    const win = new BrowserWindow({
      ...savedBounds,
      minWidth: 200,
      minHeight: 250,
      frame: false,
      transparent: true,
      backgroundColor: '#00000000',
      alwaysOnTop: settings.window.alwaysOnTop,
      skipTaskbar: true,
      resizable: true,
      minimizable: false,
      maximizable: false,
      hasShadow: false,
      acceptFirstMouse: true,
      webPreferences: {
        preload: path.join(__dirname, 'preload.js'),
        nodeIntegration: false,
        contextIsolation: true,
        sandbox: false,
        webSecurity: false,
        autoplayPolicy: 'no-user-gesture-required'
      }
    });

    win.setOpacity(settings.window.opacity);
    
    // 设置鼠标穿透
    if (typeof win.setIgnoreMouseEvents === 'function') {
      win.setIgnoreMouseEvents(settings.window.clickThrough || false, { forward: true });
    }

    win.on('move', () => {
      store.set('window.bounds', win.getBounds());
      positionChatWindow();
    });
    win.on('resize', () => {
      store.set('window.bounds', win.getBounds());
      positionChatWindow();
    });

    win.on('closed', () => {
      window = null;
    });

    const isDev = !app.isPackaged;
    if (isDev) {
      win.webContents.openDevTools({ mode: 'detach' });
    }

    win.loadFile(path.join(__dirname, 'index.html'));

    return win;
  }

  function createChatWindow() {
    const chatWin = new BrowserWindow({
      width: 320,
      height: 400,
      minWidth: 200,
      minHeight: 250,
      frame: false,
      transparent: true,
      backgroundColor: '#00000000',
      alwaysOnTop: true,
      skipTaskbar: true,
      resizable: true,
      minimizable: false,
      maximizable: false,
      hasShadow: false,
      show: false,
      webPreferences: {
        preload: path.join(__dirname, 'preload.js'),
        nodeIntegration: false,
        contextIsolation: true,
        sandbox: false,
        webSecurity: false
      }
    });

    chatWin.on('closed', () => {
      chatWindow = null;
    });

    const isDev = !app.isPackaged;
    if (isDev) {
      chatWin.webContents.openDevTools({ mode: 'detach' });
    }

    chatWin.loadFile(path.join(__dirname, 'chat.html'));

    return chatWin;
  }

  function positionChatWindow() {
    if (!window || window.isDestroyed() || !chatWindow || chatWindow.isDestroyed()) {
      return;
    }

    const [mainX, mainY] = window.getPosition();
    const [mainWidth, mainHeight] = window.getSize();
    const [chatWidth, chatHeight] = chatWindow.getSize();

    let chatX, chatY;

    if (chatWindowPosition === 'right') {
      chatX = mainX + mainWidth + 10;
    } else {
      chatX = mainX - chatWidth - 10;
    }

    chatY = mainY + (mainHeight - chatHeight) / 2;

    chatWindow.setPosition(Math.round(chatX), Math.round(chatY));
  }

  function showChatWindow() {
    if (!chatWindow) {
      chatWindow = createChatWindow();
      chatWindow.once('ready-to-show', () => {
        positionChatWindow();
        chatWindow.show();
      });
    } else if (!chatWindow.isDestroyed()) {
      positionChatWindow();
      chatWindow.show();
      chatWindow.focus();
    }
  }

  function hideChatWindow() {
    if (chatWindow && !chatWindow.isDestroyed()) {
      chatWindow.hide();
    }
  }

  function toggleChatWindow() {
    chatPanelVisible = !chatPanelVisible;
    if (chatPanelVisible) {
      showChatWindow();
    } else {
      hideChatWindow();
    }
  }

  function showPetWindows() {
    if (window && !window.isDestroyed()) {
      window.show();
      window.focus();
    }
  }

  function hidePetWindows() {
    if (window && !window.isDestroyed()) {
      window.hide();
    }
  }

  function setResizeModeEnabled(enabled) {
    resizeModeEnabled = Boolean(enabled);
    if (window && !window.isDestroyed()) {
      window.webContents.send(CHANNELS.windowStateSync, {
        resizeModeEnabled
      });
    }
    if (typeof onResizeModeChange === 'function') {
      onResizeModeChange(resizeModeEnabled);
    }
    return resizeModeEnabled;
  }

  function isResizeModeEnabled() {
    return resizeModeEnabled;
  }

  let savedClickThroughState = false;
  let settingsPanelOpen = false;

  function setClickThrough(enabled) {
    if (!window || window.isDestroyed()) {
      return;
    }
    if (typeof window.setIgnoreMouseEvents === 'function') {
      window.setIgnoreMouseEvents(enabled, { forward: true });
    }
    setSettings('window.clickThrough', enabled);
    if (settingsPanelOpen) {
      savedClickThroughState = enabled;
    }
  }

  function isClickThroughEnabled() {
    return getSettings()?.window?.clickThrough || false;
  }

  ipcMain.on('settings-panel-opened', () => {
    if (!window || window.isDestroyed()) return;
    settingsPanelOpen = true;
    savedClickThroughState = isClickThroughEnabled();
    if (savedClickThroughState) {
      if (typeof window.setIgnoreMouseEvents === 'function') {
        window.setIgnoreMouseEvents(false, { forward: true });
      }
    }
  });

  ipcMain.on('settings-panel-closed', () => {
    if (!window || window.isDestroyed()) return;
    settingsPanelOpen = false;
    if (savedClickThroughState) {
      if (typeof window.setIgnoreMouseEvents === 'function') {
        window.setIgnoreMouseEvents(true, { forward: true });
      }
    }
  });

  function toggleChatPanel() {
    toggleChatWindow();
  }

  const windowDragListener = createWindowDragListener({
    BrowserWindow,
    screen
  });

  ipcMain.on(CHANNELS.windowDrag, windowDragListener);

  ipcMain.handle(CHANNELS.getRuntimeConfig, async () => {
    const settings = getSettings();
    return {
      settings,
      resizeModeEnabled,
      assetRoot,
      workspaceRoot,
      modelServerUrl
    };
  });

  // 获取全局鼠标位置
  ipcMain.handle('live2d:get-global-mouse', async () => {
    if (!screen) {
      return { x: 0, y: 0 };
    }
    const point = screen.getCursorScreenPoint();
    return { x: point.x, y: point.y };
  });

  ipcMain.handle('settings:get', () => {
    return getSettings();
  });

  ipcMain.handle('settings:set', (event, key, value) => {
    setSettings(key, value);
    return true;
  });

  // 选择模型路径
  ipcMain.handle('settings:select-models-path', async () => {
    if (!dialog) {
      return { canceled: true };
    }
    const result = await dialog.showOpenDialog(window, {
      title: '选择 Live2D 模型文件夹',
      properties: ['openDirectory'],
    });
    if (!result.canceled && result.filePaths && result.filePaths.length > 0) {
      return { canceled: false, path: result.filePaths[0] };
    }
    return { canceled: true };
  });

  ipcMain.handle('settings:set-models-path-from-server', async (event, serverPath) => {
    if (serverPath && fs.existsSync(serverPath)) {
      logger.log('Received models_path from server:', serverPath);
      setSettings('models.path', serverPath);
      modelsPath = serverPath;
      
      if (modelServer) {
        modelServer.close();
      }
      const { server, url: modelServerUrl } = await startModelServer(modelsPath, logger);
      modelServer = server;
      
      if (window && !window.isDestroyed()) {
        window.webContents.send('models-path-updated', { 
          path: serverPath, 
          modelServerUrl: modelServerUrl 
        });
      }
      return { success: true, path: serverPath };
    }
    return { success: false, error: 'Path does not exist' };
  });

  // Chat window IPC handlers
  ipcMain.handle('chat:hide-window', () => {
    hideChatWindow();
  });

  ipcMain.handle('chat:send-message', (event, message) => {
    // Forward message to main window for WebSocket sending
    if (window && !window.isDestroyed()) {
      window.webContents.send('chat:message-from-panel', message);
    }
  });

  // Forward chat responses from main window to chat window
  ipcMain.on('chat:response', (event, message) => {
    if (chatWindow && !chatWindow.isDestroyed()) {
      chatWindow.webContents.send('chat:response', message);
    }
  });

  // Forward system messages from main window to chat window
  ipcMain.on('chat:system-message', (event, message) => {
    if (chatWindow && !chatWindow.isDestroyed()) {
      chatWindow.webContents.send('chat:system-message', message);
    }
  });

  ipcMain.on(CHANNELS.toggleChatWindow, () => {
    toggleChatPanel();
  });

  ipcMain.on(CHANNELS.chatPanelToggle, () => {
    toggleChatPanel();
  });

  ipcMain.on(CHANNELS.windowControl, (event, payload) => {
    const action = String(payload?.action || '').trim().toLowerCase();
    if (!window || window.isDestroyed()) {
      return;
    }

    if (action === 'minimize') {
      window.minimize();
    } else if (action === 'close') {
      window.hide();
    } else if (action === 'hide') {
      window.hide();
    }
  });

  ipcMain.on(CHANNELS.windowInteractivity, (event, payload) => {
    if (payload?.resizeModeEnabled !== undefined) {
      const enabled = Boolean(payload.resizeModeEnabled);
      setResizeModeEnabled(enabled);
      if (typeof onResizeModeChange === 'function') {
        onResizeModeChange(enabled);
      }
    }
  });

  ipcMain.on('tray:show-balloon', (event, title, content) => {
    logger.log(`[Balloon] ${title}: ${content}`);
  });

  window = createMainWindow();

  // 全局鼠标跟踪 - 让 Live2D 模型视线跟随整个桌面的鼠标
  let mouseTrackingInterval = null;
  let lastMouseX = null;
  let lastMouseY = null;

  function startGlobalMouseTracking() {
    if (mouseTrackingInterval) {
      return;
    }

    logger.log('启动全局鼠标跟踪');

    mouseTrackingInterval = setInterval(() => {
      if (!window || window.isDestroyed() || !screen) {
        return;
      }

      // 如果窗口最小化，暂停跟踪
      if (window.isMinimized()) {
        return;
      }

      try {
        const point = screen.getCursorScreenPoint();
        const [winX, winY] = window.getPosition();
        const winSize = window.getSize();
        const winCenterX = winX + winSize[0] / 2;
        const winCenterY = winY + winSize[1] / 2;

        // 计算鼠标相对于窗口中心的偏移
        const dx = point.x - winCenterX;
        const dy = point.y - winCenterY;

        // 归一化到 -1 到 1 范围（使用 500px 作为"活动区域"半径）
        const radius = 500;
        let normX = Math.max(-1, Math.min(1, dx / radius));
        let normY = Math.max(-1, Math.min(1, dy / radius));

        // 仅在位置变化较大时发送，减少 IPC 通信
        if (lastMouseX === null || lastMouseY === null ||
            Math.abs(normX - lastMouseX) > 0.02 ||
            Math.abs(normY - lastMouseY) > 0.02) {
          lastMouseX = normX;
          lastMouseY = normY;
          window.webContents.send('live2d:global-mouse', { x: normX, y: normY });
        }
      } catch (e) {
        // 忽略错误
      }
    }, 50); // 20fps 更新率
  }

  function stopGlobalMouseTracking() {
    if (mouseTrackingInterval) {
      clearInterval(mouseTrackingInterval);
      mouseTrackingInterval = null;
      logger.log('停止全局鼠标跟踪');
    }
  }

  // 窗口准备好后启动跟踪
  window.once('ready-to-show', () => {
    startGlobalMouseTracking();
  });

  return {
    window,
    chatWindow,
    showPetWindows,
    hidePetWindows,
    setResizeModeEnabled,
    isResizeModeEnabled,
    setClickThrough,
    isClickThroughEnabled,
    showChatWindow,
    hideChatWindow,
    toggleChatWindow,
    stop: async () => {
      stopGlobalMouseTracking();
      if (chatWindow && !chatWindow.isDestroyed()) {
        chatWindow.close();
      }
      if (window && !window.isDestroyed()) {
        window.close();
      }
      if (modelServer) {
        modelServer.close();
      }
    },
    summary: {
      assetRoot,
      workspaceRoot,
      modelServerUrl
    }
  };
}

module.exports = {
  CHANNELS,
  startDesktopSuite
};
