import math
from datetime import datetime
from PySide6.QtCore import Qt, QRect, QPoint, Signal, QObject, QStandardPaths
from PySide6.QtGui import QColor, QPainter, QPen, QCursor, QFont
from PySide6.QtWidgets import QApplication, QWidget, QFrame, QHBoxLayout, QToolButton, QFileDialog, QLineEdit


class SelectionOverlay(QWidget):
    selected = Signal(object)
    cancelled = Signal()

    def __init__(self, screen, pixmap):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.snapshot = pixmap
        self.setGeometry(screen.geometry())
        self.setCursor(Qt.CrossCursor)
        self.setMouseTracking(True)
        self.start = None
        self.end = QPoint()
        self.setFocusPolicy(Qt.StrongFocus)
        self.locked = False
        self.edited = None
        self.preview = None
        self.undo_stack = []
        self.tool = 'rect'
        self.color = QColor('#EE4141')
        self.stroke_width = 3
        self.draw_points = []
        self.text_field = None
        self.notice = ''
        self.toolbar = self.make_toolbar()
        self.toolbar.hide()

    def make_toolbar(self):
        bar = QFrame(self)
        bar.setObjectName('captureToolbar')
        bar.setStyleSheet('QFrame#captureToolbar {background:#FAFAFA;border:1px solid #DDDDDD;border-radius:8px;} QToolButton {background:transparent;color:#555555;border:1px solid transparent;border-radius:4px;font-family:"Segoe UI Symbol";font-size:19px;} QToolButton:hover {background:#EAEAEA;} QToolButton:checked {background:#DEF3E7;border-color:#07C160;} QToolButton:disabled {color:#BDBDBD;}')
        row = QHBoxLayout(bar)
        row.setContentsMargins(8,6,8,6)
        row.setSpacing(3)
        self.tool_buttons = {}
        for key,glyph,title in [('rect','□','矩形'),('ellipse','○','圆形'),('arrow','↗','箭头'),('pen','✎','画笔'),('text','T','文字'),('mosaic','▦','马赛克')]:
            b = self.tool_button(row,glyph,title,lambda checked=False,k=key:self.set_tool(k))
            b.setCheckable(True)
            b.setChecked(key == self.tool)
            self.tool_buttons[key] = b
        row.addSpacing(5)
        for value in ('#EE4141','#07C160','#2C7BE5','#FFC83D'):
            b = self.tool_button(row,'','选择标注颜色 '+value,lambda checked=False,c=value:self.set_color(c))
            b.setFixedSize(20,24)
            b.setStyleSheet(f'QToolButton {{background:{value};border:2px solid white;border-radius:6px;}} QToolButton:focus {{border-color:#444444;}}')
        self.width_button = self.tool_button(row,'3','线条粗细，点击切换',self.cycle_width)
        row.addSpacing(5)
        self.undo_button = self.tool_button(row,'↶','撤销 Ctrl+Z',self.undo)
        self.undo_button.setEnabled(False)
        self.tool_button(row,'↓','保存图片 Ctrl+S',self.save_image)
        cancel = self.tool_button(row,'×','取消 Esc',self.cancelled.emit)
        cancel.setStyleSheet('color:#ED4141;font-size:24px;')
        done = self.tool_button(row,'✓','完成并放入聊天输入框 Enter',self.finish)
        done.setStyleSheet('color:#07B45C;font-size:24px;')
        bar.adjustSize()
        return bar

    def tool_button(self,row,text,title,callback):
        b = QToolButton(self.toolbar if hasattr(self,'toolbar') else self)
        b.setText(text)
        b.setToolTip(title)
        b.setAccessibleName(title)
        b.setCursor(Qt.PointingHandCursor)
        b.setFixedSize(32,32)
        b.clicked.connect(callback)
        row.addWidget(b)
        return b

    def set_tool(self, tool):
        self.commit_text()
        self.tool = tool
        for key,b in self.tool_buttons.items():
            b.setChecked(key == tool)
        self.setFocus()

    def set_color(self, color):
        self.commit_text()
        self.color = QColor(color)
        self.setFocus()

    def cycle_width(self):
        self.stroke_width = {3:5,5:8,8:3}[self.stroke_width]
        self.width_button.setText(str(self.stroke_width))
        self.setFocus()

    def region(self):
        return QRect(self.start, self.end).normalized().intersected(self.rect()) if self.start else QRect()

    def paintEvent(self, event):
        p = QPainter(self)
        p.drawPixmap(self.rect(), self.snapshot)
        p.fillRect(self.rect(), QColor(0, 0, 0, 105))
        rect = self.region()
        if not rect.isEmpty():
            p.save()
            p.setClipRect(rect)
            p.drawPixmap(self.rect(), self.snapshot)
            p.restore()
            if self.locked and self.edited is not None:
                p.drawImage(rect,self.preview if self.preview is not None else self.edited)
            p.setPen(QPen(QColor('#07C160'), 2))
            p.drawRect(rect.adjusted(0, 0, -1, -1))
            ratio = self.snapshot.devicePixelRatio()
            hint = f'{round(rect.width()*ratio)} × {round(rect.height()*ratio)}   ' + ('Enter 完成 · Esc 取消' if self.locked else '松开选择 · Esc 取消')
            at = QPoint(max(8, min(rect.x(), self.width()-350)), max(30, rect.y()-12))
        else:
            hint = '拖动鼠标选择截图区域 · Esc / 右键取消'
            at = QPoint(32, 44)
        p.setPen(Qt.white)
        p.drawText(at, self.notice or hint)

    def physical_point(self, pos):
        rect = self.region()
        ratio = self.snapshot.devicePixelRatio()
        return QPoint(max(0,min(self.edited.width()-1,round((pos.x()-rect.x())*ratio))),max(0,min(self.edited.height()-1,round((pos.y()-rect.y())*ratio))))

    def mousePressEvent(self, event):
        if event.button() == Qt.RightButton:
            self.cancelled.emit()
        elif event.button() == Qt.LeftButton:
            if self.locked:
                self.commit_text()
                pos = event.position().toPoint()
                if not self.region().contains(pos):
                    return
                if self.tool == 'text':
                    self.open_text(pos)
                else:
                    self.before_stroke = self.edited.copy()
                    self.draw_points = [self.physical_point(pos)]
                    self.grabMouse()
                return
            self.start = event.position().toPoint()
            self.end = self.start
            self.grabMouse()
            self.update()

    def mouseMoveEvent(self, event):
        if self.locked:
            if self.draw_points:
                self.draw_points.append(self.physical_point(event.position().toPoint()))
                self.preview = self.render_stroke()
                self.update()
            return
        if self.start:
            self.end = event.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton or self.start is None:
            return
        self.releaseMouse()
        if self.locked:
            if self.draw_points:
                self.draw_points.append(self.physical_point(event.position().toPoint()))
                self.push_undo()
                self.edited = self.render_stroke()
                self.preview = None
                self.draw_points = []
                self.update()
            return
        self.end = event.position().toPoint()
        rect = self.region()
        if rect.width() < 3 or rect.height() < 3:
            self.start = None
            self.update()
            return
        ratio = self.snapshot.devicePixelRatio()
        physical = QRect(round(rect.x()*ratio), round(rect.y()*ratio), round(rect.width()*ratio), round(rect.height()*ratio))
        image = self.snapshot.toImage().copy(physical)
        image.setDevicePixelRatio(1)
        self.edited = image
        self.locked = True
        self.toolbar.adjustSize()
        bar_x = max(4,min(rect.right()-self.toolbar.width(),self.width()-self.toolbar.width()-4))
        bar_y = rect.bottom()+10
        if bar_y+self.toolbar.height() > self.height()-4:
            bar_y = max(4,rect.top()-self.toolbar.height()-10)
        self.toolbar.move(bar_x,bar_y)
        self.toolbar.show()
        self.setFocus()
        self.update()

    def render_stroke(self):
        image = self.before_stroke.copy()
        first,last = self.draw_points[0],self.draw_points[-1]
        rect = QRect(first,last).normalized().intersected(image.rect())
        ratio = self.snapshot.devicePixelRatio()
        p = QPainter(image)
        p.setRenderHint(QPainter.Antialiasing)
        width = max(1,round(self.stroke_width*ratio))
        p.setPen(QPen(self.color,width,Qt.SolidLine,Qt.RoundCap,Qt.RoundJoin))
        p.setBrush(Qt.NoBrush)
        if self.tool == 'rect':
            p.drawRect(rect)
        elif self.tool == 'ellipse':
            p.drawEllipse(rect)
        elif self.tool == 'arrow':
            p.drawLine(first,last)
            angle = math.atan2(last.y()-first.y(),last.x()-first.x())
            length = max(12*ratio,width*4)
            for offset in (-.5,.5):
                end = QPoint(round(last.x()-length*math.cos(angle+offset)),round(last.y()-length*math.sin(angle+offset)))
                p.drawLine(last,end)
        elif self.tool == 'pen':
            if len(self.draw_points)<2:
                p.drawPoint(first)
            for a,b in zip(self.draw_points,self.draw_points[1:]):
                p.drawLine(a,b)
        elif self.tool == 'mosaic' and rect.width()>1 and rect.height()>1:
            block = max(6,round(12*ratio))
            pixels = self.before_stroke.copy(rect).scaled(max(1,rect.width()//block),max(1,rect.height()//block),Qt.IgnoreAspectRatio,Qt.FastTransformation)
            pixels = pixels.scaled(rect.size(),Qt.IgnoreAspectRatio,Qt.FastTransformation)
            p.setRenderHint(QPainter.SmoothPixmapTransform,False)
            p.drawImage(rect,pixels)
        p.end()
        return image

    def push_undo(self):
        self.undo_stack.append(self.edited.copy())
        self.undo_stack = self.undo_stack[-10:]
        self.undo_button.setEnabled(True)

    def undo(self):
        self.commit_text()
        if self.undo_stack:
            self.edited = self.undo_stack.pop()
            self.undo_button.setEnabled(bool(self.undo_stack))
            self.preview = None
            self.update()
        self.setFocus()

    def open_text(self, pos):
        self.text_position = self.physical_point(pos)
        self.text_field = QLineEdit(self)
        self.text_field.setPlaceholderText('输入标注文字，Enter 确认')
        self.text_field.setMaxLength(240)
        self.text_field.setGeometry(max(0,min(pos.x(),self.width()-250)),max(0,min(pos.y(),self.height()-36)),250,36)
        self.text_field.setStyleSheet('background:white;color:'+self.color.name()+';font-size:18px;border:1px solid #07C160;')
        self.text_field.returnPressed.connect(self.commit_text)
        self.text_field.show()
        self.text_field.setFocus()

    def commit_text(self):
        field = self.text_field
        if field is None:
            return
        self.text_field = None
        text = field.text()
        field.hide()
        field.deleteLater()
        if text:
            self.push_undo()
            painter = QPainter(self.edited)
            painter.setRenderHint(QPainter.TextAntialiasing)
            painter.setPen(self.color)
            font = QFont('Microsoft YaHei UI')
            font.setPixelSize(round(20*self.snapshot.devicePixelRatio()))
            painter.setFont(font)
            painter.drawText(self.text_position+QPoint(0,font.pixelSize()),text)
            painter.end()
            self.update()
        self.setFocus()

    def finish(self):
        if not self.locked or self.edited is None:
            return
        self.commit_text()
        self.selected.emit(self.edited.copy())

    def save_image(self):
        if self.edited is None:
            return
        self.commit_text()
        initial = QStandardPaths.writableLocation(QStandardPaths.PicturesLocation) + '/截图_'+datetime.now().strftime('%Y%m%d_%H%M%S')+'.png'
        path,_ = QFileDialog.getSaveFileName(self,'保存截图',initial,'PNG 图片 (*.png)')
        if path:
            if not path.lower().endswith('.png'):
                path += '.png'
            if self.edited.save(path,'PNG'):
                self.finish()
            else:
                self.notice = '保存失败，请检查目录权限和磁盘空间'
                self.update()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.cancelled.emit()
        elif event.key() in (Qt.Key_Return,Qt.Key_Enter):
            self.finish()
        elif event.modifiers() & Qt.ControlModifier and event.key() == Qt.Key_Z:
            self.undo()
        elif event.modifiers() & Qt.ControlModifier and event.key() == Qt.Key_S:
            self.save_image()


class CaptureSession(QObject):
    finished = Signal(object)
    cancelled = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.overlays = []

    def begin(self):
        # Freeze every monitor before showing any overlay. Each uses its own DPI.
        snapshots = [(s, s.grabWindow(0)) for s in QApplication.screens()]
        if not snapshots or any(p.isNull() for _, p in snapshots):
            self.cancelled.emit()
            return
        cursor = QCursor.pos()
        active = None
        for screen, pixmap in snapshots:
            overlay = SelectionOverlay(screen, pixmap)
            overlay.selected.connect(self.complete)
            overlay.cancelled.connect(self.cancel)
            self.overlays.append(overlay)
            overlay.show()
            if screen.geometry().contains(cursor):
                active = overlay
        if active:
            active.activateWindow()
            active.setFocus()

    def clear(self):
        for overlay in self.overlays:
            overlay.releaseMouse()
            overlay.close()
            overlay.deleteLater()
        self.overlays.clear()

    def complete(self, image):
        self.clear()
        self.finished.emit(image)

    def cancel(self):
        self.clear()
        self.cancelled.emit()
