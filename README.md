# 截图聊天

微信风格的 Windows 本地截图、文字与图片记录工具。无需账号，聊天与图片保存在本机。

**版本 1.0.0 · Windows 10/11 x64 · MIT**

[下载最新版本](https://github.com/DTyun/screenshot-chat/releases/latest) · [作者 X：@yumi202607](https://x.com/yumi202607) · [更新记录](CHANGELOG.md)

![软件界面](docs/images/main-window.png)

## 下载与运行

在 [Releases](https://github.com/DTyun/screenshot-chat/releases/latest) 下载 `ScreenshotChat-v1.0.0-win64.zip`，解压后双击 **截图聊天.exe**，无需安装 Python。也可下载单文件 EXE；许可材料同时嵌入程序。

升级前先从托盘退出旧版。历史记录默认保存在用户目录，替换程序不会删除聊天。

## 功能

- 自定义全局截图快捷键，默认 **Ctrl+Alt+A**。
- 框选后标注：矩形、圆形、箭头、画笔、文字、马赛克，支持颜色、粗细、撤销和保存。
- 可编辑的图文输入框；发送文字、多张图片及图片备注。
- 多个本地聊天，可新建、重命名、确认删除；按文字、图片、日期查找并定位。
- 图片双击用内置只读窗口查看，支持缩放和拖动。
- 图片和文字右键复制、删除；删除聊天时确认后同时删除文字、原图和缩略图。
- 托盘常驻、单实例、开机启动勾选、窗口置顶、最大化与圆角。
- 自选缓存文件夹，默认迁移原记录，也可不迁移。
- “关于软件”显示版本、X 账号链接和开源信息。

## 使用

1. 按截图快捷键框选屏幕，松开后出现标注工具栏。点击 **✓ / Enter** 完成，会复制图片并打开聊天，将截图插入输入框；按 **Esc** 取消。
2. 直接输入文字，或 **Ctrl+V** 粘贴图片。文字与图片共用整个输入区，可选择、删除、替换、撤销；支持连续粘贴多张图。
3. **Enter / Ctrl+Enter** 发送，**Shift+Enter** 换行。发送将原图和文字保存到当前本地聊天。
4. 点击左上 **＋** 新建聊天。右键聊天可重命名或删除；删除会先弹窗确认，无法撤销。删除最后一个聊天会新建空的“我的图片”。
5. 点击 **查找聊天内容** 搜索当前聊天，并定位到消息。不包含图片 OCR。
6. 在 **截图设置** 修改快捷键、开机启动和缓存文件夹。设置窗口左下可进入 **关于软件**，也可通过托盘右键进入。

关闭、最小化或收起按钮会进入右下角托盘；托盘右键 **退出截图聊天** 才真正退出。重复运行只唤起已有窗口。

“发送”仅保存到本机，不发送给微信好友或网络服务。退出程序后未发送草稿不保留。

## 数据与备份

默认目录为 `%LOCALAPPDATA%\Pianyu`，沿用原目录名以兼容早期版本。

| 内容 | 文件/目录 |
|---|---|
| 原图 | `images/` |
| 缩略图 | `thumbnails/` |
| 消息与聊天索引 | `history.db` |
| 设置 | `settings.json` |
| 错误日志 | `app.log` |
| 缓存位置指针 | 默认目录下的 `location.json` |

更改缓存位置时默认复制并校验记录与图片，旧目录保留备份；目标应为空。选择不迁移会使用目标已有记录或建立空库。迁移失败保留旧库。

备份时先退出程序，再复制整个当前缓存目录。仓库和发行包不包含用户聊天或截图缓存。

## 源码运行与构建

使用 Windows x64、Python 3.13、PowerShell：

```powershell
git clone https://github.com/DTyun/screenshot-chat.git
cd screenshot-chat
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
./.venv/Scripts/python.exe main.py
```

生成独立 EXE（版本号统一维护于 `src/version.py`）：

```powershell
./build.ps1
```

输出 `dist/截图聊天.exe`。构建脚本会生成 Windows 版本元数据，并内置项目协议和第三方许可。`hooks/` 排除未使用的 PDF 与虚拟键盘插件。

```powershell
./.venv/Scripts/python.exe -m pytest -q
./.venv/Scripts/python.exe tests/render_preview.py
```

`desktop_smoke.py` 和 `packaged_smoke.py` 会打开测试窗口、写入剪贴板或启动程序，运行前应退出正式程序。测试使用独立的 `artifacts/test-data/`，不修改正式聊天。

## 许可与依赖

项目代码和自制图标使用 [MIT License](LICENSE)，Copyright (c) 2026 yumi202607。

依赖 Python、Qt、PySide6 和 Shiboken，分别保留原许可；详见 [第三方组件说明](THIRD_PARTY_NOTICES.md) 和 `licenses/`。同一 Release 提供对应 Qt / PySide 源代码包和替换共享库的构建说明。

## 范围与限制

本地工具，不提供账号、联系人、云同步、OCR 或联网聊天。单次选区位于一个显示器内，不提供跨屏拼接。混合 DPI、多屏 HDR 和另一台干净 Windows 设备尚未完成验证。

最初参考调研：[PathSnip](https://github.com/mcheiyue/PathSnip)、[MiniSnip](https://github.com/Mirochill/MiniSnip)、[WinShot](https://github.com/mrgoonie/winshot)。本项目独立实现，没有复制这些项目的代码或微信商标。
