# visiofirm/utils/videoutils.py
import cv2
import logging

logger = logging.getLogger(__name__)

def get_video_metadata(video_path):
    try:
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return None
        fps = cap.get(cv2.CAP_PROP_FPS)
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = frame_count / fps if fps > 0 else 0
        cap.release()
        return {'fps': fps, 'frame_count': frame_count, 'duration': duration}
    except Exception as e:
        logger.error(f"Error getting metadata for {video_path}: {e}")
        return None