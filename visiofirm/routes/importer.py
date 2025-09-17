# visiofirm/routes/importer.py
from fastapi import APIRouter, Request, Depends, Form, HTTPException, status, UploadFile, File
from fastapi.responses import JSONResponse
from visiofirm.security import get_current_user_from_cookie, User
from werkzeug.utils import secure_filename 
import os
import shutil
from filelock import FileLock
import time
import psutil
import errno
from visiofirm.models import Project
from visiofirm.config import PROJECTS_FOLDER, VALID_IMAGE_EXTENSIONS, VALID_VIDEO_EXTENSIONS, VALID_SETUP_TYPES, get_cache_folder
# Direct imports to break circular dependency
from visiofirm.projects import VFProjects, extract_archive, generate_unique_project_name, ensure_unique_project_name
from visiofirm.utils import CocoAnnotationParser, YoloAnnotationParser, NameMatcher, is_valid_image
import logging
import hashlib
from shutil import copyfileobj
from typing import Optional

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()

async def get_current_user_optional(request: Request) -> Optional[User]:
    try:
        return await get_current_user_from_cookie(request)
    except HTTPException:
        return None

def _process_temp_upload_dir(images_path, temp_upload_dir, videos_path: Optional[str] = None, setup_type: Optional[str] = None):
    """Process files in temp_upload_dir: move valid images to images_path, flatten annotations to temp_upload_dir, handle archives by extracting and processing."""
    all_files = os.listdir(temp_upload_dir)
    image_paths = []
    annotation_extensions = {'.json', '.yaml', '.txt'}

    print(f"Processing {len(all_files)} files...")
    for filename in all_files:
        file_path = os.path.join(temp_upload_dir, filename)
        ext = os.path.splitext(filename)[1].lower()
        if setup_type:
            if "Video" in setup_type:
                if ext in VALID_IMAGE_EXTENSIONS or ext in annotation_extensions:
                    logger.info(f"Skipping non-video file for video setup: {filename}")
                    os.remove(file_path)
                    continue
            else:
                if ext in VALID_VIDEO_EXTENSIONS:
                    logger.info(f"Skipping video file for non-video setup: {filename}")
                    os.remove(file_path)
                    continue
        if ext in VALID_IMAGE_EXTENSIONS:
            if is_valid_image(file_path):
                final_path = os.path.join(images_path, secure_filename(filename))
                if not os.path.exists(final_path):
                    lock_path = final_path + '.lock'
                    with FileLock(lock_path):
                        shutil.move(file_path, final_path)
                    image_paths.append(os.path.abspath(final_path))
                    logger.info(f"Moved image {filename} to {final_path}")
                else:
                    logger.info(f"Image {filename} already exists, skipping")
            else:
                logger.warning(f"Skipping corrupted image: {filename}")
        elif ext in annotation_extensions:
            logger.info(f"Keeping annotation {filename} in {temp_upload_dir}")
        elif ext in {'.zip', '.tar', '.tar.gz', '.rar'}:
            extract_path = os.path.join(temp_upload_dir, f'extracted_{filename}')
            os.makedirs(extract_path, exist_ok=True)
            try:
                extract_archive(file_path, extract_path)
                extracted_files = []
                for root, _, filenames in os.walk(extract_path):
                    extracted_files.extend(filenames)
                processed_extracted = 0
                for root, _, filenames in os.walk(extract_path):
                    for fname in filenames:
                        src_path = os.path.join(root, fname)
                        file_ext = os.path.splitext(fname)[1].lower()
                        if setup_type:
                            if "Video" in setup_type:
                                if file_ext in VALID_IMAGE_EXTENSIONS or file_ext in annotation_extensions:
                                    logger.info(f"Skipping non-video extracted file: {fname}")
                                    os.remove(src_path)
                                    continue
                                elif file_ext in VALID_VIDEO_EXTENSIONS:
                                    final_path = os.path.join(videos_path, secure_filename(fname))
                                    if not os.path.exists(final_path):
                                        lock_path = final_path + '.lock'
                                        with FileLock(lock_path):
                                            shutil.move(src_path, final_path)
                                        logger.info(f"Moved video {fname} from archive to {final_path}")
                                    else:
                                        logger.info(f"Video {fname} already exists, skipping")
                            else:
                                if file_ext in VALID_VIDEO_EXTENSIONS:
                                    logger.info(f"Skipping video extracted file: {fname}")
                                    os.remove(src_path)
                                    continue
                                elif file_ext in VALID_IMAGE_EXTENSIONS:
                                    if is_valid_image(src_path):
                                        final_path = os.path.join(images_path, secure_filename(fname))
                                        if not os.path.exists(final_path):
                                            lock_path = final_path + '.lock'
                                            with FileLock(lock_path):
                                                shutil.move(src_path, final_path)
                                            image_paths.append(os.path.abspath(final_path))
                                            logger.info(f"Moved image {fname} from archive to {final_path}")
                                        else:
                                            logger.info(f"Image {fname} already exists, skipping")
                                    else:
                                        logger.warning(f"Skipping corrupted image from archive: {fname}")
                                elif file_ext in annotation_extensions:
                                    dest_path = os.path.join(temp_upload_dir, secure_filename(fname))
                                    lock_path = dest_path + '.lock'
                                    with FileLock(lock_path):
                                        shutil.move(src_path, dest_path)
                                    logger.info(f"Flattened annotation {fname} to {temp_upload_dir}")
                        else:
                            # No setup_type: original behavior
                            if file_ext in VALID_IMAGE_EXTENSIONS:
                                if is_valid_image(src_path):
                                    final_path = os.path.join(images_path, secure_filename(fname))
                                    if not os.path.exists(final_path):
                                        lock_path = final_path + '.lock'
                                        with FileLock(lock_path):
                                            shutil.move(src_path, final_path)
                                        image_paths.append(os.path.abspath(final_path))
                                        logger.info(f"Moved image {fname} from archive to {final_path}")
                                    else:
                                        logger.info(f"Image {fname} already exists, skipping")
                                else:
                                    logger.warning(f"Skipping corrupted image from archive: {fname}")
                            elif file_ext in annotation_extensions:
                                dest_path = os.path.join(temp_upload_dir, secure_filename(fname))
                                lock_path = dest_path + '.lock'
                                with FileLock(lock_path):
                                    shutil.move(src_path, dest_path)
                                logger.info(f"Flattened annotation {fname} to {temp_upload_dir}")
                        processed_extracted += 1
                print(f"Processed {processed_extracted} files from archive {filename}")
                logger.info(f"Processed {processed_extracted} files from archive {filename}")
            except Exception as e:
                logger.error(f"Error extracting archive {filename}: {e}")
                print(f"Error extracting archive {filename}: {str(e)}")
            finally:
                os.remove(file_path)
                shutil.rmtree(extract_path, ignore_errors=True)
        elif ext in VALID_VIDEO_EXTENSIONS and videos_path:
            final_path = os.path.join(videos_path, secure_filename(filename))
            if not os.path.exists(final_path):
                lock_path = final_path + '.lock'
                with FileLock(lock_path):
                    shutil.move(file_path, final_path)
                logger.info(f"Moved video {filename} to {final_path}")
            else:
                logger.info(f"Video {filename} already exists, skipping")

    # Flatten annotations from subdirs (if any left after extraction)
    for root, _, filenames in os.walk(temp_upload_dir):
        for fname in filenames:
            if os.path.splitext(fname)[1].lower() in annotation_extensions:
                src_path = os.path.join(root, fname)
                dest_path = os.path.join(temp_upload_dir, secure_filename(fname))
                if src_path != dest_path:
                    lock_path = dest_path + '.lock'
                    with FileLock(lock_path):
                        shutil.move(src_path, dest_path)
                    logger.info(f"Flattened annotation {fname} to {temp_upload_dir}")

    return image_paths

@router.post("/create_project")
async def create_project(
    request: Request,
    current_user: User = Depends(get_current_user_from_cookie)
):
    tracker = request.app.tracker  # Use request.app
    form = await request.form()
    tracker.log_step('Creating project', details={'upload_id': form.get('upload_id')}) 
    try:
        project_name = form.get('project_name', '').strip()
        description = form.get('description', '')
        setup_type = form.get('setup_type', '').strip()
        class_names = form.get('class_names', '')
        upload_id = form.get('upload_id')

        if not setup_type or not upload_id:
            raise ValueError('Setup type and upload ID are required')
        if setup_type not in VALID_SETUP_TYPES:
            raise ValueError('Invalid setup type')

        class_list = [cls.strip() for cls in class_names.replace(';', ',').replace('.', ',').split(',') if cls.strip()]

        if not project_name:
            project_name = generate_unique_project_name()
        else:
            project_name = ensure_unique_project_name(project_name)

        print(f"Starting project: {project_name}")

        project_path = os.path.join(PROJECTS_FOLDER, secure_filename(project_name))
        images_path = os.path.join(project_path, 'images')
        os.makedirs(images_path, exist_ok=True)

        videos_path = None
        target_fps = int(form.get('target_fps', 5))  # Get from form, default 5
        if "Video" in setup_type:
            videos_path = os.path.join(project_path, 'videos')
            os.makedirs(videos_path, exist_ok=True)

        project = Project(project_name, description, setup_type, project_path)
        project.add_classes(class_list)

        cache_dir = get_cache_folder()
        temp_base = os.path.join(cache_dir, 'temp_chunks')
        os.makedirs(temp_base, exist_ok=True)
        temp_upload_dir = os.path.join(temp_base, upload_id)
        if not os.path.exists(temp_upload_dir):
            raise ValueError('No files found for upload ID')

        initial_files = os.listdir(temp_upload_dir)
        if not initial_files:
            raise ValueError('No files uploaded')

        initial_video_count = 0
        if videos_path and os.path.exists(videos_path):
            initial_video_count = len([f for f in os.listdir(videos_path) if os.path.splitext(f)[1].lower() in VALID_VIDEO_EXTENSIONS])

        image_paths = _process_temp_upload_dir(images_path, temp_upload_dir, videos_path=videos_path, setup_type=setup_type)

        annotation_files = [f for f in os.listdir(temp_upload_dir) if f.lower().endswith(('.json', '.yaml', '.txt'))]

        final_video_count = len([f for f in os.listdir(videos_path) if os.path.splitext(f)[1].lower() in VALID_VIDEO_EXTENSIONS]) if videos_path else 0
        new_videos = final_video_count - initial_video_count

        new_content = len(image_paths) + len(annotation_files) + new_videos
        if new_content == 0:
            raise ValueError('No valid files found')

        print(f"Total Image count: {len(image_paths)}")

        tracker.log_substep('Uploaded data processed', details={'image_count': len(image_paths), 'annotation_files_count': len(annotation_files)})

        project.add_images(image_paths)

        if "Video" in setup_type:
            video_paths = [os.path.join(videos_path, f) for f in os.listdir(videos_path) if os.path.splitext(f)[1].lower() in VALID_VIDEO_EXTENSIONS]
            selected_total = 0
            for v_path in video_paths:
                video_id = project.add_video(v_path)
                if video_id:
                    selected = project.add_selected_frames(video_id, target_fps=target_fps)
                    selected_total += selected
            tracker.log_substep('Videos processed', details={'video_count': len(video_paths), 'selected_frames': selected_total})
            print(f"Processed {len(video_paths)} videos, selected {selected_total} frame indices at {target_fps} FPS.")

        project.parse_and_add_annotations(temp_upload_dir, image_paths)
        shutil.rmtree(temp_upload_dir, ignore_errors=True)

        tracker.log_substep('Project setup completed', details={'total_images': len(image_paths), 'classes_added': len(class_list), 'setup_type': setup_type})

        tracker.log_step('Project creation completed successfully', details={'project_name': project_name, 'total_images': len(image_paths), 'annotation_files_processed': len(annotation_files)})

        print(f"Project {project_name} created successfully with {len(image_paths)} images")
        return {"success": True, "project_name": project_name}
    except Exception as e:
        tracker.log_error(e, step='Project creation') 
        logger.error(f"Error in create_project: {e}")
        print(f"Error creating project: {str(e)}")
        return JSONResponse(status_code=500, content={'error': f'Server error: {str(e)}'})

@router.get("/get_unique_project_name")
async def get_unique_project_name(request: Request, current_user: User = Depends(get_current_user_from_cookie)):  # Add request
    try:
        project_name = generate_unique_project_name()
        return {"success": True, "project_name": project_name}
    except Exception as e:
        logger.error(f"Error in get_unique_project_name: {e}")
        print(f"Error generating project name: {str(e)}")
        raise HTTPException(status_code=500, detail=f'Server error: {str(e)}')

@router.post("/import_images")
async def import_images(
    request: Request,
    project_name: str = Form(...),
    upload_id: str = Form(...),
    current_user: User = Depends(get_current_user_from_cookie)
):
    tracker = request.app.tracker
    tracker.log_step('Importing images', details={'project_name': project_name, 'upload_id': upload_id})
    try:
        project_path = os.path.join(PROJECTS_FOLDER, secure_filename(project_name))
        if not os.path.exists(project_path):
            raise ValueError('Project not found')
        
        images_path = os.path.join(project_path, 'images')
        os.makedirs(images_path, exist_ok=True)
        
        cache_dir = get_cache_folder()
        temp_upload_dir = os.path.join(cache_dir, 'temp_chunks', upload_id)
        
        # Get setup_type from existing project
        project = Project(project_name, '', '', project_path)
        setup_type = project.get_setup_type()
        videos_path = os.path.join(project_path, 'videos') if "Video" in setup_type else None
        if videos_path:
            os.makedirs(videos_path, exist_ok=True)
        
        if not os.path.exists(temp_upload_dir):
            raise ValueError('No files found for upload ID')

        initial_files = os.listdir(temp_upload_dir)
        if not initial_files:
            raise ValueError('No files uploaded')

        initial_video_count = 0
        if videos_path and os.path.exists(videos_path):
            initial_video_count = len([f for f in os.listdir(videos_path) if os.path.splitext(f)[1].lower() in VALID_VIDEO_EXTENSIONS])

        # Process files
        image_paths = _process_temp_upload_dir(images_path, temp_upload_dir, videos_path=videos_path, setup_type=setup_type)

        annotation_files = [f for f in os.listdir(temp_upload_dir) if f.lower().endswith(('.json', '.yaml', '.txt'))]

        final_video_count = len([f for f in os.listdir(videos_path) if os.path.splitext(f)[1].lower() in VALID_VIDEO_EXTENSIONS]) if videos_path else 0
        new_videos = final_video_count - initial_video_count

        new_content = len(image_paths) + len(annotation_files) + new_videos
        if new_content == 0:
            if initial_files:
                raise ValueError('All uploaded files already exist in the project')
            else:
                raise ValueError('No files uploaded')

        if len(image_paths) > 0 or len(annotation_files) > 0 or new_videos > 0:
            if len(image_paths) > 0:
                print("Adding new images to project database...")
                added_count = 0
                for path in image_paths:
                    if project.add_image(path):
                        added_count += 1
                print(f"Added {added_count}/{len(image_paths)} new images")
                tracker.log_substep('Added new images', details={'count': added_count, 'total_new': len(image_paths)})

            has_annotations_or_new_images = len(annotation_files) > 0 or len(image_paths) > 0
            if has_annotations_or_new_images:
                all_image_paths = image_paths if image_paths else [img[1] for img in project.get_images()]
                project.parse_and_add_annotations(temp_upload_dir, all_image_paths)
                tracker.log_substep('Parsed and added annotations', details={'files': len(annotation_files), 'images_processed': len(all_image_paths)})

            if "Video" in setup_type:
                target_fps = 5  # Default for import; or add form param if needed
                video_paths = [os.path.join(videos_path, f) for f in os.listdir(videos_path) if os.path.splitext(f)[1].lower() in VALID_VIDEO_EXTENSIONS]
                selected_total = 0
                for v_path in video_paths:
                    video_id = project.add_video(v_path)
                    if video_id:
                        selected = project.add_selected_frames(video_id, target_fps=target_fps)
                        selected_total += selected
                tracker.log_substep('Videos processed', details={'video_count': len(video_paths), 'selected_frames': selected_total})
                print(f"Processed {len(video_paths)} videos, selected {selected_total} frame indices at {target_fps} FPS.")

            tracker.log_step('Import completed', details={'project_name': project_name, 'new_images': len(image_paths), 'annotations_processed': len(annotation_files)})
            shutil.rmtree(temp_upload_dir, ignore_errors=True)
            print(f"Import to {project_name} completed: {len(image_paths)} new images, {len(annotation_files)} annotations processed, {new_videos} new videos")
            return {"success": True, "new_images": len(image_paths), "annotations_processed": len(annotation_files), "new_videos": new_videos}
        else:
            raise ValueError('No new images or annotations found')
    except Exception as e:
        tracker.log_error(e, step='Import images')
        logger.error(f"Error in import_images: {e}")
        print(f"Error importing to {project_name}: {str(e)}")
        raise HTTPException(status_code=500, detail=f'Server error: {str(e)}')

@router.post("/parse_annotations")
async def parse_annotations(
    request: Request,
    current_user: User = Depends(get_current_user_from_cookie)
):
    form = await request.form()
    upload_id = form.get('upload_id')
    class_names = form.get('class_names', '')
    project_classes = [cls.strip() for cls in class_names.replace(';', ',').replace('.', ',').split(',') if cls.strip()]

    cache_dir = get_cache_folder()
    temp_base = os.path.join(cache_dir, 'temp_chunks')
    temp_upload_dir = os.path.join(temp_base, upload_id)
    if not os.path.exists(temp_upload_dir):
        raise HTTPException(status_code=404, detail='Upload ID not found')

    annotation_files = [f for f in os.listdir(temp_upload_dir) if f.endswith('.json') or f.endswith('.yaml')]

    summary = {
        'coco_files': [],
        'yolo_files': [],
        'class_mapping': {},
        'annotated_images': 0
    }

    name_matcher = NameMatcher(project_classes)

    print(f"Parsing {len(annotation_files)} annotation files...")
    for anno_file in annotation_files:
        anno_path = os.path.join(temp_upload_dir, anno_file)
        if anno_file.endswith('.json'):
            try:
                parser = CocoAnnotationParser(anno_path)
                summary['coco_files'].append(anno_file)
                for img_id, annotations in parser.annotations_by_image.items():
                    image_file = parser.images_dict.get(img_id)
                    if image_file:
                        summary['annotated_images'] += 1
                        for anno in annotations:
                            cat_name = parser.categories.get(anno['category_id'], 'unknown')
                            matched_class = name_matcher.match(cat_name)
                            summary['class_mapping'][cat_name] = matched_class
            except Exception as e:
                logger.error(f"Error parsing COCO file {anno_file} for summary: {e}")
        elif anno_file.endswith('.yaml'):
            try:
                parser = YoloAnnotationParser(anno_path, temp_upload_dir)
                summary['yolo_files'].append(anno_file)
                for image_file in os.listdir(temp_upload_dir):
                    if image_file.lower().endswith(tuple(VALID_IMAGE_EXTENSIONS)):
                        annotations = parser.get_annotations_for_image(image_file)
                        if annotations:
                            summary['annotated_images'] += 1
                            for anno in annotations:
                                cat_name = anno['category_name']
                                matched_class = name_matcher.match(cat_name)
                                summary['class_mapping'][cat_name] = matched_class
            except Exception as e:
                logger.error(f"Error parsing YOLO file {anno_file} for summary: {e}")

    print(f"Annotation parsing complete: {summary['annotated_images']} annotated images found")
    return {"success": True, "summary": summary}

@router.post("/upload_chunk")
async def upload_chunk(
    request: Request,  # Add request (for potential tracker use later)
    chunk: UploadFile = File(...),
    upload_id: str = Form(...),
    file_id: str = Form(...),
    chunk_index: int = Form(...),
    filename: str = Form(...)
):
    secure_filename(filename)  # Validate
    if not all([upload_id, file_id, filename]):
        raise HTTPException(status_code=400, detail='Missing upload parameters')

    cache_dir = get_cache_folder()
    temp_base = os.path.join(cache_dir, 'temp_chunks')
    os.makedirs(temp_base, exist_ok=True)
    
    temp_dir = os.path.join(temp_base, upload_id, file_id)
    os.makedirs(temp_dir, exist_ok=True)
    
    try:
        current_time = time.time()
        for temp_upload_id in os.listdir(temp_base):
            temp_upload_path = os.path.join(temp_base, temp_upload_id)
            if os.path.isdir(temp_upload_path):
                mtime = os.path.getmtime(temp_upload_path)
                if current_time - mtime > 3600:
                    shutil.rmtree(temp_upload_path, ignore_errors=True)
                    logger.info(f"Cleaned up stale temp directory: {temp_upload_path}")
    except Exception as e:
        logger.warning(f"Error cleaning up stale temp files: {e}")

    try:
        temp_stat = os.stat(temp_base)
        if not os.access(temp_base, os.W_OK):
            logger.error(f"Temporary directory {temp_base} is not writable")
            raise HTTPException(status_code=500, detail='Server error: Temporary directory not writable')
        total, used, free = shutil.disk_usage(temp_base)
        chunk_size = chunk.size  # Use UploadFile.size
        if free < chunk_size:
            logger.error(f"Insufficient disk space in {temp_base}: {free} bytes available, {chunk_size} bytes needed")
            raise HTTPException(status_code=500, detail='Server error: Insufficient disk space')
        memory = psutil.virtual_memory()
        logger.info(f"System resources: Disk {free / (1024**3):.2f} GB available, Memory {memory.available / (1024**3):.2f} GB available")
    except Exception as e:
        logger.error(f"Error validating temporary directory: {e}")
        raise HTTPException(status_code=500, detail=f'Server error: {str(e)}')

    chunk_path = os.path.join(temp_dir, f'chunk_{chunk_index}')
    try:
        start_time = time.time()
        logger.info(f"Received chunk {chunk_index} for {filename}, size: {chunk_size} bytes")
        with open(chunk_path, "wb") as buffer:
            shutil.copyfileobj(chunk.file, buffer)
        elapsed_time = time.time() - start_time
        logger.info(f"Saved chunk {chunk_index} for {filename} at {chunk_path}, size: {os.path.getsize(chunk_path)} bytes, took {elapsed_time:.2f} seconds")
        return {"success": True}
    except Exception as e:
        logger.error(f"Error saving chunk {chunk_index} for {filename}: {e}")
        print(f"Error saving chunk {chunk_index}: {str(e)}")
        raise HTTPException(status_code=500, detail=f'Chunk save failed: {str(e)}')

@router.post("/assemble_file")
async def assemble_file(
    request: Request,
    upload_id: str = Form(...),
    file_id: str = Form(...),
    total_chunks: int = Form(...),
    filename: str = Form(...),
    expected_hash: Optional[str] = Form(None)
):
    filename = secure_filename(filename)
    if not all([upload_id, file_id, filename, total_chunks]):
        raise HTTPException(status_code=400, detail='Missing assembly parameters')

    cache_dir = get_cache_folder()
    temp_base = os.path.join(cache_dir, 'temp_chunks')
    temp_dir = os.path.join(temp_base, upload_id, file_id)
    final_dir = os.path.join(temp_base, upload_id)
    os.makedirs(final_dir, exist_ok=True)
    final_path = os.path.join(final_dir, filename)
    lock_path = final_path + '.lock'

    try:
        with FileLock(lock_path):
            start_time = time.time()
            logger.info(f"Starting assembly for {filename} (ID: {file_id}) with {total_chunks} chunks")

            total, used, free = shutil.disk_usage(os.path.dirname(final_path))
            estimated_size = sum(os.path.getsize(os.path.join(temp_dir, f'chunk_{i}'))
                                 for i in range(total_chunks) if os.path.exists(os.path.join(temp_dir, f'chunk_{i}')))
            if free < estimated_size * 1.1:
                logger.error(f"Insufficient disk space for {filename}: {free / (1024**3):.2f} GB available, "
                             f"{estimated_size / (1024**3):.2f} GB needed")
                print(f"Assembly failed for {filename}: Insufficient disk space")
                raise HTTPException(status_code=507, detail='Insufficient disk space for file assembly')

            memory = psutil.virtual_memory()
            logger.info(f"System resources: Disk {free / (1024**3):.2f} GB available, "
                        f"Memory {memory.available / (1024**3):.2f} GB available")

            with open(final_path, 'wb') as f:
                for i in range(total_chunks):
                    chunk_path = os.path.join(temp_dir, f'chunk_{i}')
                    if not os.path.exists(chunk_path):
                        logger.error(f"Missing chunk {i} for {filename}")
                        raise FileNotFoundError(f'Missing chunk {i}')

                    chunk_size = os.path.getsize(chunk_path)
                    logger.info(f"Assembling chunk {i}/{total_chunks} for {filename}, size: {chunk_size} bytes")

                    with open(chunk_path, 'rb') as chunk_file:
                        copyfileobj(chunk_file, f)

                    os.remove(chunk_path)

            if expected_hash:
                with open(final_path, 'rb') as f:
                    hasher = hashlib.md5()
                    while chunk := f.read(4096):
                        hasher.update(chunk)
                    assembled_hash = hasher.hexdigest()

                if assembled_hash != expected_hash:
                    os.remove(final_path)
                    logger.error(f"Hash mismatch for {filename}: expected {expected_hash}, got {assembled_hash}")
                    print(f"Assembly failed for {filename}: Hash mismatch")
                    raise HTTPException(status_code=400, detail='File corrupted during assembly (hash mismatch)')

            elapsed_time = time.time() - start_time
            final_size = os.path.getsize(final_path)
            logger.info(f"File {filename} assembled at {final_path}, size: {final_size} bytes, took {elapsed_time:.2f} seconds")

            try:
                os.rmdir(temp_dir)
            except OSError as e:
                if e.errno != errno.ENOTEMPTY:
                    logger.warning(f"Cleanup warning for {temp_dir}: {str(e)}")

            return {"success": True, "file_path": final_path}

    except FileNotFoundError as e:
        logger.error(f"Assembly failed for {filename}: {str(e)}")
        print(f"Assembly failed for {filename}: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except OSError as e:
        logger.error(f"OS error during assembly of {filename}: {str(e)}")
        print(f"OS error assembling {filename}: {str(e)}")
        raise HTTPException(status_code=500, detail='Server storage error')
    except Exception as e:
        logger.error(f"Unexpected error assembling {filename}: {str(e)}", exc_info=True)
        print(f"Unexpected error assembling {filename}: {str(e)}")
        raise HTTPException(status_code=500, detail='Assembly failed due to server error')
        
@router.post("/check_upload_status")
async def check_upload_status(
    request: Request,  # Add request
    upload_id: str = Form(...),
    file_id: str = Form(...)
):
    cache_dir = get_cache_folder()
    temp_base = os.path.join(cache_dir, 'temp_chunks')
    
    temp_dir = os.path.join(temp_base, upload_id, file_id)
    if not os.path.exists(temp_dir):
        return {"uploaded_chunks": 0}
    
    uploaded_chunks = len([f for f in os.listdir(temp_dir) if f.startswith('chunk_')])
    logger.info(f"Checked upload status for upload_id={upload_id}, file_id={file_id}: {uploaded_chunks} chunks uploaded")
    return {"uploaded_chunks": uploaded_chunks}

@router.post("/cleanup_chunks")
async def cleanup_chunks(request: Request, current_user: User = Depends(get_current_user_from_cookie)):
    cache_dir = get_cache_folder()
    temp_base = os.path.join(cache_dir, 'temp_chunks')
    try:
        if os.path.exists(temp_base):
            shutil.rmtree(temp_base, ignore_errors=True)
        os.makedirs(temp_base, exist_ok=True)
        logger.info("Cleaned up temporary chunk directory")
        print("Temporary chunks cleaned up")
        return {"success": True}
    except Exception as e:
        logger.error(f"Error cleaning up chunks: {e}")
        print(f"Error cleaning up chunks: {str(e)}")
        raise HTTPException(status_code=500, detail=f'Cleanup failed: {str(e)}')

@router.post("/cleanup_temp")
async def cleanup_temp(request: Request, current_user: User = Depends(get_current_user_from_cookie)):
    """Manually clean up all temporary files older than 1 hour."""
    print("Starting manual temp cleanup...")
    cache_dir = get_cache_folder()
    temp_base = os.path.join(cache_dir, 'temp_chunks')
    try:
        current_time = time.time()
        cleaned = 0
        if os.path.exists(temp_base):
            stale_dirs = [d for d in os.listdir(temp_base) if os.path.isdir(os.path.join(temp_base, d))]
            for temp_upload_id in stale_dirs:
                temp_upload_path = os.path.join(temp_base, temp_upload_id)
                mtime = os.path.getmtime(temp_upload_path)
                if current_time - mtime > 3600:
                    shutil.rmtree(temp_upload_path, ignore_errors=True)
                    logger.info(f"Cleaned up stale temp directory: {temp_upload_path}")
                    cleaned += 1
        logger.info(f"Manual temp cleanup completed, removed {cleaned} stale directories")
        print(f"Manual temp cleanup completed, removed {cleaned} stale directories")
        return {"success": True, "cleaned": cleaned}
    except Exception as e:
        logger.error(f"Error during manual temp cleanup: {e}")
        print(f"Error during manual temp cleanup: {str(e)}")
        raise HTTPException(status_code=500, detail=f'Cleanup failed: {str(e)}')