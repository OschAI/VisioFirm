from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.templating import Jinja2Templates
from visiofirm.config import PROJECTS_FOLDER
from visiofirm.models.user import init_db
from visiofirm.routes.auth import router as auth_router
from visiofirm.routes.dashboard import router as dashboard_router
from visiofirm.routes.annotation import router as annotation_router
import os
from visiofirm.security import SECRET_KEY

app_instance = None

def create_app():
    global app_instance
    if app_instance is None:
        app_instance = FastAPI(title="VisioFirm", description="Fast AI-powered image annotation tool")
        
        templates = Jinja2Templates(directory="visiofirm/templates")
        app_instance.mount("/static", StaticFiles(directory="visiofirm/static"), name="static")
        
        # Config
        app_instance.state.max_content_length = 20 * 1024 * 1024  # 20MB limit 
        app_instance.state.secret_key = SECRET_KEY
        
        # Ensure folders
        os.makedirs(PROJECTS_FOLDER, exist_ok=True)
        
        # Startup: Init DB
        @app_instance.on_event("startup")
        async def startup_event():
            init_db()
        
        # Include routers (auth first; dashboard next; annotation last)
        app_instance.include_router(auth_router)
        app_instance.include_router(dashboard_router)
        app_instance.include_router(annotation_router)
        
        # Serve project files
        @app_instance.get("/projects/{filename:path}")
        async def serve_project_file(filename: str):
            file_path = os.path.join(PROJECTS_FOLDER, filename)
            if not os.path.exists(file_path):
                raise HTTPException(status_code=404, detail="File not found")
            return FileResponse(file_path)
    
    return app_instance