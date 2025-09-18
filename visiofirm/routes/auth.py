#visiofirm/routes/auth.py
from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import RedirectResponse, HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from visiofirm.models.user import create_user, get_user_by_username, get_user_by_email, update_user, User
from visiofirm.security import verify_password, create_access_token, get_current_user_from_cookie
from typing import Optional
import os

router = APIRouter(prefix="/auth")
module_dir = os.path.dirname(__file__)
templates_dir = os.path.join(module_dir, "..", "templates")
templates = Jinja2Templates(directory=templates_dir)

@router.get("/login", response_class=HTMLResponse, name="auth.login")
async def login_get(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@router.post("/login", name="auth.login_post")
async def login_post(
    response: Response,
    identifier: str = Form(...),
    password: str = Form(...)
):
    user_data = get_user_by_username(identifier) or get_user_by_email(identifier)
    if not user_data or not verify_password(password, user_data[2]):
        # For error, redirect with message
        return RedirectResponse(url="/auth/login?flash=error&message=Invalid username/email or password", status_code=303)
    
    access_token_expires = None
    access_token = create_access_token(
        data={"sub": str(user_data[0])}, expires_delta=access_token_expires
    )
    response = RedirectResponse(url="/dashboard?flash=success&message=Login successful!", status_code=303)
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True
    )
    return response

@router.get("/register", response_class=HTMLResponse, name="auth.register")
async def register_get(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@router.post("/register", name="auth.register_post")
async def register_post(
    response: Response,
    first_name: str = Form(...),
    last_name: str = Form(...),
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    company: str = Form("")
):
    if not all([first_name, last_name, username, email, password]):
        return RedirectResponse(url="/auth/register?flash=error&message=All required fields must be filled", status_code=303)
    
    if create_user(first_name, last_name, username, email, password, company):
        return RedirectResponse(url="/auth/login?flash=success&message=Registration successful. Please log in.", status_code=303)
    else:
        return RedirectResponse(url="/auth/register?flash=error&message=Username or email already exists", status_code=303)

@router.get("/profile", response_class=HTMLResponse, name="auth.profile")
async def profile_get(request: Request, current_user: User = Depends(get_current_user_from_cookie)):
    return templates.TemplateResponse("profile.html", {"request": request, "user": current_user})

@router.post("/profile", name="auth.profile_post")
async def profile_post(
    response: Response,
    current_user: User = Depends(get_current_user_from_cookie),
    first_name: Optional[str] = Form(None),
    last_name: Optional[str] = Form(None),
    email: Optional[str] = Form(None),
    password: Optional[str] = Form(None),
    company: Optional[str] = Form(None),
    regenerate_api_key: Optional[bool] = Form(False)
):
    updates = {}
    if first_name:
        updates['first_name'] = first_name
    if last_name:
        updates['last_name'] = last_name
    if email:
        updates['email'] = email
    if password:
        updates['password'] = password 
    if company:
        updates['company'] = company
    if not updates:
        return RedirectResponse(url="/auth/profile?flash=error&message=No changes provided", status_code=303)
    if regenerate_api_key:
        from visiofirm.models.user import generate_api_key
        new_key = generate_api_key(current_user.id)
        if new_key:
            updates['api_key'] = new_key

    success = update_user(current_user.id, updates)
    if success:
        return RedirectResponse(url="/auth/profile?flash=success&message=Profile updated successfully!", status_code=303)
    else:
        return RedirectResponse(url="/auth/profile?flash=error&message=Email already exists", status_code=303)

@router.get("/profile_data", name="auth.profile_data")
async def profile_data(current_user: User = Depends(get_current_user_from_cookie)):
    from visiofirm.models.user import generate_api_key
    # Auto-generate if missing
    if not current_user.api_key:
        current_user.api_key = generate_api_key(current_user.id) or ""
    try:
        avatar = current_user.avatar
        return {"success": True, "avatar": avatar, "api_key": current_user.api_key}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/logout", name="auth.logout")
async def logout(response: Response):
    response = RedirectResponse(url="/auth/login?flash=success&message=You have been logged out.", status_code=303)
    response.delete_cookie("access_token")
    return response

@router.get("/reset_password", response_class=HTMLResponse, name="auth.reset_password")
async def reset_password_get(request: Request):
    return templates.TemplateResponse("reset.html", {"request": request})

@router.post("/reset_password", name="auth.reset_password_post")
async def reset_password_post(
    response: Response,
    identifier: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(...)
):
    if not password:
        return RedirectResponse(url="/auth/reset_password?flash=error&message=Password cannot be empty", status_code=303)
    if password != password_confirm:
        return RedirectResponse(url="/auth/reset_password?flash=error&message=Passwords do not match", status_code=303)
    
    user_data = get_user_by_username(identifier) or get_user_by_email(identifier)
    if user_data:
        success = update_user(user_data[0], {'password': password})  # Hashes in update_user
        if success:
            return RedirectResponse(url="/auth/login?flash=success&message=Password reset successful. Please log in.", status_code=303)
        else:
            return RedirectResponse(url="/auth/reset_password?flash=error&message=Error resetting password", status_code=303)
    else:
        return RedirectResponse(url="/auth/reset_password?flash=error&message=Invalid username or email", status_code=303)
    
@router.post("/generate_api_key", name="auth.generate_api_key")
async def generate_api_key_post(current_user: User = Depends(get_current_user_from_cookie)):
    from visiofirm.models.user import generate_api_key
    new_key = generate_api_key(current_user.id)
    if new_key:
        return {"success": True, "api_key": new_key}
    raise HTTPException(status_code=500, detail="Failed to generate API key")