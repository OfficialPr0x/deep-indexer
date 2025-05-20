import os
import time
import json
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, 
    QLabel, QTextEdit, QSplitter, QPushButton, 
    QTreeWidget, QTreeWidgetItem, QProgressBar,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QFileDialog, QMessageBox, QComboBox, QScrollArea
)
from PySide6.QtCore import Qt, Signal, Slot, QThread, QTimer, QSize
from PySide6.QtGui import QColor, QFont, QTextCursor, QPixmap, QIcon

import matplotlib
matplotlib.use('Qt5Agg')
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import numpy as np

class FileInspectorWidget(QWidget):
    """
    Detailed file inspector widget for examining file properties and analysis results
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Current file data
        self.current_file = None
        
        # Setup UI
        self._setup_ui()
    
    def _setup_ui(self):
        """Set up the UI components"""
        main_layout = QVBoxLayout(self)
        
        # File info header
        self.file_header = QWidget()
        header_layout = QHBoxLayout(self.file_header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        
        # File icon and name
        self.file_icon = QLabel()
        self.file_icon.setFixedSize(QSize(32, 32))
        self.file_name = QLabel("No file selected")
        self.file_name.setStyleSheet("font-weight: bold; font-size: 14px;")
        
        # File path
        self.file_path = QLabel("")
        self.file_path.setStyleSheet("color: #aaaaaa;")
        
        # File score
        self.file_score_label = QLabel("Score:")
        self.file_score = QLabel("N/A")
        self.file_score.setStyleSheet("font-weight: bold;")
        
        # Add to header layout
        header_layout.addWidget(self.file_icon)
        header_layout.addWidget(self.file_name, 0)
        header_layout.addStretch(1)
        header_layout.addWidget(self.file_path, 2)
        header_layout.addStretch(1)
        header_layout.addWidget(self.file_score_label)
        header_layout.addWidget(self.file_score)
        
        # Add header to main layout
        main_layout.addWidget(self.file_header)
        
        # Tab widget for different views
        self.tab_widget = QTabWidget()
        
        # Overview tab
        self.overview_tab = QWidget()
        self._setup_overview_tab()
        self.tab_widget.addTab(self.overview_tab, "Overview")
        
        # Details tab
        self.details_tab = QWidget()
        self._setup_details_tab()
        self.tab_widget.addTab(self.details_tab, "Details")
        
        # Hex View tab
        self.hex_tab = QWidget()
        self._setup_hex_tab()
        self.tab_widget.addTab(self.hex_tab, "Hex View")
        
        # Content tab
        self.content_tab = QWidget()
        self._setup_content_tab()
        self.tab_widget.addTab(self.content_tab, "Content")
        
        # Analysis tab
        self.analysis_tab = QWidget()
        self._setup_analysis_tab()
        self.tab_widget.addTab(self.analysis_tab, "Analysis")
        
        # Add tab widget to main layout
        main_layout.addWidget(self.tab_widget, 1)
        
        # Button row at the bottom
        button_layout = QHBoxLayout()
        self.export_button = QPushButton("Export Report")
        self.export_button.clicked.connect(self._export_report)
        self.rescan_button = QPushButton("Rescan")
        self.rescan_button.clicked.connect(self._rescan_file)
        
        button_layout.addStretch()
        button_layout.addWidget(self.export_button)
        button_layout.addWidget(self.rescan_button)
        
        main_layout.addLayout(button_layout)
    
    def _setup_overview_tab(self):
        """Set up the overview tab"""
        layout = QVBoxLayout(self.overview_tab)
        
        # Top section with file summary
        summary_widget = QWidget()
        summary_layout = QHBoxLayout(summary_widget)
        
        # Basic properties
        props_widget = QWidget()
        props_layout = QVBoxLayout(props_widget)
        props_layout.setContentsMargins(0, 0, 0, 0)
        
        # File properties table
        self.props_table = QTableWidget(5, 2)
        self.props_table.setHorizontalHeaderLabels(["Property", "Value"])
        self.props_table.verticalHeader().setVisible(False)
        self.props_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.props_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.props_table.setShowGrid(False)
        self.props_table.setAlternatingRowColors(True)
        self.props_table.setEditTriggers(QTableWidget.NoEditTriggers)
        
        # Set initial data
        self._set_table_item(self.props_table, 0, 0, "Size")
        self._set_table_item(self.props_table, 0, 1, "")
        self._set_table_item(self.props_table, 1, 0, "Type")
        self._set_table_item(self.props_table, 1, 1, "")
        self._set_table_item(self.props_table, 2, 0, "Modified")
        self._set_table_item(self.props_table, 2, 1, "")
        self._set_table_item(self.props_table, 3, 0, "Entropy")
        self._set_table_item(self.props_table, 3, 1, "")
        self._set_table_item(self.props_table, 4, 0, "Anomaly Score")
        self._set_table_item(self.props_table, 4, 1, "")
        
        props_layout.addWidget(self.props_table)
        
        # Entropy chart
        self.entropy_widget = QWidget()
        entropy_layout = QVBoxLayout(self.entropy_widget)
        
        entropy_label = QLabel("Entropy Distribution")
        entropy_label.setAlignment(Qt.AlignCenter)
        
        # Create matplotlib figure for entropy
        self.entropy_figure = Figure(figsize=(5, 3), dpi=100)
        self.entropy_canvas = FigureCanvas(self.entropy_figure)
        self.entropy_canvas.setStyleSheet("background-color: #2e2e2e;")
        self.entropy_figure.patch.set_facecolor('#2e2e2e')
        
        self.entropy_ax = self.entropy_figure.add_subplot(111)
        self.entropy_ax.set_facecolor('#1e1e1e')
        self._setup_empty_entropy_plot()
        
        entropy_layout.addWidget(entropy_label)
        entropy_layout.addWidget(self.entropy_canvas)
        
        # Add widgets to summary layout
        summary_layout.addWidget(props_widget, 1)
        summary_layout.addWidget(self.entropy_widget, 1)
        
        # Tags section
        tags_widget = QWidget()
        tags_layout = QVBoxLayout(tags_widget)
        
        tags_header = QLabel("Tags")
        self.tags_list = QTextEdit()
        self.tags_list.setReadOnly(True)
        self.tags_list.setMaximumHeight(80)
        
        tags_layout.addWidget(tags_header)
        tags_layout.addWidget(self.tags_list)
        
        # Add all sections to main layout
        layout.addWidget(summary_widget)
        layout.addWidget(tags_widget)
        
        # Anomaly details section
        anomaly_widget = QWidget()
        anomaly_layout = QVBoxLayout(anomaly_widget)
        
        anomaly_header = QLabel("Anomaly Details")
        self.anomaly_details = QTextEdit()
        self.anomaly_details.setReadOnly(True)
        
        anomaly_layout.addWidget(anomaly_header)
        anomaly_layout.addWidget(self.anomaly_details)
        
        layout.addWidget(anomaly_widget)
    
    def _setup_details_tab(self):
        """Set up the details tab with tree view of all properties"""
        layout = QVBoxLayout(self.details_tab)
        
        # Create tree widget
        self.details_tree = QTreeWidget()
        self.details_tree.setHeaderLabels(["Property", "Value"])
        self.details_tree.setAlternatingRowColors(True)
        self.details_tree.setAnimated(True)
        
        layout.addWidget(self.details_tree)
    
    def _setup_hex_tab(self):
        """Set up hex view tab"""
        layout = QVBoxLayout(self.hex_tab)
        
        # Controls for hex view
        controls_layout = QHBoxLayout()
        
        offset_label = QLabel("Offset:")
        self.offset_combo = QComboBox()
        self.offset_combo.addItems(["Hexadecimal", "Decimal"])
        self.offset_combo.currentTextChanged.connect(self._update_hex_view)
        
        width_label = QLabel("Width:")
        self.width_combo = QComboBox()
        self.width_combo.addItems(["16 bytes", "8 bytes", "4 bytes"])
        self.width_combo.currentTextChanged.connect(self._update_hex_view)
        
        controls_layout.addWidget(offset_label)
        controls_layout.addWidget(self.offset_combo)
        controls_layout.addWidget(width_label)
        controls_layout.addWidget(self.width_combo)
        controls_layout.addStretch()
        
        # Hex editor view
        self.hex_view = QTextEdit()
        self.hex_view.setReadOnly(True)
        self.hex_view.setStyleSheet("""
            QTextEdit {
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 10pt;
                background-color: #1a1a1a;
                color: white;
            }
        """)
        
        layout.addLayout(controls_layout)
        layout.addWidget(self.hex_view)
    
    def _setup_content_tab(self):
        """Set up content view tab"""
        layout = QVBoxLayout(self.content_tab)
        
        # Text view for file content
        self.content_view = QTextEdit()
        self.content_view.setReadOnly(True)
        self.content_view.setStyleSheet("""
            QTextEdit {
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 10pt;
                background-color: #1a1a1a;
                color: white;
            }
        """)
        
        layout.addWidget(self.content_view)
    
    def _setup_analysis_tab(self):
        """Set up analysis tab"""
        layout = QVBoxLayout(self.analysis_tab)
        
        # DeepSeek analysis tree
        self.analysis_tree = QTreeWidget()
        self.analysis_tree.setHeaderLabels(["Analysis", "Result"])
        self.analysis_tree.setAlternatingRowColors(True)
        self.analysis_tree.setAnimated(True)
        
        layout.addWidget(self.analysis_tree)
    
    def _setup_empty_entropy_plot(self):
        """Set up empty entropy plot"""
        self.entropy_ax.clear()
        self.entropy_ax.set_facecolor('#1e1e1e')
        
        self.entropy_ax.text(0.5, 0.5, "No entropy data",
                           horizontalalignment='center',
                           verticalalignment='center',
                           transform=self.entropy_ax.transAxes,
                           color='#aaaaaa',
                           fontsize=10)
        
        self.entropy_ax.set_xticks([])
        self.entropy_ax.set_yticks([])
        
        self.entropy_figure.tight_layout()
        self.entropy_canvas.draw()
    
    def _set_table_item(self, table, row, col, text):
        """Helper to set table items"""
        item = QTableWidgetItem(str(text))
        table.setItem(row, col, item)
    
    def load_file(self, file_data: Dict[str, Any]):
        """
        Load file data into the inspector
        
        Args:
            file_data: Dictionary with file analysis data
        """
        self.current_file = file_data
        
        # Update header information
        file_path = file_data.get('path', '')
        self.file_name.setText(os.path.basename(file_path))
        self.file_path.setText(file_path)
        
        # Set score with color
        score = file_data.get('anomaly_score', 0)
        self.file_score.setText(f"{score:.2f}")
        
        if score > 0.7:
            self.file_score.setStyleSheet("font-weight: bold; color: #F44336;")  # Red
        elif score > 0.3:
            self.file_score.setStyleSheet("font-weight: bold; color: #FFC107;")  # Yellow
        else:
            self.file_score.setStyleSheet("font-weight: bold; color: #4CAF50;")  # Green
        
        # Update overview tab
        self._update_overview()
        
        # Update details tab
        self._update_details()
        
        # Update hex tab
        self._update_hex_view()
        
        # Update content tab
        self._update_content()
        
        # Update analysis tab
        self._update_analysis()
    
    def _update_overview(self):
        """Update overview tab with file data"""
        if not self.current_file:
            return
        
        # Update properties table
        file_size = self.current_file.get('size', 0)
        self._set_table_item(self.props_table, 0, 1, self._format_size(file_size))
        
        file_type = self.current_file.get('file_type', 'unknown')
        self._set_table_item(self.props_table, 1, 1, file_type)
        
        # Last modified time (get from file if available)
        timestamp = self.current_file.get('timestamp', 0)
        modified_time = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
        self._set_table_item(self.props_table, 2, 1, modified_time)
        
        # Entropy
        entropy = self.current_file.get('entropy', 0)
        self._set_table_item(self.props_table, 3, 1, f"{entropy:.4f}")
        
        # Anomaly score
        score = self.current_file.get('anomaly_score', 0)
        self._set_table_item(self.props_table, 4, 1, f"{score:.4f}")
        
        # Update entropy chart if data available
        deepseek_analysis = self.current_file.get('deepseek_analysis', {})
        entropy_data = deepseek_analysis.get('analysis_modules', {}).get('entropy', {})
        
        if entropy_data and 'chunk_entropies' in entropy_data:
            self._update_entropy_plot(entropy_data)
        else:
            self._setup_empty_entropy_plot()
        
        # Update tags
        tags = self.current_file.get('tags', [])
        if tags:
            self.tags_list.setHtml(self._format_tags(tags))
        else:
            self.tags_list.setText("No tags")
        
        # Update anomaly details
        if score > 0.3:
            anomaly_details = self._generate_anomaly_details()
            self.anomaly_details.setHtml(anomaly_details)
        else:
            self.anomaly_details.setText("No significant anomalies detected")
    
    def _update_details(self):
        """Update details tree with all file properties"""
        if not self.current_file:
            return
        
        self.details_tree.clear()
        
        # Basic file information
        file_info = QTreeWidgetItem(self.details_tree, ["File Information"])
        self._add_tree_item(file_info, "Path", self.current_file.get('path', ''))
        self._add_tree_item(file_info, "Size", self._format_size(self.current_file.get('size', 0)))
        self._add_tree_item(file_info, "Type", self.current_file.get('file_type', 'unknown'))
        
        timestamp = self.current_file.get('timestamp', 0)
        modified_time = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
        self._add_tree_item(file_info, "Modified", modified_time)
        
        scan_duration = self.current_file.get('scan_duration', 0)
        self._add_tree_item(file_info, "Scan Duration", f"{scan_duration:.2f} seconds")
        
        # Analysis results
        analysis = QTreeWidgetItem(self.details_tree, ["Analysis Results"])
        self._add_tree_item(analysis, "Entropy", f"{self.current_file.get('entropy', 0):.6f}")
        self._add_tree_item(analysis, "Anomaly Score", f"{self.current_file.get('anomaly_score', 0):.6f}")
        
        # Tags
        tags = self.current_file.get('tags', [])
        if tags:
            tags_item = QTreeWidgetItem(self.details_tree, ["Tags"])
            for tag in tags:
                QTreeWidgetItem(tags_item, ["Tag", tag])
        
        # DeepSeek analysis
        deepseek = self.current_file.get('deepseek_analysis', {})
        if deepseek:
            deepseek_item = QTreeWidgetItem(self.details_tree, ["DeepSeek Analysis"])
            self._populate_tree_from_dict(deepseek_item, deepseek)
        
        # Expand top level items
        for i in range(self.details_tree.topLevelItemCount()):
            self.details_tree.topLevelItem(i).setExpanded(True)
    
    def _update_hex_view(self):
        """Update hex view tab with file content"""
        if not self.current_file:
            return
        
        file_path = self.current_file.get('path', '')
        if not file_path or not os.path.exists(file_path):
            self.hex_view.setText("File not found")
            return
        
        try:
            # Get display options
            width_text = self.width_combo.currentText()
            width = 16  # Default
            if width_text == "8 bytes":
                width = 8
            elif width_text == "4 bytes":
                width = 4
            
            use_hex = self.offset_combo.currentText() == "Hexadecimal"
            
            # Read file in binary mode
            with open(file_path, 'rb') as f:
                data = f.read()
            
            # Generate hex view
            hex_text = self._format_hex_view(data, width, use_hex)
            self.hex_view.setText(hex_text)
            
        except Exception as e:
            self.hex_view.setText(f"Error reading file: {str(e)}")
    
    def _update_content(self):
        """Update content tab with file content"""
        if not self.current_file:
            return
        
        file_path = self.current_file.get('path', '')
        if not file_path or not os.path.exists(file_path):
            self.content_view.setText("File not found")
            return
        
        try:
            # Check if it's a text file
            is_text = True
            try:
                with open(file_path, 'r', encoding='utf-8', errors='strict') as f:
                    content = f.read(8192)  # Read first 8K to check
            except UnicodeDecodeError:
                is_text = False
            
            if is_text:
                # It's a text file, read it
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                        content = f.read()
                    self.content_view.setText(content)
                except Exception as e:
                    self.content_view.setText(f"Error reading file: {str(e)}")
            else:
                self.content_view.setText("[Binary content not displayed]")
            
        except Exception as e:
            self.content_view.setText(f"Error reading file: {str(e)}")
    
    def _update_analysis(self):
        """Update analysis tab with DeepSeek results"""
        if not self.current_file:
            return
        
        self.analysis_tree.clear()
        
        deepseek_analysis = self.current_file.get('deepseek_analysis', {})
        if not deepseek_analysis:
            root = QTreeWidgetItem(self.analysis_tree, ["Analysis", "No data available"])
            return
        
        # Add each analysis module
        modules = deepseek_analysis.get('analysis_modules', {})
        for module_name, module_data in modules.items():
            module_item = QTreeWidgetItem(self.analysis_tree, [module_name.capitalize()])
            
            if isinstance(module_data, dict):
                self._populate_tree_from_dict(module_item, module_data)
            else:
                QTreeWidgetItem(module_item, ["Value", str(module_data)])
        
        # Expand top level items
        for i in range(self.analysis_tree.topLevelItemCount()):
            self.analysis_tree.topLevelItem(i).setExpanded(True)
    
    def _update_entropy_plot(self, entropy_data: Dict[str, Any]):
        """Update entropy distribution plot"""
        chunk_entropies = entropy_data.get('chunk_entropies', [])
        if not chunk_entropies:
            self._setup_empty_entropy_plot()
            return
        
        # Clear the plot
        self.entropy_ax.clear()
        self.entropy_ax.set_facecolor('#1e1e1e')
        
        # Plot chunk entropies
        x = list(range(len(chunk_entropies)))
        self.entropy_ax.plot(x, chunk_entropies, 'o-', color='#4CAF50', linewidth=1.5, markersize=4)
        
        # Add horizontal line for overall entropy
        overall_entropy = entropy_data.get('entropy', 0)
        self.entropy_ax.axhline(y=overall_entropy, color='#FFC107', linestyle='--', alpha=0.8)
        
        # Style plot
        self.entropy_ax.set_xlim(-0.5, len(chunk_entropies) - 0.5)
        self.entropy_ax.set_ylim(0, 8)
        self.entropy_ax.set_ylabel('Entropy', color='#cccccc')
        self.entropy_ax.set_xlabel('Chunk', color='#cccccc')
        self.entropy_ax.tick_params(axis='x', colors='#cccccc')
        self.entropy_ax.tick_params(axis='y', colors='#cccccc')
        self.entropy_ax.grid(True, linestyle='--', alpha=0.3)
        
        # Add annotation for overall entropy
        self.entropy_ax.text(len(chunk_entropies) - 1, overall_entropy, f" Avg: {overall_entropy:.2f}",
                          color='#FFC107', fontsize=9, verticalalignment='bottom')
        
        self.entropy_figure.tight_layout()
        self.entropy_canvas.draw()
    
    def _add_tree_item(self, parent, key, value):
        """Add a key-value pair to a tree widget item"""
        return QTreeWidgetItem(parent, [key, str(value)])
    
    def _populate_tree_from_dict(self, parent, data: Dict):
        """Recursively populate tree widget from dictionary"""
        if not data or not isinstance(data, dict):
            return
        
        for key, value in data.items():
            if isinstance(value, dict):
                # Create subitem and populate recursively
                sub_item = QTreeWidgetItem(parent, [str(key)])
                self._populate_tree_from_dict(sub_item, value)
            elif isinstance(value, list):
                # Create subitem and add list items
                sub_item = QTreeWidgetItem(parent, [str(key)])
                
                if value and isinstance(value[0], dict):
                    # List of dictionaries
                    for i, item in enumerate(value):
                        dict_item = QTreeWidgetItem(sub_item, [f"Item {i+1}"])
                        self._populate_tree_from_dict(dict_item, item)
                else:
                    # List of values
                    for i, item in enumerate(value):
                        QTreeWidgetItem(sub_item, [f"[{i}]", str(item)])
            else:
                # Simple key-value
                QTreeWidgetItem(parent, [str(key), str(value)])
    
    def _format_size(self, size: int) -> str:
        """Format byte size to human readable string"""
        if size < 1024:
            return f"{size} bytes"
        elif size < 1024 * 1024:
            return f"{size / 1024:.2f} KB"
        elif size < 1024 * 1024 * 1024:
            return f"{size / (1024 * 1024):.2f} MB"
        else:
            return f"{size / (1024 * 1024 * 1024):.2f} GB"
    
    def _format_tags(self, tags: List[str]) -> str:
        """Format tags as HTML for colored display"""
        if not tags:
            return "No tags"
        
        html = ""
        for tag in tags:
            html += f'<span style="background-color: #2c3e50; color: white; padding: 2px 5px; margin: 2px; border-radius: 3px;">{tag}</span> '
        
        return html
    
    def _generate_anomaly_details(self) -> str:
        """Generate HTML anomaly details from analysis data"""
        if not self.current_file:
            return ""
        
        score = self.current_file.get('anomaly_score', 0)
        if score <= 0.3:
            return "<p>No significant anomalies detected</p>"
        
        # Get details from DeepSeek analysis
        deepseek = self.current_file.get('deepseek_analysis', {})
        
        html = f"<h3>Anomaly Score: <span style='color: {'#F44336' if score > 0.7 else '#FFC107'};'>{score:.2f}</span></h3>"
        
        # Get entropy details
        entropy = self.current_file.get('entropy', 0)
        entropy_data = deepseek.get('analysis_modules', {}).get('entropy', {})
        
        if entropy > 7.0:
            html += "<p><b>High Entropy:</b> File has very high entropy (>7.0), suggesting encryption, compression, or obfuscation.</p>"
        elif entropy > 6.0:
            html += "<p><b>Above-average Entropy:</b> File has higher than normal entropy, possible indicator of compression or encoding.</p>"
        
        if entropy_data.get('chunk_entropy_std', 0) > 1.0:
            html += "<p><b>Entropy Variance:</b> Large variations in entropy between different sections of the file.</p>"
        
        # Get semantic analysis details
        semantic_data = deepseek.get('analysis_modules', {}).get('semantic', {})
        if semantic_data:
            # Check for security issues
            sec_issues = semantic_data.get('security_issues', {})
            if sec_issues:
                html += "<p><b>Security Issues:</b></p><ul>"
                for issue, present in sec_issues.items():
                    if present:
                        html += f"<li>{issue.replace('_', ' ').title()}</li>"
                html += "</ul>"
            
            # Check suspicious keywords
            keywords = semantic_data.get('suspicious_keywords', {})
            if keywords:
                html += "<p><b>Suspicious Keywords:</b></p><ul>"
                for keyword, count in keywords.items():
                    html += f"<li>{keyword} (found {count} times)</li>"
                html += "</ul>"
        
        # Get pattern analysis details
        patterns_data = deepseek.get('analysis_modules', {}).get('patterns', {})
        if patterns_data:
            uncommon = patterns_data.get('uncommon_patterns', [])
            if uncommon:
                html += "<p><b>Uncommon Patterns:</b></p><ul>"
                for pattern in uncommon:
                    html += f"<li>{pattern.get('type', 'Unknown')} - Confidence: {pattern.get('confidence', 0):.2f}</li>"
                html += "</ul>"
            
            urls = patterns_data.get('urls', [])
            if urls:
                html += f"<p><b>URLs found ({len(urls)}):</b></p><ul>"
                for url in urls[:5]:  # Show only first 5
                    html += f"<li>{url}</li>"
                if len(urls) > 5:
                    html += f"<li>... {len(urls) - 5} more</li>"
                html += "</ul>"
        
        return html
    
    def _format_hex_view(self, data: bytes, width: int = 16, use_hex_offset: bool = True) -> str:
        """Format binary data as hex view"""
        if not data:
            return "Empty file"
        
        # Limit display for very large files
        max_display = 16 * 1024  # 16KB
        data_len = len(data)
        data_display = data[:max_display]
        
        # Build hex view
        result = []
        
        for i in range(0, len(data_display), width):
            # Current chunk
            chunk = data_display[i:i+width]
            
            # Format offset
            if use_hex_offset:
                offset = f"{i:08X}"
            else:
                offset = f"{i:10d}"
            
            # Format hex values
            hex_values = " ".join(f"{b:02X}" for b in chunk)
            
            # Format ASCII representation
            ascii_values = "".join(chr(b) if 32 <= b <= 126 else "." for b in chunk)
            
            # Padding for hex values to align ASCII
            hex_padding = " " * (3 * (width - len(chunk)))
            
            # Combine all parts
            result.append(f"{offset}:  {hex_values}{hex_padding}  |{ascii_values}|")
        
        # Add indicator if the file was truncated
        if data_len > max_display:
            result.append(f"\n... Truncated display ({self._format_size(max_display)} of {self._format_size(data_len)})")
        
        return "\n".join(result)
    
    def _export_report(self):
        """Export file analysis report"""
        if not self.current_file:
            QMessageBox.warning(self, "Warning", "No file loaded")
            return
        
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export Report", "",
            "HTML Files (*.html);;Text Files (*.txt);;JSON Files (*.json)"
        )
        
        if not file_path:
            return
        
        try:
            # Handle different export formats
            if file_path.endswith(".html"):
                self._export_html_report(file_path)
            elif file_path.endswith(".txt"):
                self._export_text_report(file_path)
            elif file_path.endswith(".json"):
                self._export_json_report(file_path)
            else:
                # Default to HTML
                if not file_path.endswith(".html"):
                    file_path += ".html"
                self._export_html_report(file_path)
            
            QMessageBox.information(self, "Success", f"Report exported to {file_path}")
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to export report: {str(e)}")
    
    def _export_html_report(self, file_path: str):
        """Export report in HTML format"""
        if not self.current_file:
            return
        
        # Begin HTML content
        html = f"""<!DOCTYPE html>
        <html>
        <head>
            <title>File Analysis Report - {os.path.basename(self.current_file.get('path', ''))}</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; background-color: #f5f5f5; color: #333; }}
                .header {{ background-color: #2c3e50; color: white; padding: 10px; border-radius: 5px; }}
                .section {{ background-color: white; padding: 15px; margin: 10px 0; border-radius: 5px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
                table {{ border-collapse: collapse; width: 100%; }}
                th, td {{ text-align: left; padding: 8px; border-bottom: 1px solid #ddd; }}
                th {{ background-color: #f2f2f2; }}
                .tag {{ background-color: #2c3e50; color: white; padding: 2px 5px; margin: 2px; border-radius: 3px; }}
                .score-high {{ color: #F44336; font-weight: bold; }}
                .score-medium {{ color: #FFC107; font-weight: bold; }}
                .score-low {{ color: #4CAF50; font-weight: bold; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>File Analysis Report</h1>
                <p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            </div>
        """
        
        # File information section
        file_path_value = self.current_file.get('path', '')
        file_size = self.current_file.get('size', 0)
        file_type = self.current_file.get('file_type', 'unknown')
        timestamp = self.current_file.get('timestamp', 0)
        modified_time = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
        
        html += f"""
            <div class="section">
                <h2>File Information</h2>
                <table>
                    <tr><th>Name</th><td>{os.path.basename(file_path_value)}</td></tr>
                    <tr><th>Path</th><td>{file_path_value}</td></tr>
                    <tr><th>Size</th><td>{self._format_size(file_size)}</td></tr>
                    <tr><th>Type</th><td>{file_type}</td></tr>
                    <tr><th>Modified</th><td>{modified_time}</td></tr>
                </table>
            </div>
        """
        
        # Analysis results section
        score = self.current_file.get('anomaly_score', 0)
        entropy = self.current_file.get('entropy', 0)
        score_class = 'score-high' if score > 0.7 else 'score-medium' if score > 0.3 else 'score-low'
        
        html += f"""
            <div class="section">
                <h2>Analysis Results</h2>
                <table>
                    <tr><th>Anomaly Score</th><td class="{score_class}">{score:.4f}</td></tr>
                    <tr><th>Entropy</th><td>{entropy:.4f}</td></tr>
                </table>
            </div>
        """
        
        # Tags section
        tags = self.current_file.get('tags', [])
        if tags:
            html += f"""
                <div class="section">
                    <h2>Tags</h2>
                    <p>
            """
            for tag in tags:
                html += f'<span class="tag">{tag}</span> '
            html += """
                    </p>
                </div>
            """
        
        # Anomaly details
        if score > 0.3:
            html += f"""
                <div class="section">
                    <h2>Anomaly Details</h2>
                    {self._generate_anomaly_details()}
                </div>
            """
        
        # Close HTML
        html += """
        </body>
        </html>
        """
        
        # Write to file
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(html)
    
    def _export_text_report(self, file_path: str):
        """Export report in plain text format"""
        if not self.current_file:
            return
        
        # Format text report
        report = [
            "FILE ANALYSIS REPORT",
            "=" * 80,
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "=" * 80,
            "",
            "FILE INFORMATION",
            "-" * 80,
            f"Name: {os.path.basename(self.current_file.get('path', ''))}",
            f"Path: {self.current_file.get('path', '')}",
            f"Size: {self._format_size(self.current_file.get('size', 0))}",
            f"Type: {self.current_file.get('file_type', 'unknown')}",
            f"Modified: {datetime.fromtimestamp(self.current_file.get('timestamp', 0)).strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "ANALYSIS RESULTS",
            "-" * 80,
            f"Anomaly Score: {self.current_file.get('anomaly_score', 0):.4f}",
            f"Entropy: {self.current_file.get('entropy', 0):.4f}",
            ""
        ]
        
        # Add tags
        tags = self.current_file.get('tags', [])
        if tags:
            report.extend([
                "TAGS",
                "-" * 80,
                ", ".join(tags),
                ""
            ])
        
        # Write to file
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write("\n".join(report))
    
    def _export_json_report(self, file_path: str):
        """Export the raw data in JSON format"""
        if not self.current_file:
            return
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(self.current_file, f, indent=2)
    
    def _rescan_file(self):
        """Request a rescan of the current file"""
        if self.current_file:
            file_path = self.current_file.get('path')
            if file_path and os.path.exists(file_path):
                # Signal to rescan
                QMessageBox.information(
                    self, 
                    "Rescan", 
                    f"Rescanning file {os.path.basename(file_path)}"
                )
                # TODO: Implement callback to analyzer engine
                
    def cleanup(self):
        """Clean up resources when the widget is about to be destroyed."""
        # Clean up matplotlib figures
        if hasattr(self, 'entropy_figure'):
            self.entropy_figure.clear()
            
        if hasattr(self, 'entropy_canvas'):
            self.entropy_canvas.close()
            
        # Clean up any other matplotlib figures if present
        if hasattr(self, 'analysis_figure'):
            self.analysis_figure.clear()
            
        if hasattr(self, 'analysis_canvas'):
            self.analysis_canvas.close()
            
    def __del__(self):
        """Destructor to ensure cleanup is called."""
        self.cleanup() 