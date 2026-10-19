"""Read-only, in-process image viewing with a single native close button."""
from pathlib import Path
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImageReader, QPixmap, QPainter, QColor
from PySide6.QtWidgets import QDialog, QVBoxLayout, QGraphicsView, QGraphicsScene, QFrame


class ImageView(QGraphicsView):
    def __init__(self, parent):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.setFrameShape(QFrame.NoFrame)
        self.setBackgroundBrush(QColor('#F5F5F5'))
        self.setRenderHint(QPainter.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setAccessibleName('图片阅读区')
        self.setToolTip('滚轮缩放，拖动查看，Esc 关闭')
        self.manual_zoom = False

    def fit_image(self):
        if not self.scene().sceneRect().isEmpty():
            self.resetTransform()
            self.fitInView(self.scene().sceneRect(),Qt.KeepAspectRatio)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self.manual_zoom:
            self.fit_image()

    def wheelEvent(self, event):
        if not event.angleDelta().y():
            event.ignore()
            return
        factor = 1.2 if event.angleDelta().y()>0 else 1/1.2
        scale = self.transform().m11()*factor
        if .01 <= scale <= 32:
            self.scale(factor,factor)
            self.manual_zoom = True
        event.accept()


class ImageViewer(QDialog):
    def __init__(self, path, parent=None):
        super().__init__(parent,Qt.Dialog | Qt.CustomizeWindowHint | Qt.WindowTitleHint | Qt.WindowCloseButtonHint)
        self.setWindowTitle('图片阅读 · 截图聊天')
        if parent:
            self.setWindowIcon(parent.windowIcon())
        self.setMinimumSize(360,280)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0,0,0,0)
        self.view = ImageView(self)
        layout.addWidget(self.view)
        self.load_image(path)

    def load_image(self, path):
        path = Path(path)
        reader = QImageReader(str(path))
        reader.setAutoTransform(True)
        image = reader.read()
        if image.isNull():
            raise ValueError('图片读取失败：文件可能已损坏或无法访问')
        self.path = path
        self.pixmap = QPixmap.fromImage(image)
        self.view.scene().clear()
        self.view.scene().addPixmap(self.pixmap)
        self.view.scene().setSceneRect(0,0,image.width(),image.height())
        self.view.manual_zoom = False
        self.setWindowTitle(path.name+' · 图片阅读')
        screen = self.screen().availableGeometry()
        self.resize(min(max(560,image.width()),round(screen.width()*.85)),min(max(420,image.height()+40),round(screen.height()*.85)))
        self.view.fit_image()
        QTimer.singleShot(0,self.view.fit_image)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0,self.view.fit_image)
