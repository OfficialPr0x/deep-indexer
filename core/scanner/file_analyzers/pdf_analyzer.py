import PyPDF2
import os

class PDFAnalyzer:
    def analyze(self, path: str):
        try:
            with open(path, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                num_pages = len(reader.pages)
                info = reader.metadata
            return {
                "path": path,
                "file_type": ".pdf",
                "size": os.path.getsize(path),
                "num_pages": num_pages,
                "title": info.title if info else None,
                "author": info.author if info else None,
                "anomaly_score": 0.0,
                "timestamp": os.path.getmtime(path)
            }
        except Exception as e:
            return {"path": path, "error": str(e)} 