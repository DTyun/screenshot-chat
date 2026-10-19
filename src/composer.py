"""One editable document for draft text and original-resolution inline images."""
import uuid
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QImage, QTextCursor, QTextDocument, QTextImageFormat, QKeySequence
from PySide6.QtWidgets import QTextEdit, QApplication, QMenu


class ChatEditor(QTextEdit):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.composing = False
        self.resources = {}
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
        if source.hasImage():
            image = QImage(source.imageData())
            if not image.isNull():
                self.insert_image(image)
                return
        self.insertPlainText(source.text())

    def canInsertFromMimeData(self, source):
        return source.hasImage() or source.hasText()

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

    def toPlainText(self):
        return super().toPlainText().replace('\ufffc','')

    def remove_images(self):
        positions = []
        block = self.document().begin()
        while block.isValid():
            it = block.begin()
            while not it.atEnd():
                fragment = it.fragment()
                if fragment.isValid() and fragment.charFormat().isImageFormat():
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
        return (html, {name:image for name,image in self.resources.items() if name in html}, self.textCursor().position())

    def restore_snapshot(self, draft):
        self.resources = dict(draft[1]) if draft else {}
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

    def selected_image(self):
        cursor = self.textCursor()
        if cursor.hasSelection() and cursor.selectedText() == '\ufffc':
            check = QTextCursor(self.document())
            check.setPosition(cursor.selectionStart())
            check.movePosition(QTextCursor.NextCharacter,QTextCursor.KeepAnchor)
            name = check.charFormat().toImageFormat().name()
            if name in self.resources:
                return self.resources[name]
        return None

    def copy(self):
        image = self.selected_image()
        if image is not None:
            QApplication.clipboard().setImage(image.copy())
        else:
            super().copy()

    def cut(self):
        if self.selected_image() is not None:
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
