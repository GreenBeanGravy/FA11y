"""
Logging setup module for FA11y
Handles rotating log files (keeps last 3) and captures all output
"""
import os
import sys
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional


class TeeOutput:
    """Redirects output to both console and log file"""

    def __init__(self, original_stream, log_file):
        self.original_stream = original_stream
        self.log_file = log_file

    def write(self, message):
        """Write to both console and log file"""
        if message and message.strip():  # Don't write empty lines
            self.original_stream.write(message)
            self.original_stream.flush()
            if self.log_file and not self.log_file.closed:
                self.log_file.write(message)
                self.log_file.flush()

    def flush(self):
        """Flush both streams"""
        self.original_stream.flush()
        if self.log_file and not self.log_file.closed:
            self.log_file.flush()

    def isatty(self):
        """Check if original stream is a tty"""
        return self.original_stream.isatty()


class LogFileHandler(logging.FileHandler):
    """Custom file handler that also handles exceptions"""

    def __init__(self, filename, mode='a', encoding='utf-8', delay=False):
        super().__init__(filename, mode, encoding, delay)
        self.setFormatter(logging.Formatter(
            '[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        ))


def setup_logging() -> Optional[str]:
    """
    Setup FA11y logging system with rotating log files.

    Creates logs/ folder, maintains last 3 log files,
    redirects all output (print, logger, errors) to log file.

    Returns:
        Path to current log file, or None if setup failed
    """
    try:
        # Create logs directory
        logs_dir = Path("logs")
        logs_dir.mkdir(exist_ok=True)

        # Generate timestamped log filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_filename = logs_dir / f"fa11y_{timestamp}.log"

        # Rotate logs - keep only last 3
        existing_logs = sorted(logs_dir.glob("fa11y_*.log"))
        if len(existing_logs) >= 3:
            # Delete oldest logs
            for old_log in existing_logs[:-2]:  # Keep last 2, will add 1 new = 3 total
                try:
                    old_log.unlink()
                    print(f"Deleted old log: {old_log.name}")
                except Exception as e:
                    print(f"Warning: Could not delete old log {old_log.name}: {e}")

        # Create log file
        log_file = open(log_filename, 'w', encoding='utf-8')

        # Write header
        log_file.write(f"=" * 80 + "\n")
        log_file.write(f"FA11y Log File\n")
        log_file.write(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        log_file.write(f"=" * 80 + "\n\n")
        log_file.flush()

        # Redirect stdout and stderr to both console and log file
        # This captures print() statements
        sys.stdout = TeeOutput(sys.__stdout__, log_file)
        sys.stderr = TeeOutput(sys.__stderr__, log_file)

        # Configure root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.DEBUG)

        # Remove existing handlers
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)

        # Add console handler ONLY for warnings and errors (not INFO or DEBUG)
        console_handler = logging.StreamHandler(sys.__stdout__)
        console_handler.setLevel(logging.WARNING)  # Only show WARNING, ERROR, CRITICAL
        console_handler.setFormatter(logging.Formatter(
            '[%(levelname)s] %(message)s'
        ))
        root_logger.addHandler(console_handler)

        # Add file handler with full formatting - captures everything
        file_handler = LogFileHandler(log_filename)
        file_handler.setLevel(logging.DEBUG)
        root_logger.addHandler(file_handler)

        # Log successful initialization (goes to file only, not console)
        logging.info(f"Logging system initialized - Log file: {log_filename}")

        # Setup exception hook to log unhandled exceptions
        def exception_hook(exc_type, exc_value, exc_traceback):
            """Log unhandled exceptions"""
            if issubclass(exc_type, KeyboardInterrupt):
                # Call default handler for KeyboardInterrupt
                sys.__excepthook__(exc_type, exc_value, exc_traceback)
                return

            logging.critical("Unhandled exception:", exc_info=(exc_type, exc_value, exc_traceback))
            # Also call original handler
            sys.__excepthook__(exc_type, exc_value, exc_traceback)

        sys.excepthook = exception_hook

        return str(log_filename)

    except Exception as e:
        # If logging setup fails, print to console but don't crash
        print(f"Warning: Failed to setup logging: {e}")
        import traceback
        traceback.print_exc()
        return None


def cleanup_logging():
    """Cleanup logging system on shutdown"""
    try:
        logging.info("FA11y shutting down - closing log file")

        # Restore original stdout/stderr
        if hasattr(sys.stdout, 'original_stream'):
            sys.stdout = sys.stdout.original_stream
        if hasattr(sys.stderr, 'original_stream'):
            sys.stderr = sys.stderr.original_stream

        # Close all handlers
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            handler.close()
            root_logger.removeHandler(handler)

    except Exception as e:
        print(f"Warning: Error during logging cleanup: {e}")
