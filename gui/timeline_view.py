from PySide6.QtWidgets import QWidget, QToolTip
from PySide6.QtCore import Qt, Signal, QRectF, QPointF
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QMouseEvent
import math

class TimelineView(QWidget):
    eventSelected = Signal(object)  # Emits the selected event dict

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(100)
        self.setMaximumHeight(200)
        self._events = []  # List of dicts: {timestamp, label, color, ...}
        self._zoom = 1.0
        self._pan = 0.0
        self._selected_event = None
        self.setMouseTracking(True)
        # No timer initialization, we'll update manually

    def setEvents(self, events):
        """Set the list of events to display."""
        self._events = events
        self.update()  # Request a repaint

    def setRefreshInterval(self, interval_ms):
        """Store refresh interval but don't create a timer."""
        self._refresh_interval = interval_ms
        # No timer to update

    def mousePressEvent(self, event: QMouseEvent):
        """Handle mouse press events for selecting timeline items."""
        if event.button() == Qt.LeftButton:
            # Find if we clicked on an event
            pos = event.position()
            for event_data in self._events:
                rect = self._getEventRect(event_data)
                if rect.contains(pos):
                    self._selected_event = event_data
                    self.eventSelected.emit(event_data)
                    self.update()  # Repaint to show selection
                    break

    def mouseMoveEvent(self, event: QMouseEvent):
        """Handle mouse move for tooltips."""
        pos = event.position()
        for event_data in self._events:
            rect = self._getEventRect(event_data)
            if rect.contains(pos):
                # Show tooltip with event details
                tooltip = f"Time: {event_data.get('timestamp', 0)}\n"
                tooltip += f"Label: {event_data.get('label', '')}\n"
                if 'details' in event_data:
                    tooltip += f"Details: {event_data['details']}"
                QToolTip.showText(event.globalPosition().toPoint(), tooltip, self)
                return
        QToolTip.hideText()

    def wheelEvent(self, event):
        """Handle zoom in/out with mouse wheel."""
        delta = event.angleDelta().y()
        if delta > 0:
            self._zoom *= 1.1  # Zoom in
        else:
            self._zoom /= 1.1  # Zoom out
        self.update()  # Request repaint

    def paintEvent(self, event):
        """Draw the timeline and events."""
        if not self._events:
            return
        
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Draw timeline axis
        width = self.width()
        height = self.height()
        axis_y = height - 30
        
        # Draw horizontal line
        painter.setPen(QPen(Qt.gray, 1))
        painter.drawLine(10, axis_y, width - 10, axis_y)
        
        # Draw timeline markings
        self._drawTimelineMarkings(painter, axis_y, width)
        
        # Draw events
        for event_data in self._events:
            rect = self._getEventRect(event_data)
            color = QColor(event_data.get('color', '#1E88E5'))
            
            # Draw event marker
            painter.setBrush(QBrush(color))
            painter.setPen(QPen(Qt.black, 1))
            
            # Highlight selected event
            if self._selected_event is event_data:
                painter.setPen(QPen(Qt.red, 2))
            
            painter.drawEllipse(rect)
        
        painter.end()

    def _drawTimelineMarkings(self, painter, axis_y, width):
        """Draw time markings on the timeline."""
        if not self._events:
            return
            
        # Get time range
        times = [event.get('timestamp', 0) for event in self._events]
        min_time = min(times)
        max_time = max(times)
        
        if max_time == min_time:
            max_time = min_time + 1  # Avoid division by zero
            
        time_range = max_time - min_time
        
        # Draw tick marks
        painter.setPen(QPen(Qt.gray, 1))
        font = QFont()
        font.setPointSize(8)
        painter.setFont(font)
        
        tick_count = 5
        for i in range(tick_count + 1):
            x = 10 + (width - 20) * i / tick_count
            painter.drawLine(x, axis_y - 5, x, axis_y + 5)
            
            # Draw time labels
            tick_time = min_time + (time_range * i / tick_count)
            time_str = f"{tick_time:.1f}"
            painter.drawText(QPointF(x - 15, axis_y + 20), time_str)

    def _getEventRect(self, event_data):
        """Calculate the rectangle for an event marker."""
        width = self.width()
        height = self.height()
        axis_y = height - 30
        
        # Get time range
        times = [event.get('timestamp', 0) for event in self._events]
        min_time = min(times)
        max_time = max(times)
        
        if max_time == min_time:
            max_time = min_time + 1  # Avoid division by zero
            
        time_range = (max_time - min_time) * self._zoom
        
        # Calculate x position based on timestamp
        timestamp = event_data.get('timestamp', 0)
        x_ratio = (timestamp - min_time) / time_range
        x_pos = 10 + (width - 20) * x_ratio + self._pan
        
        # Keep within bounds
        x_pos = max(10, min(width - 10, x_pos))
        
        # Create rectangle for event marker
        marker_size = 10
        rect = QRectF(x_pos - marker_size/2, axis_y - marker_size/2, marker_size, marker_size)
        return rect

    def manualUpdate(self):
        """Method to be called externally to update the timeline."""
        self.update()  # Request a repaint
        
    def zoomIn(self):
        """Zoom in on the timeline."""
        self._zoom = min(self._zoom * 1.2, 10.0)
        self.update()
        
    def zoomOut(self):
        """Zoom out on the timeline."""
        self._zoom = max(self._zoom / 1.2, 0.1)
        self.update()
        
    def resetView(self):
        """Reset the zoom and pan to default values."""
        self._zoom = 1.0
        self._pan = 0.0
        self.update()

    # No need for timer methods anymore
    # startTimer and stopTimer are removed 