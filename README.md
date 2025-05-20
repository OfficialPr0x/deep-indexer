# SpecterWire - DeepSeek Analyst Engine

A modular, threaded real-time Python application using PySide6 for GUI and DeepSeek for recursive file/codebase analysis. Designed with an emphasis on clarity, speed, and extensibility.

> **"Watch what no one else can see."**

## Overview

SpecterWire is a powerful file analysis framework designed to identify anomalies, potential security issues, and patterns in files and codebases. It leverages entropy analysis, pattern detection, and semantic code understanding to provide actionable intelligence about your files.

Key features:
- Recursive directory scanning with multi-threading
- Real-time entropy and anomaly detection
- Detailed visualization of file characteristics
- Interactive network graph of file relationships
- PySide6-powered modern dark-themed UI
- Extensible plugin system

## Installation

### Prerequisites
- Python 3.10+
- Required libraries (see requirements.txt)

### Setup

```bash
# Clone the repository
git clone https://github.com/yourusername/specterwire.git
cd specterwire

# Create and activate virtual environment (optional but recommended)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the application
python app.py
```

## Usage

### Command-line Options

```
python app.py [OPTIONS]

Options:
  -c, --config PATH  Path to configuration file
  -t, --target PATH  Initial directory or file to scan
  -d, --debug        Enable debug logging
  -h, --help         Show this help message
```

### GUI Interface

The application offers a comprehensive graphical interface with several views:

1. **Dashboard**: Overview with key metrics and scan results
2. **Live Monitor**: Real-time stream of events and scan activities
3. **File Inspector**: Detailed information about selected files
4. **Graph Network**: Interactive visualization of file relationships

### Configuration

The application can be configured using a YAML file:

```yaml
analyzer_config:
  max_workers: 4
  max_file_size: 104857600  # 100MB
  deepseek_config:
    use_offline_mode: true
    analysis_modules:
      - entropy
      - structure
      - semantic
      - patterns

gui_config:
  theme: dark
  default_view: dashboard
  max_log_entries: 1000

plugin_config:
  enabled: true
  plugin_dir: plugins
```

## Architecture

### Core Components

1. **Analyzer Engine**: Handles file scanning, entropy calculations, and anomaly detection
2. **DeepSeek Integration**: Enables advanced semantic analysis of file contents
3. **Plugin System**: Allows extending functionality with custom analysis modules
4. **GUI Framework**: Modern PySide6-based interface with real-time updates

### Folder Structure

```
deepIndexer/
|-- core/
|   |-- analyzer.py     # Core analysis engine
|   |-- deepseek_hooks.py  # DeepSeek integration
|-- gui/
|   |-- main_window.py  # Main application window
|   |-- live_monitor.py # Real-time event display
|   |-- graph_map.py    # Network visualization
|   |-- file_inspector.py # Detailed file view
|-- plugins/            # Custom analysis modules
|-- config/             # Configuration files
|-- resources/          # Application resources
|-- app.py              # Main entry point
|-- requirements.txt    # Dependencies
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- Built with PySide6 (Qt for Python)
- Visualization powered by matplotlib and networkx 

## Troubleshooting

### QBasicTimer Issues

If you encounter errors like `QBasicTimer::start: QBasicTimer can only be used with threads started with QThread`, this is due to threading issues when GUI operations are performed from non-GUI threads. We've implemented the following fixes:

1. **GUI Operations in Main Thread**: All GUI operations are now properly marshaled to the main thread using `QTimer.singleShot(0, lambda: ...)` pattern.

2. **Thread-Safe Healing Dialog**: The healing manager has been modified to ensure dialogs are created and updated only in the main thread.

3. **Non-Blocking Callbacks**: DeepSeek engine callbacks now run in separate threads to avoid blocking the main thread.

4. **Safe Log Handling**: Log messages are now properly displayed without causing QBasicTimer errors by ensuring they are processed in the UI thread.

If you still experience issues:

1. Check that any new code that interacts with GUI elements is properly marshaled to the main thread
2. Use the thread-safe methods in the LiveMonitorWidget for adding log entries and file alerts
3. Ensure all callbacks from non-GUI threads to GUI code use proper thread synchronization

### Other Common Issues

If the healing system doesn't seem to work:

1. Check that the DeepSeek engine is properly initialized
2. Verify that API credentials are correct (if using online mode)
3. Check the logs for any specific error messages
4. Try running with `--debug` flag for more detailed logging 