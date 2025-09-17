# New file: visiofirm/imageremover.py
"""
VisioFirm Image Remover API Module

This module provides a Pythonic interface for removing specific images from a project.

Usage:
    from visiofirm.imageremover import VFImageRemover
    from visiofirm.projects import VFProjects

    proj = VFProjects.get_project('MyProject')
    remover = VFImageRemover(
        project=proj,
        image_id=None,  # Optional: DB image_id (int)
        image_name=None  # Optional: Filename (str, with/without ext; fuzzy match)
    )
    success = remover.remove()  # Deletes file/DB entries; returns True if found/deleted
"""

import os
import sqlite3
import logging
from typing import Optional, Union
from pathlib import Path

from visiofirm.projects import Project
from visiofirm.config import VALID_IMAGE_EXTENSIONS

logger = logging.getLogger(__name__)

class VFImageRemover:
    """
    API for removing a specific image.
    
    Args:
        project: Project instance.
        image_id: Optional DB image_id (int; exact match).
        image_name: Optional filename (str; e.g., 'img.jpg' or 'img'; fuzzy by basename).
    """
    def __init__(self, project: Project, image_id: Optional[int] = None, image_name: Optional[str] = None):
        if not (image_id or image_name):
            raise ValueError("Provide either image_id or image_name")
        if image_id and image_name:
            raise ValueError("Provide only one: image_id or image_name")
        self.project = project
        self.image_id = image_id
        self.image_name = image_name
        self.images_path = os.path.join(os.path.dirname(project.db_path), 'images')

    def _find_image(self) -> tuple[Optional[int], Optional[str]]:
        """Find image_id and abs_path by id or name."""
        with sqlite3.connect(self.project.db_path) as conn:
            cursor = conn.cursor()
            if self.image_id:
                cursor.execute('SELECT image_id, absolute_path FROM Images WHERE image_id = ?', (self.image_id,))
                result = cursor.fetchone()
                return result[0], result[1] if result else None
            elif self.image_name:
                base = Path(self.image_name).stem
                cursor.execute('SELECT image_id, absolute_path FROM Images WHERE absolute_path LIKE ?', (f'%{base}%',))
                results = cursor.fetchall()
                if len(results) == 1:
                    return results[0][0], results[0][1]
                elif len(results) > 1:
                    # Try exact basename match
                    for img_id, abs_path in results:
                        if Path(abs_path).name.lower() == self.image_name.lower() or Path(abs_path).stem.lower() == base.lower():
                            return img_id, abs_path
                    logger.warning(f"Multiple matches for {self.image_name}; using first")
                    return results[0][0], results[0][1]
                return None, None
        return None, None

    def remove(self) -> bool:
        """Remove image file and DB entries (annotations, etc.). Returns True if deleted."""
        img_id, abs_path = self._find_image()
        if not img_id or not abs_path:
            logger.warning(f"Image not found: id={self.image_id}, name={self.image_name}")
            return False

        try:
            # Delete file
            if os.path.exists(abs_path):
                os.remove(abs_path)
                logger.info(f"Deleted image file: {abs_path}")

            # Delete DB entries
            with sqlite3.connect(self.project.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM Annotations WHERE image_id = ?', (img_id,))
                cursor.execute('DELETE FROM Preannotations WHERE image_id = ?', (img_id,))
                cursor.execute('DELETE FROM ReviewedImages WHERE image_id = ?', (img_id,))
                cursor.execute('DELETE FROM Images WHERE image_id = ?', (img_id,))
                conn.commit()

            logger.info(f"Deleted image {img_id} ({self.image_name or self.image_id}) from project {self.project.name}")
            return True
        except Exception as e:
            logger.error(f"Error removing image {img_id}: {e}")
            return False