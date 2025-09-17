export let setupType = null;
export let annotationCache = {};
export let currentImageKey = null;
export let currentImageIndex = -1;
export let thumbnailImages = [];
export let canvas = null;
export let ctx = null;
export let viewport = { x: 0, y: 0, zoom: 1, minZoom: .1, maxZoom: 20 };
export let currentImage = null;
export let mode = 'rect';
export let annotations = [];
export let currentAnnotation = null;
export let isDrawing = false;
export let isDragging = false;
export let startX = 0;
export let startY = 0;
export let selectedAnnotation = null;
export let selectedPointIndex = -1;
export let undoStack = {};
export let isRightClickEditing = false;
export let clipboardImageResolution = { width: 0, height: 0 };
export let gridEnabled = false;
export const gridSize = 5;
export let classColors = {};
export let isRotating = false;
export let initialRotation = 0;
export let initialCorners = [];
export let preannotations = [];
export let confidenceThreshold = 0.4;
export let selectedClass = null;
export let imageEmbeddings = null;
export let imageProcessed = null;
export let worker = null;
export let selectedLabel = null;

export function setSelectedLabel(value) { selectedLabel = value; }
export function setIsMoving(value) { isMoving = value; }
export function setInitialRotation(value) { initialRotation = value; }
export function setInitialCorners(value) { initialCorners = value; }
export function setIsDrawing(value) { isDrawing = value; }
export function setMode(value) { mode = value; }
export function setCurrentImageKey(value) { currentImageKey = value; }
export function setAnnotations(value) { annotations = value; }
export function setSelectedAnnotation(value) { selectedAnnotation = value; }
export function setCurrentImage(value) { currentImage = value; }
export function setCurrentImageIndex(value) { currentImageIndex = value; }
export function setGridEnabled(value) { gridEnabled = value; }
export function setCurrentAnnotation(value) { currentAnnotation = value; }
export function setIsDragging(value) { isDragging = value; }
export function setStartX(value) { startX = value; }
export function setStartY(value) { startY = value; }
export function setSelectedPointIndex(value) { selectedPointIndex = value; }
export function setIsRightClickEditing(value) { isRightClickEditing = value; }
export function setUndoStack(value) { undoStack = value; }
export function setIsRotating(value) { isRotating = value; }
export function setSetupType(value) { setupType = value; }
export function setThumbnailImages(value) { thumbnailImages = value; }
export function setCanvas(value) { canvas = value; }
export function setCtx(value) { ctx = value; }
export function setViewport(value) { viewport = value; }
export function setClipboardImageResolution(value) { clipboardImageResolution = value; }
export function setClassColors(value) { classColors = value; }
export function setSelectedClass(value) { selectedClass = value; }
export function setPreannotations(value) { preannotations = value; }
export function setConfidenceThreshold(value) { confidenceThreshold = value; }
export function setWorker(value) { worker = value; } // Added setter for worker

export function initGlobals() {
    const config = JSON.parse(document.getElementById('app-config').textContent);
    setupType = config.setupType;
    classColors = {};
    console.log('Initializing class colors for:', config.classes);
    
    if (config.classes.length > 0) {
        setSelectedClass(config.classes[0]);
    }

    config.classes.forEach(cls => {
        classColors[cls] = getClassColor(cls);
    });
    thumbnailImages = document.querySelectorAll('#annotation-view .thumbnail-image img');
    canvas = document.getElementById('labeling-canvas');
    ctx = canvas.getContext('2d');
    mode = (setupType === "Segmentation") ? 'polygon' : 'rect';
    if (setupType === "Classification") {
        mode = 'select';
    }
    console.log('Canvas initialized:', canvas, ctx);
}

export function updateTagHighlights() {
    document.querySelectorAll('.class-tag').forEach(t => t.classList.remove('highlighted'));
    if (selectedAnnotation) {
        const tag = document.querySelector(`.class-tag[data-class="${selectedAnnotation.label}"]`);
        if (tag) tag.classList.add('highlighted');
    }
}

function getClassColor(className) {
    const hash = Array.from(className).reduce((hash, char) => char.charCodeAt(0) + ((hash << 5) - hash), 0);
    const r = (hash & 0xFF0000) >> 16;
    const g = (hash & 0x00FF00) >> 8;
    const b = hash & 0x0000FF;
    return `rgba(${r}, ${g}, ${b}, 0.95)`;
}

export function setAnnotationCache(newCache) {
    annotationCache = newCache;
    console.log('Annotation Cache Updated:', annotationCache);
}