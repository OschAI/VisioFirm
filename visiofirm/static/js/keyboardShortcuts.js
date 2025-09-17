// Updated keyboardShortcuts.js with additional check for annotation-view visibility

import {
    selectedAnnotation,
    setupType,
    annotations,
    undoStack,
    currentAnnotation,
    mode,
    currentImageIndex,
    thumbnailImages,
    currentImage,
    viewport,
    currentImageKey,
    setSelectedAnnotation,
    setSelectedPointIndex,
    setAnnotations,
    setCurrentAnnotation,
    setMode,
    clipboardImageResolution,
    setClipboardImageResolution,
    setIsRotating,
    isRotating
} from './globals.js';
import { drawImage, resetView } from './annotationDrawing.js';
import { selectImage } from './imageHandling.js';
import { pushToUndoStack, clampToImageBounds } from './annotationCore.js';

export function initKeyboardShortcuts() {
    document.addEventListener('keydown', (e) => {
        // Check if we are in annotation-view; if not, skip all shortcuts
        const annotationView = document.getElementById('annotation-view');
        if (!annotationView || !annotationView.classList.contains('show')) {
            return;
        }

        // Skip all custom shortcuts if focus is on an input, textarea, or contenteditable element.
        // This allows default browser behavior (e.g., typing, arrow navigation in text) without interference.
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.isContentEditable) {
            return; // Do nothing; let the default key behavior happen.
        }

        if (e.ctrlKey && e.key === 'a') {
            e.preventDefault();
            setSelectedAnnotation(null);
            setSelectedPointIndex(-1);
            drawImage();
        }
        else if (e.ctrlKey && e.key === 'c') {
            e.preventDefault();
            if (selectedAnnotation) {
                const copyText = JSON.stringify(selectedAnnotation);
                navigator.clipboard.writeText(copyText).then(() => {
                    setClipboardImageResolution({ width: currentImage.width, height: currentImage.height });
                    console.log('Annotation copied to clipboard');
                }).catch(err => {
                    console.error('Failed to copy annotation: ', err);
                });
            }
        }
        else if (e.ctrlKey && e.key === 'v') {
            e.preventDefault();
            navigator.clipboard.readText().then(text => {
                try {
                    const pastedAnnotation = JSON.parse(text);
                    if (pastedAnnotation && pastedAnnotation.type) {
                        pushToUndoStack();
                        const scaledAnnotation = scaleAnnotation(
                            pastedAnnotation,
                            clipboardImageResolution.width, clipboardImageResolution.height,
                            currentImage.width, currentImage.height
                        );
                        scaledAnnotation.x += 10;
                        scaledAnnotation.y += 10;
                        setAnnotations([...annotations, scaledAnnotation]);
                        setSelectedAnnotation(scaledAnnotation);
                        drawImage();
                    }
                } catch (err) {
                    console.error('Failed to paste annotation: ', err);
                }
            }).catch(err => {
                console.error('Failed to read clipboard contents: ', err);
            });
        }
        else if (e.ctrlKey && e.key === 'd') {
            e.preventDefault();
            if (selectedAnnotation) {
                pushToUndoStack();
                const duplicate = scaleAnnotation(
                    selectedAnnotation,
                    currentImage.width, currentImage.height,
                    currentImage.width, currentImage.height
                );
                duplicate.x += 0.3 * duplicate.x;
                duplicate.y += 0.3 * duplicate.y;
                if (duplicate.type === 'rect' || duplicate.type === 'obbox') {
                    duplicate.x = Math.max(0, Math.min(duplicate.x, currentImage.width - duplicate.width));
                    duplicate.y = Math.max(0, Math.min(duplicate.y, currentImage.height - duplicate.height));
                } else if (duplicate.type === 'polygon') {
                    duplicate.points = duplicate.points.map(p => clampToImageBounds(p));
                }
                setAnnotations([...annotations, duplicate]);
                setSelectedAnnotation(duplicate);
                drawImage();
            }
        }
        else if (e.ctrlKey && e.key === 'z' && currentImageKey && undoStack[currentImageKey]?.length > 0) {
            e.preventDefault();
            const newStack = undoStack[currentImageKey];
            const lastState = newStack.pop();
            setAnnotations(lastState);
            setSelectedAnnotation(lastState.length > 0 ? lastState[lastState.length - 1] : null);
            drawImage();
        }
        else if (e.key === 'Delete' && selectedAnnotation) {
            e.preventDefault();
            pushToUndoStack();
            const newAnnotations = annotations.filter(a => a !== selectedAnnotation);
            setAnnotations(newAnnotations);
            setSelectedAnnotation(newAnnotations.length > 0 ? newAnnotations[newAnnotations.length - 1] : null);
            drawImage();
        }
        else if (e.key === 'Escape' && currentAnnotation) {
            e.preventDefault();
            if (currentAnnotation.points?.length > 2) {
                currentAnnotation.closed = true;
                pushToUndoStack();
                setAnnotations([...annotations, currentAnnotation]);
                setSelectedAnnotation(currentAnnotation);
            }
            setCurrentAnnotation(null);
            drawImage();
        }
        else if (e.key === 'r' && setupType === "Oriented Bounding Box" && selectedAnnotation && (selectedAnnotation.type === 'rect' || selectedAnnotation.type === 'obbox')) {
            e.preventDefault();
            setIsRotating(!isRotating);
            drawImage();
        }
        else if (e.key === 'r' && !e.ctrlKey && !e.altKey && !e.shiftKey) {
            e.preventDefault();
            if (setupType !== "Segmentation") {
                setMode('rect');
                setCurrentAnnotation(null);
                drawImage();
            }
        }
        else if (e.ctrlKey && e.key === 's') {
            e.preventDefault();
            document.getElementById('approve-btn').click();
        }
        else if (!e.ctrlKey && e.key === 'ArrowRight' && currentImageIndex < thumbnailImages.length - 1) {
            e.preventDefault();
            selectImage(thumbnailImages[currentImageIndex + 1], currentImageIndex + 1);
        }
        else if (!e.ctrlKey && e.key === 'ArrowLeft' && currentImageIndex > 0) {
            e.preventDefault();
            selectImage(thumbnailImages[currentImageIndex - 1], currentImageIndex - 1);
        }
        else if (e.ctrlKey && selectedAnnotation && ['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(e.key)) {
            e.preventDefault();
            pushToUndoStack();
            const nudge = 1 / viewport.zoom;
            const updatedAnnotation = { ...selectedAnnotation };
            if (updatedAnnotation.type === 'rect' || updatedAnnotation.type === 'obbox') {
                if (e.key === 'ArrowUp') updatedAnnotation.y -= nudge;
                else if (e.key === 'ArrowDown') updatedAnnotation.y += nudge;
                else if (e.key === 'ArrowLeft') updatedAnnotation.x -= nudge;
                else if (e.key === 'ArrowRight') updatedAnnotation.x += nudge;
            } else if (updatedAnnotation.type === 'polygon') {
                updatedAnnotation.points = updatedAnnotation.points.map(p => {
                    if (e.key === 'ArrowUp') return { x: p.x, y: p.y - nudge };
                    else if (e.key === 'ArrowDown') return { x: p.x, y: p.y + nudge };
                    else if (e.key === 'ArrowLeft') return { x: p.x - nudge, y: p.y };
                    else if (e.key === 'ArrowRight') return { x: p.x + nudge, y: p.y };
                    return p;
                });
            }
            setAnnotations(annotations.map(a => a === selectedAnnotation ? updatedAnnotation : a));
            setSelectedAnnotation(updatedAnnotation);
            drawImage();
        }
        else if (e.key === 'p' && !e.ctrlKey && !e.altKey && !e.shiftKey) {
            e.preventDefault();
            if (setupType === "Segmentation") {
                setMode('polygon');
                setSelectedAnnotation(null);
                setCurrentAnnotation(null);
                drawImage();
            }
        }
        else if (e.key === 's' && !e.ctrlKey && !e.altKey && !e.shiftKey) {
            e.preventDefault();
            setMode('select');
            drawImage();
        }
        else if (e.key === ' ' && !e.ctrlKey && !e.altKey && !e.shiftKey) {
            e.preventDefault();
            resetView();
        }
        else if (e.key === 'g' && !e.ctrlKey && !e.altKey && !e.shiftKey) {
            e.preventDefault();
            import('./globals.js').then(module => {
                module.setGridEnabled(!module.gridEnabled);
                drawImage();
            });
        }
    });

    document.addEventListener('keyup', (e) => {
        // Check if we are in annotation-view; if not, skip
        const annotationView = document.getElementById('annotation-view');
        if (!annotationView || !annotationView.classList.contains('show')) {
            return;
        }

        // Apply the same input focus check for keyup events as well.
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.isContentEditable) {
            return;
        }

        if (e.key === 'r' && setupType === "Oriented Bounding Box") {
            setIsRotating(false);
            drawImage();
        }
    });
}

function scaleAnnotation(annotation, sourceWidth, sourceHeight, targetWidth, targetHeight) {
    const scaleX = targetWidth / sourceWidth;
    const scaleY = targetHeight / sourceHeight;
    const scaled = JSON.parse(JSON.stringify(annotation));
    if (scaled.type === 'rect' || scaled.type === 'obbox') {
        scaled.x *= scaleX;
        scaled.y *= scaleY;
        scaled.width *= scaleX;
        scaled.height *= scaleY;
    } else if (scaled.type === 'polygon') {
        scaled.points = scaled.points.map(p => ({
            x: p.x * scaleX,
            y: p.y * scaleY
        }));
    }
    return scaled;
}