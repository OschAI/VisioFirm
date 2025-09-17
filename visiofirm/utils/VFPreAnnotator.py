import sqlite3
import torch
import numpy as np
import cv2
from PIL import Image
from ultralytics import YOLO, SAM
import json
import logging
import networkx as nx
import clip
import os
import gc
from tqdm import tqdm
from groundingdino.util.inference import load_model, predict
from groundingdino.datasets import transforms as T
from visiofirm.config import WEIGHTS_FOLDER
from visiofirm.utils.downloader import get_or_download_model

os.makedirs(WEIGHTS_FOLDER, exist_ok=True)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ImageProcessor:
    def __init__(
        self,
        model_type: str = "yolo",
        yolo_model_path: str = "yolov10x.pt",
        sam2_model_path: str = "sam2.1_t.pt",
        device: str = "cuda",
        box_threshold: float = 0.2,
        text_threshold: float = 0.3,
        segmentation_min_area: int = 100,
        sam2_autocast_dtype=torch.bfloat16,
        verbose: bool = False,
    ):
        self.device_str = device if torch.cuda.is_available() else "cpu"
        self.device = torch.device(self.device_str)
        self.model_type = model_type.lower()
        self.yolo_model_path = yolo_model_path
        self.sam2_model_path = sam2_model_path
        self.box_threshold = box_threshold
        self.text_threshold = text_threshold
        self.segmentation_min_area = segmentation_min_area
        self.sam2_autocast_dtype = sam2_autocast_dtype
        self.verbose = verbose
        self.clip_model, self.clip_preprocess = clip.load("ViT-B/32", device=self.device)

        if self.model_type == "clip":
            # Skip loading YOLO/DINO/SAM for classification
            return

        if self.model_type == "yolo":
            self.yolo_model_path = get_or_download_model(self.yolo_model_path)
            self.yolo_model = YOLO(model=self.yolo_model_path)
        elif self.model_type in ["grounding_dino_tiny", "grounding_dino_base"]:
            if self.model_type == "grounding_dino_tiny":
                config_path = os.path.join(os.path.dirname(__file__), 'GroundingDinoConfigs', 'GroundingDINO_SwinT_OGC.py')
                weight_filename = "groundingdino_swint_ogc.pth"
            else:  # grounding_dino_base
                config_path = os.path.join(os.path.dirname(__file__), 'GroundingDinoConfigs', 'GroundingDINO_SwinB_cfg.py')
                weight_filename = "groundingdino_swinb_cogcoor.pth"
            weight_path = get_or_download_model(weight_filename)
            self.dino_model = load_model(config_path, weight_path)
            self.dino_model = self.dino_model.to(self.device)
        else:
            raise ValueError(f"Invalid model_type: {model_type}. Choose 'yolo', 'grounding_dino_tiny', or 'grounding_dino_base'.")

        # Download and load SAM
        self.sam2_model_path = get_or_download_model(self.sam2_model_path)
        self.sam2_model = SAM(self.sam2_model_path)
        if self.verbose:
            self.sam2_model.info()

        # Load CLIP (moved outside the if, as it's always loaded)
        self.clip_model, self.clip_preprocess = clip.load("ViT-B/32", device=self.device)
    @staticmethod
    def _parse_classes(classes_str: str):
        raw_classes = [c.strip() for c in classes_str.replace(';', ',').split(',') if c.strip()]
        clean_classes = [c.replace("picture of ", "").replace("photo of ", "").strip() for c in raw_classes]
        clean_classes = [c for c in clean_classes if c]
        prompts = [f"{'an' if c[0].lower() in 'aeiou' else 'a'} {c}" for c in clean_classes]
        return prompts, clean_classes
    def _run_grounding_dino(self, image, class_list, box_threshold, text_threshold):
        batch_size = 10
        all_boxes = []
        all_scores = []
        all_labels = []
        transform = T.Compose(
            [
                T.RandomResize([800], max_size=1333),
                T.ToTensor(),
                T.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
            ]
        )
        image_transformed, _ = transform(image, None)
        width, height = image.size
        for i in range(0, len(class_list), batch_size):
            batch_classes = class_list[i:i + batch_size]
            caption = " . ".join(batch_classes) + " ."
            boxes_batch, logits_batch, phrases_batch = predict(
                model=self.dino_model,
                image=image_transformed,
                caption=caption,
                box_threshold=box_threshold,
                text_threshold=text_threshold,
                device=self.device_str
            )
            # Convert cxcywh normalized to xyxy absolute
            boxes_xyxy = torch.zeros_like(boxes_batch)
            boxes_xyxy[:, 0] = (boxes_batch[:, 0] - boxes_batch[:, 2] / 2) * width
            boxes_xyxy[:, 1] = (boxes_batch[:, 1] - boxes_batch[:, 3] / 2) * height
            boxes_xyxy[:, 2] = (boxes_batch[:, 0] + boxes_batch[:, 2] / 2) * width
            boxes_xyxy[:, 3] = (boxes_batch[:, 1] + boxes_batch[:, 3] / 2) * height
            all_boxes.append(boxes_xyxy)
            all_scores.append(logits_batch)
            all_labels.extend(phrases_batch)
        if all_boxes:
            combined_boxes = torch.cat(all_boxes, dim=0)
            combined_scores = torch.cat(all_scores, dim=0)
        else:
            combined_boxes = torch.empty((0, 4), device=self.device)
            combined_scores = torch.empty((0,), device=self.device)
        clean_labels = []
        clean_class_set = {c.replace("a ", "").replace("an ", "").strip().lower() for c in class_list}
        for label in all_labels:
            clean_label = label.replace("a ", "").replace("an ", "").replace("photo ", "").replace("picture ", "").strip().lower()
            matched_class = next((c for c in clean_class_set if clean_label in c or c in clean_label), clean_label)
            clean_labels.append(matched_class)
        valid_indices = [
            i for i, l in enumerate(clean_labels)
            if l and l not in ["a", "an", "photo", "picture"] and l in clean_class_set
        ]
        combined_boxes = combined_boxes[valid_indices]
        combined_scores = combined_scores[valid_indices]
        combined_labels = [clean_labels[i] for i in valid_indices]
        return {
            "boxes": combined_boxes,
            "scores": combined_scores,
            "labels": combined_labels
        }
    def _run_yolo(self, image, class_list, conf_threshold):
        clean_class_set = {c.replace("a ", "").replace("an ", "").strip().lower() for c in class_list}
        class_mapping = {}
        for user_class in class_list:
            user_class_clean = user_class.replace("a ", "").replace("an ", "").replace("photo of ", "").replace("picture of ", "").strip()
            class_mapping[user_class_clean.lower()] = user_class_clean
        if any(keyword in self.yolo_model_path.lower() for keyword in ['yolo5', 'yolov5', 'y5', 'v5']):
            results = self.yolo_model(image)
            boxes = []
            scores = []
            labels = []
            kept_idx = []
            for idx, box in enumerate(results.xyxy[0]):
                x1, y1, x2, y2, conf, cls = box
                if conf >= conf_threshold:
                    icls = int(cls)
                    if 0 <= icls < len(results.names):
                        class_name = results.names[icls]
                        if class_name.lower() in clean_class_set:
                            user_class_name = class_mapping.get(class_name.lower(), class_name)
                            boxes.append([x1.item(), y1.item(), x2.item(), y2.item()])
                            scores.append(conf.item())
                            labels.append(user_class_name)
                            kept_idx.append(idx)
                    else:
                        continue
            masks = None # TODO: Add masks support for YOLOv5 if needed
        else:
            results = self.yolo_model.predict(image, conf=conf_threshold, verbose=self.verbose, retina_masks=True)
            boxes = []
            scores = []
            labels = []
            kept_idx = []
            for idx, box in enumerate(results[0].boxes):
                x1, y1, x2, y2 = box.xyxy[0]
                conf = box.conf[0]
                cls = box.cls[0]
                icls = int(cls)
                if icls in results[0].names:
                    class_name = results[0].names[icls]
                    if class_name.lower() in clean_class_set:
                        user_class_name = class_mapping.get(class_name.lower(), class_name)
                        boxes.append([x1.item(), y1.item(), x2.item(), y2.item()])
                        scores.append(conf.item())
                        labels.append(user_class_name)
                        kept_idx.append(idx)
                else:
                    continue
            masks = results[0].masks.data.cpu().numpy().astype(np.float32) if results[0].masks is not None else None
            if masks is not None and len(kept_idx) > 0:
                masks = masks[kept_idx]
        return {
            "boxes": np.array(boxes, dtype=np.float32),
            "scores": np.array(scores, dtype=np.float32),
            "labels": labels,
            "masks": masks
        }
    def _run_sam2(self, image: Image.Image, boxes: np.ndarray) -> np.ndarray:
        if boxes.size == 0:
            return np.zeros((0, image.size[1], image.size[0]), dtype=np.float32)
        multi_bboxes = [[int(x1), int(y1), int(x2), int(y2)] for x1, y1, x2, y2 in boxes]
      
        with torch.inference_mode(), torch.autocast(self.device_str, dtype=self.sam2_autocast_dtype):
            results = self.sam2_model.predict(image, bboxes=multi_bboxes, device=self.device, verbose=self.verbose)
          
            if not results:
                return np.zeros((0, image.size[1], image.size[0]), dtype=np.float32)
          
            res = results[0]
            if res.masks is not None and len(res.masks.data) > 0:
                masks = res.masks.data.cpu().numpy().astype(np.float32)
            else:
                masks = np.zeros((len(multi_bboxes), image.size[1], image.size[0]), dtype=np.float32)
      
        return masks
    
    def get_best_label(self, image, candidate_labels):
        if self.clip_model is None or self.clip_preprocess is None:
            raise ValueError("CLIP model is not loaded; required for label verification.")
        prompts = [f"a photo of a {l}" for l in candidate_labels]
        image_input = self.clip_preprocess(image).unsqueeze(0).to(self.device)
        text_inputs = clip.tokenize(prompts).to(self.device)
        with torch.no_grad():
            image_features = self.clip_model.encode_image(image_input)
            text_features = self.clip_model.encode_text(text_inputs)
            similarities = (image_features @ text_features.T).softmax(dim=-1)[0]
        best_label_idx = similarities.argmax().item()
        return candidate_labels[best_label_idx], similarities[best_label_idx].item()
    
    def process_image(
        self,
        image: Image.Image,
        classes_str: str,
        mode: str = "BoundingBox",
        box_threshold: float = None,
        text_threshold: float = None
    ) -> dict:
        box_threshold = box_threshold or self.box_threshold
        text_threshold = text_threshold or self.text_threshold
        prompts, clean_labels = self._parse_classes(classes_str)
        if not prompts:
            raise ValueError("No valid class prompts found.")
        if mode == "Classification":
            prompts, clean_labels = self._parse_classes(classes_str)
            label, score = self.get_best_label(image, clean_labels)
            return {"labels": [label], "scores": [score]}
        if self.model_type in ["grounding_dino_tiny", "grounding_dino_base"]:
            result = self._run_grounding_dino(image, prompts, box_threshold, text_threshold)
            masks = None
        else:
            result = self._run_yolo(image, prompts, box_threshold)
            masks = result.get("masks", None)
        if isinstance(result["boxes"], torch.Tensor):
            result["boxes"] = result["boxes"].cpu().numpy()
        if isinstance(result["scores"], torch.Tensor):
            result["scores"] = result["scores"].cpu().numpy()
        boxes = result["boxes"]
        scores = result["scores"]
        labels = result["labels"]
        if self.model_type == "yolo":
            is_seg_model = masks is not None
            if mode == "Segmentation":
                if not is_seg_model:
                    masks = self._run_sam2(image, boxes)
            elif mode in ["BoundingBox", "OrientedBoundingBox"]:
                if is_seg_model:
                    valid_idx = []
                    new_boxes = []
                    for idx, mask in enumerate(masks):
                        mask_uint8 = (mask > 0).astype(np.uint8)
                        x, y, w, h = cv2.boundingRect(mask_uint8)
                        if w > 0 and h > 0:
                            valid_idx.append(idx)
                            new_boxes.append([x, y, x + w, y + h])
                    if valid_idx:
                        boxes = np.array(new_boxes, dtype=np.float32)
                        scores = scores[valid_idx]
                        labels = [labels[j] for j in valid_idx]
                masks = None
        if masks is not None:
            valid = []
            new_boxes = []
            new_masks = [] if mode == "Segmentation" else None
            for i, mask in enumerate(masks):
                mask_uint8 = (mask > 0).astype(np.uint8)
                x, y, w, h = cv2.boundingRect(mask_uint8)
                if w > 0 and h > 0:
                    valid.append(i)
                    new_boxes.append([x, y, x + w, y + h])
                    if mode == "Segmentation":
                        new_masks.append(mask)
            if valid:
                boxes = np.array(new_boxes, dtype=np.float32)
                scores = scores[valid]
                labels = [labels[i] for i in valid]
                if mode == "Segmentation":
                    masks = np.array(new_masks)
        if mode in ["BoundingBox", "OrientedBoundingBox"]:
            return {"boxes": boxes, "scores": scores, "labels": labels}
        elif mode == "Segmentation":
            if masks is None:
                masks = self._run_sam2(image, boxes)
            return {"boxes": boxes, "scores": scores, "labels": labels, "masks": masks}
        else:
            raise ValueError(f"Invalid mode: {mode}. Choose 'BoundingBox', 'OrientedBoundingBox', 'Segmentation', or 'Classification'.")
    def __call__(self, *args, **kwargs):
        return self.process_image(*args, **kwargs)
    
class PreAnnotator:
    def __init__(
        self,
        model_type: str = "yolo",
        yolo_model_path: str = "yolov10x.pt",
        sam2_model_path: str = "sam2.1_t.pt",
        device: str = "cuda",
        config_db_path: str = "config.db",
        box_threshold: float = 0.2,
        verbose: bool = False,
        progress_callback=None, # Callback for progress updates (float progress)
    ):
        # Validate model type
        valid_models = ["yolo", "grounding_dino_tiny", "grounding_dino_base", "clip"]
        if model_type not in valid_models:
            raise ValueError(f"Invalid model_type: {model_type}. Choose from {valid_models}.")
      
        self.model_type = model_type
        self.device = device
        self.config_db_path = config_db_path
        self.box_threshold = box_threshold
        self.verbose = verbose
        self.progress_callback = progress_callback
        # Database connection
        self.conn = sqlite3.connect(self.config_db_path)
        cursor = self.conn.cursor()
      
        # Verify database structure
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='Project_Configuration'")
        if not cursor.fetchone():
            raise ValueError("Project_Configuration table does not exist in the database.")
        cursor.execute("SELECT setup_type FROM Project_Configuration")
        result = cursor.fetchone()
        if not result:
            raise ValueError("No setup type found in Project_Configuration table.")
        self.setup_type = result[0]
        
        if self.setup_type == "Classification":
            self.model_type = "clip"
      
        # Load classes
        cursor.execute("SELECT class_name FROM Classes")
        self.classes = [str(row[0]) for row in cursor.fetchall()]
        if not self.classes:
            logger.warning("No classes found in Classes table. May lead to empty detections.")
        self.classes_str = ", ".join(self.classes)
      
        # Load images
        cursor.execute("SELECT image_id, absolute_path FROM Images")
        self.images = cursor.fetchall()
        if not self.images:
            raise ValueError("No images found in Images table.")
      
        # Initialize image processor
        self.image_processor = ImageProcessor(
            model_type=self.model_type,
            yolo_model_path=yolo_model_path,
            sam2_model_path=sam2_model_path,
            device=self.device,
            box_threshold=self.box_threshold,
            verbose=self.verbose
        )
    def _simplify_contour(self, contour, epsilon_factor=0.002):
        min_points_for_simplification = 15
        if len(contour) < 3:
            logger.debug(f"Contour has fewer than 3 points; skipping")
            return None
        flattened_original = contour.reshape(-1, 2).astype(float).flatten().tolist()
        if len(contour) <= min_points_for_simplification:
            return flattened_original
        perimeter = cv2.arcLength(contour, closed=True)
        epsilon = epsilon_factor * perimeter
        approx = cv2.approxPolyDP(contour, epsilon, closed=True)
        if len(approx) >= 3:
            flattened = approx.reshape(-1, 2).astype(float).flatten().tolist()
            return flattened
        else:
            logger.debug(f"Simplification resulted in fewer than 3 points; using original contour with {len(contour)} points")
            return flattened_original
    @staticmethod
    def compute_iou(box1, box2):
        x1 = max(box1[0], box2[0])
        y1 = max(box1[1], box2[1])
        x2 = min(box1[2], box2[2])
        y2 = min(box1[3], box2[3])
        intersection = max(0, x2 - x1) * max(0, y2 - y1)
        area1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
        area2 = (box2[2] - box2[0]) * (box2[3] - box2[1])
        union = area1 + area2 - intersection
        return intersection / union if union > 0 else 0
    def run_inferences(self):
        # Map setup type to mode
        setup_to_mode = {
            "Bounding Box": "BoundingBox",
            "Segmentation": "Segmentation",
            "Oriented Bounding Box": "BoundingBox",
            "Classification": "Classification"
        }
        mode = setup_to_mode.get(self.setup_type, "BoundingBox")
        cursor = self.conn.cursor()
        total_images = len(self.images)
        processed = 0
        skipped = 0
        # tqdm progress bar for visual terminal updates
        with tqdm(total=total_images, desc=f"Pre-annotating {self.model_type.upper()}", unit="img") as pbar:
            for image_id, image_path in self.images:
                try:
                    # Skip if already annotated
                    cursor.execute("""
                        SELECT EXISTS(
                            SELECT 1 FROM Preannotations WHERE image_id = ?
                        ) OR EXISTS(
                            SELECT 1 FROM Annotations WHERE image_id = ?
                        )
                    """, (image_id, image_id))
                    if cursor.fetchone()[0]:
                        logger.info(f"Skipping image {image_path} (image_id: {image_id}) as it already has preannotations or annotations.")
                        skipped += 1
                        current_progress = ((processed + skipped) / total_images) * 100
                        pbar.update(1)
                        pbar.set_postfix({
                            'processed': processed,
                            'skipped': skipped,
                            'progress': f"{current_progress:.1f}%"
                        })
                        if self.progress_callback:
                            self.progress_callback(current_progress)
                        continue
                    logger.info(f"Processing image: {image_path} (image_id: {image_id})")
                    image = Image.open(image_path).convert("RGB")
                  
                    # Process image
                    results = self.image_processor.process_image(
                        image=image,
                        classes_str=self.classes_str,
                        mode=mode,
                        box_threshold=self.box_threshold
                    )
                    num_detections = len(results["scores"]) if "scores" in results else len(results.get("labels", []))
                    #logger.info(f"Detected {num_detections} objects for image {image_path}")
                    # Map labels to original class names
                    class_lower_to_original = {cls.lower(): cls for cls in self.classes}
                    mapped_labels = []
                    for label in results["labels"]:
                        label_lower = label.lower()
                        mapped_labels.append(class_lower_to_original.get(label_lower, label))
                        if label_lower not in class_lower_to_original:
                            logger.warning(f"No matching class found for label '{label}' in {image_path}; using original label")
                    results["labels"] = mapped_labels
                    # Post-process annotations
                    if mode == "Classification":
                        if num_detections > 0:
                            label = results["labels"][0]
                            score = results["scores"][0]
                            cursor.execute(
                                "INSERT INTO Preannotations (image_id, type, class_name, x, y, width, height, rotation, segmentation, confidence) "
                                "VALUES (?, ?, ?, NULL, NULL, NULL, NULL, 0, NULL, ?)",
                                (image_id, 'classification', label, float(score))
                            )
                            inserted_count = 1
                        else:
                            inserted_count = 0
                        self.conn.commit()
                        #logger.info(f"Inserted {inserted_count} unique annotations for image {image_path}")
                        processed += 1
                        current_progress = ((processed + skipped) / total_images) * 100
                        pbar.update(1)
                        pbar.set_postfix({
                            'processed': processed,
                            'skipped': skipped,
                            'progress': f"{current_progress:.1f}%"
                        })
                        if self.progress_callback:
                            self.progress_callback(current_progress)
                        continue  # Skip to next image
                    elif mode in ["BoundingBox", "OrientedBoundingBox", "Segmentation"]:
                        boxes = results["boxes"]
                        scores = results["scores"]
                        labels = results["labels"]
                        masks = results.get("masks", [None] * len(boxes))
                        annotations = [
                            {"box": boxes[i], "score": scores[i], "label": labels[i], "mask": masks[i]}
                            for i in range(len(boxes))
                        ]
                        if self.model_type == "yolo":
                            # Cluster overlapping annotations
                            G = nx.Graph()
                            for i in range(len(annotations)):
                                for j in range(i + 1, len(annotations)):
                                    if self.compute_iou(annotations[i]["box"], annotations[j]["box"]) > 0.9:
                                        G.add_edge(i, j)
                            clusters = list(nx.connected_components(G))
                            # Include singletons
                            all_indices = set(range(len(annotations)))
                            cluster_indices = set.union(*clusters) if clusters else set()
                            singletons = all_indices - cluster_indices
                            clusters.extend([{i} for i in singletons])
                            # Process clusters
                            kept_annotations = []
                            for cluster in clusters:
                                cluster_annotations = [annotations[i] for i in cluster]
                                if len(cluster) == 1:
                                    kept_annotations.append(cluster_annotations[0])
                                else:
                                    unique_labels = list(set(anno["label"] for anno in cluster_annotations))
                                    if len(unique_labels) == 1:
                                        best_anno = max(cluster_annotations, key=lambda x: x["score"])
                                    else:
                                        cluster_boxes = [anno["box"] for anno in cluster_annotations]
                                        x1 = max(0, min(b[0] for b in cluster_boxes))
                                        y1 = max(0, min(b[1] for b in cluster_boxes))
                                        x2 = min(image.width, max(b[2] for b in cluster_boxes))
                                        y2 = min(image.height, max(b[3] for b in cluster_boxes))
                                        cropped_image = image.crop((x1, y1, x2, y2))
                                        best_label, _ = self.image_processor.get_best_label(cropped_image, unique_labels)
                                        candidates = [anno for anno in cluster_annotations if anno["label"] == best_label]
                                        best_anno = max(candidates, key=lambda x: x["score"])
                                    kept_annotations.append(best_anno)
                        else:
                            kept_annotations = annotations
                        # Insert annotations into database
                        inserted_count = 0
                        for anno in kept_annotations:
                            if mode in ["BoundingBox", "OrientedBoundingBox"]:
                                x, y, w, h = anno["box"][0], anno["box"][1], anno["box"][2] - anno["box"][0], anno["box"][3] - anno["box"][1]
                                if w > 0 and h > 0:
                                    cursor.execute(
                                        "INSERT INTO Preannotations (image_id, type, class_name, x, y, width, height, rotation, segmentation, confidence) "
                                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                                        (image_id, 'rect', anno["label"], float(x), float(y), float(w), float(h), 0.0, None, float(anno["score"]))
                                    )
                                    inserted_count += 1
                                else:
                                    logger.warning(f"Skipped invalid bounding box for {anno['label']} in {image_path}: w={w}, h={h}")
                            elif mode == "Segmentation":
                                if anno["mask"] is not None and anno["mask"].any():
                                    mask_uint8 = (anno["mask"] > 0).astype(np.uint8)
                                    # Adaptive hole filling
                                    max_iterations = 10
                                    kernel_size = 5
                                    mask_filled = mask_uint8.copy()
                                    for _ in range(max_iterations):
                                        kernel = np.ones((kernel_size, kernel_size), np.uint8)
                                        mask_filled_new = cv2.morphologyEx(mask_filled, cv2.MORPH_CLOSE, kernel)
                                        contours, hierarchy = cv2.findContours(
                                            mask_filled_new,
                                            cv2.RETR_CCOMP,
                                            cv2.CHAIN_APPROX_SIMPLE
                                        )
                                        has_large_holes = False
                                        if hierarchy is not None:
                                            for i in range(len(contours)):
                                                if hierarchy[0][i][3] != -1:
                                                    area = cv2.contourArea(contours[i])
                                                    if area > 100:
                                                        has_large_holes = True
                                                        break
                                        if not has_large_holes:
                                            mask_filled = mask_filled_new
                                            break
                                        mask_filled = mask_filled_new
                                        kernel_size += 2
                                    contours, _ = cv2.findContours(mask_filled, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                                    if contours:
                                        largest_contour = max(contours, key=cv2.contourArea)
                                        simplified = self._simplify_contour(largest_contour)
                                        if simplified:
                                            segmentation = json.dumps(simplified)
                                            cursor.execute(
                                                "INSERT INTO Preannotations (image_id, type, class_name, x, y, width, height, rotation, segmentation, confidence) "
                                                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                                                (image_id, 'polygon', anno["label"], None, None, None, None, 0.0, segmentation, float(anno["score"]))
                                            )
                                            inserted_count += 1
                                        else:
                                            logger.debug(f"Skipped invalid simplified contour for {anno['label']} in {image_path}")
                                    else:
                                        logger.debug(f"Skipped empty contours for {anno['label']} in {image_path}")
                                else:
                                    logger.debug(f"Skipped empty mask for {anno['label']} in {image_path}")
                        self.conn.commit()
                        logger.info(f"Inserted {inserted_count} unique annotations for image {image_path}")
                        processed += 1
                    # Update tqdm bar after successful processing
                    current_progress = ((processed + skipped) / total_images) * 100
                    pbar.update(1)
                    pbar.set_postfix({
                        'processed': processed,
                        'skipped': skipped,
                        'progress': f"{current_progress:.1f}%"
                    })
                    if self.progress_callback:
                        self.progress_callback(current_progress)
                except Exception as e:
                    logger.error(f"Error processing image {image_path}: {str(e)}")
                    skipped += 1 # Count errors as skipped for progress
                    current_progress = ((processed + skipped) / total_images) * 100
                    pbar.update(1)
                    pbar.set_postfix({
                        'processed': processed,
                        'skipped': skipped,
                        'progress': f"{current_progress:.1f}%"
                    })
                    if self.progress_callback:
                        self.progress_callback(current_progress)
                    continue
        if self.progress_callback:
            self.progress_callback(100.0)
        
        logger.info("Starting memory cleanup after preannotation...")
        del self.image_processor
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        gc.collect()
        logger.info("Memory cleanup completed.")
    def __del__(self):
        self.conn.close()