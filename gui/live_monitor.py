import time
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, 
    QPushButton, QLabel, QComboBox, QCheckBox,
    QSpinBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QLineEdit
)
from PySide6.QtCore import Qt, Signal, Slot, QTimer
from PySide6.QtGui import QColor, QTextCursor, QFont
import logging
from gui.timeline_view import TimelineView

logger = logging.getLogger('SpecterWire.LiveMonitor')

class LogEntry:
    """Individual log entry for the live monitor"""
    
    def __init__(self, message: str, timestamp: float = None, 
                severity: str = "INFO", category: str = "SYSTEM"):
        self.message = message
        self.timestamp = timestamp or time.time()
        self.severity = severity.upper()
        self.category = category.upper()
        
        # Formatted timestamp
        self.formatted_time = datetime.fromtimestamp(self.timestamp).strftime('%H:%M:%S.%f')[:-3]
    
    def get_color(self) -> Tuple[int, int, int]:
        """Get RGB color based on severity"""
        if self.severity == "HIGH":
            return (244, 67, 54)  # Red
        elif self.severity == "MEDIUM":
            return (255, 152, 0)  # Orange
        elif self.severity == "LOW":
            return (76, 175, 80)  # Green
        elif self.severity == "WARNING":
            return (255, 193, 7)  # Yellow
        elif self.severity == "ERROR":
            return (244, 67, 54)  # Red
        else:
            return (255, 255, 255)  # White
    
    def get_html(self) -> str:
        """Get HTML formatted string for log entry"""
        r, g, b = self.get_color()
        return (f'<div style="margin: 1px 0px; color: rgb({r},{g},{b});">'
                f'<span style="color: gray;">[{self.formatted_time}]</span> '
                f'<span style="color: rgb(100,181,246);">[{self.severity}]</span> '
                f'{self.message}'
                f'</div>')

class LiveMonitorWidget(QWidget):
    """
    Live monitoring widget for real-time event tracking
    """
    
    def __init__(self, parent=None, config=None):
        super().__init__(parent)
        
        # Store configuration
        self.config = config or {}
        
        # Initialize log storage
        self.log_entries = []
        self.filtered_entries = []
        self.max_entries = 1000  # Maximum number of entries to keep
        
        # Set up UI
        self._setup_ui()
        
        # Set up filters
        self._setup_filters()
        
        # Set up colors for different severity levels
        self.severity_colors = {
            "ERROR": QColor(244, 67, 54),      # Red
            "WARNING": QColor(255, 152, 0),    # Orange
            "CRITICAL": QColor(183, 28, 28),   # Dark Red
            "INFO": QColor(255, 255, 255),     # White
            "DEBUG": QColor(158, 158, 158),    # Gray
            "SUCCESS": QColor(76, 175, 80),    # Green
            "HIGH": QColor(244, 67, 54),       # Red for high anomaly
            "MEDIUM": QColor(255, 152, 0),     # Orange for medium anomaly
            "LOW": QColor(76, 175, 80)         # Green for low anomaly
        }
        
        # No timer here - we'll update the timeline directly when needed
    
    def _setup_ui(self):
        """Set up the user interface"""
        # Main layout
        main_layout = QVBoxLayout(self)
        
        # Controls layout
        control_layout = QHBoxLayout()
        
        # Filter controls
        filter_label = QLabel("Filter:")
        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("Filter logs...")
        self.filter_input.textChanged.connect(self._apply_filters)
        
        # Severity filter
        severity_label = QLabel("Severity:")
        self.severity_filter = QComboBox()
        self.severity_filter.addItems(["All Levels", "ERROR", "WARNING", "INFO", "DEBUG", "SUCCESS"])
        self.severity_filter.currentTextChanged.connect(self._apply_filters)
        
        # Auto-scroll checkbox
        self.auto_scroll = QCheckBox("Auto-scroll")
        self.auto_scroll.setChecked(True)
        
        # Clear button
        clear_button = QPushButton("Clear Logs")
        clear_button.clicked.connect(self._clear_logs)
        
        # Add controls to layout
        control_layout.addWidget(filter_label)
        control_layout.addWidget(self.filter_input)
        control_layout.addWidget(severity_label)
        control_layout.addWidget(self.severity_filter)
        control_layout.addWidget(self.auto_scroll)
        control_layout.addWidget(clear_button)
        
        # Log display
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        self.log_display.setLineWrapMode(QTextEdit.NoWrap)
        self.log_display.setStyleSheet("""
            QTextEdit {
                background-color: #1a1a1a;
                color: white;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 9pt;
                border: none;
            }
        """)
        
        # Create timeline view
        self.timeline = QWidget()
        timeline_layout = QVBoxLayout(self.timeline)
        timeline_layout.setContentsMargins(0, 0, 0, 0)
        
        # Timeline visualization component
        self.timeline_view = TimelineView()
        self.timeline_view.setMinimumHeight(100)
        self.timeline_view.setMaximumHeight(200)
        
        # Configure timeline settings from config
        refresh_interval = 1000  # Default refresh interval
        if self.config:
            refresh_interval = self.config.get("gui_config", {}).get("refresh_interval", 1000)
        self.timeline_view.setRefreshInterval(refresh_interval)
        
        # Connect signals
        self.timeline_view.eventSelected.connect(self._on_timeline_event_selected)
        timeline_layout.addWidget(self.timeline_view)
        
        # No need to start a timer now
        
        # Add timeline controls
        timeline_controls = QHBoxLayout()
        zoom_in_btn = QPushButton("Zoom In")
        zoom_out_btn = QPushButton("Zoom Out")
        reset_view_btn = QPushButton("Reset View")
        
        zoom_in_btn.clicked.connect(self.timeline_view.zoomIn)
        zoom_out_btn.clicked.connect(self.timeline_view.zoomOut)
        reset_view_btn.clicked.connect(self.timeline_view.resetView)
        
        timeline_controls.addStretch()
        timeline_controls.addWidget(zoom_in_btn)
        timeline_controls.addWidget(zoom_out_btn)
        timeline_controls.addWidget(reset_view_btn)
        timeline_layout.addLayout(timeline_controls)
        # showing events on a horizontal timeline
        timeline_placeholder = QLabel("Timeline Visualization")
        timeline_placeholder.setAlignment(Qt.AlignCenter)
        timeline_placeholder.setStyleSheet("color: gray; border: 1px dashed gray; padding: 10px;")
        timeline_layout.addWidget(timeline_placeholder)
        
        # Status label for entry count
        self.status_label = QLabel(f"Log entries: 0/{self.max_entries}")
        
        # Add all widgets to main layout
        main_layout.addLayout(control_layout)
        main_layout.addWidget(self.log_display, 3)  # 3:1 ratio (logs:timeline)
        main_layout.addWidget(self.timeline, 1)
        main_layout.addWidget(self.status_label)
    
    def _setup_filters(self):
        """Initialize filter settings"""
        self.filters = {
            'severity': None,  # None means no filter
            'category': None,
            'text_search': None
        }
    
    def _on_timeline_event_selected(self, event_data):
        """Handle when a timeline event is selected"""
        if event_data:
            # Find the log entry for this event and highlight it
            timestamp = event_data.get('timestamp')
            if timestamp:
                # Find the log entry with this timestamp
                for i, entry in enumerate(self.filtered_entries):
                    if abs(entry.timestamp - timestamp) < 0.1:  # Small threshold for floating-point comparison
                        # Highlight this entry
                        self._highlight_log_entry(i)
                        break
    
    def _highlight_log_entry(self, index):
        """Highlight a specific log entry"""
        # This would typically scroll to the entry and highlight it
        # For now we'll just log it
        if 0 <= index < len(self.filtered_entries):
            logger.debug(f"Highlighting log entry: {self.filtered_entries[index].message}")
    
    def _apply_filters(self):
        """Apply current filters to the log entries"""
        # Get filter values
        severity_filter = self.severity_filter.currentText()
        if severity_filter == "All Levels":
            self.filters['severity'] = None
        else:
            self.filters['severity'] = severity_filter
        
        # Apply filters
        self.filtered_entries = []
        for entry in self.log_entries:
            if self._entry_matches_filters(entry):
                self.filtered_entries.append(entry)
        
        # Update display
        self._update_display()
    
    def _entry_matches_filters(self, entry: LogEntry) -> bool:
        """Check if entry matches current filters"""
        # Check severity filter
        if self.filters['severity'] is not None:
            if entry.severity != self.filters['severity']:
                return False
        
        # Check text search
        if self.filters['text_search'] is not None:
            if self.filters['text_search'].lower() not in entry.message.lower():
                return False
        
        return True
    
    def _update_display(self):
        """Update log display with filtered entries"""
        self.log_display.clear()
        
        # Build HTML content
        html_content = '<div style="font-family: Consolas, \'Courier New\', monospace;">'
        
        for entry in self.filtered_entries:
            html_content += entry.get_html()
        
        html_content += '</div>'
        
        # Set HTML content
        self.log_display.setHtml(html_content)
        
        # Auto-scroll to bottom if enabled
        if self.auto_scroll.isChecked():
            cursor = self.log_display.textCursor()
            cursor.movePosition(QTextCursor.End)
            self.log_display.setTextCursor(cursor)
    
    def _clear_logs(self):
        """Clear all log entries"""
        self.log_entries = []
        self.filtered_entries = []
        self.log_display.clear()
    
    def add_log_entry(self, message: str, severity: str = "INFO", timestamp=None):
        """Add a new log entry."""
        # Create new log entry
        entry = LogEntry(message=message, severity=severity, timestamp=timestamp)
        
        # Add to log entries
        self.log_entries.append(entry)
        
        # Check if we need to truncate
        if len(self.log_entries) > self.max_entries:
            self.log_entries = self.log_entries[-self.max_entries:]
        
        # Apply filters
        if self._entry_matches_filters(entry):
            self.filtered_entries.append(entry)
            
            # Update the display with the new entry
            self._update_display_with_entry(entry)
            
            # Update the timeline
            self._update_timeline()
        
        # Update entry count
        self.status_label.setText(f"Log entries: {len(self.log_entries)}/{self.max_entries}")
        
        # Log to standard logger as well
        log_method = getattr(logger, severity.lower(), None)
        if log_method:
            log_method(message)
        else:
            logger.info(f"[{severity}] {message}")

    def _update_timeline(self):
        """Update the timeline widget with the latest log entries."""
        if not hasattr(self, 'timeline_view'):
            return
            
        # Convert log entries to timeline events
        events = []
        for entry in self.filtered_entries:
            severity_color = self.severity_colors.get(entry.severity, QColor(200, 200, 200))
            event = {
                'timestamp': entry.timestamp,
                'label': entry.message[:20] + '...' if len(entry.message) > 20 else entry.message,
                'color': severity_color.name(),
                'details': entry.message
            }
            events.append(event)
            
        # Update timeline with events
        self.timeline_view.setEvents(events)
        
        # Manually update timeline instead of relying on timer
        self.timeline_view.manualUpdate()

    def cleanup(self):
        """Clean up resources when the widget is about to be destroyed."""
        # No timer to stop in TimelineView anymore
        pass
        
    def __del__(self):
        """Destructor to ensure cleanup is called."""
        self.cleanup()

    def _update_display_with_entry(self, entry):
        """Update the display with a single log entry."""
        cursor = self.log_display.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.log_display.setTextCursor(cursor)
        
        # Add HTML
        self.log_display.insertHtml(entry.get_html())
        
        # Auto-scroll if enabled
        if self.auto_scroll.isChecked():
            cursor.movePosition(QTextCursor.End)
            self.log_display.setTextCursor(cursor) 