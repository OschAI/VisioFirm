# visiofirm/projects.py
"""
VisioFirm Projects API Module

This module provides a Pythonic interface for managing projects, mirroring the web interface functionality.
It allows listing existing projects and creating new ones with optional data import from local paths (files, folders, archives).

Dependencies: Assumes the same environment as the Flask app, with access to config, models, utils, etc.
Supports setup types: 'Bounding Box', 'Oriented Bounding Box', 'Segmentation' (existing).
Future: 'Classification' can be added by extending Project model (e.g., annotations without geometry).

Usage:
    from visiofirm.projects import VFProjects
    from visiofirm.config import PROJECTS_FOLDER  # Optional, for custom folder

    # List projects
    projects = VFProjects.list(projects_folder=PROJECTS_FOLDER)

    # Create new project
    new_project = VFProjects.new_project(
        classes=['car', 'truck'],  # Required: non-empty list of class names
        data='/path/to/zip/or/folder/or/rar/or...',  # Required: path to data
        setup_type='Bounding Box',  # Required
        name='MyProject',  # Optional: auto-generates 'VisioFirm', 'VisioFirm_1', etc.
        description='A test project',  # Optional
        projects_folder=PROJECTS_FOLDER  # Optional: custom projects root
    )
    # Returns the Project instance

    # Get overview
    overview = VFProjects.get_project_overview('MyProject')

    # Plot overview
    VFProjects.plot_project_overview('MyProject', output_dir='/path/to/plots')
"""

import os
import shutil
import tempfile
import zipfile
import tarfile
import rarfile 
from werkzeug.utils import secure_filename
import sqlite3

from visiofirm.config import PROJECTS_FOLDER, VALID_IMAGE_EXTENSIONS, VALID_VIDEO_EXTENSIONS, VALID_SETUP_TYPES, get_cache_folder
from visiofirm.models.user import init_db 
from visiofirm.models import Project
from visiofirm.utils.file_utils import is_valid_image
import logging

# Global init for users DB if using API standalone
init_db()

logger = logging.getLogger(__name__)

# Configure logging for Project
logging.basicConfig(level=logging.INFO)

def generate_unique_project_name(projects_folder=PROJECTS_FOLDER):
    """Generate a unique project name starting from 'VisioFirm'."""
    base_name = "VisioFirm"
    name = base_name
    counter = 1
    while os.path.exists(os.path.join(projects_folder, name)):
        name = f"{base_name}_{counter}"
        counter += 1
    return name

def ensure_unique_project_name(proposed_name, projects_folder=PROJECTS_FOLDER):
    """Ensure the project name is unique by appending a counter if needed."""
    safe_name = secure_filename(proposed_name)
    full_path = os.path.join(projects_folder, safe_name)
    if not os.path.exists(full_path):
        return safe_name
    base, ext = os.path.splitext(safe_name)
    counter = 1
    while True:
        new_name = f"{base}_{counter}{ext if ext else ''}"
        full_path = os.path.join(projects_folder, new_name)
        if not os.path.exists(full_path):
            return new_name
        counter += 1

def extract_archive(file_path, extract_path):
    """Extract archive files (zip, tar, rar) to the specified path and validate images.
    Adapted from dashboard.py.
    """
    ext = os.path.splitext(file_path)[1].lower()
    try:
        if ext == '.zip':
            with zipfile.ZipFile(file_path, 'r') as zip_ref:
                zip_ref.extractall(extract_path)
        elif ext in {'.tar', '.tar.gz', '.tgz'}:
            with tarfile.open(file_path, 'r:*') as tar_ref:
                tar_ref.extractall(extract_path)
        elif ext == '.rar':
            with rarfile.RarFile(file_path) as rar_ref:
                rar_ref.extractall(extract_path)
        # Validate and remove corrupted images
        for root, _, filenames in os.walk(extract_path):
            for fname in filenames:
                if os.path.splitext(fname)[1].lower() in VALID_IMAGE_EXTENSIONS:
                    full_path = os.path.join(root, fname)
                    if not is_valid_image(full_path):
                        os.remove(full_path)
                        logger.warning(f"Removed corrupted extracted image: {full_path}")
    except Exception as e:
        logger.error(f"Error extracting archive {file_path}: {e}")
        raise

def process_local_data_path(project, source_path, class_list):
    """Process a local data path (file or directory) and import images/annotations to the project.
    - If source_path is a file (archive), extracts to temp and processes as directory.
    - If directory, recursively finds images and annotations.
    - Adds images to project.images_path and DB.
    - Parses annotations using fallback logic (COCO, YOLO, TXT) to handle subdir structures.
    - Uses NameMatcher for class matching (class_list is non-empty).
    Adapted from dashboard.py create_project and project.py parse_and_add_annotations.
    """
    created_temp_dir = None
    original_source = source_path
    try:
        if os.path.isfile(source_path):
            ext = os.path.splitext(source_path)[1].lower()
            if ext in {'.zip', '.tar', '.tar.gz', '.tgz', '.rar'}:
                # Extract archive to temp (in cache, but will clean)
                created_temp_dir = tempfile.mkdtemp(dir=get_cache_folder())
                extract_archive(source_path, created_temp_dir)
                source_path = created_temp_dir  # Process as dir
            else:
                # Single file handling
                if os.path.splitext(source_path)[1].lower() in VALID_IMAGE_EXTENSIONS:
                    images_path = os.path.join(os.path.dirname(project.db_path), 'images')
                    os.makedirs(images_path, exist_ok=True)
                    filename = os.path.basename(source_path)
                    final_path = os.path.join(images_path, secure_filename(filename))
                    if not os.path.exists(final_path):
                        shutil.copy2(source_path, final_path)
                    project.add_image(final_path)
                    return  # No annotations
                elif os.path.splitext(source_path)[1].lower() in {'.json', '.yaml', '.txt'}:
                    logger.warning(f"Single annotation file {source_path} provided without images; skipping.")
                    return
                else:
                    raise ValueError(f"Unsupported single file type: {source_path}")

        if os.path.isdir(source_path):
            # Process directory
            images_path = os.path.join(os.path.dirname(project.db_path), 'images')
            os.makedirs(images_path, exist_ok=True)

            # Find all files recursively
            all_files = []
            for root, _, filenames in os.walk(source_path):
                for fname in filenames:
                    all_files.append(os.path.join(root, fname))

            # Separate images and annotations
            image_paths = [f for f in all_files if os.path.splitext(f)[1].lower() in VALID_IMAGE_EXTENSIONS]
            annotation_files = [f for f in all_files if os.path.splitext(f)[1].lower() in {'.json', '.yaml', '.txt'}]

            # Copy images to flat structure
            added_images = []
            for img_path in image_paths:
                if is_valid_image(img_path):
                    filename = os.path.basename(img_path)
                    final_path = os.path.join(images_path, secure_filename(filename))
                    if not os.path.exists(final_path):
                        shutil.copy2(img_path, final_path)
                    added_images.append(os.path.abspath(final_path))
                    project.add_image(final_path)
                else:
                    logger.warning(f"Skipping corrupted image: {img_path}")

            if added_images:
                logger.info(f"Added {len(added_images)} images from {original_source}")
            else:
                logger.warning(f"No valid images found in {original_source}")

            if "Video" in project.setup_type:
                videos_path = os.path.join(os.path.dirname(project.db_path), 'videos')
                os.makedirs(videos_path, exist_ok=True)
                # Similar logic for moving videos and extracting
                video_paths = [f for f in all_files if os.path.splitext(f)[1].lower() in VALID_VIDEO_EXTENSIONS]
                for vid_path in video_paths:
                    filename = os.path.basename(vid_path)
                    final_path = os.path.join(videos_path, secure_filename(filename))
                    if not os.path.exists(final_path):
                        shutil.copy2(vid_path, final_path)
                    video_id = project.add_video(final_path)
                    if video_id:
                        project.extract_and_add_frames(video_id, frame_sampling=1)

            # Parse annotations using project's method (handles subdirs recursively)
            # Get all added images (including extracted frames) from DB
            added_images = [img[1] for img in project.get_images()]
            if added_images:
                project.parse_and_add_annotations(source_path, added_images)
            else:
                logger.info(f"No images to annotate from {original_source}")
    finally:
        # Cleanup: Always remove created_temp_dir
        if created_temp_dir and os.path.exists(created_temp_dir):
            shutil.rmtree(created_temp_dir, ignore_errors=True)
            logger.info(f"Cleaned temp dir: {created_temp_dir}")

class VFProjects:
    """Main API class for managing VisioFirm projects."""

    @classmethod
    def list(cls, projects_folder=PROJECTS_FOLDER):
        """List all existing projects.
        
        Returns:
            list: List of dicts with project info (name, path, creation_date if available).
        """
        projects = []
        if not os.path.exists(projects_folder):
            return projects

        for project_name in os.listdir(projects_folder):
            if project_name in ['temp_chunks', 'weights']:
                continue
            project_path = os.path.join(projects_folder, project_name)
            if os.path.isdir(project_path):
                db_path = os.path.join(project_path, 'config.db')
                creation_date = None
                if os.path.exists(db_path):
                    try:
                        with sqlite3.connect(db_path) as conn:
                            cursor = conn.cursor()
                            cursor.execute('SELECT creation_date FROM Project_Configuration WHERE project_name = ?', (project_name,))
                            result = cursor.fetchone()
                            creation_date = result[0] if result else None
                    except Exception as e:
                        logger.error(f"Error fetching creation date for {project_name}: {e}")

                projects.append({
                    'name': project_name,
                    'path': project_path,
                    'creation_date': creation_date
                })

        # Sort by creation_date descending
        projects.sort(key=lambda p: p['creation_date'] or '', reverse=True)
        return projects

    @classmethod
    def new_project(cls, classes, data, setup_type, name=None, description='', projects_folder=PROJECTS_FOLDER):
        """
        Create a new project, importing data from a local path.
        
        Args:
            classes (list): Non-empty list of class names.
            data (str): Path to local data (file/archive or directory with images/annotations).
            setup_type (str): 'Bounding Box', 'Oriented Bounding Box', or 'Segmentation'.
            name (str, optional): Project name. If None, generates unique 'VisioFirm', 'VisioFirm_1', etc.
            description (str, optional): Project description.
            projects_folder (str, optional): Custom projects root folder.
        
        Returns:
            Project: The created Project instance.
        
        Raises:
            ValueError: If classes is empty, data/setup_type not provided, or data path issues.
        """
        if classes is None or len(classes) == 0:
            raise ValueError("classes must be a non-empty list")
        if data is None:
            raise ValueError("data is required")
        if setup_type is None:
            raise ValueError("setup_type is required")
        if not isinstance(classes, list):
            raise ValueError("classes must be a list")
        if setup_type not in VALID_SETUP_TYPES:
            raise ValueError(f"Unsupported setup_type: {setup_type}. Supported: Bounding Box, Oriented Bounding Box, Segmentation, Classification, Video Detection, Video Segmentation.")
        if not os.path.exists(data):
            raise ValueError(f"Data path does not exist: {data}")

        # Ensure projects folder exists
        os.makedirs(projects_folder, exist_ok=True)

        # Generate/ensure unique name
        if name is None:
            name = generate_unique_project_name(projects_folder)
        else:
            name = ensure_unique_project_name(name, projects_folder)

        # Create project path and instance
        project_path = os.path.join(projects_folder, secure_filename(name))
        os.makedirs(project_path, exist_ok=True)
        project = Project(name, description, setup_type, project_path)

        # Add classes (non-empty)
        project.add_classes(classes)
        logger.info(f"Added {len(classes)} classes to project {name}")

        # Import data
        process_local_data_path(project, data, classes)
        logger.info(f"Imported data from {data} to project {name}")

        logger.info(f"Created project: {name} at {project_path}")
        return project

    @classmethod
    def get_project(cls, name, projects_folder=PROJECTS_FOLDER):
        """Retrieve an existing Project by name.
        
        Returns:
            Project or None: If project exists.
        """
        project_path = os.path.join(projects_folder, secure_filename(name))
        if os.path.exists(project_path):
            return Project(name, '', '', project_path)
        return None

    @classmethod
    def get_project_overview(cls, name, projects_folder=PROJECTS_FOLDER):
        """Retrieve overview stats as dict, like frontend /get_project_overview."""
        project = cls.get_project(name, projects_folder)
        if not project:
            return {'error': 'Project not found'}

        total_images = project.get_image_count()
        annotated_images = project.get_annotated_image_count()
        non_annotated_images = total_images - annotated_images
        class_distribution = project.get_class_distribution()
        annotations_per_image = project.get_annotations_per_image()
        setup_type = project.get_setup_type()
        classes = project.get_classes()

        # Description from DB
        with sqlite3.connect(project.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT description FROM Project_Configuration WHERE project_name = ?', (name,))
            description = cursor.fetchone()[0] or ''

        return {
            'name': name,
            'description': description,
            'setup_type': setup_type,
            'classes': classes,
            'total_images': total_images,
            'annotated_images': annotated_images,
            'non_annotated_images': non_annotated_images,
            'class_distribution': class_distribution,
            'annotations_per_image': annotations_per_image
        }

    @classmethod
    def plot_project_overview(cls, name, projects_folder=PROJECTS_FOLDER, output_dir=None, show=True):
        """Generate and display/save plots for project overview using matplotlib.
        
        Args:
            name: Project name.
            output_dir: Optional dir to save PNG.
            show: If True, plt.show() (blocks in scripts).
        
        Returns:
            matplotlib Figure.
        """
        data = cls.get_project_overview(name, projects_folder)
        if 'error' in data:
            raise ValueError(data['error'])

        import matplotlib.pyplot as plt

        fig, axs = plt.subplots(1, 3, figsize=(15, 5))

        # Pie: Annotation status
        axs[0].pie([data['annotated_images'], data['non_annotated_images']],
                   labels=['Annotated', 'Non-annotated'], autopct='%1.1f%%')
        axs[0].set_title('Image Annotation Status')

        # Bar: Class distribution
        classes = list(data['class_distribution'].keys())
        counts = list(data['class_distribution'].values())
        axs[1].bar(classes, counts)
        axs[1].set_title('Class Distribution')
        axs[1].tick_params(axis='x', rotation=45)

        # Hist: Annotations per image
        unique_counts = len(set(data['annotations_per_image']))
        bins = min(10, unique_counts) if unique_counts > 0 else 1
        axs[2].hist(data['annotations_per_image'], bins=bins)
        axs[2].set_title('Annotations per Image')
        axs[2].set_xlabel('Number of Annotations')
        axs[2].set_ylabel('Number of Images')

        plt.tight_layout()

        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
            filepath = os.path.join(output_dir, f'{name}_overview.png')
            plt.savefig(filepath)
            logger.info(f"Plots saved to {filepath}")

        if show:
            plt.show()

        return fig

    @classmethod
    def delete_project(cls, name, projects_folder=PROJECTS_FOLDER):
        """Delete a project by name.
        
        Returns:
            bool: True if deleted.
        """
        project_path = os.path.join(projects_folder, secure_filename(name))
        if os.path.exists(project_path):
            shutil.rmtree(project_path)
            logger.info(f"Deleted project {name}")
            return True
        logger.warning(f"Project {name} not found")
        return False