"""Local file attachment display and background atomic storage."""
from PySide6.QtCore import QThread,Qt,QRectF
from PySide6.QtGui import QImage,QPainter,QColor,QFont
from PySide6.QtWidgets import QDialog,QVBoxLayout,QLabel,QProgressBar
from .storage import Store


def human_size(size):
    value=float(size)
    for unit in ('B','KB','MB','GB','TB'):
        if value<1024 or unit=='TB':
            return f'{int(value)} B' if unit=='B' else f'{value:.1f} {unit}'
        value/=1024


def file_preview(path):
    image=QImage(240,64,QImage.Format_ARGB32)
    image.fill(QColor('#F0F3F2'))
    painter=QPainter(image)
    painter.setPen(QColor('#00A966'))
    painter.drawRoundedRect(QRectF(10,12,28,38),3,3)
    painter.drawLine(16,24,32,24)
    painter.drawLine(16,31,32,31)
    painter.drawLine(16,38,27,38)
    font=QFont('Microsoft YaHei UI');font.setPixelSize(13)
    painter.setFont(font)
    painter.setPen(QColor('#242424'))
    painter.drawText(50,26,painter.fontMetrics().elidedText(path.name,Qt.ElideMiddle,180))
    painter.setPen(QColor('#92929C'))
    painter.drawText(50,47,human_size(path.stat().st_size))
    painter.end()
    return image


class FileSendWorker(QThread):
    def __init__(self,root,parts,chat_id,parent):
        super().__init__(parent)
        self.root,self.parts,self.chat_id=root,parts,chat_id
        self.error=None

    def run(self):
        store=None
        try:
            store=Store(self.root)
            store.save_composed(self.parts,self.chat_id)
        except Exception as exc:
            self.error=str(exc)
        finally:
            if store:store.db.close()


class FileSendDialog(QDialog):
    def __init__(self,worker,parent):
        super().__init__(parent)
        self.setWindowTitle('保存文件')
        self.setFixedWidth(360)
        layout=QVBoxLayout(self)
        layout.setContentsMargins(24,24,24,24)
        layout.addWidget(QLabel('正在将文件复制到本地聊天，请稍候…'))
        progress=QProgressBar();progress.setRange(0,0)
        layout.addWidget(progress)
        worker.finished.connect(self.accept)

    def reject(self):
        pass

    def closeEvent(self,event):
        event.ignore()
