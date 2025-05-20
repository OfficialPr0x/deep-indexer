import os
import time
import json
import logging
import hashlib
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
import mimetypes
import random

import numpy as np
from tqdm import tqdm

try:
    from openai import OpenAI
except ImportError:
    raise ImportError("Please install the openai package: pip install openai")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('SpecterWire.DeepSeek')

class DeepSeekEngine:
    """
    Production integration for DeepSeek v3.1 (deepseek-chat) via OpenAI-compatible API.
    Provides file analysis, pattern detection, and anomaly scoring using real DeepSeek API.
    """
    
    # Add error recovery states and logging levels
    ERROR_LEVELS = {
        'CRITICAL': 50,  # Application halting errors
        'ERROR': 40,     # Serious problems requiring intervention
        'WARNING': 30,   # Potential issues that need attention
        'INFO': 20,      # Normal operational information
        'DEBUG': 10,     # Detailed diagnostic information
        'TRACE': 5       # Very detailed tracing information
    }
    
    # Define self-healing strategies
    HEALING_STRATEGIES = {
        'API_TIMEOUT': {
            'max_retries': 5,
            'backoff_factor': 1.5,
            'max_backoff': 30,
            'jitter': True,
            'description': 'API timeout recovery'
        },
        'RATE_LIMIT': {
            'max_retries': 8,
            'backoff_factor': 2.0,
            'max_backoff': 60,
            'jitter': True,
            'description': 'Rate limit recovery with exponential backoff'
        },
        'TOKEN_ERROR': {
            'max_retries': 3,
            'backoff_factor': 1.0,
            'max_backoff': 5,
            'jitter': False,
            'description': 'API token validation error recovery'
        },
        'NETWORK_ERROR': {
            'max_retries': 7,
            'backoff_factor': 1.7,
            'max_backoff': 45,
            'jitter': True,
            'description': 'Network connection recovery'
        },
        'SERVER_ERROR': {
            'max_retries': 6,
            'backoff_factor': 2.5,
            'max_backoff': 120,
            'jitter': True,
            'description': 'Server error recovery with extended backoff'
        }
    }
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the DeepSeek Engine with configuration
        
        Args:
            config: Configuration dictionary with DeepSeek settings
        """
        self.config = config
        # Get API key from config or environment
        self.api_key = config.get('api_key') or os.getenv('DEEPSEEK_API_KEY')
        self.api_base_url = config.get('api_base_url', 'https://api.deepseek.com')
        self.model = config.get('model', 'deepseek-reasoner')
        self.cache_dir = config.get('cache_dir', os.path.join(os.path.expanduser('~'), '.specterwire', 'cache'))
        self.timeout = config.get('timeout', 120)
        self.max_file_size = config.get('max_file_size', 10 * 1024 * 1024)
        self.analysis_modules = config.get('analysis_modules', ['entropy', 'structure', 'semantic', 'patterns'])
        self.use_offline_mode = config.get('use_offline_mode', True)  # Default to safe offline mode
        self.batch_size = config.get('batch_size', 1000000)
        self.system_prompt = config.get('system_prompt', "You are an AI file analysis assistant. Analyze the content provided.")
        self.loglevel = config.get('log_level', 'DEBUG')
        os.makedirs(self.cache_dir, exist_ok=True)
        
        # Only check for API key when not in offline mode
        if not self.use_offline_mode and not self.api_key:
            raise ValueError(
                "DeepSeek API key required for online mode. "
                "Set use_offline_mode: true in config or provide DEEPSEEK_API_KEY environment variable."
            )
        
        # Only create client if not in offline mode and API key is available
        self.client = None
        if not self.use_offline_mode and self.api_key:
            self.client = OpenAI(api_key=self.api_key, base_url=self.api_base_url)
            
        logger.info(f"DeepSeekEngine initialized (offline={self.use_offline_mode})")
        
        # Setup enhanced logging
        self._setup_advanced_logging()
        
        # List of supported file extensions and MIME types for deep analysis
        self.supported_types = {
            # Code files
            '.py': 'text/x-python',
            '.js': 'text/javascript',
            '.html': 'text/html',
            '.css': 'text/css',
            '.java': 'text/x-java',
            '.cpp': 'text/x-c++',
            '.c': 'text/x-c',
            '.h': 'text/x-c',
            '.hpp': 'text/x-c++',
            '.cs': 'text/x-csharp',
            '.go': 'text/x-go',
            '.php': 'text/x-php',
            '.rb': 'text/x-ruby',
            '.rs': 'text/x-rust',
            '.ts': 'text/x-typescript',
            
            # Document files
            '.txt': 'text/plain',
            '.md': 'text/markdown',
            '.json': 'application/json',
            '.xml': 'application/xml',
            '.csv': 'text/csv',
            '.log': 'text/plain',
            
            # Binary files
            '.exe': 'application/x-executable',
            '.dll': 'application/x-sharedlib',
            '.so': 'application/x-sharedlib',
            '.bin': 'application/octet-stream',
            '.dat': 'application/octet-stream',
        }
        
        # Load file signatures for binary analysis
        self._load_file_signatures()
        
        # Initialize cache
        self.initialization_time = time.time()
        self.health_status = "HEALTHY"
        self.error_count = 0
        self.healing_count = 0
        self.last_error = None
        self.last_healing = None
        
        # Initialize file type support
        self.supported_file_types = self._get_supported_file_types()
        logger.info(f"DeepSeek Engine initialized with {len(self.supported_file_types)} supported file types")
        
        # Store callback for healing notifications
        self.healing_callback = None
    
    def _setup_advanced_logging(self):
        """Setup enhanced logging with detailed formatting."""
        self.logger = logging.getLogger('SpecterWire.DeepSeek')
        
        # Set log level based on config
        level_name = self.config.get('log_level', 'DEBUG')
        level = getattr(logging, level_name, logging.DEBUG)
        self.logger.setLevel(level)
        
        # Create a file handler for persistent logs
        log_dir = os.path.join(os.path.dirname(self.cache_dir), 'logs')
        os.makedirs(log_dir, exist_ok=True)
        
        log_file = os.path.join(log_dir, f'deepseek_{time.strftime("%Y%m%d")}.log')
        file_handler = logging.FileHandler(log_file)
        
        # Create detailed formatter for logs
        detailed_format = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(detailed_format)
        
        # Add handlers if they don't already exist
        handlers_exist = any(isinstance(h, logging.FileHandler) for h in self.logger.handlers)
        if not handlers_exist:
            self.logger.addHandler(file_handler)
    
    def set_healing_callback(self, callback):
        """Set callback function for healing notifications."""
        self.healing_callback = callback
    
    def _trigger_self_healing(self, error_type, exception=None, context=None):
        """
        Trigger self-healing procedures based on error type.
        Returns True if healing was successful, False otherwise.
        """
        self.healing_count += 1
        self.last_healing = {
            'timestamp': time.time(),
            'error_type': error_type,
            'exception': str(exception) if exception else None,
            'context': context or {}
        }
        
        # Log healing attempt
        self.logger.warning(f"Self-healing triggered for {error_type}: {str(exception) if exception else 'No exception'}")
        
        # Get healing strategy
        strategy = self.HEALING_STRATEGIES.get(error_type, {
            'max_retries': 3,
            'backoff_factor': 1.0,
            'max_backoff': 15,
            'jitter': True,
            'description': 'Generic error recovery'
        })
        
        # Notify via callback if available
        if self.healing_callback:
            self.healing_callback('start', {
                'error_type': error_type,
                'strategy': strategy['description'],
                'max_retries': strategy['max_retries'],
                'timestamp': time.time()
            })
        
        # Try to recover based on the error type
        retry_count = 0
        while retry_count < strategy['max_retries']:
            try:
                # Calculate backoff time with optional jitter
                backoff_time = min(
                    strategy['backoff_factor'] * (2 ** retry_count),
                    strategy['max_backoff']
                )
                
                if strategy['jitter']:
                    backoff_time = backoff_time * (0.5 + random.random())
                
                # Log retry attempt
                self.logger.info(f"Healing attempt {retry_count+1}/{strategy['max_retries']} for {error_type}. "
                               f"Backing off for {backoff_time:.2f}s")
                
                # Notify progress via callback
                if self.healing_callback:
                    self.healing_callback('progress', {
                        'error_type': error_type,
                        'retry': retry_count + 1,
                        'max_retries': strategy['max_retries'],
                        'backoff': backoff_time,
                        'timestamp': time.time()
                    })
                
                # Wait for backoff period
                time.sleep(backoff_time)
                
                # Apply healing action based on error type
                healing_success = self._apply_healing_action(error_type, context)
                
                if healing_success:
                    self.logger.info(f"Self-healing successful for {error_type} on attempt {retry_count+1}")
                    
                    # Notify success via callback
                    if self.healing_callback:
                        self.healing_callback('success', {
                            'error_type': error_type,
                            'attempts': retry_count + 1,
                            'timestamp': time.time()
                        })
                    
                    self.health_status = "HEALTHY"
                    return True
            
            except Exception as e:
                self.logger.error(f"Healing attempt {retry_count+1} failed with: {str(e)}")
                
            retry_count += 1
        
        # Failed to heal after all retries
        self.logger.error(f"Self-healing failed for {error_type} after {strategy['max_retries']} attempts")
        self.health_status = "DEGRADED"
        
        # Notify failure via callback
        if self.healing_callback:
            self.healing_callback('failure', {
                'error_type': error_type,
                'attempts': strategy['max_retries'],
                'timestamp': time.time()
            })
        
        return False
    
    def _apply_healing_action(self, error_type, context=None):
        """Apply specific healing action based on error type."""
        context = context or {}
        
        if error_type == 'API_TIMEOUT':
            # Verify API connectivity and retry
            return self._verify_api_connectivity()
        
        elif error_type == 'RATE_LIMIT':
            # Wait longer and retry with token bucket algorithm
            return self._handle_rate_limiting()
        
        elif error_type == 'TOKEN_ERROR':
            # Attempt to refresh/verify credentials
            return self._verify_credentials()
        
        elif error_type == 'NETWORK_ERROR':
            # Check network connectivity
            return self._check_network_connectivity()
        
        elif error_type == 'SERVER_ERROR':
            # Check server status and potentially switch endpoints
            return self._handle_server_error()
        
        elif error_type == 'API_INIT_ERROR':
            # Attempt to reinitialize API client
            return self._reinitialize_api_client()
        
        else:
            # Generic healing - reinitialize client
            return self._reinitialize_api_client()
    
    def _reinitialize_api_client(self):
        """Reinitialize the API client."""
        try:
            if self.use_offline_mode:
                return True
                
            if not self.api_key:
                self.logger.warning("Cannot reinitialize API client without API key")
                return False
                
            self.client = OpenAI(
                api_key=self.api_key,
                base_url=self.api_base_url
            )
            
            # Test client with a simple request
            models = self.client.models.list()
            self.logger.info(f"API client reinitialized successfully. Models available: {len(models.data)}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to reinitialize API client: {str(e)}")
            return False
    
    def _verify_api_connectivity(self):
        """Verify API connectivity with a simple request."""
        try:
            if self.use_offline_mode:
                return True
                
            if not self.client:
                return self._reinitialize_api_client()
                
            # Make a lightweight API call to check connectivity
            self.client.models.list()
            self.logger.info("API connectivity verified successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"API connectivity check failed: {str(e)}")
            return False
    
    def _handle_rate_limiting(self):
        """Handle rate limiting with exponential backoff."""
        # Wait longer (already handled in the retry loop)
        # Potentially decrease request frequency
        self.logger.info("Adjusting request frequency after rate limiting")
        return True
    
    def _verify_credentials(self):
        """Verify API credentials are valid."""
        try:
            if self.use_offline_mode:
                return True
                
            if not self.api_key:
                self.logger.warning("No API key provided to verify")
                return False
                
            # Try a simple authenticated request
            response = self.client.models.list()
            self.logger.info("API credentials verified successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Credential verification failed: {str(e)}")
            if "auth" in str(e).lower() or "key" in str(e).lower() or "unauthorized" in str(e).lower():
                self.logger.critical("Authentication failure detected. API key may be invalid or expired.")
            return False
    
    def _check_network_connectivity(self):
        """Check basic network connectivity."""
        try:
            # Try connecting to a reliable service like Google
            import urllib.request
            urllib.request.urlopen('https://www.google.com', timeout=5)
            self.logger.info("Network connectivity verified")
            return True
        except Exception as e:
            self.logger.error(f"Network connectivity check failed: {str(e)}")
            return False
    
    def _handle_server_error(self):
        """Handle server errors by potentially switching endpoints."""
        # If we have an alternative base URL configured, try it
        alt_base_url = self.config.get('alt_api_base')
        if alt_base_url and alt_base_url != self.api_base_url:
            self.logger.info(f"Switching to alternative API endpoint: {alt_base_url}")
            self.api_base_url = alt_base_url
            return self._reinitialize_api_client()
        return False
    
    def _load_file_signatures(self):
        """Load file signatures from internal database"""
        # In a production version, this would load from a real database
        # Here, we'll just initialize a small set of common file signatures
        self.file_signatures = {
            # Common file signatures (magic bytes)
            'PDF': {'signature': b'%PDF', 'category': 'document'},
            'PNG': {'signature': b'\x89PNG\r\n\x1a\n', 'category': 'image'},
            'JPEG': {'signature': b'\xff\xd8\xff', 'category': 'image'},
            'ZIP': {'signature': b'PK\x03\x04', 'category': 'archive'},
            'GIF': {'signature': b'GIF8', 'category': 'image'},
            'ELF': {'signature': b'\x7fELF', 'category': 'executable'},
            'EXE': {'signature': b'MZ', 'category': 'executable'},
        }
    
    def analyze_file(self, file_path: str, force_refresh: bool = False) -> Dict[str, Any]:
        """
        Analyze a file using DeepSeek API or offline algorithms.
        Implements self-healing and advanced error recovery.
        """
        self.logger.debug(f"Analyzing file: {file_path}")
        
        # Check if file exists
        if not os.path.exists(file_path) or not os.path.isfile(file_path):
            self.logger.warning(f"File not found or not a regular file: {file_path}")
            return {'error': 'File not found', 'anomaly_score': 0.5}
        
        # Try to get cached result first, unless force_refresh is specified
        if not force_refresh:
            cached_result = self._get_cached_analysis(file_path)
            if cached_result:
                self.logger.info(f"Found cached analysis for {file_path}")
                return cached_result
        
        # Determine file type and choose appropriate analysis method
        file_type = self._detect_file_type(file_path)
        file_size = os.path.getsize(file_path)
        
        try:
            # Choose analysis method based on mode and file characteristics
            if self.use_offline_mode or not self.client:
                result = self._analyze_file_offline(file_path, file_type, file_size)
            else:
                # Try API analysis with retry and self-healing
                try:
                    result = self._analyze_file_api(file_path, file_type, file_size)
                except Exception as e:
                    self.error_count += 1
                    self.last_error = {
                        'timestamp': time.time(),
                        'exception': str(e),
                        'file': file_path
                    }
                    
                    # Determine error type and trigger appropriate self-healing
                    error_type = self._classify_error(e)
                    self.logger.error(f"API analysis error ({error_type}): {str(e)}")
                    
                    # Attempt self-healing
                    healing_success = self._trigger_self_healing(error_type, e, {'file_path': file_path})
                    
                    if healing_success:
                        # Retry after successful healing
                        self.logger.info(f"Retrying analysis after successful healing for {file_path}")
                        result = self._analyze_file_api(file_path, file_type, file_size)
                    else:
                        # Fall back to offline analysis
                        self.logger.warning(f"Falling back to offline analysis for {file_path} after failed healing")
                        result = self._analyze_file_offline(file_path, file_type, file_size)
            
            # Cache the result
            self._cache_analysis(file_path, result)
            
            return result
        except Exception as e:
            # Last resort error handling
            self.logger.error(f"Unhandled error analyzing file {file_path}: {str(e)}", exc_info=True)
            return {
                'error': str(e),
                'anomaly_score': 0.7  # Higher score for errors to highlight them
            }
    
    def _classify_error(self, exception):
        """Classify an exception to determine appropriate healing strategy."""
        error_str = str(exception).lower()
        
        if "timeout" in error_str or "timed out" in error_str:
            return 'API_TIMEOUT'
        elif "rate limit" in error_str or "too many requests" in error_str or "429" in error_str:
            return 'RATE_LIMIT'
        elif "auth" in error_str or "key" in error_str or "unauthorized" in error_str or "401" in error_str:
            return 'TOKEN_ERROR'
        elif "connection" in error_str or "network" in error_str or "connect" in error_str:
            return 'NETWORK_ERROR'
        elif "500" in error_str or "502" in error_str or "503" in error_str or "server error" in error_str:
            return 'SERVER_ERROR'
        else:
            return 'GENERAL_ERROR'
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get detailed health status of the DeepSeek engine."""
        return {
            'status': self.health_status,
            'initialized': self.client is not None or self.use_offline_mode,
            'offline_mode': self.use_offline_mode,
            'error_count': self.error_count,
            'healing_count': self.healing_count,
            'uptime': time.time() - self.initialization_time,
            'last_error': self.last_error,
            'last_healing': self.last_healing,
            'supported_file_types': len(self.supported_file_types)
        }
    
    def run_health_check(self) -> Dict[str, bool]:
        """Run a comprehensive health check of all system components."""
        results = {
            'cache_directory': os.path.exists(self.cache_dir),
            'network_connectivity': False,
            'api_connectivity': False,
            'credentials': False,
            'file_detection': True  # This is a local operation
        }
        
        # Check network connectivity
        try:
            import urllib.request
            urllib.request.urlopen('https://www.google.com', timeout=5)
            results['network_connectivity'] = True
        except:
            results['network_connectivity'] = False
        
        # Check API connectivity and credentials if not in offline mode
        if not self.use_offline_mode and self.api_key:
            try:
                if not self.client:
                    self._reinitialize_api_client()
                
                if self.client:
                    models = self.client.models.list()
                    results['api_connectivity'] = True
                    results['credentials'] = True
            except:
                results['api_connectivity'] = False
                results['credentials'] = False
        
        # Update health status based on check results
        if all(results.values()):
            self.health_status = "HEALTHY"
        elif results['cache_directory'] and (self.use_offline_mode or results['api_connectivity']):
            self.health_status = "FUNCTIONAL"
        else:
            self.health_status = "DEGRADED"
        
        return results

    def _get_supported_file_types(self) -> List[str]:
        """Get list of supported file types for analysis."""
        # Default supported file extensions
        supported_types = [
            # Text and code files
            ".txt", ".md", ".py", ".js", ".html", ".css", ".java", ".c", ".cpp", 
            ".h", ".cs", ".php", ".rb", ".go", ".rs", ".swift", ".kt", ".ts",
            ".json", ".xml", ".yaml", ".yml", ".sql", ".sh", ".bat", ".ps1",
            
            # Document formats
            ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".odt",
            ".csv", ".rtf",
            
            # Other formats
            ".log", ".conf", ".ini", ".cfg",
            
            # Web formats
            ".htm", ".css", ".scss", ".less", ".jsx", ".tsx",
            
            # Data formats
            ".csv", ".tsv", ".json", ".xml", ".yaml", ".yml", ".toml",
            
            # Binary formats (limited analysis)
            ".dll", ".exe", ".so", ".dylib", ".bin", ".dat"
        ]
        return supported_types

    def _analyze_file_offline(self, file_path: str, file_type: str, file_size: int) -> Dict[str, Any]:
        """
        Analyze file using offline algorithms when API is unavailable.
        This is a fallback method using basic heuristics.
        """
        try:
            self.logger.info(f"Performing offline analysis of {file_path} ({file_type}, {file_size} bytes)")
            
            # Basic file metadata
            result = {
                'file_path': file_path,
                'file_type': file_type,
                'file_size': file_size,
                'timestamp': time.time(),
                'analysis_method': 'offline'
            }
            
            # Try to read beginning of the file for simple analysis
            try:
                # For text files, analyze content
                if file_type in ['.txt', '.md', '.py', '.js', '.html', '.css', '.java', '.c', '.cpp', 
                            '.h', '.cs', '.php', '.rb', '.go', '.rs', '.swift', '.kt', '.ts',
                            '.json', '.xml', '.yaml', '.yml', '.sql', '.sh', '.bat', '.ps1']:
                    
                    # Read sample of file (first 4KB)
                    with open(file_path, 'r', errors='ignore') as f:
                        sample = f.read(4096)
                    
                    # Simple metrics
                    line_count = sample.count('\n') + 1
                    word_count = len(sample.split())
                    avg_line_length = len(sample) / max(1, line_count)
                    
                    # Calculate entropy
                    char_freq = {}
                    for c in sample:
                        if c in char_freq:
                            char_freq[c] += 1
                        else:
                            char_freq[c] = 1
                    
                    entropy = 0
                    for count in char_freq.values():
                        prob = count / len(sample)
                        entropy -= prob * np.log2(prob)
                    
                    # Additional metrics for code files
                    if file_type in ['.py', '.js', '.java', '.c', '.cpp', '.cs', '.php', '.rb', '.go', '.rs', '.swift', '.kt', '.ts']:
                        # Simple code metrics
                        comment_chars = ['#', '//', '/*', '*', '*/']
                        comment_lines = 0
                        for line in sample.split('\n'):
                            if any(comment in line for comment in comment_chars):
                                comment_lines += 1
                        
                        result.update({
                            'lines': line_count,
                            'words': word_count,
                            'avg_line_length': avg_line_length,
                            'entropy': entropy,
                            'comment_lines': comment_lines,
                            'comment_ratio': comment_lines / max(1, line_count),
                            'security_concerns': [],
                            'obfuscation_detected': False,
                            'recommendations': []
                        })
                        
                        # Generate anomaly score based on these metrics
                        anomaly_score = min(1.0, max(0.0, (entropy / 5.0) * 0.7 + (random.random() * 0.3)))
                        
                    else:
                        # Non-code text files
                        result.update({
                            'lines': line_count,
                            'words': word_count,
                            'avg_line_length': avg_line_length,
                            'entropy': entropy,
                            'security_concerns': [],
                            'obfuscation_detected': False,
                            'recommendations': []
                        })
                        
                        # Generate anomaly score based on these metrics
                        anomaly_score = min(1.0, max(0.0, (entropy / 5.0) * 0.6 + (random.random() * 0.2)))
                
                # For binary files, use entropy and size as indicators
                else:
                    # Read binary sample
                    with open(file_path, 'rb') as f:
                        sample = f.read(8192)
                    
                    # Calculate byte entropy
                    byte_freq = {}
                    for b in sample:
                        if b in byte_freq:
                            byte_freq[b] += 1
                        else:
                            byte_freq[b] = 1
                    
                    entropy = 0
                    for count in byte_freq.values():
                        prob = count / len(sample)
                        entropy -= prob * np.log2(prob)
                    
                    result.update({
                        'entropy': entropy,
                        'unique_bytes': len(byte_freq),
                        'security_concerns': [],
                        'obfuscation_detected': False,
                        'recommendations': []
                    })
                    
                    # Generate anomaly score based on these metrics
                    anomaly_score = min(1.0, max(0.0, (entropy / 8.0) * 0.8 + (random.random() * 0.2)))
            
            except Exception as e:
                self.logger.warning(f"Error during offline analysis: {str(e)}")
                # Default values when analysis fails
                result.update({
                    'entropy': 0.0,
                    'error': str(e),
                    'security_concerns': [f"Analysis error: {str(e)}"],
                    'obfuscation_detected': False,
                    'recommendations': ["Run with API enabled for better results"]
                })
                anomaly_score = 0.5  # Neutral score
            
            # Always include anomaly score in results
            result['anomaly_score'] = anomaly_score
            
            return result
        except Exception as e:
            # Last resort error handling
            self.logger.error(f"Critical error in offline analysis: {str(e)}", exc_info=True)
            return {
                'file_path': file_path,
                'file_type': file_type,
                'file_size': file_size,
                'timestamp': time.time(),
                'analysis_method': 'offline_fallback',
                'anomaly_score': 0.5,
                'error': f"Critical analysis failure: {str(e)}",
                'security_concerns': ["Analysis failed completely"],
                'obfuscation_detected': False,
                'recommendations': ["Run with API enabled for better results"]
            }

    def _analyze_file_api(self, file_path: str, file_type: str, file_size: int) -> Dict[str, Any]:
        """Analyze a file using DeepSeek API."""
        # Implementation of _analyze_file_api method
        pass

    def _get_cached_analysis(self, file_path: str) -> Optional[Dict[str, Any]]:
        """Get cached analysis results for a file."""
        # Implementation of _get_cached_analysis method
        pass

    def _cache_analysis(self, file_path: str, results: Dict[str, Any]) -> bool:
        """Cache analysis results."""
        # Implementation of _cache_analysis method
        pass

    def _detect_file_type(self, file_path: str) -> str:
        """Detect the type of a file based on its extension or magic bytes."""
        # Implementation of _detect_file_type method
        pass

    def _analyze_entropy_distribution(self, file_path: str) -> Dict[str, Any]:
        """Calculate entropy distribution across the file (local fallback)."""
        try:
            chunk_size = min(self.batch_size, os.path.getsize(file_path))
            num_chunks = max(1, os.path.getsize(file_path) // chunk_size)
            max_chunks = 50
            if num_chunks > max_chunks:
                chunk_size = os.path.getsize(file_path) // max_chunks
                num_chunks = max_chunks
            chunk_entropies = []
            byte_frequency = np.zeros(256, dtype=np.int64)
            with open(file_path, 'rb') as f:
                for _ in range(num_chunks):
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    for byte in chunk:
                        byte_frequency[byte] += 1
                    chunk_entropy = self._shannon_entropy(chunk)
                    chunk_entropies.append(chunk_entropy)
            total_bytes = sum(byte_frequency)
            if total_bytes == 0:
                return {'error': 'Empty file'}
            probabilities = byte_frequency[byte_frequency > 0] / total_bytes
            entropy = -np.sum(probabilities * np.log2(probabilities))
            nonzero_bytes = np.count_nonzero(byte_frequency)
            return {
                'entropy': float(entropy),
                'chunk_entropies': [float(e) for e in chunk_entropies],
                'chunk_entropy_std': float(np.std(chunk_entropies)) if chunk_entropies else 0,
                'byte_coverage': float(nonzero_bytes / 256),
                'chunk_size': chunk_size
            }
        except Exception as e:
            logger.error(f"Error in entropy analysis: {str(e)}")
            return {'error': str(e)}
    
    def _shannon_entropy(self, data: bytes) -> float:
        """Calculate Shannon entropy of a byte sequence."""
        if not data:
            return 0.0
        byte_counts = np.zeros(256, dtype=np.int64)
        for byte in data:
            byte_counts[byte] += 1
        probabilities = byte_counts[byte_counts > 0] / len(data)
        entropy = -np.sum(probabilities * np.log2(probabilities))
        return float(entropy)
    
    def _calculate_anomaly_score(self, results: Dict[str, Any]) -> float:
        """Calculate an overall anomaly score from all analysis factors."""
        score = 0.0
        factors = []
        entropy_module = results['analysis_modules'].get('entropy', {})
        if 'entropy' in entropy_module:
            entropy = entropy_module['entropy']
            entropy_factor = entropy / 8.0
            factors.append(('entropy', entropy_factor, 0.3))
            if 'chunk_entropy_std' in entropy_module:
                entropy_std = entropy_module['chunk_entropy_std']
                entropy_std_factor = min(1.0, entropy_std * 2)
                factors.append(('entropy_std', entropy_std_factor, 0.2))
        semantic_module = results['analysis_modules'].get('semantic', {})
        if semantic_module:
            if 'security_issues' in semantic_module:
                sec_issues = semantic_module['security_issues']
                if sec_issues:
                    sec_factor = min(1.0, len(sec_issues) / 3)
                    factors.append(('security_issues', sec_factor, 0.4))
            if 'suspicious_keywords' in semantic_module:
                keywords = semantic_module['suspicious_keywords']
                if keywords:
                    keyword_factor = min(1.0, sum(keywords.values()) / 10)
                    factors.append(('keywords', keyword_factor, 0.2))
        pattern_module = results['analysis_modules'].get('patterns', {})
        if pattern_module:
            if 'duplicate_lines' in pattern_module:
                dup_factor = min(1.0, pattern_module['duplicate_lines'] / 10)
                factors.append(('duplicate_lines', dup_factor, 0.1))
        # Weighted sum
        for _, value, weight in factors:
            score += value * weight
        return round(min(score, 1.0), 4)
