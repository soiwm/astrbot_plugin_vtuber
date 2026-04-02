# AstrBot VTuber Desktop Client

基于 Electron + Vue 3 的 VTuber 桌面客户端。

## 功能特性

- Live2D 虚拟形象展示
- WebSocket 实时通信
- 透明悬浮窗
- 系统托盘
- 全局快捷键
- 点击穿透模式
- 窗口透明度调节

## 开发

```bash
# 安装依赖
npm install

# 开发模式
npm run dev

# 构建
npm run build
```

## 配置

默认连接到 `ws://localhost:6191/client-ws`，可在设置中修改。

## 技术栈

- Electron 30
- Vue 3
- Vite
- Pinia
- Naive UI
