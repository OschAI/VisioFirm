import json
import os
import yaml
from rapidfuzz.distance import Levenshtein
from PIL import Image
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def is_valid_image(file_path):
    """Verify if the file is a valid image."""
    try:
        with Image.open(file_path) as img:
            img.verify()  # Verify image integrity
        return True
    except Exception as e:
        logger.error(f"Invalid image detected: {file_path}, error: {e}")
        return False

class CocoAnnotationParser:
    def __init__(self, coco_json_path):
        with open(coco_json_path, 'r') as f:
            self.coco_data = json.load(f)
        self.categories = {cat['id']: cat['name'] for cat in self.coco_data.get('categories', [])}
        self.images_dict = {img['id']: img['file_name'] for img in self.coco_data.get('images', [])}
        self.annotations_by_image = {}
        for anno in self.coco_data.get('annotations', []):
            image_id = anno['image_id']
            if image_id not in self.annotations_by_image:
                self.annotations_by_image[image_id] = []
            self.annotations_by_image[image_id].append(anno)
        logger.info(f"Initialized COCO parser for {coco_json_path}")

    def get_annotations_for_image(self, image_file_name):
        for img_id, file_name in self.images_dict.items():
            if file_name == image_file_name:
                if img_id in self.annotations_by_image:
                    annotations = [
                        {
                            'category_name': self.categories.get(anno['category_id'], 'unknown'),
                            'bbox': anno.get('bbox'),
                            'segmentation': anno.get('segmentation')
                        } for anno in self.annotations_by_image[img_id]
                    ]
                    #logger.info(f"Retrieved {len(annotations)} COCO annotations for {image_file_name}")
                    return annotations
                else:
                    logger.info(f"No COCO annotations found for {image_file_name}")
                    return []
        logger.info(f"Image {image_file_name} not found in COCO annotations")
        return []

class YoloAnnotationParser:
    def __init__(self, yaml_path, images_dir=None):
        with open(yaml_path, 'r') as f:
            self.yaml_data = yaml.safe_load(f)
        self.classes = self.yaml_data.get('names', [])
        self.images_dir = images_dir
        logger.info(f"Initialized YOLO parser for {yaml_path}" + (f" with images_dir={images_dir}" if images_dir else ""))

    def get_annotations_for_image(self, image_file_name):
        txt_base = os.path.splitext(image_file_name)[0] + '.txt'
        if self.images_dir:
            txt_file = os.path.join(self.images_dir, txt_base)
        else:
            # For existing project: Assumes txt in annotation dir; but since parse_and_add_annotations walks temp_dir, it can pass full txt paths if needed.
            # For simplicity: Return empty if no dir (handled in parse_and_add_annotations by checking existence)
            logger.warning(f"No images_dir provided for YOLO; cannot locate {txt_base} without path")
            return []
        
        if os.path.exists(txt_file):
            annotations = []
            with open(txt_file, 'r') as f:
                for line in f:
                    parts = line.strip().split()
                    if len(parts) < 5:
                        logger.warning(f"Invalid YOLO annotation line in {txt_file}: {line.strip()}")
                        continue
                    class_id = int(parts[0])
                    if 0 <= class_id < len(self.classes):
                        class_name = self.classes[class_id]
                        if len(parts) == 5:
                            x_center, y_center, w, h = map(float, parts[1:5])
                            annotations.append({
                                'category_name': class_name,
                                'bbox_norm': [x_center, y_center, w, h],
                                'obbox': None,
                                'segmentation': None
                            })
                        elif len(parts) == 9:
                            points = list(map(float, parts[1:9]))
                            annotations.append({
                                'category_name': class_name,
                                'bbox_norm': None,
                                'obbox': points,
                                'segmentation': None
                            })
                        elif len(parts) > 5 and (len(parts) - 1) % 2 == 0:
                            points = list(map(float, parts[1:]))
                            annotations.append({
                                'category_name': class_name,
                                'bbox_norm': None,
                                'obbox': None,
                                'segmentation': points
                            })
            #logger.info(f"Retrieved {len(annotations)} YOLO annotations for {image_file_name}")
            return annotations
        logger.info(f"No YOLO annotations found for {image_file_name}")
        return []

class NameMatcher:
    def __init__(self, project_classes, similarity_threshold=0.85):
        self.project_classes = [cls.strip() for cls in project_classes if cls.strip()]
        self.similarity_threshold = similarity_threshold
        logger.info(f"Initialized NameMatcher with {len(self.project_classes)} project classes")

    def match(self, annotation_class):
        if not annotation_class or not self.project_classes:
            logger.warning("No annotation class or project classes provided for matching")
            return None

        annotation_class = annotation_class.strip()
        best_match = None
        best_similarity = 0.0

        for project_class in self.project_classes:
            distance = Levenshtein.distance(annotation_class.lower(), project_class.lower())
            max_len = max(len(annotation_class), len(project_class))
            if max_len == 0:
                continue
            similarity = 1.0 - (distance / max_len)

            if similarity > best_similarity and similarity >= self.similarity_threshold:
                best_similarity = similarity
                best_match = project_class

        #logger.info(f"Matched '{annotation_class}' to '{best_match}' with similarity {best_similarity}")
        return best_match