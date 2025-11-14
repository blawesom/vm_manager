"""Unified logging configuration for all VMAN services and agents.

This module provides centralized logging configuration that ensures consistent
log formatting and output across INTEL, OPERATOR, and OBSERVER services.
Includes log rotation to prevent large log files.
"""
import logging
import logging.handlers
import sys
import os
from pathlib import Path
from typing import Optional


class UnifiedLogger:
    """Unified logger configuration for VMAN services."""
    
    # Service identifiers
    SERVICE_INTEL = "INTEL"
    SERVICE_OPERATOR = "OPERATOR"
    SERVICE_OBSERVER = "OBSERVER"
    
    _configured = False
    
    @classmethod
    def configure(
        cls,
        log_level: Optional[str] = None,
        log_file: Optional[Path] = None,
        log_dir: Optional[Path] = None,
        service_name: str = "VMAN",
        max_bytes: int = 10 * 1024 * 1024,  # 10MB default
        backup_count: int = 5
    ) -> None:
        """Configure unified logging for all services.
        
        Args:
            log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
                      Defaults to INFO, or VMAN_LOG_LEVEL env var.
            log_file: Path to log file. If None, uses VMAN_LOG_FILE env var or
                     creates vman.log in log_dir.
            log_dir: Directory for log files. Defaults to ./logs or VMAN_LOG_DIR.
            service_name: Service name prefix for logs.
            max_bytes: Maximum log file size in bytes before rotation (default: 10MB).
                      Can be set via VMAN_LOG_MAX_BYTES env var.
            backup_count: Number of backup log files to keep (default: 5).
                         Can be set via VMAN_LOG_BACKUP_COUNT env var.
        """
        if cls._configured:
            return  # Already configured
        
        # Get configuration from environment or defaults
        level_str = log_level or os.environ.get("VMAN_LOG_LEVEL", "INFO").upper()
        log_level_map = {
            "DEBUG": logging.DEBUG,
            "INFO": logging.INFO,
            "WARNING": logging.WARNING,
            "ERROR": logging.ERROR,
            "CRITICAL": logging.CRITICAL,
        }
        level = log_level_map.get(level_str, logging.INFO)
        
        # Get rotation settings from environment or use defaults
        max_bytes = int(os.environ.get("VMAN_LOG_MAX_BYTES", str(max_bytes)))
        backup_count = int(os.environ.get("VMAN_LOG_BACKUP_COUNT", str(backup_count)))
        
        # Determine log file location
        if log_file:
            log_path = Path(log_file)
        elif os.environ.get("VMAN_LOG_FILE"):
            log_path = Path(os.environ["VMAN_LOG_FILE"])
        else:
            log_dir = log_dir or Path(os.environ.get("VMAN_LOG_DIR", "./logs"))
            log_dir.mkdir(parents=True, exist_ok=True)
            log_path = log_dir / "vman.log"
        
        # Create formatter with service identification
        formatter = logging.Formatter(
            fmt='%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # Configure root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(level)
        
        # Remove existing handlers to avoid duplicates
        root_logger.handlers.clear()
        
        # Console handler (always enabled)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)
        
        # File handler with rotation (if log file specified)
        if log_path:
            try:
                # Ensure log directory exists
                log_path.parent.mkdir(parents=True, exist_ok=True)
                
                # Use RotatingFileHandler for automatic log rotation
                file_handler = logging.handlers.RotatingFileHandler(
                    log_path,
                    mode='a',
                    maxBytes=max_bytes,
                    backupCount=backup_count,
                    encoding='utf-8'
                )
                file_handler.setLevel(level)
                file_handler.setFormatter(formatter)
                root_logger.addHandler(file_handler)
                
                max_mb = max_bytes / (1024 * 1024)
                logging.info(
                    f"Logging to file: {log_path} "
                    f"(rotation: {max_mb:.1f}MB, backups: {backup_count})"
                )
            except Exception as e:
                logging.warning(f"Failed to create file handler: {e}")
        
        cls._configured = True
        logging.info(f"Unified logging configured (level={level_str}, service={service_name})")
    
    @classmethod
    def get_logger(cls, module_name: str, service: Optional[str] = None) -> logging.Logger:
        """Get a logger for a module with service identification.
        
        Args:
            module_name: Module name (typically __name__).
            service: Service identifier (INTEL, OPERATOR, OBSERVER).
                    If None, attempts to infer from module name.
        
        Returns:
            Configured logger instance.
        """
        # Ensure logging is configured
        if not cls._configured:
            cls.configure()
        
        # Infer service from module name if not provided
        if not service:
            if "main" in module_name or "intel" in module_name.lower():
                service = cls.SERVICE_INTEL
            elif "operator" in module_name.lower():
                service = cls.SERVICE_OPERATOR
            elif "observer" in module_name.lower():
                service = cls.SERVICE_OBSERVER
        
        # Create logger name with service prefix
        if service:
            logger_name = f"{service}.{module_name.split('.')[-1]}"
        else:
            logger_name = module_name.split('.')[-1]
        
        return logging.getLogger(logger_name)
    
    @classmethod
    def log_request(cls, logger: logging.Logger, method: str, path: str, 
                   status_code: int, duration_ms: float = None):
        """Log HTTP request in unified format.
        
        Args:
            logger: Logger instance.
            method: HTTP method (GET, POST, etc.).
            path: Request path.
            status_code: HTTP status code.
            duration_ms: Request duration in milliseconds (optional).
        """
        duration_str = f" ({duration_ms:.2f}ms)" if duration_ms else ""
        logger.info(f"HTTP {method} {path} -> {status_code}{duration_str}")
    
    @classmethod
    def log_error(cls, logger: logging.Logger, operation: str, error: Exception, 
                 context: Optional[dict] = None):
        """Log error in unified format.
        
        Args:
            logger: Logger instance.
            operation: Operation that failed.
            error: Exception that occurred.
            context: Additional context dictionary (optional).
        """
        context_str = f" | Context: {context}" if context else ""
        logger.error(f"{operation} failed: {error}{context_str}", exc_info=True)
    
    @classmethod
    def log_coherence_issue(cls, logger: logging.Logger, issue_type: str, 
                           resource_id: str, details: str):
        """Log coherence issue in unified format.
        
        Args:
            logger: Logger instance.
            issue_type: Type of coherence issue.
            resource_id: Resource identifier.
            details: Issue details.
        """
        logger.warning(f"Coherence issue [{issue_type}] {resource_id}: {details}")

