# visiofirm/tracker.py
import cv2
import numpy as np
import threading
import time
import logging
from tqdm import tqdm  
import os
from visiofirm.config import TMP_FOLDER
from ultralytics.models.sam import SAM2VideoPredictor, SAM
import sqlite3
import json
from visiofirm.utils.downloader import get_or_download_model
import copy

logger = logging.getLogger(__name__)

last_progress_track = {}
    
class VFTrackerBase:
    """
    Base class for trackers.
    """
    def __init__(self, project, video_path, start_frame, end_frame, initial_annotations, frame_step=1, device='cpu'):
        self.project = project
        self.video_path = video_path
        self.start_frame = int(start_frame)  # Ensure int
        self.end_frame = int(end_frame)
        self.initial_annotations = initial_annotations
        self.frame_step = frame_step
        self.device = device 
        self.status = 'not_started'
        self.progress = 0
        self.results = {}
        self.thread = None
        self.cap = None
        self.fps = None
        self.video_h = None
        self.video_w = None
        self.frame_data = []  # list of tuples (frame_num, timestamp, subsampled, image_id)

    def average_multiples_of_30(self):
        multiples = [fn for fn in list(self.results.keys()) if fn % 30 == 0]
        for fn in multiples:
            prev_fns = [f for f in self.results if f < fn]
            next_fns = [f for f in self.results if f > fn]
            if not prev_fns and not next_fns:
                continue
            if not prev_fns:
                # first, copy next
                next_fn = min(next_fns)
                self.results[fn] = copy.deepcopy(self.results[next_fn])
                continue
            if not next_fns:
                # last, copy prev
                prev_fn = max(prev_fns)
                self.results[fn] = copy.deepcopy(self.results[prev_fn])
                continue
            # average
            prev_fn = max(prev_fns)
            next_fn = min(next_fns)
            prev_annos = self.results[prev_fn]
            next_annos = self.results[next_fn]
            if len(prev_annos) != len(next_annos):
                logger.warning(f"Annotation count mismatch {len(prev_annos)} vs {len(next_annos)} at {fn}, skipping average")
                continue
            # assume same order and labels
            avg_annos = []
            for i in range(len(prev_annos)):
                p = prev_annos[i]
                n = next_annos[i]
                if p['label'] != n['label']:
                    logger.warning(f"Label mismatch at {fn}: {p['label']} vs {n['label']}, copying prev")
                    avg_annos.append(copy.deepcopy(p))
                    continue
                avg = {'label': p['label']}
                conf = (p.get('confidence', 1.0) + n.get('confidence', 1.0)) / 2
                avg['confidence'] = conf
                if 'bbox' in p and 'bbox' in n:
                    bx = (p['bbox'][0] + n['bbox'][0]) / 2
                    by = (p['bbox'][1] + n['bbox'][1]) / 2
                    bw = (p['bbox'][2] + n['bbox'][2]) / 2
                    bh = (p['bbox'][3] + n['bbox'][3]) / 2
                    avg['bbox'] = [float(bx), float(by), float(bw), float(bh)]
                elif 'segmentation' in p and 'segmentation' in n:
                    # for mask, average points? Hard, perhaps average bboxes then ignore, or skip
                    # for now, average as bbox then find contour or something, but complicated
                    # assume bbox for this fix
                    logger.warning(f"Segmentation averaging not implemented at {fn}, copying prev")
                    avg = copy.deepcopy(p)
                else:
                    avg = copy.deepcopy(p)
                avg_annos.append(avg)
            self.results[fn] = avg_annos

    def _init_capture(self):
        self.cap = cv2.VideoCapture(self.video_path)
        if not self.cap.isOpened():
            raise RuntimeError(f"Failed to open video: {self.video_path}")
        self.fps = self.cap.get(cv2.CAP_PROP_FPS)
        self.video_h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.video_w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))

    def _get_frame_data(self):
        with sqlite3.connect(self.project.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT video_id, absolute_path, fps, frame_count, width, height FROM Videos WHERE absolute_path = ?', (self.video_path,))
            result = cursor.fetchone()
            if not result:
                raise ValueError(f"Video not found in database: {self.video_path}")
            video_id, absolute_path, fps, total_frames, width, height = result
            self.video_id = video_id
            self.video_w = width
            self.video_h = height
            # Use DB fps if available, else fall back to 30 (will be overwritten by cap if opened)
            self.fps = fps or self.fps

        start_frame = max(0, min(self.start_frame, total_frames - 1))
        end_frame = max(start_frame, min(self.end_frame, total_frames - 1))

        # Query existing frames in range
        cursor.execute('''
            SELECT frame_number, subsampled
            FROM Frames
            WHERE video_id = ? AND frame_number BETWEEN ? AND ?
            ORDER BY frame_number
        ''', (self.video_id, start_frame, end_frame))
        db_frames = cursor.fetchall()

        if len(db_frames) != (end_frame - start_frame + 1):
            logger.warning(f"Missing {(end_frame - start_frame + 1) - len(db_frames)} frames in range [{start_frame}, {end_frame}] for video {self.video_id}")

        # Build frame_data as (frame_num, timestamp, subsampled, image_id)
        self.frame_data = []
        for frame_num in range(start_frame, end_frame + 1):
            db_entry = next((row for row in db_frames if row[0] == frame_num), None)
            subsampled = bool(db_entry[1]) if db_entry else False
            timestamp = (frame_num / self.fps) if self.fps and self.fps > 0 else 0.0
            self.frame_data.append((frame_num, timestamp, subsampled, None))

    def run(self):
        """Synchronous run. Blocks until done."""
        if self.status == 'running':
            raise RuntimeError("Tracking already running")
        self._run_core()
        return self.get_status()

    def run_threaded(self, callback=None):
        """Background thread. Optional callback for status."""
        if self.status == 'running':
            raise RuntimeError("Tracking already running")
        self.thread = threading.Thread(target=self._run_core)
        self.thread.start()
        key = f"{self.project.name}_{self.video_path}_{self.start_frame}"
        if callback:
            def poll():
                while self.thread.is_alive():
                    callback(self.get_status())
                    time.sleep(1)
                callback(self.get_status())
            threading.Thread(target=poll).start()
        else:
            # Local poll with prints
            def poll_local():
                while self.thread.is_alive():
                    progress = self.progress
                    if key not in last_progress_track:
                        last_progress_track[key] = 0
                    if abs(progress - last_progress_track[key]) >= 5 or self.status != 'running':
                        print(f"Tracking progress for '{key}': {progress:.1f}% ({self.status})")
                        last_progress_track[key] = progress
                    time.sleep(1)
                print(f"Tracking completed for '{key}': 100.0% (completed)")
                if key in last_progress_track:
                    del last_progress_track[key]
            threading.Thread(target=poll_local).start()
        return self.thread

    def get_status(self):
        return {'status': self.status, 'progress': self.progress, 'results': self.results if self.status == 'completed' else None}

    def _run_core(self):
        raise NotImplementedError("Subclasses must implement _run_core")

    def _interpolate_bbox(self, bbox1, bbox2, factor):
        """Linear interpolate between two bboxes [x,y,w,h]."""
        return [
            int(bbox1[0] + factor * (bbox2[0] - bbox1[0])),
            int(bbox1[1] + factor * (bbox2[1] - bbox1[1])),
            int(bbox1[2] + factor * (bbox2[2] - bbox1[2])),
            int(bbox1[3] + factor * (bbox2[3] - bbox1[3]))
        ]

    def fill_missing_segments(self, results_dict):
        # Sort frame data by frame_num
        sorted_frame_data = sorted(self.frame_data, key=lambda x: x[0])
        # Get a list of all frame_nums that have annotations
        annotated_frame_nums = sorted(results_dict.keys())

        # There must be at least two annotated frames to perform interpolation
        if len(annotated_frame_nums) < 2:
            return

        # Identify segments that lack annotations
        segments = []
        start_of_segment = None
        end_of_segment = None

        # Iterate over sorted frame data to identify segments without annotations
        for frame_num, ts, subsampled, _ in sorted_frame_data:
            if frame_num not in results_dict:
                if start_of_segment is None:
                    start_of_segment = frame_num  # Start of a potential missing segment
                end_of_segment = frame_num  # Update the end of the potential missing segment
            else:
                if start_of_segment is not None:
                    segments.append((start_of_segment, end_of_segment))
                    start_of_segment = None
                    end_of_segment = None

        # Add the last segment if it ends without finding another annotation
        if start_of_segment is not None:
            segments.append((start_of_segment, end_of_segment))

        # Interpolate for each identified segment
        for segment_start, segment_end in segments:
            prev_fn = None
            next_fn = None
            prev_annos = None
            next_annos = None

            # Find the latest annotated frame_num before the segment starts
            for fn in reversed(annotated_frame_nums):
                if fn < segment_start:
                    prev_fn = fn
                    prev_annos = results_dict[prev_fn]
                    break

            # Find the earliest annotated frame_num after the segment ends
            for fn in annotated_frame_nums:
                if fn > segment_end:
                    next_fn = fn
                    next_annos = results_dict[next_fn]
                    break

            # If we have both surrounding annotated frames, interpolate
            if prev_fn is not None and next_fn is not None and prev_annos and next_annos:
                # Calculate the interpolation factor for each frame_num in the missing segment
                for frame_num, ts, subsampled, _ in sorted_frame_data:
                    if segment_start <= frame_num <= segment_end:
                        factor = (frame_num - prev_fn) / (next_fn - prev_fn)
                        interpolated_annos = []

                        # Interpolate each corresponding annotation
                        for prev_anno, next_anno in zip(prev_annos, next_annos):
                            if 'bbox' in prev_anno and 'bbox' in next_anno:
                                interp_bbox = self._interpolate_bbox(prev_anno['bbox'], next_anno['bbox'], factor)
                                interpolated_annos.append({
                                    'bbox': interp_bbox,
                                    'label': prev_anno['label'],
                                    'confidence': (prev_anno.get('confidence', 1.0) + next_anno.get('confidence', 1.0)) / 2
                                })

                        # Add interpolated annotations for this frame_num
                        results_dict[frame_num] = interpolated_annos

    def push_to_db(self):
        if self.status != 'completed':
            raise RuntimeError("Tracking must be completed before pushing to DB")
        with sqlite3.connect(self.project.db_path) as conn:
            cursor = conn.cursor()
            frame_to_image_id = {}
            for frame_num, ts, subsampled, image_id in self.frame_data:
                if image_id is None:
                    absolute_path = f"{self.video_path}#{frame_num}"
                    cursor.execute('SELECT image_id FROM Images WHERE absolute_path = ?', (absolute_path,))
                    res = cursor.fetchone()
                    if res:
                        image_id = res[0]
                    else:
                        cursor.execute('''
                            INSERT INTO Images (absolute_path, width, height)
                            VALUES (?, ?, ?)
                        ''', (absolute_path, self.video_w, self.video_h))
                        image_id = cursor.lastrowid
                    cursor.execute('SELECT frame_id FROM Frames WHERE video_id = ? AND frame_number = ?', (self.video_id, frame_num))
                    if not cursor.fetchone():
                        timestamp = ts  # use precomputed timestamp
                        cursor.execute('''
                            INSERT INTO Frames (video_id, image_id, frame_number, timestamp)
                            VALUES (?, ?, ?, ?)
                        ''', (self.video_id, image_id, frame_num, timestamp))
                frame_to_image_id[frame_num] = image_id

            for frame_num, annos in self.results.items():
                image_id = frame_to_image_id.get(frame_num)
                if image_id is None:
                    logger.warning(f"No image_id for frame_num {frame_num}, skipping")
                    continue
                cursor.execute('SELECT COUNT(*) FROM Annotations WHERE image_id = ?', (image_id,))
                if cursor.fetchone()[0] > 0:
                    logger.info(f"Skipping preannotations for annotated frame at frame_num {frame_num}")
                    continue
                cursor.execute('DELETE FROM Preannotations WHERE image_id = ?', (image_id,))
                for anno in annos:
                    class_name = anno['label']
                    confidence = anno.get('confidence', 1.0)
                    if 'bbox' in anno:
                        x, y, w, h = map(float, anno['bbox'])
                        rotation = 0.0
                        cursor.execute('''
                            INSERT INTO Preannotations (image_id, type, class_name, x, y, width, height, rotation, confidence)
                            VALUES (?, 'bbox', ?, ?, ?, ?, ?, ?, ?)
                        ''', (image_id, class_name, x, y, w, h, rotation, confidence))
                    elif 'segmentation' in anno:
                        segmentation = anno['segmentation']
                        segmentation_json = json.dumps(segmentation)
                        cursor.execute('''
                            INSERT INTO Preannotations (image_id, type, class_name, segmentation, confidence)
                            VALUES (?, 'segmentation', ?, ?, ?)
                        ''', (image_id, class_name, segmentation_json, confidence))
            conn.commit()
        logger.info(f"Pushed {len(self.results)} frames' preannotations to DB for project {self.project.name}")

class CV2Tracker(VFTrackerBase):
    """
    OpenCV-based tracker with optional interpolation for multiple annotated frames.
    Supports multiple annotations for single and multiple classes.
    """
    OPENCV_TRACKERS = {
        'csrt': cv2.TrackerCSRT_create,
        'kcf': cv2.TrackerKCF_create,
        'mil': cv2.TrackerMIL_create,
        'boosting': cv2.legacy.TrackerBoosting_create,
        'medianflow': cv2.legacy.TrackerMedianFlow_create,
        'tld': cv2.legacy.TrackerTLD_create,
        'mosse': cv2.legacy.TrackerMOSSE_create,
    }

    def __init__(self, project, video_path, start_frame, end_frame, initial_annotations,
                 tracker_type='csrt', use_keyframes=False, frame_step=1):
        super().__init__(project, video_path, start_frame, end_frame, initial_annotations, frame_step)
        if tracker_type not in self.OPENCV_TRACKERS:
            raise ValueError(f"Unsupported tracker: {tracker_type}. Options: {list(self.OPENCV_TRACKERS.keys())}")
        self.tracker_type = tracker_type
        self.use_keyframes = use_keyframes
        self.keyframe_map = {}  # Initialize keyframe_map

    def _initialize_keyframes(self):
        """Initialize keyframe_map with snapped frame_nums (snapping by frame number)."""
        if self.use_keyframes:
            self.initial_annotations.sort(key=lambda a: a.get('keyframe_frame', self.start_frame))
            for anno in self.initial_annotations:
                frame = int(anno.get('keyframe_frame', self.start_frame))
                # snap using frame_num (d[0]) not subsampled flag
                snapped_data = min(self.frame_data, key=lambda d: abs(d[0] - frame), default=self.frame_data[0])
                snapped_fn = snapped_data[0]
                if abs(snapped_data[0] - frame) > 1:
                    logger.warning(f"No close match for keyframe_frame {frame}, using {snapped_data[0]}")
                if snapped_fn not in self.keyframe_map:
                    self.keyframe_map[snapped_fn] = []
                self.keyframe_map[snapped_fn].append(anno)

    def _run_core(self):
        try:
            self.status = 'running'
            self.progress = 0
            print(f"Tracking objects in '{self.video_path}' from frame {self.start_frame} to {self.end_frame} using {self.tracker_type}...")

            self._get_frame_data()
            self._initialize_keyframes()
            self._init_capture()

            if not self.frame_data:
                raise ValueError("No frames in range")

            first_f_num, first_ts, first_sub, _ = self.frame_data[0]
            # Seek once to first frame and read
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, first_f_num)
            ret, frame = self.cap.read()
            if not ret:
                # Try a retry once
                logger.warning(f"Failed to read first frame {first_f_num}, retrying...")
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, first_f_num)
                ret, frame = self.cap.read()
            if not ret:
                raise RuntimeError(f"Failed to read first frame {first_f_num}")

            # Init trackers at first frame
            initials = self.keyframe_map.get(first_f_num, self.initial_annotations if not self.use_keyframes else [])
            trackers = []  # List of (tracker, label, last_bbox)
            first_frame_annos = []
            for anno in initials:
                bbox = tuple(map(int, anno['bbox']))
                tracker = self.OPENCV_TRACKERS[self.tracker_type]()
                tracker.init(frame, bbox)
                trackers.append((tracker, anno['label'], bbox))
                first_frame_annos.append({'bbox': list(bbox), 'label': anno['label'], 'confidence': 1.0})

            self.results[first_f_num] = first_frame_annos

            num_frames = len(self.frame_data)
            with tqdm(total=num_frames, desc="Tracking frames", unit="frame") as pbar:
                pbar.update(1)  # First frame done

                # Track the "current" frame index we've consumed from frame_data
                current_idx = 0  # we've consumed index 0
                for idx in range(1, num_frames):
                    f_num, f_ts, f_sub, _ = self.frame_data[idx]

                    # If contiguous, avoid seeking: read next frame
                    if idx == current_idx + 1:
                        ret, frame = self.cap.read()
                    else:
                        # Only seek when necessary (jumping)
                        self.cap.set(cv2.CAP_PROP_POS_FRAMES, f_num)
                        ret, frame = self.cap.read()

                    if not ret:
                        logger.warning(f"Failed to read frame {f_num} at idx {idx}; attempting one retry...")
                        # Retry once
                        self.cap.set(cv2.CAP_PROP_POS_FRAMES, f_num)
                        ret, frame = self.cap.read()
                        if not ret:
                            logger.error(f"Retry failed for frame {f_num}; breaking loop")
                            break

                    # update current_idx to match the frame we just consumed
                    current_idx = idx

                    # If keyframe, reset trackers
                    if self.use_keyframes and f_num in self.keyframe_map:
                        trackers = []
                        for anno in self.keyframe_map[f_num]:
                            bbox = tuple(map(int, anno['bbox']))
                            tracker = self.OPENCV_TRACKERS[self.tracker_type]()
                            tracker.init(frame, bbox)
                            trackers.append((tracker, anno['label'], bbox))

                    # Update trackers
                    frame_annos = []
                    for i, (tracker, label, last_bbox) in enumerate(trackers):
                        success, new_bbox = tracker.update(frame)
                        if success:
                            new_bbox = list(map(int, new_bbox))
                            new_bbox[0] = max(0, min(new_bbox[0], self.video_w - new_bbox[2]))
                            new_bbox[1] = max(0, min(new_bbox[1], self.video_h - new_bbox[3]))
                            new_bbox[2] = max(1, min(new_bbox[2], self.video_w - new_bbox[0]))
                            new_bbox[3] = max(1, min(new_bbox[3], self.video_h - new_bbox[1]))
                            confidence = 1.0
                            frame_annos.append({'bbox': new_bbox, 'label': label, 'confidence': confidence})
                            trackers[i] = (tracker, label, new_bbox)
                        else:
                            logger.warning(f"Tracker lost for {label} at frame {f_num}")

                    # Interpolation correction (if keyframes)
                    if self.use_keyframes and frame_annos:
                        keyframes_fn = sorted(self.keyframe_map.keys())
                        for i_k in range(len(keyframes_fn) - 1):
                            if keyframes_fn[i_k] <= f_num < keyframes_fn[i_k+1]:
                                factor = (f_num - keyframes_fn[i_k]) / (keyframes_fn[i_k+1] - keyframes_fn[i_k])
                                for j, anno in enumerate(frame_annos):
                                    try:
                                        prev_anno = self.keyframe_map[keyframes_fn[i_k]][j]
                                        next_anno = self.keyframe_map[keyframes_fn[i_k+1]][j]
                                        interp_bbox = self._interpolate_bbox(prev_anno['bbox'], next_anno['bbox'], factor)
                                        interp_bbox[0] = max(0, min(interp_bbox[0], self.video_w - interp_bbox[2]))
                                        interp_bbox[1] = max(0, min(interp_bbox[1], self.video_h - interp_bbox[3]))
                                        interp_bbox[2] = max(1, min(interp_bbox[2], self.video_w - interp_bbox[0]))
                                        interp_bbox[3] = max(1, min(interp_bbox[3], self.video_h - interp_bbox[1]))
                                        anno['bbox'] = interp_bbox
                                    except IndexError:
                                        logger.warning(f"Mismatched annotation count at fn {f_num}, skipping interpolation")
                                        continue

                    self.results[f_num] = frame_annos
                    self.progress = (idx + 1) / num_frames * 100
                    pbar.update(1)

            self.fill_missing_segments(self.results)
            self.average_multiples_of_30()
            if self.cap:
                self.cap.release()
            self.status = 'completed'
            logger.info(f"Tracking completed for {self.video_path}")
        except Exception as e:
            print(f"Tracking failed: {str(e)}")
            logger.error(f"Tracking failed: {e}")
            self.status = 'failed'
            self.progress = 0

class VFInterpolator(VFTrackerBase):
    """
    Pure interpolation tracker between annotated start and end frames (or multiple keyframes).
    Supports multiple annotations for single and multiple classes.
    """
    def __init__(self, project, video_path, start_frame, end_frame, initial_annotations, frame_step=1):
        super().__init__(project, video_path, start_frame, end_frame, initial_annotations, frame_step)
        self.keyframe_map = {}

    def _run_core(self):
        try:
            self.status = 'running'
            self.progress = 0
            print(f"Interpolating annotations in '{self.video_path}' from frame {self.start_frame} to {self.end_frame}...")

            self._get_frame_data()
            # Snap annotations to nearest frame_num (use d[0])
            self.initial_annotations.sort(key=lambda a: a.get('keyframe_frame', self.start_frame))
            for anno in self.initial_annotations:
                frame = int(anno.get('keyframe_frame', self.start_frame))
                snapped_data = min(self.frame_data, key=lambda d: abs(d[0] - frame), default=self.frame_data[0])
                snapped_fn = snapped_data[0]
                if abs(snapped_data[0] - frame) > 1:
                    logger.warning(f"No close match for keyframe_frame {frame}, using {snapped_data[0]}")
                    continue
                if snapped_fn not in self.keyframe_map:
                    self.keyframe_map[snapped_fn] = []
                self.keyframe_map[snapped_fn].append(anno)
            if len(self.keyframe_map) < 2:
                raise ValueError("For interpolation, at least 2 keyframes are required.")

            # Filter keyframes to those in frame_data
            keyframes_fn = [fn for fn in self.keyframe_map if fn in [d[0] for d in self.frame_data]]
            if len(keyframes_fn) < 2:
                raise ValueError("Insufficient keyframes in selected frames for interpolation")
            num_objects = len(self.keyframe_map[keyframes_fn[0]])
            for fn in keyframes_fn:
                if len(self.keyframe_map[fn]) != num_objects:
                    raise ValueError("All keyframes must have the same number of annotations.")

            # No need for capture in pure interpolation
            num_frames = len(self.frame_data)
            with tqdm(total=num_frames, desc="Interpolating frames", unit="frame") as pbar:
                for idx, (f_num, f_ts, f_sub, _) in enumerate(self.frame_data):
                    # Find prev/next keyframe indices
                    prev_idx = 0
                    for i in range(1, len(keyframes_fn)):
                        if f_num < keyframes_fn[i]:
                            prev_idx = i - 1
                            break
                    else:
                        prev_idx = len(keyframes_fn) - 1
                    prev_fn = keyframes_fn[prev_idx]
                    next_fn = keyframes_fn[prev_idx + 1] if prev_idx + 1 < len(keyframes_fn) else keyframes_fn[-1]
                    factor = 0 if prev_fn == next_fn else (f_num - prev_fn) / (next_fn - prev_fn)
                    frame_annos = []
                    for j in range(num_objects):
                        prev_anno = self.keyframe_map[prev_fn][j]
                        next_anno = self.keyframe_map[next_fn][j]
                        interp_bbox = self._interpolate_bbox(prev_anno['bbox'], next_anno['bbox'], factor)
                        interp_bbox[0] = max(0, min(interp_bbox[0], self.video_w - interp_bbox[2]))
                        interp_bbox[1] = max(0, min(interp_bbox[1], self.video_h - interp_bbox[3]))
                        interp_bbox[2] = max(1, min(interp_bbox[2], self.video_w - interp_bbox[0]))
                        interp_bbox[3] = max(1, min(interp_bbox[3], self.video_h - interp_bbox[1]))
                        confidence = 1.0
                        frame_annos.append({'bbox': interp_bbox, 'label': prev_anno['label'], 'confidence': confidence})
                    self.results[f_num] = frame_annos
                    self.progress = (idx + 1) / num_frames * 100
                    pbar.update(1)

            self.fill_missing_segments(self.results)
            self.average_multiples_of_30()
            self.status = 'completed'
            logger.info(f"Interpolation completed for {self.video_path}")
        except Exception as e:
            print(f"Interpolation failed: {str(e)}")
            logger.error(f"Interpolation failed: {e}")
            self.status = 'failed'
            self.progress = 0

def _extract_mask_from_result(res):
    """
    Robust extraction of a single binary mask (H,W) from various ultralytics SAM return shapes.
    Returns uint8 mask with 0/1 values or None.
    """
    if res is None:
        return None
    try:
        # ultralytics often returns a Results object; try common paths
        if hasattr(res, 'masks') and res.masks is not None:
            masks_obj = res.masks
            # Many versions: masks.data is torch tensor (N,H,W)
            if hasattr(masks_obj, 'data'):
                arr = masks_obj.data
                # choose first mask if multiple
                m = arr[0].cpu().numpy()
                return (m > 0).astype(np.uint8)
            # sometimes masks is already array-like
            arr = np.array(masks_obj)
            if arr.ndim == 3:
                m = arr[0]
                return (m > 0).astype(np.uint8)
        # sometimes the result is a list-like of Results
        if isinstance(res, (list, tuple)) and len(res) > 0:
            return _extract_mask_from_result(res[0])
    except Exception as e:
        logger.warning(f"Failed to parse SAM result masks: {e}")
    return None

def sample_pos_neg_from_mask(mask, n_pos=6, n_neg=12, neg_dilate=25):
    """
    mask: binary (H,W) uint8 or bool
    returns: points_list [[x,y],...], labels_list [1/0,...]
    Strategy:
      - sample up to n_pos points from mask interior (attempt spatial spread)
      - dilate mask by neg_dilate and take ring area as negative candidate; sample up to n_neg points
    """
    h, w = mask.shape
    ys, xs = np.where(mask > 0)
    pts = []
    lbls = []
    if len(xs) > 0:
        # attempt to evenly sample interior points
        if len(xs) <= n_pos:
            choose = np.arange(len(xs))
        else:
            choose = np.linspace(0, len(xs)-1, n_pos).astype(int)
        for idx in choose:
            pts.append([int(xs[idx]), int(ys[idx])])
            lbls.append(1)
    # negative area: dilated minus mask
    kernel = np.ones((neg_dilate, neg_dilate), np.uint8)
    dilated = cv2.dilate((mask > 0).astype(np.uint8), kernel, iterations=1)
    ring = (dilated > 0) & (mask == 0)
    nys, nxs = np.where(ring)
    if len(nxs) > 0:
        if len(nxs) <= n_neg:
            choose = np.arange(len(nxs))
        else:
            choose = np.linspace(0, len(nxs)-1, n_neg).astype(int)
        for idx in choose:
            pts.append([int(nxs[idx]), int(nys[idx])])
            lbls.append(0)
    return pts, lbls

def _centroid_from_polygon(segmentation):
    """
    segmentation: flat list [x0,y0,x1,y1,...]
    returns (cx,cy) as floats
    """
    pts = np.array(segmentation).reshape(-1,2)
    if pts.shape[0] == 0:
        return None
    # polygon centroid formula
    x = pts[:,0]
    y = pts[:,1]
    area = 0.5 * np.sum(x[:-1]*y[1:] - x[1:]*y[:-1]) if pts.shape[0] > 2 else 0
    if abs(area) < 1e-6:
        # fallback to mean
        return float(np.mean(x)), float(np.mean(y))
    factor = 1/(6*area)
    cx = factor * np.sum((x[:-1] + x[1:]) * (x[:-1]*y[1:] - x[1:]*y[:-1]))
    cy = factor * np.sum((y[:-1] + y[1:]) * (x[:-1]*y[1:] - x[1:]*y[:-1]))
    return float(cx), float(cy)

class VFAutoPropagator(VFTrackerBase):
    """
    Use SAM on the annotated frame to compute a mask per-annotation, sample positive
    points inside the mask and negative points in the surrounding ring, then pass
    these per-object prompts to SAM2VideoPredictor to propagate masks across frames.
    """
    def __init__(self, project, video_path, start_frame, end_frame, initial_annotations, frame_step=1,
                 output_type='bbox', sam_model='sam2.1_t.pt', device='cpu'):
        super().__init__(project, video_path, start_frame, end_frame, initial_annotations, frame_step, device=device)
        self.output_type = output_type
        self.sam_model = sam_model
        # build simple prompts list so we keep label order
        self.prompts = []
        for anno in self.initial_annotations:
            label = anno.get('label', 'object')
            if 'bbox' in anno:
                x,y,w,h = anno['bbox']
                self.prompts.append({'type':'bbox','data':[x, y, x+w, y+h],'label':label})
            elif 'segmentation' in anno:
                self.prompts.append({'type':'segmentation','data':anno['segmentation'],'label':label})
            elif 'points' in anno and anno['points']:
                # use first point if multiple provided
                self.prompts.append({'type':'point','data':anno['points'][0],'label':label})
            else:
                logger.warning(f"Skipping annotation without bbox/segmentation/points: {anno}")
        if not self.prompts:
            raise ValueError("No valid initial annotations found")

    def _run_core(self):
        try:
            self.status = 'running'
            self.progress = 0
            print(f"Preparing SAM-based propagation for '{self.video_path}' from frame {self.start_frame} to {self.end_frame}...")
            self._get_frame_data()
            if not self.frame_data:
                raise ValueError("No frames in range")
            first_f_num, first_ts, first_sub, _ = self.frame_data[0]  # use tuple shape

            # read annotated (first) frame
            cap = cv2.VideoCapture(self.video_path)
            cap.set(cv2.CAP_PROP_POS_FRAMES, first_f_num)
            ret, frame_bgr = cap.read()
            cap.release()
            if not ret:
                # retry once
                cap = cv2.VideoCapture(self.video_path)
                cap.set(cv2.CAP_PROP_POS_FRAMES, first_f_num)
                ret, frame_bgr = cap.read()
                cap.release()
            if not ret:
                raise RuntimeError("Failed to read annotated frame")

            # convert to RGB for ultralytics SAM
            frame_rgb = frame_bgr[:, :, ::-1]

            # ensure model file exists
            model_path = get_or_download_model(self.sam_model)

            sam_init = SAM(model_path)

            # For each prompt, compute a mask on the annotated frame and sample pos/neg points
            points_per_object = []
            labels_per_object = []
            object_labels = []  # label strings to preserve mapping

            for p in self.prompts:
                mask = None
                try:
                    if p['type'] == 'bbox':
                        # call SAM with bbox (xyxy)
                        res = sam_init(frame_rgb, bboxes=[p['data']], verbose=False, save=False)
                        mask = _extract_mask_from_result(res)
                    elif p['type'] == 'segmentation':
                        # compute centroid and call SAM with a point
                        centroid = _centroid_from_polygon(p['data'])
                        if centroid is None:
                            logger.warning("Could not compute centroid, skipping object")
                            continue
                        cx, cy = centroid
                        res = sam_init(frame_rgb, points=[[int(cx), int(cy)]], labels=[1], verbose=False, save=False)
                        mask = _extract_mask_from_result(res)
                    elif p['type'] == 'point':
                        px, py = p['data']
                        res = sam_init(frame_rgb, points=[[int(px), int(py)]], labels=[1], verbose=False, save=False)
                        mask = _extract_mask_from_result(res)
                except Exception as e:
                    logger.warning(f"SAM init inference failed for prompt {p}: {e}")
                    mask = None

                # fallbacks if SAM didn't return a mask
                if mask is None:
                    if p['type'] == 'bbox':
                        # create mask by filling bbox region
                        x1,y1,x2,y2 = map(int, p['data'])
                        mask = np.zeros((frame_rgb.shape[0], frame_rgb.shape[1]), dtype=np.uint8)
                        x2 = min(x2, mask.shape[1]-1)
                        y2 = min(y2, mask.shape[0]-1)
                        mask[y1:y2+1, x1:x2+1] = 1
                        logger.info("Using bbox-as-mask fallback")
                    elif p['type'] == 'segmentation':
                        # rasterize polygon
                        pts = np.array(p['data']).reshape(-1,2).astype(np.int32)
                        mask = np.zeros((frame_rgb.shape[0], frame_rgb.shape[1]), dtype=np.uint8)
                        if pts.shape[0] >= 3:
                            cv2.fillPoly(mask, [pts], 1)
                            logger.info("Using polygon-as-mask fallback")
                        else:
                            logger.warning("Invalid segmentation fallback; skipping object")
                            continue
                    elif p['type'] == 'point':
                        # small disk around point
                        px,py = int(p['data'][0]), int(p['data'][1])
                        mask = np.zeros((frame_rgb.shape[0], frame_rgb.shape[1]), dtype=np.uint8)
                        cv2.circle(mask, (px,py), radius=5, color=1, thickness=-1)
                        logger.info("Using point-disk fallback")

                # sample positive and negative points from mask
                pts, lbls = sample_pos_neg_from_mask(mask, n_pos=6, n_neg=12, neg_dilate=25)
                # ensure at least one positive
                if not any(l==1 for l in lbls):
                    ys, xs = np.where(mask > 0)
                    if len(xs) > 0:
                        cx = int(np.mean(xs)); cy = int(np.mean(ys))
                        pts.insert(0, [cx, cy]); lbls.insert(0, 1)
                    else:
                        # as last resort use centroid of bbox or provided point
                        if p['type'] == 'bbox':
                            x1,y1,x2,y2 = map(int, p['data'])
                            cx = (x1 + x2)//2; cy = (y1 + y2)//2
                            pts.insert(0, [cx, cy]); lbls.insert(0, 1)
                        elif p['type'] == 'point':
                            px,py = int(p['data'][0]), int(p['data'][1])
                            pts.insert(0, [px, py]); lbls.insert(0, 1)

                if not pts:
                    logger.warning(f"Could not create point prompt for object {p}; skipping")
                    continue

                points_per_object.append(pts)
                labels_per_object.append(lbls)
                object_labels.append(p['label'])

            # free single-image sam_init
            del sam_init

            if not points_per_object:
                raise RuntimeError("Failed to build any per-object point prompts from annotated frame")

            # Prepare temp video segment (extract exactly len(self.frame_data) frames)
            temp_video = os.path.join(TMP_FOLDER, f"temp_video_{int(time.time())}.mp4")
            os.makedirs(TMP_FOLDER, exist_ok=True)
            cap = cv2.VideoCapture(self.video_path)
            # We will use explicit per-frame seeks to robustly extract exact frames
            self.video_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            self.video_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            self.fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            out = cv2.VideoWriter(temp_video, fourcc, self.fps, (self.video_w, self.video_h))

            num_frames = len(self.frame_data)
            frame_count = 0
            while frame_count < num_frames:
                target_pos = first_f_num + frame_count
                # absolute seek per-frame (retry once on failure)
                cap.set(cv2.CAP_PROP_POS_FRAMES, target_pos)
                ret, frame = cap.read()
                if not ret:
                    logger.warning(f"Failed to read frame {target_pos}; retrying once...")
                    cap.set(cv2.CAP_PROP_POS_FRAMES, target_pos)
                    ret, frame = cap.read()
                    if not ret:
                        logger.error(f"Retry failed for frame {target_pos}; skipping this frame")
                        frame_count += 1
                        continue
                out.write(frame)
                frame_count += 1
            out.release()
            cap.release()
            if frame_count < num_frames:
                logger.warning(f"Only extracted {frame_count}/{num_frames} frames; video may be shorter than expected")
            if frame_count == 0:
                raise RuntimeError("No frames extracted for segment")

            # instantiate SAM2VideoPredictor with same model
            model_path = get_or_download_model(self.sam_model)
            overrides = dict(
                conf=0.25,
                task="segment",
                mode="predict",
                imgsz=640,
                model=model_path,
                save=False,
                verbose=False,
                device=self.device
            )
            predictor = SAM2VideoPredictor(overrides=overrides)

            # Prepare prompt args: ultralytics supports lists-of-lists for per-object points/labels
            prompt_args = {
                "points": points_per_object,
                "labels": labels_per_object
            }

            # run predictor (stream=True yields per-frame results)
            results = predictor(temp_video, **prompt_args, stream=True)
            results_dict = {}

            with tqdm(total=frame_count, desc="Propagating frames", unit="frame") as pbar:
                i = 0
                for res in results:
                    frame_num = first_f_num + i
                    if getattr(res, 'masks', None) is None:
                        # forward-fill previous frame if available
                        if i > 0 and (first_f_num + i - 1) in results_dict:
                            results_dict[frame_num] = copy.deepcopy(results_dict[first_f_num + i - 1])
                        self.progress = (i + 1) / frame_count * 100
                        pbar.update(1); i += 1
                        continue

                    # extract numpy masks robustly
                    try:
                        masks_obj = res.masks
                        if hasattr(masks_obj, 'data'):
                            masks = masks_obj.data.cpu().numpy()
                        else:
                            masks = np.array(masks_obj)
                    except Exception as e:
                        logger.warning(f"Unable to convert masks to numpy at frame {i}: {e}")
                        masks = None

                    if masks is None:
                        self.progress = (i + 1) / frame_count * 100
                        pbar.update(1); i += 1
                        continue

                    annos = []
                    # ensure masks axis 0 corresponds to objects; map to object_labels order
                    num_masks = masks.shape[0]
                    num_expected = len(object_labels)
                    num_use = min(num_masks, num_expected)
                    for j in range(num_use):
                        mask = (masks[j] > 0).astype(np.uint8)
                        label = object_labels[j]
                        confidence = 1.0
                        if self.output_type == 'mask':
                            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                            if contours:
                                cnt = max(contours, key=cv2.contourArea)
                                epsilon = 0.001 * cv2.arcLength(cnt, True)
                                approx = cv2.approxPolyDP(cnt, epsilon, True)
                                segmentation = approx.flatten().tolist()
                            else:
                                segmentation = []
                            annos.append({'segmentation': segmentation, 'label': label, 'confidence': confidence})
                        else:
                            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                            if contours:
                                cnt = max(contours, key=cv2.contourArea)
                                x,y,w,h = cv2.boundingRect(cnt)
                                x = max(0, min(x, self.video_w - w))
                                y = max(0, min(y, self.video_h - h))
                                w = max(1, min(w, self.video_w - x))
                                h = max(1, min(h, self.video_h - y))
                                annos.append({'bbox':[float(x), float(y), float(w), float(h)], 'label': label, 'confidence': confidence})
                            else:
                                logger.warning(f"No contour found for mask {j} at frame {i}")

                    if annos:
                        results_dict[frame_num] = annos

                    self.progress = (i + 1) / frame_count * 100
                    pbar.update(1); i += 1

            # optionally fill missing (only meaningful for bbox outputs)
            if self.output_type != 'mask':
                self.fill_missing_segments(results_dict)
            self.average_multiples_of_30()
            self.results = results_dict

            # cleanup
            if os.path.exists(temp_video):
                os.unlink(temp_video)
            self.status = 'completed'
            del predictor
            if self.device.startswith('cuda'):
                import torch
                torch.cuda.empty_cache()
            import gc
            gc.collect()
            logger.info(f"SAM2 propagation (prepared from annotated frame) completed for {self.video_path}")

        except Exception as e:
            print(f"SAM2 propagation failed: {e}")
            logger.error(f"SAM2 propagation failed: {e}")
            self.status = 'failed'
            self.progress = 0
            if 'temp_video' in locals() and os.path.exists(temp_video):
                os.unlink(temp_video)

class VFTracker:
    """
    API wrapper for object tracking across video frames.
    """
    def __init__(self, project, video_path, start_frame, end_frame, initial_annotations,
                 method='cv2', tracker_type='csrt', use_keyframes=False, frame_step=1,
                 output_type='bbox', sam_model='sam2.1_t.pt', device='cpu'):
        if method == 'cv2':
            self.impl = CV2Tracker(project, video_path, start_frame, end_frame, initial_annotations,
                                   tracker_type=tracker_type, use_keyframes=use_keyframes, frame_step=frame_step)
        elif method == 'interpolate':
            self.impl = VFInterpolator(project, video_path, start_frame, end_frame, initial_annotations,
                                       frame_step=frame_step)
        elif method == 'sam2':
            self.impl = VFAutoPropagator(project, video_path, start_frame, end_frame, initial_annotations,
                                         frame_step=frame_step, output_type=output_type, sam_model=sam_model, device=device)
        else:
            raise ValueError(f"Unsupported method: {method}. Options: 'cv2', 'interpolate', 'sam2'")

    def run(self):
        return self.impl.run()

    def run_threaded(self, callback=None):
        return self.impl.run_threaded(callback)

    def get_status(self):
        return self.impl.get_status()

    def push_to_db(self):
        return self.impl.push_to_db()