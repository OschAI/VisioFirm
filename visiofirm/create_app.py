from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Depends, status, Request
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

# Force MIME type override at module level (fallback, but we'll override in custom class anyway)
mimetypes.add_type("application/javascript", ".js", strict=True)
mimetypes.add_type("application/javascript", ".min.js", strict=True)
mimetypes.add_type("application/javascript", ".mjs", strict=True)

# Custom StaticFiles to force JS MIME type
from starlette.staticfiles import StaticFiles as StarletteStaticFiles
from starlette.responses import FileResponse as StarletteFileResponse
from starlette.types import Scope, Receive, Send
import typing

class CustomStaticFiles(StarletteStaticFiles):
    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["path"].endswith((".js", ".min.js", ".mjs")):
            # Temporarily patch guess_type for this request
            original_guess = mimetypes.guess_type
            try:
                mimetypes.guess_type = lambda path, strict=None: ("application/javascript", None)
                await super().__call__(scope, receive, send)
            finally:
                mimetypes.guess_type = original_guess
        else:
            await super().__call__(scope, receive, send)

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

        templates = Jinja2Templates(directory=templates_dir)
        app_instance.state.templates = templates
        
        # Mount with custom class to force JS MIME types
        app_instance.mount("/static", CustomStaticFiles(directory=static_dir), name="static")
       
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