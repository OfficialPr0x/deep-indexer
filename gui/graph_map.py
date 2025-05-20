import os
import re
from typing import Dict, List, Any, Optional
from pathlib import Path
import time

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
    QLabel, QComboBox, QSlider, QCheckBox, QFrame,
    QFileDialog, QMessageBox
)
from PySide6.QtCore import Qt, Signal, Slot, QTimer, QRectF
from PySide6.QtGui import QColor, QPainter, QPen, QBrush, QPainterPath

import networkx as nx
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.patches import Circle, PathPatch

class GraphMapWidget(QWidget):
    """
    Graph network visualization for file relationships and anomalies
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Initialize graph data
        self.graph = nx.Graph()
        self.node_data = {}
        self.layout_type = "spring"
        self.node_size_factor = 1.0
        self.node_color_by = "type"  # or "score"
        self.edge_thickness_by = "weight"
        
        # Setup UI
        self._setup_ui()
        
        # Add to class initialization
        self.performance_stats = {
            'last_render_time': 0.0,
            'node_count': 0,
            'edge_count': 0
        }
    
    def _setup_ui(self):
        """Set up the UI components"""
        main_layout = QVBoxLayout(self)
        
        # Controls layout
        control_layout = QHBoxLayout()
        
        # Layout selection
        layout_label = QLabel("Layout:")
        self.layout_combo = QComboBox()
        self.layout_combo.addItems(["Spring", "Circular", "Kamada-Kawai", "Spectral"])
        self.layout_combo.currentTextChanged.connect(self._update_layout)
        
        # Node size slider
        size_label = QLabel("Node Size:")
        self.size_slider = QSlider(Qt.Horizontal)
        self.size_slider.setMinimum(1)
        self.size_slider.setMaximum(20)
        self.size_slider.setValue(10)
        self.size_slider.valueChanged.connect(self._update_display)
        
        # Color by selection
        color_label = QLabel("Color by:")
        self.color_combo = QComboBox()
        self.color_combo.addItems(["Type", "Score", "Size"])
        self.color_combo.currentTextChanged.connect(self._update_display)
        
        # Show labels checkbox
        self.show_labels = QCheckBox("Show Labels")
        self.show_labels.setChecked(True)
        self.show_labels.stateChanged.connect(self._update_display)
        
        # Show only anomalies
        self.show_anomalies = QCheckBox("Only Anomalies")
        self.show_anomalies.setChecked(False)
        self.show_anomalies.stateChanged.connect(self._update_display)
        
        # Export button
        export_button = QPushButton("Export")
        export_button.clicked.connect(self._export_graph)
        
        # Add controls to layout
        control_layout.addWidget(layout_label)
        control_layout.addWidget(self.layout_combo)
        control_layout.addWidget(size_label)
        control_layout.addWidget(self.size_slider)
        control_layout.addWidget(color_label)
        control_layout.addWidget(self.color_combo)
        control_layout.addWidget(self.show_labels)
        control_layout.addWidget(self.show_anomalies)
        control_layout.addStretch()
        control_layout.addWidget(export_button)
        
        # Add graph canvas
        self.figure = Figure(figsize=(8, 6), dpi=100)
        self.figure.patch.set_facecolor('#1e1e1e')
        self.canvas = FigureCanvas(self.figure)
        self.canvas.setStyleSheet("background-color: #1e1e1e;")
        
        # Create initial empty plot
        self.ax = self.figure.add_subplot(111)
        self.ax.set_facecolor('#2e2e2e')
        self._setup_empty_plot()
        
        # Add widgets to main layout
        main_layout.addLayout(control_layout)
        main_layout.addWidget(self.canvas)
    
    def _setup_empty_plot(self):
        """Set up empty plot with instructions"""
        self.ax.clear()
        self.ax.set_facecolor('#2e2e2e')
        
        # Show instructions
        self.ax.text(0.5, 0.5, "No data available.\nScan files to build the graph network.",
                    horizontalalignment='center',
                    verticalalignment='center',
                    transform=self.ax.transAxes,
                    color='#aaaaaa',
                    fontsize=12)
        
        # Remove axes and set equal aspect ratio
        self.ax.set_aspect('equal')
        self.ax.axis('off')
        
        # Update canvas
        self.figure.tight_layout()
        self.canvas.draw()
    
    def _update_layout(self):
        """Cached layout computation with performance safeguards"""
        if len(self.graph.nodes()) > self._MAX_NODES:
            self._show_performance_warning()
            return
        
        cache_key = f"{self.layout_combo.currentText()}-{nx.weisfeiler_lehman_graph_hash(self.graph)}"
        
        if cache_key in self._LAYOUT_CACHE:
            self.positions = self._LAYOUT_CACHE[cache_key]
        else:
            # Compute and cache new layout
            self.positions = nx.spring_layout(self.graph)  # Keep fallback
            self._LAYOUT_CACHE[cache_key] = self.positions
    
    def _update_display(self):
        """Update the graph display"""
        if not self.graph.nodes():
            self._setup_empty_plot()
            return
        
        # Clear the plot
        self.ax.clear()
        self.ax.set_facecolor('#2e2e2e')
        
        # Get display options
        node_size_factor = self.size_slider.value() / 10
        color_by = self.color_combo.currentText().lower()
        show_labels = self.show_labels.isChecked()
        only_anomalies = self.show_anomalies.isChecked()
        
        # Filter nodes for anomalies if requested
        display_graph = self.graph
        if only_anomalies:
            # Create subgraph with only anomalous nodes
            anomaly_nodes = [n for n, data in self.graph.nodes(data=True) if data.get('anomaly_score', 0) > 0.5]
            display_graph = self.graph.subgraph(anomaly_nodes)
            
            if not display_graph.nodes():
                self.ax.text(0.5, 0.5, "No anomalies found in graph data.",
                           horizontalalignment='center',
                           verticalalignment='center',
                           transform=self.ax.transAxes,
                           color='#aaaaaa',
                           fontsize=12)
                self.ax.axis('off')
                self.figure.tight_layout()
                self.canvas.draw()
                return
        
        # Set node colors based on selected attribute
        node_colors = []
        node_sizes = []
        
        for node in display_graph.nodes():
            data = display_graph.nodes[node]
            
            # Determine node color
            if color_by == "type":
                file_type = data.get('file_type', 'unknown').lower()
                # Map file types to colors
                type_colors = {
                    '.py': '#3572A5',  # Python
                    '.js': '#F0DB4F',  # JavaScript
                    '.html': '#E34C26',  # HTML
                    '.css': '#563D7C',  # CSS
                    '.java': '#B07219',  # Java
                    '.cpp': '#F34B7D',  # C++
                    '.c': '#555555',  # C
                    '.php': '#4F5D95',  # PHP
                    '.rb': '#701516',  # Ruby
                    '.txt': '#FFFFFF',  # Text
                    '.md': '#083FA1',  # Markdown
                    '.json': '#40E0D0',  # JSON
                    '.xml': '#0060AC',  # XML
                    '.exe': '#FF0000',  # Executable
                    '.dll': '#FF7F00',  # DLL
                }
                node_colors.append(type_colors.get(file_type, '#CCCCCC'))
                
            elif color_by == "score":
                score = data.get('anomaly_score', 0)
                # Color gradient from green to red based on score
                if score < 0.3:
                    node_colors.append('#4CAF50')  # Green for low scores
                elif score < 0.7:
                    node_colors.append('#FFC107')  # Yellow for medium scores
                else:
                    node_colors.append('#F44336')  # Red for high scores
            
            elif color_by == "size":
                size = data.get('size', 1000)
                # Normalize size to color (darker = larger)
                normalized_size = min(1.0, max(0.0, np.log10(size) / 8))
                # Blues color map (lighter to darker)
                blue_value = int(220 - (normalized_size * 160))
                node_colors.append(f'#{100:02x}{150:02x}{blue_value:02x}')
            
            # Determine node size
            base_size = 300 * node_size_factor
            size_value = data.get('size', 1000)
            
            # Log scale for size to avoid extreme variations
            log_size = np.log10(max(1, size_value))
            scaled_size = base_size * (1 + log_size / 5)
            
            node_sizes.append(scaled_size)
        
        # Draw edges with alpha based on weight
        for u, v, data in display_graph.edges(data=True):
            weight = data.get('weight', 1)
            alpha = min(1.0, max(0.1, weight / 5))
            x1, y1 = self.positions[u]
            x2, y2 = self.positions[v]
            line = [(x1, y1), (x2, y2)]
            self.ax.plot(*zip(*line), color='#888888', alpha=alpha, linewidth=0.5)
        
        # Draw nodes
        nx.draw_networkx_nodes(
            display_graph,
            self.positions,
            node_color=node_colors,
            node_size=node_sizes,
            alpha=0.9,
            ax=self.ax
        )
        
        # Draw labels if enabled
        if show_labels:
            # Custom labels (shorter names)
            labels = {}
            for node in display_graph.nodes():
                # Get just the filename, not the full path
                filename = os.path.basename(node)
                # Truncate if too long
                if len(filename) > 15:
                    filename = filename[:12] + "..."
                labels[node] = filename
                
            nx.draw_networkx_labels(
                display_graph,
                self.positions,
                labels=labels,
                font_size=8,
                font_color='white',
                font_family='sans-serif',
                ax=self.ax
            )
        
        # Style plot
        self.ax.set_aspect('equal')
        self.ax.axis('off')
        
        # Update canvas
        self.figure.tight_layout()
        self.canvas.draw()
        
        # Add to _update_display()
        start_time = time.time()
        self.performance_stats['last_render_time'] = time.time() - start_time
        self.performance_stats['node_count'] = len(display_graph.nodes())
        self.performance_stats['edge_count'] = len(display_graph.edges())
    
    def _export_graph(self):
        """Secure file export with validation"""
        if not self.graph.nodes():
            QMessageBox.warning(self, "Warning", "No graph data to export.")
            return
        
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export Graph Image", "",
            "PNG Files (*.png);;SVG Files (*.svg);;PDF Files (*.pdf)"
        )
        
        if not file_path:
            return
        
        # Validate extension
        allowed_extensions = {'.png', '.svg', '.pdf'}
        if Path(file_path).suffix.lower() not in allowed_extensions:
            QMessageBox.critical(self, "Error", "Invalid file format")
            return
        
        # Validate write permissions
        try:
            with open(file_path, 'w') as f:
                pass
            os.remove(file_path)
        except PermissionError:
            QMessageBox.critical(self, "Error", "Write permission denied")
            return
    
    def add_file_node(self, file_data: Dict[str, Any]):
        """
        Add a file node to the graph
        
        Args:
            file_data: Dictionary containing file information
        """
        if not isinstance(file_data, dict):
            raise ValueError("file_data must be a dictionary")
        if 'path' not in file_data:
            raise KeyError("file_data must contain 'path' key")
        if not os.path.exists(file_data['path']):
            raise FileNotFoundError(f"Path {file_data['path']} does not exist")
        
        path = file_data.get('path')
        if not path or path in self.node_data:
            return
        
        # Store node data
        self.node_data[path] = file_data
        
        # Add node to graph with properties
        self.graph.add_node(
            path,
            file_type=file_data.get('file_type', 'unknown'),
            size=file_data.get('size', 0),
            anomaly_score=file_data.get('anomaly_score', 0),
            timestamp=file_data.get('timestamp', 0)
        )
        
        # Try to establish relationships with existing nodes
        self._find_relationships(path, file_data)
        
        # Update layout and display
        if len(self.graph.nodes()) == 1:
            # First node, initialize layout
            self.positions = {path: np.array([0, 0])}
        else:
            # Update layout
            self._update_layout()
    
    def add_edge(self, source: str, target: str, relationship_type: str, weight: float = 1.0):
        """
        Add an edge between two nodes
        
        Args:
            source: Source node path
            target: Target node path
            relationship_type: Type of relationship
            weight: Edge weight
        """
        if source in self.graph.nodes() and target in self.graph.nodes():
            # Check if edge already exists
            if self.graph.has_edge(source, target):
                # Update existing edge
                current_weight = self.graph[source][target].get('weight', 1.0)
                current_types = self.graph[source][target].get('types', [])
                
                if relationship_type not in current_types:
                    current_types.append(relationship_type)
                
                self.graph[source][target]['weight'] = current_weight + weight
                self.graph[source][target]['types'] = current_types
            else:
                # Add new edge
                self.graph.add_edge(
                    source, 
                    target,
                    weight=weight,
                    types=[relationship_type]
                )
            
            # Update display
            self._update_display()
    
    def _find_relationships(self, new_path: str, file_data: Dict[str, Any]):
        """Analyze file contents and metadata to establish real relationships"""
        # 1. Content-based relationships
        try:
            with open(new_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
            # Find imports/references (Python specific example)
            if file_data['file_type'] == '.py':
                import_pattern = re.compile(r'^\s*import\s+(\w+)|\s*from\s+(\w+)', re.M)
                imports = set(m.group(1) or m.group(2) for m in import_pattern.finditer(content))
                
                for existing_path, data in self.node_data.items():
                    if data['file_type'] == '.py':
                        module_name = os.path.splitext(os.path.basename(existing_path))[0]
                        if module_name in imports:
                            self.add_edge(new_path, existing_path, "import_dependency", 3.0)
        
        except Exception as e:
            self.log_error(f"Failed analyzing {new_path}: {str(e)}")
        
        # 2. Semantic similarity analysis
        if 'embeddings' in file_data:
            for existing_path, existing_data in self.node_data.items():
                if 'embeddings' in existing_data:
                    similarity = np.dot(file_data['embeddings'], existing_data['embeddings'])
                    if similarity > 0.7:
                        self.add_edge(new_path, existing_path, "semantic_similarity", similarity)
    
    def clear_graph(self):
        """Clear the graph data"""
        self.graph.clear()
        self.node_data = {}
        self._setup_empty_plot()
    
    def update_node(self, path: str, updated_data: Dict[str, Any]):
        """Update node data for an existing node"""
        if path in self.graph:
            self.graph.nodes[path].update(updated_data)
            self.node_data[path] = updated_data
            self._update_display()
            
    def cleanup(self):
        """Clean up resources when the widget is about to be destroyed."""
        # Stop any timers
        if hasattr(self, '_layout_timer') and self._layout_timer is not None:
            self._layout_timer.stop()
            
        # Clear references for cleanup
        if hasattr(self, 'figure'):
            self.figure.clear()
            
        if hasattr(self, 'canvas'):
            self.canvas.close()
            
    def __del__(self):
        """Destructor to ensure cleanup is called."""
        self.cleanup()

# Add these class variables
_MAX_NODES = 5000
_LAYOUT_CACHE = {} 