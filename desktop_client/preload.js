const { contextBridge, ipcRenderer } = require('electron');

const CHANNELS = {
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
};

contextBridge.exposeInMainWorld('desktopLive2dBridge', {
  onInvoke(handler) {
    const listener = (_event, payload) => handler(payload);
    ipcRenderer.on(CHANNELS.invoke, listener);
    return () => ipcRenderer.off(CHANNELS.invoke, listener);
  },
  sendResult(payload) {
    ipcRenderer.send(CHANNELS.result, payload);
  },
  notifyReady(payload = {}) {
    ipcRenderer.send(CHANNELS.rendererReady, payload);
  },
  notifyError(payload = {}) {
    ipcRenderer.send(CHANNELS.rendererError, payload);
  },
  sendChatInput(payload = {}) {
    ipcRenderer.send(CHANNELS.chatInputSubmit, payload);
  },
  sendChatPanelToggle(payload = {}) {
    ipcRenderer.send(CHANNELS.chatPanelToggle, payload);
  },
  sendModelBounds(payload = {}) {
    ipcRenderer.send(CHANNELS.modelBoundsUpdate, payload);
  },
  sendBubbleMetrics(payload = {}) {
    ipcRenderer.send(CHANNELS.bubbleMetricsUpdate, payload);
  },
  onChatStateSync(handler) {
    const listener = (_event, payload) => handler(payload);
    ipcRenderer.on(CHANNELS.chatStateSync, listener);
    return () => ipcRenderer.off(CHANNELS.chatStateSync, listener);
  },
  onChatStreamSync(handler) {
    const listener = (_event, payload) => handler(payload);
    ipcRenderer.on(CHANNELS.chatStreamSync, listener);
    return () => ipcRenderer.off(CHANNELS.chatStreamSync, listener);
  },
  onBubbleStateSync(handler) {
    const listener = (_event, payload) => handler(payload);
    ipcRenderer.on(CHANNELS.bubbleStateSync, listener);
    return () => ipcRenderer.off(CHANNELS.bubbleStateSync, listener);
  },
  sendWindowDrag(payload = {}) {
    ipcRenderer.send(CHANNELS.windowDrag, payload);
  },
  sendWindowControl(payload = {}) {
    ipcRenderer.send(CHANNELS.windowControl, payload);
  },
  sendWindowResize(payload = {}) {
    ipcRenderer.send(CHANNELS.windowResizeRequest, payload);
  },
  sendWindowInteractivity(payload = {}) {
    ipcRenderer.send(CHANNELS.windowInteractivity, payload);
  },
  sendChatPanelVisibility(payload = {}) {
    ipcRenderer.send(CHANNELS.chatPanelVisibility, payload);
  },
  onWindowStateSync(handler) {
    const listener = (_event, payload) => handler(payload);
    ipcRenderer.on(CHANNELS.windowStateSync, listener);
    return () => ipcRenderer.off(CHANNELS.windowStateSync, listener);
  },
  getRuntimeConfig() {
    return ipcRenderer.invoke(CHANNELS.getRuntimeConfig);
  }
});

contextBridge.exposeInMainWorld('electronAPI', {
  send: (channel, ...args) => {
    ipcRenderer.send(channel, ...args);
  },
  on: (channel, callback) => {
    const subscription = (_event, ...args) => callback(...args);
    ipcRenderer.on(channel, subscription);
    return () => ipcRenderer.off(channel, subscription);
  },
  invoke: (channel, ...args) => {
    return ipcRenderer.invoke(channel, ...args);
  },
  windowDrag: (action, screenX, screenY) => {
    ipcRenderer.send(CHANNELS.windowDrag, { action, screenX, screenY });
  },
  onBubbleStateSync: (callback) => {
    const handler = (_event, payload) => callback(payload);
    ipcRenderer.on(CHANNELS.bubbleStateSync, handler);
    return () => ipcRenderer.off(CHANNELS.bubbleStateSync, handler);
  },
  sendBubbleMetrics: (metrics) => {
    ipcRenderer.send(CHANNELS.bubbleMetricsUpdate, metrics);
  },
  setCaption: (caption) => {
    },
  showContextMenu: (x, y) => {
    ipcRenderer.send('show-context-menu', { x, y });
  },
  hideChatWindow: () => {
    ipcRenderer.invoke('chat:hide-window');
  },
  sendChatMessage: (message) => {
    ipcRenderer.invoke('chat:send-message', message);
  },
  onChatResponse: (callback) => {
    const handler = (_event, payload) => callback(payload);
    ipcRenderer.on('chat:response', handler);
    return () => ipcRenderer.off('chat:response', handler);
  },
  onChatSystemMessage: (callback) => {
    const handler = (_event, payload) => callback(payload);
    ipcRenderer.on('chat:system-message', handler);
    return () => ipcRenderer.off('chat:system-message', handler);
  },
  onOpenSettings: (callback) => {
    const handler = (_event) => callback();
    ipcRenderer.on('settings:open', handler);
    return () => ipcRenderer.off('settings:open', handler);
  },
  getSettings: () => {
    return ipcRenderer.invoke('settings:get');
  },
  setSettings: (key, value) => {
    return ipcRenderer.invoke('settings:set', key, value);
  },
  setModelsPath: (path) => {
    return ipcRenderer.invoke('settings:set-models-path-from-server', path);
  }
});

contextBridge.exposeInMainWorld('mouseTracker', {
  getGlobalPosition: () => {
    return ipcRenderer.invoke('live2d:get-global-mouse');
  },
  onGlobalMouseMove: (callback) => {
    const listener = (_event, payload) => callback(payload);
    ipcRenderer.on('live2d:global-mouse', listener);
    return () => ipcRenderer.off('live2d:global-mouse', listener);
  }
});
