# visiofirm/blindtrust.py
"""
VisioFirm BlindTrust API Module

This module provides a Pythonic interface for blind trust conversion, mirroring routes/annotation.py.
It converts pre-annotations (above threshold) to official annotations.

Usage:
    from visiofirm.blindtrust import VFBlindTrust
    from visiofirm.projects import VFProjects

    proj = VFProjects.get_project('MyProject')
    blind_trust = VFBlindTrust(
        project=proj,
        confidence_threshold=0.5,
        user_id=None  # Optional, for auditing
    )
    blind_trust.run()  # Synchronous; returns processed count
    # Or: blind_trust.run_threaded()

    # Status: blind_trust.status, blind_trust.progress
"""

import threading
import sqlite3
import logging
from tqdm import tqdm

logger = logging.getLogger(__name__)

last_progress_bt = {}

class VFBlindTrust:
    """
    API for blind trust: Convert high-confidence pre-annotations to annotations.
    
    Args:
        project: Project instance.
        confidence_threshold: Min confidence (default 0.5).
        user_id: Optional user ID for annotations.
    """
    def __init__(self, project, confidence_threshold=0.5, user_id=None):
        self.project = project
        self.confidence_threshold = confidence_threshold
        self.user_id = user_id
        self.status = 'not_started'
        self.progress = 0
        self.thread = None
        self.processed_count = 0

    def _run_core(self):
        """Internal runner."""
        try:
            self.status = 'running'
            self.progress = 0
            print(f"VisioFirm is running blind trust for project '{self.project.name}' (threshold: {self.confidence_threshold})...")  

            with sqlite3.connect(self.project.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT DISTINCT i.image_id, i.absolute_path
                    FROM Images i
                    JOIN Preannotations p ON i.image_id = p.image_id
                    WHERE p.confidence >= ?
                ''', (self.confidence_threshold,))
                images = cursor.fetchall()

                total_images = len(images)
                self.processed_count = 0

                with tqdm(total=total_images, desc=f"Blind trust for {self.project.name}", unit="img") as pbar:
                    for image_id, abs_path in images:
                        cursor.execute('''
                            SELECT preannotation_id, type, class_name, x, y, width, height, rotation, segmentation, confidence
                            FROM Preannotations
                            WHERE image_id = ? AND confidence >= ?
                        ''', (image_id, self.confidence_threshold))
                        preannotations = cursor.fetchall()

                        # Delete existing annotations
                        cursor.execute('DELETE FROM Annotations WHERE image_id = ?', (image_id,))

                        for preanno in preannotations:
                            cursor.execute('''
                                INSERT INTO Annotations (image_id, user_id, type, class_name, x, y, width, height, rotation, segmentation)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            ''', (image_id, self.user_id, preanno[1], preanno[2], preanno[3], preanno[4], preanno[5], preanno[6], preanno[7], preanno[8]))

                        cursor.execute('DELETE FROM Preannotations WHERE image_id = ?', (image_id,))

                        cursor.execute('''
                            INSERT OR REPLACE INTO ReviewedImages (image_id, user_id) VALUES (?, ?)
                        ''', (image_id, self.user_id))

                        self.processed_count += 1
                        self.progress = (self.processed_count / total_images) * 100 if total_images > 0 else 100
                        pbar.update(1)
                        pbar.set_postfix({'progress': f"{self.progress:.1f}%"}) 

                        conn.commit() 

                self.status = 'completed'
                print(f"Blind trust completed for '{self.project.name}': {self.processed_count}/{total_images} images processed.")
                logger.info(f"Blind trust completed for {self.project.name}: {self.processed_count} images")
        except Exception as e:
            print(f"Blind trust failed for '{self.project.name}': {str(e)}")
            logger.error(f"Blind trust failed for {self.project.name}: {e}")
            self.status = 'failed'
            self.progress = 0

    def run(self):
        """Synchronous run."""
        if self.status == 'running':
            raise RuntimeError("Blind trust already running")
        self._run_core()
        return {'status': self.status, 'progress': self.progress, 'processed': self.processed_count}

    def run_threaded(self, callback=None):
        """Background run."""
        if self.status == 'running':
            raise RuntimeError("Blind trust already running")
        self.thread = threading.Thread(target=self._run_core)
        self.thread.start()
        if callback:
            def poll():
                key = self.project.name 
                while self.thread.is_alive():
                    callback({'status': self.status, 'progress': self.progress})
                    
                    progress = self.progress
                    if key not in last_progress_bt:
                        last_progress_bt[key] = 0
                    if abs(progress - last_progress_bt[key]) >= 5 or self.status != 'running':
                        print(f"Blind trust progress for '{key}': {progress:.1f}% ({self.status})")
                        last_progress_bt[key] = progress
                    threading.Event().wait(1)  # Poll every second
                callback({'status': self.status, 'progress': self.progress, 'processed': self.processed_count})
                if self.status == 'completed':
                    print(f"Blind trust completed for '{key}': {self.processed_count} images processed.")  # Final print
            threading.Thread(target=poll).start()
        return self.thread

    def get_status(self):
        """Current status."""
        return {'status': self.status, 'progress': self.progress, 'processed': self.processed_count}