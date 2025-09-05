![VisioFirm](https://github.com/OschAI/VisioFirm/blob/main/examples/visiofirm-logo.gif)

# VisioFirm: Fast Almost fully-Automated Image Annotation for Computer Vision

[![GitHub Stars](https://img.shields.io/github/stars/OschAI/VisioFirm?style=social)](https://github.com/OschAI/VisioFirm/stargazers)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://github.com/OschAI/VisioFirm/blob/main/LICENSE)
[![PyPI](https://img.shields.io/pypi/v/visiofirm.svg)](https://pypi.org/project/visiofirm/) <!-- Update if published -->
[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
-------
> [!IMPORTANT]
> A new release has just dropped. `VisioFirm 0.1.1` has now a different GroundingDINO dependency which is tied directly to the original [Grounding DINO GitHub](https://github.com/IDEA-Research/GroundingDINO) through the pip library 'groundingdino-py' thanks to [@giswqs](https://github.com/giswqs).

> [!NOTE]
>If you prefer the HF transformers-based library you can install the version from main branch [main branch](https://github.com/OschAI/VisioFirm/tree/main) via the command line `pip install visiofirm==0.1.0`..
-------

**VisioFirm** is an open-source, AI-powered image annotation tool designed to accelerate labeling for computer vision tasks like object detection, oriented bounding boxes (OBB), and segmentation. Built for speed and simplicity, it leverages state-of-the-art models for semi-automated pre-annotations, allowing you to focus on refining rather than starting from scratch. Whether you're preparing datasets for YOLO, SAM, or custom models, VisioFirm streamlines your workflow with a intuitive web interface and powerful backend.

Perfect for researchers, data scientists, and ML engineers handling large image datasets—get high-quality annotations in minutes, not hours!

## Why VisioFirm?

Unlike other annotation tool, this one is majoraly focused on CV tasks annotation detection (normal and oriented bounding box) and segmentation.

- **AI-Driven Pre-Annotation**: Automatically detect and segment objects using YOLOv10, SAM2, and Grounding DINO—saving up to 80% of manual effort.
- **Multi-Task Support**: Handles bounding boxes, oriented bounding boxes, and polygon segmentation in one tool.
- **Browser-Based Editing**: Interactive canvas for precise adjustments, with real-time SAM-powered segmentation in the browser.
- **Offline-Friendly**: Models download automatically (or pre-fetch for offline use), with SQLite backend for local projects.
- **Extensible & Open-Source**: Customize with your own ultralytics models or integrate into pipelines—contributions welcome!
- **SAM2-base webgpu**: insta-drawing of annotation via SAM2!
![Annotation Editing Demo](https://github.com/OschAI/VisioFirm/blob/main/examples/orange-apples-test.gif) 

## Features

- **Semi-Automated Labeling**: Kickstart annotations with AI models like YOLO for detection, SAM for segmentation, and Grounding DINO for zero-shot object grounding.
- **Flexible Annotation Types**:
  - Axis-aligned bounding boxes for standard detection.
  - Oriented bounding boxes for rotated objects (e.g., aerial imagery).
  - Polygon segmentation for precise boundaries.
- **Interactive Frontend**: Draw, edit, and refine labels on a responsive canvas. Click-to-segment with browser-based SAM for instant masks.
- **Project Management**: Create, manage, and export projects with SQLite database storage. Support for multiple classes and images.
- **Export Formats**: Seamless exports to YOLO, COCO, or custom formats for training.
- **Performance Optimizations**: Cluster overlapping detections, simplify contours, and filter by confidence for clean datasets.
- **Cross-Platform**: Runs locally on Linux, macOS, or Windows via Python— no cloud dependency.

![Annotation Editing Demo](https://github.com/OschAI/VisioFirm/blob/main/examples/AIpreannotator-demo.gif) 

## Installation

VisioFirm is easy to install via pip from GitHub (PyPI coming soon!).

It was tested with `Python 3.10+`.

```bash
pip install visiofirm==0.1.1
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

Access at `http://localhost:8000` (or next available port).

The VisioFirm app uses cache directories to store settings locally.

## Usage

### Pre-Annotation with AI
VisioFirm uses advanced models for initial labels:
- **YOLOv10**: Fast detection.
- **SAM2**: Precise segmentation.
- **Grounding DINO**: Zero-shot detection via text prompts.

Models auto-download on first run (stored in current dir or cache). For offline prep:

### Frontend Customization
The web interface (Flask + JS) supports hotkeys, undo/redo, and zoom. Edit `static/js/sam.js` for browser SAM tweaks.

### Exporting Data
From the dashboard, export to JSON, TXT (YOLO format), or images with masks.

## Community & Support

- **Issues**: Report bugs or request features [here](https://github.com/OschAI/VisioFirm/issues).
- **Discord**: Coming soon—star the repo for updates!
- **Roadmap**: Multi-user support, video annotation, custom model integration.

## License

Apache 2.0 - See [LICENSE](LICENSE) for details.

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

## TODOs

**SOON**:

- Documentation website
- Discord community
- Paper - detailing the implementation and AI preannotation pipeline
- Classification

**Futur**:

- Support for video annotation
- Support for more ML frameworks (such as mmdetection and detectron2)

