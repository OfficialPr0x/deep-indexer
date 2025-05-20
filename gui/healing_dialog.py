import os
import sys
import time
import logging
from datetime import datetime
from typing import Dict, Any, List

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextEdit,
    QProgressBar, QScrollArea, QWidget, QFrame, QTabWidget, QTableWidget,
    QTableWidgetItem, QHeaderView, QSplitter, QStyleFactory
)
from PySide6.QtCore import Qt, QTimer, Signal, Slot, QSize, QThread
from PySide6.QtGui import QFont, QColor, QTextCursor, QIcon, QPalette

# Configure logging
logger = logging.getLogger('SpecterWire.Healing')

class LogHandler(logging.Handler):
    """Custom log handler that emits signals when new logs are available."""
    log_signal = Signal(str, int)  # Log message, log level
    
    def __init__(self):
        super().__init__()
        self.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%H:%M:%S'
        ))
        
    def emit(self, record):
        try:
            msg = self.format(record)
            self.log_signal.emit(msg, record.levelno)
        except Exception as e:
            print(f"Error in log handler: {e}")


class HealingDialog(QDialog):
    """
    Modal dialog that displays real-time information during DeepSeek's 
    self-healing process, with detailed logs and recovery status.
    """
    
    def __init__(self, parent=None, error_type=None, context=None):
        super().__init__(parent)
        self.setWindowTitle("DeepSeek Self-Healing in Progress")
        self.setMinimumSize(700, 500)
        self.setModal(True)
        
        # Store healing context
        self.error_type = error_type or "Unknown Error"
        self.context = context or {}
        self.healing_start_time = time.time()
        self.max_retries = self.context.get('max_retries', 3)
        self.current_retry = 0
        self.healing_successful = False
        self.error_details = self.context.get('error_details', {})
        
        # Setup UI
        self._setup_ui()
        
        # Start update timer
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self._update_elapsed_time)
        self.update_timer.start(1000)  # Update every second
        
        # Set up log handler
        self.log_handler = LogHandler()
        self.log_handler.log_signal.connect(self._on_new_log)
        self.log_handler.setLevel(logging.DEBUG)
        
        # Add log handler to logger
        root_logger = logging.getLogger()
        root_logger.addHandler(self.log_handler)
        
        # Initial log message
        logger.info(f"Self-healing process initiated for: {self.error_type}")
        logger.info(f"Attempting recovery with strategy: {self.context.get('strategy', 'Standard recovery')}")
    
    def _setup_ui(self):
        """Set up dialog UI components."""
        main_layout = QVBoxLayout(self)
        
        # Header section with error information
        header_frame = QFrame()
        header_frame.setFrameShape(QFrame.StyledPanel)
        header_layout = QVBoxLayout(header_frame)
        
        # Add error title
        error_title = QLabel(f"<h2>Self-Healing: {self.error_type}</h2>")
        error_title.setAlignment(Qt.AlignCenter)
        header_layout.addWidget(error_title)
        
        # Add description
        desc_text = self.context.get('description', 'Automatic recovery process is running to fix an issue detected in the DeepSeek engine.')
        description = QLabel(desc_text)
        description.setWordWrap(True)
        header_layout.addWidget(description)
        
        # Add status section
        status_layout = QHBoxLayout()
        
        # Status indicator
        self.status_label = QLabel("<b>Status:</b> Running")
        status_layout.addWidget(self.status_label)
        
        # Elapsed time
        self.elapsed_label = QLabel("<b>Elapsed:</b> 00:00")
        status_layout.addWidget(self.elapsed_label)
        
        # Retry counter
        self.retry_label = QLabel(f"<b>Attempts:</b> 0/{self.max_retries}")
        status_layout.addWidget(self.retry_label)
        
        header_layout.addLayout(status_layout)
        
        # Add progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        header_layout.addWidget(self.progress_bar)
        
        main_layout.addWidget(header_frame)
        
        # Add tab widget for logs and details
        self.tab_widget = QTabWidget()
        
        # Log tab
        self.log_widget = QTextEdit()
        self.log_widget.setReadOnly(True)
        self.log_widget.setLineWrapMode(QTextEdit.NoWrap)
        self.log_widget.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #f0f0f0;
                font-family: "Consolas", "Monaco", monospace;
                font-size: 10pt;
            }
        """)
        self.tab_widget.addTab(self.log_widget, "Live Logs")
        
        # Details tab
        details_widget = QWidget()
        details_layout = QVBoxLayout(details_widget)
        
        # Error details
        error_info = QTableWidget(0, 2)
        error_info.setHorizontalHeaderLabels(["Property", "Value"])
        error_info.horizontalHeader().setStretchLastSection(True)
        error_info.verticalHeader().setVisible(False)
        error_info.setAlternatingRowColors(True)
        
        # Fill with context details
        if self.context:
            for row, (key, value) in enumerate(self.context.items()):
                if key != 'description' and key != 'strategy' and key != 'max_retries':
                    error_info.insertRow(row)
                    error_info.setItem(row, 0, QTableWidgetItem(str(key)))
                    error_info.setItem(row, 1, QTableWidgetItem(str(value)))
        
        details_layout.addWidget(error_info)
        self.tab_widget.addTab(details_widget, "Error Details")
        
        # Add diagnostic tab
        diagnostic_widget = QWidget()
        diagnostic_layout = QVBoxLayout(diagnostic_widget)
        
        # System status
        status_table = QTableWidget(0, 2)
        status_table.setHorizontalHeaderLabels(["Component", "Status"])
        status_table.horizontalHeader().setStretchLastSection(True)
        status_table.verticalHeader().setVisible(False)
        
        # Add some basic diagnostic entries
        diagnostics = [
            ("Cache Directory", "Checking..."),
            ("Network Connectivity", "Checking..."),
            ("API Connectivity", "Checking..."),
            ("Credentials", "Checking..."),
            ("Rate Limit Status", "Checking...")
        ]
        
        for row, (key, value) in enumerate(diagnostics):
            status_table.insertRow(row)
            status_table.setItem(row, 0, QTableWidgetItem(str(key)))
            status_table.setItem(row, 1, QTableWidgetItem(str(value)))
        
        diagnostic_layout.addWidget(status_table)
        self.tab_widget.addTab(diagnostic_widget, "Diagnostics")
        
        main_layout.addWidget(self.tab_widget)
        
        # Add buttons
        button_layout = QHBoxLayout()
        
        # Spacer to push buttons to the right
        button_layout.addStretch()
        
        # Details button
        self.details_button = QPushButton("Show Details")
        self.details_button.setCheckable(True)
        self.details_button.toggled.connect(self._toggle_details)
        button_layout.addWidget(self.details_button)
        
        # Cancel button
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)
        
        # Auto close checkbox
        self.auto_close_checkbox = QPushButton("Auto-Close on Success")
        self.auto_close_checkbox.setCheckable(True)
        self.auto_close_checkbox.setChecked(True)
        button_layout.addWidget(self.auto_close_checkbox)
        
        main_layout.addLayout(button_layout)
        
        # Set dialog layout
        self.setLayout(main_layout)
        
        # Initially hide details
        self.tab_widget.setVisible(False)
        self.resize(500, 200)
    
    def _toggle_details(self, checked):
        """Toggle the visibility of the details section."""
        if checked:
            self.details_button.setText("Hide Details")
            self.tab_widget.setVisible(True)
            if self.height() < 500:
                self.resize(700, 500)
        else:
            self.details_button.setText("Show Details")
            self.tab_widget.setVisible(False)
            self.resize(500, 200)
    
    def _update_elapsed_time(self):
        """Update the elapsed time display."""
        elapsed = time.time() - self.healing_start_time
        minutes = int(elapsed // 60)
        seconds = int(elapsed % 60)
        self.elapsed_label.setText(f"<b>Elapsed:</b> {minutes:02d}:{seconds:02d}")
    
    @Slot(str, int)
    def _on_new_log(self, message, level):
        """Handle new log messages."""
        # Add log to text edit with appropriate color
        if level >= logging.ERROR:
            color = "#FF5252"  # Red for errors
        elif level >= logging.WARNING:
            color = "#FFC107"  # Yellow for warnings
        elif level >= logging.INFO:
            color = "#FFFFFF"  # White for info
        else:
            color = "#AAAAAA"  # Gray for debug
        
        self.log_widget.append(f"<span style='color: {color}'>{message}</span>")
        
        # Autoscroll
        cursor = self.log_widget.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.log_widget.setTextCursor(cursor)
    
    def update_healing_progress(self, event_type, data):
        """Update healing progress based on events from DeepSeek."""
        if event_type == 'progress':
            # Update retry counter and progress
            self.current_retry = data.get('retry', self.current_retry)
            self.retry_label.setText(f"<b>Attempts:</b> {self.current_retry}/{self.max_retries}")
            
            # Calculate progress percentage
            progress_pct = min(100, int(self.current_retry * 100 / self.max_retries))
            self.progress_bar.setValue(progress_pct)
            
            # Add log entry
            logger.info(f"Recovery attempt {self.current_retry}/{self.max_retries}: "
                      f"Strategy: {data.get('strategy', 'Unknown')}, "
                      f"Backing off for {data.get('backoff', 0):.2f}s")
        
        elif event_type == 'success':
            # Success! Update UI
            self.healing_successful = True
            self.progress_bar.setValue(100)
            self.status_label.setText("<b>Status:</b> <span style='color: #4CAF50;'>Successful</span>")
            
            logger.info(f"Self-healing successful after {data.get('attempts', self.current_retry)} attempts.")
            
            # Enable close button
            self.cancel_button.setText("Close")
            
            # Auto-close if enabled
            if self.auto_close_checkbox.isChecked():
                QTimer.singleShot(3000, self.accept)
        
        elif event_type == 'failure':
            # Failed to heal, update UI
            self.progress_bar.setValue(100)
            self.status_label.setText("<b>Status:</b> <span style='color: #FF5252;'>Failed</span>")
            
            logger.error(f"Self-healing failed after {data.get('attempts', self.max_retries)} attempts.")
            
            # Enable close button
            self.cancel_button.setText("Close")
    
    def closeEvent(self, event):
        """Handle when dialog is closed."""
        # Stop the update timer
        if hasattr(self, 'update_timer') and self.update_timer.isActive():
            self.update_timer.stop()
        
        # Remove log handler
        root_logger = logging.getLogger()
        if self.log_handler in root_logger.handlers:
            root_logger.removeHandler(self.log_handler)
        
        # Accept the event
        event.accept()


class HealingManager:
    """
    Manager for self-healing processes.
    Displays and handles healing dialogs.
    """
    
    def __init__(self, parent=None):
        """Initialize healing manager."""
        self.parent = parent
        self.active_dialogs = {}
    
    def start_healing_process(self, error_type, context=None):
        """Start a healing process for the specified error type."""
        # Check if there's already a dialog for this error type
        if error_type in self.active_dialogs and self.active_dialogs[error_type].isVisible():
            # Just bring it to front
            self.active_dialogs[error_type].raise_()
            self.active_dialogs[error_type].activateWindow()
            return self.active_dialogs[error_type]
        
        # Create a new healing dialog
        dialog = HealingDialog(self.parent, error_type, context)
        self.active_dialogs[error_type] = dialog
        
        # Show the dialog (non-blocking)
        dialog.show()
        return dialog
    
    def update_healing_progress(self, error_type, event_type, data):
        """Update the healing progress for a specific error type."""
        if error_type in self.active_dialogs and self.active_dialogs[error_type].isVisible():
            self.active_dialogs[error_type].update_healing_progress(event_type, data)


# Test function
def main():
    """Run a standalone test of the healing dialog"""
    import sys
    from PySide6.QtWidgets import QApplication
    
    app = QApplication(sys.argv)
    
    # Create a healing dialog
    context = {
        'strategy': 'Exponential backoff with jitter',
        'max_retries': 5,
        'description': 'Recovering from API rate limit exceeded error. The system will automatically retry with increasing delays.',
        'file': 'example.py',
        'endpoint': '/v1/chat/completions',
        'status_code': 429
    }
    
    dialog = HealingDialog(None, "RATE_LIMIT", context)
    
    # Simulate some healing events
    def simulate_progress():
        import random
        retries = context['max_retries']
        
        # Log some diagnostic info
        logger.debug("Checking system connectivity...")
        logger.info("Network connection verified. Latency: 45ms")
        logger.warning("API rate limits approaching threshold (80% used)")
        
        # Simulate progress updates
        for i in range(1, retries + 1):
            QTimer.singleShot(i * 2000, lambda i=i: dialog.update_healing_progress('progress', {
                'retry': i,
                'strategy': context['strategy'],
                'backoff': i * 1.5 + random.random() * 0.5
            }))
        
        # Simulate success after last retry
        QTimer.singleShot((retries + 1) * 2000, lambda: dialog.update_healing_progress('success', {
            'attempts': retries
        }))
    
    # Start simulation after a short delay
    QTimer.singleShot(1000, simulate_progress)
    
    dialog.exec()
    sys.exit(0)

if __name__ == "__main__":
    main() 