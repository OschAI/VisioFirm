"""
VisioFirm SessionTracker API Module

This module provides a Pythonic interface for tracking sessions, operations, logs, and bugs in JSON format.
It mirrors the API style of other modules (e.g., VFPreAnnotator) and integrates with existing logging.
JSON sessions are saved to ~/.cache/visiofirm_cache/logs/ with a maximum of 10 files; the oldest is removed when an 11th is created.

Usage:
    from visiofirm.tracker import VFSessionTracker
    from visiofirm.config import get_cache_folder  # For logs path

    # Initialize (uses centralized version)
    tracker = VFSessionTracker()

    # Start session (creates JSON)
    tracker.start_session()

    # Log a major step
    tracker.log_step(
        step='Creating project',
        details={'name': 'MyProject', 'classes': ['car']},
        substeps=None  # Optional list of dicts
    )

    # In loops (e.g., with tqdm for terminal progress)
    # for i in tqdm(range(100)): tracker.log_substep('Processed item', {'index': i})

    # On error
    try:
        ...
    except Exception as e:
        tracker.log_error(e, step='Loading images')

    # End session (finalizes JSON, prints path)
    tracker.end_session()
    # JSON path: /path/to/logs/session_20250908_143022.json
"""

import os
import json
import datetime
import threading
import traceback
import inspect
import logging
import platform
import multiprocessing
import torch
import psutil
from pathlib import Path
from typing import Optional, Dict, Any, List
from visiofirm.config import get_cache_folder
import visiofirm

logger = logging.getLogger(__name__)

class JSONLogHandler(logging.Handler):
    """Custom logging handler to append ERROR/WARNING to tracker's logs array."""
    def __init__(self, tracker):
        super().__init__()
        self.tracker = tracker
        self.setLevel(logging.WARNING)  # Only warnings/errors

    def emit(self, record):
        if self.tracker.session_active:
            log_entry = {
                'level': record.levelname,
                'module': record.module,
                'message': record.getMessage(),
                'timestamp': datetime.datetime.now().isoformat()
            }
            if record.exc_info:
                log_entry['traceback'] = ''.join(traceback.format_exception(*record.exc_info))
            self.tracker._append_to_json('logs', log_entry)
            if record.levelname == 'WARNING':
                self.tracker._append_to_json('warnings', log_entry)
            if record.levelname == 'ERROR':
                self.tracker._append_to_json('errors', log_entry)

class VFSessionTracker:
    """
    API for session tracking: Logs steps, substeps, logs, and bugs to JSON.
    Maintains a maximum of 10 JSON files, removing the oldest when an 11th is created.
    """
    def __init__(self):
        self.version = visiofirm.__version__
        self.session_active = False
        self.json_path: Optional[str] = None
        self.data: Dict = {}
        self.bug_counter = 0
        self.start_time: Optional[datetime.datetime] = None
        self.end_time: Optional[datetime.datetime] = None
        self.lock = threading.Lock()
        self.log_handler: Optional[JSONLogHandler] = None
        self.logs_dir = Path(get_cache_folder()) / 'logs'
        self.logs_dir.mkdir(exist_ok=True)

    def start_session(self):
        """Start session: Create JSON with header, remove oldest log if >= 10 files."""
        if self.session_active:
            raise RuntimeError("Session already active")
        self.start_time = datetime.datetime.now()
        self.session_active = True
        self.bug_counter = 0
        self.data = {}

        # Check and manage log file limit
        MAX_LOG_FILES = 10
        log_files = sorted(
            [f for f in self.logs_dir.glob('VisioFirm_session_*.json')],
            key=lambda x: os.path.getctime(x)
        )
        if len(log_files) >= MAX_LOG_FILES:
            oldest_file = log_files[0]  # Oldest file by creation time
            try:
                oldest_file.unlink()
                logger.info(f"Removed oldest log file: {oldest_file}")
            except Exception as e:
                logger.warning(f"Failed to remove oldest log file {oldest_file}: {str(e)}")

        # Header
        header = {
            'version': self.version,
            'os': platform.system(),
            'python_version': platform.python_version(),
            'cuda_available': torch.cuda.is_available(),
            'torch_version': torch.__version__,
            'start_time': self.start_time.isoformat(),
            'essential_info': {
                'cpu_count': multiprocessing.cpu_count(),
                'memory_gb': round(psutil.virtual_memory().total / (1024**3), 1),
                'projects_folder': get_cache_folder()  # Reuse config
            }
        }

        # JSON file
        timestamp = self.start_time.strftime('%Y%m%d_%H%M%S')
        self.json_path = self.logs_dir / f"VisioFirm_session_{timestamp}.json"
        self.data = {'header': header}
        self._write_json(self.data)

        # Add handler to root logger
        self.log_handler = JSONLogHandler(self)
        logging.getLogger().addHandler(self.log_handler)

        # Suppress INFO in console
        logging.getLogger().setLevel(logging.WARNING)

        logging.info(f"Session started: {self.json_path}")  # Will go to JSON

    def _get_caller_info(self) -> tuple[str, str, str]:
        """Auto-detect module/class/method from stack."""
        frame_info = inspect.stack()[2]  # Caller of log_step
        frame_obj = frame_info.frame
        module = os.path.basename(frame_info.filename)  # Simpler: basename of filename
        class_name = ''
        if 'self' in frame_obj.f_locals:
            self_obj = frame_obj.f_locals['self']
            class_name = self_obj.__class__.__name__
        method = frame_info.function
        return module, class_name, method

    def log_step(self, step: str, details: Optional[Dict[str, Any]] = None, substeps: Optional[List[Dict]] = None):
        """Log a major step (success assumed; use log_error for failures)."""
        if not self.session_active:
            return
        with self.lock:
            module, class_name, method = self._get_caller_info()
            operation = {
                'step': step,
                'module': module,
                'class': class_name,
                'method': method,
                'timestamp': datetime.datetime.now().isoformat(),
                'success': True,
                'details': details or {},
                'substeps': substeps or []
            }
            if 'operations' not in self.data:
                self.data['operations'] = []
            self.data['operations'].append(operation)
            self._write_json(self.data)

    def log_substep(self, substep: str, details: Optional[Dict[str, Any]] = None):
        """Log a substep to the last operation."""
        if not self.session_active or 'operations' not in self.data or not self.data['operations']:
            return
        with self.lock:
            last_op = self.data['operations'][-1]
            sub = {
                'substep': substep,
                'timestamp': datetime.datetime.now().isoformat(),
                'success': True,
                'details': details or {}
            }
            last_op['substeps'].append(sub)
            # Update last operation in JSON
            self._write_json(self.data)  # Re-write full for simplicity

    def log_error(self, exc: Exception, step: str):
        """Log an error as a bug and mark step as failed."""
        if not self.session_active:
            return
        with self.lock:
            # Log step as failed (if not already)
            module, class_name, method = self._get_caller_info()
            operation = {
                'step': step,
                'module': module,
                'class': class_name,
                'method': method,
                'timestamp': datetime.datetime.now().isoformat(),
                'success': False,
                'details': {'error_type': type(exc).__name__, 'error_msg': str(exc)},
                'substeps': []
            }
            if 'operations' not in self.data:
                self.data['operations'] = []
            self.data['operations'].append(operation)

            # Bug entry
            self.bug_counter += 1
            bug_id = f"vf-bug-{self.start_time.strftime('%Y%m%d')}-{self.bug_counter:03d}"
            tb = ''.join(traceback.format_exception(type(exc), exc, exc.__traceback__))
            suggestion = self._get_error_suggestion(type(exc).__name__, str(exc))
            bug = {
                'bug_id': bug_id,
                'step': step,
                'module': module,
                'error': f"{type(exc).__name__}: {str(exc)}",
                'traceback': tb,
                'timestamp': datetime.datetime.now().isoformat(),
                'suggestion': suggestion
            }
            if 'bugs' not in self.data:
                self.data['bugs'] = []
            self.data['bugs'].append(bug)

            self._write_json(self.data)

            # Also log to logs via handler (will capture)

    def _get_error_suggestion(self, error_type: str, error_msg: str) -> str:
        """Simple suggestions for common errors."""
        suggestions = {
            'FileNotFoundError': 'Check if the data path or file exists and permissions are correct.',
            'ValueError': 'Verify input parameters (e.g., classes list non-empty, valid setup_type).',
            'RuntimeError': 'Possible device issue (CUDA?); try switching to CPU.',
            'ImportError': 'Missing dependency; ensure all requirements are installed.'
        }
        return suggestions.get(error_type, 'Please provide more details in the GitHub issue.')

    def _write_json(self, data: Dict):
        """Write JSON atomically."""
        if not self.json_path:
            return
        tmp_path = self.json_path.with_suffix('.tmp')
        with open(tmp_path, 'w') as f:
            json.dump(data, f, indent=2)
        os.replace(tmp_path, self.json_path)

    def _append_to_json(self, key: str, entry: Dict):
        """Append to a list key in JSON (in-memory)."""
        with self.lock:
            if key not in self.data:
                self.data[key] = []
            self.data[key].append(entry)
            self._write_json(self.data)

    def end_session(self, print_path: bool = True):
        """End session: Add footer, remove handler, print if bugs."""
        if not self.session_active:
            return
        self.end_time = datetime.datetime.now()
        self.session_active = False

        # Footer
        duration = (self.end_time - self.start_time).total_seconds()
        successful_steps = len([op for op in self.data.get('operations', []) if op['success']])
        footer = {
            'total_steps': len(self.data.get('operations', [])),
            'successful_steps': successful_steps,
            'errors': len(self.data.get('bugs', [])),
            'warnings_count': len(self.data.get('warnings', [])),
            'end_time': self.end_time.isoformat(),
            'duration_seconds': duration,
            'recommendation': 'If bugs occurred, copy this JSON to a new GitHub issue at https://github.com/OschAI/VisioFirm/issues'
        }

        self.data['footer'] = footer
        self._write_json(self.data)

        # Remove handler
        if self.log_handler:
            logging.getLogger().removeHandler(self.log_handler)
            self.log_handler = None

        # Reset console logging if needed
        logging.getLogger().setLevel(logging.INFO)

        if print_path:
            print(f"Session log saved to: {self.json_path}")
            if self.data.get('bugs'):
                bug_ids = [b['bug_id'] for b in self.data['bugs']]
                print(f"Bugs detected (IDs: {', '.join(bug_ids)}); paste JSON to GitHub for help.")