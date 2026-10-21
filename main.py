"""Local chat entry point. Public release checks are optional to core operation."""
import sys
import time
from PySide6.QtCore import QTimer
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QSystemTrayIcon
from src.platform_win import SingleInstance, GlobalHotkey
from src.storage import Store
from src.theme import stylesheet
from src.ui import MainWindow
from src.version import APP_VERSION
from src.app_logging import logger,configure_logging,close_logging


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
    configure_logging(store.root)
    logger.info('截图聊天 %s 启动；开机启动模式=%s',APP_VERSION,'--autostart' in sys.argv)
    hotkey = GlobalHotkey(app)
    window = MainWindow(store, hotkey)
    server = QLocalServer()
    QLocalServer.removeServer(server_name)
    if not server.listen(server_name):
        logger.error('单例激活通道不可用：%s',server.errorString())

    def activate():
        while server.hasPendingConnections():
            socket = server.nextPendingConnection()
            socket.disconnectFromServer()
            socket.deleteLater()
        window.restore()

    server.newConnection.connect(activate)

    def error_hook(kind, value, tb):
        logger.error('未处理异常',exc_info=(kind,value,tb))
        window.notify('操作失败，详细信息已写入本地 app.log')

    sys.excepthook = error_hook
    if '--autostart' not in sys.argv or not QSystemTrayIcon.isSystemTrayAvailable():
        window.show()
    QTimer.singleShot(5000, window.update_checker.check)
    code = app.exec()
    logger.info('应用退出')
    server.close()
    hotkey.close()
    window.store.db.close()
    instance.close()
    close_logging()
    return code


if __name__ == '__main__':
    sys.exit(main())
