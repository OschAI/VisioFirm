from io import BytesIO
import zipfile
import json
import yaml
import math
import sqlite3
import os
from datetime import datetime
import random
import json
from PIL import Image, ImageDraw
import numpy as np

def split_images(images, split_choices, split_ratios):
    """Split images into train/test/val sets based on specified ratios."""
    if not split_choices:
        return {'train': images}
   
    selected_ratios = [split_ratios[split] for split in split_choices]
    if sum(selected_ratios) != 100:
        raise ValueError("Split ratios must sum to 100%")
   
    shuffled = images.copy()
    random.shuffle(shuffled)
    n_total = len(shuffled)
    split_points = []
    cumulative = 0
    for ratio in selected_ratios[:-1]:
        cumulative += ratio
        split_points.append(int(n_total * cumulative / 100))
   
    split_indices = [0] + split_points + [n_total]
    splits = {}
    for i, split_name in enumerate(split_choices):
        start = split_indices[i]
        end = split_indices[i+1]
        splits[split_name] = shuffled[start:end]
   
    return splits

def generate_coco_export(project, splits, setup_type, project_name, project_description):
    """Generate COCO format export with proper folder structure."""
    categories = project.get_classes()
    category_dict = {name: idx + 1 for idx, name in enumerate(categories)}
   
    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        # Create COCO folder structure
        for split_name, split_images in splits.items():
            images_list = []
            annotations_list = []
            annotation_id = 1
           
            for img_path in split_images:
                with sqlite3.connect(project.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute('SELECT image_id, width, height FROM Images WHERE absolute_path = ?', (img_path,))
                    image_id, width, height = cursor.fetchone()
                   
                    # Add image to zip in images/{split_name} folder
                    with open(img_path, 'rb') as f:
                        zip_file.writestr(f'images/{split_name}/{os.path.basename(img_path)}', f.read())
                   
                    images_list.append({
                        'id': image_id,
                        'file_name': os.path.basename(img_path),
                        'width': width,
                        'height': height
                    })
                    # Process annotations
                    cursor.execute('SELECT * FROM Annotations WHERE image_id = ?', (image_id,))
                    for row in cursor.fetchall():
                        anno = {
                            'id': annotation_id,
                            'image_id': image_id,
                            'category_id': category_dict.get(row[4], 0),
                            'iscrowd': 0,
                            'area': 0
                        }
                       
                        if setup_type == "Bounding Box":
                            anno['bbox'] = [row[5], row[6], row[7], row[8]]
                            anno['area'] = row[7] * row[8]
                        elif setup_type == "Segmentation":
                            segmentation = json.loads(row[10]) if row[10] else []
                            anno['segmentation'] = [segmentation]
                            if segmentation:
                                xs = segmentation[0::2]
                                ys = segmentation[1::2]
                                min_x, min_y = min(xs), min(ys)
                                max_x, max_y = max(xs), max(ys)
                                anno['bbox'] = [min_x, min_y, max_x - min_x, max_y - min_y]
                                anno['area'] = (max_x - min_x) * (max_y - min_y)
                        elif setup_type == "Oriented Bounding Box":
                            center_x = row[5] + (row[7] / 2) if row[7] else 0
                            center_y = row[6] + (row[8] / 2) if row[8] else 0
                            angle = row[9] * math.pi / 180 if row[9] else 0
                            w = row[7] if row[7] else 0
                            h = row[8] if row[8] else 0
                            points = [(-w/2, -h/2), (w/2, -h/2), (w/2, h/2), (-w/2, h/2)]
                            rotated_points = []
                            for p in points:
                                x = p[0] * math.cos(angle) - p[1] * math.sin(angle) + center_x
                                y = p[0] * math.sin(angle) + p[1] * math.cos(angle) + center_y
                                rotated_points.extend([x, y])
                            anno['segmentation'] = [rotated_points]
                            xs = rotated_points[0::2]
                            ys = rotated_points[1::2]
                            min_x, min_y = min(xs), min(ys)
                            max_x, max_y = max(xs), max(ys)
                            anno['bbox'] = [min_x, min_y, max_x - min_x, max_y - min_y]
                            anno['area'] = (max_x - min_x) * (max_y - min_y)
                       
                        annotations_list.append(anno)
                        annotation_id += 1
            # Create COCO JSON for this split
            coco_data = {
                'info': {
                    'year': datetime.now().year,
                    'Software': 'VisioFirm',
                    'contributor': '',
                    'date_created': datetime.now().strftime('%Y-%m-%d'),
                    'project_name': project_name,
                    'project_description': project_description
                },
                'licenses': [{
                    'id': 1,
                    'url': 'https://creativecommons.org/licenses/by/4.0/',
                    'name': 'CC BY 4.0'
                }],
                'images': images_list,
                'annotations': annotations_list,
                'categories': [{'id': idx, 'name': name} for name, idx in category_dict.items()]
            }
           
            zip_file.writestr(f'annotations/instances_{split_name}.json', json.dumps(coco_data, indent=2))
   
    zip_buffer.seek(0)
    return zip_buffer

def generate_yolo_export(project, splits, setup_type, project_name, project_description):
    """Generate YOLO format export with proper folder structure."""
    categories = project.get_classes()
    category_dict = {name: idx for idx, name in enumerate(categories)}
   
    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        # Create YOLO folder structure
        for split_name, split_images in splits.items():
            for img_path in split_images:
                # Add image to zip in {split_name}/images folder
                with open(img_path, 'rb') as f:
                    zip_file.writestr(f'{split_name}/images/{os.path.basename(img_path)}', f.read())
               
                # Process annotations
                with sqlite3.connect(project.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute('SELECT image_id, width, height FROM Images WHERE absolute_path = ?', (img_path,))
                    image_id, img_width, img_height = cursor.fetchone()
                    cursor.execute('SELECT * FROM Annotations WHERE image_id = ?', (image_id,))
                    lines = []
                    for row in cursor.fetchall():
                        class_id = category_dict.get(row[4], -1)
                        if class_id == -1:
                            continue
                           
                        if setup_type == "Bounding Box":
                            x_center = (row[5] + row[7] / 2) / img_width
                            y_center = (row[6] + row[8] / 2) / img_height
                            width = row[7] / img_width
                            height = row[8] / img_height
                            lines.append(f"{class_id} {x_center} {y_center} {width} {height}")
                        elif setup_type == "Oriented Bounding Box":
                            center_x = row[5] + (row[7] / 2) if row[7] else 0
                            center_y = row[6] + (row[8] / 2) if row[8] else 0
                            angle = row[9] * math.pi / 180 if row[9] else 0
                            w = row[7] if row[7] else 0
                            h = row[8] if row[8] else 0
                            points = [(-w/2, -h/2), (w/2, -h/2), (w/2, h/2), (-w/2, h/2)]
                            rotated_points = []
                            for p in points:
                                x = p[0] * math.cos(angle) - p[1] * math.sin(angle) + center_x
                                y = p[0] * math.sin(angle) + p[1] * math.cos(angle) + center_y
                                rotated_points.append((x / img_width, y / img_height))
                            line = f"{class_id} " + " ".join(f"{p[0]} {p[1]}" for p in rotated_points)
                            lines.append(line)
                        elif setup_type == "Segmentation":
                            segmentation = json.loads(row[10]) if row[10] else []
                            if segmentation:
                                normalized_points = []
                                for i in range(0, len(segmentation), 2):
                                    x = segmentation[i] / img_width
                                    y = segmentation[i + 1] / img_height
                                    normalized_points.extend([x, y])
                                line = f"{class_id} " + " ".join(map(str, normalized_points))
                                lines.append(line)
                   
                    # Add label to zip in {split_name}/labels folder
                    txt_filename = os.path.splitext(os.path.basename(img_path))[0] + '.txt'
                    zip_file.writestr(f'{split_name}/labels/{txt_filename}', "\n".join(lines))
        # Create data.yaml
        yaml_data = {
            'names': categories,
            'nc': len(categories),
            'train': 'train/images' if 'train' in splits else '',
            'val': 'val/images' if 'val' in splits else '',
            'test': 'test/images' if 'test' in splits else '',
            'VisioFirm': {
                'year': datetime.now().year,
                'Software': 'VisioFirm',
                'contributor': '',
                'date_created': datetime.now().strftime('%Y-%m-%d'),
                'project_name': project_name,
                'project_description': project_description
            }
        }
        zip_file.writestr('data.yaml', yaml.dump(yaml_data, default_flow_style=False))
   
    zip_buffer.seek(0)
    return zip_buffer

def generate_pascal_voc_export(project, splits, setup_type):
    """Generate Pascal VOC format export with proper folder structure."""
    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for split_name, split_images in splits.items():
            # Create ImageSets/Main directory
            image_set_lines = []
           
            for img_path in split_images:
                basename = os.path.splitext(os.path.basename(img_path))[0]
                image_set_lines.append(basename)
               
                # Add image to JPEGImages
                with open(img_path, 'rb') as f:
                    zip_file.writestr(f'VOC2007/JPEGImages/{os.path.basename(img_path)}', f.read())
               
                # Create annotation XML
                with sqlite3.connect(project.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute('SELECT image_id, width, height FROM Images WHERE absolute_path = ?', (img_path,))
                    image_id, img_width, img_height = cursor.fetchone()
                    cursor.execute('SELECT * FROM Annotations WHERE image_id = ?', (image_id,))
                    objects = []
                    for row in cursor.fetchall():
                        class_name = row[4]
                        if setup_type == "Bounding Box":
                            xmin = row[5]
                            ymin = row[6]
                            xmax = row[5] + row[7]
                            ymax = row[6] + row[8]
                        elif setup_type == "Oriented Bounding Box":
                            center_x = row[5] + (row[7] / 2) if row[7] else 0
                            center_y = row[6] + (row[8] / 2) if row[8] else 0
                            angle = row[9] * math.pi / 180 if row[9] else 0
                            w = row[7] if row[7] else 0
                            h = row[8] if row[8] else 0
                            points = [(-w/2, -h/2), (w/2, -h/2), (w/2, h/2), (-w/2, h/2)]
                            rotated_points = []
                            for p in points:
                                x = p[0] * math.cos(angle) - p[1] * math.sin(angle) + center_x
                                y = p[0] * math.sin(angle) + p[1] * math.cos(angle) + center_y
                                rotated_points.append((x, y))
                            xs = [p[0] for p in rotated_points]
                            ys = [p[1] for p in rotated_points]
                            xmin, ymin = min(xs), min(ys)
                            xmax, ymax = max(xs), max(ys)
                        elif setup_type == "Segmentation":
                            segmentation = json.loads(row[10]) if row[10] else []
                            if segmentation:
                                xs = segmentation[0::2]
                                ys = segmentation[1::2]
                                xmin, ymin = min(xs), min(ys)
                                xmax, ymax = max(xs), max(ys)
                            else:
                                continue
                        objects.append({
                            'name': class_name,
                            'bndbox': {'xmin': xmin, 'ymin': ymin, 'xmax': xmax, 'ymax': ymax}
                        })
                    xml_content = f"""<annotation>
    <folder>{project.name}</folder>
    <filename>{os.path.basename(img_path)}</filename>
    <size>
        <width>{img_width}</width>
        <height>{img_height}</height>
        <depth>3</depth>
    </size>
"""
                    for obj in objects:
                        xml_content += f""" <object>
        <name>{obj['name']}</name>
        <bndbox>
            <xmin>{obj['bndbox']['xmin']}</xmin>
            <ymin>{obj['bndbox']['ymin']}</ymin>
            <xmax>{obj['bndbox']['xmax']}</xmax>
            <ymax>{obj['bndbox']['ymax']}</ymax>
        </bndbox>
    </object>
"""
                    xml_content += "</annotation>"
                    zip_file.writestr(f'VOC2007/Annotations/{basename}.xml', xml_content)
           
            # Write ImageSet file
            zip_file.writestr(f'VOC2007/ImageSets/Main/{split_name}.txt', "\n".join(image_set_lines))
   
    zip_buffer.seek(0)
    return zip_buffer


def generate_classification_labels(project, splits, output_format='csv'):
    """Generate classification labels in CSV, TXT, or JSON with splits."""
    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for split_name, split_images in splits.items():
            if output_format == 'csv':
                csv_lines = ["image_id,image_name,class_name"]
                for img_path in split_images:
                    with sqlite3.connect(project.db_path) as conn:
                        cursor = conn.cursor()
                        cursor.execute('SELECT image_id FROM Images WHERE absolute_path = ?', (img_path,))
                        result = cursor.fetchone()
                        image_id = result[0] if result else ''
                        cursor.execute('SELECT class_name FROM Annotations WHERE image_id = ?', (image_id,))
                        result = cursor.fetchone()
                        class_name = result[0] if result else ''
                        csv_lines.append(f"{image_id},{os.path.basename(img_path)},{class_name}")
                zip_file.writestr(f'annotation/{split_name}.csv', "\n".join(csv_lines))
            elif output_format == 'txt':
                for img_path in split_images:
                    with sqlite3.connect(project.db_path) as conn:
                        cursor = conn.cursor()
                        cursor.execute('SELECT image_id FROM Images WHERE absolute_path = ?', (img_path,))
                        image_id = cursor.fetchone()[0]
                        cursor.execute('SELECT class_name FROM Annotations WHERE image_id = ?', (image_id,))
                        result = cursor.fetchone()
                        class_name = result[0] if result else ''
                    txt_filename = os.path.splitext(os.path.basename(img_path))[0] + '.txt'
                    zip_file.writestr(f'{split_name}/labels/{txt_filename}', class_name)
            elif output_format == 'json':
                data = []
                for img_path in split_images:
                    with sqlite3.connect(project.db_path) as conn:
                        cursor = conn.cursor()
                        cursor.execute('SELECT image_id FROM Images WHERE absolute_path = ?', (img_path,))
                        image_id = cursor.fetchone()[0]
                        cursor.execute('SELECT class_name FROM Annotations WHERE image_id = ?', (image_id,))
                        result = cursor.fetchone()
                        class_name = result[0] if result else ''
                    data.append({'image_id': image_id, 'filename': os.path.basename(img_path), 'class': class_name})
                zip_file.writestr(f'annotation/{split_name}.json', json.dumps(data, indent=2))
            else:
                raise ValueError(f"Unsupported output_format: {output_format}. Choose 'csv', 'txt', or 'json'.")

            # Add images to split/images
            for img_path in split_images:
                with open(img_path, 'rb') as f:
                    zip_file.writestr(f'{split_name}/images/{os.path.basename(img_path)}', f.read())

    zip_buffer.seek(0)
    return zip_buffer

def generate_csv_export(project, splits, setup_type):
    """Generate CSV format export with proper folder structure."""
    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for split_name, split_images in splits.items():
            csv_lines = []
            if setup_type == "Classification":
                header = "image_id,image_name,class_name"
                csv_lines.append(header)
                for img_path in split_images:
                    with sqlite3.connect(project.db_path) as conn:
                        cursor = conn.cursor()
                        cursor.execute('SELECT image_id FROM Images WHERE absolute_path = ?', (img_path,))
                        image_id = cursor.fetchone()[0]
                        cursor.execute('SELECT class_name FROM Annotations WHERE image_id = ?', (image_id,))
                        result = cursor.fetchone()
                        class_name = result[0] if result else ''
                        csv_lines.append(f"{image_id},{os.path.basename(img_path)},{class_name}")
            else:
                header = "image_id,image_name,class_name,x,y,width,height" if setup_type != "Oriented Bounding Box" else "image_id,image_name,class_name,xc,yc,dx,dy,angle"
                csv_lines.append(header)
                for img_path in split_images:
                    with sqlite3.connect(project.db_path) as conn:
                        cursor = conn.cursor()
                        cursor.execute('SELECT image_id FROM Images WHERE absolute_path = ?', (img_path,))
                        image_id = cursor.fetchone()[0]
                        cursor.execute('SELECT * FROM Annotations WHERE image_id = ?', (image_id,))
                        for row in cursor.fetchall():
                            class_name = row[4]
                            img_name = os.path.basename(img_path)
                            if setup_type == "Bounding Box":
                                x, y, width, height = row[5], row[6], row[7], row[8]
                                csv_lines.append(f"{image_id},{img_name},{class_name},{x},{y},{width},{height}")
                            elif setup_type == "Oriented Bounding Box":
                                xc = row[5] + (row[7] / 2) if row[7] else 0
                                yc = row[6] + (row[8] / 2) if row[8] else 0
                                dx = row[7] if row[7] else 0
                                dy = row[8] if row[8] else 0
                                angle = row[9] if row[9] else 0
                                csv_lines.append(f"{image_id},{img_name},{class_name},{xc},{yc},{dx},{dy},{angle}")
                            elif setup_type == "Segmentation":
                                segmentation = json.loads(row[10]) if row[10] else []
                                if segmentation:
                                    xs = segmentation[0::2]
                                    ys = segmentation[1::2]
                                    x = min(xs)
                                    y = min(ys)
                                    width = max(xs) - x
                                    height = max(ys) - y
                                    csv_lines.append(f"{image_id},{img_name},{class_name},{x},{y},{width},{height}")
            # Write CSV file to annotation folder
            zip_file.writestr(f'annotation/{split_name}.csv', "\n".join(csv_lines))
            
            # Add images to split folder
            for img_path in split_images:
                with open(img_path, 'rb') as f:
                    zip_file.writestr(f'{split_name}/{os.path.basename(img_path)}', f.read())
   
    zip_buffer.seek(0)
    return zip_buffer

def generate_mask_export(project, splits):
    """Generate binary PNG mask export for semantic segmentation (white for annotations, black for background)."""
    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for split_name, split_images in splits.items():
            for img_path in split_images:
                # Add image to zip in split/images/
                with open(img_path, 'rb') as f:
                    zip_file.writestr(f'{split_name}/images/{os.path.basename(img_path)}', f.read())
                
                # Create binary mask
                with sqlite3.connect(project.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute('SELECT image_id, width, height FROM Images WHERE absolute_path = ?', (img_path,))
                    image_id, width, height = cursor.fetchone()
                    
                    mask = Image.new('L', (width, height), 0)  # Grayscale, background=0 (black)
                    draw = ImageDraw.Draw(mask)
                    
                    cursor.execute('SELECT class_name, segmentation FROM Annotations WHERE image_id = ?', (image_id,))
                    annotations = cursor.fetchall()
                    print(f"Found {len(annotations)} annotations for image_id {image_id} ({os.path.basename(img_path)})")
                    
                    for class_name, seg_json in annotations:
                        if not seg_json:
                            print(f"Skipping empty segmentation for class {class_name}")
                            continue
                        try:
                            points = json.loads(seg_json)
                            if len(points) < 6:  # Minimum 3 points (x,y) for a polygon
                                print(f"Invalid segmentation for class {class_name}: too few points {points}")
                                continue
                            point_tuples = [(points[i], points[i+1]) for i in range(0, len(points), 2)]
                            #print(f"Drawing polygon for class {class_name}: {point_tuples}")
                            draw.polygon(point_tuples, fill=255)  # Fill with white (255)
                        except json.JSONDecodeError:
                            print(f"Invalid JSON segmentation for class {class_name}: {seg_json}")
                            continue
                
                # Check mask contents
                mask_array = np.array(mask)
                print(f"Mask for {os.path.basename(img_path)}: min={mask_array.min()}, max={mask_array.max()}")
                
                # Save mask to bytes and add to zip in split/labels/
                mask_bytes = BytesIO()
                mask.save(mask_bytes, format='PNG')
                mask_bytes.seek(0)
                
                basename = os.path.splitext(os.path.basename(img_path))[0]
                zip_file.writestr(f'{split_name}/labels/{basename}.png', mask_bytes.read())
    
    zip_buffer.seek(0)
    return zip_buffer