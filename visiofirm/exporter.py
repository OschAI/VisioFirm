#visiofirm/exporter.py
"""
VisioFirm Exporter API Module

This module provides a Pythonic interface for exporting annotations, mirroring the web export functionality.
It handles splitting datasets and generating formats like COCO, YOLO, etc., then zips and saves to a path.

Dependencies: Assumes access to export_utils.py and Project.

Usage:
    from visiofirm.exporter import VFExporter
    from visiofirm.projects import VFProjects

    proj = VFProjects.get_project('MyProject')
    exporter = VFExporter(
        project=proj,
        path='/path/to/export/folder',  # Directory to save ZIP (creates if needed)
        format='COCO',  # 'COCO', 'YOLO', 'PASCAL_VOC', 'CSV'
        selected_images=None,  # List of abs paths; None for all annotated
        split_choices=['train', 'val'],  # Default ['train']
        split_ratios={'train': 80, 'val': 20}  # Default {'train': 100}
    )
    exporter.export()  # Saves ZIP to path/MyProject_COCO.zip; returns ZIP path
"""

import os
from io import BytesIO
import logging
from pathlib import Path
from typing import List, Optional, Dict

from visiofirm.utils.export_utils import (
    split_images, generate_coco_export, generate_yolo_export,
    generate_pascal_voc_export, generate_csv_export,
    generate_classification_labels, generate_mask_export
)
from visiofirm.utils.video_export_utils import (
    get_videos_and_frames, generate_video_export
)
from visiofirm.config import VALID_VIDEO_FORMATS, VALID_IMAGE_FORMATS
from visiofirm.models.project import Project
logger = logging.getLogger(__name__)

class VFExporter:
    """
    API for exporting annotations to various formats with optional splitting (images only).
    For videos: no splitting, supports frame extraction.
    
    Args:
        project: Project instance.
        path: Directory to save ZIP.
        format: Export format (image: 'COCO', etc.; video: 'COCO_VIDEO', etc.).
        selected_images: Optional list of absolute image paths (for images).
        split_choices: List of splits (images only).
        split_ratios: Dict of ratios (images only).
        videos: Optional list of absolute video paths (for videos).
        extract_frames: If True and videos provided, extract frame JPEGs.
        semantic: For segmentation mask exports: True for semantic (class_id), False for instance.
    """

    def __init__(
        self,
        project: Project,
        path: str,
        format: str,
        selected_images: Optional[List[str]] = None,
        split_choices: Optional[List[str]] = None,
        split_ratios: Optional[Dict[str, int]] = None,
        videos: Optional[List[str]] = None,
        extract_frames: bool = False,
        semantic: bool = False
    ):
        if not isinstance(project, Project):
            raise ValueError("project must be a Project instance")
        
        self.project = project
        
        self.videos = videos or []
        self.is_video = len(self.videos) > 0
        raw_setup_type = project.get_setup_type()
        self.setup_type = raw_setup_type
        if self.setup_type == "Video Detection":
            self.setup_type = "Bounding Box"
        elif self.setup_type == "Video Segmentation":
            self.setup_type = "Segmentation"
        
        # Fallback for video projects with empty videos list
        if raw_setup_type.startswith("Video ") and not self.is_video:
            all_videos = project.get_videos()
            if all_videos:
                self.videos = [v[1] for v in all_videos]
                self.is_video = True
            else:
                raise ValueError("No videos found in project")
        
        if self.is_video:
            if format not in VALID_VIDEO_FORMATS:
                raise ValueError(f"Video format must be one of {VALID_VIDEO_FORMATS}")
            if raw_setup_type == "Classification":
                raise ValueError("Classification not supported for video export")
            if format in ['MOT'] and self.setup_type not in {"Bounding Box", "Oriented Bounding Box"}:
                raise ValueError("MOT only for Bounding Box / Oriented Bounding Box")
            if format in ['MASK_SEQUENCE', 'MASK_VIDEO'] and self.setup_type != "Segmentation":
                raise ValueError("Mask exports only for Segmentation")
        else:
            if format not in VALID_IMAGE_FORMATS:
                raise ValueError(f"Image format must be one of {VALID_IMAGE_FORMATS}")
            if self.setup_type == "Oriented Bounding Box" and format not in {'CSV', 'YOLO'}:
                raise ValueError("Oriented Bounding Box only supports 'CSV' or 'YOLO'")
            if self.setup_type == "Segmentation" and format not in {'COCO', 'YOLO', 'MASK'}:
                raise ValueError("Segmentation only supports 'COCO' or 'YOLO' or 'MASK'")
            if self.setup_type == "Classification" and format not in {'CSV'}:
                raise ValueError("Classification supports 'CSV' only")  # Simplified
        
        path_obj = Path(path)
        if path_obj.is_file() or path == '/':
            raise ValueError("path must be a non-root directory, not a file")
        self.path = path_obj
        self.format = format
        self.selected_images = selected_images
        self.split_choices = split_choices or ['train']
        self.split_ratios = split_ratios or {'train': 100}
        self.extract_frames = extract_frames
        self.semantic = semantic
        self.project_name = project.name
        self.project_description = self._get_description()

    def _get_description(self) -> str:
        """Fetch project description from DB."""
        import sqlite3
        with sqlite3.connect(self.project.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT description FROM Project_Configuration WHERE project_name = ?', (self.project_name,))
            return cursor.fetchone()[0] or ''

    def _get_annotated_images(self) -> List[str]:
        """Get annotated images (all or selected)."""
        import sqlite3
        with sqlite3.connect(self.project.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT DISTINCT i.absolute_path
                FROM Images i JOIN Annotations a ON i.image_id = a.image_id
            ''')
            annotated = [row[0] for row in cursor.fetchall()]

        if self.selected_images:
            basenames = {os.path.basename(p) for p in self.selected_images}
            annotated = [img for img in annotated if os.path.basename(img) in basenames]

        existing = [img for img in annotated if os.path.exists(img)]
        if len(existing) != len(annotated):
            logger.warning(f"Skipped {len(annotated) - len(existing)} missing images")
        if not existing:
            raise ValueError("No valid annotated images to export")
        return existing

    def _generate_export(self) -> BytesIO:
        """Generate export ZIP BytesIO."""
        if self.is_video:
            videos_data = get_videos_and_frames(self.project, self.videos, self.extract_frames)
            return generate_video_export(
                self.project, videos_data, self.format, self.setup_type,
                self.project_name, self.project_description,
                self.extract_frames, self.semantic
            )
        else:
            if self.setup_type == "Classification":
                return generate_classification_labels(self.project, self._get_annotated_images(), output_format=self.format.lower())
            annotated_images = self._get_annotated_images()
            splits = split_images(annotated_images, self.split_choices, self.split_ratios)
            if self.format == 'COCO':
                return generate_coco_export(self.project, splits, self.setup_type, self.project_name, self.project_description)
            elif self.format == 'YOLO':
                return generate_yolo_export(self.project, splits, self.setup_type, self.project_name, self.project_description)
            elif self.format == 'PASCAL_VOC':
                return generate_pascal_voc_export(self.project, splits, self.setup_type)
            elif self.format == 'CSV':
                return generate_csv_export(self.project, splits, self.setup_type)
            elif self.format == 'MASK':
                return generate_mask_export(self.project, splits)
            raise ValueError(f"Unsupported format: {self.format}")
    
    def export(self) -> str:
        """Export and save ZIP to path. Returns ZIP filepath."""
        self.path.mkdir(parents=True, exist_ok=True)
        
        export_io = self._generate_export()
        zip_filename = f'{self.project_name}_{self.format}{"_video" if self.is_video else ""}.zip'
        zip_path = self.path / zip_filename

        with open(zip_path, 'wb') as f:
            f.write(export_io.getvalue())

        n_items = len(self.videos) if self.is_video else len(self._get_annotated_images())
        logger.info(f"Exported {self.format} ({'video' if self.is_video else 'image'}) for {self.project_name} to {zip_path} ({n_items} items)")
        return str(zip_path)