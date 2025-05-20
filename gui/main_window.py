import os
import sys
import time
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QLabel, QPushButton, QFileDialog, QComboBox,
    QTabWidget, QLineEdit, QMessageBox, QProgressBar, QToolBar,
    QStatusBar, QTreeView, QMenu, QDockWidget, QTextEdit, QTableWidget,
    QTableWidgetItem, QHeaderView, QDialog, QFormLayout, QDialogButtonBox
)
from PySide6.QtCore import Qt, QSize, Signal, Slot, QThread, QTimer, QDir, QModelIndex
from PySide6.QtGui import QIcon, QAction, QStandardItemModel, QStandardItem, QColor, QFont
import yaml

import matplotlib
matplotlib.use('Qt5Agg')
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import numpy as np

from core.analyzer import AnalyzerEngine
from gui.live_monitor import LiveMonitorWidget
from gui.graph_map import GraphMapWidget
from gui.file_inspector import FileInspectorWidget
from gui.healing_dialog import HealingManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('SpecterWire.GUI')

class SettingsDialog(QDialog):
    apiKeyChanged = Signal(str)
    def __init__(self, parent=None, current_key=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        layout = QFormLayout(self)
        self.api_key_input = QLineEdit(self)
        self.api_key_input.setEchoMode(QLineEdit.Password)
        if current_key:
            self.api_key_input.setText(current_key)
        layout.addRow("DeepSeek API Key:", self.api_key_input)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.setLayout(layout)
        buttons.accepted.connect(self._on_accept)
    def _on_accept(self):
        key = self.api_key_input.text().strip()
        if key:
            self.apiKeyChanged.emit(key)

class MainWindow(QMainWindow):
    """Main application window for SpecterWire"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__()
        
        self.config = config
        self.setWindowTitle("SpecterWire Analyst")
        self.resize(1280, 800)
        
        # Create healing manager
        self.healing_manager = HealingManager(self)
        
        # Initialize analyzer engine
        self.analyzer = AnalyzerEngine(config.get('analyzer_config', {}))
        
        # Set up callback functions for analyzer progress
        self.analyzer.set_callbacks(
            progress_callback=self._on_scan_progress,
            result_callback=self._on_scan_result
        )
        
        # Register healing callback with DeepSeek engine
        self._register_healing_callbacks()
        
        # Set up UI
        self._setup_ui()
        
        # Start analyzer thread
        self.analyzer_thread = self.analyzer.start_scanning_thread()
        
        # Status update timer
        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self._update_status)
        self.status_timer.start(1000)  # Update every second
        
        logger.info("Main window initialized")
    
    def _register_healing_callbacks(self):
        """Register healing callbacks with the DeepSeek engine."""
        try:
            # Get reference to DeepSeek engine
            deepseek = self.analyzer.deepseek
            
            # Set healing callback
            deepseek.set_healing_callback(self._on_healing_event)
            
            logger.info("Registered healing callbacks with DeepSeek engine")
        except Exception as e:
            logger.error(f"Failed to register healing callbacks: {str(e)}")
    
    def _on_healing_event(self, event_type, data):
        """Handle healing events from DeepSeek engine."""
        # Extract error type from data
        error_type = data.get('error_type', 'UNKNOWN_ERROR')
        
        # Use QTimer.singleShot to ensure GUI operations happen in the main thread
        QTimer.singleShot(0, lambda: self._process_healing_event(event_type, error_type, data))
    
    def _process_healing_event(self, event_type, error_type, data):
        """Process healing events in the main thread."""
        if event_type == 'start':
            # Start a new healing process dialog
            context = {
                'strategy': data.get('strategy', 'Standard recovery'),
                'max_retries': data.get('max_retries', 3),
                'description': f"DeepSeek encountered an error and is attempting to self-heal: {error_type}",
                'timestamp': data.get('timestamp', time.time())
            }
            
            # Add any additional error details
            if 'exception' in data:
                context['error'] = data['exception']
            
            # Start dialog - this returns immediately as dialog is shown non-blocking
            self.healing_manager.start_healing_process(error_type, context)
            
            # Log the healing attempt
            self.live_monitor.add_log_entry(
                f"Self-healing initiated for {error_type}",
                severity="WARNING"
            )
        
        elif event_type in ['progress', 'success', 'failure']:
            # Update existing dialog
            self.healing_manager.update_healing_progress(error_type, event_type, data)
            
            # Log the progress
            if event_type == 'progress':
                retry = data.get('retry', 0)
                max_retries = data.get('max_retries', 3)
                self.live_monitor.add_log_entry(
                    f"Self-healing {error_type}: attempt {retry}/{max_retries}",
                    severity="INFO"
                )
            elif event_type == 'success':
                self.live_monitor.add_log_entry(
                    f"Self-healing {error_type}: successful recovery",
                    severity="SUCCESS"
                )
            elif event_type == 'failure':
                self.live_monitor.add_log_entry(
                    f"Self-healing {error_type}: failed after {data.get('attempts', 0)} attempts",
                    severity="ERROR"
                )
    
    def _setup_ui(self):
        """Set up the main UI components"""
        # Set dark theme palette
        self._setup_dark_theme()
        
        # Create central widget with layout
        central_widget = QWidget()
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        self.setCentralWidget(central_widget)
        
        # Create toolbar
        self._create_toolbar()
        
        # Create main splitter
        self.main_splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(self.main_splitter)
        
        # Left panel - File browser and controls
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        
        # File controls
        file_controls = QWidget()
        file_layout = QHBoxLayout(file_controls)
        self.directory_input = QLineEdit()
        self.directory_input.setPlaceholderText("Directory path...")
        browse_button = QPushButton("Browse")
        browse_button.clicked.connect(self._browse_directory)
        scan_button = QPushButton("Scan")
        scan_button.clicked.connect(self._start_scan)
        file_layout.addWidget(self.directory_input)
        file_layout.addWidget(browse_button)
        file_layout.addWidget(scan_button)
        left_layout.addWidget(file_controls)
        
        # File tree
        self.file_tree = QTreeView()
        self.file_model = QStandardItemModel()
        self.file_model.setHorizontalHeaderLabels(["File", "Status", "Score"])
        self.file_tree.setModel(self.file_model)
        self.file_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.file_tree.customContextMenuRequested.connect(self._show_context_menu)
        self.file_tree.clicked.connect(self._on_tree_item_clicked)
        left_layout.addWidget(self.file_tree)
        
        # Add left panel to splitter
        self.main_splitter.addWidget(left_panel)
        
        # Right panel - Tab widget for different views
        self.tab_widget = QTabWidget()
        
        # Dashboard tab
        self.dashboard_widget = QWidget()
        dashboard_layout = QVBoxLayout(self.dashboard_widget)
        
        # Status overview
        status_frame = QWidget()
        status_layout = QHBoxLayout(status_frame)
        
        # Stat boxes
        self.stats_widgets = {}
        for stat_name in ["Files Scanned", "Anomalies Found", "Scan Time", "Avg. Score"]:
            stat_widget = QWidget()
            stat_layout = QVBoxLayout(stat_widget)
            stat_label = QLabel(stat_name)
            stat_label.setAlignment(Qt.AlignCenter)
            stat_value = QLabel("0")
            stat_value.setAlignment(Qt.AlignCenter)
            stat_layout.addWidget(stat_label)
            stat_layout.addWidget(stat_value)
            status_layout.addWidget(stat_widget)
            self.stats_widgets[stat_name] = stat_value
        
        dashboard_layout.addWidget(status_frame)
        
        # Create progress section
        progress_frame = QWidget()
        progress_layout = QVBoxLayout(progress_frame)
        progress_label = QLabel("Scan Progress")
        self.progress_bar = QProgressBar()
        self.progress_status = QLabel("Ready")
        progress_layout.addWidget(progress_label)
        progress_layout.addWidget(self.progress_bar)
        progress_layout.addWidget(self.progress_status)
        dashboard_layout.addWidget(progress_frame)
        
        # Create graph area
        self.plot_canvas = self._create_plot_canvas()
        dashboard_layout.addWidget(self.plot_canvas)
        
        # Add dashboard to tabs
        self.tab_widget.addTab(self.dashboard_widget, "Dashboard")
        
        # Live Monitor tab
        self.live_monitor = LiveMonitorWidget(config=self.config)
        self.tab_widget.addTab(self.live_monitor, "Live Monitor")
        
        # File Inspector tab
        self.file_inspector = FileInspectorWidget()
        self.tab_widget.addTab(self.file_inspector, "File Inspector")
        
        # Graph Network tab
        self.graph_map = GraphMapWidget()
        self.tab_widget.addTab(self.graph_map, "Graph Network")
        
        # Add tab widget to splitter
        self.main_splitter.addWidget(self.tab_widget)
        
        # Set splitter sizes
        self.main_splitter.setSizes([300, 700])
        
        # Create status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_message = QLabel("Ready")
        self.status_bar.addWidget(self.status_message)
        self.task_counter = QLabel("Tasks: 0 active, 0 completed")
        self.status_bar.addPermanentWidget(self.task_counter)
    
    def _create_toolbar(self):
        """Create the main toolbar"""
        self.toolbar = QToolBar("Main Toolbar")
        self.toolbar.setMovable(False)
        self.toolbar.setIconSize(QSize(24, 24))
        self.addToolBar(self.toolbar)
        
        # Add actions
        scan_action = QAction("Scan Directory", self)
        scan_action.triggered.connect(self._browse_directory)
        self.toolbar.addAction(scan_action)
        
        scan_file_action = QAction("Scan File", self)
        scan_file_action.triggered.connect(self._browse_file)
        self.toolbar.addAction(scan_file_action)
        
        self.toolbar.addSeparator()
        
        settings_action = QAction("Settings", self)
        settings_action.triggered.connect(self._show_settings)
        self.toolbar.addAction(settings_action)
        
        export_action = QAction("Export Results", self)
        export_action.triggered.connect(self._export_results)
        self.toolbar.addAction(export_action)
        
        self.toolbar.addSeparator()
        
        about_action = QAction("About", self)
        about_action.triggered.connect(self._show_about)
        self.toolbar.addAction(about_action)
    
    def _setup_dark_theme(self):
        """Set up dark theme color palette"""
        app = QApplication.instance()
        app.setStyle("Fusion")
        
        dark_palette = app.palette()
        
        # Set dark theme colors
        dark_palette.setColor(dark_palette.ColorRole.Window, QColor(53, 53, 53))
        dark_palette.setColor(dark_palette.ColorRole.WindowText, QColor(230, 230, 230))
        dark_palette.setColor(dark_palette.ColorRole.Base, QColor(42, 42, 42))
        dark_palette.setColor(dark_palette.ColorRole.AlternateBase, QColor(66, 66, 66))
        dark_palette.setColor(dark_palette.ColorRole.ToolTipBase, QColor(53, 53, 53))
        dark_palette.setColor(dark_palette.ColorRole.ToolTipText, QColor(230, 230, 230))
        dark_palette.setColor(dark_palette.ColorRole.Text, QColor(230, 230, 230))
        dark_palette.setColor(dark_palette.ColorRole.Button, QColor(53, 53, 53))
        dark_palette.setColor(dark_palette.ColorRole.ButtonText, QColor(230, 230, 230))
        dark_palette.setColor(dark_palette.ColorRole.BrightText, QColor(255, 255, 255))
        dark_palette.setColor(dark_palette.ColorRole.Link, QColor(42, 130, 218))
        dark_palette.setColor(dark_palette.ColorRole.Highlight, QColor(42, 130, 218))
        dark_palette.setColor(dark_palette.ColorRole.HighlightedText, QColor(0, 0, 0))
        
        app.setPalette(dark_palette)
    
    def _create_plot_canvas(self):
        """Create a matplotlib canvas for dashboard visualizations"""
        fig = Figure(figsize=(5, 4), dpi=100)
        fig.subplots_adjust(left=0.1, right=0.9, top=0.9, bottom=0.1)
        canvas = FigureCanvas(fig)
        canvas.setStyleSheet("background-color: #2e2e2e;")
        fig.patch.set_facecolor('#2e2e2e')
        
        # Create initial plot
        self.ax = fig.add_subplot(111)
        self.ax.set_facecolor('#1e1e1e')
        
        # No data initially
        self.ax.text(0.5, 0.5, "No data available", 
                    horizontalalignment='center',
                    verticalalignment='center',
                    transform=self.ax.transAxes,
                    color='#aaaaaa',
                    fontsize=12)
        
        # Clear ticks for empty plot
        self.ax.set_xticks([])
        self.ax.set_yticks([])
        
        # Style grid and spines
        self.ax.spines['top'].set_color('#555555')
        self.ax.spines['right'].set_color('#555555')
        self.ax.spines['bottom'].set_color('#555555')
        self.ax.spines['left'].set_color('#555555')
        
        fig.tight_layout()
        canvas.draw()
        
        return canvas
    
    def _update_plot(self, data=None):
        """Update the dashboard plot with new data"""
        if not data or len(data) < 2:
            return
            
        self.ax.clear()
        self.ax.set_facecolor('#1e1e1e')
        
        # Extract data
        labels = [d.get('file_type', 'unknown') for d in data]
        scores = [d.get('anomaly_score', 0) for d in data]
        sizes = [d.get('size', 1) for d in data]
        
        # Normalize sizes for scatter plot
        if sum(sizes) > 0:
            norm_sizes = [50 * (s / max(sizes)) + 10 for s in sizes]
        else:
            norm_sizes = [30] * len(sizes)
            
        # Create color map based on scores
        colors = []
        for score in scores:
            if score < 0.3:
                colors.append('#4CAF50')  # Green for low scores
            elif score < 0.7:
                colors.append('#FFC107')  # Yellow for medium scores
            else:
                colors.append('#F44336')  # Red for high scores
        
        # Create scatter plot
        x = np.random.rand(len(labels))
        y = np.random.rand(len(labels))
        
        scatter = self.ax.scatter(x, y, s=norm_sizes, c=colors, alpha=0.6)
        
        # Style plot
        self.ax.set_title('File Analysis Overview', color='#cccccc')
        self.ax.set_xticks([])
        self.ax.set_yticks([])
        self.ax.spines['top'].set_visible(False)
        self.ax.spines['right'].set_visible(False)
        self.ax.spines['bottom'].set_visible(False)
        self.ax.spines['left'].set_visible(False)
        
        # Update canvas
        self.plot_canvas.draw()
    
    def _browse_directory(self):
        """Open directory browser dialog"""
        directory = QFileDialog.getExistingDirectory(
            self, "Select Directory to Scan", 
            os.path.expanduser("~")
        )
        
        if directory:
            self.directory_input.setText(directory)
    
    def _browse_file(self):
        """Open file browser dialog"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select File to Scan",
            os.path.expanduser("~"),
            "All Files (*)"
        )
        
        if file_path:
            self._scan_single_file(file_path)
    
    def _start_scan(self):
        """Start directory scan"""
        directory = self.directory_input.text()
        if not directory:
            QMessageBox.warning(self, "Warning", "Please select a directory to scan.")
            return
            
        if not os.path.exists(directory):
            QMessageBox.warning(self, "Warning", "Directory does not exist.")
            return
        
        # Clear previous results
        self.file_model.clear()
        self.file_model.setHorizontalHeaderLabels(["File", "Status", "Score"])
        
        # Reset status
        self.progress_bar.setValue(0)
        self.progress_status.setText("Starting scan...")
        
        # Start recursive scan
        task_id = self.analyzer.scan_directory(directory, recursive=True)
        
        # Add root item to tree
        root_item = QStandardItem(directory)
        self.file_model.appendRow(root_item)
        
        # Update status
        self.status_message.setText(f"Scanning directory: {directory}")
        
        # Log scan start
        self.live_monitor.add_log_entry(f"Started scan of directory: {directory}")
    
    def _scan_single_file(self, file_path):
        """Scan a single file"""
        if not os.path.exists(file_path) or not os.path.isfile(file_path):
            QMessageBox.warning(self, "Warning", "File does not exist or is not a regular file.")
            return
        
        # Start scan
        task_id = self.analyzer.scan_file(file_path)
        
        # Update status
        self.status_message.setText(f"Scanning file: {file_path}")
        
        # Log scan start
        self.live_monitor.add_log_entry(f"Started scan of file: {file_path}")
    
    def _on_scan_progress(self, event_type, data):
        """Handle scan progress updates from analyzer"""
        if event_type == 'start':
            self.progress_bar.setMaximum(data.get('total_files', 100))
            self.progress_bar.setValue(0)
            self.progress_status.setText(f"Scanning {data.get('total_files', 0)} files...")
            
        elif event_type == 'progress':
            self.progress_bar.setValue(data.get('processed', 0))
            current_file = data.get('current_file', '')
            self.progress_status.setText(f"Scanning: {os.path.basename(current_file)}")
            
            # Log progress periodically
            if data.get('processed', 0) % 10 == 0:
                self.live_monitor.add_log_entry(
                    f"Progress: {data.get('processed', 0)}/{data.get('total', 0)} files"
                )
            
        elif event_type == 'complete':
            self.progress_bar.setValue(data.get('processed_files', 0))
            duration = data.get('duration', 0)
            self.progress_status.setText(
                f"Scan completed. Processed {data.get('processed_files', 0)} files in {duration:.2f}s"
            )
            
            # Update stats
            self.stats_widgets["Files Scanned"].setText(str(data.get('processed_files', 0)))
            self.stats_widgets["Scan Time"].setText(f"{duration:.2f}s")
            
            # Log completion
            self.live_monitor.add_log_entry(
                f"Scan completed. Processed {data.get('processed_files', 0)} files in {duration:.2f} seconds."
            )
    
    def _on_scan_result(self, result):
        """Handle individual file scan results"""
        # Log the result
        score = result.anomaly_score
        severity = "HIGH" if score > 0.7 else "MEDIUM" if score > 0.3 else "LOW"
        self.live_monitor.add_log_entry(
            f"File: {result.path}, Score: {score:.2f}, Severity: {severity}",
            severity=severity
        )
        
        # Add to tree view
        self._add_result_to_tree(result)
        
        # Count anomalies
        if score > 0.5:  # Threshold for counting as anomaly
            current_count = int(self.stats_widgets["Anomalies Found"].text())
            self.stats_widgets["Anomalies Found"].setText(str(current_count + 1))
        
        # Update average score
        current_files = int(self.stats_widgets["Files Scanned"].text())
        if current_files > 0:
            current_avg = float(self.stats_widgets["Avg. Score"].text() or "0")
            new_avg = ((current_avg * (current_files - 1)) + score) / current_files
            self.stats_widgets["Avg. Score"].setText(f"{new_avg:.2f}")
        else:
            self.stats_widgets["Avg. Score"].setText(f"{score:.2f}")
        
        # Update plot occasionally
        if current_files % 5 == 0:
            # Get latest results for plotting
            completed_tasks = self.analyzer.get_completed_tasks()
            plot_data = []
            for task_id in completed_tasks:
                task_status = self.analyzer.get_task_status(task_id)
                if task_status and task_status.get('result'):
                    result_data = task_status['result']
                    if isinstance(result_data, dict) and 'results' not in result_data:
                        plot_data.append(result_data)
            
            self._update_plot(plot_data)
    
    def _add_result_to_tree(self, result):
        """Add scan result to the file tree view"""
        path = result.path
        relative_path = os.path.dirname(path)
        filename = os.path.basename(path)
        
        # Find or create parent path items
        parent_item = self.file_model.invisibleRootItem()
        
        # Create items for the file
        file_item = QStandardItem(filename)
        status_item = QStandardItem("Scanned")
        
        # Format score with color based on value
        score = result.anomaly_score
        score_text = f"{score:.2f}"
        score_item = QStandardItem(score_text)
        
        # Set color based on score
        if score > 0.7:
            score_item.setForeground(QColor(244, 67, 54))  # Red
        elif score > 0.3:
            score_item.setForeground(QColor(255, 193, 7))  # Yellow
        else:
            score_item.setForeground(QColor(76, 175, 80))  # Green
        
        # Store result data in the item
        file_item.setData(result.to_dict(), Qt.UserRole)
        
        # Add to model
        row = [file_item, status_item, score_item]
        parent_item.appendRow(row)
        
        # Adjust column widths
        self.file_tree.resizeColumnToContents(0)
        self.file_tree.resizeColumnToContents(1)
        self.file_tree.resizeColumnToContents(2)
    
    def _on_tree_item_clicked(self, index):
        """Handle clicking on a file in the tree view"""
        # Get item data
        file_item = self.file_model.itemFromIndex(index)
        if not file_item:
            return
            
        row = file_item.row()
        file_item = self.file_model.item(row, 0)
        if not file_item:
            return
            
        # Get result data
        result_data = file_item.data(Qt.UserRole)
        if not result_data:
            return
        
        # Switch to File Inspector tab
        self.tab_widget.setCurrentWidget(self.file_inspector)
        
        # Load file in inspector
        self.file_inspector.load_file(result_data)
        
        # Log the action
        self.live_monitor.add_log_entry(f"Inspecting file: {result_data.get('path', '')}")
    
    def _show_context_menu(self, position):
        """Show context menu for file tree items"""
        index = self.file_tree.indexAt(position)
        if not index.isValid():
            return
            
        # Get item data
        file_item = self.file_model.itemFromIndex(index)
        if not file_item:
            return
            
        row = file_item.row()
        file_item = self.file_model.item(row, 0)
        if not file_item:
            return
            
        # Get result data
        result_data = file_item.data(Qt.UserRole)
        if not result_data:
            return
        
        # Create context menu
        menu = QMenu()
        inspect_action = menu.addAction("Inspect File")
        menu.addSeparator()
        copy_path_action = menu.addAction("Copy Path")
        
        # Show menu and handle actions
        action = menu.exec(self.file_tree.viewport().mapToGlobal(position))
        
        if action == inspect_action:
            # Switch to File Inspector tab
            self.tab_widget.setCurrentWidget(self.file_inspector)
            
            # Load file in inspector
            self.file_inspector.load_file(result_data)
            
        elif action == copy_path_action:
            # Copy file path to clipboard
            path = result_data.get('path', '')
            if path:
                QApplication.clipboard().setText(path)
    
    def _update_status(self):
        """Update status bar with current analyzer state"""
        active_tasks = self.analyzer.get_active_tasks()
        completed_tasks = self.analyzer.get_completed_tasks()
        
        self.task_counter.setText(f"Tasks: {len(active_tasks)} active, {len(completed_tasks)} completed")
    
    def _show_settings(self):
        """Show settings dialog for API key management"""
        current_key = self.config.get('analyzer_config', {}).get('deepseek_config', {}).get('api_key', '')
        dlg = SettingsDialog(self, current_key)
        dlg.apiKeyChanged.connect(self._update_api_key)
        if dlg.exec() == QDialog.Accepted:
            pass  # Already handled by signal
    def _update_api_key(self, new_key):
        # Update in-memory config
        self.config['analyzer_config']['deepseek_config']['api_key'] = new_key
        # Persist to YAML file
        settings_path = os.path.join(os.path.dirname(__file__), '../config/settings.yml')
        os.makedirs(os.path.dirname(settings_path), exist_ok=True)
        with open(settings_path, 'w') as f:
            yaml.dump({'deepseek_api_key': new_key}, f)
        QMessageBox.information(self, "Settings", "API key updated. Please restart the application for changes to take effect.")
    
    def _export_results(self):
        """Export scan results"""
        # Placeholder - would implement export functionality
        QMessageBox.information(self, "Export", "Export functionality would be implemented here.")
    
    def _show_about(self):
        """Show about dialog"""
        QMessageBox.about(self, "About SpecterWire",
            "<h2>SpecterWire Analyst</h2>"
            "<p>Version 1.0</p>"
            "<p>Powerful file analysis and anomaly detection tool.</p>"
            "<p><b>Watch what no one else can see.</b></p>"
        )
    
    def closeEvent(self, event):
        """Handle window close event"""
        # Clean up live monitor resources
        if hasattr(self, 'live_monitor'):
            self.live_monitor.cleanup()
            
        # Clean up graph map resources
        if hasattr(self, 'graph_map'):
            self.graph_map.cleanup()
            
        # Clean up file inspector resources
        if hasattr(self, 'file_inspector'):
            self.file_inspector.cleanup()
            
        # Stop status update timer
        if hasattr(self, 'status_timer') and self.status_timer.isActive():
            self.status_timer.stop()
            
        # Stop analyzer thread
        self.analyzer.stop_scanning_thread()
        
        # Accept the close event
        event.accept()


# Standalone test function
def main():
    """Run the main application"""
    app = QApplication(sys.argv)
    
    # Basic configuration
    config = {
        'analyzer_config': {
            'max_workers': 4,
            'max_file_size': 100 * 1024 * 1024,  # 100MB
            'deepseek_config': {
                'use_offline_mode': True
            }
        }
    }
    
    window = MainWindow(config)
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main() 