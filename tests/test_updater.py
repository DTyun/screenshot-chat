import json
import pytest
from PySide6.QtCore import QObject, Signal, QByteArray
from PySide6.QtNetwork import QNetworkReply
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QPushButton
from tests.test_app import app, FakeHotkey, FakeStartup
from src.updater import UpdateChecker, parse_release, version_tuple, MAX_RESPONSE, API_URL
from src.storage import Store
from src.ui import MainWindow, AboutDialog, SettingsDialog


def payload(tag='v1.3.0', **changes):
    return dict(tag_name=tag, draft=False, prerelease=False, body='修复问题\n新增功能', **changes)


def test_release_numeric_versions_and_trusted_destination():
    assert version_tuple('v1.10.0') > version_tuple('1.9.9')
    assert parse_release(payload('v1.2.0'), '1.2.0') is None
    assert parse_release(payload('v1.1.9'), '1.2.0') is None
    release = parse_release(payload(html_url='https://example.com/bad.exe'), '1.2.0')
    assert release.url == 'https://github.com/DTyun/screenshot-chat/releases/tag/v1.3.0'
    assert release.notes.startswith('修复问题')
    for bad in ('1.3', '1.3.0-beta', 'v1.3.0/../../bad', '01.3.0', None):
        with pytest.raises(ValueError):
            parse_release(payload(bad))
    for field in ('draft', 'prerelease'):
        data = payload(); data[field] = True
        with pytest.raises(ValueError):
            parse_release(data)


class Reply(QObject):
    readyRead = Signal()
    finished = Signal()

    def __init__(self):
        super().__init__()
        self.data = b''
        self.status = 200
        self.code = QNetworkReply.NoError

    def readAll(self):
        data, self.data = self.data, b''
        return QByteArray(data)

    def attribute(self, key):
        return self.status

    def error(self):
        return self.code

    def abort(self):
        self.code = QNetworkReply.OperationCanceledError
        self.finished.emit()


class Manager:
    def __init__(self):
        self.requests = []
        self.reply = Reply()

    def get(self, request):
        self.requests.append(request)
        return self.reply


@pytest.mark.parametrize('status,body,expected', [
    (200, json.dumps(payload()).encode(), ''),
    (200, b'bad json', '格式'), (403,b'{}','受限'),
    (404,b'{}','未找到'), (500,b'{}','网络'),
])
def test_async_check_and_errors(app,status,body,expected):
    manager = Manager()
    checker = UpdateChecker(manager=manager)
    results=[]; busy=[]
    checker.finished.connect(lambda r,e: results.append((r,e)))
    checker.busy_changed.connect(busy.append)
    checker.check(); checker.check()
    assert len(manager.requests)==1 and checker.deadline.isActive()
    assert manager.requests[0].url().toString()==API_URL
    assert not manager.requests[0].hasRawHeader('Authorization')
    manager.reply.status=status; manager.reply.data=body
    manager.reply.readyRead.emit(); manager.reply.finished.emit()
    assert checker.reply is None and not checker.deadline.isActive()
    assert busy==[True,False] and len(results)==1
    if expected:
        assert results[0][0] is None and expected in results[0][1]
    else:
        assert results[0][0].version=='1.3.0' and results[0][1]==''


def test_bounded_response_and_cancel(app):
    for oversized in (False, True):
        manager=Manager(); checker=UpdateChecker(manager=manager); errors=[]
        checker.finished.connect(lambda r,e: errors.append(e))
        checker.check()
        if oversized:
            manager.reply.data=b'x'*(MAX_RESPONSE+1)
            manager.reply.readyRead.emit()
            assert '过大' in errors[0]
        else:
            checker.deadline.timeout.emit()
            assert '网络' in errors[0]
        assert checker.reply is None and not checker.deadline.isActive()


@pytest.mark.parametrize('entry', ['settings', 'tray'])
def test_manual_check_about_download_and_retry(app,tmp_path,monkeypatch,entry):
    w=MainWindow(Store(tmp_path),FakeHotkey(),FakeStartup())
    manager=Manager()
    w.update_checker.deleteLater()
    w.update_checker=UpdateChecker(w,manager)
    w.update_checker.finished.connect(w.update_checked)
    shown=[]
    monkeypatch.setattr(AboutDialog,'exec',lambda dialog: shown.append(dialog) or 0)
    settings=None
    if entry=='settings':
        settings=SettingsDialog(w)
        next(b for b in settings.findChildren(QPushButton) if b.text()=='关于软件').click()
    else:
        w.about()
    assert len(shown)==1
    about=shown[0]
    assert about.parent() is (settings if settings else w)
    opened=[]
    monkeypatch.setattr(QDesktopServices,'openUrl',lambda url: opened.append(url.toString()) or True)
    next(b for b in about.findChildren(QPushButton) if b.text()=='检查更新').click()
    dialog=w.update_dialog
    assert dialog.parent() is about and not dialog.action.isEnabled()
    manager.reply.data=json.dumps(payload()).encode()
    manager.reply.finished.emit()
    assert dialog.action.text()=='下载更新' and dialog.action.isEnabled()
    dialog.act()
    assert opened==['https://github.com/DTyun/screenshot-chat/releases/tag/v1.3.0']
    assert w.store.count()==0 and w.pending_update is None
    dialog.reject(); app.processEvents()
    assert w.update_dialog is None
    about.close()
    if settings:
        settings.close()
    w.tray.hide(); w.quitting=True; w.close()


def test_background_checks_defer_during_capture_hidden_and_modal(app,tmp_path,monkeypatch):
    w=MainWindow(Store(tmp_path),FakeHotkey(),FakeStartup())
    w.hide()
    notices=[]
    monkeypatch.setattr(w.tray,'showMessage',lambda *args: notices.append(args))
    release=parse_release(payload())
    w.update_checked(None,'断网')
    assert w.update_dialog is None and w.pending_update is None
    w.update_checked(release,'')
    assert notices and w.pending_update is release
    w.present_update()
    assert w.update_dialog is None
    w.show(); monkeypatch.setattr(w,'isActiveWindow',lambda: True)
    w.capture_busy=True
    w.present_update()
    assert w.update_dialog is None
    w.capture_busy=False
    monkeypatch.setattr('src.ui.QApplication.activeModalWidget',lambda: w)
    w.present_update()
    assert w.update_dialog is None
    monkeypatch.setattr('src.ui.QApplication.activeModalWidget',lambda: None)
    w.present_update()
    assert w.update_dialog.release is release and w.pending_update is None
    w.update_dialog.reject()
    w.tray.hide(); w.quitting=True; w.close()
