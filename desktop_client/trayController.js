const fs = require('node:fs');
const path = require('node:path');

const TRAY_TOOLTIP = 'AstrBot VTuber';
const TRAY_ICON_RELATIVE_PATHS = [
  path.join('public', 'assets', 'logo.png'),
  path.join('assets', 'logo.png')
];
const TRAY_ICON_RELATIVE_PATH = TRAY_ICON_RELATIVE_PATHS[0];

function resolveTrayIconPath({ projectRoot = process.cwd() } = {}) {
  const candidateRoots = [
    projectRoot,
    process.resourcesPath,
    path.join(process.resourcesPath || '', 'app.asar')
  ].filter(Boolean);

  for (const root of candidateRoots) {
    for (const relativePath of TRAY_ICON_RELATIVE_PATHS) {
      const candidate = path.resolve(root, relativePath);
      if (fs.existsSync(candidate)) {
        return candidate;
      }
    }
  }

  return path.resolve(projectRoot, TRAY_ICON_RELATIVE_PATHS[0]);
}

function createTrayImage({ nativeImage, iconPath, size = 18 } = {}) {
  if (!nativeImage || typeof nativeImage.createFromPath !== 'function') {
    return null;
  }

  try {
    const icon = nativeImage.createFromPath(iconPath);
    if (!icon || typeof icon.isEmpty !== 'function' || icon.isEmpty()) {
      return null;
    }

    if (typeof icon.resize !== 'function') {
      return icon;
    }

    return icon.resize({
      width: size,
      height: size,
      quality: 'best'
    });
  } catch {
    return null;
  }
}

function createTrayController({
  Tray,
  Menu,
  nativeImage,
  projectRoot = process.cwd(),
  tooltip = TRAY_TOOLTIP,
  onShow = null,
  onHide = null,
  onToggleResizeMode = null,
  isResizeModeEnabled = null,
  onToggleClickThrough = null,
  isClickThroughEnabled = null,
  onOpenSettings = null,
  onQuit = null
} = {}) {
  if (typeof Tray !== 'function' || !Menu || typeof Menu.buildFromTemplate !== 'function') {
    throw new Error('createTrayController requires Electron Tray/Menu');
  }

  const iconPath = resolveTrayIconPath({ projectRoot });
  const icon = createTrayImage({ nativeImage, iconPath });
  const tray = new Tray(icon || nativeImage?.createEmpty?.());

  if (typeof tray.setToolTip === 'function') {
    tray.setToolTip(tooltip);
  }

  let resizeModeEnabled = typeof isResizeModeEnabled === 'function'
    ? Boolean(isResizeModeEnabled())
    : false;

  let clickThroughEnabled = typeof isClickThroughEnabled === 'function'
    ? Boolean(isClickThroughEnabled())
    : false;

  function buildMenu() {
    return Menu.buildFromTemplate([
      {
        label: '显示 Live2D',
        click: () => {
          if (typeof onShow === 'function') {
            void onShow();
          }
        }
      },
      {
        label: '隐藏 Live2D',
        click: () => {
          if (typeof onHide === 'function') {
            onHide();
          }
        }
      },
      {
        label: '调整大小模式',
        type: 'checkbox',
        checked: resizeModeEnabled,
        click: (menuItem) => {
          resizeModeEnabled = Boolean(menuItem?.checked);
          if (typeof onToggleResizeMode === 'function') {
            onToggleResizeMode(resizeModeEnabled);
          }
        }
      },
      {
        label: '窗口穿透',
        type: 'checkbox',
        checked: clickThroughEnabled,
        click: (menuItem) => {
          clickThroughEnabled = Boolean(menuItem?.checked);
          if (typeof onToggleClickThrough === 'function') {
            onToggleClickThrough(clickThroughEnabled);
          }
        }
      },
      { type: 'separator' },
      {
        label: '设置',
        click: () => {
          if (typeof onOpenSettings === 'function') {
            onOpenSettings();
          }
        }
      },
      { type: 'separator' },
      {
        label: '退出',
        click: () => {
          if (typeof onQuit === 'function') {
            onQuit();
          }
        }
      }
    ]);
  }

  let menu = buildMenu();

  if (typeof tray.setContextMenu === 'function') {
    tray.setContextMenu(menu);
  }

  if (typeof tray.on === 'function') {
    tray.on('click', () => {
      if (typeof onShow === 'function') {
        void onShow();
      }
    });

    tray.on('double-click', () => {
      if (typeof onShow === 'function') {
        void onShow();
      }
    });
  }

  return {
    tray,
    get menu() {
      return menu;
    },
    iconPath,
    setResizeModeEnabled(enabled) {
      resizeModeEnabled = Boolean(enabled);
      menu = buildMenu();
      if (typeof tray.setContextMenu === 'function') {
        tray.setContextMenu(menu);
      }
    },
    setClickThroughEnabled(enabled) {
      clickThroughEnabled = Boolean(enabled);
      menu = buildMenu();
      if (typeof tray.setContextMenu === 'function') {
        tray.setContextMenu(menu);
      }
    },
    destroy() {
      if (typeof tray?.destroy === 'function') {
        tray.destroy();
      }
    }
  };
}

module.exports = {
  TRAY_TOOLTIP,
  TRAY_ICON_RELATIVE_PATH,
  TRAY_ICON_RELATIVE_PATHS,
  resolveTrayIconPath,
  createTrayImage,
  createTrayController
};
