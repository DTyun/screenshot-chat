"""Local-only image history. Commit files before publishing a database row."""
from pathlib import Path
from datetime import datetime
import json
import os
import sqlite3
import uuid

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage


def config_root():
    return Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'Pianyu'


def default_root():
    try:
        path = Path(json.loads((config_root() / 'location.json').read_text(encoding='utf-8'))['data_root'])
        if path.is_absolute():
            return path
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return config_root()


class Store:
    def __init__(self, root=None):
        self.root = Path(root) if root else default_root()
        self.images = self.root / 'images'
        self.thumbs = self.root / 'thumbnails'
        self.images.mkdir(parents=True, exist_ok=True)
        self.thumbs.mkdir(exist_ok=True)
        self.db = sqlite3.connect(self.root / 'history.db')
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute("CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY AUTOINCREMENT, filename TEXT UNIQUE, created TEXT NOT NULL, width INTEGER NOT NULL DEFAULT 0, height INTEGER NOT NULL DEFAULT 0, kind TEXT NOT NULL DEFAULT 'image', text TEXT NOT NULL DEFAULT '')")
        self.db.commit()
        columns = {row['name'] for row in self.db.execute('PRAGMA table_info(messages)')}
        if 'kind' not in columns:
            # Transactional migration preserves every old image ID and file reference.
            with self.db:
                self.db.execute('BEGIN IMMEDIATE')
                self.db.execute("CREATE TABLE messages_upgrade (id INTEGER PRIMARY KEY AUTOINCREMENT, filename TEXT UNIQUE, created TEXT NOT NULL, width INTEGER NOT NULL DEFAULT 0, height INTEGER NOT NULL DEFAULT 0, kind TEXT NOT NULL DEFAULT 'image', text TEXT NOT NULL DEFAULT '')")
                self.db.execute('INSERT INTO messages_upgrade(id,filename,created,width,height) SELECT id,filename,created,width,height FROM messages')
                self.db.execute('DROP TABLE messages')
                self.db.execute('ALTER TABLE messages_upgrade RENAME TO messages')
        columns = {row['name'] for row in self.db.execute('PRAGMA table_info(messages)')}
        with self.db:
            self.db.execute('CREATE TABLE IF NOT EXISTS conversations (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL)')
            if not self.db.execute('SELECT 1 FROM conversations LIMIT 1').fetchone():
                self.db.execute("INSERT INTO conversations(name) VALUES('我的图片')")
            if 'conversation_id' not in columns:
                self.db.execute('ALTER TABLE messages ADD COLUMN conversation_id INTEGER NOT NULL DEFAULT 1')
            self.db.execute('CREATE INDEX IF NOT EXISTS messages_conversation ON messages(conversation_id,id)')
        self.recover_deletions()

    def recover_deletions(self):
        for folder in (self.images, self.thumbs):
            for temp in folder.glob('*.deleting'):
                original = temp.with_suffix('.png')
                exists = self.db.execute('SELECT 1 FROM messages WHERE filename=?', (original.name,)).fetchone()
                if exists and not original.exists():
                    temp.rename(original)
                else:
                    temp.unlink(missing_ok=True)

    def save(self, image, text='', conversation_id=1):
        return self.save_composed([(image,text)],conversation_id)[0]

    def save_composed(self, parts, conversation_id=1):
        """Commit one edited draft atomically, including all image files."""
        files, records = [], []
        try:
            with self.db:
                for image,text in parts:
                    filename, width, height = None, 0, 0
                    kind = 'text'
                    if image is not None:
                        if image.isNull():
                            raise ValueError('图片为空，无法发送')
                        filename = datetime.now().strftime('%Y%m%d_%H%M%S_') + uuid.uuid4().hex[:10] + '.png'
                        original, thumb = self.images / filename, self.thumbs / filename
                        files.extend((original,thumb))
                        if not image.save(str(original),'PNG'):
                            raise OSError('图片保存失败，请检查磁盘空间和目录权限')
                        small = image.scaled(680,440,Qt.KeepAspectRatio,Qt.SmoothTransformation)
                        if not small.save(str(thumb),'PNG'):
                            raise OSError('预览图保存失败')
                        width,height,kind = image.width(),image.height(),'image'
                    elif not text.strip():
                        raise ValueError('请输入文字再发送')
                    cur = self.db.execute('INSERT INTO messages(filename,created,width,height,text,conversation_id,kind) VALUES(?,?,?,?,?,?,?)', (filename,datetime.now().isoformat(timespec='seconds'),width,height,text,conversation_id,kind))
                    records.append(dict(self.db.execute('SELECT * FROM messages WHERE id=?',(cur.lastrowid,)).fetchone()))
            return records
        except Exception:
            for path in files:
                path.unlink(missing_ok=True)
            raise

    def save_text(self, text, conversation_id=1):
        if not text.strip():
            raise ValueError('请输入文字再发送')
        with self.db:
            cur = self.db.execute("INSERT INTO messages(created,kind,text,conversation_id) VALUES(?,'text',?,?)", (datetime.now().isoformat(timespec='seconds'), text, conversation_id))
        return dict(self.db.execute('SELECT * FROM messages WHERE id=?', (cur.lastrowid,)).fetchone())

    def search(self, keyword='', kind=None, before=None, limit=40, conversation_id=1):
        escaped = keyword.strip().replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        pattern = '%' + escaped + '%'
        where = ["(text LIKE ? ESCAPE '\\' OR created LIKE ? ESCAPE '\\' OR COALESCE(filename,'') LIKE ? ESCAPE '\\')"]
        where.append('conversation_id=?')
        args = [pattern, pattern, pattern, conversation_id]
        if kind:
            where.append('kind=?')
            args.append(kind)
        if before is not None:
            where.append('id<?')
            args.append(before)
        args.append(limit)
        return [dict(row) for row in self.db.execute('SELECT * FROM messages WHERE ' + ' AND '.join(where) + ' ORDER BY id DESC LIMIT ?', args)]

    def around(self, identifier, conversation_id=1):
        older = self.db.execute('SELECT * FROM messages WHERE id<=? AND conversation_id=? ORDER BY id DESC LIMIT 21', (identifier, conversation_id)).fetchall()
        newer = self.db.execute('SELECT * FROM messages WHERE id>? AND conversation_id=? ORDER BY id LIMIT 20', (identifier, conversation_id)).fetchall()
        return [dict(row) for row in list(reversed(older)) + list(newer)]

    def page_after(self, after, limit=40, conversation_id=1):
        return [dict(row) for row in self.db.execute('SELECT * FROM messages WHERE id>? AND conversation_id=? ORDER BY id LIMIT ?', (after, conversation_id, limit))]

    def has_before(self, identifier, conversation_id=1):
        return self.db.execute('SELECT 1 FROM messages WHERE id<? AND conversation_id=? LIMIT 1', (identifier, conversation_id)).fetchone() is not None

    def has_after(self, identifier, conversation_id=1):
        return self.db.execute('SELECT 1 FROM messages WHERE id>? AND conversation_id=? LIMIT 1', (identifier, conversation_id)).fetchone() is not None

    def page(self, before=None, limit=40, conversation_id=1):
        if before is None:
            rows = self.db.execute('SELECT * FROM messages WHERE conversation_id=? ORDER BY id DESC LIMIT ?', (conversation_id, limit)).fetchall()
        else:
            rows = self.db.execute('SELECT * FROM messages WHERE id < ? AND conversation_id=? ORDER BY id DESC LIMIT ?', (before, conversation_id, limit)).fetchall()
        return [dict(row) for row in reversed(rows)]

    def count(self, conversation_id=1):
        return self.db.execute('SELECT COUNT(*) FROM messages WHERE conversation_id=?', (conversation_id,)).fetchone()[0]

    def conversations(self):
        return [dict(row) for row in self.db.execute('SELECT c.*, COUNT(m.id) AS count FROM conversations c LEFT JOIN messages m ON m.conversation_id=c.id GROUP BY c.id ORDER BY c.id')]

    def create_conversation(self, name):
        name = self.valid_name(name)
        with self.db:
            cur = self.db.execute('INSERT INTO conversations(name) VALUES(?)', (name,))
        return cur.lastrowid

    def rename_conversation(self, identifier, name):
        with self.db:
            self.db.execute('UPDATE conversations SET name=? WHERE id=?', (self.valid_name(name), identifier))

    @staticmethod
    def valid_name(name):
        name = name.strip()
        if not name or len(name) > 40:
            raise ValueError('聊天名称需要 1–40 个字')
        return name

    def delete(self, message):
        self._delete_messages([message])

    def delete_conversation(self, identifier):
        if not self.db.execute('SELECT 1 FROM conversations WHERE id=?',(identifier,)).fetchone():
            raise ValueError('聊天已被删除')
        messages = self.db.execute('SELECT * FROM messages WHERE conversation_id=?',(identifier,)).fetchall()
        self._delete_messages(messages,identifier)

    def _delete_messages(self, messages, conversation_id=None):
        # Stage files by renaming first; failure restores both files and the row.
        staged = []
        try:
            for message in messages:
                for folder in (self.images, self.thumbs):
                    if not message['filename']:
                        continue
                    path = folder / message['filename']
                    if path.exists():
                        temp = path.with_suffix('.deleting')
                        path.rename(temp)
                        staged.append((path, temp))
            with self.db:
                self.db.executemany('DELETE FROM messages WHERE id=?',((message['id'],) for message in messages))
                if conversation_id is not None:
                    self.db.execute('DELETE FROM conversations WHERE id=?',(conversation_id,))
                    if not self.db.execute('SELECT 1 FROM conversations LIMIT 1').fetchone():
                        self.db.execute("INSERT INTO conversations(name) VALUES('我的图片')")
        except Exception:
            for path, temp in reversed(staged):
                temp.rename(path)
            raise
        for _, temp in staged:
            try:
                temp.unlink()
            except OSError:
                pass  # Unreferenced cleanup can be retried without losing history.

    def settings(self):
        try:
            data = json.loads((self.root / 'settings.json').read_text(encoding='utf-8'))
            if not isinstance(data, dict) or not isinstance(data.get('hotkey'), str):
                return {'hotkey': 'Ctrl+Alt+A'}
            return data
        except (OSError, ValueError):
            return {'hotkey': 'Ctrl+Alt+A'}

    def save_settings(self, settings):
        tmp = self.root / 'settings.tmp'
        tmp.write_text(json.dumps(settings, ensure_ascii=False), encoding='utf-8')
        tmp.replace(self.root / 'settings.json')
