"""Read-only viewer for the active application diagnostic log."""
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLabel,QLineEdit,QPlainTextEdit,QPushButton,QApplication
from .app_logging import read_log_tail


class LogViewer(QDialog):
    def __init__(self,parent,path_provider):
        super().__init__(parent)
        self.path_provider = path_provider
        self.setWindowTitle('运行日志 · 截图聊天')
        self.setWindowIcon(parent.windowIcon())
        self.resize(800,520)
        self.setMinimumSize(580,380)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22,20,22,18)
        layout.setSpacing(12)
        title = QLabel('运行日志')
        title.setObjectName('title')
        layout.addWidget(title)
        self.path_field = QLineEdit()
        self.path_field.setReadOnly(True)
        self.path_field.setAccessibleName('当前日志文件')
        layout.addWidget(self.path_field)
        self.editor = QPlainTextEdit()
        self.editor.setObjectName('logContent')
        self.editor.setReadOnly(True)
        self.editor.setFont(QFont('Consolas',10))
        self.editor.setAccessibleName('日志内容，可选择和复制')
        self.editor.setPlaceholderText('暂无日志。运行信息和错误会显示在这里。')
        layout.addWidget(self.editor,1)
        self.status = QLabel()
        self.status.setObjectName('muted')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        actions = QHBoxLayout()
        self.copy_button = QPushButton('复制日志')
        self.copy_button.clicked.connect(self.copy_log)
        actions.addWidget(self.copy_button)
        folder = QPushButton('打开文件夹')
        folder.clicked.connect(self.open_folder)
        actions.addWidget(folder)
        actions.addStretch()
        refresh = QPushButton('刷新')
        refresh.clicked.connect(self.refresh)
        actions.addWidget(refresh)
        close = QPushButton('关闭')
        close.clicked.connect(self.close)
        actions.addWidget(close)
        layout.addLayout(actions)
        self.refresh()

    def refresh(self):
        path = self.path_provider()
        self.path_field.setText(str(path))
        self.path_field.setCursorPosition(0)
        bar = self.editor.verticalScrollBar()
        at_bottom = bar.value()==bar.maximum()
        previous = bar.value()
        try:
            text,truncated = read_log_tail(path)
            self.editor.setPlainText(text)
            self.status.setText('日志较大，仅显示最近 512KB；完整记录位于上方文件。' if truncated else '暂无日志记录。' if not text else '日志只读；可选择部分内容复制，或复制当前显示的全部日志。')
            self.copy_button.setEnabled(bool(text))
        except OSError as exc:
            self.editor.clear()
            self.copy_button.setEnabled(False)
            self.status.setText('读取日志失败：'+str(exc))
        bar.setValue(bar.maximum() if at_bottom else previous)

    def copy_log(self):
        QApplication.clipboard().setText(self.editor.toPlainText())

    def open_folder(self):
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.path_provider().parent))):
            self.status.setText('打开文件夹失败，请复制上方路径后手动打开。')
