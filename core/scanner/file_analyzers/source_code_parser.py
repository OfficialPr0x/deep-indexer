import os
import ast

class SourceCodeParser:
    def analyze(self, path: str):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                source = f.read()
            tree = ast.parse(source)
            imports = [n.names[0].name for n in ast.walk(tree) if isinstance(n, ast.Import)]
            func_count = sum(isinstance(n, ast.FunctionDef) for n in ast.walk(tree))
            class_count = sum(isinstance(n, ast.ClassDef) for n in ast.walk(tree))
            return {
                "path": path,
                "file_type": ".py",
                "size": os.path.getsize(path),
                "imports": imports,
                "function_count": func_count,
                "class_count": class_count,
                "anomaly_score": 0.0,
                "timestamp": os.path.getmtime(path)
            }
        except Exception as e:
            return {"path": path, "error": str(e)} 