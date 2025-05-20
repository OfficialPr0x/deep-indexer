#!/usr/bin/env python3
"""
SpecterWire - DeepSeek Analyst Engine

A modular, threaded file analysis application using PySide6 for GUI
and DeepSeek for recursive file/codebase analysis.

"Watch what no one else can see."
"""

import os
import sys
import argparse
import yaml
import logging
from pathlib import Path

from PySide6.QtWidgets import QApplication

from gui.main_window import MainWindow

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('SpecterWire')

def load_config(config_path=None):
    """
    Load configuration from file or use defaults
    
    Args:
        config_path: Path to YAML configuration file
        
    Returns:
        Configuration dictionary
    """
    # Default configuration
    default_config = {
        'analyzer_config': {
            'max_workers': 4,
            'max_file_size': 100 * 1024 * 1024,  # 100MB
            'deepseek_config': {
                'use_offline_mode': True,  # Default to offline mode to avoid requiring API key
                'cache_dir': os.path.join(os.path.expanduser('~'), '.specterwire', 'cache'),
                'analysis_modules': ['entropy', 'structure', 'semantic', 'patterns'],
                # API key will be injected below if available
            }
        },
        'gui_config': {
            'theme': 'dark',
            'default_view': 'dashboard',
            'max_log_entries': 1000,
        },
        'plugin_config': {
            'enabled': True,
            'plugin_dir': 'plugins'
        }
    }
    
    # Try to load from file if provided
    if config_path and os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                user_config = yaml.safe_load(f)
                
            # Merge user config with defaults
            if user_config:
                # Recursive dictionary merge
                def merge_dicts(default, user):
                    for key, value in user.items():
                        if key in default and isinstance(default[key], dict) and isinstance(value, dict):
                            merge_dicts(default[key], value)
                        else:
                            default[key] = value
                
                merge_dicts(default_config, user_config)
                logger.info(f"Loaded configuration from {config_path}")
            
        except Exception as e:
            logger.error(f"Error loading configuration from {config_path}: {str(e)}")
            logger.info("Using default configuration")
    
    # Inject API key from settings.yml if present
    settings_path = os.path.join(os.path.dirname(__file__), 'config/settings.yml')
    if os.path.exists(settings_path):
        try:
            with open(settings_path, 'r') as f:
                settings = yaml.safe_load(f)
            if settings and 'deepseek_api_key' in settings:
                default_config['analyzer_config']['deepseek_config']['api_key'] = settings['deepseek_api_key']
        except Exception as e:
            logger.warning(f"Could not load settings.yml: {e}")
    
    # Inject API key from environment if not present
    deepseek_cfg = default_config['analyzer_config']['deepseek_config']
    if not deepseek_cfg.get('api_key'):
        env_key = os.getenv('DEEPSEEK_API_KEY')
        if env_key:
            deepseek_cfg['api_key'] = env_key
    
    # Ensure cache directory exists
    cache_dir = deepseek_cfg['cache_dir']
    os.makedirs(cache_dir, exist_ok=True)
    
    return default_config

def setup_plugins(config):
    """
    Load and initialize plugins
    
    Args:
        config: Application configuration
        
    Returns:
        Plugin manager instance or None
    """
    if not config.get('plugin_config', {}).get('enabled', False):
        logger.info("Plugins disabled")
        return None
        
    plugin_dir = config.get('plugin_config', {}).get('plugin_dir', 'plugins')
    
    try:
        # In a real implementation, this would dynamically load plugins
        # For now, we'll just return None
        logger.info(f"Plugin directory: {plugin_dir}")
        logger.info("Plugin system initialized")
        return None
    except Exception as e:
        logger.error(f"Error initializing plugin system: {str(e)}")
        return None

def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='SpecterWire - DeepSeek Analyst Engine')
    parser.add_argument('--config', '-c', help='Path to configuration file')
    parser.add_argument('--target', '-t', help='Initial directory or file to scan')
    parser.add_argument('--debug', '-d', action='store_true', help='Enable debug logging')
    
    return parser.parse_args()

def main():
    """Main application entry point"""
    # Parse command line arguments
    args = parse_arguments()
    
    # Configure logging level
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.debug("Debug logging enabled")
    
    # Load configuration
    logger.debug("Loading configuration...")
    config = load_config(args.config)
    logger.debug("Configuration loaded")
    
    # Setup plugins
    logger.debug("Setting up plugins...")
    plugin_manager = setup_plugins(config)
    logger.debug("Plugins setup complete")
    
    # Create application
    logger.debug("Creating QApplication...")
    app = QApplication(sys.argv)
    app.setApplicationName('SpecterWire')
    app.setApplicationDisplayName('SpecterWire Analyst')
    logger.debug("QApplication created")
    
    try:
        # Create main window
        logger.debug("Creating main window...")
        window = MainWindow(config)
        logger.debug("Main window created")
        window.show()
        logger.debug("Main window shown")
        
        # If a target was specified, queue it for scanning
        if args.target and os.path.exists(args.target):
            logger.debug(f"Processing target: {args.target}")
            if os.path.isdir(args.target):
                window.directory_input.setText(args.target)
                window._start_scan()
            elif os.path.isfile(args.target):
                window._scan_single_file(args.target)
        
        # Start application event loop
        logger.debug("Starting application event loop")
        return_code = app.exec()
        logger.debug(f"Application event loop exited with code {return_code}")
        sys.exit(return_code)
    except Exception as e:
        logger.error(f"Fatal error in main: {str(e)}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main() 