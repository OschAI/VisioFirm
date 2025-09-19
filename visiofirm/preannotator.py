#  visiofirm/preannotator.py
"""
VisioFirm PreAnnotator API Module

This module provides a Pythonic interface for AI pre-annotation, mirroring the web functionality in routes/annotation.py.
It wraps VFPreAnnotator.py and handles configuration, execution (synchronous or threaded), and status tracking.

Usage:
    from visiofirm.preannotator import VFPreAnnotator
    from visiofirm.projects import VFProjects

    proj = VFProjects.get_project('MyProject')
    preannotator = VFPreAnnotator(
        project=proj,
        mode='zero-shot',  # or 'custom-model'
        device='cpu',
        box_threshold=0.2,
        dino_model='tiny',  # for zero-shot
        model_path='yolov10x.pt'  # for custom-model
    )
    preannotator.run()  # Synchronous; returns status/progress
    # Or: preannotator.run_threaded() for background

    # Check status: preannotator.status, preannotator.progress
"""

import threading
import time 
import logging
from visiofirm.utils.VFPreAnnotator import PreAnnotator as CorePreAnnotator

logger = logging.getLogger(__name__)

# Global for tracking last printed progress to avoid spam (per project)
last_progress_pre = {}

class VFPreAnnotator:
    """
    API wrapper for pre-annotation.
    
    Args:
        project: Project instance from VFProjects.get_project().
        mode: 'zero-shot' or 'custom-model'.
        device: 'cpu' or 'cuda'.
        box_threshold: Confidence threshold (default 0.2).
        dino_model: For zero-shot (default 'tiny').
        model_path: For custom-model (default 'yolov10x.pt').
    """
    def __init__(self, project, mode, device='cpu', box_threshold=0.2, dino_model='tiny', model_path='yolov10x.pt'):
        if project.setup_type == "Classification":
            self.mode = 'clip'
        elif mode not in ['zero-shot', 'custom-model']:
            raise ValueError("Mode must be 'zero-shot' or 'custom-model'")
        self.project = project
        self.mode = mode
        self.device = device
        self.box_threshold = box_threshold
        self.dino_model = dino_model
        self.model_path = model_path
        self.status = 'not_started'
        self.progress = 0
        self.thread = None
        self.config_db_path = self.project.db_path 

    def _run_core(self):
        """Internal runner for PreAnnotator."""
        try:
            self.status = 'running'
            self.progress = 0
            model_details = f"{self.dino_model}" if self.mode == 'zero-shot' else f"{self.model_path}"
            print(f"VisioFirm is pre-annotating images for project '{self.project.name}' using {self.mode} mode ({model_details}), threshold {self.box_threshold}...")

            def progress_cb(progress):
                self.progress = progress

            if self.mode == 'zero-shot':
                model_type = f"grounding_dino_{self.dino_model}"
                proc = CorePreAnnotator(
                    model_type=model_type,
                    config_db_path=self.config_db_path,
                    device=self.device,
                    box_threshold=self.box_threshold,
                    progress_callback=progress_cb
                )
            elif self.mode == 'custom-model':
                proc = CorePreAnnotator(
                    model_type="yolo",
                    yolo_model_path=self.model_path,
                    config_db_path=self.config_db_path,
                    device=self.device,
                    box_threshold=self.box_threshold,
                    progress_callback=progress_cb
                )
            elif self.mode == 'clip':
                proc = CorePreAnnotator(
                    model_type="clip",
                    config_db_path=self.config_db_path,
                    device=self.device,
                    box_threshold=self.box_threshold,
                    progress_callback=progress_cb
                )
            else:
                raise ValueError(f"Invalid mode: {self.mode}. Choose 'zero-shot', 'custom-model', or 'clip'.")

            proc.run_inferences()  # Core call; progress updated internally via tqdm + callback
            self.status = 'completed'
            logger.info(f"Pre-annotation completed for project {self.project.name}")
        except Exception as e:
            print(f"Pre-annotation failed for '{self.project.name}': {str(e)}")
            logger.error(f"Pre-annotation failed for {self.project.name}: {e}")
            self.status = 'failed'
            self.progress = 0


    def run(self):
        """Run pre-annotation synchronously. Blocks until done."""
        if self.status == 'running':
            raise RuntimeError("Pre-annotation already running")
        self._run_core()
        return {'status': self.status, 'progress': self.progress}

    def run_threaded(self, callback=None):
        """Run pre-annotation in background thread. Optional callback for progress."""
        if self.status == 'running':
            raise RuntimeError("Pre-annotation already running")
        self.thread = threading.Thread(target=self._run_core)
        self.thread.start()
        if callback:
            key = self.project.name
            def poll():
                while self.thread.is_alive():
                    callback({'status': self.status, 'progress': self.progress})
                    #skip local print if callback provided (e.g., web use; tqdm in core handles viz)
                    if callback is None:
                        progress = self.progress
                        if key not in last_progress_pre:
                            last_progress_pre[key] = 0
                        if abs(progress - last_progress_pre[key]) >= 5 or self.status != 'running':
                            print(f"Pre-annotation progress for '{key}': {progress:.1f}% ({self.status})")
                            last_progress_pre[key] = progress
                    time.sleep(1)  # Poll every second
                callback({'status': self.status, 'progress': self.progress})
                # Clean up last_progress after completion
                if key in last_progress_pre:
                    del last_progress_pre[key]
            threading.Thread(target=poll).start()
        else:
            # For direct use without callback, poll locally with prints
            key = self.project.name
            def poll_local():
                while self.thread.is_alive():
                    progress = self.progress
                    if key not in last_progress_pre:
                        last_progress_pre[key] = 0
                    if abs(progress - last_progress_pre[key]) >= 5 or self.status != 'running':
                        print(f"Pre-annotation progress for '{key}': {progress:.1f}% ({self.status})")
                        last_progress_pre[key] = progress
                    time.sleep(1)
                print(f"Pre-annotation completed for '{key}': 100.0% (completed)")
                if key in last_progress_pre:
                    del last_progress_pre[key]
            threading.Thread(target=poll_local).start()
        return self.thread

    def get_status(self):
        """Get current status and progress."""
        return {'status': self.status, 'progress': self.progress}

    def stop(self):
        """Stop if possible (extend CorePreAnnotator if needed)."""
        self.status = 'stopped'
        if self.thread and self.thread.is_alive():
            logger.warning("Stopping pre-annotation; implement interrupt in CorePreAnnotator if needed")
            print("Pre-annotation stopped")