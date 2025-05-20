#!/usr/bin/env python3
"""
SpecterWire - Entropy Scanner Plugin

This plugin analyzes file entropy patterns and adds specific tags
based on entropy characteristics that may indicate encryption,
compression, or obfuscation.
"""

import os
import logging
import numpy as np
from typing import Dict, Any, List, Tuple

logger = logging.getLogger('SpecterWire.Plugins.EntropyScanner')

class EntropyScanner:
    """
    Plugin for entropy-based analysis and tagging
    """
    
    # Plugin metadata
    NAME = "Entropy Scanner"
    VERSION = "1.0.0"
    DESCRIPTION = "Analyzes entropy patterns in files to identify encryption, compression, or obfuscation"
    AUTHOR = "SpecterWire Team"
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize the plugin
        
        Args:
            config: Optional configuration dictionary
        """
        self.config = config or {}
        
        # Default thresholds
        self.thresholds = {
            'high_entropy': 7.5,           # Threshold for very high entropy
            'encrypted_threshold': 7.8,    # Likely encrypted/compressed content
            'compressed_threshold': 7.0,   # Likely compressed content
            'low_entropy': 3.0,            # Low entropy (repetitive content)
            'chunk_variance': 0.5,         # High variance between chunks
            'chunk_size': 4096,            # Chunk size for analysis
            'min_size': 1024,              # Minimum file size to analyze
        }
        
        # Update thresholds from config if provided
        if 'thresholds' in self.config:
            self.thresholds.update(self.config['thresholds'])
        
        logger.info(f"Entropy Scanner plugin initialized with thresholds: {self.thresholds}")
    
    def analyze_file(self, file_path: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Analyze a file and return results
        
        Args:
            file_path: Path to the file to analyze
            context: Additional context data from the main analyzer
            
        Returns:
            Analysis results dictionary
        """
        results = {
            'tags': [],
            'details': {},
            'plugin_name': self.NAME,
            'plugin_version': self.VERSION
        }
        
        # Skip if file doesn't exist
        if not os.path.exists(file_path) or not os.path.isfile(file_path):
            logger.warning(f"File not found: {file_path}")
            return results
        
        # Get file size
        file_size = os.path.getsize(file_path)
        
        # Skip files that are too small
        if file_size < self.thresholds['min_size']:
            logger.debug(f"File too small for entropy analysis: {file_path}")
            return results
        
        try:
            # Check if entropy is already calculated by the main analyzer
            if context and 'entropy' in context:
                entropy = context['entropy']
                chunk_entropies = None
                
                # Try to get chunk entropies if available
                if 'deepseek_results' in context:
                    deepseek = context['deepseek_results']
                    entropy_module = deepseek.get('analysis_modules', {}).get('entropy', {})
                    if entropy_module:
                        chunk_entropies = entropy_module.get('chunk_entropies', [])
            else:
                # Calculate entropy ourselves
                entropy, chunk_entropies = self._calculate_entropy(file_path)
            
            # Analyze entropy results
            results['details']['entropy'] = entropy
            results['details']['entropy_classification'] = self._classify_entropy(entropy)
            
            # Analyze chunk entropy variance if available
            if chunk_entropies:
                entropy_variance = np.std(chunk_entropies)
                results['details']['entropy_variance'] = float(entropy_variance)
                
                if entropy_variance > self.thresholds['chunk_variance']:
                    results['details']['high_variance'] = True
                    results['tags'].append('high_entropy_variance')
                    
                    # Check for potential steganography or hidden data
                    if self._detect_anomalous_chunks(chunk_entropies):
                        results['tags'].append('potential_hidden_data')
            
            # Add tags based on entropy values
            if entropy > self.thresholds['encrypted_threshold']:
                results['tags'].append('likely_encrypted')
            elif entropy > self.thresholds['compressed_threshold']:
                results['tags'].append('likely_compressed')
            elif entropy > self.thresholds['high_entropy']:
                results['tags'].append('high_entropy')
            elif entropy < self.thresholds['low_entropy']:
                results['tags'].append('low_entropy')
                
            # Check for specific patterns
            file_type = os.path.splitext(file_path)[1].lower()
            
            # Suspicious encrypted data in non-encrypted file types
            if entropy > self.thresholds['encrypted_threshold']:
                if file_type not in ['.zip', '.gz', '.xz', '.bz2', '.7z', '.jpg', '.png', '.mp3', '.mp4']:
                    results['tags'].append('suspicious_high_entropy')
            
            # Add specific file type tags
            if file_type == '.py' and entropy > 6.5:
                results['tags'].append('obfuscated_python')
            
            logger.debug(f"Entropy analysis for {file_path}: {entropy:.2f}")
            
        except Exception as e:
            logger.error(f"Error analyzing entropy for {file_path}: {str(e)}")
        
        return results
    
    def _calculate_entropy(self, file_path: str) -> Tuple[float, List[float]]:
        """
        Calculate Shannon entropy of a file
        
        Args:
            file_path: Path to the file
            
        Returns:
            Overall entropy and list of chunk entropies
        """
        chunk_size = self.thresholds['chunk_size']
        chunk_entropies = []
        
        # Initialize byte counters
        total_byte_counts = np.zeros(256, dtype=np.int64)
        total_bytes = 0
        
        try:
            with open(file_path, 'rb') as f:
                # Read and analyze chunks
                while chunk := f.read(chunk_size):
                    # Convert to numpy array for faster processing
                    chunk_array = np.frombuffer(chunk, dtype=np.uint8)
                    
                    # Update total counts
                    unique, counts = np.unique(chunk_array, return_counts=True)
                    for byte, count in zip(unique, counts):
                        total_byte_counts[byte] += count
                    
                    total_bytes += len(chunk)
                    
                    # Calculate chunk entropy
                    chunk_entropy = self._shannon_entropy(chunk_array)
                    chunk_entropies.append(chunk_entropy)
            
            # Calculate overall entropy
            if total_bytes == 0:
                return 0.0, []
                
            probabilities = total_byte_counts[total_byte_counts > 0] / total_bytes
            entropy = -np.sum(probabilities * np.log2(probabilities))
            
            return float(entropy), chunk_entropies
            
        except Exception as e:
            logger.error(f"Error calculating entropy: {str(e)}")
            return 0.0, []
    
    def _shannon_entropy(self, data: np.ndarray) -> float:
        """
        Calculate Shannon entropy of a byte array
        
        Args:
            data: Numpy array of bytes
            
        Returns:
            Entropy value between 0 and 8
        """
        if len(data) == 0:
            return 0.0
            
        # Get byte frequencies
        unique, counts = np.unique(data, return_counts=True)
        probabilities = counts / len(data)
        
        # Calculate entropy
        entropy = -np.sum(probabilities * np.log2(probabilities))
        return float(entropy)
    
    def _classify_entropy(self, entropy: float) -> str:
        """
        Classify entropy value into categories
        
        Args:
            entropy: Entropy value
            
        Returns:
            Classification string
        """
        if entropy > self.thresholds['encrypted_threshold']:
            return "encrypted_or_compressed"
        elif entropy > self.thresholds['compressed_threshold']:
            return "likely_compressed"
        elif entropy > self.thresholds['high_entropy']:
            return "high"
        elif entropy < self.thresholds['low_entropy']:
            return "low"
        else:
            return "normal"
    
    def _detect_anomalous_chunks(self, chunk_entropies: List[float]) -> bool:
        """
        Detect suspicious patterns in chunk entropy distribution
        that might indicate steganography or hidden data
        
        Args:
            chunk_entropies: List of entropy values for each chunk
            
        Returns:
            True if suspicious patterns found
        """
        if not chunk_entropies or len(chunk_entropies) < 3:
            return False
        
        try:
            # Convert to numpy array
            entropies = np.array(chunk_entropies)
            
            # Calculate mean and standard deviation
            mean = np.mean(entropies)
            std = np.std(entropies)
            
            if std < 0.1:
                # Very uniform entropy, not suspicious
                return False
                
            # Look for outliers
            z_scores = np.abs((entropies - mean) / std)
            outliers = np.where(z_scores > 2.5)[0]
            
            # If we have significant outliers, flag as suspicious
            if len(outliers) > 0 and len(outliers) < len(entropies) * 0.2:
                return True
                
            # Look for sudden changes
            diffs = np.abs(np.diff(entropies))
            max_diff = np.max(diffs)
            
            # Significant jump in entropy between adjacent chunks
            if max_diff > 1.5:
                return True
                
            return False
            
        except Exception as e:
            logger.error(f"Error detecting anomalous chunks: {str(e)}")
            return False

# Plugin entry point - required for the plugin system
def get_plugin():
    """Return the plugin class for the plugin system"""
    return EntropyScanner 