# New file: visiofirm/imagedownloader.py
"""
© VisioFirm https://github.com/OschAI/VisioFirm

VisioFirm Image Downloader API Module

This module provides a Pythonic interface for downloading (zipping) images from a project.

Usage:
    from visiofirm.imagedownloader import VFImageDownloader
    from visiofirm.projects import VFProjects

    proj = VFProjects.get_project('MyProject')
    downloader = VFImageDownloader(
        project=proj,
        path='/path/to/download/folder',  # Directory to save ZIP
        selected_images=None  # List of filenames; None for all
    )
    zip_path = downloader.download()  # Saves ZIP; returns path
"""

import os
import zipfile
from pathlib import Path
from typing import Optional, List
import logging
from visiofirm.config import VALID_IMAGE_EXTENSIONS
from visiofirm.projects import Project

logger = logging.getLogger(__name__)

class VFImageDownloader:
    """
    API for zipping and saving images.
    
    Args:
        project: Project instance.
        path: Directory to save ZIP (creates if needed; not root/file).
        selected_images: Optional list of filenames (e.g., ['img1.jpg']); None for all.
    """
    def __init__(self, project: Project, path: str, selected_images: Optional[List[str]] = None):
        if not isinstance(project, Project):
            raise ValueError("project must be a Project instance")
        path_obj = Path(path)
        if path_obj.is_file() or path == '/':
            raise ValueError("path must be a non-root directory, not a file")
        self.project = project
        self.path = path_obj
        self.selected_images = selected_images or []

    def _get_images(self) -> List[str]:
        """Get image paths (all or selected)."""
        images_path = os.path.join(os.path.dirname(self.project.db_path), 'images')
        if not os.path.exists(images_path):
            raise ValueError("No images directory found")
        
        all_images = [f for f in os.listdir(images_path) if os.path.splitext(f)[1].lower() in VALID_IMAGE_EXTENSIONS]
        if self.selected_images:
            selected = [f for f in all_images if os.path.basename(f) in self.selected_images]
            if len(selected) != len(self.selected_images):
                logger.warning(f"Skipped {len(self.selected_images) - len(selected)} missing selected images")
            return selected
        return all_images

    def download(self) -> str:
        """Zip and save images. Returns ZIP filepath."""
        self.path.mkdir(parents=True, exist_ok=True)
        filenames = self._get_images()
        if not filenames:
            raise ValueError("No images to download")

        images_path = os.path.join(os.path.dirname(self.project.db_path), 'images')
        zip_filename = f'{self.project.name}_images.zip'
        zip_path = self.path / zip_filename

        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for filename in filenames:
                file_path = os.path.join(images_path, filename)
                if os.path.exists(file_path):
                    zf.write(file_path, arcname=filename)
                else:
                    logger.warning(f"Skipping missing image: {file_path}")

        logger.info(f"Downloaded {len(filenames)} images for {self.project.name} to {zip_path}")
        return str(zip_path)