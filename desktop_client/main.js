const path = require('node:path');
const fs = require('node:fs');
const { app, BrowserWindow, ipcMain, screen, shell, Tray, Menu, nativeImage, dialog } = require('electron');
const Store = require('electron-store');

const { startDesktopSuite } = require('./desktopSuite');
const { createTrayController } = require('./trayController');

function resolveDesktopPathRoots({ isPackaged, appPath, customModelsPath }) {
  const projectRoot = isPackaged ? path.dirname(appPath) : __dirname;
  const assetRoot = projectRoot;

  if (customModelsPath && fs.existsSync(customModelsPath)) {
    console.log('Using custom models path:', customModelsPath);
    return {
      projectRoot,
      assetRoot,
      modelsRoot: customModelsPath,
      isStandalone: true
    };
  }

  try {
    const pluginRoot = path.join(projectRoot, '..');
    const workspaceRoot = path.join(projectRoot, '..', '..', '..', '..');
    const modelsRoot = path.join(pluginRoot, 'live2d-models');

    console.log('Plugin mode - live2d-models exists:', fs.existsSync(modelsRoot));

    if (fs.existsSync(pluginRoot) && fs.existsSync(modelsRoot)) {
      return {
        projectRoot,
        assetRoot,
        workspaceRoot,
        pluginRoot,
        modelsRoot,
        isStandalone: false
      };
    }
  } catch (e) {
    console.log('Failed to resolve plugin paths, falling back to standalone mode');
  }

  const standaloneModelsRoot = path.join(projectRoot, 'live2d-models');
  console.log('Standalone mode - using models path:', standaloneModelsRoot);

  return {
    projectRoot,
    assetRoot,
    modelsRoot: standaloneModelsRoot,
    isStandalone: true
  };
}

let suite = null;
let trayController = null;
let shuttingDown = false;
let bootstrapPromise = null;

const gotSingleInstanceLock = app.requestSingleInstanceLock();
if (!gotSingleInstanceLock) {
  app.quit();
}

async function bootstrap() {
  if (bootstrapPromise) {
    return bootstrapPromise;
  }

  bootstrapPromise = (async () => {
    if (suite?.window && !suite.window.isDestroyed()) {
      return suite;
    }

    const store = new Store();
    const savedSettings = store.get('settings', {});
    const customModelsPath = savedSettings?.models?.path;

    const roots = resolveDesktopPathRoots({
      isPackaged: app.isPackaged,
      appPath: app.getAppPath(),
      customModelsPath
    });

    suite = await startDesktopSuite({
      app,
      BrowserWindow,
      ipcMain,
      screen,
      shell,
      dialog,
      assetRoot: roots.assetRoot,
      workspaceRoot: roots.workspaceRoot,
      pluginRoot: roots.pluginRoot,
      modelsRoot: roots.modelsRoot,
      onResizeModeChange: (enabled) => {
        trayController?.setResizeModeEnabled(enabled);
      },
      logger: console
    });

    if (!trayController) {
      trayController = createTrayController({
        Tray,
        Menu,
        nativeImage,
        projectRoot: roots.assetRoot,
        onShow: () => {
          showPetWindow();
        },
        onHide: () => {
          hidePetWindow();
        },
        onToggleResizeMode: (enabled) => {
          const nextEnabled = suite?.setResizeModeEnabled
            ? suite.setResizeModeEnabled(enabled)
            : Boolean(enabled);
          trayController?.setResizeModeEnabled(nextEnabled);
        },
        isResizeModeEnabled: () => suite?.isResizeModeEnabled?.() || false,
        onToggleClickThrough: (enabled) => {
          if (suite?.setClickThrough) {
            suite.setClickThrough(enabled);
          }
          trayController?.setClickThroughEnabled(enabled);
        },
        isClickThroughEnabled: () => suite?.isClickThroughEnabled?.() || false,
        onOpenSettings: () => {
          if (suite?.window && !suite.window.isDestroyed()) {
            suite.window.webContents.send('settings:open');
          }
        },
        onQuit: () => {
          app.quit();
        }
      });
    } else if (suite?.isResizeModeEnabled) {
      trayController.setResizeModeEnabled(suite.isResizeModeEnabled());
    }

    showPetWindow();

    return suite;
  })();

  try {
    await bootstrapPromise;
  } finally {
    bootstrapPromise = null;
  }
}

function hidePetWindow() {
  if (suite?.hidePetWindows) {
    suite.hidePetWindows();
    return;
  }
  if (suite?.window && !suite.window.isDestroyed()) {
    suite.window.hide();
  }
}

function showPetWindow() {
  if (suite?.showPetWindows) {
    suite.showPetWindows();
    return;
  }
  if (suite?.window && !suite.window.isDestroyed()) {
    suite.window.show();
    suite.window.focus();
    return;
  }
  void bootstrap().catch((err) => {
    console.error('[astrbot-vtuber] tray show failed', err);
  });
}

async function teardown() {
  if (shuttingDown) return;
  shuttingDown = true;

  if (trayController) {
    trayController.destroy();
    trayController = null;
  }
  if (suite) {
    await suite.stop();
    suite = null;
  }
}

app.whenReady().then(bootstrap).catch(async (err) => {
  console.error('[astrbot-vtuber] bootstrap failed', err);
  await teardown();
  app.quit();
});

app.on('before-quit', async () => {
  await teardown();
});

app.on('window-all-closed', () => {
});

app.on('activate', async () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    showPetWindow();
    return;
  }
  showPetWindow();
});

app.on('second-instance', () => {
  if (suite?.window && !suite.window.isDestroyed()) {
    if (suite.window.isMinimized?.()) {
      suite.window.restore();
    }
    showPetWindow();
    return;
  }

  void bootstrap().then(() => {
    showPetWindow();
  }).catch((err) => {
    console.error('[astrbot-vtuber] second-instance bootstrap failed', err);
  });
});

ipcMain.on('show-context-menu', (event, { x, y }) => {
  if (trayController?.menu && suite?.window && !suite.window.isDestroyed()) {
    trayController.menu.popup({
      window: suite.window,
      x: Math.round(x),
      y: Math.round(y)
    });
  }
});
