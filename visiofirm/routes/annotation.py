# visiofirm/routes/annotation.py
from fastapi import APIRouter, Request, Depends, HTTPException, File, Query
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from visiofirm.security import get_current_user_from_cookie, User
from tqdm import tqdm
import os
import json
from visiofirm.config import PROJECTS_FOLDER, TMP_FOLDER
from visiofirm.projects import VFProjects
from visiofirm.models.project import Project 
from visiofirm.models.user import get_user_by_id
from visiofirm.preannotator import VFPreAnnotator
from visiofirm.blindtrust import VFBlindTrust
from visiofirm.exporter import VFExporter
from visiofirm.imagedownloader import VFImageDownloader
from visiofirm.imageremover import VFImageRemover
from visiofirm.tracker import VFTracker
import logging
import sqlite3
from werkzeug.utils import secure_filename
from typing import Optional
import shutil

router = APIRouter(prefix="/annotation")
module_dir = os.path.dirname(__file__)
templates_dir = os.path.join(module_dir, "..", "templates")
templates = Jinja2Templates(directory=templates_dir)
logger = logging.getLogger(__name__)

# In-memory storage for status (shared for web; API can use instance attrs)
preannotation_status = {}
preannotation_progress = {}
blind_trust_status = {}
blind_trust_progress = {}
preannotation_instances = {}

@router.get('/check_gpu')
async def check_gpu(request: Request): 
    tracker = request.app.tracker 
    tracker.log_step('Checking GPU availability')
    try:
        import torch
        has_gpu = torch.cuda.is_available()
        tracker.log_substep('GPU check completed', details={'available': has_gpu})
        tracker.log_step('GPU check successful')
        logger.info(f"GPU check: {'Available' if has_gpu else 'Not available'}")
        print(f"GPU check: {'Available' if has_gpu else 'Not available'}")
        return {'success': True, 'has_gpu': has_gpu}
    except ImportError as e:
        tracker.log_error(e, step='GPU check')
        logger.error(f"Failed to import torch: {e}")
        print(f"GPU check failed: PyTorch not installed")
        raise HTTPException(status_code=500, detail='PyTorch not installed')
    except Exception as e:
        tracker.log_error(e, step='GPU check')
        logger.error(f"Error checking GPU: {e}")
        print(f"GPU check error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Optional user dependency that returns None if not authenticated (for redirects)
async def get_current_user_optional(request: Request) -> Optional[User]:
    try:
        return get_current_user_from_cookie(request=request)
    except HTTPException:
        return None

@router.post('/ai_preannotator_config')
async def ai_preannotator_config(
    request: Request,
    current_user: User = Depends(get_current_user_from_cookie)
):
    tracker = request.app.tracker  # Use request.app instead of get_current_app()
    form = await request.form()
    tracker.log_step('Configuring AI preannotator', details={'project_name': form.get('project_name'), 'mode': form.get('mode')})
    try:
        project_name = form.get('project_name')
        mode = form.get('mode')
        device = form.get('processing_unit', 'cpu')
        box_threshold = float(form.get('box_threshold', 0.2))

        if not project_name or not mode:
            raise ValueError('Project name and mode required')

        proj = VFProjects.get_project(project_name)
        if not proj:
            raise ValueError('Project not found')

        key = project_name  # Use project_name as key for status
        if preannotation_status.get(key) == 'running':
            raise RuntimeError('Pre-annotation is already running')

        print(f"VisioFirm is pre-annotating your images for project '{project_name}' using {mode} mode...")

        # Create instance
        if mode == 'zero-shot':
            preannotator = VFPreAnnotator(
                project=proj,
                mode=mode,
                device=device,
                box_threshold=box_threshold,
                dino_model=form.get('dino_model', 'tiny')
            )
            model_details = form.get('dino_model', 'tiny')
        elif mode == 'custom-model':
            preannotator = VFPreAnnotator(
                project=proj,
                mode=mode,
                device=device,
                box_threshold=box_threshold,
                model_path=form.get('model_path', 'yolov10x.pt')
            )
            model_details = form.get('model_path', 'yolov10x.pt')
        elif mode == 'clip':
            preannotator = VFPreAnnotator(
                project=proj,
                mode=mode,
                device=device,
                box_threshold=box_threshold  #ignored for classif
            )
            model_details = 'CLIP'
        else:
            raise ValueError('Invalid mode')

        preannotation_status[key] = 'running'
        preannotation_progress[key] = 0

        # Background run with callback to update shared status
        def callback(status_dict):
            preannotation_status[key] = status_dict['status']
            progress = status_dict.get('progress', 0)
            preannotation_progress[key] = progress
            tracker.log_substep('Preannotation progress update', details=status_dict)

        preannotator.run_threaded(callback=callback)
        tracker.log_step('Pre-annotation started successfully', details={'project': project_name, 'mode': mode, 'device': device, 'box_threshold': box_threshold})
        print(f"VisioFirm is pre-annotating your images for project '{project_name}' using {mode} mode ({model_details}), threshold {box_threshold}...")
        return {'success': True, 'message': 'Pre-annotation started'}

    except Exception as e:
        tracker.log_error(e, step='AI preannotator config')
        logger.error(f"Error in ai_preannotator_config: {e}")
        print(f"Pre-annotation failed for '{project_name}': {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get('/check_tracking_status')
async def check_tracking_status(
    request: Request,
    current_user: User = Depends(get_current_user_from_cookie)
):
    key = request.query_params.get('key')
    if not key:
        raise HTTPException(status_code=400, detail='Key required')
    status = tracking_status.get(key, 'not_started')
    progress = tracking_progress.get(key, 0)
    results = tracking_results.get(key) if status == 'completed' else None
    return {'success': True, 'status': status, 'progress': progress, 'results': results}
    
@router.get('/check_preannotation_status')
async def check_preannotation_status(
    request: Request,
    current_user: User = Depends(get_current_user_from_cookie)
):
    project_name = request.query_params.get('project_name')
    if not project_name:
        raise HTTPException(status_code=400, detail='Project name required')
    status = preannotation_status.get(project_name, 'not_started')
    progress = preannotation_progress.get(project_name, 0)
    return {'success': True, 'status': status, 'progress': progress}

@router.post('/blind_trust')
async def blind_trust(
    request: Request,
    current_user: User = Depends(get_current_user_from_cookie)
):
    tracker = request.app.tracker  # Use request.app
    form = await request.form()
    tracker.log_step('Starting blind trust', details={'project_name': form.get('project_name'), 'threshold': form.get('confidence_threshold', 0.5)})
    try:
        project_name = form.get('project_name')
        confidence_threshold = float(form.get('confidence_threshold', 0.5))

        if not project_name:
            raise ValueError('Project name required')

        proj = VFProjects.get_project(project_name)
        if not proj:
            raise ValueError('Project not found')

        key = project_name
        if blind_trust_status.get(key) == 'running':
            raise RuntimeError('Blind Trust is already running')

        print(f"VisioFirm is running blind trust for project '{project_name}' (threshold: {confidence_threshold})...")

        blind_trust = VFBlindTrust(
            project=proj,
            confidence_threshold=confidence_threshold,
            user_id=current_user.id
        )

        # Set initial status
        blind_trust_status[key] = 'running'
        blind_trust_progress[key] = 0

        # Background run with callback
        def callback(status_dict):
            blind_trust_status[key] = status_dict['status']
            progress = status_dict.get('progress', 0)
            blind_trust_progress[key] = progress
            tracker.log_substep('Blind trust progress update', details=status_dict)

        blind_trust.run_threaded(callback=callback)
        tracker.log_step('Blind trust started successfully', details={'project': project_name, 'threshold': confidence_threshold, 'user_id': current_user.id})
        print(f"VisioFirm is running blind trust for project '{project_name}' (threshold: {confidence_threshold})...")
        return {'success': True, 'message': 'Blind Trust started'}

    except Exception as e:
        tracker.log_error(e, step='Blind trust')
        logger.error(f"Error in blind_trust: {e}")
        print(f"Blind trust failed for '{project_name}': {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get('/check_blind_trust_status')
async def check_blind_trust_status(
    request: Request,
    current_user: User = Depends(get_current_user_from_cookie)
):
    project_name = request.query_params.get('project_name')
    if not project_name:
        raise HTTPException(status_code=400, detail='Project name required')
    status = blind_trust_status.get(project_name, 'not_started')
    progress = blind_trust_progress.get(project_name, 0)
    return {'success': True, 'status': status, 'progress': progress}

@router.get('/{project_name}', response_class=HTMLResponse)
async def annotation(
    project_name: str,
    request: Request,
    current_user: User = Depends(get_current_user_from_cookie)
):
    print(f"Starting annotation for project: {project_name}") 
    tracker = request.app.tracker  # Use request.app
    tracker.log_step('Loading annotation interface', details={'project_name': project_name})
    try:
        project_path = os.path.join(PROJECTS_FOLDER, project_name)
        if not os.path.exists(project_path):
            raise ValueError('Project not found')
        
        project = Project(project_name, "", "", project_path)
        class_list = project.get_classes()
        setup_type = project.get_setup_type()
        
        if "Video" in setup_type:
            raw_videos = project.get_videos()  # List of tuples: (video_id, absolute_path, name, duration, fps, frame_count)
            video_data = []  # List of dicts for template
            for vid in raw_videos:
                if len(vid) < 6:
                    logger.warning(f"Invalid video tuple in get_videos(): {vid}")
                    continue
                video_id = vid[0]
                abs_path = vid[1]
                filename = os.path.basename(abs_path)
                url = os.path.join('/projects', project_name, 'videos', filename)
                date = '2023-01-01'  # Placeholder; add creation_date to Videos table if needed
                video_data.append({
                    'id': video_id,
                    'filename': filename,
                    'url': url,
                    'date': date,
                    'annotated': False,  # Placeholder; adapt if needed (e.g., check if any frames annotated)
                    'preannotated': False  # Placeholder
                })
            image_annotators = {}  # No annotators for videos (adapt if needed for frames)
            tracker.log_substep('Project data loaded', details={'videos_count': len(video_data), 'classes_count': len(class_list)})
            tracker.log_step('Annotation interface loaded successfully', details={'project_name': project_name, 'setup_type': setup_type})
            print(f"Annotation interface loaded for {project_name} ({len(video_data)} videos)")
            return templates.TemplateResponse('video_annotation.html',
                                {"request": request,
                                "project_name": project_name,
                                "videos": video_data,  # Use "videos" key (frontend can adapt)
                                "classes": class_list,
                                "setup_type": setup_type,
                                "image_annotators": image_annotators,
                                "user": current_user,
                                "current_user_avatar": current_user.avatar})
        else:
            raw_images = project.get_images()  # List of tuples, e.g., [(id, path), ...] or [(id, path, date), ...]
            image_data = []  # List of dicts for template
            
            with sqlite3.connect(project.db_path) as conn:
                cursor = conn.cursor()

                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS ReviewedImages (
                        image_id INTEGER PRIMARY KEY,
                        reviewed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        user_id INTEGER
                    )
                ''')
                
                cursor.execute('''
                    SELECT i.absolute_path
                    FROM Images i
                    LEFT JOIN Annotations a ON i.image_id = a.image_id
                    LEFT JOIN ReviewedImages r ON i.image_id = r.image_id
                    WHERE a.annotation_id IS NOT NULL OR r.image_id IS NOT NULL
                    GROUP BY i.image_id
                ''')
                annotated_images = {
                    os.path.join('/projects', project_name, 'images', os.path.basename(row[0]))
                    for row in cursor.fetchall()
                }
            
            cursor.execute('''
                SELECT i.absolute_path
                FROM Images i
                JOIN Preannotations p ON i.image_id = p.image_id
                LEFT JOIN Annotations a ON i.image_id = a.image_id
                LEFT JOIN ReviewedImages r ON i.image_id = r.image_id
                WHERE a.annotation_id IS NULL AND r.image_id IS NULL
                GROUP BY i.image_id
            ''')
            preannotated_images = {
                os.path.join('/projects', project_name, 'images', os.path.basename(row[0]))
                for row in cursor.fetchall()
            }
            
            for img in raw_images:
                if len(img) < 2:
                    logger.warning(f"Invalid image tuple in get_images(): {img}")
                    continue
                img_id = img[0]
                abs_path = img[1]
                filename = os.path.basename(abs_path)
                url = os.path.join('/projects', project_name, 'images', filename)
                
                date = img[2] if len(img) > 2 else '2023-01-01'
                
                annotated = url in annotated_images
                pre_anno = url in preannotated_images
                
                image_data.append({
                    'id': img_id,
                    'filename': filename,
                    'url': url,
                    'date': date, 
                    'annotated': annotated,
                    'preannotated': pre_anno
                })
            
            cursor.execute('''
                SELECT i.absolute_path, r.user_id
                FROM Images i
                LEFT JOIN ReviewedImages r ON i.image_id = r.image_id
            ''')
            rows = cursor.fetchall()
            image_annotators = {}
            for row in rows:
                if len(row) < 2:
                    continue
                absolute_path = row[0]
                user_id = row[1]
                image_url = os.path.join('/projects', project_name, 'images', os.path.basename(absolute_path))
                if user_id:
                    user = get_user_by_id(user_id)
                    image_annotators[image_url] = f"{user[3][0]}.{user[4][0]}" if user else None
                else:
                    image_annotators[image_url] = None
        
        tracker.log_substep('Project data loaded', details={'images_count': len(image_data), 'classes_count': len(class_list)})
        tracker.log_step('Annotation interface loaded successfully', details={'project_name': project_name, 'setup_type': setup_type})
        print(f"Annotation interface loaded for {project_name} ({len(image_data)} images)")
        return templates.TemplateResponse('image_annotation.html',
                            {"request": request,
                            "project_name": project_name,
                            "images": image_data,
                            "classes": class_list,
                            "setup_type": setup_type,
                            "image_annotators": image_annotators,
                            "user": current_user,
                            "current_user_avatar": current_user.avatar})
    
    except Exception as e:
        tracker.log_error(e, step='Annotation interface load')
        logger.error(f"Error in annotation route for {project_name}: {str(e)}")
        print(f"Error loading annotation for {project_name}: {str(e)}")
        raise HTTPException(status_code=500, detail="Project not found or server error")
    
@router.get('/get_annotations/{project_name}/{image_path:path}')
async def get_annotations(
    project_name: str,
    image_path: str,
    request: Request, 
    current_user: User = Depends(get_current_user_from_cookie)
):
    tracker = request.app.tracker  # Use request.app
    tracker.log_step('Fetching annotations', details={'project_name': project_name, 'image_path': image_path})
    try:
        project_path = os.path.join(PROJECTS_FOLDER, project_name)
        if not os.path.exists(project_path):
            raise ValueError('Project not found')
        
        project = Project(project_name, "", "", project_path)
        image_path = os.path.normpath(image_path)
        absolute_image_path = os.path.abspath(os.path.join(PROJECTS_FOLDER, project_name, 'images', image_path))
        logger.info(f"Looking up image with absolute path: {absolute_image_path}")
        
        with sqlite3.connect(project.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT image_id FROM Images WHERE absolute_path = ?', (absolute_image_path,))
            image_id = cursor.fetchone()
            
            if not image_id:
                cursor.execute('SELECT image_id, absolute_path FROM Images')
                all_images = cursor.fetchall()
                for row in all_images:
                    stored_path = row[1]
                    if os.path.normpath(stored_path).lower() == os.path.normpath(absolute_image_path).lower():
                        logger.info(f"Found matching image with path: {stored_path}")
                        image_id = (row[0],)
                        absolute_image_path = stored_path
                        break
            
            if not image_id:
                filename = os.path.basename(image_path)
                cursor.execute('SELECT image_id, absolute_path FROM Images WHERE absolute_path LIKE ?', (f'%{filename}',))
                image_id = cursor.fetchone()
                if image_id:
                    logger.info(f"Found image by filename match: {filename} -> {image_id[1]}")
                    absolute_image_path = image_id[1]
                    image_id = (image_id[0],)
                else:
                    available_paths = [row[1] for row in all_images]
                    logger.warning(f"No image_id found for path: {absolute_image_path} or filename: {filename} in project {project_name}. Available paths: {available_paths}")
                    raise ValueError('Image not found')
            
            image_id = image_id[0]
            
            # Check if the image is reviewed
            cursor.execute('SELECT 1 FROM ReviewedImages WHERE image_id = ?', (image_id,))
            reviewed = cursor.fetchone() is not None

        result = project.get_annotations(absolute_image_path)
        annotations = result['annotations']
        preannotations = result['preannotations']
        
        tracker.log_substep('Annotations fetched', details={'annotations_count': len(annotations), 'preannotations_count': len(preannotations), 'reviewed': reviewed})
        tracker.log_step('Annotations retrieval completed', details={'project_name': project_name, 'image': image_path})
        logger.info(f"Retrieved {len(annotations)} annotations and {len(preannotations)} preannotations for {absolute_image_path}, reviewed: {reviewed}")
        return {
            'success': True,
            'annotations': annotations,
            'preannotations': preannotations,
            'reviewed': reviewed
        }
    except Exception as e:
        tracker.log_error(e, step='Get annotations')
        logger.error(f"Error fetching annotations and preannotations: {e}")
        print(f"Error fetching annotations for {image_path} in {project_name}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post('/save_annotations')
async def save_annotations(
    request: Request,
    current_user: User = Depends(get_current_user_from_cookie)
):
    tracker = request.app.tracker  # Use request.app
    data = await request.json()
    tracker.log_step('Saving annotations', details={'project': data.get('project'), 'image': data.get('image'), 'annotations_count': len(data.get('annotations', [])) if data else 0})
    try:
        if not data or 'project' not in data or 'image' not in data or 'annotations' not in data:
            raise ValueError('Invalid request data')

        project_name = data['project']
        image_filename = data['image']  # expects just the filename, e.g., "image.jpg"
        raw_annotations = data['annotations']

        print(f"Saving annotations for image {image_filename} in project {project_name} ({len(raw_annotations)} annotations)...")

        project_path = os.path.join(PROJECTS_FOLDER, project_name)
        project = Project(project_name, "", "", project_path)
        absolute_image_path = os.path.abspath(os.path.join(PROJECTS_FOLDER, project_name, 'images', secure_filename(image_filename)))
        logger.info(f"Looking up image with absolute path: {absolute_image_path}")

        with sqlite3.connect(project.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT image_id FROM Images WHERE absolute_path = ?', (absolute_image_path,))
            image_id = cursor.fetchone()

            # Fallback 1: Case-insensitive normalized path match
            if not image_id:
                cursor.execute('SELECT image_id, absolute_path FROM Images')
                all_images = cursor.fetchall()
                for row in all_images:
                    stored_path = row[1]
                    if os.path.normpath(stored_path).lower() == os.path.normpath(absolute_image_path).lower():
                        logger.info(f"Found matching image with path: {stored_path}")
                        image_id = (row[0],)
                        absolute_image_path = stored_path
                        break

            # Fallback 2: Filename match (last resort)
            if not image_id:
                filename = os.path.basename(image_filename)
                cursor.execute('SELECT image_id, absolute_path FROM Images WHERE absolute_path LIKE ?', (f'%{filename}',))
                result = cursor.fetchone()
                if result:
                    logger.info(f"Found image by filename match: {filename} -> {result[1]}")
                    absolute_image_path = result[1]
                    image_id = (result[0],)

            # If still not found, try to add if file exists (original behavior)
            if not image_id:
                if os.path.exists(absolute_image_path):
                    project.add_image(absolute_image_path)
                    cursor.execute('SELECT image_id FROM Images WHERE absolute_path = ?', (absolute_image_path,))
                    image_id = cursor.fetchone()
                else:
                    logger.error(f"Image file {absolute_image_path} not found on disk")
                    raise ValueError(f'Image file {absolute_image_path} not found on disk')

            if not image_id:
                logger.error(f"No image entry found or created for {absolute_image_path}")
                raise ValueError('Image not found or could not be added')

            image_id = image_id[0]

            # Proceed with saving (rest of the function unchanged)
            cursor.execute('DELETE FROM Annotations WHERE image_id = ?', (image_id,))
            cursor.execute('DELETE FROM Preannotations WHERE image_id = ?', (image_id,))

            saved_count = 0
            # Progress bar for saving annotations
            with tqdm(total=len(raw_annotations), desc=f"Saving annotations for {image_filename}", unit="anno", leave=False) as save_pbar:
                for anno in raw_annotations:
                    anno_type = anno.get('type', 'rect')
                    if project.get_setup_type() == "Segmentation" and anno.get('segmentation'):
                        anno_type = 'polygon'
                    elif project.get_setup_type() == "Oriented Bounding Box":
                        anno_type = 'obbox'

                    x = y = width = height = rotation = segmentation = None
                    if project.get_setup_type() in ("Bounding Box", "Oriented Bounding Box"):
                        if anno.get('bbox'):
                            try:
                                x, y, width, height = map(float, anno['bbox'])
                                if width <= 0 or height <= 0:
                                    logger.warning(f"Invalid bbox dimensions for {anno.get('category_name')} in {absolute_image_path}: width={width}, height={height}")
                                    save_pbar.update(1)
                                    continue
                                if project.get_setup_type() == "Oriented Bounding Box":
                                    rotation = float(anno.get('rotation', 0))
                            except (ValueError, TypeError) as e:
                                logger.warning(f"Invalid bbox format for {anno.get('category_name')} in {absolute_image_path}: {anno.get('bbox')}, error: {e}")
                                save_pbar.update(1)
                                continue
                        else:
                            logger.warning(f"No bbox provided for {anno.get('category_name')} in {absolute_image_path}: {anno}")
                            save_pbar.update(1)
                            continue
                    elif project.get_setup_type() == "Segmentation" and anno.get('segmentation'):
                        seg = anno['segmentation']
                        if isinstance(seg, list) and seg:
                            seg = seg[0] if isinstance(seg[0], list) else seg
                            segmentation = json.dumps(seg)
                        else:
                            logger.warning(f"Skipping invalid segmentation for {anno.get('category_name')} in {absolute_image_path}")
                            save_pbar.update(1)
                            continue

                    if (project.get_setup_type() in ("Bounding Box", "Oriented Bounding Box") and (x is None or y is None or width is None or height is None)) or \
                       (project.get_setup_type() == "Segmentation" and segmentation is None):
                        logger.warning(f"Skipping invalid annotation for {anno.get('category_name')} in {absolute_image_path}: {anno}")
                        save_pbar.update(1)
                        continue

                    cursor.execute('''
                        INSERT INTO Annotations (image_id, type, class_name, x, y, width, height, rotation, segmentation)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        image_id,
                        anno_type,
                        anno.get('category_name') or anno.get('label'),
                        x,
                        y,
                        width,
                        height,
                        rotation,
                        segmentation
                    ))
                    saved_count += 1
                    save_pbar.update(1)

            # Mark the image as reviewed
            cursor.execute('''
                INSERT OR REPLACE INTO ReviewedImages (image_id) VALUES (?)
            ''', (image_id,))

            conn.commit()
            logger.info(f"Saved {saved_count} annotations for {absolute_image_path} and marked as reviewed")

        tracker.log_substep('Annotations saved', details={'saved_count': saved_count, 'image': image_filename, 'total_attempted': len(raw_annotations)})
        tracker.log_step('Annotations save completed', details={'project': project_name, 'user_id': current_user.id})
        print(f"Saved {saved_count}/{len(raw_annotations)} annotations for {image_filename} in {project_name}")
        return {'success': True}

    except Exception as e:
        tracker.log_error(e, step='Save annotations')
        logger.error(f"Error saving annotations: {str(e)}")
        print(f"Error saving annotations for {image_filename} in {project_name}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post('/delete_images')
async def delete_images(
    request: Request,
    current_user: User = Depends(get_current_user_from_cookie)
):
    tracker = request.app.tracker  # Use request.app
    data = await request.json()
    tracker.log_step('Deleting images', details={'project': data.get('project'), 'image_count': len(data.get('images', []))})
    try:
        project_name = data.get('project')
        image_urls = data.get('images', [])  # List of filenames/URLs

        if not project_name or not image_urls:
            raise ValueError('Project name and image list are required')

        print(f"Deleting {len(image_urls)} images from project {project_name}...")

        proj = VFProjects.get_project(project_name)
        if not proj:
            raise ValueError('Project not found')

        deleted_count = 0
        # Progress bar for deletion
        with tqdm(total=len(image_urls), desc=f"Deleting images from {project_name}", unit="img", leave=False) as del_pbar:
            for image_url in image_urls:
                image_name = os.path.basename(image_url)  # Extract filename
                remover = VFImageRemover(proj, image_name=image_name)
                if remover.remove():
                    deleted_count += 1
                del_pbar.update(1)

        tracker.log_substep('Images deleted', details={'deleted_count': deleted_count, 'total_attempted': len(image_urls)})
        tracker.log_step('Image deletion completed', details={'project': project_name})
        logger.info(f"Deleted {deleted_count} images from {project_name}")
        print(f"Deleted {deleted_count}/{len(image_urls)} images from {project_name}")
        return {'success': True, 'deleted': deleted_count}
    except Exception as e:
        tracker.log_error(e, step='Delete images')
        logger.error(f"Error deleting images: {e}")
        print(f"Error deleting images from {project_name}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post('/download_images')
async def download_images(
    request: Request,
    current_user: User = Depends(get_current_user_from_cookie)
):
    tracker = request.app.tracker  # Use request.app
    data = await request.json()
    tracker.log_step('Downloading images', details={'project': data.get('project'), 'image_count': len(data.get('images', []))})
    try:
        project_name = data.get('project')
        filenames = data.get('images', [])  # List of filenames
        save_path = data.get('save_path')  # For web: if provided, save locally; else stream

        if not project_name:
            raise ValueError('Project name required')

        proj = VFProjects.get_project(project_name)
        if not proj:
            raise ValueError('Project not found')

        print(f"Downloading {len(filenames or [])} images from {project_name}...")

        downloader = VFImageDownloader(proj, save_path or TMP_FOLDER, selected_images=filenames if filenames else None)
        zip_path = downloader.download()
        tracker.log_substep('Images downloaded', details={'zip_path': zip_path, 'image_count': len(filenames or [])})
        tracker.log_step('Image download completed', details={'project': project_name})
        print(f"Images downloaded to {zip_path}")
        if save_path:
            return {'success': True, 'saved_file': zip_path}
        else:
            # Stream for download
            return FileResponse(
                zip_path,
                media_type='application/zip',
                filename=f'{project_name}_images.zip'
            )
    except Exception as e:
        tracker.log_error(e, step='Download images')
        logger.error(f"Download failed: {e}")
        print(f"Download failed for {project_name}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/export/{project_name}")
async def export_annotations(
    project_name: str,
    request: Request,
    current_user: User = Depends(get_current_user_from_cookie)
):
    print(f"Endpoint hit for project: {project_name}", flush=True)
    tracker_app = request.app.tracker
    
    # Log raw body to see EXACT payload
    body = await request.body()
    print(f"Raw request body: {body.decode('utf-8')}", flush=True)
    
    data = await request.json()
    print(f"Received export data: {data}", flush=True)
    print(f"local_export from data: {data.get('local_export')} (type: {type(data.get('local_export'))})", flush=True)
    
    format = data.get('format')
    images_list = data.get('images', [])  # For image projects
    videos = data.get('videos') or []
    split_choices = data.get('split_choices', ['train'])
    split_ratios = data.get('split_ratios', {'train': 100})
    extract_frames = data.get('extract_frames', False)
    semantic = data.get('semantic', False)
    user_export_path = data.get('export_path') or data.get('save_path')
    local_export = data.get('local_export', False) or bool(user_export_path)
    print(f"local_export after get: {local_export} (type: {type(local_export)})", flush=True)
    print(f"user_export_path: {user_export_path}", flush=True)
    
    try:
        proj = VFProjects.get_project(project_name)
        if not proj:
            raise HTTPException(status_code=404, detail="Project not found")
        print(f"Project loaded: {proj.name}", flush=True)
        
        is_video_project = proj.get_setup_type().startswith('Video ')
        print(f"Is video project: {is_video_project}", flush=True)
        
        # For image projects: handle selected_images
        selected_images = None
        if not is_video_project:
            selected_images = images_list if images_list else None
            print(f"Incoming images: {images_list} -> selected_images: {selected_images}", flush=True)
        
        # Video handling only for video projects
        if is_video_project:
            # Fetch all videos for mapping/fallback
            all_videos = proj.get_videos()
            internal_ids = [v[0] for v in all_videos]
            internal_paths = [v[1] for v in all_videos]
            print(f"All videos from project: {all_videos}", flush=True)
            print(f"Internal IDs: {internal_ids}", flush=True)
            print(f"Internal paths: {internal_paths}", flush=True)
            
            if not videos:
                videos = internal_paths
                print(f"Fetched all videos (paths): {len(videos)}", flush=True)
            else:
                print(f"Incoming videos: {videos}", flush=True)
                # Map incoming videos (IDs or paths) to internal paths
                mapped_videos = []
                for vid in videos:
                    if not vid: 
                        continue
                    try:
                        vid_int = int(vid)  # Handle string '1' -> int 1
                        if vid_int in internal_ids:
                            idx = internal_ids.index(vid_int)
                            mapped_path = internal_paths[idx]
                            mapped_videos.append(mapped_path)
                            print(f"Mapped ID '{vid}' to path '{mapped_path}'", flush=True)
                        elif vid in internal_paths:
                            # Already a path: keep it
                            mapped_videos.append(vid)
                            print(f"Direct path match: '{vid}'", flush=True)
                        else:
                            print(f"Warning: No match for '{vid}' (not ID or path)", flush=True)
                    except ValueError:
                        # Not an int: treat as potential path
                        if vid in internal_paths:
                            mapped_videos.append(vid)
                        else:
                            print(f"Warning: Invalid non-numeric '{vid}'", flush=True)
                
                videos = mapped_videos
                print(f"Final videos for exporter: {videos}", flush=True)
            
            if not videos:
                raise ValueError("No valid videos found or matched in project")
        
        # For image projects: treat empty selected_images as all annotated
        if not is_video_project and selected_images is not None and not selected_images:
            selected_images = None
        
        # Determine exporter path based on mode
        exporter_path = user_export_path if local_export else TMP_FOLDER
        print(f"exporter_path: {exporter_path}", flush=True)
        
        exporter = VFExporter(
            project=proj,
            path=exporter_path, 
            format=format,
            selected_images=selected_images,
            split_choices=split_choices,
            split_ratios=split_ratios,
            videos=videos,
            extract_frames=extract_frames,
            semantic=semantic
        )
        print(f"VFExporter created with path: {exporter_path}", flush=True)
        
        zip_path = exporter.export()
        print(f"Export completed: {zip_path}", flush=True)
        
        if local_export:
            print(f"Local export branch hit: Returning JSON with path {zip_path}", flush=True)
            # Validate path was used (fixed for trailing /)
            clean_user_path = user_export_path.rstrip('/') if user_export_path else ''
            common_prefix = os.path.commonprefix([str(zip_path), clean_user_path])
            print(f"Path validation: zip_path={zip_path}, user_path={clean_user_path}, common_prefix={common_prefix}", flush=True)
            if common_prefix != clean_user_path:
                raise ValueError(f"Export saved to unexpected path: {zip_path} (expected prefix: {clean_user_path})")
            return JSONResponse({"success": True, "saved_path": zip_path})
        else:
            print("Non-local export: Returning FileResponse", flush=True)
            filename = os.path.basename(zip_path)
            return FileResponse(
                path=zip_path,
                media_type='application/zip',
                filename=filename,
                headers={"Content-Disposition": f"attachment; filename={filename}"}
            )
    except ValueError as ve:
        tracker_app.log_error(ve, step='Export annotations')
        print(f"Export validation failed for {project_name}: {ve}", flush=True)
        logger.error(f"Export validation failed for {project_name}: {ve}")
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        tracker_app.log_error(e, step='Export annotations')
        print(f"Export failed for {project_name}: {e}", flush=True)
        logger.error(f"Export failed for {project_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
                        
@router.post('/delete_preannotations/{project_name}')
async def delete_preannotations(
    project_name: str,
    request: Request,
    current_user: User = Depends(get_current_user_from_cookie)
):
    """Web endpoint for deleting preannotations (e.g., per image)."""
    tracker = request.app.tracker  # Use request.app
    data = await request.json()
    tracker.log_step('Deleting preannotations', details={'project_name': project_name, 'image_path': data.get('image_path')})
    try:
        image_path = data.get('image_path')
        proj = VFProjects.get_project(project_name)
        if not proj:
            raise ValueError('Project not found')
        print(f"Deleting preannotations from {project_name} {'(image: ' + image_path + ')' if image_path else 'all'}...")
        deleted = proj.delete_preannotations(image_path)
        tracker.log_substep('Preannotations deleted', details={'deleted_count': deleted})
        tracker.log_step('Preannotations deletion completed')
        print(f"Deleted {deleted} preannotations from {project_name}")
        return {'success': True, 'deleted': deleted}
    except Exception as e:
        tracker.log_error(e, step='Delete preannotations')
        logger.error(f"Error deleting preannotations: {e}")
        print(f"Error deleting preannotations from {project_name}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post('/delete_annotations/{project_name}')
async def delete_annotations(
    project_name: str,
    request: Request,
    current_user: User = Depends(get_current_user_from_cookie)
):
    """Web endpoint for deleting annotations (e.g., per image/user)."""
    tracker = request.app.tracker  # Use request.app
    data = await request.json()
    tracker.log_step('Deleting annotations', details={'project_name': project_name, 'image_path': data.get('image_path')})
    try:
        image_path = data.get('image_path')
        user_id = data.get('user_id', current_user.id)
        proj = VFProjects.get_project(project_name)
        if not proj:
            raise ValueError('Project not found')
        print(f"Deleting annotations from {project_name} {'(image: ' + image_path + ')' if image_path else 'all'}...")
        deleted = proj.delete_annotations(image_path, user_id)
        tracker.log_substep('Annotations deleted', details={'deleted': deleted})
        tracker.log_step('Annotations deletion completed')
        print(f"Deleted annotations from {project_name}: {deleted}")
        return {'success': True, 'deleted': deleted}
    except Exception as e:
        tracker.log_error(e, step='Delete annotations')
        logger.error(f"Error deleting annotations: {e}")
        print(f"Error deleting annotations from {project_name}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    
@router.get('/get_frames/{project_name}/{video_id}')
async def get_frames(
    project_name: str,
    video_id: int,
    request: Request,
    current_user: User = Depends(get_current_user_from_cookie)
):
    tracker = request.app.tracker
    tracker.log_step('Fetching frames', details={'project_name': project_name, 'video_id': video_id})
    try:
        project_path = os.path.join(PROJECTS_FOLDER, project_name)
        if not os.path.exists(project_path):
            raise HTTPException(status_code=404, detail='Project not found')

        project = Project(project_name, "", "", project_path)
        raw_frames = project.get_frames_for_video(video_id)
        
        # Fetch FPS from Videos table for timestamp calculation
        with sqlite3.connect(project.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT fps FROM Videos WHERE video_id = ?', (video_id,))
            fps_result = cursor.fetchone()
            fps = fps_result[0] if fps_result else 30.0  # Fallback to 30 FPS if not found
        
        # Build response: frame_number, subsampled, and derived timestamp
        frames = [
            {
                'frame_number': f[1],
                'subsampled': bool(f[2]),
                'timestamp': f[1] / fps
            }
            for f in raw_frames
        ]

        tracker.log_substep('Frames fetched', details={'frames_count': len(frames)})
        tracker.log_step('Frames retrieval completed', details={'project_name': project_name, 'video_id': video_id})
        logger.info(f"Retrieved {len(frames)} frames for video {video_id} in {project_name}")
        return {'frames': frames, 'fps': fps}
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        tracker.log_error(e, step='Get frames')
        logger.error(f"Error fetching frames: {e}")
        print(f"Error fetching frames for video {video_id} in {project_name}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

def _bbox_from_points(points):
    """
    Accepts either:
      - flat list [x0,y0,x1,y1,...] OR
      - list of pairs [[x,y], [x,y], ...]
    Returns bbox [x,y,w,h] with ints, or None if invalid.
    """
    if not points:
        return None
    # detect flat list
    if isinstance(points[0], (int, float)):
        xs = points[0::2]
        ys = points[1::2]
    else:
        # list of [x,y]
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
    if not xs or not ys:
        return None
    x_min = int(min(xs))
    y_min = int(min(ys))
    x_max = int(max(xs))
    y_max = int(max(ys))
    w = max(1, int(x_max - x_min))
    h = max(1, int(y_max - y_min))
    return [x_min, y_min, w, h]


def _expand_bbox_xywh(bbox, pad_px=0, img_w=None, img_h=None):
    """
    bbox: [x,y,w,h]
    pad_px: pixels to expand on each side (int, >=0)
    img_w/img_h: optional to clip
    returns expanded bbox [x,y,w,h]
    """
    x, y, w, h = map(int, bbox)
    x1 = x - pad_px
    y1 = y - pad_px
    x2 = x + w + pad_px
    y2 = y + h + pad_px
    if img_w is not None:
        x1 = max(0, x1)
        x2 = min(img_w - 1, x2)
    if img_h is not None:
        y1 = max(0, y1)
        y2 = min(img_h - 1, y2)
    w2 = max(1, x2 - x1)
    h2 = max(1, y2 - y1)
    return [float(x1), float(y1), float(w2), float(h2)]


tracking_status = {}
tracking_progress = {}
tracking_results = {} 

@router.post('/track_objects/{project_name}/{video_id}')
async def track_objects(
    project_name: str,
    video_id: int,
    request: Request,
    current_user: User = Depends(get_current_user_from_cookie)
):
    tracker_app = request.app.tracker
    data = await request.json()
    print("Received data:", data)
    print("Initial annotations (raw):", data.get('initial_annotations', []))
    tracker_app.log_step('Starting object tracking', details={
        'project_name': project_name, 'video_id': video_id,
        'start_frame': data.get('start_frame'), 'end_frame': data.get('end_frame'),
        'initial_annotations': len(data.get('initial_annotations', []))
    })
    try:
        method = data.get('method', 'cv2')

        # parse frame numbers safely
        try:
            start_frame = int(data.get('start_frame', 0) or 0)
        except Exception:
            start_frame = 0
        try:
            end_frame_raw = data.get('end_frame', None)
            end_frame = int(end_frame_raw) if end_frame_raw is not None else None
        except Exception:
            end_frame = None

        # Read incoming annotations BEFORE using them (this was the bug)
        initial_annotations = data.get('initial_annotations', []) or []

        # optional padding from frontend
        bbox_padding_px = int(data.get('bbox_padding_px', 0) or 0)

        # sanitize annotations -> bbox-only (xywh)
        sanitized_annotations = []
        for i, anno in enumerate(initial_annotations):
            # If it's already a bbox (xywh), keep it
            if 'bbox' in anno and isinstance(anno['bbox'], (list, tuple)) and len(anno['bbox']) == 4:
                bbox = anno['bbox']
            else:
                # try segmentation -> bbox
                if 'segmentation' in anno and anno['segmentation']:
                    bbox = _bbox_from_points(anno['segmentation'])
                # try points (list of [x,y]) -> bbox
                elif 'points' in anno and anno['points']:
                    bbox = _bbox_from_points(anno['points'])
                else:
                    bbox = None

            if bbox is None:
                print(f"Skipping invalid annotation {i}: {anno}")
                continue

            # optionally expand
            if bbox_padding_px > 0:
                # Note: img_w/h could be fetched from DB if needed, but assuming not clipped here
                bbox = _expand_bbox_xywh(bbox, pad_px=bbox_padding_px)

            # construct minimal annotation for the tracker (bbox, label, keyframe_frame)
            sanitized = {
                'bbox': bbox,
                'label': anno.get('label', 'object'),
            }
            if 'keyframe_frame' in anno and anno['keyframe_frame'] is not None:
                try:
                    sanitized['keyframe_frame'] = int(anno['keyframe_frame'])
                except Exception:
                    sanitized['keyframe_frame'] = start_frame
            sanitized_annotations.append(sanitized)

        if len(sanitized_annotations) == 0:
            raise ValueError('No valid initial annotations after sanitization')

        # replace initial_annotations with sanitized list for tracking
        initial_annotations = sanitized_annotations

        tracker_type = data.get('tracker_type', 'csrt') if method == 'cv2' else None
        use_keyframes = data.get('use_keyframes', False) if method == 'cv2' else True  # Default true for others
        output_type = data.get('output_type', 'bbox') if method == 'sam2' else None
        device = data.get('device', 'cpu') if method == 'sam2' else 'cpu'
        sam_model = data.get('sam_model', 'sam2.1_t.pt') if method == 'sam2' else 'sam2.1_b.pt'

        if end_frame is None or len(initial_annotations) == 0:
            raise ValueError('End frame and at least one initial annotation required')

        proj = VFProjects.get_project(project_name)
        if not proj:
            raise ValueError('Project not found')

        # Get video path from DB (assume method added to Project)
        video_path = proj.get_video_path(video_id)

        key = f"{project_name}_{video_id}_{start_frame}_{end_frame}_{method}"
        if tracking_status.get(key) == 'running':
            raise RuntimeError('Tracking is already running for this range')

        print(f"VisioFirm is tracking objects in video {video_id} (project '{project_name}') from frame {start_frame} to {end_frame} using {method}...")

        tracker = VFTracker(
            project=proj,
            video_path=video_path,
            start_frame=start_frame,  # NEW: frame number
            end_frame=end_frame,
            initial_annotations=initial_annotations,
            method=method,
            tracker_type=tracker_type,
            use_keyframes=use_keyframes,
            output_type=output_type,
            sam_model=sam_model,
            device=device
        )

        tracking_status[key] = 'running'
        tracking_progress[key] = 0

        def callback(status_dict):
            tracking_status[key] = status_dict['status']
            progress = status_dict.get('progress', 0)
            tracking_progress[key] = progress
            if status_dict['status'] == 'completed':
                tracker.push_to_db()
                tracking_results[key] = status_dict['results']
            tracker_app.log_substep('Tracking progress update', details=status_dict)

        tracker.run_threaded(callback=callback)
        tracker_app.log_step('Tracking started successfully', details={'key': key, 'method': method})
        return {'success': True, 'message': 'Tracking started', 'key': key}

    except Exception as e:
        tracker_app.log_error(e, step='Object tracking')
        logger.error(f"Error in track_objects: {e}")
        print(f"Tracking failed for '{project_name}' video {video_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    
@router.get("/check_tracking_status")
def check_tracking_status(key: str):
    status = tracking_status.get(key, 'not_started')
    progress = tracking_progress.get(key, 0)
    results = tracking_results.get(key) if status == 'completed' else None
    return {'status': status, 'progress': progress, 'results': results}

@router.get("/get_video_annotations/{project_name}/{video_id}")
def get_video_annotations(project_name: str, video_id: int):
    proj = VFProjects.get_project(project_name)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    return proj.get_video_annotations(video_id)

@router.post('/delete_segment_annotations/{project_name}/{video_id}')
async def delete_segment_annotations(
    project_name: str,
    video_id: int,
    request: Request,
    current_user: User = Depends(get_current_user_from_cookie)
):
    tracker = request.app.tracker
    tracker.log_step('Deleting segment annotations', details={'project_name': project_name, 'video_id': video_id})
    try:
        data = await request.json()
        start_frame = data.get('start_frame')
        end_frame = data.get('end_frame')
        if start_frame is None or end_frame is None:
            raise HTTPException(status_code=400, detail='start_frame and end_frame are required')

        proj = VFProjects.get_project(project_name)
        if not proj:
            raise HTTPException(status_code=404, detail="Project not found")

        result = proj.delete_annotations(video_id=video_id, start_frame=start_frame, end_frame=end_frame)
        tracker.log_substep('Segment annotations deleted', details=result)
        tracker.log_step('Segment annotations deletion completed', details={'project_name': project_name, 'video_id': video_id})
        logger.info(f"Deleted segment annotations for video {video_id} in {project_name}: frames {start_frame}-{end_frame}")
        return {'success': True, 'deleted': result}
    except HTTPException:
        raise
    except Exception as e:
        tracker.log_error(e, step='Delete segment annotations')
        logger.error(f"Error deleting segment annotations: {e}")
        print(f"Error deleting segment annotations for video {video_id} in {project_name}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post('/delete_segment_preannotations/{project_name}/{video_id}')
async def delete_segment_preannotations(
    project_name: str,
    video_id: int,
    request: Request,
    current_user: User = Depends(get_current_user_from_cookie)
):
    tracker = request.app.tracker
    tracker.log_step('Deleting segment preannotations', details={'project_name': project_name, 'video_id': video_id})
    try:
        data = await request.json()
        start_frame = data.get('start_frame')
        end_frame = data.get('end_frame')
        if start_frame is None or end_frame is None:
            raise HTTPException(status_code=400, detail='start_frame and end_frame are required')

        proj = VFProjects.get_project(project_name)
        if not proj:
            raise HTTPException(status_code=404, detail="Project not found")

        deleted = proj.delete_preannotations(video_id=video_id, start_frame=start_frame, end_frame=end_frame)
        tracker.log_substep('Segment preannotations deleted', details={'deleted': deleted})
        tracker.log_step('Segment preannotations deletion completed', details={'project_name': project_name, 'video_id': video_id})
        logger.info(f"Deleted {deleted} segment preannotations for video {video_id} in {project_name}: frames {start_frame}-{end_frame}")
        return {'success': True, 'deleted': deleted}
    except HTTPException:
        raise
    except Exception as e:
        tracker.log_error(e, step='Delete segment preannotations')
        logger.error(f"Error deleting segment preannotations: {e}")
        print(f"Error deleting segment preannotations for video {video_id} in {project_name}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    
@router.post('/commit_video_preannotations/{project_name}/{video_id}')
async def commit_video_preannotations(
    project_name: str,
    video_id: int,
    request: Request,
    current_user: User = Depends(get_current_user_from_cookie)
):
    tracker = request.app.tracker
    tracker.log_step('Committing video preannotations', details={'project_name': project_name, 'video_id': video_id})
    try:
        proj = VFProjects.get_project(project_name)
        if not proj:
            raise ValueError('Project not found')
        result = proj.commit_preannotations_for_video(video_id, current_user.id)
        if result['success']:
            tracker.log_substep('Preannotations committed', details=result)
            tracker.log_step('Video preannotations commit completed')
            print(f"Committed preannotations for video {video_id} in {project_name}")
            return result
        else:
            raise ValueError(result['error'])
    except Exception as e:
        tracker.log_error(e, step='Commit video preannotations')
        logger.error(f"Error committing video preannotations: {e}")
        print(f"Error committing preannotations for video {video_id} in {project_name}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
