![VisioFirm](examples/visiofirm-logo.gif)

# VisioFirm: Fast Almost fully-Automated Image Annotation for Computer Vision

[![GitHub Stars](https://img.shields.io/github/stars/OschAI/VisioFirm?style=social)](https://github.com/OschAI/VisioFirm/stargazers)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://github.com/OschAI/VisioFirm/blob/main/LICENSE)
[![PyPI](https://img.shields.io/pypi/v/visiofirm.svg)](https://pypi.org/project/visiofirm/) 
[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)

-------
> [!IMPORTANT]
> VisioFirm v1 is now available. VisioFirm has now much more support for computer vision annotation, pushing further the boundaries of efficient, fast, and accurate annotation. Here's  what’s New in v1.0.2 ✨
> * **Classification and Preannotation**: Predict and pre-suggest image classes using **OpenAI CLIP pretrained model**, enabling near-automatic labeling.
> * **Video Support & Label Propagation**: New **VFTracker** auto-labeling with frame-to-frame propagation: choose between: (1) **SmartPropagator** – Leverages **SAM2 + pre/post processing** for accurate, cumulative tracking. Annotate the first frame, propagate across the sequence. (2) **OpenCV Trackers** – Full support (CSRT, KCF, Boosting, MIL, TLD, MedianFlow, MOSSE, GOTURN) and (3) **Interpolation** – Classic propagation between `[labeled_start]` and `[labeled_end]`.
> * **Ultralytics Model Support**: Works with **YOLOv12 → YOLOv5**, including **YOLOv8-world** for open-vocab pre-annotation.
> * **Cross-domain annotation**: use detection models to pre-generate segmentation masks, or segmentation models to pre-label bounding boxes.
> * **Memory Management Improvements**: Optimized GPU usage with better model load/unload behavior for large-scale pre-annotation and tracking.
> * **Backend Migration to FastAPI**: Faster performance, async support, and smoother UI interactions.
> * **Python API**: Integrate VisioFirm seamlessly into pipelines with the new `visiofirm` Python API.
-------

**VisioFirm** is an open-source, AI-powered image annotation tool designed to accelerate labeling for computer vision tasks like classification, object detection, oriented bounding boxes (OBB), segmentation and video annotation. Built for speed and simplicity, it leverages state-of-the-art models for semi-automated pre-annotations, allowing you to focus on refining rather than starting from scratch. Whether you're preparing datasets for YOLO, SAM, or custom models, VisioFirm streamlines your workflow with a intuitive web interface and powerful backend.

Perfect for researchers, data scientists, and ML engineers handling large image datasets—get high-quality annotations in minutes, not hours!

## Why VisioFirm?

VisioFirm is majoraly focused on AI-model integration easiness for fast CV tasks annotation.

- **AI-Driven Pre-Annotation**: Automatically detect and segment objects using YOLO, SAM2, and Grounding DINO—saving up to 80% of manual effort.
- **Multi-Task Support**: Handles classification, bounding boxes, oriented bounding boxes, and polygon segmentation and now even videos in one tool.
- **Browser-Based Editing**: Interactive canvas for precise adjustments, with real-time SAM-powered segmentation in the browser.
- **Offline-Friendly**: Models download automatically (or pre-fetch for offline use), with SQLite backend for local projects.
- **Extensible & Open-Source**: Customize with your own ultralytics models or integrate into pipelines—contributions welcome!
- **SAM2-base webgpu**: Insta-drawing of annotations via SAM2 with worker offloading and auto-annotation for faster computing!

![Annotation Editing Demo](examples/visiofirmv1.gif) 

## Features

* **Semi-Automated Labeling**
  Kickstart annotations with AI models like **YOLO (v5–v12)** for detection, **SAM2** for segmentation, **Grounding DINO** for zero-shot object grounding, and **CLIP** for automated classification.

* **Flexible Annotation Types**

  * Axis-aligned bounding boxes for standard detection.
  * Oriented bounding boxes for rotated objects (e.g., aerial imagery).
  * Polygon segmentation for precise boundaries.
  * Image classification with automatic label suggestions.

* **Video Annotation & Label Propagation**
  Annotate videos with frame-to-frame consistency:

  * **SmartPropagator** (SAM2-powered accurate propagation).
  * **OpenCV trackers** (CSRT, KCF, Boosting, MIL, TLD, MedianFlow, MOSSE, GOTURN).
  * **Interpolation** between annotated start/end frames.

* **Cross-Domain Annotation**

  * Use detection models to auto-generate segmentation masks.
  * Use segmentation models to pre-label bounding boxes.

* **Ultralytics Model Support**
  Full support for **YOLOv12, v11, v10, v9, v8, v5**, plus **YOLOv8-world** for open-vocab pre-annotations (no GPU required).

* **Interactive Frontend**
  Draw, edit, and refine labels on a responsive canvas.

  * **Click-to-segment** with browser-based SAM2.
  * Hotkeys, undo/redo, and zoom for efficient annotation.

* **Project Management**
  Organize datasets with SQLite-backed projects.

  * Multi-class support.
  * Import/export with minimal setup.

* **Export Formats**
  Export annotations to **YOLO, COCO, or custom formats** for seamless training.

* **Performance Optimizations**

  * GPU memory management for efficient model loading/unloading.
  * Cluster overlapping detections, simplify contours, and filter by confidence.
  * Multi-threaded uploading and optimized image import.

* **Cloud/SSH Integration**
  Download images from cloud storage or SSH servers, save annotations remotely, and manage large-scale projects.

* **Backend Migration to FastAPI**
  Faster response times, async support, and smoother UI performance.

* **VisioFirm Python API**
  Integrate annotation workflows into custom scripts and ML pipelines.

## DEMOs

Detection based on pre-trained/zeroshot models:

![Annotation Editing Demo](examples/AIpreannotator-demo.gif)

Video Segmentation using Smart Propagator:

![Video Editing Demo](examples/demo_annotation_.mp4)

## Installation

VisioFirm was tested with `Python 3.10+`.

> [!NOTE]
> VisioFirm v1 introduces a new database management logic.  
> To avoid conflicts with older versions, you need to **rename/remove the old cache folder** before running the new release:  
> 
> - **Linux**: `~/.cache/visiofirm_cache`  
> - **macOS**: `~/Library/Caches/visiofirm_cache`  
> - **Windows**: `%LOCALAPPDATA%\visiofirm_cache`  
> 
> After deleting the folder, restart VisioFirm — it will automatically recreate the cache directory with the new structure.

```bash
pip install -U visiofirm
```

For development or editable install (from a cloned repo):

```bash
git clone https://github.com/OschAI/VisioFirm.git
cd VisioFirm
pip install -e .
```
 
## Quick Start

Launch VisioFirm with a single command—it auto-starts a local web server and opens in your browser.

```bash
visiofirm
```

1. Create a new project and upload images.
2. Define classes (e.g., "car", "person").
3. For easy-to-detect object run AI pre-annotation (select model: YOLO, Grounding DINO).
4. Refine labels in the interactive editor.
5. Export your annotated dataset.

The VisioFirm app uses cache directories to store settings locally.

## Usage

### Pre-Annotation with AI

VisioFirm uses advanced models for initial labels:

- **YOLO**: All ultralytics based YOLO model are now compatible and can be used.
- **SAM2**: Precise segmentation use in image annotation and video propagation
- **Grounding DINO**: Zero-shot detection via text prompts.

## Community & Support

- **Issues**: Report bugs or request features [here](https://github.com/OschAI/VisioFirm/issues).
- **Discord**: Coming soon—star the repo for updates!
- **Roadmap**: Multi-user support, custom model integration.

## License

Apache 2.0 - See [LICENSE](LICENSE) for details.

This project uses third-party software and models:

- Ultralytics YOLO  
  https://github.com/ultralytics/ultralytics  
  License: AGPL-3.0  

- SAM2 (Segment Anything Model v2)  
  https://github.com/facebookresearch/sam2  
  Licenses: Apache 2.0 and BSD 3-Clause  

- GroundingDINO  
  https://github.com/IDEA-Research/GroundingDINO  
  License: Apache 2.0

---

Built by [Safouane El Ghazouali](https://github.com/safouaneelg) for the research community. Star the repo if it helps your workflow! 🚀

## Citation

```
@misc{ghazouali2025visiofirm,
    title={VisioFirm: Cross-Platform AI-assisted Annotation Tool for Computer Vision},
    author={Safouane El Ghazouali and Umberto Michelucci},
    year={2025},
    eprint={2509.04180},
    archivePrefix={arXiv},
    primaryClass={cs.CV}
}
```

**SOON**:

- Documentation website
- Discord community
