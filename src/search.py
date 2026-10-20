"""Local chat search with bounded result pages and location in original history."""
from datetime import datetime
from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLineEdit,
    QLabel, QPushButton, QListWidget, QListWidgetItem, QWidget, QTabBar)


class SearchDialog(QDialog):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.setWindowTitle('与“' + window.chat_title.text() + '”的聊天记录')
        self.resize(570,680)
        self.setMinimumSize(460,400)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24,20,24,18)
        layout.setSpacing(14)
        self.query = QLineEdit()
        self.query.setPlaceholderText('搜索聊天内容')
        self.query.setAccessibleName('搜索聊天内容')
        self.query.setClearButtonEnabled(True)
        layout.addWidget(self.query)
        self.tabs = QTabBar()
        for title in ('全部', '文字', '图片','文件'):
            self.tabs.addTab(title)
        self.tabs.setExpanding(False)
        layout.addWidget(self.tabs)
        self.feedback = QLabel()
        self.feedback.setObjectName('muted')
        layout.addWidget(self.feedback)
        self.results = QListWidget()
        self.results.setAccessibleName('聊天搜索结果')
        self.results.setSpacing(8)
        self.results.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.results.itemDoubleClicked.connect(self.locate_item)
        layout.addWidget(self.results, 1)
        self.more = QPushButton('加载更多记录')
        self.more.setCursor(Qt.PointingHandCursor)
        self.more.clicked.connect(self.load_more)
        layout.addWidget(self.more)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(300)
        self.timer.timeout.connect(self.reset)
        self.query.textChanged.connect(self.schedule)
        self.query.returnPressed.connect(self.reset)
        self.tabs.currentChanged.connect(self.reset)
        self.reset()
        self.query.setFocus()

    def schedule(self, text):
        self.more.setEnabled(False)
        self.timer.start(300 if text else 0)

    def reset(self):
        self.timer.stop()
        self.results.clear()
        self.load_more()

    def load_more(self):
        try:
            last = self.results.item(self.results.count()-1)
            before = last.data(Qt.UserRole)['id'] if last else None
            kind = (None, 'text', 'image','file')[self.tabs.currentIndex()]
            messages = self.window.store.search(self.query.text(), kind, before, limit=41, conversation_id=self.window.chat_id)
            self.more.setVisible(len(messages) > 40)
            self.more.setEnabled(True)
            for message in messages[:40]:
                self.add_result(message)
            self.feedback.setText(f'已显示 {self.results.count()} 条记录' if self.results.count() else '没有找到相关记录，试试其他关键词。')
        except Exception as exc:
            self.feedback.setText('查找失败：' + str(exc))
            self.more.setVisible(False)

    def add_result(self, message):
        item = QListWidgetItem()
        item.setData(Qt.UserRole, message)
        item.setData(Qt.AccessibleTextRole, message['original_name'] or message['text'] or '图片')
        panel = QWidget()
        body = QVBoxLayout(panel)
        body.setContentsMargins(4,10,4,12)
        top = QHBoxLayout()
        sender = QLabel('我')
        sender.setObjectName('muted')
        top.addWidget(sender)
        top.addStretch()
        when = QLabel(datetime.fromisoformat(message['created']).strftime('%Y年%m月%d日 %H:%M'))
        when.setObjectName('muted')
        top.addWidget(when)
        body.addLayout(top)
        if message['kind'] == 'image':
            preview = QLabel()
            pix = QPixmap(str(self.window.store.thumbs / message['filename']))
            if pix.isNull():
                preview.setText('图片文件已被移动或删除')
            else:
                preview.setPixmap(pix.scaled(180,110,Qt.KeepAspectRatio,Qt.SmoothTransformation))
            body.addWidget(preview)
        if message['kind']=='file':
            from .attachments import human_size
            filename=QLabel(message['original_name']+' · '+human_size(message['file_size']))
            filename.setTextFormat(Qt.PlainText)
            filename.setWordWrap(True)
            body.addWidget(filename)
        if message['text']:
            text = QLabel(message['text'][:400] + ('…' if len(message['text']) > 400 else ''))
            text.setTextFormat(Qt.PlainText)
            text.setWordWrap(True)
            text.setTextInteractionFlags(Qt.TextSelectableByMouse)
            text.setMaximumHeight(100)
            body.addWidget(text)
        location = QPushButton('定位到聊天位置')
        location.setObjectName('searchLink')
        location.setCursor(Qt.PointingHandCursor)
        location.clicked.connect(lambda checked=False, identifier=message['id']: self.locate(identifier))
        body.addWidget(location, alignment=Qt.AlignRight)
        panel.setFixedWidth(max(350, self.results.viewport().width()-28))
        item.setSizeHint(QSize(panel.width(), panel.sizeHint().height()))
        self.results.addItem(item)
        self.results.setItemWidget(item, panel)
        QTimer.singleShot(0, self.fit_results)

    def fit_results(self):
        width = max(100, self.results.viewport().width()-18)
        for i in range(self.results.count()):
            item = self.results.item(i)
            panel = self.results.itemWidget(item)
            if panel:
                panel.setFixedWidth(width)
                height = panel.layout().heightForWidth(width)
                item.setSizeHint(QSize(width, height if height > 0 else panel.sizeHint().height()))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, self.fit_results)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self.fit_results)

    def locate_item(self, item):
        self.locate(item.data(Qt.UserRole)['id'])

    def locate(self, identifier):
        self.accept()
        self.window.locate_message(identifier)
