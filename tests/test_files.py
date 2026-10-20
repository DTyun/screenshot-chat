from pathlib import Path
import shutil
import pytest
from PySide6.QtCore import Qt,QMimeData,QUrl,QPoint,QPointF
from PySide6.QtGui import QDesktopServices,QDropEvent,QDragEnterEvent,QTextCursor
from PySide6.QtWidgets import QApplication,QFileDialog
from PySide6.QtTest import QTest
from tests.test_app import app,image,FakeHotkey,FakeStartup
from src.storage import Store
from src.ui import MainWindow
from src.relocation import prepare_destination


@pytest.fixture
def file(tmp_path):
    path=tmp_path/'原始文件 报告.txt'
    path.write_text('文件内容🙂',encoding='utf-8')
    return path


@pytest.fixture
def window(app,tmp_path):
    w=MainWindow(Store(tmp_path/'cache'),FakeHotkey(),FakeStartup())
    w.show();w.activateWindow();app.processEvents()
    yield w
    w.tray.hide();w.quitting=True;w.close()


def file_mime(paths):
    mime=QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(p)) for p in paths])
    return mime


def test_file_copy_metadata_restart_and_duplicate_names(tmp_path,file):
    store=Store(tmp_path/'cache')
    first=store.save_file(file)
    second=store.save_file(file)
    assert first['filename']!=second['filename']
    assert first['original_name']==file.name
    assert first['file_size']==file.stat().st_size
    assert store.file_path(first['filename']).read_bytes()==file.read_bytes()
    assert store.search(file.name,kind='file')[0]['id']==second['id']
    file.unlink()
    store.db.close()
    store=Store(tmp_path/'cache')
    assert store.file_path(first['filename']).is_file()
    assert store.count()==2
    with pytest.raises(ValueError):store.file_path('../outside.txt')


def test_atomic_mixed_file_save_failure_leaves_source_and_draft_assets(tmp_path,file,image,monkeypatch):
    store=Store(tmp_path/'cache')
    def fail(source,destination):
        Path(destination).write_bytes(b'partial')
        raise OSError('test disk full')
    monkeypatch.setattr(shutil,'copyfile',fail)
    with pytest.raises(OSError):store.save_composed([(None,'文字'),(image,''),(file,'')])
    assert store.count()==0
    assert file.read_text('utf-8')=='文件内容🙂'
    assert not list(store.images.iterdir()) and not list(store.thumbs.iterdir())
    assert not [p for p in store.files.rglob('*') if p.is_file()]


def test_delete_file_and_chat_removes_only_cached_copy(tmp_path,file):
    store=Store(tmp_path/'cache')
    record=store.save_file(file)
    cached=store.file_path(record['filename'])
    store.delete(record)
    assert file.exists() and not cached.exists()
    identifier=store.create_conversation('文件聊天')
    record=store.save_file(file,conversation_id=identifier)
    cached=store.file_path(record['filename'])
    store.delete_conversation(identifier)
    assert file.exists() and not cached.exists() and store.count(identifier)==0


def test_file_delete_rollback_and_crash_recovery(tmp_path,file,monkeypatch):
    store=Store(tmp_path/'cache')
    record=store.save_file(file)
    path=store.file_path(record['filename'])
    real=Path.rename
    def deny(source,target):
        if source==path:raise PermissionError('test locked')
        return real(source,target)
    monkeypatch.setattr(Path,'rename',deny)
    with pytest.raises(PermissionError):store.delete(record)
    assert path.exists() and store.count()==1
    monkeypatch.undo()
    staged=path.with_name(path.name+'.deleting')
    path.rename(staged)
    store.db.close()
    store=Store(tmp_path/'cache')
    assert path.exists() and not staged.exists()
    path.rename(staged)
    with store.db:store.db.execute('DELETE FROM messages WHERE id=?',(record['id'],))
    store.db.close()
    store=Store(tmp_path/'cache')
    assert not staged.exists() and file.exists()


def test_legitimate_deleting_extension_is_not_treated_as_staged_file(tmp_path):
    source=tmp_path/'notes.deleting';source.write_bytes(b'keep')
    store=Store(tmp_path/'cache')
    record=store.save_file(source)
    store.db.close()
    store=Store(tmp_path/'cache')
    assert store.file_path(record['filename']).read_bytes()==b'keep'


def test_file_cache_migration_preserves_bytes(tmp_path,file):
    store=Store(tmp_path/'old')
    record=store.save_file(file)
    target=prepare_destination(store.root,tmp_path/'new',True)
    moved=Store(target)
    assert moved.file_path(record['filename']).read_bytes()==file.read_bytes()
    assert store.file_path(record['filename']).exists()


def test_clipboard_files_send_and_double_click_default_app(window,file,app,monkeypatch):
    app.clipboard().setMimeData(file_mime([file]))
    window.text_editor.setFocus()
    QTest.keyClick(window.text_editor,Qt.Key_V,Qt.ControlModifier)
    assert window.text_editor.files()==[file]
    assert not window.text_editor.images() and window.send_button.isEnabled()
    window.send()
    assert not window.text_editor.files()
    record=window.store.page()[0]
    assert record['kind']=='file'
    copied=window.store.file_path(record['filename'])
    file.unlink()
    opened=[]
    monkeypatch.setattr(QDesktopServices,'openUrl',lambda url:opened.append(Path(url.toLocalFile())) or True)
    item=window.history.item(0)
    point=window.history.visualItemRect(item).center()
    QTest.mouseClick(window.history.viewport(),Qt.LeftButton,pos=point)
    QTest.mouseDClick(window.history.viewport(),Qt.LeftButton,pos=point)
    assert opened==[copied.resolve()]
    window.copy_file(item)
    assert Path(app.clipboard().mimeData().urls()[0].toLocalFile())==copied.resolve()


def test_drop_file_uses_copy_action_and_upload_button(window,file,app,monkeypatch):
    mime=file_mime([file])
    enter=QDragEnterEvent(QPoint(10,10),Qt.CopyAction|Qt.MoveAction,mime,Qt.LeftButton,Qt.NoModifier)
    QApplication.sendEvent(window.text_editor.viewport(),enter)
    drop=QDropEvent(QPointF(10,10),Qt.CopyAction|Qt.MoveAction,mime,Qt.LeftButton,Qt.NoModifier)
    QApplication.sendEvent(window.text_editor.viewport(),drop)
    assert drop.isAccepted() and drop.dropAction()==Qt.CopyAction
    assert window.text_editor.files()==[file] and file.exists()
    window.text_editor.reset()
    monkeypatch.setattr(QFileDialog,'getOpenFileNames',lambda *args:([str(file)],''))
    QTest.mouseClick(window.upload_button,Qt.LeftButton)
    assert window.text_editor.files()==[file]
    monkeypatch.setattr(QFileDialog,'getOpenFileNames',lambda *args:([],''))
    window.choose_files()
    assert window.text_editor.files()==[file]


def test_mixed_text_image_files_send_in_order_and_draft_restore(window,file,image):
    editor=window.text_editor
    editor.insertPlainText('文件之前')
    editor.insert_files([file])
    editor.insertPlainText('图片之前')
    editor.insert_image(image)
    editor.insert_files([file])
    snapshot=editor.snapshot()
    editor.reset();editor.restore_snapshot(snapshot)
    assert len(editor.files())==2 and len(editor.images())==1
    window.send()
    assert [m['kind'] for m in window.store.page()]==['text','file','text','image','file']
    assert not editor.files() and not editor.images()


def test_file_draft_delete_undo_copy_and_remove_images_keeps_files(window,file,image,app):
    editor=window.text_editor
    editor.insert_files([file])
    editor.selectAll();editor.copy()
    assert Path(app.clipboard().mimeData().urls()[0].toLocalFile())==file
    editor.cut()
    assert not editor.files()
    editor.undo()
    assert editor.files()==[file]
    editor.insert_image(image)
    editor.remove_images()
    assert editor.files()==[file] and not editor.images()


def test_missing_source_send_preserves_complete_draft(window,file):
    window.text_editor.insertPlainText('保留文字')
    window.text_editor.insert_files([file])
    file.unlink()
    window.send()
    assert window.store.count()==0
    assert window.text_editor.files()==[file]
    assert window.text_editor.toPlainText()=='保留文字'
    assert '发送失败' in window.status.text() and window.send_button.isEnabled()


def test_directory_is_rejected_and_missing_sent_file_reports_error(window,tmp_path,file,monkeypatch):
    assert not window.text_editor.insert_files([tmp_path])
    assert not window.text_editor.files()
    record=window.store.save_file(file)
    window.reload_latest()
    window.store.file_path(record['filename']).unlink()
    monkeypatch.setattr(QDesktopServices,'openUrl',lambda *args:pytest.fail('Missing file should not be opened'))
    window.open_image(window.history.item(0))
    assert '文件已被移动或删除' in window.status.text()
