# visiofirm/utils/video_export_utils.py
"""
VisioFirm Video Export Utilities

This module provides functions for exporting video annotations to various formats.
No splitting is supported; all frames from selected videos are exported as a single set.
Supports extraction of frame images if specified.

Dependencies: Assumes access to Project, cv2, PIL, etc.

Supported Formats:
- Detection (Bounding Box / Oriented Bounding Box): 'COCO_VIDEO' (JSON), 'MOT' (TXT)
- Segmentation: 'COCO_SEG_VIDEO' (JSON with polygons), 'MASK_SEQUENCE' (PNG per frame, instance/semantic), 'MASK_VIDEO' (MP4 video of masks)

Usage:
    videos_data = get_videos_and_frames(project, selected_videos_paths)
    zip_buffer = generate_coco_video_export(project, videos_data, 'COCO_VIDEO', extract_frames=True)
"""

import os
import zipfile
from io import BytesIO
import json
import sqlite3
import cv2
import numpy as np
from PIL import Image
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)

def get_videos_and_frames(project, selected_videos: List[str] = None, extract_frames: bool = False) -> List[Dict[str, Any]]:
    """
    Retrieve videos and their annotated frames from the project DB.
    
    Args:
        project: Project instance.
        selected_videos: List of absolute video paths; None for all videos with annotations.
        extract_frames: If True, pre-extract frame images (heavy; done during export).
    
    Returns:
        List of dicts: [{'video_id': int, 'path': str, 'name': str, 'fps': float, 'width': int, 'height': int, 'frames': List[Dict with 'frame_number', 'image_id']}]
    """
    with sqlite3.connect(project.db_path) as conn:
        cursor = conn.cursor()
        if selected_videos:
            placeholders = ','.join('?' for _ in selected_videos)
            cursor.execute(f'''
                SELECT v.video_id, v.absolute_path, v.name, v.fps, v.width, v.height
                FROM Videos v
                WHERE v.absolute_path IN ({placeholders})
            ''', selected_videos)
        else:
            cursor.execute('''
                SELECT v.video_id, v.absolute_path, v.name, v.fps, v.width, v.height
                FROM Videos v
                JOIN Frames f ON v.video_id = f.video_id
                JOIN Images i ON f.image_id = i.image_id
                JOIN Annotations a ON i.image_id = a.image_id
                GROUP BY v.video_id
            ''')
        videos = cursor.fetchall()

    video_data = []
    for vid in videos:
        video_id, path, name, fps, width, height = vid
        cursor.execute('''
            SELECT f.frame_number, f.image_id
            FROM Frames f
            JOIN Images i ON f.image_id = i.image_id
            JOIN Annotations a ON i.image_id = a.image_id
            WHERE f.video_id = ?
            ORDER BY f.frame_number
        ''', (video_id,))
        annotated_frames = cursor.fetchall()
        
        frames = [{'frame_number': fn, 'image_id': iid} for fn, iid in annotated_frames]
        
        if not frames:
            logger.warning(f"No annotated frames for video {name}")
            continue
            
        video_data.append({
            'video_id': video_id,
            'path': path,
            'name': name,
            'fps': fps or 30.0,
            'width': width,
            'height': height,
            'frames': frames
        })
    
    if not video_data:
        raise ValueError("No annotated videos found")
    
    logger.info(f"Retrieved {len(video_data)} videos with {sum(len(v['frames']) for v in video_data)} annotated frames")
    return video_data

def _extract_frame_image(video_path: str, frame_number: int, width: int, height: int) -> BytesIO:
    """Extract a single frame as JPEG bytes using OpenCV. Assumes frame_number is 1-based."""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")
    # Seek to 0-based index (frame_number - 1)
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number - 1)
    ret, frame = cap.read()
    cap.release()
    if not ret:
        raise RuntimeError(f"Failed to extract frame {frame_number} from {video_path}")
    # Resize if needed (though DB has width/height)
    frame = cv2.resize(frame, (width, height))
    # BGR to RGB
    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    # To JPEG bytes
    pil_img = Image.fromarray(frame_rgb)
    img_buffer = BytesIO()
    pil_img.save(img_buffer, format='JPEG', quality=95)
    img_buffer.seek(0)
    return img_buffer

def _add_videos_to_zip(zip_file, videos_data: List[Dict[str, Any]]):
    """Helper to add video files to the ZIP under videos/ folder."""
    for vid in videos_data:
        video_path = vid['path']
        video_name = vid['name']
        if os.path.exists(video_path):
            try:
                zip_file.write(video_path, f"videos/{video_name}")
                logger.debug(f"Added video {video_name} to ZIP")
            except Exception as e:
                logger.error(f"Failed to add video {video_name} to ZIP: {e}")
        else:
            logger.warning(f"Video file not found: {video_path}")

def generate_coco_video_export(project, videos_data: List[Dict[str, Any]], setup_type: str, project_name: str, project_description: str, extract_frames: bool = False) -> BytesIO:
    """
    Generate COCO-style JSON for video detection/segmentation (no track_id for simplicity).
    If extract_frames=True, includes frame JPEGs in zip.
    """
    categories = project.get_classes()
    category_dict = {name: idx + 1 for idx, name in enumerate(categories)}
    
    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        images_list = []
        annotations_list = []
        annotation_id = 1
        
        for vid in videos_data:
            for frame_info in vid['frames']:
                frame_num = frame_info['frame_number']
                image_id = f"{vid['name']}_{frame_num:06d}"
                
                file_name = f"{vid['name']}_{frame_num:06d}.jpg" if extract_frames else None
                if extract_frames:
                    try:
                        img_buffer = _extract_frame_image(vid['path'], frame_num, vid['width'], vid['height'])
                        zip_file.writestr(f"frames/{file_name}", img_buffer.getvalue())
                        logger.info(f"Successfully added frame {file_name} to frames/ in ZIP")
                    except Exception as e:
                        logger.error(f"Failed to extract frame {frame_num} for {vid['name']}: {e}")
                        continue
                
                images_list.append({
                    'id': image_id,
                    'video_id': vid['name'],
                    'frame_index': frame_num,
                    'file_name': file_name,
                    'width': vid['width'],
                    'height': vid['height']
                })
                
                # Get annotations for this frame
                with sqlite3.connect(project.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute('SELECT * FROM Annotations WHERE image_id = ?', (frame_info['image_id'],))
                    rows = cursor.fetchall()
                    
                    for row in rows:
                        anno = {
                            'id': annotation_id,
                            'image_id': image_id,
                            'category_id': category_dict.get(row[4], 1),  # class_name
                            'iscrowd': 0,
                            'area': 0
                        }
                        
                        if setup_type in ["Bounding Box", "Oriented Bounding Box"]:
                            x, y, w, h = row[5], row[6], row[7], row[8]
                            if setup_type == "Oriented Bounding Box" and row[9]:  # rotation
                                # Approximate bbox (ignore rotation for COCO bbox; use segmentation if needed)
                                pass
                            anno['bbox'] = [x, y, w, h]
                            anno['area'] = w * h
                        elif setup_type == "Segmentation":
                            segmentation = json.loads(row[10]) if row[10] else []
                            anno['segmentation'] = [segmentation]  # List of polygons
                            if segmentation:
                                xs = segmentation[0::2]
                                ys = segmentation[1::2]
                                min_x, min_y = min(xs), min(ys)
                                max_x, max_y = max(xs), max(ys)
                                anno['bbox'] = [min_x, min_y, max_x - min_x, max_y - min_y]
                                anno['area'] = (max_x - min_x) * (max_y - min_y)
                        
                        annotations_list.append(anno)
                        annotation_id += 1
        
        # Create COCO JSON
        coco_data = {
            'info': {
                'year': datetime.now().year,
                'Software': 'VisioFirm',
                'contributor': '',
                'date_created': datetime.now().strftime('%Y-%m-%d'),
                'project_name': project_name,
                'project_description': project_description,
                'description': 'Video annotations in COCO format'
            },
            'licenses': [{'id': 1, 'url': 'https://creativecommons.org/licenses/by/4.0/', 'name': 'CC BY 4.0'}],
            'images': images_list,
            'annotations': annotations_list,
            'categories': [{'id': idx, 'name': name} for name, idx in category_dict.items()]
        }
        
        zip_file.writestr('annotations/coco_video.json', json.dumps(coco_data, indent=2))

        # Add videos to ZIP
        _add_videos_to_zip(zip_file, videos_data)
    
    zip_buffer.seek(0)
    return zip_buffer

def generate_mot_export(project, videos_data: List[Dict[str, Any]], setup_type: str, extract_frames: bool = False) -> BytesIO:
    """
    Generate MOT format TXT for detection (Bounding Box only; ignores rotation).
    One TXT per video: frame, -1 (no track), x, y, w, h, 1.0, -1,-1,-1
    If extract_frames=True, includes frame JPEGs in ZIP.
    """
    if setup_type not in ["Bounding Box", "Oriented Bounding Box"]:
        raise ValueError("MOT only supports Bounding Box / Oriented Bounding Box")
    
    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for vid in videos_data:
            lines = []
            lines.append("# frame, -1, left, top, width, height, 1.0, -1, -1, -1")  # Header (no track_id)
            
            for frame_info in vid['frames']:
                frame_num = frame_info['frame_number']
                
                # Extract frame if requested
                file_name = f"{vid['name']}_{frame_num:06d}.jpg"
                if extract_frames:
                    try:
                        img_buffer = _extract_frame_image(vid['path'], frame_num, vid['width'], vid['height'])
                        zip_file.writestr(f"frames/{file_name}", img_buffer.getvalue())
                        logger.info(f"Successfully added frame {file_name} to frames/ in ZIP")
                    except Exception as e:
                        logger.error(f"Failed to extract frame {frame_num} for {vid['name']}: {e}")
                
                with sqlite3.connect(project.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute('SELECT * FROM Annotations WHERE image_id = ?', (frame_info['image_id'],))
                    rows = cursor.fetchall()
                    
                    for row in rows:
                        x, y, w, h = row[5], row[6], row[7], row[8]
                        if setup_type == "Oriented Bounding Box":
                            # Approximate axis-aligned bbox
                            center_x = row[5] + (row[7] / 2)
                            center_y = row[6] + (row[8] / 2)
                            angle = row[9] or 0
                            # Simple approx: use w,h as is, ignore rotation for MOT
                            pass
                        lines.append(f"{frame_num}, -1, {x:.1f}, {y:.1f}, {w:.1f}, {h:.1f}, 1.0, -1, -1, -1")
            
            txt_name = f"{vid['name']}.txt"
            zip_file.writestr(f"annotations/{txt_name}", "\n".join(lines))

        # Add videos to ZIP
        _add_videos_to_zip(zip_file, videos_data)
    
    zip_buffer.seek(0)
    return zip_buffer

def generate_mask_sequence_export(project, videos_data: List[Dict[str, Any]], setup_type: str, extract_frames: bool = False, semantic: bool = False) -> BytesIO:
    """
    Generate PNG mask sequence per frame (instance or semantic).
    - Instance: pixel value = instance_id (sequential per object across video).
    - Semantic: pixel value = class_id.
    Includes original frames if extract_frames=True.
    """
    if setup_type != "Segmentation":
        raise ValueError("Mask sequence only supports Segmentation")
    
    categories = project.get_classes()
    cat_to_id = {c: i+1 for i, c in enumerate(categories)}
    
    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for vid in videos_data:
            instance_counter = {}  # For instance: {class_name: current_id}
            
            for frame_info in vid['frames']:
                frame_num = frame_info['frame_number']
                basename = f"{vid['name']}_{frame_num:06d}"
                
                # Original frame if requested
                if extract_frames:
                    try:
                        img_buffer = _extract_frame_image(vid['path'], frame_num, vid['width'], vid['height'])
                        zip_file.writestr(f"frames/{basename}.jpg", img_buffer.getvalue())
                    except Exception as e:
                        logger.error(f"Failed to extract frame {frame_num}: {e}")
                
                # Create mask: np array
                mask = np.zeros((vid['height'], vid['width']), dtype=np.uint8)
                
                with sqlite3.connect(project.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute('SELECT class_name, segmentation FROM Annotations WHERE image_id = ?', (frame_info['image_id'],))
                    rows = cursor.fetchall()
                    
                    for row in rows:
                        class_name, seg_json = row[0], row[1]
                        if not seg_json:
                            continue
                        points = json.loads(seg_json)
                        if len(points) < 6:
                            continue
                        pts = np.array(points).reshape(-1, 2).astype(np.int32)
                        
                        if semantic:
                            # Semantic: fill with class_id
                            fill_val = cat_to_id.get(class_name, 0)
                        else:
                            # Instance: assign unique id per object
                            if class_name not in instance_counter:
                                instance_counter[class_name] = 1
                            fill_val = instance_counter[class_name]
                            instance_counter[class_name] += 1
                        
                        cv2.fillPoly(mask, [pts], fill_val)
                
                # Save mask as PNG
                pil_mask = Image.fromarray(mask)
                mask_buffer = BytesIO()
                pil_mask.save(mask_buffer, format='PNG')
                mask_buffer.seek(0)
                zip_file.writestr(f"masks/{basename}.png", mask_buffer.getvalue())

        # Add videos to ZIP
        _add_videos_to_zip(zip_file, videos_data)
    
    zip_buffer.seek(0)
    return zip_buffer

def generate_mask_video_export(project, videos_data: List[Dict[str, Any]], setup_type: str, semantic: bool = False, extract_frames: bool = False) -> BytesIO:
    """
    Generate MP4 video of annotation masks (grayscale or colored).
    One video per input video_data list item? No, single video concatenating all? For simplicity, one ZIP with per-video MP4.
    If extract_frames=True, includes original frame JPEGs in ZIP.
    """
    if setup_type != "Segmentation":
        raise ValueError("Mask video only supports Segmentation")
    
    categories = project.get_classes()
    if semantic and len(categories) > 255:
        logger.warning("Too many classes for uint8; using grayscale binary")
        semantic = False  # Fallback
    
    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for vid in videos_data:
            # Temp video path for masks
            temp_mask_video = f"temp_mask_{vid['name']}.mp4"
            
            # Open video capture
            cap = cv2.VideoCapture(vid['path'])
            if not cap.isOpened():
                logger.error(f"Cannot open video for mask video: {vid['path']}")
                continue
            fps = vid['fps']
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            if total_frames == 0:
                logger.warning(f"Video {vid['name']} has 0 frames")
                cap.release()
                continue
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            out = cv2.VideoWriter(temp_mask_video, fourcc, fps, (vid['width'], vid['height']))
            
            frame_map = {f['frame_number']: f['image_id'] for f in vid['frames']}
            
            cat_to_id = {c: i+1 for i, c in enumerate(categories)}
            instance_counter = {}  # Reset per video
            
            frame_num = 1
            while frame_num <= total_frames:
                ret, frame_bgr = cap.read()
                if not ret:
                    logger.warning(f"Failed to read frame {frame_num} from {vid['name']}")
                    break
                
                # Extract original frame if requested (use the read frame_bgr)
                if extract_frames:
                    try:
                        # Use the read frame (already in BGR); convert and save
                        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
                        pil_img = Image.fromarray(frame_rgb)
                        img_buffer = BytesIO()
                        pil_img.save(img_buffer, format='JPEG', quality=95)
                        file_name = f"{vid['name']}_{frame_num:06d}.jpg"
                        zip_file.writestr(f"frames/{file_name}", img_buffer.getvalue())
                        logger.info(f"Successfully added frame {file_name} to frames/ in ZIP")
                    except Exception as e:
                        logger.error(f"Failed to extract frame {frame_num} for {vid['name']}: {e}")
                
                # Create mask for this frame
                mask = np.zeros((vid['height'], vid['width']), dtype=np.uint8)
                image_id = frame_map.get(frame_num)
                if image_id:
                    with sqlite3.connect(project.db_path) as conn:
                        cursor = conn.cursor()
                        cursor.execute('SELECT class_name, segmentation FROM Annotations WHERE image_id = ?', (image_id,))
                        rows = cursor.fetchall()
                        
                        for row in rows:
                            class_name, seg_json = row[0], row[1]
                            if not seg_json:
                                continue
                            points = json.loads(seg_json)
                            if len(points) < 6:
                                continue
                            pts = np.array(points).reshape(-1, 2).astype(np.int32)
                            
                            if semantic:
                                fill_val = cat_to_id.get(class_name, 0)
                            else:
                                if class_name not in instance_counter:
                                    instance_counter[class_name] = 1
                                fill_val = instance_counter[class_name]
                                instance_counter[class_name] += 1
                            
                            cv2.fillPoly(mask, [pts], fill_val)
                
                # If semantic and multi-class, colorize? For now, grayscale if binary, else as-is
                if semantic and max(cat_to_id.values()) > 1:
                    # Optional: create colored mask
                    colored_mask = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)
                    # Assign colors per class? Skip for simplicity, use grayscale
                    pass
                else:
                    colored_mask = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)
                
                out.write(colored_mask)
                frame_num += 1
            
            out.release()
            cap.release()
            
            if os.path.exists(temp_mask_video):
                with open(temp_mask_video, 'rb') as f:
                    zip_file.writestr(f"masks/{vid['name']}_mask_video.mp4", f.read())
                os.unlink(temp_mask_video)

        # Add videos to ZIP
        _add_videos_to_zip(zip_file, videos_data)
    
    zip_buffer.seek(0)
    return zip_buffer

def generate_video_export(project, videos_data: List[Dict[str, Any]], format: str, setup_type: str, project_name: str, project_description: str, extract_frames: bool = False, semantic: bool = False) -> BytesIO:
    """
    Dispatch to specific video export generators.
    """
    VALID_VIDEO_FORMATS = {
        'COCO_VIDEO': lambda p, vd, st, pn, pd, ef, s: generate_coco_video_export(p, vd, st, pn, pd, ef),
        'MOT': lambda p, vd, st, pn, pd, ef, s: generate_mot_export(p, vd, st, ef),
        'COCO_SEG_VIDEO': lambda p, vd, st, pn, pd, ef, s: generate_coco_video_export(p, vd, st, pn, pd, ef),
        'MASK_SEQUENCE': lambda p, vd, st, pn, pd, ef, s: generate_mask_sequence_export(p, vd, st, ef, s),
        'MASK_VIDEO': lambda p, vd, st, pn, pd, ef, s: generate_mask_video_export(p, vd, st, s, ef)
    }
    
    if format not in VALID_VIDEO_FORMATS:
        raise ValueError(f"Unsupported video format: {format}")
    
    if setup_type == "Segmentation" and format in ['COCO_VIDEO', 'MOT']:
        format = 'COCO_SEG_VIDEO' if format == 'COCO_VIDEO' else None  # Redirect
    
    gen_func = VALID_VIDEO_FORMATS[format]
    return gen_func(project, videos_data, setup_type, project_name, project_description, extract_frames, semantic)