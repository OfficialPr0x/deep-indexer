import os
import sys
import time
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextEdit,
    QScrollArea, QFrame, QSplitter, QTableWidget, QTableWidgetItem,
    QHeaderView, QProgressBar, QListWidget, QListWidgetItem
)
from PySide6.QtCore import Qt, Signal, Slot, QTimer, QThread
from PySide6.QtGui import QFont, QColor, QTextCursor

# Configure logging
logger = logging.getLogger('SpecterWire.LiveMonitor')

class LogOutputWidget(QTextEdit):
    """Widget that displays formatted log output with syntax highlighting."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setLineWrapMode(QTextEdit.NoWrap)
        # Use monospace font
        self.setFont(QFont("Consolas", 9))
        # Customize appearance
        self.setStyleSheet("""
            background-color: #1e1e1e;
            color: #f0f0f0;
            border: none;
        """)
    
    def add_log_entry(self, message, severity="INFO"):
        """Add a log entry with appropriate color based on severity."""
        # Define colors for different log levels
        colors = {
            "DEBUG": "#9A9A9A",     # Gray
            "INFO": "#FFFFFF",      # White
            "WARNING": "#FFC107",   # Yellow
            "ERROR": "#F44336",     # Red
            "SUCCESS": "#4CAF50",   # Green
            "MEDIUM": "#FFC107",    # Yellow (for alerts)
            "HIGH": "#F44336",      # Red (for alerts)
            "CRITICAL": "#D32F2F"   # Dark Red
        }
        
        # Get color based on severity (defaulting to white if not found)
        color = colors.get(severity.upper(), "#FFFFFF")
        
        # Get current timestamp
        timestamp = time.strftime('%H:%M:%S')
        
        # Add formatted message to log
        self._append_to_log(f"<span style='color:#777777'>[{timestamp}]</span> "
                           f"<span style='color:{color}'>{message}</span>")
    
    def _append_to_log(self, html_text):
        """Thread-safe method to append text to the log."""
        # Get cursor at the end
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.End)
        
        # Insert HTML-formatted text
        cursor.insertHtml(html_text + "<br>")
        
        # Auto-scroll to the latest entry
        self.setTextCursor(cursor)
        self.ensureCursorVisible()

class LiveMonitorWidget(QWidget):
    """
    Widget displaying real-time file scanning results and activity logs.
    
    This widget provides a live view of the scanning process, including
    file analysis results, warnings, and system status.
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Setup UI
        self.setup_ui()
        
        # Local state
        self.files_processed = 0
        self.start_time = None
        self.file_counts = {
            "LOW": 0,
            "MEDIUM": 0, 
            "HIGH": 0,
            "CRITICAL": 0
        }
        
        # Ensure thread safety for timer operations
        self.main_thread = QThread.currentThread()
        
        # Set up update timer (for refreshing statistics)
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self.update_statistics)
        self.update_timer.start(1000)  # Update once per second
        
    def setup_ui(self):
        """Set up the UI components."""
        # Main layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Top area with statistics
        stats_frame = QFrame()
        stats_frame.setFrameShape(QFrame.StyledPanel)
        stats_frame.setStyleSheet("""
            QFrame {
                background-color: #2d2d30;
                border: 1px solid #3f3f46;
            }
        """)
        
        stats_layout = QHBoxLayout(stats_frame)
        
        # Statistics blocks
        self.stat_widgets = {}
        for stat_name, default_value, tooltip in [
            ("Files Processed", "0", "Total number of files analyzed"),
            ("Elapsed Time", "00:00", "Total scanning time"),
            ("Medium Risk", "0", "Files with medium risk score"),
            ("High Risk", "0", "Files with high risk score"),
            ("Critical Risk", "0", "Files with critical risk score")
        ]:
            stat_widget = QWidget()
            stat_layout = QVBoxLayout(stat_widget)
            stat_layout.setContentsMargins(5, 5, 5, 5)
            
            # Stat label
            label = QLabel(stat_name)
            label.setAlignment(Qt.AlignCenter)
            label.setStyleSheet("color: #cccccc; font-size: 9pt;")
            
            # Stat value
            value = QLabel(default_value)
            value.setAlignment(Qt.AlignCenter)
            value.setStyleSheet("color: #ffffff; font-size: 14pt; font-weight: bold;")
            
            stat_layout.addWidget(label)
            stat_layout.addWidget(value)
            
            stats_layout.addWidget(stat_widget)
            
            # Store reference for later updates
            self.stat_widgets[stat_name] = value
            
            # Set tooltip
            stat_widget.setToolTip(tooltip)
        
        layout.addWidget(stats_frame)
        
        # Progress section
        progress_layout = QHBoxLayout()
        
        # Progress status
        self.progress_status = QLabel("Ready")
        progress_layout.addWidget(self.progress_status, 1)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        progress_layout.addWidget(self.progress_bar, 4)
        
        layout.addLayout(progress_layout)
        
        # Create splitter for log and alert areas
        splitter = QSplitter(Qt.Vertical)
        
        # Log output area
        self.log_output = LogOutputWidget()
        splitter.addWidget(self.log_output)
        
        # Alerts table
        alerts_frame = QFrame()
        alerts_layout = QVBoxLayout(alerts_frame)
        alerts_layout.setContentsMargins(0, 0, 0, 0)
        
        alerts_header = QLabel("File Alerts")
        alerts_header.setStyleSheet("font-weight: bold; padding: 5px;")
        alerts_layout.addWidget(alerts_header)
        
        self.alerts_table = QTableWidget(0, 3)
        self.alerts_table.setHorizontalHeaderLabels(["File", "Score", "Severity"])
        self.alerts_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.alerts_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.alerts_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.alerts_table.verticalHeader().setVisible(False)
        self.alerts_table.setSelectionBehavior(QTableWidget.SelectRows)
        alerts_layout.addWidget(self.alerts_table)
        
        splitter.addWidget(alerts_frame)
        
        # Set initial sizes
        splitter.setSizes([300, 200])
        
        layout.addWidget(splitter)
        
        # Add initial log message
        self.add_log_entry("Live monitoring initialized and ready", "INFO")
    
    def add_file_alert(self, file_path, score, severity):
        """Add a file alert to the alerts table."""
        # Ensure this is called from the main thread
        if QThread.currentThread() != self.main_thread:
            QTimer.singleShot(0, lambda: self.add_file_alert(file_path, score, severity))
            return
            
        # Add to table
        row = self.alerts_table.rowCount()
        self.alerts_table.insertRow(row)
        
        # File path
        self.alerts_table.setItem(row, 0, QTableWidgetItem(file_path))
        
        # Score
        score_item = QTableWidgetItem(f"{score:.2f}")
        score_item.setTextAlignment(Qt.AlignCenter)
        self.alerts_table.setItem(row, 1, score_item)
        
        # Severity
        severity_item = QTableWidgetItem(severity)
        severity_item.setTextAlignment(Qt.AlignCenter)
        
        # Set background color based on severity
        if severity == "HIGH":
            severity_item.setBackground(QColor(244, 67, 54, 100))  # Red
        elif severity == "MEDIUM":
            severity_item.setBackground(QColor(255, 193, 7, 100))  # Yellow
        elif severity == "CRITICAL":
            severity_item.setBackground(QColor(183, 28, 28, 100))  # Dark Red
        
        self.alerts_table.setItem(row, 2, severity_item)
        
        # Update counter
        if severity in self.file_counts:
            self.file_counts[severity] += 1
        
        # Sort by severity (most severe at top)
        self.alerts_table.sortItems(2, Qt.DescendingOrder)
    
    def add_log_entry(self, message, severity="INFO"):
        """Add a log entry to the log output."""
        # Ensure this is called from the main thread
        if QThread.currentThread() != self.main_thread:
            QTimer.singleShot(0, lambda: self.add_log_entry(message, severity))
            return
            
        # Add to log widget
        self.log_output.add_log_entry(message, severity)
        
        # Also log to Python logger if it's a warning or error
        if severity.upper() in ["WARNING", "ERROR", "CRITICAL"]:
            log_method = getattr(logger, severity.lower(), logger.info)
            log_method(message)
    
    def update_progress(self, current, total, status_text=None):
        """Update the progress bar."""
        # Ensure this is called from the main thread
        if QThread.currentThread() != self.main_thread:
            QTimer.singleShot(0, lambda: self.update_progress(current, total, status_text))
            return
            
        # Start timer if not started
        if self.start_time is None:
            self.start_time = time.time()
        
        # Update progress bar
        if total > 0:
            percent = min(100, int((current / total) * 100))
            self.progress_bar.setValue(percent)
            self.progress_bar.setFormat(f"{percent}% ({current}/{total} files)")
        else:
            self.progress_bar.setValue(0)
            self.progress_bar.setFormat("0%")
        
        # Update status text if provided
        if status_text:
            self.progress_status.setText(status_text)
    
    def update_statistics(self):
        """Update the statistics display."""
        # Ensure this is called from the main thread
        if QThread.currentThread() != self.main_thread:
            QTimer.singleShot(0, self.update_statistics)
            return
            
        # Update file count
        self.stat_widgets["Files Processed"].setText(str(self.files_processed))
        
        # Update risk counts
        self.stat_widgets["Medium Risk"].setText(str(self.file_counts.get("MEDIUM", 0)))
        self.stat_widgets["High Risk"].setText(str(self.file_counts.get("HIGH", 0)))
        self.stat_widgets["Critical Risk"].setText(str(self.file_counts.get("CRITICAL", 0)))
        
        # Update elapsed time if scan has started
        if self.start_time:
            elapsed = time.time() - self.start_time
            minutes = int(elapsed // 60)
            seconds = int(elapsed % 60)
            self.stat_widgets["Elapsed Time"].setText(f"{minutes:02d}:{seconds:02d}")
    
    def reset(self):
        """Reset the monitor state."""
        # Ensure this is called from the main thread
        if QThread.currentThread() != self.main_thread:
            QTimer.singleShot(0, self.reset)
            return
            
        # Reset counters
        self.files_processed = 0
        self.start_time = None
        self.file_counts = {
            "LOW": 0,
            "MEDIUM": 0, 
            "HIGH": 0,
            "CRITICAL": 0
        }
        
        # Reset progress
        self.progress_bar.setValue(0)
        self.progress_status.setText("Ready")
        
        # Clear alerts table
        self.alerts_table.setRowCount(0)
        
        # Add log entry
        self.add_log_entry("Monitor reset and ready for new scan", "INFO")
        
        # Update stats to show zeros
        self.update_statistics() 