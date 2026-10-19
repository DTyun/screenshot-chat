"""Selectable text in virtualized, read-only chat bubbles."""
from PySide6.QtCore import Qt, QPointF, QTimer, QVariantAnimation, QEasingCurve
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QListWidget
from .theme import MESSAGE_WHEEL_STEP, MESSAGE_WHEEL_DURATION, MESSAGE_WHEEL_MAX_AHEAD


class MessageHistory(QListWidget):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.text_message_id = None
        self.text_anchor = self.text_position = 0
        self.dragging_text = False
        self.drag_point = None
        self.selection_scroll = QTimer(self)
        self.selection_scroll.setInterval(35)
        self.selection_scroll.timeout.connect(self.auto_scroll_selection)
        self.wheel_target = None
        self.animating_scroll = False
        self.wheel_animation = QVariantAnimation(self)
        self.wheel_animation.setDuration(MESSAGE_WHEEL_DURATION)
        self.wheel_animation.setEasingCurve(QEasingCurve.OutCubic)
        self.wheel_animation.valueChanged.connect(self.animate_scroll)
        self.verticalScrollBar().setSingleStep(20)
        self.verticalScrollBar().valueChanged.connect(self.external_scroll)
        self.verticalScrollBar().rangeChanged.connect(lambda *args: self.stop_wheel_scroll())
        self.verticalScrollBar().sliderPressed.connect(self.stop_wheel_scroll)
        self.currentItemChanged.connect(lambda current,previous: self.clear_text_selection())
        self.model().modelReset.connect(self.clear_text_selection)
        self.model().rowsRemoved.connect(lambda *args: self.clear_text_selection())
        self.setMouseTracking(True)

    def clear_text_selection(self):
        self.stop_wheel_scroll()
        self.text_message_id = None
        self.text_anchor = self.text_position = 0
        self.dragging_text = False
        self.selection_scroll.stop()
        self.viewport().update()

    def stop_wheel_scroll(self):
        self.wheel_animation.stop()
        self.wheel_target = None

    def external_scroll(self,value):
        if not self.animating_scroll:
            self.stop_wheel_scroll()

    def animate_scroll(self,value):
        self.animating_scroll = True
        try:
            self.verticalScrollBar().setValue(round(float(value)))
        finally:
            self.animating_scroll = False

    def wheelEvent(self,event):
        bar = self.verticalScrollBar()
        if event.pixelDelta().y():
            # Touchpads already deliver smooth pixel distances; do not multiply them.
            self.stop_wheel_scroll()
            bar.setValue(bar.value()-event.pixelDelta().y())
            event.accept()
            return
        if not event.angleDelta().y():
            event.ignore()
            return
        current = bar.value()
        distance = -event.angleDelta().y()/120*MESSAGE_WHEEL_STEP
        target = self.wheel_target if self.wheel_target is not None else float(current)
        if (target-current)*distance<0:
            target = float(current)
        target = max(bar.minimum(),min(bar.maximum(),target+distance))
        # Do not queue a long inertial tail when the wheel is spun repeatedly.
        target = max(current-MESSAGE_WHEEL_MAX_AHEAD,min(current+MESSAGE_WHEEL_MAX_AHEAD,target))
        self.wheel_animation.stop()
        self.wheel_target = target
        self.wheel_animation.setStartValue(float(current))
        self.wheel_animation.setEndValue(float(target))
        self.wheel_animation.start()
        event.accept()

    def text_layout(self,item):
        if item and item.data(Qt.UserRole)['text']:
            return self.itemDelegate().text_layout(item.data(Qt.UserRole),self.visualItemRect(item))
        return None

    def text_at(self,point):
        item = self.itemAt(point)
        layout = self.text_layout(item)
        if layout and layout[1].contains(point):
            return item,layout
        return None,None

    @staticmethod
    def position_at(layout,point):
        document,rect = layout
        local = QPointF(point.x()-rect.x()-10,point.y()-rect.y()-10)
        if local.y()<0:
            return 0
        if local.y()>document.size().height():
            return document.characterCount()-1
        return max(0,document.documentLayout().hitTest(local,Qt.FuzzyHit))

    def selected_text(self,item=None):
        item = item or self.currentItem()
        if not item or item.data(Qt.UserRole)['id'] != self.text_message_id:
            return ''
        layout = self.text_layout(item)
        if not layout:
            return ''
        cursor = QTextCursor(layout[0])
        cursor.setPosition(self.text_anchor)
        cursor.setPosition(self.text_position,QTextCursor.KeepAnchor)
        return cursor.selectedText().replace('\u2029','\n')

    def select_to(self,point):
        item = self.currentItem()
        if item and item.data(Qt.UserRole)['id']==self.text_message_id:
            layout = self.text_layout(item)
            if layout:
                self.text_position = self.position_at(layout,point)
                self.viewport().update()

    def mousePressEvent(self,event):
        self.stop_wheel_scroll()
        item,layout = self.text_at(event.position().toPoint())
        if event.button()==Qt.LeftButton and layout:
            self.setCurrentItem(item)
            self.setFocus(Qt.MouseFocusReason)
            self.text_message_id = item.data(Qt.UserRole)['id']
            self.text_anchor = self.text_position = self.position_at(layout,event.position().toPoint())
            self.dragging_text = True
            self.viewport().update()
            event.accept()
            return
        if event.button()==Qt.LeftButton:
            self.clear_text_selection()
        super().mousePressEvent(event)

    def mouseMoveEvent(self,event):
        point = event.position().toPoint()
        if self.dragging_text:
            self.drag_point = point
            self.select_to(point)
            if point.y()<0 or point.y()>=self.viewport().height():
                self.selection_scroll.start()
            else:
                self.selection_scroll.stop()
            event.accept()
            return
        _,layout = self.text_at(point)
        self.viewport().setCursor(Qt.IBeamCursor if layout else Qt.ArrowCursor)
        super().mouseMoveEvent(event)

    def auto_scroll_selection(self):
        if not self.dragging_text or self.drag_point is None:
            self.selection_scroll.stop()
            return
        bar = self.verticalScrollBar()
        bar.setValue(bar.value()+(-18 if self.drag_point.y()<0 else 18))
        self.select_to(self.drag_point)

    def mouseReleaseEvent(self,event):
        if event.button()==Qt.LeftButton and self.dragging_text:
            self.select_to(event.position().toPoint())
            self.dragging_text = False
            self.selection_scroll.stop()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self,event):
        item,layout = self.text_at(event.position().toPoint())
        if event.button()==Qt.LeftButton and layout:
            self.setCurrentItem(item)
            self.text_message_id = item.data(Qt.UserRole)['id']
            cursor = QTextCursor(layout[0])
            cursor.setPosition(self.position_at(layout,event.position().toPoint()))
            cursor.select(QTextCursor.WordUnderCursor)
            self.text_anchor,self.text_position = cursor.anchor(),cursor.position()
            self.viewport().update()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self,event):
        self.stop_wheel_scroll()
        item = self.currentItem()
        layout = self.text_layout(item)
        if layout and event.key()==Qt.Key_A and event.modifiers() & Qt.ControlModifier:
            self.text_message_id = item.data(Qt.UserRole)['id']
            self.text_anchor,self.text_position = 0,layout[0].characterCount()-1
            self.viewport().update()
            event.accept()
            return
        moves = {Qt.Key_Left:QTextCursor.PreviousCharacter,Qt.Key_Right:QTextCursor.NextCharacter,
                 Qt.Key_Up:QTextCursor.Up,Qt.Key_Down:QTextCursor.Down,
                 Qt.Key_Home:QTextCursor.StartOfLine,Qt.Key_End:QTextCursor.EndOfLine}
        if layout and self.text_message_id==item.data(Qt.UserRole)['id'] and event.key() in moves and event.modifiers() & Qt.ShiftModifier:
            cursor = QTextCursor(layout[0])
            cursor.setPosition(self.text_anchor)
            cursor.setPosition(self.text_position,QTextCursor.KeepAnchor)
            cursor.movePosition(moves[event.key()],QTextCursor.KeepAnchor)
            self.text_position = cursor.position()
            self.viewport().update()
            event.accept()
            return
        super().keyPressEvent(event)

    def hideEvent(self,event):
        self.stop_wheel_scroll()
        self.selection_scroll.stop()
        super().hideEvent(event)
