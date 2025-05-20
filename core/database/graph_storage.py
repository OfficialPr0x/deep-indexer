import sqlite3
import json
import threading
from typing import Dict, List, Any, Optional
from datetime import datetime
from contextlib import contextmanager

class GraphStorageError(Exception):
    """Base exception for graph storage errors"""
    pass

class GraphStorage:
    def __init__(self, db_path='deepindexer.db', max_connections=5):
        """Initialize graph storage with connection pooling."""
        self.db_path = db_path
        self.max_connections = max_connections
        self._connection_pool = []
        self._pool_lock = threading.Lock()
        self._init_schema()

    def _get_connection(self):
        """Get a connection from the pool or create a new one."""
        with self._pool_lock:
            if self._connection_pool:
                return self._connection_pool.pop()
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            return conn

    def _return_connection(self, conn):
        """Return a connection to the pool."""
        with self._pool_lock:
            if len(self._connection_pool) < self.max_connections:
                self._connection_pool.append(conn)
            else:
                conn.close()

    @contextmanager
    def _transaction(self):
        """Context manager for database transactions."""
        conn = self._get_connection()
        try:
            yield conn.cursor()
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise GraphStorageError(f"Transaction failed: {str(e)}") from e
        finally:
            self._return_connection(conn)

    def _init_schema(self):
        """Initialize database schema with indices."""
        with self._transaction() as c:
            # Nodes table with metadata
            c.execute('''CREATE TABLE IF NOT EXISTS nodes (
                id INTEGER PRIMARY KEY,
                path TEXT UNIQUE NOT NULL,
                metadata TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )''')

            # Edges table with relationship metadata
            c.execute('''CREATE TABLE IF NOT EXISTS edges (
                id INTEGER PRIMARY KEY,
                source TEXT NOT NULL,
                target TEXT NOT NULL,
                type TEXT NOT NULL,
                weight REAL NOT NULL,
                metadata TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(source, target, type)
            )''')

            # Create indices for fast lookups
            c.execute('CREATE INDEX IF NOT EXISTS idx_nodes_path ON nodes(path)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_edges_type ON edges(type)')

    def save_node(self, path: str, metadata: Dict[str, Any]) -> int:
        """Save or update a node with metadata."""
        try:
            with self._transaction() as c:
                c.execute('''
                    INSERT OR REPLACE INTO nodes (path, metadata, updated_at)
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                ''', (path, json.dumps(metadata)))
                return c.lastrowid
        except Exception as e:
            raise GraphStorageError(f"Failed to save node {path}: {str(e)}")

    def save_edge(self, source: str, target: str, type: str, weight: float, metadata: Optional[Dict] = None) -> int:
        """Save or update an edge with metadata."""
        try:
            with self._transaction() as c:
                c.execute('''
                    INSERT OR REPLACE INTO edges (source, target, type, weight, metadata)
                    VALUES (?, ?, ?, ?, ?)
                ''', (source, target, type, weight, json.dumps(metadata) if metadata else None))
                return c.lastrowid
        except Exception as e:
            raise GraphStorageError(f"Failed to save edge {source}->{target}: {str(e)}")

    def get_node(self, path: str) -> Optional[Dict[str, Any]]:
        """Retrieve a node by path."""
        try:
            with self._transaction() as c:
                c.execute('SELECT * FROM nodes WHERE path = ?', (path,))
                row = c.fetchone()
                if row:
                    return {
                        'id': row['id'],
                        'path': row['path'],
                        'metadata': json.loads(row['metadata']),
                        'created_at': row['created_at'],
                        'updated_at': row['updated_at']
                    }
                return None
        except Exception as e:
            raise GraphStorageError(f"Failed to retrieve node {path}: {str(e)}")

    def get_edges(self, source: Optional[str] = None, target: Optional[str] = None, 
                 edge_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieve edges with optional filtering."""
        try:
            query = 'SELECT * FROM edges WHERE 1=1'
            params = []
            if source:
                query += ' AND source = ?'
                params.append(source)
            if target:
                query += ' AND target = ?'
                params.append(target)
            if edge_type:
                query += ' AND type = ?'
                params.append(edge_type)

            with self._transaction() as c:
                c.execute(query, params)
                return [{
                    'id': row['id'],
                    'source': row['source'],
                    'target': row['target'],
                    'type': row['type'],
                    'weight': row['weight'],
                    'metadata': json.loads(row['metadata']) if row['metadata'] else None,
                    'created_at': row['created_at']
                } for row in c.fetchall()]
        except Exception as e:
            raise GraphStorageError(f"Failed to retrieve edges: {str(e)}")

    def delete_node(self, path: str) -> bool:
        """Delete a node and its associated edges."""
        try:
            with self._transaction() as c:
                c.execute('DELETE FROM edges WHERE source = ? OR target = ?', (path, path))
                c.execute('DELETE FROM nodes WHERE path = ?', (path,))
                return c.rowcount > 0
        except Exception as e:
            raise GraphStorageError(f"Failed to delete node {path}: {str(e)}")

    def cleanup(self):
        """Clean up connections and resources."""
        with self._pool_lock:
            for conn in self._connection_pool:
                conn.close()
            self._connection_pool.clear() 