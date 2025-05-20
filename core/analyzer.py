import os
import threading
import queue
import time
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Dict, List, Set, Optional, Callable, Any, Tuple
from pathlib import Path

import numpy as np
from tqdm import tqdm

from core.deepseek_hooks import DeepSeekEngine

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('SpecterWire.Analyzer')

@dataclass
class ScanResult:
    """Container for file scan results"""
    path: str
    file_type: str
    size: int
    entropy: float
    anomaly_score: float
    deepseek_analysis: Dict[str, Any]
    timestamp: float
    scan_duration: float
    tags: List[str]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation"""
        return {
            'path': self.path,
            'file_type': self.file_type,
            'size': self.size,
            'entropy': self.entropy,
            'anomaly_score': self.anomaly_score,
            'deepseek_analysis': self.deepseek_analysis,
            'timestamp': self.timestamp,
            'scan_duration': self.scan_duration,
            'tags': self.tags
        }

class AnalyzerEngine:
    """Core analyzer engine for SpecterWire"""
    
    def __init__(self, config: Dict[str, Any], plugin_manager=None):
        self.config = config
        self.plugin_manager = plugin_manager
        # Pass the correct DeepSeek config dictionary for v3.1
        deepseek_config = config.get('deepseek_config', {})
        # Support legacy key as fallback
        if not deepseek_config and 'deepseek_api_key' in config:
            deepseek_config = {'api_key': config['deepseek_api_key']}
        self.deepseek = DeepSeekEngine(deepseek_config)
        
        # Queue for scan tasks
        self.task_queue = queue.Queue()
        
        # Thread pool for file processing
        self.max_workers = config.get('max_workers', os.cpu_count())
        self.executor = ThreadPoolExecutor(max_workers=self.max_workers)
        
        # Task tracking
        self.active_tasks = set()
        self.completed_tasks = set()
        self.results_cache = {}
        
        # Stop flag for scan thread
        self.stop_requested = threading.Event()
        
        # Locks
        self.results_lock = threading.Lock()
        self.tasks_lock = threading.Lock()
        
        # Callbacks
        self.progress_callback = None
        self.result_callback = None
        
        logger.info(f"Analyzer initialized with {self.max_workers} workers")
    
    def set_callbacks(self, progress_callback=None, result_callback=None):
        """Set callbacks for scan progress and results"""
        self.progress_callback = progress_callback
        self.result_callback = result_callback
    
    def scan_directory(self, directory_path: str, recursive: bool = True, 
                      file_patterns: List[str] = None) -> List[str]:
        """
        Schedule a directory scan and return a task ID
        """
        task_id = f"scan_{int(time.time() * 1000)}"
        
        # Default to all files if no patterns specified
        if not file_patterns:
            file_patterns = ['*']
            
        scan_task = {
            'task_id': task_id,
            'type': 'directory',
            'path': directory_path,
            'recursive': recursive,
            'file_patterns': file_patterns,
            'timestamp': time.time()
        }
        
        # Add to task queue
        self.task_queue.put(scan_task)
        
        with self.tasks_lock:
            self.active_tasks.add(task_id)
        
        logger.info(f"Scheduled directory scan: {directory_path} (Task ID: {task_id})")
        return task_id
    
    def scan_file(self, file_path: str) -> str:
        """
        Schedule a single file scan and return a task ID
        """
        task_id = f"scan_{int(time.time() * 1000)}"
        
        scan_task = {
            'task_id': task_id,
            'type': 'file',
            'path': file_path,
            'timestamp': time.time()
        }
        
        # Add to task queue
        self.task_queue.put(scan_task)
        
        with self.tasks_lock:
            self.active_tasks.add(task_id)
            
        logger.info(f"Scheduled file scan: {file_path} (Task ID: {task_id})")
        return task_id
    
    def start_scanning_thread(self):
        """Start the background scanning thread"""
        self.stop_requested.clear()
        scan_thread = threading.Thread(target=self._scanning_worker, daemon=True)
        scan_thread.start()
        logger.info("Scanning thread started")
        return scan_thread
    
    def stop_scanning_thread(self):
        """Signal the scanning thread to stop"""
        self.stop_requested.set()
        
        # Shutdown the thread pool executor
        if hasattr(self, 'executor'):
            self.executor.shutdown(wait=False)
            
        logger.info("Requested scanning thread to stop")
    
    def _scanning_worker(self):
        """Background worker that processes the scan queue"""
        logger.info("Scanning worker started")
        
        while not self.stop_requested.is_set():
            try:
                # Get task with 1-second timeout to allow checking stop flag
                task = self.task_queue.get(timeout=1)
                
                if task['type'] == 'directory':
                    self._process_directory_scan(task)
                elif task['type'] == 'file':
                    self._process_file_scan(task)
                
                self.task_queue.task_done()
            
            except queue.Empty:
                # No tasks available, just continue
                continue
            except Exception as e:
                logger.error(f"Error in scanning worker: {str(e)}", exc_info=True)
        
        logger.info("Scanning worker stopped")
    
    def _process_directory_scan(self, task):
        """Process a directory scan task"""
        directory_path = task['path']
        recursive = task['recursive']
        patterns = task['file_patterns']
        task_id = task['task_id']
        
        try:
            # Find all files matching the patterns
            all_files = []
            base_path = Path(directory_path)
            
            if not base_path.exists():
                logger.error(f"Directory not found: {directory_path}")
                return
            
            logger.info(f"Starting directory scan of {directory_path}")
            
            if recursive:
                for root, _, files in os.walk(directory_path):
                    for file in files:
                        # Check against patterns (simplistic, could be improved)
                        if any(file.endswith(p.replace('*', '')) for p in patterns) or '*' in patterns:
                            all_files.append(os.path.join(root, file))
            else:
                for file in os.listdir(directory_path):
                    file_path = os.path.join(directory_path, file)
                    if os.path.isfile(file_path):
                        if any(file.endswith(p.replace('*', '')) for p in patterns) or '*' in patterns:
                            all_files.append(file_path)
            
            # Submit all files for scanning
            file_tasks = []
            progress_bar = None
            
            if self.progress_callback:
                self.progress_callback('start', {'task_id': task_id, 'total_files': len(all_files)})
                
            for file_path in all_files:
                # Create subtask for file
                file_task = {
                    'task_id': f"{task_id}_file_{len(file_tasks)}",
                    'parent_task_id': task_id,
                    'type': 'file',
                    'path': file_path,
                    'timestamp': time.time()
                }
                
                # Submit to thread pool
                future = self.executor.submit(self._scan_file, file_task)
                file_tasks.append((file_task, future))
            
            # Process results as they complete
            results = []
            
            for idx, (file_task, future) in enumerate(file_tasks):
                try:
                    result = future.result()
                    if result:
                        results.append(result)
                        
                        # Call result callback if provided
                        if self.result_callback:
                            self.result_callback(result)
                    
                    # Update progress
                    if self.progress_callback:
                        progress = {
                            'task_id': task_id,
                            'processed': idx + 1,
                            'total': len(file_tasks),
                            'current_file': file_task['path']
                        }
                        self.progress_callback('progress', progress)
                        
                except Exception as e:
                    logger.error(f"Error processing file {file_task['path']}: {str(e)}", exc_info=True)
            
            # Store aggregated results
            with self.results_lock:
                self.results_cache[task_id] = {
                    'task_id': task_id,
                    'type': 'directory',
                    'path': directory_path,
                    'file_count': len(all_files),
                    'processed_count': len(results),
                    'timestamp': task['timestamp'],
                    'duration': time.time() - task['timestamp'],
                    'results': results
                }
            
            # Update task status
            with self.tasks_lock:
                if task_id in self.active_tasks:
                    self.active_tasks.remove(task_id)
                    self.completed_tasks.add(task_id)
            
            # Final progress update
            if self.progress_callback:
                self.progress_callback('complete', {
                    'task_id': task_id,
                    'total_files': len(all_files),
                    'processed_files': len(results),
                    'duration': time.time() - task['timestamp']
                })
                
            logger.info(f"Directory scan completed: {directory_path} - {len(results)}/{len(all_files)} files processed")
            
        except Exception as e:
            logger.error(f"Error scanning directory {directory_path}: {str(e)}", exc_info=True)
    
    def _process_file_scan(self, task):
        """Process a single file scan task"""
        result = self._scan_file(task)
        
        if result and self.result_callback:
            self.result_callback(result)
        
        # Update task status
        task_id = task['task_id']
        with self.tasks_lock:
            if task_id in self.active_tasks:
                self.active_tasks.remove(task_id)
                self.completed_tasks.add(task_id)
    
    def _scan_file(self, task) -> Optional[ScanResult]:
        """
        Perform the actual file scanning and analysis
        """
        file_path = task['path']
        task_id = task['task_id']
        start_time = time.time()
        
        try:
            if not os.path.exists(file_path) or not os.path.isfile(file_path):
                logger.warning(f"File not found or not a file: {file_path}")
                return None
            
            # Get basic file information
            file_stats = os.stat(file_path)
            file_size = file_stats.st_size
            file_extension = os.path.splitext(file_path)[1].lower()
            
            # Skip files that are too large based on config
            max_file_size = self.config.get('max_file_size', 100 * 1024 * 1024)  # Default 100MB
            if file_size > max_file_size:
                logger.warning(f"Skipping file {file_path}: size {file_size} exceeds maximum {max_file_size}")
                return None
                
            # Calculate entropy
            entropy = self._calculate_entropy(file_path)
            
            # Run DeepSeek analysis with error handling
            try:
                deepseek_results = self.deepseek.analyze_file(file_path)
                if deepseek_results is None:
                    logger.warning(f"DeepSeek analysis returned None for {file_path}")
                    deepseek_results = {
                        'error': 'Analysis failed',
                        'anomaly_score': 0.5  # Default neutral score
                    }
            except Exception as e:
                logger.error(f"Error in DeepSeek analysis for {file_path}: {str(e)}")
                # Create a minimal result object with error info
                deepseek_results = {
                    'error': str(e),
                    'anomaly_score': 0.5,  # Default neutral score
                    'analysis_method': 'fallback'
                }
            
            # Assign anomaly score based on DeepSeek results and entropy
            anomaly_score = self._calculate_anomaly_score(deepseek_results, entropy, file_extension)
            
            # Apply plugins if available
            tags = []
            if self.plugin_manager:
                plugin_results = self.plugin_manager.run_plugins_on_file(file_path, {
                    'entropy': entropy,
                    'deepseek_results': deepseek_results,
                    'file_size': file_size,
                    'file_extension': file_extension
                })
                
                # Extract tags from plugin results
                if plugin_results and 'tags' in plugin_results:
                    tags = plugin_results['tags']
            
            # Create scan result
            result = ScanResult(
                path=file_path,
                file_type=file_extension,
                size=file_size,
                entropy=entropy,
                anomaly_score=anomaly_score,
                deepseek_analysis=deepseek_results,
                timestamp=time.time(),
                scan_duration=time.time() - start_time,
                tags=tags
            )
            
            # Cache result
            with self.results_lock:
                self.results_cache[task_id] = result.to_dict()
            
            logger.debug(f"Scanned file: {file_path} - Score: {anomaly_score:.2f}")
            return result
            
        except Exception as e:
            logger.error(f"Error scanning file {file_path}: {str(e)}", exc_info=True)
            
            # Create a minimal error result when possible
            try:
                return ScanResult(
                    path=file_path,
                    file_type=os.path.splitext(file_path)[1].lower(),
                    size=os.path.getsize(file_path) if os.path.exists(file_path) else 0,
                    entropy=0.0,
                    anomaly_score=0.7,  # Higher score to highlight errors
                    deepseek_analysis={'error': str(e)},
                    timestamp=time.time(),
                    scan_duration=time.time() - start_time,
                    tags=['error']
                )
            except:
                # Last resort, return None if everything fails
                return None
    
    def _calculate_entropy(self, file_path: str) -> float:
        """
        Calculate Shannon entropy of a file
        """
        try:
            # Use a reasonable chunk size
            chunk_size = 8192
            
            # Initialize frequency dictionary for byte values
            byte_counts = np.zeros(256, dtype=np.int64)
            file_size = 0
            
            # Read file in chunks to avoid memory issues with large files
            with open(file_path, 'rb') as f:
                while chunk := f.read(chunk_size):
                    # Update byte frequency counts
                    for byte in chunk:
                        byte_counts[byte] += 1
                    file_size += len(chunk)
            
            # Calculate probabilities
            if file_size == 0:
                return 0.0
                
            probabilities = byte_counts[byte_counts > 0] / file_size
            
            # Calculate entropy
            entropy = -np.sum(probabilities * np.log2(probabilities))
            return float(entropy)
            
        except Exception as e:
            logger.error(f"Error calculating entropy for {file_path}: {str(e)}", exc_info=True)
            return 0.0
    
    def _calculate_anomaly_score(self, deepseek_results: Dict[str, Any], 
                               entropy: float, file_extension: str) -> float:
        """
        Calculate an overall anomaly score based on multiple factors
        """
        # Defensive check - ensure deepseek_results is a dict
        if deepseek_results is None:
            deepseek_results = {
                'error': 'No analysis results',
                'anomaly_score': 0.5  # Default neutral score
            }
        elif not isinstance(deepseek_results, dict):
            logger.warning(f"Invalid deepseek_results type: {type(deepseek_results)}")
            deepseek_results = {
                'error': 'Invalid analysis results',
                'anomaly_score': 0.5  # Default neutral score
            }
        
        # Entropy contributes to score (normalized to 0-1)
        # 8 is max entropy for a byte
        entropy_score = min(1.0, entropy / 8.0)
        
        # DeepSeek analysis score with defensive handling
        deepseek_score = deepseek_results.get('anomaly_score', 0.0)
        
        # If result has an error, slightly increase the anomaly score
        # to ensure such files receive more attention
        if 'error' in deepseek_results:
            deepseek_score = max(0.5, deepseek_score)
        
        # Weight the components (these could be in config)
        weights = {
            'entropy': 0.3,
            'deepseek': 0.7
        }
        
        # Calculate weighted score with defensive clamping
        try:
            score = (weights['entropy'] * entropy_score) + (weights['deepseek'] * deepseek_score)
        except (TypeError, ValueError) as e:
            logger.warning(f"Error calculating anomaly score: {e}")
            score = 0.5  # Default to neutral
        
        # Normalize to 0-1 range
        return max(0.0, min(1.0, score))
    
    def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """
        Get the status of a specific task
        """
        with self.tasks_lock:
            is_active = task_id in self.active_tasks
            is_completed = task_id in self.completed_tasks
        
        status = "unknown"
        if is_active:
            status = "active"
        elif is_completed:
            status = "completed"
        
        result = None
        with self.results_lock:
            if task_id in self.results_cache:
                result = self.results_cache[task_id]
        
        return {
            "task_id": task_id,
            "status": status,
            "result": result
        }
    
    def get_active_tasks(self) -> List[str]:
        """Get list of active task IDs"""
        with self.tasks_lock:
            return list(self.active_tasks)
    
    def get_completed_tasks(self) -> List[str]:
        """Get list of completed task IDs"""
        with self.tasks_lock:
            return list(self.completed_tasks) 