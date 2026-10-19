"""Pianyu Windows entry point. No network or accounts required."""
import logging
import sys
import time
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QSystemTrayIcon
from src.platform_win import SingleInstance, GlobalHotkey
from src.storage import Store
from src.theme import stylesheet
from src.ui import MainWindow
from src.version import APP_VERSION


def main():
    app = QApplication(sys.argv)
    app.setApplicationName('截图聊天')
    app.setApplicationVersion(APP_VERSION)
    app.setQuitOnLastWindowClosed(False)
    app.setStyle('Fusion')
    app.setStyleSheet(stylesheet())
    instance = SingleInstance()
    server_name = 'PianyuScreenshot_1'
    if not instance.is_primary:
        socket = QLocalSocket()
        for _ in range(12):
            socket.connectToServer(server_name)
            if socket.waitForConnected(250):
                socket.write(b'show')
                socket.waitForBytesWritten(500)
                socket.disconnectFromServer()
                break
            socket.abort()
            time.sleep(.1)
        instance.close()
        return 0
    store = Store()
    logging.basicConfig(filename=store.root / 'app.log', level=logging.ERROR)
    hotkey = GlobalHotkey(app)
    window = MainWindow(store, hotkey)
    server = QLocalServer()
    QLocalServer.removeServer(server_name)
    if not server.listen(server_name):
        logging.error('Activation pipe unavailable: %s', server.errorString())

    def activate():
        while server.hasPendingConnections():
            socket = server.nextPendingConnection()
            socket.disconnectFromServer()
            socket.deleteLater()
        window.restore()

    server.newConnection.connect(activate)

    def error_hook(kind, value, tb):
        logging.error('Unhandled exception', exc_info=(kind, value, tb))
        window.notify('操作失败，详细信息已写入本地 app.log')

    sys.excepthook = error_hook
    if '--autostart' not in sys.argv or not QSystemTrayIcon.isSystemTrayAvailable():
        window.show()
    code = app.exec()
    server.close()
    hotkey.close()
    window.store.db.close()
    instance.close()
    return code


if __name__ == '__main__':
    sys.exit(main())
