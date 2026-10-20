"""Stage a complete local store before switching the user's data directory."""
import json
import shutil
import sqlite3
import uuid
from contextlib import closing
from pathlib import Path
from PySide6.QtCore import QThread
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QProgressBar
from .storage import Store, config_root


def validate_destination(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if source == destination:
        return destination
    if source.is_relative_to(destination) or destination.is_relative_to(source):
        raise ValueError('新旧文件夹不能相互包含，请选择独立的文件夹')
    if destination.exists() and not destination.is_dir():
        raise ValueError('请选择文件夹')
    return destination


def prepare_destination(source, destination, migrate):
    source = Path(source).resolve()
    target = validate_destination(source, destination)
    if source == target:
        return target
    if not migrate:
        # Allows selecting a previously used cache without overwriting any files.
        store = Store(target)
        store.db.close()
        return target
    if target.exists() and any(target.iterdir()):
        raise ValueError('迁移目标文件夹需要为空，以免覆盖现有文件；也可以取消勾选迁移')
    target.parent.mkdir(parents=True, exist_ok=True)
    staged = target.parent / ('.screenshot-chat-move-' + uuid.uuid4().hex)
    staged.mkdir()
    try:
        for name in ('images', 'thumbnails','files'):
            if (source / name).exists():
                shutil.copytree(source / name, staged / name)
        if (source / 'settings.json').exists():
            shutil.copy2(source / 'settings.json', staged / 'settings.json')
        with closing(sqlite3.connect(source / 'history.db')) as old, closing(sqlite3.connect(staged / 'history.db')) as new:
            old.backup(new)
            new.commit()
        # Validate migrated history and every referenced original before switching.
        check = Store(staged)
        try:
            if check.db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise OSError('聊天记录校验失败')
            for row in check.db.execute("SELECT filename,kind FROM messages WHERE kind IN ('image','file')"):
                name = row['filename']
                folder = 'files' if row['kind']=='file' else 'images'
                if (source / folder / name).exists() and not (staged / folder / name).exists():
                    raise OSError('附件迁移校验失败：' + name)
        finally:
            check.db.close()
        if target.exists():
            target.rmdir()  # Only the verified empty selected folder, never recursive.
        staged.rename(target)
        return target
    except Exception:
        # Staged path is created in this function, with a fixed prefix and UUID.
        if staged.exists() and not staged.is_symlink() and staged.resolve().parent == target.parent.resolve() and staged.resolve().name.startswith('.screenshot-chat-move-'):
            shutil.rmtree(staged)
        raise


def write_location(destination):
    config = config_root()
    config.mkdir(parents=True, exist_ok=True)
    temporary = config / 'location.tmp'
    temporary.write_text(json.dumps({'data_root': str(Path(destination).resolve())}, ensure_ascii=False), encoding='utf-8')
    temporary.replace(config / 'location.json')


class MoveWorker(QThread):
    def __init__(self, source, destination, migrate, parent):
        super().__init__(parent)
        self.source, self.destination, self.migrate = source, destination, migrate
        self.error = None
        self.result = None

    def run(self):
        try:
            self.result = prepare_destination(self.source, self.destination, self.migrate)
        except Exception as exc:
            self.error = str(exc)


class MoveDialog(QDialog):
    def __init__(self, parent, worker):
        super().__init__(parent)
        self.setWindowTitle('更改缓存文件夹')
        self.setFixedWidth(400)
        body = QVBoxLayout(self)
        body.setContentsMargins(24,24,24,24)
        body.addWidget(QLabel('正在迁移并校验聊天和图片，请稍候…' if worker.migrate else '正在切换文件夹，请稍候…'))
        progress = QProgressBar()
        progress.setRange(0,0)
        body.addWidget(progress)
        worker.finished.connect(self.accept)

    def reject(self):
        pass  # A directory switch must finish or roll back as one operation.

    def closeEvent(self, event):
        event.ignore()
