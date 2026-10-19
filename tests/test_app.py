import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import pytest
from PySide6.QtCore import QObject, Signal, Qt, QPoint
from PySide6.QtGui import QImage, QColor, QPixmap
from PySide6.QtWidgets import QApplication, QDialog
from PySide6.QtTest import QTest
from src.storage import Store
from src.platform_win import parse_hotkey, SingleInstance, GlobalHotkey, Startup
from src.ui import MainWindow, SettingsDialog
from src.capture import SelectionOverlay
from src.theme import stylesheet


@pytest.fixture(scope='session')
def app():
    a = QApplication.instance() or QApplication([])
    a.setStyle('Fusion')
    a.setStyleSheet(stylesheet())
    yield a


@pytest.fixture
def image():
    im = QImage(900, 480, QImage.Format_RGB32)
    im.fill(QColor('#07A653'))
    return im


def test_save_restart_copy_delete(tmp_path, image):
    store = Store(tmp_path)
    m = store.save(image)
    store.db.close()
    store = Store(tmp_path)
    assert store.count() == 1
    assert store.page()[0] == m
    original = QImage(str(store.images / m['filename']))
    assert original.size() == image.size()
    assert original.pixelColor(0,0) == image.pixelColor(0,0)
    store.delete(m)
    assert store.count() == 0
    assert not list(store.images.iterdir())
    assert not list(store.thumbs.iterdir())


def test_paging_and_failed_save(tmp_path, image, monkeypatch):
    store = Store(tmp_path)
    for _ in range(45):
        store.save(image)
    latest = store.page()
    assert len(latest) == 40
    assert len(store.page(latest[0]['id'])) == 5
    with pytest.raises(ValueError):
        store.save(QImage())
    assert store.count() == 45
    files = set(store.images.iterdir())
    monkeypatch.setattr(QImage, 'save', lambda *a: False)
    with pytest.raises(OSError):
        store.save(image)
    assert store.count() == 45
    assert set(store.images.iterdir()) == files


def test_interrupted_delete_recovery(tmp_path, image):
    store = Store(tmp_path)
    m = store.save(image)
    path = store.images / m['filename']
    path.rename(path.with_suffix('.deleting'))
    store.db.close()
    store = Store(tmp_path)
    assert path.exists()
    assert store.count() == 1


def test_malformed_settings_falls_back(tmp_path):
    store = Store(tmp_path)
    for text in ('null', '[]', '{"hotkey":42}', 'invalid json'):
        (tmp_path / 'settings.json').write_text(text, encoding='utf-8')
        assert store.settings()['hotkey'] == 'Ctrl+Alt+A'


def test_delete_failure_rolls_back(tmp_path, image, monkeypatch):
    store = Store(tmp_path)
    m = store.save(image)
    real = Path.rename
    def rename(path, target):
        if path.parent == store.thumbs:
            raise PermissionError('test locked file')
        return real(path, target)
    monkeypatch.setattr(Path, 'rename', rename)
    with pytest.raises(PermissionError):
        store.delete(m)
    assert store.count() == 1
    assert (store.images / m['filename']).exists()


def test_hotkey_validation():
    assert parse_hotkey('Ctrl+Alt+A') == (0x4003, 65)
    assert parse_hotkey('F8') == (0x4000, 0x77)
    for text in ('A', '', 'Ctrl+Tab', 'Ctrl+F25', 'Ctrl+Alt'):
        with pytest.raises(ValueError):
            parse_hotkey(text)


def test_single_instance_mutex():
    import uuid
    name = 'Local\\ScreenshotChatTest_'+uuid.uuid4().hex
    first = SingleInstance(name)
    second = SingleInstance(name)
    try:
        assert first.is_primary
        assert not second.is_primary
    finally:
        second.close()
        first.close()


def test_real_hotkey_conflict_retains_previous(app):
    first, second = GlobalHotkey(app), GlobalHotkey(app)
    try:
        first.set('Ctrl+Alt+F10')
        second.set('Ctrl+Alt+F11')
        with pytest.raises(ValueError):
            second.set('Ctrl+Alt+F10')
        assert second.current[0] == 'Ctrl+Alt+F11'
    finally:
        first.close()
        second.close()


class FakeEvents(QObject):
    triggered = Signal()


class FakeHotkey:
    def __init__(self):
        self.events = FakeEvents()
    def set(self, text):
        parse_hotkey(text)
    def close(self):
        pass


class FakeStartup:
    def __init__(self):
        self.value = None
    def read(self):
        return self.value
    def set_enabled(self, enabled):
        self.value = ('"C:\\Test App\\Pianyu.exe" --autostart', 1) if enabled else None
    def restore(self, value):
        self.value = value


def test_ui_flow(app, tmp_path, image, monkeypatch):
    from src import ui
    w = MainWindow(Store(tmp_path), FakeHotkey(), FakeStartup())
    w.show()
    app.processEvents()
    assert w.empty.isVisible()
    assert not w.send_button.isEnabled()
    QApplication.clipboard().setImage(image)
    QTest.keyClick(w, Qt.Key_V, Qt.ControlModifier)
    app.processEvents()
    assert w.pending is not None
    QTest.mouseClick(w.send_button, Qt.LeftButton)
    app.processEvents()
    assert w.store.count() == 1 and w.pending is None
    item = w.history.item(0)
    w.copy(item)
    assert QApplication.clipboard().image().width() == 900
    monkeypatch.setattr(ui.ConfirmDelete, 'exec', lambda self: QDialog.Rejected)
    w.delete(item)
    assert w.store.count() == 1
    monkeypatch.setattr(ui.ConfirmDelete, 'exec', lambda self: QDialog.Accepted)
    w.delete(item)
    assert w.store.count() == 0
    assert w.empty.isVisible()
    w.set_pending(image)
    monkeypatch.setattr(w.store, 'save', lambda *args: (_ for _ in ()).throw(OSError('disk full')))
    w.send()
    assert w.pending is not None and w.send_button.isEnabled()
    assert 'disk full' in w.status.text()
    dialog = SettingsDialog(w)
    dialog.editor.setKeySequence('Ctrl+Shift+F8')
    dialog.save()
    assert w.store.settings()['hotkey'] == 'Ctrl+Shift+F8'
    w.quitting = True
    w.tray.hide()
    w.close()


def test_capture_crop_and_cancel(app, image):
    pix = QPixmap.fromImage(image)
    overlay = SelectionOverlay(app.primaryScreen(), pix)
    overlay.resize(900,480)
    overlay.show()
    received = []
    overlay.selected.connect(received.append)
    QTest.mousePress(overlay, Qt.LeftButton, pos=QPoint(20,30))
    QTest.mouseMove(overlay, QPoint(219,129))
    QTest.mouseRelease(overlay, Qt.LeftButton, pos=QPoint(219,129))
    assert not received
    assert overlay.toolbar.isVisible()
    overlay.finish()
    assert received[0].size().width() == 200
    assert received[0].size().height() == 100
    cancelled = []
    overlay.cancelled.connect(lambda: cancelled.append(True))
    QTest.keyClick(overlay, Qt.Key_Escape)
    assert cancelled
    overlay.close()


def test_capture_high_dpi(app):
    pix = QPixmap(1800, 960)
    pix.fill(QColor('#07A653'))
    pix.setDevicePixelRatio(2)
    overlay = SelectionOverlay(app.primaryScreen(), pix)
    overlay.resize(900,480)
    overlay.show()
    received = []
    overlay.selected.connect(received.append)
    QTest.mousePress(overlay, Qt.LeftButton, pos=QPoint(20,30))
    QTest.mouseRelease(overlay, Qt.LeftButton, pos=QPoint(219,129))
    overlay.finish()
    assert received[0].width() == 400
    assert received[0].height() == 200
    assert received[0].devicePixelRatio() == 1
    overlay.close()


def test_startup_registry_roundtrip(monkeypatch):
    import winreg
    import uuid
    import sys
    path = r'Software\PianyuTest_' + uuid.uuid4().hex
    startup = Startup(path)
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, 'executable', r'C:\My Apps\片语\Pianyu.exe')
    try:
        assert startup.read() is None
        startup.set_enabled(True)
        value = startup.read()
        assert value == ('"C:\\My Apps\\片语\\Pianyu.exe" --autostart', winreg.REG_SZ)
        startup.set_enabled(False)
        assert startup.read() is None
        startup.set_enabled(False)
        startup.restore(value)
        assert startup.read() == value
    finally:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)


def test_startup_checkbox_and_rollback(app, tmp_path, monkeypatch):
    startup = FakeStartup()
    w = MainWindow(Store(tmp_path), FakeHotkey(), startup)
    dialog = SettingsDialog(w)
    assert not dialog.autostart.isChecked()
    dialog.autostart.setChecked(True)
    dialog.reject()
    assert startup.read() is None
    dialog = SettingsDialog(w)
    dialog.autostart.setChecked(True)
    dialog.save()
    saved = startup.read()
    assert saved is not None
    dialog = SettingsDialog(w)
    assert dialog.autostart.isChecked()
    dialog.autostart.setChecked(False)
    monkeypatch.setattr(w.store, 'save_settings', lambda settings: (_ for _ in ()).throw(OSError('disk full')))
    dialog.save()
    assert startup.read() == saved
    assert 'disk full' in dialog.error.text()
    monkeypatch.undo()
    dialog.save()
    assert startup.read() is None
    w.tray.hide()
    w.quitting = True
    w.close()


def test_title_bar_controls(app, tmp_path):
    w = MainWindow(Store(tmp_path), FakeHotkey(), FakeStartup())
    w.show()
    app.processEvents()
    QTest.mouseClick(w.title_bar.pin, Qt.LeftButton)
    assert w.windowFlags() & Qt.WindowStaysOnTopHint
    assert w.title_bar.pin.isChecked()
    QTest.mouseClick(w.title_bar.pin, Qt.LeftButton)
    assert not w.windowFlags() & Qt.WindowStaysOnTopHint
    QTest.mouseClick(w.title_bar.maximize, Qt.LeftButton)
    assert w.isMaximized()
    QTest.mouseClick(w.title_bar.maximize, Qt.LeftButton)
    assert not w.isMaximized()
    w.tray.hide()
    w.quitting = True
    w.close()


def test_text_conversations_and_literal_search(tmp_path, image):
    store = Store(tmp_path)
    second = store.create_conversation('工作记录')
    a = store.save_text('完成 100% 测试_记录\n第二行')
    store.save_text('完成 100% 测试_记录', second)
    store.save(image, '截图备注', second)
    assert store.count() == 1 and store.count(second) == 2
    assert len(store.search('100%')) == 1
    assert store.search('测试_')[0]['id'] == a['id']
    assert len(store.search('截图', conversation_id=second)) == 1
    assert store.search('截图') == []
    store.rename_conversation(second, '项目资料')
    assert store.conversations()[1]['name'] == '项目资料'
    store.delete(a)
    assert store.count() == 0
    with pytest.raises(ValueError):
        store.save_text('   ')


def test_legacy_database_migration(tmp_path):
    import sqlite3
    db = sqlite3.connect(tmp_path / 'history.db')
    db.execute('CREATE TABLE messages (id INTEGER PRIMARY KEY AUTOINCREMENT, filename TEXT UNIQUE NOT NULL, created TEXT NOT NULL, width INTEGER NOT NULL, height INTEGER NOT NULL)')
    db.execute("INSERT INTO messages VALUES(7,'legacy.png','2026-10-19T10:00:00',100,80)")
    db.commit()
    db.close()
    store = Store(tmp_path)
    assert store.page()[0]['id'] == 7
    assert store.page()[0]['kind'] == 'image'
    assert store.page()[0]['conversation_id'] == 1
    assert store.save_text('升级后新增的消息')['id'] > 7


def test_text_ui_search_locate_and_chat_drafts(app, tmp_path, image):
    from src.search import SearchDialog
    w = MainWindow(Store(tmp_path), FakeHotkey(), FakeStartup())
    w.show()
    w.text_editor.setPlainText('今天安排：发送测试文字')
    QTest.keyClick(w.text_editor, Qt.Key_Return)
    assert w.store.count() == 1
    assert w.text_editor.toPlainText() == ''
    QTest.keyClick(w.text_editor, Qt.Key_Return, Qt.ShiftModifier)
    assert '\n' in w.text_editor.toPlainText()
    w.text_editor.clear()
    for n in range(80):
        w.store.save_text(f'历史记录 {n}')
    w.reload_latest()
    search = SearchDialog(w)
    search.query.setText('今天安排')
    search.reset()
    assert search.results.count() == 1
    result = search.results.item(0).data(Qt.UserRole)
    search.locate(result['id'])
    assert w.history.currentItem().data(Qt.UserRole)['id'] == result['id']
    assert w.newer_button.isVisible()
    w.load_newer()
    assert w.history.count() > 40
    second = w.store.create_conversation('测试聊天')
    w.refresh_conversations()
    w.text_editor.setPlainText('尚未发送的草稿')
    w.set_pending(image)
    w.chats.setCurrentRow(1)
    assert w.chat_id == second and w.pending is None
    w.text_editor.setPlainText('第二个聊天')
    w.send()
    assert w.store.count(second) == 1
    w.chats.setCurrentRow(0)
    assert w.pending is not None and w.text_editor.toPlainText() == '尚未发送的草稿'
    search = SearchDialog(w)
    search.query.setText('第二个聊天')
    search.reset()
    assert search.results.count() == 0
    search.close()
    w.tray.hide()
    w.quitting = True
    w.close()


def test_cache_move_and_no_migration(tmp_path, image):
    from src.relocation import prepare_destination
    source, target, empty = tmp_path/'source', tmp_path/'target', tmp_path/'empty'
    store = Store(source)
    chat = store.create_conversation('需要迁移的聊天')
    record = store.save(image, '说明文字', chat)
    store.save_text('迁移文字', chat)
    prepare_destination(source, target, True)
    moved = Store(target)
    assert moved.count(chat) == 2
    assert (moved.images / record['filename']).exists()
    assert moved.conversations()[1]['name'] == '需要迁移的聊天'
    assert store.count(chat) == 2  # Original directory remains a recovery backup.
    prepare_destination(source, empty, False)
    assert Store(empty).count() == 0
    with pytest.raises(ValueError):
        prepare_destination(source, target, True)
    with pytest.raises(ValueError):
        prepare_destination(source, source/'nested', True)


def test_failed_migration_preserves_source(tmp_path, image, monkeypatch):
    from src import relocation
    source, target = tmp_path/'source', tmp_path/'target'
    store = Store(source)
    message = store.save(image)
    monkeypatch.setattr(relocation.shutil, 'copytree', lambda *args, **kwargs: (_ for _ in ()).throw(OSError('disk full')))
    with pytest.raises(OSError):
        relocation.prepare_destination(source,target,True)
    assert store.count() == 1 and (store.images / message['filename']).exists()
    assert not list(tmp_path.glob('.screenshot-chat-move-*'))
    assert not target.exists()


def test_cache_setting_background_switch(app, tmp_path, image, monkeypatch):
    from src.storage import default_root
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path/'config'))
    source, target = tmp_path/'source', tmp_path/'target'
    w = MainWindow(Store(source), FakeHotkey(), FakeStartup())
    w.store.save_text('迁移保留消息')
    w.store.save(image)
    dialog = SettingsDialog(w)
    assert dialog.migrate.isChecked()
    dialog.cache_path.setText(str(target))
    dialog.save()
    assert not dialog.error.text(), dialog.error.text()
    assert w.store.root == target and w.store.count() == 2
    assert default_root() == target
    blank = tmp_path/'blank'
    dialog = SettingsDialog(w)
    dialog.cache_path.setText(str(blank))
    dialog.migrate.setChecked(False)
    dialog.save()
    assert w.store.root == blank and w.store.count() == 0
    assert Store(target).count() == 2
    w.store.db.close()
    w.tray.hide()
    w.quitting = True
    w.close()


def test_new_chat_button_and_rename(app, tmp_path, monkeypatch):
    from src import ui
    w = MainWindow(Store(tmp_path), FakeHotkey(), FakeStartup())
    w.show()
    def accept_name(dialog):
        dialog.value = '新建工作聊天'
        return QDialog.Accepted
    monkeypatch.setattr(ui.ChatNameDialog, 'exec', accept_name)
    QTest.mouseClick(w.add_chat_button, Qt.LeftButton)
    assert w.chats.count() == 2 and w.chat_id != 1
    chat = w.chats.currentItem().data(Qt.UserRole)
    def rename_name(dialog):
        dialog.value = '已重命名的聊天'
        return QDialog.Accepted
    monkeypatch.setattr(ui.ChatNameDialog, 'exec', rename_name)
    w.rename_conversation(chat)
    assert w.chat_title.text() == '已重命名的聊天'
    w.chat_filter.setText('不存在的聊天')
    assert all(w.chats.item(i).isHidden() for i in range(w.chats.count()))
    w.chat_filter.clear()
    assert all(not w.chats.item(i).isHidden() for i in range(w.chats.count()))
    w.tray.hide()
    w.quitting = True
    w.close()


@pytest.mark.parametrize('visible', [False, True])
def test_capture_confirm_opens_chat_and_inserts_without_losing_draft(app, tmp_path, image, visible):
    w = MainWindow(Store(tmp_path), FakeHotkey(), FakeStartup())
    w.was_visible = visible
    if visible:
        w.show()
    w.text_editor.setPlainText('原有草稿')
    previous = image.copy(0,0,50,50)
    w.set_pending(previous)
    w.status.setText('原来的状态')
    w.hide()
    w.captured(image)
    assert QApplication.clipboard().image().size() == image.size()
    assert w.isVisible()
    assert len(w.text_editor.images()) == 2
    assert w.text_editor.images()[0].size() == previous.size()
    assert w.text_editor.images()[1].size() == image.size()
    assert w.text_editor.toPlainText() == '原有草稿'
    assert w.status.text() == '原来的状态'
    assert w.store.count() == 0
    w.tray.hide()
    w.quitting = True
    w.close()


def test_capture_cancel_does_not_paste_or_open_hidden_chat(app, tmp_path, image):
    w = MainWindow(Store(tmp_path),FakeHotkey(),FakeStartup())
    w.was_visible = False
    w.hide()
    QApplication.clipboard().setImage(image)
    w.capture_cancelled()
    assert not w.isVisible() and not w.text_editor.images()
    assert QApplication.clipboard().image().size() == image.size()
    w.tray.hide()
    w.quitting = True
    w.close()


def test_unified_editor_image_editing_and_draft_restore(app, tmp_path, image):
    from PySide6.QtGui import QTextCursor, QTextDocument
    from PySide6.QtCore import QUrl
    w = MainWindow(Store(tmp_path), FakeHotkey(), FakeStartup())
    w.show()
    app.processEvents()
    editor = w.text_editor
    w.set_pending(image)
    editor.insertPlainText('图片旁边可以写字')
    QTest.mouseClick(editor.viewport(), Qt.LeftButton, pos=QPoint(editor.viewport().width()-20,editor.viewport().height()-25))
    editor.insertPlainText('，空白处也可以继续编辑')
    assert '空白处' in editor.toPlainText()
    cursor = editor.textCursor()
    cursor.setPosition(0)
    cursor.movePosition(QTextCursor.NextCharacter,QTextCursor.KeepAnchor)
    editor.setTextCursor(cursor)
    editor.copy()
    assert QApplication.clipboard().image().size() == image.size()
    QTest.keyClick(editor,Qt.Key_Delete)
    assert w.pending is None
    editor.undo()
    assert w.pending is not None
    replacement = image.copy(0,0,75,60)
    cursor.setPosition(0)
    cursor.movePosition(QTextCursor.NextCharacter,QTextCursor.KeepAnchor)
    editor.setTextCursor(cursor)
    w.set_pending(replacement)
    assert len(editor.images()) == 1 and w.pending.size() == replacement.size()
    second = w.store.create_conversation('输入区草稿')
    w.refresh_conversations()
    w.chats.setCurrentRow(1)
    assert w.chat_id == second and not editor.images()
    w.chats.setCurrentRow(0)
    assert editor.images()[0].size() == replacement.size()
    assert '空白处' in editor.toPlainText()
    assert not editor.document().resource(QTextDocument.ImageResource,QUrl(next(iter(editor.resources)))).isNull()
    w.send()
    saved = w.store.page()[0]
    assert saved['width'] == 75 and '空白处' in saved['text']
    assert not editor.images() and editor.toPlainText() == ''
    w.tray.hide()
    w.quitting = True
    w.close()


def test_multi_image_draft_is_atomic(tmp_path, image):
    store = Store(tmp_path)
    with pytest.raises(ValueError):
        store.save_composed([(image,''),(QImage(),'')])
    assert store.count() == 0
    assert not list(store.images.iterdir())
    records = store.save_composed([(None,'第一段'),(image,''),(None,'第二段'),(image.copy(0,0,40,30),'')])
    assert [m['kind'] for m in records] == ['text','image','text','image']
    assert store.count() == 4


def test_annotation_tools_undo_and_save(app, tmp_path, monkeypatch):
    from PySide6.QtGui import QPainter
    from PySide6.QtWidgets import QFileDialog
    pix = QPixmap(640,480)
    pix.fill(QColor('white'))
    painter = QPainter(pix)
    painter.setPen(QColor('red'))
    painter.drawLine(0,0,640,480)
    painter.end()
    overlay = SelectionOverlay(app.primaryScreen(),pix)
    overlay.resize(640,480)
    overlay.show()
    QTest.mousePress(overlay,Qt.LeftButton,pos=QPoint(80,80))
    QTest.mouseRelease(overlay,Qt.LeftButton,pos=QPoint(500,360))
    baseline = overlay.edited.copy()
    for tool in ('rect','ellipse','arrow','pen','mosaic'):
        overlay.set_tool(tool)
        QTest.mousePress(overlay,Qt.LeftButton,pos=QPoint(110,110))
        QTest.mouseMove(overlay,QPoint(300,200))
        QTest.mouseRelease(overlay,Qt.LeftButton,pos=QPoint(300,200))
        assert overlay.edited != baseline, tool
        overlay.undo()
        assert overlay.edited == baseline, tool
    overlay.set_tool('text')
    QTest.mouseClick(overlay,Qt.LeftButton,pos=QPoint(110,110))
    overlay.text_field.setText('文字标注')
    overlay.commit_text()
    assert overlay.edited != baseline
    target = tmp_path/'annotation.png'
    monkeypatch.setattr(QFileDialog,'getSaveFileName',lambda *args: (str(target),'PNG 图片 (*.png)'))
    received = []
    overlay.selected.connect(received.append)
    overlay.save_image()
    assert target.exists() and received
    assert QImage(str(target)) == overlay.edited
    overlay.close()


def test_multiple_inline_images_send_in_document_order(app, tmp_path, image):
    w = MainWindow(Store(tmp_path), FakeHotkey(), FakeStartup())
    w.text_editor.insertPlainText('前面文字')
    w.set_pending(image)
    w.text_editor.insertPlainText('中间文字')
    w.set_pending(image.copy(0,0,40,30))
    w.send()
    messages = w.store.page()
    assert [m['kind'] for m in messages] == ['text','image','text','image']
    assert messages[0]['text']=='前面文字' and messages[2]['text']=='中间文字'
    assert messages[1]['width']==900 and messages[3]['width']==40
    assert not w.text_editor.images() and not w.send_button.isEnabled()
    w.tray.hide()
    w.quitting = True
    w.close()


@pytest.mark.parametrize('caption', ['', '截图备注文字'])
def test_selected_image_keeps_pixels_and_caption(app, tmp_path, image, caption):
    from PySide6.QtCore import QRect
    from PySide6.QtGui import QPainter
    from PySide6.QtWidgets import QStyleOptionViewItem, QStyle
    w = MainWindow(Store(tmp_path),FakeHotkey(),FakeStartup())
    w.store.save(image,caption)
    w.reload_latest()
    delegate = w.history.itemDelegate()
    index = w.history.model().index(0,0)
    def paint(focused):
        canvas = QImage(600,400,QImage.Format_RGB32)
        canvas.fill(QColor('#FAFAFA'))
        painter = QPainter(canvas)
        option = QStyleOptionViewItem()
        option.rect = QRect(0,0,600,400)
        option.state = QStyle.State_Enabled
        if focused:
            option.state |= QStyle.State_HasFocus | QStyle.State_Selected
        delegate.paint(painter,option,index)
        painter.end()
        return canvas
    unfocused,focused = paint(False),paint(True)
    size = delegate.dimensions(index.data(Qt.UserRole),600)
    image_x = 599-54-14-size.width()
    inside = QRect(image_x+4,38,size.width()-8,size.height()-8)
    assert focused.copy(inside) == unfocused.copy(inside)
    assert focused.pixelColor(inside.center()) == image.pixelColor(0,0)
    if caption:
        doc = delegate.document(caption,600)
        text_inside = QRect(599-54-24-round(doc.size().width())+10,34+size.height()+10,round(doc.size().width()),round(doc.size().height()))
        assert focused.copy(text_inside) == unfocused.copy(text_inside)
    w.tray.hide()
    w.quitting = True
    w.close()


def test_double_click_uses_read_only_internal_viewer(app, tmp_path, image, monkeypatch):
    from PySide6.QtGui import QDesktopServices
    from PySide6.QtWidgets import QPushButton
    w = MainWindow(Store(tmp_path),FakeHotkey(),FakeStartup())
    record = w.store.save(image)
    w.reload_latest()
    w.show()
    app.processEvents()
    monkeypatch.setattr(QDesktopServices,'openUrl',lambda *args: pytest.fail('Image viewing must stay inside the app'))
    item = w.history.item(0)
    QTest.mouseClick(w.history.viewport(),Qt.LeftButton,pos=w.history.visualItemRect(item).center())
    QTest.mouseDClick(w.history.viewport(),Qt.LeftButton,pos=w.history.visualItemRect(item).center())
    app.processEvents()
    viewer = w.image_viewer
    assert viewer is not None and viewer.isVisible()
    assert viewer.pixmap.size() == image.size()
    assert viewer.windowFlags() & Qt.WindowCloseButtonHint
    assert not viewer.windowFlags() & Qt.WindowMinMaxButtonsHint
    assert not viewer.findChildren(QPushButton)
    bounds = viewer.view.transform().mapRect(viewer.view.sceneRect())
    assert bounds.width() <= viewer.view.viewport().width()+1
    assert bounds.height() <= viewer.view.viewport().height()+1
    QTest.keyClick(viewer,Qt.Key_Escape)
    assert not viewer.isVisible() and w.isVisible()
    w.open_image(item)
    assert w.image_viewer is viewer and viewer.isVisible()
    assert QImage(str(w.store.images/record['filename'])) == image
    viewer.close()
    w.tray.hide()
    w.quitting = True
    w.close()


def test_image_viewer_missing_and_corrupt_files(app, tmp_path, image):
    w = MainWindow(Store(tmp_path),FakeHotkey(),FakeStartup())
    record = w.store.save(image)
    w.reload_latest()
    path = w.store.images/record['filename']
    path.unlink()
    w.open_image(w.history.item(0))
    assert w.image_viewer is None
    assert '移动或删除' in w.status.text()
    path.write_bytes(b'invalid image')
    w.open_image(w.history.item(0))
    assert w.image_viewer is None
    assert '读取失败' in w.status.text()
    w.tray.hide()
    w.quitting = True
    w.close()


def test_delete_conversation_removes_all_pages_and_files(tmp_path, image):
    store = Store(tmp_path)
    removed = store.create_conversation('删除的聊天')
    for i in range(43):
        store.save_text(f'记录 {i}',removed)
    record = store.save(image,'图片备注',removed)
    kept = store.save(image,'保留的图片',1)
    store.delete_conversation(removed)
    assert store.count(removed)==0 and store.search(conversation_id=removed)==[]
    assert not any(c['id']==removed for c in store.conversations())
    for folder in (store.images,store.thumbs):
        assert not (folder/record['filename']).exists()
        assert not list(folder.glob('*.deleting'))
        assert (folder/kept['filename']).exists()
    assert store.count(1)==1
    store.db.close()
    store = Store(tmp_path)
    assert not any(c['id']==removed for c in store.conversations())


def test_delete_chat_file_failure_restores_whole_chat(tmp_path, image, monkeypatch):
    store = Store(tmp_path)
    records = [store.save(image),store.save_text('保留文字'),store.save(image)]
    real = Path.rename
    def rename(path,target):
        if path.parent == store.thumbs:
            raise PermissionError('test locked image')
        return real(path,target)
    monkeypatch.setattr(Path,'rename',rename)
    with pytest.raises(PermissionError):
        store.delete_conversation(1)
    assert store.count()==3 and len(store.conversations())==1
    for record in (records[0],records[2]):
        assert (store.images/record['filename']).exists()
        assert (store.thumbs/record['filename']).exists()
    assert not list(store.images.glob('*.deleting'))


def test_delete_chat_database_failure_rolls_back_files_and_messages(tmp_path, image):
    import sqlite3
    store=Store(tmp_path)
    record=store.save(image,'图片备注')
    store.save_text('重要文字')
    store.db.execute("CREATE TRIGGER reject_chat_delete BEFORE DELETE ON conversations BEGIN SELECT RAISE(ABORT,'test database failure'); END")
    store.db.commit()
    with pytest.raises(sqlite3.IntegrityError):
        store.delete_conversation(1)
    assert store.count()==2 and store.conversations()[0]['id']==1
    assert len(store.search('重要文字'))==1
    for folder in (store.images,store.thumbs):
        assert (folder/record['filename']).exists()
        assert not list(folder.glob('*.deleting'))


def test_delete_last_chat_creates_empty_chat_and_restart(app, tmp_path, image, monkeypatch):
    from src.ui import ConfirmDelete
    w = MainWindow(Store(tmp_path),FakeHotkey(),FakeStartup())
    chat = w.store.conversations()[0]
    w.store.save(image,'旧消息')
    w.text_editor.insertPlainText('旧草稿')
    monkeypatch.setattr(ConfirmDelete,'exec',lambda self: QDialog.Accepted)
    w.delete_conversation(chat)
    assert w.chat_id != chat['id'] and w.history.count()==0
    assert w.text_editor.toPlainText()==''
    assert w.store.count(w.chat_id)==0
    assert w.chats.count()==1 and w.chat_title.text()=='我的图片'
    current = w.chat_id
    w.store.db.close()
    w.tray.hide()
    w.quitting=True
    w.close()
    store = Store(tmp_path)
    assert [c['id'] for c in store.conversations()]==[current]
    assert not list(store.images.iterdir()) and not list(store.thumbs.iterdir())
    w = MainWindow(store,FakeHotkey(),FakeStartup())
    assert w.chat_id==current
    w.tray.hide()
    w.quitting=True
    w.close()


def test_delete_chat_confirmation_cancel_and_other_draft(app, tmp_path, image, monkeypatch):
    from src.ui import ConfirmDelete
    from PySide6.QtWidgets import QLabel
    w = MainWindow(Store(tmp_path),FakeHotkey(),FakeStartup())
    identifier=w.store.create_conversation('test2')
    record=w.store.save(image,'待删备注',identifier)
    chat=next(c for c in w.store.conversations() if c['id']==identifier)
    w.text_editor.insertPlainText('当前聊天草稿')
    dialog=ConfirmDelete(w,chat=chat)
    text=' '.join(l.text() for l in dialog.findChildren(QLabel))
    assert all(word in text for word in ('test2','全部聊天记录','文字','图片','本地原图','无法撤销'))
    dialog.close()
    monkeypatch.setattr(ConfirmDelete,'exec',lambda self: QDialog.Rejected)
    w.delete_conversation(chat)
    assert w.store.count(identifier)==1 and (w.store.images/record['filename']).exists()
    monkeypatch.setattr(ConfirmDelete,'exec',lambda self: QDialog.Accepted)
    w.delete_conversation(chat)
    assert w.store.count(identifier)==0 and w.chat_id==1
    assert w.text_editor.toPlainText()=='当前聊天草稿'
    assert not (w.store.images/record['filename']).exists()
    w.tray.hide()
    w.quitting=True
    w.close()


def history_text_point(window,item,text_offset):
    from PySide6.QtGui import QTextCursor
    doc,rect=window.history.text_layout(item)
    text=item.data(Qt.UserRole)['text']
    cursor=QTextCursor(doc)
    cursor.setPosition(len(text[:text_offset].encode('utf-16-le'))//2)
    layout=cursor.block().layout()
    line=layout.lineForTextPosition(cursor.positionInBlock())
    x=line.cursorToX(cursor.positionInBlock())[0]
    return QPoint(round(rect.x()+10+layout.position().x()+x),round(rect.y()+10+layout.position().y()+line.y()+line.height()/2))


@pytest.mark.parametrize('with_image,reverse',[(False,False),(False,True),(True,False),(True,True)])
def test_partial_message_drag_and_copy(app,tmp_path,image,with_image,reverse):
    original='开始文字：\n目标🙂片段\n末尾保留文字'
    expected='标🙂片段\n末尾'
    w=MainWindow(Store(tmp_path),FakeHotkey(),FakeStartup())
    if with_image:
        record=w.store.save(image,original)
    else:
        record=w.store.save_text(original)
    w.reload_latest()
    w.show()
    w.activateWindow()
    app.processEvents()
    item=w.history.item(0)
    start=original.index(expected)
    points=[history_text_point(w,item,start),history_text_point(w,item,start+len(expected))]
    if reverse: points.reverse()
    QTest.mousePress(w.history.viewport(),Qt.LeftButton,pos=points[0])
    QTest.mouseMove(w.history.viewport(),points[1])
    QTest.mouseRelease(w.history.viewport(),Qt.LeftButton,pos=points[1])
    assert w.history.selected_text()==expected
    QTest.keyClick(w.history,Qt.Key_C,Qt.ControlModifier)
    assert app.clipboard().text()==expected
    assert w.store.page()[0]['text']==original
    if with_image:
        w.copy_image(item)
        assert app.clipboard().image()==image
    w.tray.hide()
    w.quitting=True
    w.close()


def test_selected_text_context_menu_and_chat_switch(app,tmp_path,monkeypatch):
    from PySide6.QtWidgets import QMenu
    w=MainWindow(Store(tmp_path),FakeHotkey(),FakeStartup())
    w.store.save_text('prefix selected suffix')
    other=w.store.create_conversation('其他聊天')
    w.reload_latest()
    w.refresh_conversations()
    w.show()
    app.processEvents()
    item=w.history.item(0)
    a,b=history_text_point(w,item,7),history_text_point(w,item,15)
    QTest.mousePress(w.history.viewport(),Qt.LeftButton,pos=a)
    QTest.mouseRelease(w.history.viewport(),Qt.LeftButton,pos=b)
    def choose(menu,*args):
        names=[action.text() for action in menu.actions()]
        assert '复制所选文字' in names and '复制全文' in names
        next(a for a in menu.actions() if a.text()=='复制所选文字').trigger()
    class TestMenu(QMenu):
        def exec(self,*args):
            return choose(self,*args)
    monkeypatch.setattr('src.ui.QMenu',TestMenu)
    w.context_menu(a)
    assert app.clipboard().text()=='selected'
    w.chats.setCurrentRow(1)
    assert w.chat_id==other and w.history.selected_text()==''
    w.chats.setCurrentRow(0)
    w.copy(w.history.item(0))
    assert app.clipboard().text()=='prefix selected suffix'
    w.tray.hide()
    w.quitting=True
    w.close()


def test_double_click_word_and_ctrl_a_in_history(app,tmp_path):
    original='prefix selected suffix'
    w=MainWindow(Store(tmp_path),FakeHotkey(),FakeStartup())
    w.store.save_text(original)
    w.reload_latest()
    w.show()
    w.activateWindow()
    app.processEvents()
    p=history_text_point(w,w.history.item(0),10)
    QTest.mouseClick(w.history.viewport(),Qt.LeftButton,pos=p)
    QTest.mouseDClick(w.history.viewport(),Qt.LeftButton,pos=p)
    assert w.history.selected_text()=='selected'
    QTest.keyClick(w.history,Qt.Key_A,Qt.ControlModifier)
    QTest.keyClick(w.history,Qt.Key_C,Qt.ControlModifier)
    assert app.clipboard().text()==original
    QTest.keyClick(w.history,Qt.Key_Backspace)
    assert w.store.page()[0]['text']==original
    w.reload_latest()
    assert w.history.selected_text()==''
    w.tray.hide()
    w.quitting=True
    w.close()


def test_partial_copy_across_soft_wrapped_lines(app,tmp_path):
    text='开头 '+('资料记录'*8)+'需要单独复制的内容🙂'+('结尾文字'*5)
    expected=text[5:50]
    w=MainWindow(Store(tmp_path),FakeHotkey(),FakeStartup())
    w.store.save_text(text)
    w.reload_latest()
    w.show()
    app.processEvents()
    item=w.history.item(0)
    a,b=history_text_point(w,item,5),history_text_point(w,item,50)
    assert b.y()>a.y()
    QTest.mousePress(w.history.viewport(),Qt.LeftButton,pos=a)
    QTest.mouseMove(w.history.viewport(),b)
    QTest.mouseRelease(w.history.viewport(),Qt.LeftButton,pos=b)
    w.copy(item)
    assert app.clipboard().text()==expected
    assert '\n' not in app.clipboard().text()
    w.tray.hide()
    w.quitting=True
    w.close()


def test_long_message_selection_scrolls_at_viewport_edge(app,tmp_path):
    w=MainWindow(Store(tmp_path),FakeHotkey(),FakeStartup())
    w.store.save_text('\n'.join(f'第{i}行文字' for i in range(120)))
    w.reload_latest()
    w.show()
    app.processEvents()
    w.history.verticalScrollBar().setValue(0)
    item=w.history.item(0)
    a=history_text_point(w,item,0)
    below=QPoint(a.x()+30,w.history.viewport().height()+15)
    QTest.mousePress(w.history.viewport(),Qt.LeftButton,pos=a)
    QTest.mouseMove(w.history.viewport(),below)
    QTest.qWait(160)
    assert w.history.verticalScrollBar().value()>0
    assert w.history.selected_text().startswith('第0行文字\n')
    QTest.mouseRelease(w.history.viewport(),Qt.LeftButton,pos=below)
    assert not w.history.selection_scroll.isActive()
    w.tray.hide()
    w.quitting=True
    w.close()
