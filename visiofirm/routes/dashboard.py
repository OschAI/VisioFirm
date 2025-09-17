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

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()
module_dir = os.path.dirname(__file__)
templates_dir = os.path.join(module_dir, "..", "templates")
templates = Jinja2Templates(directory=templates_dir)

async def get_current_user_optional(request: Request) -> Optional[User]:
    try:
        return get_current_user_from_cookie(request)
    except HTTPException:
        return None

@router.get("/", response_class=HTMLResponse)
async def index(request: Request, current_user: Optional[User] = Depends(get_current_user_optional)):
    if current_user is None:
        # Redirect to login if not authenticated (mimic Flask @login_required)
        return RedirectResponse(url="/auth/login?next=/", status_code=status.HTTP_302_FOUND)
    
    # Import VFProjects here to avoid circular import issues
    from visiofirm.projects import VFProjects
    
    projects_list = VFProjects.list(PROJECTS_FOLDER)
    projects = []
    for p in projects_list:
        project_full_path = os.path.join(PROJECTS_FOLDER, secure_filename(p['name']))
        if not os.path.exists(os.path.join(project_full_path, 'config.db')):
            continue 
        
        project = Project(p['name'], '', '', project_full_path)
        p['setup_type'] = project.get_setup_type()
        
        if 'Video' in p['setup_type']:
            videos_path = os.path.join(p['path'], 'videos')
            if os.path.exists(videos_path):
                video_files = sorted(
                    [
                        f for f in os.listdir(videos_path)
                        if os.path.isfile(os.path.join(videos_path, f)) and os.path.splitext(f)[1].lower() in VALID_VIDEO_EXTENSIONS
                    ],
                    key=lambda f: os.path.getmtime(os.path.join(videos_path, f))
                )
            else:
                video_files = []
            p['videos'] = [
                os.path.join('/projects', p['name'], 'videos', vid)
                for vid in video_files[:3]
            ]
        else:
            images_path = os.path.join(p['path'], 'images')
            image_files = [
                f for f in os.listdir(images_path)
                if os.path.isfile(os.path.join(images_path, f)) and os.path.splitext(f)[1].lower() in VALID_IMAGE_EXTENSIONS
            ] if os.path.exists(images_path) else []
            p['images'] = [
                os.path.join('/projects', p['name'], 'images', img)
                for img in image_files[:3]
            ]
        projects.append(p)
    return templates.TemplateResponse('dashboard.html', {"request": request, "projects": projects, "user": current_user})

@router.post("/log_error")
async def log_error(
    request: Request,
    current_user: User = Depends(get_current_user_from_cookie)
):
    tracker = request.app.tracker  # Use request.app
    data = await request.json()
    error_msg = data.get('message', 'Unknown frontend error')
    endpoint = data.get('endpoint', 'unknown')
    status_code = data.get('status', 0)
    try:
        class FrontendError(Exception):
            pass
        fe = FrontendError(f"Frontend error on {endpoint}: {error_msg} (status: {status_code})")
        tracker.log_error(fe, step='Frontend error report')
        logger.error(f"Frontend error logged: {error_msg} on {endpoint} (status: {status_code})")
        print(f"Frontend error reported: {error_msg} on {endpoint}")
        return {"success": True}
    except Exception as e:
        logger.error(f"Failed to log frontend error: {e}")
        print(f"Failed to log frontend error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/delete_project/{project_name}")
async def delete_project(request: Request, project_name: str, current_user: User = Depends(get_current_user_from_cookie)):
    print(f"Deleting project: {project_name}")
    # Import VFProjects here to avoid circular import issues
    from visiofirm.projects import VFProjects
    if VFProjects.delete_project(project_name, PROJECTS_FOLDER):
        logger.info(f"Deleted project {project_name}")
        print(f"Project {project_name} deleted successfully")
        return {"success": True}
    print(f"Project {project_name} not found")
    raise HTTPException(status_code=404, detail='Project not found')

@router.get("/get_project_overview/{project_name}")
async def get_project_overview(request: Request, project_name: str, current_user: User = Depends(get_current_user_from_cookie)):
    project_path = os.path.join(PROJECTS_FOLDER, secure_filename(project_name))
    if not os.path.exists(project_path):
        raise HTTPException(status_code=404, detail='Project not found')

    try:
        project = Project(project_name, '', '', project_path)
        total_images = project.get_image_count()
        annotated_images = project.get_annotated_image_count()
        class_distribution = project.get_class_distribution()
        annotations_per_image = project.get_annotations_per_image()
        non_annotated_images = total_images - annotated_images

        data = {
            'total_images': total_images,
            'annotated_images': annotated_images,
            'non_annotated_images': non_annotated_images,
            'class_distribution': class_distribution,
            'annotations_per_image': annotations_per_image
        }
        print(f"Project overview for {project_name}: {total_images} total, {annotated_images} annotated")
        return data
    except Exception as e:
        logger.error(f"Error fetching overview for {project_name}: {e}")
        print(f"Error fetching overview for {project_name}: {str(e)}")
        raise HTTPException(status_code=500, detail=f'Server error: {str(e)}')