# visiofirm/routes/dashboard.py
from fastapi import APIRouter, Request, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from visiofirm.security import get_current_user_from_cookie, User
from visiofirm.models import Project
from visiofirm.config import PROJECTS_FOLDER, VALID_IMAGE_EXTENSIONS, VALID_VIDEO_EXTENSIONS
from werkzeug.utils import secure_filename
import os
import logging
from typing import Optional
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard")
module_dir = os.path.dirname(__file__)
templates_dir = os.path.join(module_dir, "..", "templates")
templates = Jinja2Templates(directory=templates_dir)

async def get_current_user_optional(request: Request) -> Optional[User]:
    try:
        return await get_current_user_from_cookie(request)
    except HTTPException:
        return None

@router.get("/", response_class=HTMLResponse)
async def index(request: Request, current_user: Optional[User] = Depends(get_current_user_optional)):
    if current_user is None:
        return RedirectResponse(url="/auth/login?next=/dashboard", status_code=status.HTTP_302_FOUND)

    # Import here to avoid circular import
    from visiofirm.projects import VFProjects

    projects_list = VFProjects.list(PROJECTS_FOLDER) or []
    projects = []

    for p in projects_list:
        # Ensure we use a safe, canonical project folder for all operations
        safe_name = secure_filename(p.get('name', ''))
        project_full_path = os.path.join(PROJECTS_FOLDER, safe_name)

        # skip projects without config.db
        if not os.path.exists(os.path.join(project_full_path, 'config.db')):
            continue

        project = Project(p['name'], '', '', project_full_path)
        try:
            p['setup_type'] = project.get_setup_type()
        except Exception as e:
            logger.warning("Failed to get setup_type for %s: %s", p.get('name'), e)
            p['setup_type'] = ''

        # Always use the canonical path (project_full_path) when listing media
        if 'Video' in p.get('setup_type', ''):
            videos_path = os.path.join(project_full_path, 'videos')
            video_files = []
            if os.path.exists(videos_path):
                try:
                    video_files = [
                        f for f in os.listdir(videos_path)
                        if os.path.isfile(os.path.join(videos_path, f)) and os.path.splitext(f)[1].lower() in VALID_VIDEO_EXTENSIONS
                    ]
                    # newest first
                    video_files = sorted(
                        video_files,
                        key=lambda f: os.path.getmtime(os.path.join(videos_path, f)),
                        reverse=True
                    )
                except Exception as e:
                    logger.error("Error listing videos for %s: %s", safe_name, e)
                    video_files = []
            p['videos'] = [os.path.join('/projects', safe_name, 'videos', vid) for vid in video_files[:3]]
        else:
            images_path = os.path.join(project_full_path, 'images')
            image_files = []
            if os.path.exists(images_path):
                try:
                    image_files = [
                        f for f in os.listdir(images_path)
                        if os.path.isfile(os.path.join(images_path, f)) and os.path.splitext(f)[1].lower() in VALID_IMAGE_EXTENSIONS
                    ]
                    # newest first
                    image_files = sorted(
                        image_files,
                        key=lambda f: os.path.getmtime(os.path.join(images_path, f)),
                        reverse=True
                    )
                except Exception as e:
                    logger.error("Error listing images for %s: %s", safe_name, e)
                    image_files = []
            p['images'] = [os.path.join('/projects', safe_name, 'images', img) for img in image_files[:3]]

        # ensure p has a canonical path field for template use
        p['path'] = project_full_path
        projects.append(p)

    return templates.TemplateResponse('dashboard.html', {"request": request, "projects": projects, "user": current_user})

@router.post("/log_error")
async def log_error(
    request: Request,
    current_user: User = Depends(get_current_user_from_cookie)
):
    tracker = getattr(request.app, "tracker", None)
    data = await request.json()
    error_msg = data.get('message', 'Unknown frontend error')
    endpoint = data.get('endpoint', 'unknown')
    status_code = data.get('status', 0)
    try:
        class FrontendError(Exception):
            pass
        fe = FrontendError(f"Frontend error on {endpoint}: {error_msg} (status: {status_code})")
        if tracker is not None and hasattr(tracker, "log_error"):
            tracker.log_error(fe, step='Frontend error report')
        logger.error(f"Frontend error logged: {error_msg} on {endpoint} (status: {status_code})")
        return {"success": True}
    except Exception as e:
        logger.exception("Failed to log frontend error")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/delete_project/{project_name}")
async def delete_project(request: Request, project_name: str, current_user: User = Depends(get_current_user_from_cookie)):
    # Import here to avoid circular import
    from visiofirm.projects import VFProjects
    logger.info("Deleting project: %s", project_name)
    try:
        deleted = VFProjects.delete_project(project_name, PROJECTS_FOLDER)
    except Exception as e:
        logger.exception("Error deleting project %s", project_name)
        raise HTTPException(status_code=500, detail=str(e))

    if deleted:
        logger.info("Deleted project %s", project_name)
        return {"success": True}
    raise HTTPException(status_code=404, detail='Project not found')

@router.get("/get_project_overview/{project_name}")
async def get_project_overview(request: Request, project_name: str, current_user: User = Depends(get_current_user_from_cookie)):
    safe_name = secure_filename(project_name)
    project_path = os.path.join(PROJECTS_FOLDER, safe_name)
    if not os.path.exists(project_path):
        raise HTTPException(status_code=404, detail='Project not found')

    try:
        project = Project(project_name, '', '', project_path)
        total_images = project.get_image_count() or 0
        annotated_images = project.get_annotated_image_count() or 0
        class_distribution = project.get_class_distribution() or {}
        annotations_per_image = project.get_annotations_per_image() or {}
        non_annotated_images = max(0, total_images - annotated_images)

        data = {
            'total_images': total_images,
            'annotated_images': annotated_images,
            'non_annotated_images': non_annotated_images,
            'class_distribution': class_distribution,
            'annotations_per_image': annotations_per_image
        }
        logger.info("Project overview for %s: %s total, %s annotated", project_name, total_images, annotated_images)
        return data
    except Exception as e:
        logger.exception("Error fetching overview for %s", project_name)
        raise HTTPException(status_code=500, detail=f'Server error: {str(e)}')
