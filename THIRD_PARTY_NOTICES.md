# 第三方组件与源代码

截图聊天的项目代码和自制图标按根目录 `LICENSE`（MIT）发布。
此许可不改变 Python、Qt、PySide6、Shiboken 或其他第三方组件的许可。

## 运行组件

| 组件 | 版本 | 许可及材料 |
|---|---|---|
| Python | 3.13.15 | PSF License 及其所含组件许可，`licenses/Python-3.13.txt` |
| Qt Base | 6.12.0 | LGPLv3，本项目使用 Core、Gui、Widgets、Network、OpenGL 共享库；`licenses/qtbase/` |
| Qt SVG / Image Formats | 6.12.0 | LGPLv3 及内含第三方许可，`licenses/qtsvg/`、`licenses/qtimageformats/` |
| PySide6 Essentials / Shiboken6 | 6.12.0 | LGPLv3，`licenses/pyside/` |
| PyInstaller bootloader | 6.22.3 | GPLv2-or-later with bootloader exception，`licenses/PyInstaller-COPYING.txt` |

完整 LGPLv3 与 GPLv3 文本位于 `licenses/LGPL-3.0.txt`、`licenses/GPL-3.0.txt`。
Qt 官方许可说明：https://doc.qt.io/qtforpython-6/licenses.html
Qt LGPL 说明：https://www.qt.io/development/open-source-lgpl-obligations

本项目未修改 Qt / PySide6 / Shiboken 的上游代码，动态加载共享库。
未使用 Qt PDF、Qt WebEngine 或 Qt Virtual Keyboard；构建钩子排除无关插件。

## 对应源代码

与 Windows 二进制一起发布的以下完整上游源代码附件可从同一 Release 免费下载：

https://github.com/DTyun/screenshot-chat/releases/tag/v1.0.0

- `qtbase-everywhere-src-6.12.0.tar.xz`
- `qtsvg-everywhere-src-6.12.0.tar.xz`
- `qtimageformats-everywhere-src-6.12.0.tar.xz`
- `pyside-setup-everywhere-src-6.12.0.tar.xz`（包含 PySide6 与 Shiboken）

官方原始来源：

- https://download.qt.io/official_releases/qt/6.12/6.12.0/submodules/
- https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.12.0-src/
- https://www.python.org/downloads/release/python-31315/
- https://github.com/pyinstaller/pyinstaller/tree/v6.22.3

## 替换共享库和重建

允许用户修改、替换 LGPL 组件，并为调试这些修改进行逆向工程。
本项目没有签名锁、设备锁或阻止替换组件的校验。

1. 从本仓库获取与 Release 对应的完整项目源代码；源码构建步骤见 README。
2. 按上述 Qt / PySide 源代码中的构建说明生成 ABI 兼容的 Windows x64 库。
3. 在独立 Python 环境中安装自己构建的 PySide6 / Shiboken wheel，或替换其中对应的 Qt DLL。
4. 运行 `main.py` 测试，随后执行 `build.ps1` 重新打包。打包工具会使用该环境中的共享库。

图标是按用户要求生成的绿色底白色剪刀；没有复用微信商标或其应用图标。
