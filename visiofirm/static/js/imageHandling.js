import {
    currentImageKey,
    currentImage,
    annotations,
    annotationCache,
    undoStack,
    thumbnailImages,
    viewport,
    canvas,
    setupType,
    confidenceThreshold,
    setSelectedLabel,
    setCurrentImageKey,
    setCurrentImage,
    setAnnotations,
    setAnnotationCache,
    setUndoStack,
    setSelectedAnnotation,
    setCurrentImageIndex,
    updateTagHighlights
} from './globals.js';
import { drawImage, resetView } from './annotationDrawing.js';
import { updateAnnotationStatus, updateClassTags } from './main.js';

export async function selectImage(imgElement, index = -1) {
    if (!imgElement || !imgElement.getAttribute('src')) {
        console.error('Invalid image element provided to selectImage');
        return;
    }

    const img = new Image();
    let imageKey = imgElement.getAttribute('src');
    if (imageKey.startsWith('http')) {
        const url = new URL(imageKey);
        imageKey = url.pathname;
    }
    console.log('Selecting Image:', imageKey);

    if (currentImageKey) {
        setAnnotationCache({
            ...annotationCache,
            [currentImageKey]: [...annotations]
        });
    }

    img.onload = async () => {
        setCurrentImageKey(imageKey);
        setCurrentImageIndex(index >= 0 ? index : Array.from(thumbnailImages).indexOf(imgElement));
        setCurrentImage(img);

        let loadedAnnotations = [];
        let loadedPreannotations = [];
        let isReviewed = false;
        try {
            const projectName = JSON.parse(document.getElementById('app-config').textContent).projectName;
            const imagePath = imageKey.split('/').slice(-1)[0];
            console.log('Fetching annotations for:', imagePath);
            const response = await fetch(`/annotation/get_annotations/${projectName}/${encodeURIComponent(imagePath)}`);
            const result = await response.json();

            if (result.success) {
                loadedAnnotations = result.annotations.map(anno => ({
                    ...anno,
                    type: setupType === "Oriented Bounding Box" ? 'obbox' : anno.type,
                    rotation: anno.rotation || 0,
                    isPreannotation: false // Flag for regular annotations
                }));
                loadedPreannotations = result.preannotations.map(preanno => ({
                    ...preanno,
                    type: setupType === "Oriented Bounding Box" ? 'obbox' : preanno.type,
                    rotation: preanno.rotation || 0,
                    confidence: preanno.confidence,
                    isPreannotation: true // Flag for preannotations
                }));
                isReviewed = result.reviewed || false;
                console.log('Fetched Annotations:', loadedAnnotations);
                console.log('Fetched Preannotations:', loadedPreannotations);
                console.log('Reviewed:', isReviewed);
            } else {
                console.error('Failed to fetch annotations:', result.error);
            }
        } catch (error) {
            console.error('Error fetching annotations:', error);
        }

        // Combine into a single array
        const allAnnotations = [...loadedAnnotations, ...loadedPreannotations];
        
        if (setupType === 'Classification') {
            setAnnotations(allAnnotations);
            setSelectedAnnotation(null);
            if (allAnnotations.length > 0) {
                setSelectedLabel(allAnnotations[0].label);
                // Filter out preannotations if needed, or handle confidence
                const preanno = loadedPreannotations[0];
                if (preanno && preanno.confidence >= confidenceThreshold) {
                    // Optionally suggest preannotation, but for now, use loaded annotation
                }
            } else {
                setSelectedLabel(null);
            }
            updateClassTags(); // Refresh UI with selected label
        } else {
            setAnnotations(allAnnotations);

            // Select the first annotation to show handles
            setSelectedAnnotation(allAnnotations.length > 0 ? allAnnotations[0] : null);
            updateTagHighlights();
        }
        
        const cachedAnnotations = annotationCache[imageKey] || [];
        if (cachedAnnotations.length > 0) {
            const updatedCachedAnnotations = cachedAnnotations.map(anno => ({
                ...anno,
                type: setupType === "Oriented Bounding Box" ? 'obbox' : anno.type,
                rotation: anno.rotation || 0,
                isPreannotation: anno.isPreannotation || false // Preserve flag if cached
            }));
            if (setupType === 'Classification') {
                setAnnotations(updatedCachedAnnotations);
                setSelectedAnnotation(null);
                if (updatedCachedAnnotations.length > 0) {
                    setSelectedLabel(updatedCachedAnnotations[0].label);
                    updateClassTags();
                } else {
                    setSelectedLabel(null);
                }
            } else {
                setAnnotations(updatedCachedAnnotations);
                setSelectedAnnotation(updatedCachedAnnotations.length > 0 ? updatedCachedAnnotations[0] : null);
                console.log('Using cached annotations:', updatedCachedAnnotations);
            }
        }

        setUndoStack({
            ...undoStack,
            [imageKey]: undoStack[imageKey] || []
        });

        resizeCanvas();

        const filename = imageKey.split('/').pop();
        const isAnnotated = loadedAnnotations.length > 0 || isReviewed;
        const isPreannotated = loadedPreannotations.length > 0 && !isAnnotated;
        updateAnnotationStatus(imageKey, isAnnotated, isPreannotated);

        const statusElement = document.querySelector(`[data-id="${filename}"] .image-status`);
        if (statusElement) {
            statusElement.textContent = isAnnotated ? 'Annotated' : (isPreannotated ? 'Pre-Annotated' : 'Not Annotated');
            statusElement.dataset.annotated = isAnnotated ? 'true' : 'false';
            statusElement.dataset.preannotated = isPreannotated ? 'true' : 'false';
        }

        document.querySelector('.image-info').textContent =
            `${filename} | Resolution: ${currentImage.width}x${currentImage.height}`;
        drawImage();

        document.querySelectorAll('.thumbnail-row').forEach(row => row.classList.remove('selected'));
        const annotationRow = document.querySelector(`.thumbnail-row[data-id="${filename}"]`);
        if (annotationRow) {
            annotationRow.classList.add('selected');
            annotationRow.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        } else {
            console.warn(`No thumbnail-row found with data-id: ${filename}`);
        }
    };

    img.src = imageKey;

    document.querySelectorAll('.grid-card').forEach(card => card.classList.remove('selected'));
    const gridCard = imgElement.closest('.grid-card');
    if (gridCard) gridCard.classList.add('selected');
}

export function resizeCanvas() {
    if (!currentImage || !currentImageKey) return;
    const container = document.querySelector('.image-container');
    if (!container) {
        console.error('Container element not found');
        return;
    }
    const maxWidth = container.clientWidth * 0.9;
    const maxHeight = container.clientHeight * 0.9;
    const aspectRatio = currentImage.width / currentImage.height;
    if (currentImage.width / currentImage.height > maxWidth / maxHeight) {
        canvas.width = maxWidth;
        canvas.height = maxWidth / aspectRatio;
        viewport.minZoom = 0.9 * maxWidth / currentImage.width;
    } else {
        canvas.height = maxHeight;
        canvas.width = maxHeight * aspectRatio;
        viewport.minZoom = 0.9 * maxHeight / currentImage.height;
    }
    viewport.zoom = Math.max(viewport.minZoom, viewport.zoom);
    resetView();
}