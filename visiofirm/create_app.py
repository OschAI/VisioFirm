from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Depends, status, Request  # FIXED: Add Request here
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from visiofirm.config import PROJECTS_FOLDER
from visiofirm.models.user import init_db
from visiofirm.routes.auth import router as auth_router
from visiofirm.routes.dashboard import router as dashboard_router
from visiofirm.routes.annotation import router as annotation_router
from visiofirm.routes.importer import router as import_router
from visiofirm.security import SECRET_KEY
from visiofirm.models.user import User
from visiofirm.routes.dashboard import get_current_user_optional
import os
import mimetypes

app_instance = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    init_db()
    yield

def create_app():
    global app_instance
    if app_instance is None:
        app_instance = FastAPI(
            title="VisioFirm",
            description="Fast AI-powered image annotation tool",
            lifespan=lifespan
        )
       
        # Compute paths relative to this module's directory
        module_dir = os.path.dirname(__file__)
        templates_dir = os.path.join(module_dir, "templates")
        static_dir = os.path.join(module_dir, "static")

        mimetypes.types_map.update({
            '.js': 'application/javascript',
            '.min.js': 'application/javascript',  # Explicit for .min.js if splitext behaves oddly
        })
        
        templates = Jinja2Templates(directory=templates_dir)
        app_instance.state.templates = templates
        app_instance.mount("/static", StaticFiles(directory=static_dir), name="static")
       
        # Config
        app_instance.state.max_content_length = 20 * 1024 * 1024 # 20MB limit
        app_instance.state.secret_key = SECRET_KEY
       
        # Ensure folders
        os.makedirs(PROJECTS_FOLDER, exist_ok=True)
       
        # Include routers (auth first; dashboard next; annotation last)
        app_instance.include_router(auth_router)
        app_instance.include_router(dashboard_router)
        app_instance.include_router(import_router)
        app_instance.include_router(annotation_router)
       
        # FIXED: Type the 'request' param as Request to inject the HTTP Request object
        @app_instance.get("/")
        async def root(request: Request, current_user: User | None = Depends(get_current_user_optional)):
            if current_user:
                return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
            return RedirectResponse(url="/auth/login", status_code=status.HTTP_303_SEE_OTHER)
       
        # Serve project files
        @app_instance.get("/projects/{filename:path}")
        async def serve_project_file(filename: str):
            file_path = os.path.join(PROJECTS_FOLDER, filename)
            if not os.path.exists(file_path):
                raise HTTPException(status_code=404, detail="File not found")
            return FileResponse(file_path)
   
    return app_instance