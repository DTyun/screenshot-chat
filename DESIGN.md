---
version: alpha
name: 截图聊天
description: 微信风格的本地截图、文字与图片聊天工具
colors:
  primary: '#00C878'
  primary-hover: '#00B46B'
  background: '#FAFAFA'
  panel: '#EFEFF1'
  rail: '#E2E3E7'
  surface: '#FAFAFA'
  text: '#242424'
  muted: '#92929C'
  border: '#E2E2E6'
  selected: '#E2E2E5'
  danger: '#C53939'
  thumb: '#B8B8BE'
typography:
  sans:
    fontFamily: Microsoft YaHei UI
  mono:
    fontFamily: Consolas
rounded:
  DEFAULT: 4px
spacing:
  section-gap: 24px
components:
  button: {}
  dialog: {}
  message: {}
---

# 截图聊天 Design System

## Overview

### Creative North Star
以用户在 2026-10-19 提供的 Windows 微信新版截图为参照：浅灰窄侧栏、浅灰会话栏、近白色消息区、底部圆角输入区。
用户明确要求采用参考图的风格和配色；最新识别元素为绿色方底、白色剪刀，简洁清晰，适合托盘小尺寸显示。

### Product context and register
中国中文 Windows 用户；产品工具界面；简体中文。截图、文字与图片消息、多聊天、新建重命名、聊天内容查找、可迁移缓存目录。
所有图片只存本机，不登录、不联网发送。没有已有 sibling workflow；设置窗口复用主界面的按钮与反馈语汇。
避免深色侧栏、营销页面、大卡片、渐变背景和多余功能。
Token ownership: Model B，`src/theme.py::COLORS` 为运行时色彩源，`stylesheet()` 统一转换为 Qt QSS；本文件镜像色值。
`MessageDelegate` 通过同一 COLORS 取色。系统原生高对比度模式未宣称专门适配。

## Colors
primary 用于亮绿色发送和会话图标；灰色建立区域层级；danger 只用于删除。主消息区与输入区同为近白底色。

## Typography
Microsoft YaHei UI，正文 13px，说明 12px，标题 16px/500；不使用斜体。数据保持原始尺寸文字可读。

## Layout
默认 1040×760，最小 760×560。左栏 64px、会话栏 216px，剩余宽度归对话。
图片消息区独立滚动，发送区始终可见。每批 40 条，通过“查看更早的图片”向前加载并保留浏览位置。

## Elevation & Depth
平面底色和一像素分隔线；不添加阴影。截图时用暗色遮罩凸显选区。

## Shapes
普通控件圆角 4px，会话卡片 5px，发送按钮 6px，输入区 10px。剪刀 logo 采用绿色方底、纯白剪刀，增强小尺寸识别。

## Components
### Foundational visual states
按钮定义 hover、pressed、focus、disabled；发送无图片时禁用。
聊天消息的选中/焦点态只描边，画边框前显式使用 Qt.NoBrush，不能用残留填充覆盖原图或备注文字。
主窗口状态栏统一显示成功和错误；失败保留待发送图片。
### Buttons and actions
发送使用 primary，删除使用 danger，其余灰底 hover。按钮尺寸不随状态变化。
### Navigation and data display
左侧名称搜索与＋新建聊天，列表右键重命名。消息右对齐，文字使用浅绿气泡，图片保持原样，时间居中。
查找聊天内容使用独立对话框，提供关键词及全部/文字/图片过滤和定位；输入区支持多行文字及图片备注，工具栏与发送按钮置于底部。
输入区由 `src/composer.py::ChatEditor`（Qt QTextEdit）统一拥有，图片作为行内对象与文字共用整个可编辑区域；不保留独立图片 QLabel 或说明行。反馈移入底部工具栏；“移除图片”保留其他文字。草稿保存文档、原图资源和光标位置。
### Forms and overlays
SettingsDialog 管理快捷键，输入为 Qt 原生 QKeySequenceEdit，最多一个组合。
开机启动使用 Qt 原生 QCheckBox，以注册表实际值回显，保存时应用，取消时不修改。顶部为浅灰色自绘标题栏，保留拖动、双击最大化和边缘缩放；置顶按钮选中时显示浅绿色底。
缓存路径使用只读路径框与系统目录选择器，默认勾选迁移；迁移时使用应用模态进度窗口、后台复制和数据库快照，失败保留原目录。
ConfirmDelete 为应用 QDialog，说明原图和记录一起删除，默认聚焦取消。
### Iconography
assets/scissors.png 为 imagegen 生成的绿色方底白剪刀 logo，派生包含 16–256px 的多尺寸 scissors.ico；窗口、托盘与头像统一引用。侧栏聊天图标使用代码绘制的绿色气泡，其他工具配中文提示及 accessibleName。
### Motion
消息列表滚轮使用 MessageHistory.wheelEvent 统一处理：每 120 角度单位移动 40 逻辑像素，160ms OutCubic 过渡，目标最多领先当前位置 120px。高精度滚轮按比例累积，触摸板 pixelDelta 原样使用；滚动条和程序定位优先，用户反向立即反向，不保留长惯性。参数由 src/theme.py 的 MESSAGE_WHEEL_* 统一维护。
无装饰动画；截图前延迟 220ms 等待窗口隐藏完成。
按用户最新要求，点击截图工具栏 ✓ / Enter 确定后，复制到剪贴板并打开当前聊天，将截图插入统一输入框；保留已有草稿，发送前可继续编辑。取消截图恢复原先显隐状态，不激活隐藏的窗口。
框选松开后出现 `src/capture.py::SelectionOverlay` 自有工具栏，矩形/圆形/箭头/画笔/文字/马赛克；红绿蓝黄为标注色，3/5/8 为逻辑像素线宽。Ctrl+Z 撤销，Ctrl+S 保存，✓/Enter 完成并放入聊天输入框，Esc/× 取消。只有完成后才写剪贴板。
### Content and data visualization
历史记录由 MessageHistory 管理文字选区，与 MessageDelegate.text_layout 共用布局与命中范围。文本使用 QTextDocument 的原生光标位置处理 UTF-16、中文与 emoji；选择只高亮文字，不填充图片。Ctrl+C 优先复制选区，右键保留复制所选/全文/原图；切换或清空记录时移除选区，历史仍只读。
关于软件复用 AboutDialog，可从设置和托盘进入；显示绿色 logo、软件名称、src/version.py 单一来源的版本号、作者 X 和仓库可点击链接、MIT 项目代码许可与 Qt/PySide6 依赖说明。
左下工具区采用共同底边与 100px 等高区域：左侧设置/收起均为 20px 线形图标、44×36 点击区；快捷键标题与数值居中，底部 36px“修改快捷键”按钮与收起按钮横向对齐。两列底边距统一 16px，上下行间距 8px，保持窄窗口下的对称和对齐。
聊天列表右键菜单提供重命名与删除。删除聊天复用 `ConfirmDelete`，显示名称和不可撤销说明，涵盖全部文字、本地原图与缩略图；取消默认聚焦。当前聊天被删后显示其他聊天，最后一个被删后新建空“我的图片”。文件与数据库删除由 `Store.delete_conversation` 统一处理，出错回滚。
标题栏四个窗口按钮由 `CaptionButton` 直接绘制统一矢量图形：44×34 点击区域、12px 图标网格、1.2px 灰色线条，常态透明无边框，不使用字体符号或有底色的位图。置顶状态仅改变图标颜色；悬停显示轻背景，关闭悬停红底白线；键盘导航时提供焦点提示。
主窗口四个外角统一采用 10px 圆角，由 `MainWindow.update_window_corners` 裁剪整个窗口，避免标题栏和侧栏覆盖圆角。最大化时取消裁剪贴合屏幕，恢复窗口后重新应用；调整大小与置顶重建窗口后同步更新。
聊天图片双击使用 `src/viewer.py::ImageViewer` 在软件内读取原图。浅灰背景，按比例适应窗口；原生标题栏仅保留关闭按钮，无编辑工具栏。滚轮缩放、拖动查看、Esc 关闭；重复打开复用窗口并重置适应尺寸，不修改图片文件。
中文动作使用“截图 / 粘贴图片 / 发送 / 复制图片 / 删除图片”。时间使用本机本地时间；无图表。

## Do's and Don'ts
- 保持图片原尺寸存储，显示时只缩放缩略图。
- 快捷键占用提示后保留原来的有效组合。
- 不增加联系人、OCR、涂鸦或网络发送。仅实现用户明确新增的本地多聊天与搜索功能。
- 不以生成示例冒充用户历史记录；预览素材只存在测试目录。
