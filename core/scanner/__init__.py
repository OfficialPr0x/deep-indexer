import os
from core.scanner.file_analyzers.pdf_analyzer import PDFAnalyzer
from core.scanner.file_analyzers.office_analyzer import OfficeAnalyzer
from core.scanner.file_analyzers.source_code_parser import SourceCodeParser
from core.security import ContentSanitizer, InvalidPathError

class DeepScanner:
    def __init__(self, cache=None):
        self._file_handlers = {
            '.pdf': PDFAnalyzer(),
            '.docx': OfficeAnalyzer(),
            '.py': SourceCodeParser()
        }
        self.cache = cache or {}
        self.sanitizer = ContentSanitizer()

    def safe_scan(self, path: str) -> dict:
        path = self.sanitizer.sanitize_path(path)
        if not os.path.exists(path):
            raise FileNotFoundError(f"File not found: {path}")
        ext = os.path.splitext(path)[1].lower()
        if ext not in self._file_handlers:
            raise ValueError(f"Unsupported file type: {ext}")
        if path in self.cache:
            return self.cache[path]
        result = self._file_handlers[ext].analyze(path)
        self.cache[path] = result
        return result 