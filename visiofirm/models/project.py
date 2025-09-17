import sqlite3
import os
from PIL import Image
import json
import math
import logging
from visiofirm.utils import CocoAnnotationParser, YoloAnnotationParser, NameMatcher, is_valid_image
from visiofirm.config import VALID_IMAGE_EXTENSIONS
from tqdm import tqdm 

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Project:
    def __init__(self, name, description, setup_type, project_path):
        self.name = name
        self.description = description
        self.setup_type = setup_type
        self.db_path = os.path.join(project_path, 'config.db')
        self._initialize_db()
        self.setup_type = self.get_setup_type()
        self.videos_path = os.path.join(project_path, 'videos')

    def _initialize_db(self):
        """Initialize the SQLite database with required tables."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS Project_Configuration (
                    project_name TEXT PRIMARY KEY,
                    description TEXT,
                    setup_type TEXT NOT NULL,
                    creation_date DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS Classes (
                    class_name TEXT PRIMARY KEY
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS Images (
                    image_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    absolute_path TEXT UNIQUE,
                    width INTEGER,
                    height INTEGER
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS Annotations (
                    annotation_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    image_id INTEGER,
                    user_id INTEGER,
                    type TEXT NOT NULL,
                    class_name TEXT,
                    x REAL,
                    y REAL,
                    width REAL,
                    height REAL,
                    rotation REAL DEFAULT 0,
                    segmentation TEXT,
                    FOREIGN KEY (image_id) REFERENCES Images(image_id),
                    FOREIGN KEY (class_name) REFERENCES Classes(class_name)
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS Preannotations (
                    preannotation_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    image_id INTEGER,
                    type TEXT NOT NULL,
                    class_name TEXT,
                    x REAL,
                    y REAL,
                    width REAL,
                    height REAL,
                    rotation REAL DEFAULT 0,
                    segmentation TEXT,
                    confidence REAL NOT NULL,
                    FOREIGN KEY (image_id) REFERENCES Images(image_id),
                    FOREIGN KEY (class_name) REFERENCES Classes(class_name)
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS ReviewedImages (
                    image_id INTEGER PRIMARY KEY,
                    reviewed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    user_id INTEGER
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS Videos (
                    video_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    absolute_path TEXT UNIQUE,
                    name TEXT,
                    duration REAL,
                    fps REAL,
                    frame_count INTEGER,
                    width INTEGER,
                    height INTEGER
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS Frames (
                    frame_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    video_id INTEGER,
                    image_id INTEGER,
                    frame_number INTEGER,
                    subsampled BOOLEAN DEFAULT 0,
                    timestamp REAL,
                    FOREIGN KEY (video_id) REFERENCES Videos(video_id),
                    FOREIGN KEY (image_id) REFERENCES Images(image_id)
                )
            ''')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_frames_video_id ON Frames(video_id)')
            # Check if user_id column exists, and add it if not
            cursor.execute("PRAGMA table_info(ReviewedImages)")
            columns = [col[1] for col in cursor.fetchall()]
            if 'user_id' not in columns:
                cursor.execute('''
                    ALTER TABLE ReviewedImages ADD COLUMN user_id INTEGER
                ''')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_images_absolute_path ON Images(absolute_path)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_annotations_image_id ON Annotations(image_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_preannotations_image_id ON Preannotations(image_id)')
            cursor.execute('''
                INSERT OR IGNORE INTO Project_Configuration (project_name, description, setup_type)
                VALUES (?, ?, ?)
            ''', (self.name, self.description, self.setup_type))
            conn.commit()

    def add_classes(self, class_list):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            for cls in class_list:
                cursor.execute('INSERT OR IGNORE INTO Classes (class_name) VALUES (?)', (cls,))
            conn.commit()
            logger.info(f"Added {len(class_list)} classes to project {self.name}")

    def add_image(self, absolute_path):
        try:
            with Image.open(absolute_path) as img:
                img.verify()  # Verify image integrity
                img = Image.open(absolute_path)  # Reopen after verify
                width, height = img.size
        except Exception as e:
            logger.error(f"Skipping corrupted image {absolute_path}: {str(e)}")
            return None

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR IGNORE INTO Images (absolute_path, width, height)
                VALUES (?, ?, ?)
            ''', (absolute_path, width, height))
            conn.commit()
            cursor.execute('SELECT image_id FROM Images WHERE absolute_path = ?', (absolute_path,))
            result = cursor.fetchone()
            if result:
                logger.info(f"Added image to database: {absolute_path}, image_id: {result[0]}")
                return result[0]
            else:
                logger.error(f"Failed to add image to database: {absolute_path}")
                return None

    def get_images(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT image_id, absolute_path, width, height FROM Images')
            images = cursor.fetchall()
            logger.info(f"Retrieved {len(images)} images from database for project {self.name}")
            return images

    def get_images_with_status(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT i.absolute_path, 
                       EXISTS (
                           SELECT 1 FROM Annotations a WHERE a.image_id = i.image_id
                       ) as is_annotated
                FROM Images i
            ''')
            return cursor.fetchall()

    def get_classes(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT class_name FROM Classes')
            classes = [row[0] for row in cursor.fetchall()]
            logger.info(f"Retrieved {len(classes)} classes for project {self.name}: {classes}")
            return classes

    def get_setup_type(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT setup_type FROM Project_Configuration WHERE project_name = ?', (self.name,))
            result = cursor.fetchone()
            if result:
                return result[0]
            return None

    def add_images(self, absolute_paths):
        print(f"Adding {len(absolute_paths)} images to project '{self.name}'...") 
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            image_data = []
            with tqdm(total=len(absolute_paths), desc=f"Verifying/Adding images to {self.name}", unit="img") as pbar:
                for path in absolute_paths:
                    try:
                        with Image.open(path) as img:
                            img.verify()
                            img = Image.open(path)
                            width, height = img.size
                        image_data.append((path, width, height))
                        pbar.set_postfix({'valid': len(image_data)})
                    except Exception as e:
                        logger.error(f"Skipping corrupted image {path}: {str(e)}")
                    pbar.update(1)
            if image_data:
                cursor.executemany('''
                    INSERT OR IGNORE INTO Images (absolute_path, width, height)
                    VALUES (?, ?, ?)
                ''', image_data)
                conn.commit()
                added = len(image_data)
                logger.info(f"Added {added} images to database for project {self.name}")
                print(f"Added {added}/{len(absolute_paths)} valid images to '{self.name}'")  
            else:
                logger.warning(f"No valid images to add for project {self.name}")
                print(f"No valid images added to '{self.name}'")

    def add_video(self, absolute_path):
        try:
            import cv2
            cap = cv2.VideoCapture(absolute_path)
            if not cap.isOpened():
                logger.error(f"Cannot open video {absolute_path}")
                return None
            fps = cap.get(cv2.CAP_PROP_FPS)
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            duration = frame_count / fps if fps > 0 else 0
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            cap.release()
        except Exception as e:
            logger.error(f"Error getting video metadata for {absolute_path}: {str(e)}")
            return None

        name = os.path.basename(absolute_path)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR IGNORE INTO Videos (absolute_path, name, duration, fps, frame_count, width, height)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (absolute_path, name, duration, fps, frame_count, width, height))
            conn.commit()
            cursor.execute('SELECT video_id FROM Videos WHERE absolute_path = ?', (absolute_path,))
            result = cursor.fetchone()
            if result:
                logger.info(f"Added video to database: {absolute_path}, video_id: {result[0]}")
                return result[0]
            else:
                logger.error(f"Failed to add video to database: {absolute_path}")
                return None

    def add_selected_frames(self, video_id, target_fps=5):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT absolute_path, fps, frame_count, width, height FROM Videos WHERE video_id = ?', (video_id,))
            result = cursor.fetchone()
            if not result:
                logger.error(f"Video ID {video_id} not found")
                return 0
            absolute_path, fps, total_frames, width, height = result

        sampling = max(1, math.ceil(fps / target_fps)) if target_fps < fps else 1

        added = 0
        video_name = os.path.basename(absolute_path)
        image_data = []
        frame_numbers = []
        timestamps = []  

        with tqdm(total=total_frames, desc=f"Adding all frames for {video_name}", unit="frame") as pbar:
            for frame_num in range(total_frames):  # No 'step=sampling'
                timestamp = frame_num / fps  # Denormalized
                virtual_path = f"{absolute_path}#{frame_num}"
                image_data.append((virtual_path, width, height))
                frame_numbers.append(frame_num)
                timestamps.append(timestamp)
                pbar.update(1)

        if image_data:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.executemany('''
                    INSERT OR IGNORE INTO Images (absolute_path, width, height)
                    VALUES (?, ?, ?)
                ''', image_data)
                conn.commit()

                frame_data = []
                for i, virtual_path in enumerate([d[0] for d in image_data]):
                    cursor.execute('SELECT image_id FROM Images WHERE absolute_path = ?', (virtual_path,))
                    image_id = cursor.fetchone()[0]
                    cursor.execute('SELECT frame_id FROM Frames WHERE video_id = ? AND frame_number = ?', (video_id, frame_numbers[i]))
                    if not cursor.fetchone():
                        is_subsampled = (frame_numbers[i] % sampling == 0)
                        frame_data.append((video_id, image_id, frame_numbers[i], is_subsampled, timestamps[i]))

                if frame_data:
                    cursor.executemany('''
                        INSERT INTO Frames (video_id, image_id, frame_number, subsampled, timestamp)
                        VALUES (?, ?, ?, ?, ?)
                    ''', frame_data)
                    added = len(frame_data)

        logger.info(f"Selected and added {added} frame indices for video ID {video_id} at {target_fps} FPS")
        print(f"Added {added} frames (subsampled every {sampling}) for {video_name}")
        return added

    def get_videos(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT video_id, absolute_path, name, duration, fps, frame_count FROM Videos')
            videos = cursor.fetchall()
            logger.info(f"Retrieved {len(videos)} videos from database for project {self.name}")
            return videos
        
    def get_video_path(self, video_id):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT absolute_path FROM Videos WHERE video_id = ?', (video_id,))
            result = cursor.fetchone()
            if result:
                logger.info(f"Retrieved video path for ID {video_id} in project {self.name}: {result[0]}")
                return result[0]
            else:
                logger.error(f"Video ID {video_id} not found in project {self.name}")
                raise ValueError(f"Video ID {video_id} not found")
            
    def get_frames_for_video(self, video_id):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT f.frame_id, f.frame_number, f.subsampled
                FROM Frames f
                WHERE f.video_id = ?
                ORDER BY f.frame_number
            ''', (video_id,))
            frames = cursor.fetchall()
            return frames

    def save_frame_annotations(self, video_id, frame_number, annotations, user_id=None):
        """Save annotations for a specific video frame by transferring preannotations to annotations and clearing preannotations."""
        try:
            video_path = self.get_video_path(video_id)
            image_path = f"{video_path}#{frame_number}"
            self.save_annotations(image_path, annotations, user_id)
            logger.info(f"Saved annotations for frame {frame_number} in video {video_id} for project {self.name}")
            return True
        except Exception as e:
            logger.error(f"Failed to save annotations for frame {frame_number} in video {video_id}: {str(e)}")
            return False
    
    def save_annotations(self, image_path, annotations, user_id=None):
        #print(f"Saving annotations for image '{os.path.basename(image_path)}' in project '{self.name}'...")
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT image_id FROM Images WHERE absolute_path = ?', (image_path,))
            image_id = cursor.fetchone()
            if not image_id:
                logger.error(f"Image {image_path} not found in database for project {self.name}")
                print(f"Error: Image {image_path} not found in project '{self.name}'") 
                return
            image_id = image_id[0]

            cursor.execute('DELETE FROM Annotations WHERE image_id = ?', (image_id,))
            #logger.info(f"Deleted existing annotations for {image_path} in project {self.name}")

            saved_count = 0
            if self.setup_type == "Classification":
                # For classification, assume one annotation per image; take the first/only one
                if annotations:
                    anno = annotations[0]
                    class_name = anno.get('category_name') or anno.get('label')
                    if class_name:
                        cursor.execute('''
                            INSERT INTO Annotations (image_id, user_id, type, class_name)
                            VALUES (?, ?, ?, ?)
                        ''', (image_id, user_id, 'classification', class_name))
                        saved_count = 1
                    else:
                        logger.warning(f"No valid class_name for classification in {image_path}")
                else:
                    logger.info(f"No annotations provided for classification in {image_path}")
            else:
                unique_annotations = []
                seen = set()
                with tqdm(total=len(annotations), desc=f"Saving annotations for {os.path.basename(image_path)}", unit="anno", leave=False) as pbar:
                    for anno in annotations:
                        anno_type = anno.get('type', 'rect')
                        if self.setup_type == "Segmentation" and anno.get('segmentation'):
                            anno_type = 'polygon'
                        elif self.setup_type == "Oriented Bounding Box":
                            anno_type = 'obbox'

                        key = (anno_type, anno.get('category_name') or anno.get('label'))
                        if anno.get('bbox'):
                            bbox = tuple(round(float(coord), 4) for coord in anno['bbox'])
                            rotation = round(float(anno.get('rotation', 0)), 4)
                            key += bbox + (rotation,)
                        elif anno.get('segmentation'):
                            seg = anno['segmentation']
                            if isinstance(seg, list) and seg:
                                seg = seg[0] if isinstance(seg[0], list) else seg
                                sorted_seg = tuple(sorted(tuple(round(float(coord), 4) for coord in seg)))
                                key += sorted_seg

                        if key not in seen:
                            seen.add(key)
                            unique_annotations.append(anno)
                        pbar.update(1)

                with tqdm(total=len(unique_annotations), desc=f"Inserting annotations for {os.path.basename(image_path)}", unit="anno", leave=False) as pbar:
                    for anno in unique_annotations:
                        anno_type = anno.get('type', 'rect')
                        if self.setup_type == "Segmentation" and anno.get('segmentation'):
                            anno_type = 'polygon'
                        elif self.setup_type == "Oriented Bounding Box":
                            anno_type = 'obbox'

                        x = y = width = height = rotation = segmentation = None
                        if self.setup_type in ("Bounding Box", "Oriented Bounding Box"):
                            if anno.get('bbox'):
                                try:
                                    x, y, width, height = map(float, anno['bbox'])
                                    if width <= 0 or height <= 0:
                                        logger.warning(f"Invalid bbox dimensions for {anno.get('category_name')} in {image_path}: width={width}, height={height}")
                                        pbar.update(1)
                                        continue
                                    if self.setup_type == "Oriented Bounding Box":
                                        rotation = float(anno.get('rotation', 0))
                                except (ValueError, TypeError) as e:
                                    logger.warning(f"Invalid bbox format for {anno.get('category_name')} in {image_path}: {anno.get('bbox')}, error: {e}")
                                    pbar.update(1)
                                    continue
                            else:
                                logger.warning(f"No bbox provided for {anno.get('category_name')} in {image_path}: {anno}")
                                pbar.update(1)
                                continue
                        elif self.setup_type == "Segmentation" and anno.get('segmentation'):
                            seg = anno['segmentation']
                            if isinstance(seg, list) and seg:
                                seg = seg[0] if isinstance(seg[0], list) else seg
                                segmentation = json.dumps(seg)
                            else:
                                logger.warning(f"Skipping invalid segmentation for {anno.get('category_name')} in {image_path}")
                                pbar.update(1)
                                continue

                        if (self.setup_type in ("Bounding Box", "Oriented Bounding Box") and (x is None or y is None or width is None or height is None)) or \
                           (self.setup_type == "Segmentation" and segmentation is None):
                            logger.warning(f"Skipping invalid annotation for {anno.get('category_name')} in {image_path}: {anno}")
                            pbar.update(1)
                            continue

                        cursor.execute('''
                            INSERT INTO Annotations (image_id, user_id, type, class_name, x, y, width, height, rotation, segmentation)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (
                            image_id,
                            user_id,
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
                        pbar.update(1)
                        pbar.set_postfix({'saved': saved_count})

            cursor.execute('DELETE FROM Preannotations WHERE image_id = ?', (image_id,))
            #logger.info(f"Cleared preannotations for {image_path} after transfer to annotations")
            conn.commit()
            #print(f"Saved {saved_count}/{len(annotations)} annotations for '{os.path.basename(image_path)}' in project '{self.name}'")

    def get_annotations(self, image_path):
        print(f"Retrieving annotations for image '{os.path.basename(image_path)}' in project '{self.name}'...") 
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT image_id FROM Images WHERE absolute_path = ?', (image_path,))
            image_id = cursor.fetchone()
            if not image_id:
                logger.warning(f"No image_id found for path: {image_path} in project {self.name}")
                print(f"Error: Image {image_path} not found in project '{self.name}'") 
                return {'annotations': [], 'preannotations': []}
            image_id = image_id[0]

            if self.setup_type == "Classification":
                cursor.execute('''
                    SELECT annotation_id, image_id, class_name
                    FROM Annotations WHERE image_id = ?
                ''', (image_id,))
                annotations = []
                with tqdm(total=cursor.rowcount or 1, desc=f"Fetching annotations for {os.path.basename(image_path)}", unit="anno", leave=False) as pbar:
                    for row in cursor.fetchall():
                        anno = {
                            'annotation_id': row[0],
                            'image_id': row[1],
                            'type': 'classification',
                            'label': row[2]
                        }
                        annotations.append(anno)
                        pbar.update(1)

                cursor.execute('''
                    SELECT preannotation_id, image_id, class_name, confidence
                    FROM Preannotations WHERE image_id = ?
                ''', (image_id,))
                preannotations = []
                for row in cursor.fetchall():
                    preanno = {
                        'preannotation_id': row[0],
                        'image_id': row[1],
                        'type': 'classification',
                        'label': row[2],
                        'confidence': float(row[3]) if row[3] is not None else 0.0
                    }
                    preannotations.append(preanno)

                logger.info(f"Retrieved {len(annotations)} annotations and {len(preannotations)} preannotations for {image_path} in project {self.name}")
                print(f"Retrieved {len(annotations)} annotations for '{os.path.basename(image_path)}' in project '{self.name}'") 
                return {'annotations': annotations, 'preannotations': preannotations}
            else:
                cursor.execute('''
                    SELECT annotation_id, image_id, type, class_name, x, y, width, height, rotation, segmentation
                    FROM Annotations WHERE image_id = ?
                ''', (image_id,))
                annotations = []
                with tqdm(total=cursor.rowcount or 1, desc=f"Fetching annotations for {os.path.basename(image_path)}", unit="anno", leave=False) as pbar:
                    for row in cursor.fetchall():
                        anno = {
                            'annotation_id': row[0],
                            'image_id': row[1],
                            'type': 'obbox' if self.setup_type == "Oriented Bounding Box" else row[2],
                            'label': row[3]
                        }
                        if row[4] is not None and row[5] is not None and row[6] is not None and row[7] is not None:
                            anno['x'] = row[4]
                            anno['y'] = row[5]
                            anno['width'] = row[6]
                            anno['height'] = row[7]
                            anno['bbox'] = [row[4], row[5], row[6], row[7]]
                        if row[8] is not None:
                            anno['rotation'] = row[8]
                        else:
                            anno['rotation'] = 0
                        if row[9]:
                            try:
                                segmentation = json.loads(row[9])
                                if isinstance(segmentation, list):
                                    anno['segmentation'] = [segmentation]
                                    anno['points'] = [{'x': segmentation[i], 'y': segmentation[i+1]} for i in range(0, len(segmentation), 2)]
                                    anno['closed'] = True
                            except (json.JSONDecodeError, TypeError) as e:
                                logger.error(f"Error parsing segmentation for annotation_id {row[0]}: {e}")
                                anno['segmentation'] = []
                                anno['points'] = []
                        annotations.append(anno)
                        pbar.update(1)

                cursor.execute('''
                    SELECT preannotation_id, image_id, type, class_name, x, y, width, height, rotation, segmentation, confidence
                    FROM Preannotations WHERE image_id = ?
                ''', (image_id,))
                preannotations = []
                for row in cursor.fetchall():
                    preanno = {
                        'preannotation_id': row[0],
                        'image_id': row[1],
                        'type': 'obbox' if self.setup_type == "Oriented Bounding Box" else row[2],
                        'label': row[3],
                        'confidence': float(row[10]) if row[10] is not None else 0.0
                    }
                    if row[4] is not None and row[5] is not None and row[6] is not None and row[7] is not None:
                        preanno['x'] = row[4]
                        preanno['y'] = row[5]
                        preanno['width'] = row[6]
                        preanno['height'] = row[7]
                        preanno['bbox'] = [row[4], row[5], row[6], row[7]]
                    if row[8] is not None:
                        preanno['rotation'] = row[8]
                    else:
                        preanno['rotation'] = 0
                    if row[9]:
                        try:
                            segmentation = json.loads(row[9])
                            if isinstance(segmentation, list):
                                preanno['segmentation'] = [segmentation]
                                preanno['points'] = [{'x': segmentation[i], 'y': segmentation[i+1]} for i in range(0, len(segmentation), 2)]
                                preanno['closed'] = True
                        except (json.JSONDecodeError, TypeError) as e:
                            logger.error(f"Error parsing segmentation for preannotation_id {row[0]}: {e}")
                            preanno['segmentation'] = []
                            preanno['points'] = []
                    preannotations.append(preanno)

                logger.info(f"Retrieved {len(annotations)} annotations and {len(preannotations)} preannotations for {image_path} in project {self.name}")
                print(f"Retrieved {len(annotations)} annotations for '{os.path.basename(image_path)}' in project '{self.name}'") 
                return {'annotations': annotations, 'preannotations': preannotations}

    def get_video_annotations(self, video_id):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT f.frame_number, f.timestamp, f.image_id
                FROM Frames f
                WHERE f.video_id = ?
                ORDER BY f.frame_number
            ''', (video_id,))
            frames = cursor.fetchall()
            
            if not frames:
                logger.warning(f"No frames found for video_id {video_id}")
                return {}
            
            image_ids = [row[2] for row in frames]
            image_ids_tuple = tuple(image_ids)
            
            annotations_by_image = {iid: [] for iid in image_ids}
            if self.setup_type == "Classification":
                cursor.execute(f'''
                    SELECT annotation_id, image_id, class_name
                    FROM Annotations
                    WHERE image_id IN {image_ids_tuple}
                ''')
                for row in cursor.fetchall():
                    image_id = row[1]
                    anno = {
                        'annotation_id': row[0],
                        'image_id': image_id,
                        'type': 'classification',
                        'label': row[2]
                    }
                    annotations_by_image[image_id].append(anno)
            else:
                cursor.execute(f'''
                    SELECT annotation_id, image_id, type, class_name, x, y, width, height, rotation, segmentation
                    FROM Annotations
                    WHERE image_id IN {image_ids_tuple}
                ''')
                for row in cursor.fetchall():
                    image_id = row[1]
                    anno = {
                        'annotation_id': row[0],
                        'image_id': image_id,
                        'type': 'obbox' if self.setup_type == "Oriented Bounding Box" else row[2],
                        'label': row[3]
                    }
                    if row[4] is not None and row[5] is not None and row[6] is not None and row[7] is not None:
                        anno['x'] = row[4]
                        anno['y'] = row[5]
                        anno['width'] = row[6]
                        anno['height'] = row[7]
                        anno['bbox'] = [row[4], row[5], row[6], row[7]]
                    if row[8] is not None:
                        anno['rotation'] = row[8]
                    else:
                        anno['rotation'] = 0
                    if row[9]:
                        try:
                            segmentation = json.loads(row[9])
                            if isinstance(segmentation, list):
                                anno['segmentation'] = [segmentation]
                                anno['points'] = [{'x': segmentation[i], 'y': segmentation[i+1]} for i in range(0, len(segmentation), 2)]
                                anno['closed'] = True
                        except (json.JSONDecodeError, TypeError) as e:
                            logger.error(f"Error parsing segmentation for annotation_id {row[0]}: {e}")
                            anno['segmentation'] = []
                            anno['points'] = []
                    annotations_by_image[image_id].append(anno)
            
            # Get all preannotations
            preannotations_by_image = {iid: [] for iid in image_ids}
            if self.setup_type == "Classification":
                cursor.execute(f'''
                    SELECT preannotation_id, image_id, class_name, confidence
                    FROM Preannotations
                    WHERE image_id IN {image_ids_tuple}
                ''')
                for row in cursor.fetchall():
                    image_id = row[1]
                    preanno = {
                        'preannotation_id': row[0],
                        'image_id': image_id,
                        'type': 'classification',
                        'label': row[2],
                        'confidence': float(row[3]) if row[3] is not None else 0.0
                    }
                    preannotations_by_image[image_id].append(preanno)
            else:
                cursor.execute(f'''
                    SELECT preannotation_id, image_id, type, class_name, x, y, width, height, rotation, segmentation, confidence
                    FROM Preannotations
                    WHERE image_id IN {image_ids_tuple}
                ''')
                for row in cursor.fetchall():
                    image_id = row[1]
                    preanno = {
                        'preannotation_id': row[0],
                        'image_id': image_id,
                        'type': 'obbox' if self.setup_type == "Oriented Bounding Box" else row[2],
                        'label': row[3],
                        'confidence': float(row[10]) if row[10] is not None else 0.0
                    }
                    if row[4] is not None and row[5] is not None and row[6] is not None and row[7] is not None:
                        preanno['x'] = row[4]
                        preanno['y'] = row[5]
                        preanno['width'] = row[6]
                        preanno['height'] = row[7]
                        preanno['bbox'] = [row[4], row[5], row[6], row[7]]
                    if row[8] is not None:
                        preanno['rotation'] = row[8]
                    else:
                        preanno['rotation'] = 0
                    if row[9]:
                        try:
                            segmentation = json.loads(row[9])
                            if isinstance(segmentation, list):
                                preanno['segmentation'] = [segmentation]
                                preanno['points'] = [{'x': segmentation[i], 'y': segmentation[i+1]} for i in range(0, len(segmentation), 2)]
                                preanno['closed'] = True
                        except (json.JSONDecodeError, TypeError) as e:
                            logger.error(f"Error parsing segmentation for preannotation_id {row[0]}: {e}")
                            preanno['segmentation'] = []
                            preanno['points'] = []
                    preannotations_by_image[image_id].append(preanno)
            
            # Compile result keyed by frame_number
            result = {}
            for frame_number, ts, image_id in frames:
                result[frame_number] = {
                    'annotations': annotations_by_image.get(image_id, []),
                    'preannotations': preannotations_by_image.get(image_id, [])
                }
            logger.info(f"Retrieved annotations for {len(result)} frames in video {video_id} for project {self.name}")
        
        return result

    def parse_and_add_annotations(self, temp_upload_dir, image_paths, matcher=None):
        if self.setup_type == "Classification":
            logger.info(f"Skipping annotation parsing for classification project {self.name}")
            print(f"Skipping annotation parsing for classification project '{self.name}'")
            return  # No support for imported annotations in classification for now

        print(f"Parsing annotations for {len(image_paths)} images in project '{self.name}'...")
        name_matcher = matcher or NameMatcher(self.get_classes())
        if not image_paths:
            existing_images = self.get_images()
            image_paths = [img[1] for img in existing_images]
            logger.info(f"No new images; using {len(image_paths)} existing images for annotation matching")
            print(f"No new images; using {len(image_paths)} existing images for annotation matching")
        image_basenames = [os.path.basename(path) for path in image_paths]
        annotation_files = []
        for root, _, files in os.walk(temp_upload_dir):
            for file in files:
                if file.lower().endswith(('.json', '.yaml', '.yml', '.txt')):
                    annotation_files.append(os.path.join(root, file))
        logger.info(f"Found {len(annotation_files)} annotation files in {temp_upload_dir}: {[os.path.basename(f) for f in annotation_files]}")
        print(f"Found {len(annotation_files)} annotation files for project '{self.name}'")
        if not annotation_files:
            logger.info("No annotation files found; skipping parsing")
            print("No annotation files; skipping parsing")
            return

        json_paths = [p for p in annotation_files if p.lower().endswith('.json')]
        yaml_paths = [p for p in annotation_files if p.lower().endswith(('.yaml', '.yml'))]
        txt_paths = [p for p in annotation_files if p.lower().endswith('.txt')]

        for anno_path in json_paths:
            try:
                parser = CocoAnnotationParser(anno_path)
                matched_count = 0
                # Progress bar for images
                with tqdm(total=len(image_basenames), desc=f"Processing images for {os.path.basename(anno_path)}", unit="image") as pbar:
                    for image_file in image_basenames:
                        annotations = parser.get_annotations_for_image(image_file)
                        if annotations:
                            absolute_image_path = next(
                                (path for path in image_paths if os.path.basename(path).lower() == image_file.lower()), None
                            )
                            if absolute_image_path:
                                normalized_annotations = []
                                for anno in annotations:
                                    matched_class = name_matcher.match(anno.get('category_name', ''))
                                    if matched_class:
                                        normalized_anno = {'category_name': matched_class, 'rotation': 0}
                                        if self.setup_type in ("Bounding Box", "Oriented Bounding Box"):
                                            if anno.get('bbox') and len(anno['bbox']) == 4:
                                                normalized_anno['bbox'] = anno['bbox']
                                            else:
                                                continue
                                        elif self.setup_type == "Segmentation":
                                            if anno.get('segmentation'):
                                                normalized_anno['segmentation'] = anno['segmentation']
                                            else:
                                                continue
                                        normalized_annotations.append(normalized_anno)
                                if normalized_annotations:
                                    self.save_annotations(absolute_image_path, normalized_annotations)
                                    matched_count += 1
                        pbar.update(1)
                pbar.set_postfix({'matched': matched_count})
            except Exception as e:
                logger.error(f"Error parsing COCO file {os.path.basename(anno_path)}: {e}")
                print(f"Error parsing COCO file {os.path.basename(anno_path)}: {str(e)}")

        if yaml_paths:
            yaml_path = yaml_paths[0]
            try:
                yolo_parser = YoloAnnotationParser(yaml_path, temp_upload_dir)
                matched_count = 0
                # Progress bar for images
                with tqdm(total=len(image_basenames), desc=f"Processing images for {os.path.basename(yaml_path)}", unit="image") as pbar:
                    for image_file in image_basenames:
                        annotations = yolo_parser.get_annotations_for_image(image_file)
                        if annotations:
                            absolute_image_path = next(
                                (path for path in image_paths if os.path.basename(path).lower() == image_file.lower()), None
                            )
                            if absolute_image_path:
                                with sqlite3.connect(self.db_path) as conn:
                                    cursor = conn.cursor()
                                    cursor.execute('SELECT width, height FROM Images WHERE absolute_path = ?', (absolute_image_path,))
                                    result = cursor.fetchone()
                                    if result:
                                        img_width, img_height = result
                                        normalized_annotations = []
                                        for anno in annotations:
                                            matched_class = name_matcher.match(anno.get('category_name', ''))
                                            if matched_class:
                                                normalized_anno = {'category_name': matched_class, 'rotation': 0}
                                                if self.setup_type == "Bounding Box":
                                                    if anno.get('bbox_norm') and len(anno['bbox_norm']) == 4:
                                                        x_center, y_center, w, h = anno['bbox_norm']
                                                        normalized_anno['bbox'] = [
                                                            (x_center - w / 2) * img_width,
                                                            (y_center - h / 2) * img_height,
                                                            w * img_width,
                                                            h * img_height
                                                        ]
                                                elif self.setup_type == "Oriented Bounding Box":
                                                    if anno.get('obbox') and len(anno['obbox']) == 8:
                                                        x1, y1, x2, y2, x3, y3, x4, y4 = anno['obbox']
                                                        min_x = min(x1, x2, x3, x4) * img_width
                                                        max_x = max(x1, x2, x3, x4) * img_width
                                                        min_y = min(y1, y2, y3, y4) * img_height
                                                        max_y = max(y1, y2, y3, y4) * img_height
                                                        width = max_x - min_x
                                                        height = max_y - min_y
                                                        dx = (x2 - x1) * img_width
                                                        dy = (y2 - y1) * img_height
                                                        rotation = math.degrees(math.atan2(dy, dx))
                                                        normalized_anno['bbox'] = [min_x, min_y, width, height]
                                                        normalized_anno['rotation'] = rotation
                                                elif self.setup_type == "Segmentation":
                                                    if anno.get('segmentation'):
                                                        points = anno['segmentation']
                                                        denormalized_points = []
                                                        for i in range(0, len(points), 2):
                                                            x = points[i] * img_width
                                                            y = points[i + 1] * img_height
                                                            denormalized_points.extend([x, y])
                                                        normalized_anno['segmentation'] = denormalized_points
                                                if 'bbox' in normalized_anno or 'segmentation' in normalized_anno:
                                                    normalized_annotations.append(normalized_anno)
                                        if normalized_annotations:
                                            self.save_annotations(absolute_image_path, normalized_annotations, None)
                                            matched_count += 1
                                    else:
                                        logger.error(f"No image dimensions found for {absolute_image_path}")
                                        print(f"Error: No image dimensions for {absolute_image_path}")
                        pbar.update(1)
                pbar.set_postfix({'matched': matched_count})
            except Exception as e:
                logger.error(f"Error initializing YOLO parser with {os.path.basename(yaml_path)}: {e}")
                print(f"Error parsing YOLO file {os.path.basename(yaml_path)}: {str(e)}")

        for txt_path in txt_paths:
            try:
                txt_file = os.path.basename(txt_path)
                img_file_base = os.path.splitext(txt_file)[0]
                abs_img_path = None
                for ext in VALID_IMAGE_EXTENSIONS:
                    img_file = img_file_base + ext
                    candidate = next(
                        (path for path in image_paths if os.path.basename(path).lower() == img_file.lower()), None
                    )
                    if candidate:
                        abs_img_path = candidate
                        break
                if abs_img_path:
                    with open(txt_path, 'r') as f:
                        lines = f.readlines()
                    with sqlite3.connect(self.db_path) as conn:
                        cursor = conn.cursor()
                        cursor.execute('SELECT width, height FROM Images WHERE absolute_path = ?', (abs_img_path,))
                        result = cursor.fetchone()
                        if result:
                            img_width, img_height = result
                            project_classes = self.get_classes()
                            normalized_annotations = []
                            for line in lines:
                                parts = line.strip().split()
                                if len(parts) >= 5:
                                    class_id = int(parts[0])
                                    if 0 <= class_id < len(project_classes):
                                        class_name = project_classes[class_id]
                                        if self.setup_type == "Bounding Box" and len(parts) == 5:
                                            x_center, y_center, w, h = map(float, parts[1:5])
                                            bbox = [
                                                (x_center - w / 2) * img_width,
                                                (y_center - h / 2) * img_height,
                                                w * img_width,
                                                h * img_height
                                            ]
                                            normalized_annotations.append({
                                                'category_name': class_name,
                                                'bbox': bbox,
                                                'rotation': 0
                                            })
                                        elif self.setup_type == "Oriented Bounding Box" and len(parts) == 9:
                                            points = list(map(float, parts[1:9]))
                                            min_x = min(points[0::2]) * img_width
                                            max_x = max(points[0::2]) * img_width
                                            min_y = min(points[1::2]) * img_height
                                            max_y = max(points[1::2]) * img_height
                                            width = max_x - min_x
                                            height = max_y - min_y
                                            dx = (points[2] - points[0]) * img_width
                                            dy = (points[3] - points[1]) * img_height
                                            rotation = math.degrees(math.atan2(dy, dx))
                                            normalized_annotations.append({
                                                'category_name': class_name,
                                                'bbox': [min_x, min_y, width, height],
                                                'rotation': rotation
                                            })
                                        elif self.setup_type == "Segmentation" and len(parts) > 5 and (len(parts) - 1) % 2 == 0:
                                            points = list(map(float, parts[1:]))
                                            denormalized_points = []
                                            for i in range(0, len(points), 2):
                                                denormalized_points.extend([points[i] * img_width, points[i + 1] * img_height])
                                            normalized_annotations.append({
                                                'category_name': class_name,
                                                'segmentation': denormalized_points
                                            })
                            if normalized_annotations:
                                self.save_annotations(abs_img_path, normalized_annotations)
            except Exception as e:
                logger.error(f"Error parsing standalone TXT file {os.path.basename(txt_path)}: {e}")
                print(f"Error parsing TXT file {os.path.basename(txt_path)}: {str(e)}")

        logger.info(f"Annotation parsing completed for {len(image_paths)} images")
        print(f"Annotation parsing completed for '{self.name}': processed {len(image_paths)} images")

    def get_image_count(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM Images')
            count = cursor.fetchone()[0]
            logger.info(f"Image count for project {self.name}: {count}")
            return count

    def get_annotated_image_count(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(DISTINCT image_id) FROM Annotations')
            count = cursor.fetchone()[0]
            logger.info(f"Annotated image count for project {self.name}: {count}")
            return count

    def get_class_distribution(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT class_name, COUNT(*) FROM Annotations GROUP BY class_name')
            distribution = dict(cursor.fetchall())
            logger.info(f"Class distribution for project {self.name}: {distribution}")
            return distribution

    def get_annotations_per_image(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT COUNT(a.annotation_id)
                FROM Images i
                LEFT JOIN Annotations a ON i.image_id = a.image_id
                GROUP BY i.image_id
            ''')
            counts = [row[0] for row in cursor.fetchall()]
            return counts
    
    def commit_preannotations_for_video(self, video_id, user_id):
        """Transfer all preannotations for a video to annotations, then clear preannotations for the video."""
        try:
            # Get all image_ids for the video
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT DISTINCT f.image_id
                    FROM Frames f
                    WHERE f.video_id = ?
                ''', (video_id,))
                image_ids = [row[0] for row in cursor.fetchall()]

            transferred = 0
            for image_id in image_ids:
                # Get preannotations for this image
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        SELECT type, class_name, x, y, width, height, rotation, segmentation, confidence
                        FROM Preannotations
                        WHERE image_id = ?
                    ''', (image_id,))
                    pre_rows = cursor.fetchall()
                    if not pre_rows:
                        continue
                    # Insert as annotations (ignore confidence)
                    for row in pre_rows:
                        type_, class_name, x, y, width, height, rotation, segmentation, _ = row
                        cursor.execute('''
                            INSERT INTO Annotations (image_id, user_id, type, class_name, x, y, width, height, rotation, segmentation)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (image_id, user_id, type_, class_name, x, y, width, height, rotation, segmentation))
                    transferred += len(pre_rows)
                    # Clear pre for this image
                    cursor.execute('DELETE FROM Preannotations WHERE image_id = ?', (image_id,))
                    conn.commit()
            logger.info(f"Transferred {transferred} preannotations to annotations for video {video_id} in project {self.name}")
            return {'success': True, 'transferred': transferred}
        except Exception as e:
            logger.error(f"Failed to commit preannotations for video {video_id}: {str(e)}")
            return {'success': False, 'error': str(e)}
        
    def delete_annotations(self, image_path=None, user_id=None, video_id=None, start_frame=None, end_frame=None, unmark_reviewed=True):
        """Delete annotations for specific image/user/video range or all."""
        print(f"Deleting annotations for project '{self.name}' {'(image: ' + image_path + ')' if image_path else ''}{' (user: ' + str(user_id) + ')' if user_id else ''}{' (video: ' + str(video_id) + ', frames ' + str(start_frame) + '-' + str(end_frame) + ')' if video_id and start_frame is not None and end_frame is not None else ''}...")
        annotations_deleted = 0
        reviewed_deleted = 0
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            target_image_ids = set()
            if image_path:
                cursor.execute('SELECT image_id FROM Images WHERE absolute_path = ?', (image_path,))
                image_result = cursor.fetchone()
                if image_result:
                    target_image_ids.add(image_result[0])
                else:
                    logger.warning(f"Image {image_path} not found")
                    print(f"Error: Image {image_path} not found in project '{self.name}'") 
                    return {'annotations_deleted': 0, 'reviewed_deleted': 0}
            elif video_id and start_frame is not None and end_frame is not None:
                # Get image_ids for frames in range
                cursor.execute('''
                    SELECT DISTINCT f.image_id
                    FROM Frames f
                    WHERE f.video_id = ? AND f.frame_number >= ? AND f.frame_number <= ?
                ''', (video_id, start_frame, end_frame))
                for row in cursor.fetchall():
                    target_image_ids.add(row[0])
            elif video_id:
                # Delete all for video if no range specified
                cursor.execute('''
                    SELECT DISTINCT f.image_id
                    FROM Frames f
                    WHERE f.video_id = ?
                ''', (video_id,))
                for row in cursor.fetchall():
                    target_image_ids.add(row[0])

            if target_image_ids:
                image_ids_tuple = tuple(target_image_ids)
                if user_id:
                    cursor.execute('DELETE FROM Annotations WHERE image_id IN {t} AND user_id = ?'.format(t=image_ids_tuple), (user_id,))
                else:
                    cursor.execute('DELETE FROM Annotations WHERE image_id IN {t}'.format(t=image_ids_tuple))
                annotations_deleted = cursor.rowcount
                if unmark_reviewed:
                    cursor.execute('DELETE FROM ReviewedImages WHERE image_id IN {t}'.format(t=image_ids_tuple))
                    reviewed_deleted = cursor.rowcount
            elif user_id:
                cursor.execute('DELETE FROM Annotations WHERE user_id = ?', (user_id,))
                annotations_deleted = cursor.rowcount
                if unmark_reviewed:
                    cursor.execute('DELETE FROM ReviewedImages WHERE user_id = ?', (user_id,))
                    reviewed_deleted = cursor.rowcount
            else:
                cursor.execute('DELETE FROM Annotations')
                annotations_deleted = cursor.rowcount
                if unmark_reviewed:
                    cursor.execute('DELETE FROM ReviewedImages')
                    reviewed_deleted = cursor.rowcount
            conn.commit()
            logger.info(f"Deleted {annotations_deleted} annotations and {reviewed_deleted} reviews for project {self.name}{' (image: ' + image_path + ')' if image_path else ''}{' (user: ' + str(user_id) + ')' if user_id else ''}{' (video: ' + str(video_id) + ', frames ' + str(start_frame) + '-' + str(end_frame) + ')' if video_id and start_frame is not None and end_frame is not None else ''}")
            print(f"Deleted {annotations_deleted} annotations and {reviewed_deleted} reviews from '{self.name}'") 
            return {'annotations_deleted': annotations_deleted, 'reviewed_deleted': reviewed_deleted}

    def delete_preannotations(self, image_path=None, video_id=None, start_frame=None, end_frame=None):
        """Delete preannotations for specific image/video range or all."""
        print(f"Deleting preannotations for project '{self.name}' {'(image: ' + image_path + ')' if image_path else ''}{' (video: ' + str(video_id) + ', frames ' + str(start_frame) + '-' + str(end_frame) + ')' if video_id and start_frame is not None and end_frame is not None else ''}...")
        deleted = 0
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            target_image_ids = set()
            if image_path:
                cursor.execute('SELECT image_id FROM Images WHERE absolute_path = ?', (image_path,))
                image_result = cursor.fetchone()
                if image_result:
                    target_image_ids.add(image_result[0])
                else:
                    logger.warning(f"Image {image_path} not found")
                    print(f"Error: Image {image_path} not found in project '{self.name}'") 
                    return 0
            elif video_id and start_frame is not None and end_frame is not None:
                # Get image_ids for frames in range
                cursor.execute('''
                    SELECT DISTINCT f.image_id
                    FROM Frames f
                    WHERE f.video_id = ? AND f.frame_number >= ? AND f.frame_number <= ?
                ''', (video_id, start_frame, end_frame))
                for row in cursor.fetchall():
                    target_image_ids.add(row[0])
            elif video_id:
                # Delete all for video if no range specified
                cursor.execute('''
                    SELECT DISTINCT f.image_id
                    FROM Frames f
                    WHERE f.video_id = ?
                ''', (video_id,))
                for row in cursor.fetchall():
                    target_image_ids.add(row[0])

            if target_image_ids:
                image_ids_tuple = tuple(target_image_ids)
                cursor.execute('DELETE FROM Preannotations WHERE image_id IN {t}'.format(t=image_ids_tuple))
            else:
                cursor.execute('DELETE FROM Preannotations')
            deleted = cursor.rowcount
            conn.commit()
            logger.info(f"Deleted {deleted} preannotations for project {self.name}{' (image: ' + image_path + ')' if image_path else ''}{' (video: ' + str(video_id) + ', frames ' + str(start_frame) + '-' + str(end_frame) + ')' if video_id and start_frame is not None and end_frame is not None else ''}")
            print(f"Deleted {deleted} preannotations from '{self.name}'") 
            return deleted        
        
    # def delete_preannotations(self, image_path=None):
    #     """Delete preannotations for specific image or all."""
    #     print(f"Deleting preannotations for project '{self.name}' {'(image: ' + image_path + ')' if image_path else 'all'}...")
    #     with sqlite3.connect(self.db_path) as conn:
    #         cursor = conn.cursor()
    #         if image_path:
    #             cursor.execute('SELECT image_id FROM Images WHERE absolute_path = ?', (image_path,))
    #             image_id = cursor.fetchone()
    #             if image_id:
    #                 cursor.execute('DELETE FROM Preannotations WHERE image_id = ?', (image_id[0],))
    #             else:
    #                 logger.warning(f"Image {image_path} not found")
    #                 print(f"Error: Image {image_path} not found in project '{self.name}'")  
    #                 return 0
    #         else:
    #             cursor.execute('DELETE FROM Preannotations')
    #         deleted = cursor.rowcount
    #         conn.commit()
    #         logger.info(f"Deleted {deleted} preannotations for project {self.name}{' (image: ' + image_path + ')' if image_path else ''}")
    #         print(f"Deleted {deleted} preannotations from '{self.name}'")  
    #         return deleted

    # def delete_annotations(self, image_path=None, user_id=None, unmark_reviewed=True):
    #     """Delete annotations for specific image/user or all."""
    #     print(f"Deleting annotations for project '{self.name}' {'(image: ' + image_path + ')' if image_path else 'all'}...") 
    #     annotations_deleted = 0
    #     reviewed_deleted = 0
    #     with sqlite3.connect(self.db_path) as conn:
    #         cursor = conn.cursor()
    #         if image_path:
    #             cursor.execute('SELECT image_id FROM Images WHERE absolute_path = ?', (image_path,))
    #             image_id = cursor.fetchone()
    #             if image_id:
    #                 image_id = image_id[0]
    #                 if user_id:
    #                     cursor.execute('DELETE FROM Annotations WHERE image_id = ? AND user_id = ?', (image_id, user_id))
    #                 else:
    #                     cursor.execute('DELETE FROM Annotations WHERE image_id = ?', (image_id,))
    #                 annotations_deleted = cursor.rowcount
    #                 if unmark_reviewed:
    #                     cursor.execute('DELETE FROM ReviewedImages WHERE image_id = ?', (image_id,))
    #                     reviewed_deleted = cursor.rowcount
    #             else:
    #                 logger.warning(f"Image {image_path} not found")
    #                 print(f"Error: Image {image_path} not found in project '{self.name}'")  
    #         elif user_id:
    #             cursor.execute('DELETE FROM Annotations WHERE user_id = ?', (user_id,))
    #             annotations_deleted = cursor.rowcount
    #             if unmark_reviewed:
    #                 cursor.execute('DELETE FROM ReviewedImages WHERE user_id = ?', (user_id,))
    #                 reviewed_deleted = cursor.rowcount
    #         else:
    #             cursor.execute('DELETE FROM Annotations')
    #             annotations_deleted = cursor.rowcount
    #             if unmark_reviewed:
    #                 cursor.execute('DELETE FROM ReviewedImages')
    #                 reviewed_deleted = cursor.rowcount
    #         conn.commit()
    #         logger.info(f"Deleted {annotations_deleted} annotations and {reviewed_deleted} reviews for project {self.name}{' (image: ' + image_path + ')' if image_path else ''}{' (user: ' + str(user_id) + ')' if user_id else ''}")
    #         print(f"Deleted {annotations_deleted} annotations and {reviewed_deleted} reviews from '{self.name}'")
    #         return {'annotations_deleted': annotations_deleted, 'reviewed_deleted': reviewed_deleted}
        