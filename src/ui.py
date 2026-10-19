from pathlib import Path
from datetime import datetime
import sys
import sqlite3
import ctypes
from ctypes import wintypes

from PySide6.QtCore import Qt, QSize, QRect, QRectF, QPointF, QTimer, QEvent
from PySide6.QtGui import QPixmap, QIcon, QImage, QPainter, QColor, QKeySequence, QShortcut, QDesktopServices, QPen, QTextDocument, QFont, QPainterPath, QRegion, QTextCursor, QAbstractTextDocumentLayout
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QFrame, QLabel, QPushButton,
    QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem, QAbstractItemView,
    QStyledItemDelegate, QMenu, QDialog, QKeySequenceEdit, QSystemTrayIcon, QStyle, QCheckBox, QLineEdit, QFileDialog, QSizePolicy)

from .capture import CaptureSession
from .platform_win import Startup
from .theme import COLORS, stylesheet, WINDOW_CORNER_RADIUS
from .composer import ChatEditor
from .version import APP_NAME, APP_VERSION, AUTHOR, AUTHOR_URL, REPOSITORY_URL
from .history import MessageHistory
from .app_logging import logger,active_log_path,configure_logging


def asset(name):
    return Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent)) / 'assets' / name


def label(text, name=None):
    w = QLabel(text)
    if name:
        w.setObjectName(name)
    return w


def button(text, callback, name=None, tip=None):
    w = QPushButton(text)
    w.setCursor(Qt.PointingHandCursor)
    w.setAccessibleName(tip or text)
    if name:
        w.setObjectName(name)
    if tip:
        w.setToolTip(tip)
    w.clicked.connect(callback)
    return w


def chat_icon():
    pix = QPixmap(32, 32)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(COLORS['primary']))
    p.drawRoundedRect(3,5,26,19,8,8)
    p.setPen(QPen(QColor(COLORS['primary']), 3))
    p.drawLine(9,21,6,27)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor('white'))
    for x in (9,15,21):
        p.drawEllipse(x,13,3,3)
    p.end()
    return QIcon(pix)


def rail_icon(symbol):
    pix = QPixmap(40,40)
    pix.fill(Qt.transparent)
    pix.setDevicePixelRatio(2)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor('#686970'),1.4,Qt.SolidLine,Qt.RoundCap,Qt.RoundJoin))
    if symbol == 'settings':
        for y,x in ((4,7),(10,13),(16,8)):
            p.drawLine(QPointF(3,y),QPointF(x-2,y))
            p.drawLine(QPointF(x+2,y),QPointF(17,y))
            p.drawEllipse(QPointF(x,y),2,2)
    elif symbol == 'logs':
        p.drawRoundedRect(QRectF(4,2,12,16),2,2)
        p.drawLine(7,6,13,6)
        p.drawLine(7,10,13,10)
        p.drawLine(7,14,11,14)
    else:
        p.drawLine(15,5,5,15)
        p.drawLine(5,8,5,15)
        p.drawLine(5,15,12,15)
    p.end()
    return QIcon(pix)


class ChatNameDialog(QDialog):
    def __init__(self, parent, title, initial):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setFixedWidth(360)
        body = QVBoxLayout(self)
        body.setContentsMargins(24,24,24,24)
        body.setSpacing(14)
        body.addWidget(label(title, 'title'))
        self.editor = QLineEdit(initial)
        self.editor.setMaxLength(40)
        self.editor.setPlaceholderText('输入聊天名称')
        self.editor.setAccessibleName('聊天名称')
        body.addWidget(self.editor)
        self.error = label('', 'status')
        body.addWidget(self.error)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(button('取消', self.reject))
        row.addWidget(button('保存', self.save, 'primary'))
        body.addLayout(row)
        self.editor.returnPressed.connect(self.save)
        self.editor.selectAll()
        self.editor.setFocus()

    def save(self):
        value = self.editor.text().strip()
        if not value:
            self.error.setText('请输入聊天名称')
            return
        self.value = value
        self.accept()


class MessageDelegate(QStyledItemDelegate):
    def __init__(self, store, parent):
        super().__init__(parent)
        self.store = store
        self.avatar = QPixmap(str(asset('scissors.png'))).scaled(34, 34, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.cache = {}

    def thumbnail(self, m):
        key = m['filename']
        if key not in self.cache:
            if len(self.cache) > 100:
                self.cache.clear()
            self.cache[key] = QPixmap(str(self.store.thumbs / key))
        return self.cache[key]

    def dimensions(self, m, width):
        scale = min(1, max(90, width-120)/m['width'], 340/m['width'], 220/m['height'])
        return QSize(max(1, round(m['width']*scale)), max(1, round(m['height']*scale)))

    def sizeHint(self, option, index):
        m = index.data(Qt.UserRole)
        width = self.parent().viewport().width()
        height = self.dimensions(m, width).height() if m['kind'] == 'image' else 0
        if m['text']:
            height += self.document(m['text'], width).size().height() + 20
        return QSize(option.rect.width(), round(height)+66)

    def document(self, text, width):
        doc = QTextDocument()
        font = QFont('Microsoft YaHei UI')
        font.setPixelSize(14)
        doc.setDefaultFont(font)
        doc.setDocumentMargin(0)
        doc.setPlainText(text)
        doc.setTextWidth(min(340, max(100,width-140)))
        doc.setTextWidth(max(24, doc.idealWidth()))
        return doc

    def text_layout(self,message,rect):
        doc = self.document(message['text'],rect.width())
        image_height = self.dimensions(message,rect.width()).height() if message['kind']=='image' else 0
        bubble = QRect(rect.right()-54-24-round(doc.size().width()),rect.top()+34+image_height,
                       round(doc.size().width())+20,round(doc.size().height())+20)
        return doc,bubble

    def paint(self, painter, option, index):
        m = index.data(Qt.UserRole)
        size = self.dimensions(m, option.rect.width()) if m['kind'] == 'image' else QSize()
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        r = option.rect
        painter.setPen(QColor(COLORS['muted']))
        painter.drawText(r.adjusted(20, 6, -20, 0), Qt.AlignHCenter | Qt.AlignTop, datetime.fromisoformat(m['created']).strftime('%m月%d日  %H:%M'))
        avatar_rect = QRect(r.right()-54, r.top()+34, 34, 34)
        painter.drawPixmap(avatar_rect, self.avatar)
        image_rect = QRect(avatar_rect.left()-14-size.width(), r.top()+34, size.width(), size.height())
        if m['kind'] == 'image':
            pix = self.thumbnail(m)
            painter.setPen(QColor(COLORS['border']))
            painter.setBrush(QColor('white'))
            painter.drawRoundedRect(image_rect.adjusted(-3,-3,3,3), 4, 4)
            if not pix.isNull():
                painter.drawPixmap(image_rect, pix)
            else:
                painter.drawText(image_rect, Qt.AlignCenter, '图片文件已移走')
        if m['text']:
            doc,text_rect = self.text_layout(m,r)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor('#A9EA7A'))
            painter.drawRoundedRect(text_rect,6,6)
            painter.save()
            painter.translate(text_rect.x()+10,text_rect.y()+10)
            painter.setPen(QColor(COLORS['text']))
            context = QAbstractTextDocumentLayout.PaintContext()
            history = self.parent()
            if history.text_message_id==m['id'] and history.text_anchor!=history.text_position:
                selected = QAbstractTextDocumentLayout.Selection()
                selected.cursor = QTextCursor(doc)
                selected.cursor.setPosition(history.text_anchor)
                selected.cursor.setPosition(history.text_position,QTextCursor.KeepAnchor)
                selected.format.setBackground(QColor('#B5D9FF'))
                selected.format.setForeground(QColor(COLORS['text']))
                context.selections = [selected]
            doc.documentLayout().draw(painter,context)
            painter.restore()
            image_rect = image_rect.united(text_rect) if m['kind']=='image' else text_rect
        if option.state & QStyle.State_HasFocus:
            painter.setPen(QColor(COLORS['primary']))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(image_rect.adjusted(-4,-4,4,4), 4, 4)
        painter.restore()


class ConfirmDelete(QDialog):
    def __init__(self, parent, image=True, chat=None):
        super().__init__(parent)
        self.setWindowTitle('删除聊天' if chat else '删除消息')
        self.setFixedWidth(370)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24,24,24,24)
        layout.setSpacing(18)
        title = label('删除这个聊天？' if chat else '删除这条消息？', 'title')
        layout.addWidget(title)
        text = label(f'将删除“{chat["name"]}”及其全部聊天记录，包括文字、图片和本地原图、缩略图，无法撤销。' if chat else '消息和本地原图将一起删除，无法撤销。' if image else '这条文字消息将被删除，无法撤销。')
        text.setWordWrap(True)
        layout.addWidget(text)
        actions = QHBoxLayout()
        cancel = button('取消', self.reject)
        actions.addStretch()
        actions.addWidget(cancel)
        actions.addWidget(button('删除', self.accept, 'danger'))
        layout.addLayout(actions)
        cancel.setFocus()


class CaptionButton(QPushButton):
    """Uniform vector controls painted directly on the title bar background."""
    def __init__(self, symbol, callback, tip, parent):
        super().__init__(parent)
        self.symbol = symbol
        self.setFixedSize(44,34)
        self.setToolTip(tip)
        self.setAccessibleName(tip)
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover)
        self.clicked.connect(callback)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        hovered = self.underMouse()
        if hovered:
            p.fillRect(self.rect(),QColor('#E84949' if self.symbol=='close' else '#D3D4DA'))
        color = '#FFFFFF' if hovered and self.symbol=='close' else COLORS['primary_hover'] if self.isChecked() else '#686970'
        p.setPen(QPen(QColor(color),1.2,Qt.SolidLine,Qt.SquareCap,Qt.MiterJoin))
        p.setBrush(Qt.NoBrush)
        p.translate(self.width()/2-6,self.height()/2-6)
        if self.symbol=='minimize':
            p.drawLine(0,6,12,6)
        elif self.symbol=='maximize':
            p.drawRect(QRectF(0.5,0.5,11,11))
        elif self.symbol=='restore':
            p.drawPolyline([QPointF(3.5,.5),QPointF(11.5,.5),QPointF(11.5,8.5)])
            p.drawRect(QRectF(.5,3.5,8,8))
        elif self.symbol=='close':
            p.drawLine(1,1,11,11)
            p.drawLine(11,1,1,11)
        elif self.symbol=='pin':
            p.drawLine(3,0,9,0)
            p.drawLine(4,0,4,5)
            p.drawLine(8,0,8,5)
            p.drawLine(4,5,1,8)
            p.drawLine(8,5,11,8)
            p.drawLine(1,8,11,8)
            p.drawLine(6,8,6,13)
        if self.hasFocus() and self.window().testAttribute(Qt.WA_KeyboardFocusChange):
            p.resetTransform()
            p.setPen(QPen(QColor(COLORS['primary']),1,Qt.DotLine))
            p.drawRect(self.rect().adjusted(3,3,-4,-4))


class TitleBar(QFrame):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.setObjectName('titleBar')
        self.setFixedHeight(34)
        row = QHBoxLayout(self)
        row.setContentsMargins(12,0,0,0)
        row.setSpacing(0)
        icon = QLabel()
        icon.setPixmap(window.windowIcon().pixmap(18,18))
        row.addWidget(icon)
        row.addSpacing(8)
        row.addWidget(label('截图聊天'))
        row.addStretch()
        self.pin = CaptionButton('pin',window.set_topmost,'置顶窗口',self)
        self.pin.setCheckable(True)
        row.addWidget(self.pin)
        row.addWidget(CaptionButton('minimize',window.hide_to_tray,'最小化到托盘',self))
        self.maximize = CaptionButton('maximize',window.toggle_maximize,'最大化',self)
        row.addWidget(self.maximize)
        row.addWidget(CaptionButton('close',window.close,'关闭到托盘',self))
        for child in self.findChildren(QPushButton):
            child.setFixedSize(44,34)
        # Let dragging/double-clicking all non-button parts operate the title bar.
        for child in (icon, row.itemAt(2).widget()):
            child.setAttribute(Qt.WA_TransparentForMouseEvents)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.window.windowHandle():
            self.window.windowHandle().startSystemMove()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.window.toggle_maximize()


class AboutDialog(QDialog):
    def __init__(self,parent):
        super().__init__(parent)
        self.setWindowTitle('关于软件')
        self.setFixedWidth(400)
        self.setWindowIcon(parent.windowIcon())
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32,28,32,24)
        layout.setSpacing(14)
        icon = QLabel()
        icon.setPixmap(QPixmap(str(asset('scissors.png'))).scaled(64,64,Qt.KeepAspectRatio,Qt.SmoothTransformation))
        layout.addWidget(icon,alignment=Qt.AlignHCenter)
        name = label(APP_NAME,'title')
        name.setAlignment(Qt.AlignCenter)
        layout.addWidget(name)
        version = label('版本 '+APP_VERSION,'muted')
        version.setAlignment(Qt.AlignCenter)
        layout.addWidget(version)
        description = label('截图、记录，让图片和文字留在本机。','muted')
        description.setAlignment(Qt.AlignCenter)
        layout.addWidget(description)
        for text,url in (('X  @'+AUTHOR,AUTHOR_URL),('GitHub 开源仓库',REPOSITORY_URL)):
            link = label(f'<a href="{url}" style="color:{COLORS["primary_hover"]};text-decoration:none;">{text}</a>')
            link.setAlignment(Qt.AlignCenter)
            link.setTextInteractionFlags(Qt.TextBrowserInteraction)
            link.linkActivated.connect(lambda target: QDesktopServices.openUrl(QUrl(target)))
            layout.addWidget(link)
        license_info = label('项目代码：MIT License\n使用 Qt / PySide6（LGPLv3），详见随附许可。','muted')
        license_info.setAlignment(Qt.AlignCenter)
        layout.addWidget(license_info)
        layout.addWidget(button('关闭',self.accept),alignment=Qt.AlignHCenter)


class SettingsDialog(QDialog):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.setWindowTitle('截图设置')
        self.setFixedWidth(420)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26,24,26,24)
        layout.setSpacing(16)
        layout.addWidget(label('截图快捷键', 'title'))
        layout.addWidget(label('点击下面的输入框，按下新的组合键。', 'muted'))
        self.editor = QKeySequenceEdit(QKeySequence(window.hotkey_text))
        self.editor.setMaximumSequenceLength(1)
        self.editor.setAccessibleName('截图快捷键')
        layout.addWidget(self.editor)
        self.error = label('', 'status')
        self.error.setWordWrap(True)
        layout.addWidget(self.error)
        self.autostart = QCheckBox('开机启动')
        self.autostart.setAccessibleName('开机启动')
        self.autostart.setCursor(Qt.PointingHandCursor)
        try:
            self.autostart.setChecked(window.startup.read() is not None)
        except OSError as exc:
            self.autostart.setEnabled(False)
            self.error.setText('无法读取开机启动设置：' + str(exc))
        layout.addWidget(self.autostart)
        layout.addWidget(label('登录 Windows 后自动启动，并收起到托盘。', 'muted'))
        layout.addWidget(label('文件缓存位置', 'muted'))
        self.cache_path = QLineEdit(str(window.store.root))
        self.cache_path.setReadOnly(True)
        self.cache_path.setAccessibleName('文件缓存文件夹')
        directory_row = QHBoxLayout()
        directory_row.addWidget(self.cache_path, 1)
        directory_row.addWidget(button('修改文件夹', self.choose_directory))
        layout.addLayout(directory_row)
        self.migrate = QCheckBox('迁移原有聊天和图片（保留旧目录备份）')
        self.migrate.setChecked(True)
        layout.addWidget(self.migrate)
        hint = label('不迁移时使用新目录的记录，旧目录的文件会保留。', 'muted')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addWidget(button('打开图片文件夹', lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(window.store.images)))))
        row = QHBoxLayout()
        row.addWidget(button('关于软件',lambda: AboutDialog(self).exec()))
        row.addStretch()
        row.addWidget(button('取消', self.reject))
        row.addWidget(button('保存', self.save, 'primary'))
        layout.addLayout(row)

    def choose_directory(self):
        path = QFileDialog.getExistingDirectory(self, '选择缓存文件夹', self.cache_path.text())
        if path:
            self.cache_path.setText(path)

    def save(self):
        text = self.editor.keySequence().toString(QKeySequence.PortableText)
        previous = self.window.hotkey_text
        startup_changed = False
        settings_saved = False
        previous_settings = self.window.store.settings()
        try:
            startup_previous = self.window.startup.read() if self.autostart.isEnabled() else None
            self.window.hotkey.set(text)
            try:
                if self.autostart.isEnabled():
                    self.window.startup.set_enabled(self.autostart.isChecked())
                    startup_changed = True
                settings = self.window.store.settings()
                settings['hotkey'] = text
                self.window.store.save_settings(settings)
                settings_saved = True
                if Path(self.cache_path.text()).resolve() != self.window.store.root.resolve():
                    self.window.move_cache(self.cache_path.text(), self.migrate.isChecked(), self)
            except Exception:
                self.window.hotkey.set(previous)
                if startup_changed:
                    self.window.startup.restore(startup_previous)
                if settings_saved:
                    self.window.store.save_settings(previous_settings)
                raise
            self.window.hotkey_text = text
            self.window.update_hotkey_labels()
            self.window.notify('设置已保存')
            logger.info('设置已保存；快捷键=%s',text)
            self.accept()
        except (ValueError, OSError) as exc:
            logger.exception('保存设置失败')
            self.error.setText(str(exc))


class MainWindow(QMainWindow):
    def __init__(self, store, hotkey, startup=None):
        super().__init__()
        self.store, self.hotkey = store, hotkey
        self.startup = startup if startup is not None else Startup()
        self.chat_id = store.conversations()[0]['id']
        self.drafts = {}
        self.cache_drafts = {}
        self.image_viewer = None
        self.log_viewer = None
        self.hotkey_text = store.settings().get('hotkey', 'Ctrl+Alt+A')
        self.pending = None
        self.capture_session = None
        self.capture_busy = False
        self.quitting = False
        self.setWindowTitle('截图聊天')
        self.setWindowIcon(QIcon(str(asset('scissors.ico'))))
        self.setWindowFlag(Qt.FramelessWindowHint)
        self.resize(1040, 760)
        self.setMinimumSize(760, 560)
        self.build_ui()
        self.tray = QSystemTrayIcon(self.windowIcon(), self)
        self.tray.setToolTip('截图聊天')
        menu = QMenu()
        menu.addAction('打开截图聊天', self.restore)
        menu.addAction('截图', self.capture)
        menu.addAction('截图设置', self.settings)
        menu.addAction('关于软件', self.about)
        menu.addSeparator()
        menu.addAction('退出截图聊天', self.quit_app)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda reason: self.restore() if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick) else None)
        self.tray.show()
        self.hotkey.events.triggered.connect(self.capture)
        try:
            self.hotkey.set(self.hotkey_text)
            logger.info('截图快捷键已注册：%s',self.hotkey_text)
        except ValueError as exc:
            logger.warning('截图快捷键注册失败：%s',exc)
            self.notify(str(exc) + '；点击设置修改')
        self.paste_shortcut = QShortcut(QKeySequence.Paste, self)
        self.paste_shortcut.activated.connect(self.paste)
        self.ctrl_send = QShortcut(QKeySequence('Ctrl+Return'), self)
        self.ctrl_send.activated.connect(self.send)
        self.load_older()
        self.refresh_conversations()
        QTimer.singleShot(0, self.history.scrollToBottom)
        QTimer.singleShot(0, self.text_editor.setFocus)

    def build_ui(self):
        root = QWidget()
        root.setObjectName('root')
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(1,1,1,1)
        outer.setSpacing(0)
        self.title_bar = TitleBar(self)
        outer.addWidget(self.title_bar)
        body = QWidget()
        outer.addWidget(body, 1)
        layout = QHBoxLayout(body)
        layout.setSpacing(0)
        layout.setContentsMargins(0,0,0,0)
        rail = QFrame()
        rail.setObjectName('rail')
        rail.setFixedWidth(64)
        nav = QVBoxLayout(rail)
        nav.setContentsMargins(10,22,10,16)
        nav.setSpacing(0)
        avatar = QLabel()
        avatar.setPixmap(QPixmap(str(asset('scissors.png'))).scaled(38,38,Qt.KeepAspectRatio,Qt.SmoothTransformation))
        nav.addWidget(avatar, alignment=Qt.AlignHCenter)
        nav.addSpacing(24)
        conversation_button = button('', self.restore, 'selectedRail', '图片对话')
        conversation_button.setIcon(chat_icon())
        conversation_button.setIconSize(QSize(28,28))
        nav.addWidget(conversation_button)
        nav.addStretch()
        self.log_button = button('',self.show_logs,'railButton','查看日志')
        self.log_button.setIcon(rail_icon('logs'))
        self.log_button.setIconSize(QSize(20,20))
        self.log_button.setFixedSize(44,36)
        nav.addWidget(self.log_button,alignment=Qt.AlignHCenter)
        nav.addSpacing(12)
        rail_footer = QWidget()
        rail_footer.setObjectName('railFooter')
        rail_footer.setFixedHeight(100)
        rail_actions = QVBoxLayout(rail_footer)
        rail_actions.setContentsMargins(0,0,0,0)
        rail_actions.setSpacing(8)
        settings_slot = QWidget()
        settings_slot.setFixedHeight(56)
        settings_slot_layout = QVBoxLayout(settings_slot)
        settings_slot_layout.setContentsMargins(0,0,0,0)
        self.rail_settings = button('',self.settings,'railButton','截图设置')
        self.rail_settings.setIcon(rail_icon('settings'))
        self.rail_settings.setIconSize(QSize(20,20))
        self.rail_settings.setFixedSize(44,36)
        settings_slot_layout.addWidget(self.rail_settings,alignment=Qt.AlignCenter)
        rail_actions.addWidget(settings_slot)
        self.rail_collapse = button('',self.hide_to_tray,'railButton','收起到托盘')
        self.rail_collapse.setIcon(rail_icon('collapse'))
        self.rail_collapse.setIconSize(QSize(20,20))
        self.rail_collapse.setFixedSize(44,36)
        rail_actions.addWidget(self.rail_collapse,alignment=Qt.AlignHCenter)
        nav.addWidget(rail_footer)
        layout.addWidget(rail)
        sidebar = QFrame()
        sidebar.setObjectName('sidebar')
        sidebar.setFixedWidth(216)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(14,25,14,16)
        chats_top = QHBoxLayout()
        self.chat_filter = QLineEdit()
        self.chat_filter.setPlaceholderText('搜索聊天')
        self.chat_filter.setAccessibleName('按名称搜索聊天')
        self.chat_filter.setClearButtonEnabled(True)
        self.chat_filter.textChanged.connect(self.filter_conversations)
        chats_top.addWidget(self.chat_filter, 1)
        self.add_chat_button = button('＋', self.new_conversation, 'addChat', '新建聊天')
        self.add_chat_button.setFixedSize(32,34)
        chats_top.addWidget(self.add_chat_button)
        side.addLayout(chats_top)
        self.chats = QListWidget()
        self.chats.setObjectName('chatList')
        self.chats.setIconSize(QSize(34,34))
        self.chats.setAccessibleName('聊天列表；右键重命名')
        self.chats.currentItemChanged.connect(self.switch_conversation)
        self.chats.setContextMenuPolicy(Qt.CustomContextMenu)
        self.chats.customContextMenuRequested.connect(self.chat_menu)
        side.addWidget(self.chats, 1)
        shortcut_footer = QWidget()
        shortcut_footer.setObjectName('shortcutFooter')
        shortcut_footer.setFixedHeight(100)
        shortcut_layout = QVBoxLayout(shortcut_footer)
        shortcut_layout.setContentsMargins(0,0,0,0)
        shortcut_layout.setSpacing(8)
        shortcut_summary = QWidget()
        shortcut_summary.setFixedHeight(56)
        summary_layout = QVBoxLayout(shortcut_summary)
        summary_layout.setContentsMargins(0,4,0,4)
        summary_layout.setSpacing(2)
        shortcut_title = label('截图快捷键','muted')
        shortcut_title.setAlignment(Qt.AlignCenter)
        summary_layout.addWidget(shortcut_title)
        self.hotkey_label = label(self.hotkey_text,'shortcutValue')
        self.hotkey_label.setAlignment(Qt.AlignCenter)
        self.hotkey_label.setFixedHeight(26)
        summary_layout.addWidget(self.hotkey_label)
        shortcut_layout.addWidget(shortcut_summary)
        self.edit_hotkey_button = button('修改快捷键',self.settings,'editHotkey')
        self.edit_hotkey_button.setFixedHeight(36)
        shortcut_layout.addWidget(self.edit_hotkey_button)
        side.addWidget(shortcut_footer)
        layout.addWidget(sidebar)
        main = QVBoxLayout()
        main.setSpacing(0)
        main.setContentsMargins(0,0,0,0)
        header = QFrame()
        header.setObjectName('header')
        head = QHBoxLayout(header)
        head.setContentsMargins(20,14,18,14)
        names = QVBoxLayout()
        self.chat_title = label('我的图片', 'title')
        names.addWidget(self.chat_title)
        head.addLayout(names)
        head.addStretch()
        head.addWidget(button('查找聊天内容', self.search_messages))
        head.addWidget(button('截图设置', self.settings))
        main.addWidget(header)
        self.older_button = button('查看更早的图片', self.load_older)
        main.addWidget(self.older_button, alignment=Qt.AlignHCenter)
        self.history = MessageHistory()
        self.history.setAccessibleName('图片对话记录；右键复制或删除')
        self.history.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.history.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.history.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.history.setSelectionMode(QAbstractItemView.SingleSelection)
        self.history.setItemDelegate(MessageDelegate(self.store, self.history))
        self.history.setContextMenuPolicy(Qt.CustomContextMenu)
        self.history.customContextMenuRequested.connect(self.context_menu)
        self.history.itemDoubleClicked.connect(self.open_image)
        main.addWidget(self.history, 1)
        self.newer_button = button('查看更新的记录', self.load_newer)
        main.addWidget(self.newer_button, alignment=Qt.AlignHCenter)
        self.empty = label('还没有消息\n\n输入文字，或截图、粘贴图片\n发送后就会出现在这里。', 'muted')
        self.empty.setAlignment(Qt.AlignCenter)
        self.empty.setMinimumHeight(100)
        main.addWidget(self.empty, 1)
        composer = QFrame()
        composer.setObjectName('composer')
        edit = QVBoxLayout(composer)
        edit.setContentsMargins(14,12,12,10)
        tools = QHBoxLayout()
        self.capture_button = button('✂  截图', self.capture, tip='框选屏幕区域')
        tools.addWidget(self.capture_button)
        tools.addWidget(button('▢  粘贴图片', self.paste, tip='从剪贴板粘贴图片 Ctrl+V'))
        self.status = label('', 'status')
        self.status.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Preferred)
        tools.addWidget(self.status, 1)
        self.discard_button = button('移除图片', self.discard)
        self.discard_button.hide()
        tools.addWidget(self.discard_button)
        self.text_editor = ChatEditor(self)
        self.text_editor.setPlaceholderText('输入文字…')
        self.text_editor.setAccessibleName('聊天输入框，可编辑文字和图片')
        self.text_editor.setFixedHeight(188)
        self.text_editor.textChanged.connect(self.update_send_state)
        edit.addWidget(self.text_editor)
        self.send_button = button('发送', self.send, 'primary')
        self.send_button.setEnabled(False)
        tools.addWidget(self.send_button)
        edit.addLayout(tools)
        composer_shell = QWidget()
        composer_shell_layout = QVBoxLayout(composer_shell)
        composer_shell_layout.setContentsMargins(10,4,10,12)
        composer_shell_layout.addWidget(composer)
        main.addWidget(composer_shell)
        layout.addLayout(main, 1)
        self.copy_shortcut = QShortcut(QKeySequence.Copy, self.history)
        self.copy_shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        self.copy_shortcut.activated.connect(lambda: self.copy(self.history.currentItem()))
        self.delete_shortcut = QShortcut(QKeySequence.Delete, self.history)
        self.delete_shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        self.delete_shortcut.activated.connect(lambda: self.delete(self.history.currentItem()))
        self.update_hotkey_labels()

    def update_hotkey_labels(self):
        self.hotkey_label.setText(self.hotkey_text)
        self.capture_button.setToolTip('框选截图 · ' + self.hotkey_text)

    def about(self):
        AboutDialog(self).exec()

    def show_logs(self):
        from .log_viewer import LogViewer
        if self.log_viewer is None:
            self.log_viewer = LogViewer(self,lambda: active_log_path(self.store.root))
        else:
            self.log_viewer.refresh()
        self.log_viewer.show()
        self.log_viewer.raise_()
        self.log_viewer.activateWindow()

    def refresh_conversations(self):
        self.chats.blockSignals(True)
        self.chats.clear()
        for chat in self.store.conversations():
            item = QListWidgetItem(QIcon(str(asset('scissors.png'))), f"{chat['name']}\n{chat['count']} 条消息")
            item.setData(Qt.UserRole, chat)
            item.setSizeHint(QSize(180,66))
            self.chats.addItem(item)
            if chat['id'] == self.chat_id:
                self.chats.setCurrentItem(item)
                self.chat_title.setText(chat['name'])
        self.chats.blockSignals(False)
        self.filter_conversations(self.chat_filter.text())

    def filter_conversations(self, text):
        for i in range(self.chats.count()):
            item = self.chats.item(i)
            item.setHidden(text.casefold() not in item.data(Qt.UserRole)['name'].casefold())

    def new_conversation(self):
        dialog = ChatNameDialog(self, '新建聊天', '')
        if dialog.exec() != QDialog.Accepted:
            return
        try:
            identifier = self.store.create_conversation(dialog.value)
            self.chat_filter.clear()
            self.refresh_conversations()
            for i in range(self.chats.count()):
                if self.chats.item(i).data(Qt.UserRole)['id'] == identifier:
                    self.chats.setCurrentRow(i)
                    break
        except (OSError, sqlite3.Error, ValueError) as exc:
            self.notify('创建聊天失败：' + str(exc))

    def chat_menu(self, pos):
        item = self.chats.itemAt(pos)
        if not item:
            return
        menu = QMenu(self)
        menu.addAction('重命名聊天', lambda: self.rename_conversation(item.data(Qt.UserRole)))
        menu.addSeparator()
        menu.addAction('删除聊天', lambda: self.delete_conversation(item.data(Qt.UserRole)))
        menu.exec(self.chats.viewport().mapToGlobal(pos))

    def delete_conversation(self, chat):
        if ConfirmDelete(self,chat=chat).exec() != QDialog.Accepted:
            return
        try:
            self.store.delete_conversation(chat['id'])
        except (OSError,sqlite3.Error,ValueError) as exc:
            self.notify('删除聊天失败：' + str(exc))
            return
        self.drafts.pop(chat['id'],None)
        self.cache_drafts.pop(str(self.store.root.resolve()),None)
        if self.image_viewer:
            self.image_viewer.close()
        self.history.itemDelegate().cache.clear()
        if self.chat_id == chat['id']:
            self.chat_id = self.store.conversations()[0]['id']
            self.text_editor.restore_snapshot(self.drafts.get(self.chat_id))
            self.update_send_state()
            self.reload_latest()
        self.chat_filter.clear()
        self.refresh_conversations()
        self.notify('聊天及全部文字、图片已删除')

    def rename_conversation(self, chat):
        dialog = ChatNameDialog(self, '重命名聊天', chat['name'])
        if dialog.exec() == QDialog.Accepted:
            try:
                self.store.rename_conversation(chat['id'], dialog.value)
                self.refresh_conversations()
            except (OSError, sqlite3.Error, ValueError) as exc:
                self.notify('重命名失败：' + str(exc))

    def switch_conversation(self, item, previous=None):
        if not item or item.data(Qt.UserRole)['id'] == self.chat_id:
            return
        self.drafts[self.chat_id] = self.text_editor.snapshot()
        self.chat_id = item.data(Qt.UserRole)['id']
        self.chat_title.setText(item.data(Qt.UserRole)['name'])
        self.text_editor.restore_snapshot(self.drafts.get(self.chat_id))
        self.update_send_state()
        self.reload_latest()

    def reload_latest(self):
        self.history.clear()
        for message in self.store.page(conversation_id=self.chat_id):
            self.add_message(message)
        self.refresh_count()
        self.history.scrollToBottom()

    def load_newer(self):
        item = self.history.item(self.history.count()-1)
        if item:
            for message in self.store.page_after(item.data(Qt.UserRole)['id'], conversation_id=self.chat_id):
                self.add_message(message)
        self.refresh_count()

    def search_messages(self):
        from .search import SearchDialog
        SearchDialog(self).exec()

    def locate_message(self, identifier):
        messages = self.store.around(identifier, self.chat_id)
        if not any(m['id'] == identifier for m in messages):
            self.notify('这条消息已被删除')
            return
        self.history.clear()
        selected = None
        for message in messages:
            item = self.add_message(message)
            if message['id'] == identifier:
                selected = item
        self.refresh_count()
        self.history.doItemsLayout()
        self.history.setCurrentItem(selected)
        self.history.scrollToItem(selected, QAbstractItemView.PositionAtCenter)
        self.restore()
        self.history.setFocus()
        self.notify('已定位到聊天位置')

    def notify(self, text):
        self.status.setText(text)
        self.status.setToolTip(text)

    def refresh_count(self):
        total = self.store.count(self.chat_id)
        self.empty.setVisible(total == 0)
        self.history.setVisible(total > 0)
        first, last = self.history.item(0), self.history.item(self.history.count()-1)
        self.older_button.setVisible(bool(first and self.store.has_before(first.data(Qt.UserRole)['id'], self.chat_id)))
        self.newer_button.setVisible(bool(last and self.store.has_after(last.data(Qt.UserRole)['id'], self.chat_id)))

    def add_message(self, message, index=None):
        item = QListWidgetItem()
        item.setData(Qt.UserRole, message)
        item.setText((message['text'] or '图片') + ' ' + message['created'])
        if index is None:
            self.history.addItem(item)
        else:
            self.history.insertItem(index, item)
        return item

    def load_older(self):
        first = self.history.item(0)
        before = first.data(Qt.UserRole)['id'] if first else None
        previous_height = self.history.verticalScrollBar().maximum()
        previous_value = self.history.verticalScrollBar().value()
        messages = self.store.page(before, conversation_id=self.chat_id)
        for i, m in enumerate(messages):
            self.add_message(m, i)
        self.history.doItemsLayout()
        if first:
            self.history.verticalScrollBar().setValue(previous_value+self.history.verticalScrollBar().maximum()-previous_height)
        self.refresh_count()

    def paste(self):
        image = QApplication.clipboard().image()
        if image.isNull():
            text = QApplication.clipboard().text()
            if text:
                self.text_editor.insertPlainText(text)
                return
            self.notify('剪贴板里没有图片，请先截图或复制图片')
            return
        self.set_pending(image)

    def update_send_state(self):
        images = self.text_editor.images()
        self.pending = images[0] if images else None
        self.discard_button.setVisible(bool(images))
        self.send_button.setEnabled(self.pending is not None or bool(self.text_editor.toPlainText().strip()))

    def set_pending(self, image):
        self.text_editor.insert_image(image)
        self.update_send_state()
        self.text_editor.setFocus()

    def discard(self):
        self.text_editor.remove_images()
        self.update_send_state()
        self.notify('')
        self.text_editor.setFocus()

    def send(self):
        text = self.text_editor.toPlainText()
        if (self.pending is None and not text.strip()) or self.capture_busy or self.capture_session or self.text_editor.composing:
            return
        self.send_button.setEnabled(False)
        try:
            images = self.text_editor.images()
            if len(images) > 1:
                parts = []
                buffer = ''
                for kind,value in self.text_editor.elements():
                    if kind == 'text':
                        buffer += value
                    else:
                        if buffer.strip():
                            parts.append((None,buffer))
                        buffer = ''
                        parts.append((value,''))
                if buffer.strip():
                    parts.append((None,buffer))
                self.store.save_composed(parts,self.chat_id)
            elif self.pending is not None:
                message = self.store.save(self.pending, text, self.chat_id)
            else:
                message = self.store.save_text(text, self.chat_id)
        except (OSError, ValueError, sqlite3.Error) as exc:
            logger.exception('保存消息失败；聊天编号=%s',self.chat_id)
            self.notify('发送失败：' + str(exc))
            self.send_button.setEnabled(True)
            return
        logger.info('消息已保存；聊天编号=%s；图片数=%s',self.chat_id,len(self.text_editor.images()))
        self.text_editor.reset()
        self.update_send_state()
        self.reload_latest()
        self.refresh_conversations()
        self.history.scrollToBottom()
        self.notify('已发送并保存到本地')
        self.text_editor.setFocus()

    def capture(self):
        if self.capture_busy or self.capture_session or QApplication.activeModalWidget():
            return
        self.was_visible = self.isVisible() and not self.isMinimized()
        logger.info('开始截图')
        self.capture_busy = True
        self.hide()
        QTimer.singleShot(220, self.begin_capture)

    def begin_capture(self):
        self.capture_busy = False
        self.capture_session = CaptureSession(self)
        self.capture_session.finished.connect(self.captured)
        self.capture_session.cancelled.connect(self.capture_cancelled)
        self.capture_session.begin()

    def release_capture(self):
        if self.capture_session:
            self.capture_session.deleteLater()
            self.capture_session = None

    def captured(self, image):
        logger.info('截图完成；尺寸=%sx%s',image.width(),image.height())
        self.release_capture()
        QApplication.clipboard().setImage(image)
        self.restore()
        self.set_pending(image)

    def restore_after_capture(self):
        if self.was_visible:
            # Restore only prior visibility; never activate the chat or focus its editor.
            self.setAttribute(Qt.WA_ShowWithoutActivating, True)
            try:
                self.showMaximized() if self.isMaximized() else self.showNormal()
            finally:
                self.setAttribute(Qt.WA_ShowWithoutActivating, False)

    def capture_cancelled(self):
        logger.info('截图已取消')
        self.release_capture()
        self.restore_after_capture()

    def context_menu(self, pos):
        item = self.history.itemAt(pos)
        if not item:
            return
        self.history.setCurrentItem(item)
        menu = QMenu(self)
        message = item.data(Qt.UserRole)
        selected = self.history.selected_text(item)
        if selected:
            menu.addAction('复制所选文字',lambda: QApplication.clipboard().setText(selected))
        if message['kind']=='image':
            menu.addAction('复制图片',lambda: self.copy_image(item))
        else:
            menu.addAction('复制全文' if selected else '复制文字',lambda: QApplication.clipboard().setText(message['text']))
        if message['kind']=='image' and message['text']:
            menu.addAction('复制文字', lambda: QApplication.clipboard().setText(message['text']))
        menu.addAction('删除消息', lambda: self.delete(item))
        menu.exec(self.history.viewport().mapToGlobal(pos))

    def copy(self, item):
        if not item:
            return
        selected = self.history.selected_text(item)
        if selected:
            QApplication.clipboard().setText(selected)
            self.notify('所选文字已复制')
            return
        if item.data(Qt.UserRole)['kind'] == 'text':
            QApplication.clipboard().setText(item.data(Qt.UserRole)['text'])
            self.notify('文字已复制')
            return
        self.copy_image(item)

    def copy_image(self,item):
        image = QImage(str(self.store.images / item.data(Qt.UserRole)['filename']))
        if image.isNull():
            self.notify('图片读取失败：文件可能已被移动或删除')
            return
        QApplication.clipboard().setImage(image)
        self.notify('图片已复制，可以粘贴到其他对话框')

    def delete(self, item):
        if not item or ConfirmDelete(self, image=item.data(Qt.UserRole)['kind']=='image').exec() != QDialog.Accepted:
            return
        try:
            self.store.delete(item.data(Qt.UserRole))
            self.history.takeItem(self.history.row(item))
            self.refresh_count()
            self.refresh_conversations()
            self.notify('消息已删除')
        except (OSError, sqlite3.Error) as exc:
            self.notify('删除失败：' + str(exc))

    def open_image(self, item):
        if item.data(Qt.UserRole)['kind'] != 'image':
            self.copy(item)
            return
        path = self.store.images / item.data(Qt.UserRole)['filename']
        if not path.exists():
            self.notify('图片文件已被移动或删除')
            return
        from .viewer import ImageViewer
        try:
            if self.image_viewer is None:
                self.image_viewer = ImageViewer(path,self)
            else:
                self.image_viewer.load_image(path)
            self.image_viewer.show()
            self.image_viewer.raise_()
            self.image_viewer.activateWindow()
        except (OSError,ValueError) as exc:
            self.notify(str(exc))

    def settings(self):
        SettingsDialog(self).exec()

    def move_cache(self, destination, migrate, parent):
        from .relocation import MoveWorker, MoveDialog, validate_destination, write_location
        from .storage import Store
        target = validate_destination(self.store.root, destination)
        self.store.db.commit()
        self.relocating = True
        worker = MoveWorker(self.store.root, target, migrate, parent)
        dialog = MoveDialog(parent, worker)
        worker.start()
        dialog.exec()
        worker.wait()
        self.relocating = False
        if worker.error:
            raise OSError(worker.error)
        replacement = Store(worker.result)
        try:
            # Keep this application's current hotkey when switching to an existing cache.
            settings = replacement.settings()
            settings['hotkey'] = self.hotkey.current[0] if getattr(self.hotkey, 'current', None) else self.hotkey_text
            replacement.save_settings(settings)
            write_location(worker.result)
        except Exception:
            replacement.db.close()
            raise
        old_root = str(self.store.root.resolve())
        current_drafts = dict(self.drafts)
        current_drafts[self.chat_id] = self.text_editor.snapshot()
        self.cache_drafts[old_root] = (self.chat_id, current_drafts)
        previous_chat_id = self.chat_id
        self.store.db.close()
        self.store = replacement
        try:
            configure_logging(replacement.root)
            logger.info('缓存位置已切换；迁移=%s',migrate)
        except OSError:
            logger.exception('切换日志文件失败，继续使用原日志文件')
        self.chat_id, self.drafts = (previous_chat_id, current_drafts) if migrate else self.cache_drafts.get(str(replacement.root.resolve()), (1, {}))
        if not any(chat['id'] == self.chat_id for chat in self.store.conversations()):
            self.chat_id = self.store.conversations()[0]['id']
        self.text_editor.restore_snapshot(self.drafts.get(self.chat_id))
        self.update_send_state()
        self.history.itemDelegate().store = replacement
        self.history.itemDelegate().cache.clear()
        self.reload_latest()
        self.refresh_conversations()

    def restore(self):
        if self.capture_busy or self.capture_session:
            return
        self.showMaximized() if self.isMaximized() else self.showNormal()
        self.raise_()
        self.activateWindow()

    def hide_to_tray(self):
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.hide()
        else:
            self.showMinimized()

    def set_topmost(self, enabled):
        visible = self.isVisible()
        maximized = self.isMaximized()
        self.setWindowFlag(Qt.WindowStaysOnTopHint, enabled)
        self.title_bar.pin.setToolTip('取消置顶' if enabled else '置顶窗口')
        self.title_bar.pin.setAccessibleName('取消置顶' if enabled else '置顶窗口')
        if visible:
            self.showMaximized() if maximized else self.showNormal()

    def toggle_maximize(self):
        self.showNormal() if self.isMaximized() else self.showMaximized()

    def update_window_corners(self):
        if self.isMaximized() or self.isFullScreen():
            self.clearMask()
            return
        outline = QPainterPath()
        outline.addRoundedRect(QRectF(self.rect()), WINDOW_CORNER_RADIUS, WINDOW_CORNER_RADIUS)
        self.setMask(QRegion(outline.toFillPolygon().toPolygon()))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_window_corners()

    def showEvent(self, event):
        super().showEvent(event)
        self.update_window_corners()

    def nativeEvent(self, event_type, message):
        msg = wintypes.MSG.from_address(int(message))
        if msg.message == 0x0084 and not self.isMaximized():
            rect = wintypes.RECT()
            ctypes.windll.user32.GetWindowRect(wintypes.HWND(int(self.winId())), ctypes.byref(rect))
            x = ctypes.c_short(msg.lParam & 0xFFFF).value
            y = ctypes.c_short((msg.lParam >> 16) & 0xFFFF).value
            border = round(6 * self.devicePixelRatioF())
            left, right = x < rect.left+border, x >= rect.right-border
            top, bottom = y < rect.top+border, y >= rect.bottom-border
            hit = (13 if left else 14 if right else 12) if top else (16 if left else 17 if right else 15) if bottom else 10 if left else 11 if right else None
            if hit is not None:
                return True, hit
        return super().nativeEvent(event_type, message)

    def changeEvent(self, event):
        if event.type() == QEvent.WindowStateChange:
            self.update_window_corners()
            if hasattr(self, 'title_bar'):
                self.title_bar.maximize.symbol = 'restore' if self.isMaximized() else 'maximize'
                self.title_bar.maximize.update()
                self.title_bar.maximize.setToolTip('还原' if self.isMaximized() else '最大化')
            if self.isMinimized() and QSystemTrayIcon.isSystemTrayAvailable():
                QTimer.singleShot(0, self.hide)
        super().changeEvent(event)

    def closeEvent(self, event):
        if self.quitting:
            event.accept()
        elif QSystemTrayIcon.isSystemTrayAvailable():
            event.ignore()
            self.hide()
        else:
            self.quit_app()
            event.accept()

    def quit_app(self):
        if getattr(self, 'relocating', False):
            self.notify('正在切换缓存文件夹，请等待完成后退出')
            return
        self.quitting = True
        self.tray.hide()
        self.hotkey.close()
        QApplication.quit()
