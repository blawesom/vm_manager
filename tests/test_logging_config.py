"""Unit tests for logging configuration module."""
import pytest
import os
import tempfile
import logging
from pathlib import Path
from unittest.mock import patch, MagicMock
from app import logging_config


class TestUnifiedLogger:
    """Test UnifiedLogger class."""
    
    def setup_method(self):
        """Reset configuration state before each test."""
        logging_config.UnifiedLogger._configured = False
        # Clear all handlers
        root_logger = logging.getLogger()
        root_logger.handlers.clear()
    
    def test_configure_basic(self):
        """Test basic configuration."""
        logging_config.UnifiedLogger.configure()
        assert logging_config.UnifiedLogger._configured is True
        root_logger = logging.getLogger()
        assert len(root_logger.handlers) > 0
    
    def test_configure_with_custom_level(self):
        """Test configuration with custom log level."""
        logging_config.UnifiedLogger.configure(log_level="DEBUG")
        root_logger = logging.getLogger()
        assert root_logger.level == logging.DEBUG
    
    def test_configure_with_custom_log_file(self):
        """Test configuration with custom log file path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "custom.log"
            logging_config.UnifiedLogger.configure(log_file=log_file)
            assert log_file.exists()
    
    def test_configure_with_custom_log_dir(self):
        """Test configuration with custom log directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir) / "custom_logs"
            logging_config.UnifiedLogger.configure(log_dir=log_dir)
            log_file = log_dir / "vman.log"
            assert log_file.exists()
    
    def test_configure_with_env_vars(self):
        """Test configuration with environment variables."""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["VMAN_LOG_LEVEL"] = "WARNING"
            os.environ["VMAN_LOG_DIR"] = str(tmpdir)
            try:
                logging_config.UnifiedLogger.configure()
                root_logger = logging.getLogger()
                assert root_logger.level == logging.WARNING
            finally:
                os.environ.pop("VMAN_LOG_LEVEL", None)
                os.environ.pop("VMAN_LOG_DIR", None)
    
    def test_configure_with_env_log_file(self):
        """Test configuration with VMAN_LOG_FILE env var."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "env.log"
            os.environ["VMAN_LOG_FILE"] = str(log_file)
            try:
                logging_config.UnifiedLogger.configure()
                assert log_file.exists()
            finally:
                os.environ.pop("VMAN_LOG_FILE", None)
    
    def test_configure_with_rotation_settings(self):
        """Test configuration with rotation settings."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "rotated.log"
            logging_config.UnifiedLogger.configure(
                log_file=log_file,
                max_bytes=1024,  # 1KB
                backup_count=3
            )
            assert log_file.exists()
    
    def test_configure_with_env_rotation_settings(self):
        """Test configuration with rotation settings from env."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "rotated.log"
            os.environ["VMAN_LOG_MAX_BYTES"] = "2048"
            os.environ["VMAN_LOG_BACKUP_COUNT"] = "2"
            try:
                logging_config.UnifiedLogger.configure(log_file=log_file)
                assert log_file.exists()
            finally:
                os.environ.pop("VMAN_LOG_MAX_BYTES", None)
                os.environ.pop("VMAN_LOG_BACKUP_COUNT", None)
    
    def test_configure_file_handler_error(self):
        """Test configuration handles file handler creation errors."""
        with patch('app.logging_config.logging.handlers.RotatingFileHandler') as mock_handler:
            mock_handler.side_effect = PermissionError("Permission denied")
            with tempfile.TemporaryDirectory() as tmpdir:
                log_file = Path(tmpdir) / "error.log"
                # Should not raise, just log warning
                logging_config.UnifiedLogger.configure(log_file=log_file)
                assert logging_config.UnifiedLogger._configured is True
    
    def test_configure_idempotent(self):
        """Test that configure can be called multiple times safely."""
        logging_config.UnifiedLogger.configure()
        first_handlers = len(logging.getLogger().handlers)
        logging_config.UnifiedLogger.configure()
        second_handlers = len(logging.getLogger().handlers)
        # Should not add duplicate handlers
        assert first_handlers == second_handlers
    
    def test_get_logger_with_service(self):
        """Test getting logger with explicit service."""
        logging_config.UnifiedLogger.configure()
        logger = logging_config.UnifiedLogger.get_logger("test_module", "INTEL")
        assert logger.name == "INTEL.test_module"
    
    def test_get_logger_without_service(self):
        """Test getting logger without service (auto-inference)."""
        logging_config.UnifiedLogger.configure()
        # Test INTEL inference
        logger = logging_config.UnifiedLogger.get_logger("app.main")
        assert "INTEL" in logger.name
        
        # Test OPERATOR inference
        logger = logging_config.UnifiedLogger.get_logger("app.operator")
        assert "OPERATOR" in logger.name
        
        # Test OBSERVER inference
        logger = logging_config.UnifiedLogger.get_logger("app.observer")
        assert "OBSERVER" in logger.name
        
        # Test no inference
        logger = logging_config.UnifiedLogger.get_logger("app.unknown")
        assert logger.name == "unknown"
    
    def test_get_logger_auto_configure(self):
        """Test that get_logger auto-configures if not configured."""
        logging_config.UnifiedLogger._configured = False
        logger = logging_config.UnifiedLogger.get_logger("test")
        assert logging_config.UnifiedLogger._configured is True
        assert logger is not None
    
    def test_log_request_with_duration(self):
        """Test log_request with duration."""
        logging_config.UnifiedLogger.configure()
        logger = logging_config.UnifiedLogger.get_logger("test")
        with patch.object(logger, 'info') as mock_info:
            logging_config.UnifiedLogger.log_request(
                logger, "GET", "/test", 200, 123.45
            )
            mock_info.assert_called_once()
            assert "123.45ms" in mock_info.call_args[0][0]
    
    def test_log_request_without_duration(self):
        """Test log_request without duration."""
        logging_config.UnifiedLogger.configure()
        logger = logging_config.UnifiedLogger.get_logger("test")
        with patch.object(logger, 'info') as mock_info:
            logging_config.UnifiedLogger.log_request(
                logger, "POST", "/test", 201
            )
            mock_info.assert_called_once()
            assert "ms" not in mock_info.call_args[0][0]
    
    def test_log_error_with_context(self):
        """Test log_error with context."""
        logging_config.UnifiedLogger.configure()
        logger = logging_config.UnifiedLogger.get_logger("test")
        error = ValueError("Test error")
        with patch.object(logger, 'error') as mock_error:
            logging_config.UnifiedLogger.log_error(
                logger, "test_operation", error, {"key": "value"}
            )
            mock_error.assert_called_once()
            assert "Context:" in mock_error.call_args[0][0]
    
    def test_log_error_without_context(self):
        """Test log_error without context."""
        logging_config.UnifiedLogger.configure()
        logger = logging_config.UnifiedLogger.get_logger("test")
        error = ValueError("Test error")
        with patch.object(logger, 'error') as mock_error:
            logging_config.UnifiedLogger.log_error(
                logger, "test_operation", error
            )
            mock_error.assert_called_once()
            assert "Context:" not in mock_error.call_args[0][0]
    
    def test_log_coherence_issue(self):
        """Test log_coherence_issue."""
        logging_config.UnifiedLogger.configure()
        logger = logging_config.UnifiedLogger.get_logger("test")
        with patch.object(logger, 'warning') as mock_warning:
            logging_config.UnifiedLogger.log_coherence_issue(
                logger, "vm_state_mismatch", "vm-123", "VM is running but DB says stopped"
            )
            mock_warning.assert_called_once()
            assert "vm_state_mismatch" in mock_warning.call_args[0][0]
            assert "vm-123" in mock_warning.call_args[0][0]
    
    def test_configure_invalid_log_level(self):
        """Test configuration with invalid log level defaults to INFO."""
        logging_config.UnifiedLogger.configure(log_level="INVALID")
        root_logger = logging.getLogger()
        assert root_logger.level == logging.INFO
    
    def test_service_constants(self):
        """Test service identifier constants."""
        assert logging_config.UnifiedLogger.SERVICE_INTEL == "INTEL"
        assert logging_config.UnifiedLogger.SERVICE_OPERATOR == "OPERATOR"
        assert logging_config.UnifiedLogger.SERVICE_OBSERVER == "OBSERVER"

