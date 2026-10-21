"""Asynchronous public GitHub release checks; downloads open in the browser."""
from dataclasses import dataclass
import json
import re

from PySide6.QtCore import QObject, Signal, QUrl, QTimer, Qt
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QPlainTextEdit

from .version import APP_VERSION, REPOSITORY_URL

API_URL = 'https://api.github.com/repos/DTyun/screenshot-chat/releases/latest'
MAX_RESPONSE = 512 * 1024


def version_tuple(value):
    if not isinstance(value, str) or not re.fullmatch(r'v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)', value):
        raise ValueError('版本号格式无效')
    return tuple(int(part) for part in value.removeprefix('v').split('.'))


@dataclass(frozen=True)
class Release:
    version: str
    url: str
    notes: str


def parse_release(data, current=APP_VERSION):
    if not isinstance(data, dict) or data.get('draft') is not False or data.get('prerelease') is not False:
        raise ValueError('未取得正式发布版本')
    tag = data.get('tag_name')
    remote = version_tuple(tag)
    # Build our own URL: a release response cannot redirect users to another site.
    if remote <= version_tuple(current):
        return None
    notes = data.get('body') or '此版本未提供更新说明。'
    if not isinstance(notes, str):
        raise ValueError('更新说明格式无效')
    return Release(tag.removeprefix('v'), REPOSITORY_URL+'/releases/tag/'+tag, notes[:12000])


class UpdateChecker(QObject):
    finished = Signal(object, str)
    busy_changed = Signal(bool)

    def __init__(self, parent=None, manager=None):
        super().__init__(parent)
        self.manager = manager if manager is not None else QNetworkAccessManager(self)
        self.reply = None
        self.buffer = bytearray()
        self.too_large = False
        self.finishing = False
        self.deadline = QTimer(self)
        self.deadline.setSingleShot(True)
        self.deadline.setInterval(15000)
        self.deadline.timeout.connect(self.cancel)

    def check(self):
        if self.reply is not None:
            return
        request = QNetworkRequest(QUrl(API_URL))
        request.setRawHeader(b'Accept', b'application/vnd.github+json')
        request.setRawHeader(b'User-Agent', ('ScreenshotChat/'+APP_VERSION).encode('ascii'))
        request.setTransferTimeout(15000)
        request.setAttribute(QNetworkRequest.RedirectPolicyAttribute, QNetworkRequest.ManualRedirectPolicy)
        self.buffer.clear()
        self.too_large = False
        self.finishing = False
        self.reply = self.manager.get(request)
        self.reply.readyRead.connect(self._read)
        self.reply.finished.connect(self._finish)
        self.deadline.start()
        self.busy_changed.emit(True)

    def _read(self):
        chunk = bytes(self.reply.readAll())
        if len(self.buffer)+len(chunk) > MAX_RESPONSE:
            self.too_large = True
            if not self.finishing:
                self.reply.abort()
        else:
            self.buffer.extend(chunk)

    def _finish(self):
        reply = self.reply
        self.finishing = True
        self.deadline.stop()
        self._read()
        release, error = None, ''
        status = reply.attribute(QNetworkRequest.HttpStatusCodeAttribute)
        try:
            if self.too_large:
                raise ValueError('更新响应过大，请稍后重试')
            if status in (403, 429):
                raise ValueError('GitHub 请求受限，请稍后重试')
            if status == 404:
                raise ValueError('暂未找到正式发布版本')
            if reply.error() != QNetworkReply.NoError or status != 200:
                raise ValueError('无法连接 GitHub，请检查网络后重试')
            release = parse_release(json.loads(self.buffer))
        except (ValueError, TypeError, UnicodeError) as exc:
            error = str(exc) if not isinstance(exc, json.JSONDecodeError) else '更新响应格式无效'
        self.reply = None
        reply.deleteLater()
        self.busy_changed.emit(False)
        self.finished.emit(release, error)

    def cancel(self):
        self.deadline.stop()
        if self.reply is not None:
            self.reply.abort()


class UpdateDialog(QDialog):
    def __init__(self, checker, parent):
        super().__init__(parent)
        self.checker = checker
        self.release = None
        self.setWindowTitle('软件更新')
        self.resize(440, 360)
        self.setWindowIcon(parent.windowIcon())
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)
        self.status = QLabel('正在检查更新…')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.notes = QPlainTextEdit()
        self.notes.setObjectName('updateNotes')
        self.notes.setReadOnly(True)
        layout.addWidget(self.notes)
        hint = QLabel('下载后从托盘退出旧版，再解压替换程序。\n聊天记录保存在原缓存文件夹，会继续保留。')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.action = QPushButton('检查更新')
        self.action.setObjectName('primary')
        self.action.setCursor(Qt.PointingHandCursor)
        self.action.clicked.connect(self.act)
        layout.addWidget(self.action)
        close = QPushButton('稍后')
        close.clicked.connect(self.reject)
        layout.addWidget(close)
        checker.finished.connect(self.show_result)
        checker.busy_changed.connect(self.set_busy)

    def set_busy(self, busy):
        self.action.setEnabled(not busy)
        if busy:
            self.status.setText('正在检查更新…')

    def show_result(self, release, error=''):
        self.release = release
        self.action.setEnabled(True)
        self.action.setText('下载更新' if release else '重新检查')
        self.status.setText(('发现新版本 '+release.version+'（当前 '+APP_VERSION+'）') if release else
                            (error or '当前已是最新版本（'+APP_VERSION+'）'))
        self.notes.setPlainText(release.notes if release else '')

    def act(self):
        if self.release:
            if not QDesktopServices.openUrl(QUrl(self.release.url)):
                self.status.setText('无法打开浏览器，请重试或前往 GitHub 仓库下载。')
        else:
            self.checker.check()
