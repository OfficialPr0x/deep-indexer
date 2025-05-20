from abc import ABC, abstractmethod
from typing import Dict, Any

class AnalysisPlugin(ABC):
    @abstractmethod
    def analyze_file(self, path: str) -> Dict[str, Any]:
        """Process file and return metadata"""
        
    @property
    @abstractmethod
    def version(self) -> str:
        """Plugin API version"""
        
    @abstractmethod
    def validate_config(self, config: Dict) -> bool:
        """Verify plugin configuration""" 