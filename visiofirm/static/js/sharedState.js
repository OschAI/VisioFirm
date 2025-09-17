// Fetch configuration from the app-config element
const config = JSON.parse(document.getElementById('app-config').textContent);

// Define the state object using config values
export const state = {
    setupType: config.setupType,
    annotationCache: {},
    currentImageKey: null,
    currentImageIndex: -1,
    currentImage: null,
    viewport: { x: 0, y: 0, zoom: 1, minZoom: 1, maxZoom: 5 },
    mode: null, // Will be initialized below
    annotations: [],
    currentAnnotation: null,
    isDrawing: false,
    isDragging: false,
    startX: 0,
    startY: 0,
    selectedAnnotation: null,
    selectedPointIndex: -1,
    undoStack: {},
    isRightClickEditing: false,
    clipboardImageResolution: { width: 0, height: 0 },
    gridEnabled: false,
    gridSize: 5,
    classColors: {},
    canvas: document.getElementById('labeling-canvas'),
    ctx: document.getElementById('labeling-canvas')?.getContext('2d'),
    thumbnailImages: document.querySelectorAll('#annotation-view .thumbnail-image img'),
    projectName: config.projectName,
    thumbnailImages: Array.from(document.querySelectorAll('#annotation-view .thumbnail-image img')).map(img => {
        if (img.dataset.src && !img.src) {
            img.src = img.dataset.src;  // Pre-load for fallback
            img.classList.add('loaded');  // Mark as loaded to skip observer
        }
        return img;
    }),
};

// Initialize mode based on setup type
state.mode = (state.setupType === "Segmentation") ? 'polygon' : 'rect';

// Initialize class colors from config.classes
const classes = config.classes;
classes.forEach(cls => {
    const hash = Array.from(cls).reduce((hash, char) => char.charCodeAt(0) + ((hash << 5) - hash), 0);
    const r = (hash & 0xFF0000) >> 16;
    const g = (hash & 0x00FF00) >> 8;
    const b = hash & 0x0000FF;
    state.classColors[cls] = `rgba(${r}, ${g}, ${b}, 0.7)`;
});