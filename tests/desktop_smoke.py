"""Exercise the native event loop, frozen monitor overlays and tray lifecycle."""
import ctypes
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QTimer, Qt, QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QSystemTrayIcon
from src.platform_win import GlobalHotkey
from src.storage import Store
from src.ui import MainWindow
from src.theme import stylesheet

app = QApplication([])
app.setQuitOnLastWindowClosed(False)
app.setStyleSheet(stylesheet())
root = Path(__file__).resolve().parents[1]
store = Store(root / 'artifacts' / 'test-data' / 'desktop')
for message in store.page(limit=1000):
    store.delete(message)
hotkey = GlobalHotkey(app)
w = MainWindow(store, hotkey)
w.show()
failures = []

def check(callback):
    def run():
        try:
            callback()
        except Exception as exc:
            failures.append(repr(exc))
            print('FAIL:', repr(exc), flush=True)
            cleanup()
    return run

def trigger():
    # Inject WM_HOTKEY into this test's own thread queue, through the OS event filter.
    ctypes.windll.user32.PostThreadMessageW(ctypes.windll.kernel32.GetCurrentThreadId(), 0x0312, hotkey.identifier, 0)

def select():
    assert w.capture_session and w.capture_session.overlays
    overlay = w.capture_session.overlays[0]
    QTest.mousePress(overlay, Qt.LeftButton, pos=QPoint(100,100))
    QTest.mouseMove(overlay, QPoint(419,299))
    QTest.mouseRelease(overlay, Qt.LeftButton, pos=QPoint(419,299))
    assert overlay.locked and overlay.toolbar.isVisible()
    overlay.finish()
    assert w.pending is not None
    assert w.isVisible()
    assert not QApplication.clipboard().image().isNull()
    assert len(w.text_editor.images()) == 1
    w.send()
    assert store.count() == 1
    assert w.pending is None
    w.hide_to_tray()
    if QSystemTrayIcon.isSystemTrayAvailable():
        assert not w.isVisible()
    w.restore()
    assert w.isVisible()
    w.grab().save(str(root / 'artifacts' / 'desktop-smoke.png'))
    w.capture()

def cancel():
    assert w.capture_session
    w.capture_session.cancel()
    assert w.isVisible() and w.pending is None
    print('PASS: native hotkey event, desktop region capture, clipboard, send/save, tray restore, cancel', flush=True)
    cleanup()

def cleanup():
    if w.capture_session:
        w.capture_session.clear()
    w.tray.hide()
    hotkey.close()
    app.quit()

QTimer.singleShot(300, check(trigger))
QTimer.singleShot(1000, check(select))
QTimer.singleShot(1800, check(cancel))
QTimer.singleShot(10000, cleanup)
app.exec()
sys.exit(1 if failures else 0)
