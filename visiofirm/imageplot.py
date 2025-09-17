# New file: visiofirm/imageplot.py
"""
VisioFirm Image Plot API Module

This module provides a Pythonic interface for plotting/debugging images with annotations (API-only).

Dependencies: matplotlib, Pillow.

Usage:
    from visiofirm.imageplot import VFImagePlot
    from visiofirm.projects import VFProjects

    proj = VFProjects.get_project('MyProject')
    plotter = VFImagePlot(
        project=proj,
        image_id=1,  # Or image_name='img.jpg'
        image_name=None,
        output_path='/path/to/save/plot.png',  # Optional; saves PNG
        show=True  # Display if no path (blocks)
    )
    plotter.plot()  # Plots image + annotations (bbox/seg); returns fig
"""

import matplotlib.pyplot as plt
import matplotlib.patches as patches
from PIL import Image as PILImage
import os
import json
import logging
from typing import Optional, Union
from pathlib import Path

from visiofirm.projects import Project

logger = logging.getLogger(__name__)

class VFImagePlot:
    """
    API for plotting an image with annotations for debugging.
    
    Args:
        project: Project instance.
        image_id: Optional DB image_id (int).
        image_name: Optional filename (str; fuzzy match).
        output_path: Optional path to save PNG.
        show: If True and no output_path, plt.show() (blocks).
    """
    def __init__(
        self,
        project: Project,
        image_id: Optional[int] = None,
        image_name: Optional[str] = None,
        output_path: Optional[str] = None,
        show: bool = False
    ):
        if not (image_id or image_name):
            raise ValueError("Provide image_id or image_name")
        self.project = project
        self.image_id = image_id
        self.image_name = image_name
        self.output_path = output_path
        self.show = show and not output_path
        self.fig = None
        self._load_image_and_annotations()

    def _load_image_and_annotations(self):
        """Load image and annotations."""
        import sqlite3
        with sqlite3.connect(self.project.db_path) as conn:
            cursor = conn.cursor()
            if self.image_id:
                cursor.execute('SELECT absolute_path, width, height FROM Images WHERE image_id = ?', (self.image_id,))
            else:
                base = os.path.splitext(self.image_name)[0] if self.image_name else ''
                cursor.execute('SELECT image_id, absolute_path, width, height FROM Images WHERE absolute_path LIKE ?', (f'%{base}%',))
                result = cursor.fetchone()
                if result:
                    self.image_id = result[0]
                else:
                    raise ValueError(f"Image not found: id={self.image_id}, name={self.image_name}")
            if not result:
                raise ValueError(f"Image not found")
            self.abs_path, self.img_w, self.img_h = result[1], result[2], result[3]

        if not os.path.exists(self.abs_path):
            raise ValueError(f"Image file missing: {self.abs_path}")

        self.annotations = self.project.get_annotations(self.abs_path)
        if self.project.get_setup_type() == "Segmentation":
            # Load seg as polygons
            for anno in self.annotations:
                if anno.get('segmentation'):
                    seg = json.loads(anno['segmentation']) if isinstance(anno['segmentation'], str) else anno['segmentation']
                    anno['polygon'] = seg

        logger.info(f"Loaded {len(self.annotations)} annotations for {self.abs_path}")

    def plot(self):
        """Plot image with annotations (bbox/polygons). Returns matplotlib Figure."""
        img = PILImage.open(self.abs_path)
        fig, ax = plt.subplots(1, figsize=(self.img_w/100, self.img_h/100))
        ax.imshow(img)
        ax.set_title(f"{self.project.name} - {os.path.basename(self.abs_path)}")

        colors = plt.cm.tab10.colors  # Cycle colors
        for i, anno in enumerate(self.annotations):
            color = colors[i % len(colors)]
            label = anno['label']
            if self.project.get_setup_type() in ("Bounding Box", "Oriented Bounding Box"):
                if 'bbox' in anno:
                    x, y, w, h = anno['bbox']
                    if self.project.get_setup_type() == "Oriented Bounding Box" and 'rotation' in anno:
                        # Simple rotated rect (approx)
                        rect = patches.Rectangle((x, y), w, h, angle=anno['rotation'], linewidth=2, edgecolor=color, facecolor='none')
                    else:
                        rect = patches.Rectangle((x, y), w, h, linewidth=2, edgecolor=color, facecolor='none')
                    ax.add_patch(rect)
                    ax.text(x, y-5, label, color=color, fontsize=8, weight='bold')
            elif self.project.get_setup_type() == "Segmentation" and 'polygon' in anno:
                poly = anno['polygon']
                if len(poly) >= 6:  # Min triangle
                    poly_x = poly[::2]
                    poly_y = poly[1::2]
                    poly_patch = patches.Polygon(list(zip(poly_x, poly_y)), linewidth=2, edgecolor=color, facecolor='none')
                    ax.add_patch(poly_patch)
                    ax.text(poly_x[0], poly_y[0]-5, label, color=color, fontsize=8, weight='bold')

        ax.axis('off')
        self.fig = fig

        if self.output_path:
            self.path = Path(self.output_path)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fig.savefig(self.output_path, bbox_inches='tight', dpi=150)
            logger.info(f"Plotted {self.abs_path} to {self.output_path}")
            plt.close(fig)
        elif self.show:
            plt.show()

        return fig