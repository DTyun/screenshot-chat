"""One editable document for draft text and original-resolution inline images."""
import uuid
from pathlib import Path
from PySide6.QtCore import Qt, QUrl,QMimeData
from PySide6.QtGui import QImage, QTextCursor, QTextDocument, QTextImageFormat, QKeySequence
from PySide6.QtWidgets import QTextEdit, QApplication, QMenu
from .attachments import file_preview


class ChatEditor(QTextEdit):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.composing = False
        self.resources = {}
        self.file_resources = {}
        self.setAcceptRichText(False)
        self.setToolTip('Enter 发送 · Shift+Enter 换行；图片可选中、删除和替换')
        self.document().setDocumentMargin(5)

    def inputMethodEvent(self, event):
        self.composing = bool(event.preeditString())
        super().inputMethodEvent(event)

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.Copy):
            self.copy()
            return
        if event.matches(QKeySequence.Cut):
            self.cut()
            return
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and not (event.modifiers() & Qt.ShiftModifier) and not self.composing:
            self.window.send()
            event.accept()
            return
        super().keyPressEvent(event)

    def insertFromMimeData(self, source):
        paths=[Path(url.toLocalFile()) for url in source.urls() if url.isLocalFile()]
        if paths:
            self.insert_files(paths)
            return
        if source.hasImage():
            image = QImage(source.imageData())
            if not image.isNull():
                self.insert_image(image)
                return
        self.insertPlainText(source.text())

    def canInsertFromMimeData(self, source):
        return source.hasImage() or source.hasText() or any(url.isLocalFile() for url in source.urls())

    def insert_files(self,paths):
        try:
            paths=[Path(path).resolve(strict=True) for path in paths]
            if any(not path.is_file() for path in paths):
                raise ValueError('仅支持文件，不支持文件夹')
            previews=[file_preview(path) for path in paths]
        except (OSError,ValueError) as exc:
            self.window.notify('添加文件失败：'+str(exc))
            return False
        cursor=self.textCursor()
        cursor.beginEditBlock()
        for path,preview in zip(paths,previews):
            name='draft-file://'+uuid.uuid4().hex
            self.file_resources[name]=path
            self.resources[name]=preview
            self.document().addResource(QTextDocument.ImageResource,QUrl(name),preview)
            fmt=QTextImageFormat();fmt.setName(name);fmt.setWidth(240);fmt.setHeight(64)
            cursor.insertImage(fmt)
        cursor.endEditBlock()
        self.setTextCursor(cursor)
        self.ensureCursorVisible()
        return bool(paths)

    def dragEnterEvent(self,event):
        if any(url.isLocalFile() for url in event.mimeData().urls()):
            event.setDropAction(Qt.CopyAction)
            event.accept()
        else:super().dragEnterEvent(event)

    def dragMoveEvent(self,event):
        if any(url.isLocalFile() for url in event.mimeData().urls()):
            event.setDropAction(Qt.CopyAction)
            event.accept()
        else:super().dragMoveEvent(event)

    def dropEvent(self,event):
        paths=[Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
        if paths:
            self.setTextCursor(self.cursorForPosition(event.position().toPoint()))
            if self.insert_files(paths):
                event.setDropAction(Qt.CopyAction)
                event.accept()
            else:event.ignore()
        else:super().dropEvent(event)

    def insert_image(self, image):
        if image.isNull():
            return
        name = 'draft-image://' + uuid.uuid4().hex
        self.resources[name] = image.copy()
        self.document().addResource(QTextDocument.ImageResource, QUrl(name), image.copy())
        preview = image.size().scaled(160,110,Qt.KeepAspectRatio)
        fmt = QTextImageFormat()
        fmt.setName(name)
        fmt.setWidth(preview.width())
        fmt.setHeight(preview.height())
        cursor = self.textCursor()
        cursor.insertImage(fmt)
        self.setTextCursor(cursor)
        self.ensureCursorVisible()

    def elements(self):
        parts = []
        block = self.document().begin()
        while block.isValid():
            it = block.begin()
            while not it.atEnd():
                fragment = it.fragment()
                if fragment.isValid():
                    fmt = fragment.charFormat()
                    if fmt.isImageFormat():
                        name = fmt.toImageFormat().name()
                        if name in self.file_resources:
                            parts.append(('file',self.file_resources[name]))
                            it += 1
                            continue
                        image = self.resources.get(name)
                        if image is not None:
                            parts.append(('image', image))
                    else:
                        parts.append(('text', fragment.text()))
                it += 1
            block = block.next()
            if block.isValid():
                parts.append(('text', '\n'))
        return parts

    def images(self):
        return [value for kind,value in self.elements() if kind=='image']

    def files(self):
        return [value for kind,value in self.elements() if kind=='file']

    def toPlainText(self):
        return super().toPlainText().replace('\ufffc','')

    def remove_images(self):
        positions = []
        block = self.document().begin()
        while block.isValid():
            it = block.begin()
            while not it.atEnd():
                fragment = it.fragment()
                if fragment.isValid() and fragment.charFormat().isImageFormat() and fragment.charFormat().toImageFormat().name() not in self.file_resources:
                    positions.append((fragment.position(), fragment.length()))
                it += 1
            block = block.next()
        cursor = self.textCursor()
        cursor.beginEditBlock()
        for position,length in reversed(positions):
            cursor.setPosition(position)
            cursor.setPosition(position+length,QTextCursor.KeepAnchor)
            cursor.removeSelectedText()
        cursor.endEditBlock()

    def snapshot(self):
        html = self.toHtml()
        return (html, {name:image for name,image in self.resources.items() if name in html}, self.textCursor().position(),{name:path for name,path in self.file_resources.items() if name in html})

    def restore_snapshot(self, draft):
        self.resources = dict(draft[1]) if draft else {}
        self.file_resources=dict(draft[3]) if draft and len(draft)>3 else {}
        self.clear()
        if not draft:
            return
        for name,image in self.resources.items():
            self.document().addResource(QTextDocument.ImageResource,QUrl(name),image)
        self.setHtml(draft[0])
        cursor = self.textCursor()
        cursor.setPosition(min(draft[2],self.document().characterCount()-1))
        self.setTextCursor(cursor)

    def reset(self):
        self.clear()
        self.resources.clear()
        self.file_resources.clear()

    def selected_image(self):
        cursor = self.textCursor()
        if cursor.hasSelection() and cursor.selectedText() == '\ufffc':
            check = QTextCursor(self.document())
            check.setPosition(cursor.selectionStart())
            check.movePosition(QTextCursor.NextCharacter,QTextCursor.KeepAnchor)
            name = check.charFormat().toImageFormat().name()
            if name in self.resources and name not in self.file_resources:
                return self.resources[name]
        return None

    def selected_file(self):
        cursor=self.textCursor()
        if cursor.hasSelection() and cursor.selectedText()=='\ufffc':
            check=QTextCursor(self.document())
            check.setPosition(cursor.selectionStart())
            check.movePosition(QTextCursor.NextCharacter,QTextCursor.KeepAnchor)
            return self.file_resources.get(check.charFormat().toImageFormat().name())

    def copy(self):
        path=self.selected_file()
        if path is not None:
            mime=QMimeData();mime.setUrls([QUrl.fromLocalFile(str(path))])
            QApplication.clipboard().setMimeData(mime)
            return
        image = self.selected_image()
        if image is not None:
            QApplication.clipboard().setImage(image.copy())
        else:
            super().copy()

    def cut(self):
        if self.selected_image() is not None or self.selected_file() is not None:
            self.copy()
            self.textCursor().removeSelectedText()
        else:
            super().cut()

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.addAction('撤销',self.undo).setEnabled(self.document().isUndoAvailable())
        menu.addAction('重做',self.redo).setEnabled(self.document().isRedoAvailable())
        menu.addSeparator()
        menu.addAction('剪切',self.cut).setEnabled(self.textCursor().hasSelection())
        menu.addAction('复制',self.copy).setEnabled(self.textCursor().hasSelection())
        menu.addAction('粘贴',self.paste).setEnabled(self.canPaste())
        menu.addSeparator()
        menu.addAction('全选',self.selectAll)
        menu.exec(event.globalPos())
