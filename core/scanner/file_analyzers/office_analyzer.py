import os
from docx import Document

class OfficeAnalyzer:
    def analyze(self, path: str):
        try:
            doc = Document(path)
            word_count = sum(len(p.text.split()) for p in doc.paragraphs)
            props = doc.core_properties
            return {
                "path": path,
                "file_type": ".docx",
                "size": os.path.getsize(path),
                "word_count": word_count,
                "title": props.title,
                "author": props.author,
                "anomaly_score": 0.0,
                "timestamp": os.path.getmtime(path)
            }
        except Exception as e:
            return {"path": path, "error": str(e)} 