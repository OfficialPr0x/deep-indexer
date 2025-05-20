import os
import re
import chardet
from typing import Dict, Any
from datetime import datetime
from plugins.base_plugin import AnalysisPlugin

class TextFilePlugin(AnalysisPlugin):
    MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB
    SUSPICIOUS_PATTERNS = [
        r'(?:password|secret|key|token)\s*[=:]\s*[\'"][^\'"]+[\'"]',  # Potential secrets
        r'(?:https?://|ftp://)[^\s/$.?#].[^\s]*',  # URLs
        r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',  # Emails
    ]

    def __init__(self):
        self.patterns = [re.compile(pattern) for pattern in self.SUSPICIOUS_PATTERNS]

    def analyze_file(self, path: str) -> Dict[str, Any]:
        """Analyze text file content with robust error handling and validation."""
        try:
            # Validate file
            if not os.path.exists(path):
                raise FileNotFoundError(f"File not found: {path}")
            
            file_size = os.path.getsize(path)
            if file_size > self.MAX_FILE_SIZE:
                raise ValueError(f"File too large: {file_size} bytes")
            
            # Detect encoding
            with open(path, 'rb') as f:
                raw_content = f.read()
                encoding = chardet.detect(raw_content)['encoding'] or 'utf-8'
            
            # Read and analyze content
            with open(path, 'r', encoding=encoding) as f:
                content = f.read()
            
            # Content analysis
            line_count = len(content.splitlines())
            avg_line_length = len(content) / max(line_count, 1)
            word_count = len(content.split())
            
            # Find suspicious patterns
            matches = []
            for pattern in self.patterns:
                matches.extend(pattern.finditer(content))
            
            # Calculate anomaly score based on findings
            anomaly_factors = [
                bool(matches) * 0.3,  # Suspicious content
                (avg_line_length > 120) * 0.2,  # Unusually long lines
                (word_count == 0 and len(content) > 100) * 0.5,  # Binary-like content
            ]
            anomaly_score = min(1.0, sum(anomaly_factors))
            
            return {
                "path": path,
                "file_type": ".txt",
                "size": file_size,
                "encoding": encoding,
                "line_count": line_count,
                "word_count": word_count,
                "avg_line_length": avg_line_length,
                "suspicious_matches": [
                    {
                        "pattern": m.re.pattern,
                        "line": content.count('\n', 0, m.start()) + 1,
                        "excerpt": content[max(0, m.start()-20):m.end()+20]
                    } for m in matches
                ],
                "anomaly_score": anomaly_score,
                "timestamp": datetime.fromtimestamp(os.path.getmtime(path)).isoformat(),
                "analysis_timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            # Log the error (in production, use proper logging)
            print(f"Error analyzing {path}: {str(e)}")
            return {
                "path": path,
                "error": str(e),
                "error_type": type(e).__name__,
                "timestamp": datetime.utcnow().isoformat()
            }

    @property
    def version(self) -> str:
        return "1.0.0"

    def validate_config(self, config: Dict[str, Any]) -> bool:
        """Validate plugin configuration."""
        required_keys = {'max_file_size', 'allowed_encodings'}
        if not all(key in config for key in required_keys):
            return False
        
        try:
            if not isinstance(config['max_file_size'], int) or config['max_file_size'] <= 0:
                return False
            if not isinstance(config['allowed_encodings'], list) or not config['allowed_encodings']:
                return False
            return True
        except Exception:
            return False 