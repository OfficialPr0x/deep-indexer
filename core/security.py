import os
import jwt
import yaml
import time
from typing import Dict, Optional
from datetime import datetime, timezone
from pathlib import Path

class SecurityError(Exception):
    """Base exception for security-related errors"""
    pass

class InvalidPathError(SecurityError):
    """Raised when a path is invalid or potentially malicious"""
    pass

class AuthenticationError(SecurityError):
    """Raised for authentication-related errors"""
    pass

class RateLimitExceeded(SecurityError):
    """Raised when rate limit is exceeded"""
    pass

class ContentSanitizer:
    BANNED_SEQUENCES = {'..', '//', '\\\\', '~', '$', '|', '>', '<', '*', '?'}
    MAX_PATH_DEPTH = 10
    
    def __init__(self, config_path='config/security.yaml'):
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)['file_handling']
    
    def sanitize_path(self, path: str) -> str:
        """
        Sanitize and validate file paths.
        
        Args:
            path: Input path to sanitize
            
        Returns:
            Sanitized path
            
        Raises:
            InvalidPathError: If path is potentially malicious
        """
        if not isinstance(path, str):
            raise InvalidPathError("Path must be a string")
            
        # Convert to Path object for safe handling
        try:
            path_obj = Path(path)
        except Exception as e:
            raise InvalidPathError(f"Invalid path format: {str(e)}")
            
        # Basic security checks
        path_str = str(path_obj)
        if any(seq in path_str for seq in self.BANNED_SEQUENCES):
            raise InvalidPathError("Path contains forbidden sequences")
            
        # Depth check
        if len(path_obj.parts) > self.MAX_PATH_DEPTH:
            raise InvalidPathError(f"Path depth exceeds maximum ({self.MAX_PATH_DEPTH})")
            
        # Extension check
        if path_obj.suffix.lower() in self.config['banned_extensions']:
            raise InvalidPathError(f"File type {path_obj.suffix} is not allowed")
            
        # Size check for existing files
        if path_obj.exists() and path_obj.is_file():
            size = path_obj.stat().st_size
            if size > self.config['max_file_size']:
                raise InvalidPathError(f"File size {size} exceeds maximum")
                
        return os.path.normpath(path_str)

class AuthManager:
    def __init__(self, config_path='config/security.yaml'):
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)['auth']
        self.jwt_secret = self.config['jwt_secret']
        self._rate_limit_store = {}  # In production, use Redis
        
    def _check_rate_limit(self, user_id: str, max_requests: int = 100, 
                         window_seconds: int = 60) -> bool:
        """Check if user has exceeded rate limit."""
        now = time.time()
        user_requests = self._rate_limit_store.get(user_id, [])
        
        # Clean old requests
        user_requests = [ts for ts in user_requests if now - ts < window_seconds]
        
        if len(user_requests) >= max_requests:
            return False
            
        user_requests.append(now)
        self._rate_limit_store[user_id] = user_requests
        return True
        
    def validate_jwt(self, token: str) -> Dict:
        """
        Validate JWT token and return claims.
        
        Args:
            token: JWT token to validate
            
        Returns:
            Dict containing validated claims
            
        Raises:
            AuthenticationError: If token is invalid or expired
        """
        try:
            # Decode and validate token
            payload = jwt.decode(
                token,
                self.jwt_secret,
                algorithms=["HS256"],
                options={
                    "require": ["exp", "iat", "sub", "permissions"],
                    "verify_exp": True,
                    "verify_iat": True,
                }
            )
            
            # Validate required claims
            if not all(k in payload for k in ['sub', 'permissions']):
                raise AuthenticationError("Missing required claims")
                
            # Check rate limit
            if not self._check_rate_limit(payload['sub']):
                raise RateLimitExceeded("Too many requests")
                
            return payload
            
        except jwt.ExpiredSignatureError:
            raise AuthenticationError("Token has expired")
        except jwt.InvalidTokenError as e:
            raise AuthenticationError(f"Invalid token: {str(e)}")
            
    def check_permission(self, claims: Dict, required_permission: str) -> bool:
        """Check if claims grant a specific permission."""
        return required_permission in claims.get('permissions', []) 