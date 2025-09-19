# visiofirm/utils/downloader.py
import os
import requests
import logging
from pathlib import Path
from visiofirm.config import WEIGHTS_FOLDER

logger = logging.getLogger(__name__)

KNOWN_MODELS = {
    #### YOLO DETECTION
    # YOLOv5
    "yolov5nu.pt": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov5nu.pt",
    "yolov5su.pt": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov5su.pt",
    "yolov5mu.pt": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov5mu.pt",
    "yolov5lu.pt": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov5lu.pt",
    "yolov5xu.pt": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov5xu.pt",
    "yolov5n6u.pt": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov5n6u.pt",
    "yolov5s6u.pt": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov5s6u.pt",
    "yolov5m6u.pt": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov5m6u.pt",
    "yolov5l6u.pt": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov5l6u.pt",
    "yolov5x6u.pt": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov5x6u.pt",
    # YOLOv8
    "yolov8n.pt": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8n.pt",
    "yolov8s.pt": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8s.pt",
    "yolov8m.pt": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8m.pt",
    "yolov8l.pt": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8l.pt",
    "yolov8x.pt": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8x.pt",
    # YOLOv9
    "yolov9t.pt": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov9t.pt",
    "yolov9s.pt": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov9s.pt",
    "yolov9m.pt": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov9m.pt",
    "yolov9c.pt": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov9c.pt",
    "yolov9e.pt": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov9e.pt",
    # YOLOv10
    "yolov10n.pt": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov10n.pt",
    "yolov10s.pt": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov10s.pt",
    "yolov10m.pt": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov10m.pt",
    "yolov10b.pt": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov10b.pt",
    "yolov10l.pt": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov10l.pt",
    "yolov10x.pt": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov10x.pt",
    # YOLOv11
    "yolo11n.pt": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.pt",
    "yolo11s.pt": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11s.pt",
    "yolo11m.pt": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11m.pt",
    "yolo11l.pt": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11l.pt",
    "yolo11x.pt": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11x.pt",
    # YOLOv12
    "yolo12n.pt": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo12n.pt",
    "yolo12s.pt": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo12s.pt",
    "yolo12m.pt": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo12m.pt",
    "yolo12l.pt": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo12l.pt",
    "yolo12x.pt": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo12x.pt",

    #### YOLO SEGMENTATION
    "yolo8n-seg.pt": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo8n-seg.pt",
    "yolo8s-seg.pt": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo8s-seg.pt",
    "yolo8m-seg.pt": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo8m-seg.pt",
    "yolo8l-seg.pt": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo8l-seg.pt",
    "yolo8x-seg.pt": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo8x-seg.pt",

    "yolo11n-seg.pt": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n-seg.pt",
    "yolo11s-seg.pt": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11s-seg.pt",
    "yolo11m-seg.pt": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11m-seg.pt",
    "yolo11l-seg.pt": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11l-seg.pt",
    "yolo11x-seg.pt": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11x-seg.pt",

    "yolo12n-seg.pt": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo12n-seg.pt",
    "yolo12s-seg.pt": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo12s-seg.pt",
    "yolo12m-seg.pt": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo12m-seg.pt",
    "yolo12l-seg.pt": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo12l-seg.pt",
    "yolo12x-seg.pt": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo12x-seg.pt",

    # SAM2
    "sam2_t.pt": "https://github.com/ultralytics/assets/releases/download/v8.3.0/sam2_t.pt",
    "sam2_s.pt": "https://github.com/ultralytics/assets/releases/download/v8.3.0/sam2_s.pt",
    "sam2_b.pt": "https://github.com/ultralytics/assets/releases/download/v8.3.0/sam2_b.pt",
    "sam2_l.pt": "https://github.com/ultralytics/assets/releases/download/v8.3.0/sam2_l.pt",
    "sam2.1_t.pt": "https://github.com/ultralytics/assets/releases/download/v8.3.0/sam2.1_t.pt",
    "sam2.1_s.pt": "https://github.com/ultralytics/assets/releases/download/v8.3.0/sam2.1_s.pt",
    "sam2.1_b.pt": "https://github.com/ultralytics/assets/releases/download/v8.3.0/sam2.1_b.pt",
    "sam2.1_l.pt": "https://github.com/ultralytics/assets/releases/download/v8.3.0/sam2.1_l.pt",

    #### ZEROSHOT
    # Grounding DINO
    "groundingdino_swint_ogc.pth": "https://github.com/IDEA-Research/GroundingDINO/releases/download/v0.1.0-alpha/groundingdino_swint_ogc.pth",
    "groundingdino_swinb_cogcoor.pth": "https://github.com/IDEA-Research/GroundingDINO/releases/download/v0.1.0-alpha2/groundingdino_swinb_cogcoor.pth",

    "yolov8s-world.pt": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8x-world.pt",
    "yolov8m-world.pt": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8m-world.pt",
    "yolov8l-world.pt": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8l-world.pt",
    "yolov8x-world.pt": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8x-world.pt",

    "yolov8s-worldv2.pt": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8s-worldv2.pt",
    "yolov8m-worldv2.pt": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8m-worldv2.pt",
    "yolov8l-worldv2.pt": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8l-worldv2.pt",
    "yolov8x-worldv2.pt": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8x-worldv2.pt",
}

def get_or_download_model(model_name: str) -> str:
    """
    Retrieve the local path for a model, downloading it if necessary.
    
    Args:
        model_name (str): The filename of the model (e.g., 'yolov10x.pt').
    
    Returns:
        str: The absolute path to the model file.
    
    Raises:
        ValueError: If the model_name is unknown.
    """
    if model_name not in KNOWN_MODELS:
        raise ValueError(f"Unknown model: {model_name}. Add it to KNOWN_MODELS in downloader.py if needed.")
    
    path = Path(WEIGHTS_FOLDER) / model_name
    if path.exists():
        logger.info(f"Using existing model {model_name} at {path}")
        return str(path)
    
    url = KNOWN_MODELS[model_name]
    os.makedirs(WEIGHTS_FOLDER, exist_ok=True)
    logger.info(f"Downloading {model_name} from {url}...")
    response = requests.get(url, stream=True)
    response.raise_for_status()
    with open(path, 'wb') as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
    logger.info(f"Downloaded {model_name} to {path}")
    return str(path)