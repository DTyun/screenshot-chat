"""Render real Qt widgets and exercise desktop capture without changing user history."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import Qt, QTimer, QPoint
from PySide6.QtGui import QImage, QPainter, QColor, QFont
from PySide6.QtTest import QTest
from src.capture import SelectionOverlay
from PySide6.QtWidgets import QApplication
from src.storage import Store
from src.ui import MainWindow, SettingsDialog
from src.search import SearchDialog
from src.theme import stylesheet
from PySide6.QtCore import QObject, Signal

class Events(QObject):
    triggered = Signal()

class FakeHotkey:
    def __init__(self):
        self.events = Events()
    def set(self, text):
        pass
    def close(self):
        pass

app = QApplication([])
app.setStyle('Fusion')
app.setStyleSheet(stylesheet())
root = Path(__file__).resolve().parents[1]
store = Store(root / 'artifacts' / 'test-data' / 'preview')
for message in store.page(limit=1000):
    store.delete(message)
image = QImage(str(root / 'assets' / 'scissors.png'))
store.save(image)
sample = QImage(820, 400, QImage.Format_RGB32)
sample.fill(QColor('#EFF4EF'))
p = QPainter(sample)
p.setPen(QColor('#245643'))
p.setFont(QFont('Microsoft YaHei UI', 29))
p.drawText(48, 110, '让灵感有个落脚的地方。')
p.setFont(QFont('Microsoft YaHei UI', 14))
p.drawText(50, 170, '截图 · 粘贴 · 发送')
p.setPen(QColor('#6E8278'))
p.drawText(50, 320, '截图聊天  /  我的图片')
p.end()
store.save(sample)
store.save_text('今天的截图整理好了，放在这里随时查找。')
store.save_text('文字和图片都可以发送，聊天内容会保存在本地。')
if not any(chat['name']=='工作资料' for chat in store.conversations()):
    store.create_conversation('工作资料')
w = MainWindow(store, FakeHotkey())
w.set_pending(sample)
w.text_editor.insertPlainText('  图片旁边可以直接写字。')
cursor = w.text_editor.textCursor()
cursor.insertBlock()
w.text_editor.setTextCursor(cursor)
w.text_editor.insertPlainText('整个输入区都能编辑，也能选中图片删除或替换。')
w.show()

def render():
    w.grab().save(str(root / 'artifacts' / 'window-preview.png'))
    selected = w.history.item(1)
    w.history.setCurrentItem(selected)
    w.history.setFocus()
    w.history.scrollToItem(selected)
    app.processEvents()
    w.grab().save(str(root / 'artifacts' / 'selected-image-preview.png'))
    w.open_image(selected)
    app.processEvents()
    w.image_viewer.grab().save(str(root / 'artifacts' / 'viewer-preview.png'))
    w.image_viewer.close()
    overlay = SelectionOverlay(app.primaryScreen(),w.grab())
    overlay.resize(w.size())
    overlay.show()
    QTest.mousePress(overlay,Qt.LeftButton,pos=QPoint(320,90))
    QTest.mouseRelease(overlay,Qt.LeftButton,pos=QPoint(950,440))
    QTest.mousePress(overlay,Qt.LeftButton,pos=QPoint(590,200))
    QTest.mouseRelease(overlay,Qt.LeftButton,pos=QPoint(920,280))
    overlay.set_tool('arrow')
    overlay.set_color('#2C7BE5')
    QTest.mousePress(overlay,Qt.LeftButton,pos=QPoint(500,360))
    QTest.mouseRelease(overlay,Qt.LeftButton,pos=QPoint(700,250))
    app.processEvents()
    overlay.grab().save(str(root / 'artifacts' / 'annotation-preview.png'))
    overlay.close()
    w.resize(760,560)
    app.processEvents()
    w.grab().save(str(root / 'artifacts' / 'window-narrow.png'))
    dialog = SettingsDialog(w)
    dialog.show()
    app.processEvents()
    dialog.grab().save(str(root / 'artifacts' / 'settings-preview.png'))
    dialog.close()
    search = SearchDialog(w)
    search.query.setText('整理')
    search.reset()
    search.show()
    app.processEvents()
    search.grab().save(str(root / 'artifacts' / 'search-preview.png'))
    search.close()
    screen = app.primaryScreen().grabWindow(0)
    assert not screen.isNull(), 'Native screen grab failed'
    print(f'Qt window rendered; desktop capture: {screen.width()}x{screen.height()}')
    w.tray.hide()
    app.quit()

QTimer.singleShot(600, render)
app.exec()
