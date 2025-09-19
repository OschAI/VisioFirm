import { globals } from './video_globals.js';
import {
    toImageCoords,
    clampToImageBounds,
    findAnnotationByPoint,
    findHandleIndex,
    findClosestPolygonSegment,
    resizeAnnotation,
    clampAnnotationToBounds,
    clampPosition,
    toCanvasCoords
} from './video_utils.js';
import { drawTimeline } from './timeline_helpers.js';

export function setupAnnotationInteractions(drawImage, pushToUndoStack, setSelectedAnnotation, clampView) {
    const canvas = globals.canvas;
    if (!canvas) {
        console.warn('Canvas not found for annotation interactions');
        return;
    }

    // Ensure previewPoint is initialized
    if (globals.previewPoint === undefined) {
        globals.previewPoint = null;
    }

    function findClosestHandle(canvasX, canvasY, annotations, viewport) {
        let closestDist = Infinity;
        let closestAnn = null;
        let closestIndex = -1;
        const threshold = 20; // Increased pixels in canvas space for larger uncertainty area

        // Check finished annotations
        annotations.forEach(ann => {
            let handles = [];
            if (ann.type === 'rect') {
                handles = [
                    { x: ann.x, y: ann.y },
                    { x: ann.x + ann.width, y: ann.y },
                    { x: ann.x, y: ann.y + ann.height },
                    { x: ann.x + ann.width, y: ann.y + ann.height }
                ];
            } else if (ann.type === 'polygon') {
                handles = ann.points.map(p => ({ x: p.x, y: p.y }));
            }

            handles.forEach((point, idx) => {
                const canvasPoint = toCanvasCoords(point.x, point.y, viewport);
                const dist = Math.hypot(canvasPoint.x - canvasX, canvasPoint.y - canvasY);
                if (dist < closestDist) {
                    closestDist = dist;
                    closestAnn = ann;
                    closestIndex = idx;
                }
            });
        });

        // Also check current unfinished polygon if applicable
        if (globals.currentAnnotation && globals.currentAnnotation.type === 'polygon' && !globals.currentAnnotation.closed) {
            const handles = globals.currentAnnotation.points.map(p => ({ x: p.x, y: p.y }));
            handles.forEach((point, idx) => {
                const canvasPoint = toCanvasCoords(point.x, point.y, viewport);
                const dist = Math.hypot(canvasPoint.x - canvasX, canvasPoint.y - canvasY);
                if (dist < closestDist) {
                    closestDist = dist;
                    closestAnn = globals.currentAnnotation;
                    closestIndex = idx;
                }
            });
        }

        if (closestDist < threshold) {
            return { ann: closestAnn, index: closestIndex };
        }
        return null;
    }

    canvas.addEventListener('mousedown', e => {
        console.log('=== Mousedown fired ===', {
            button: e.button,
            target: e.target.id || e.target.tagName,  // Confirm it's the canvas
            clientX: e.clientX,
            clientY: e.clientY,
            mode: globals.mode,
            selectedClass: globals.selectedClass,
            currentAnnotationExists: !!globals.currentAnnotation
        });

        const rect = canvas.getBoundingClientRect();
        const canvasX = e.clientX - rect.left;
        const canvasY = e.clientY - rect.top;
        let imgPoint = toImageCoords(canvasX, canvasY, globals.viewport);
        imgPoint = clampToImageBounds(imgPoint, globals.currentVideo);
        console.log('Computed image point:', { x: imgPoint.x.toFixed(1), y: imgPoint.y.toFixed(1) });

        // Handle right-click for translation in any mode
        if (e.button === 2) {
            console.log('Right-click detected - skipping draw');
            const ann = findAnnotationByPoint(imgPoint, globals.annotations);
            if (ann) {
                pushToUndoStack();
                globals.selectedAnnotation = ann;
                globals.isTranslating = true;
                globals.lastX = canvasX;
                globals.lastY = canvasY;
            }
            e.preventDefault();
            drawImage();
            return;  // Prevent drawing on right-click
        }

        // Handle left-click logic: prioritize existing annotation modification in any mode
        if (e.button === 0) {
            const closestHandle = findClosestHandle(canvasX, canvasY, globals.annotations, globals.viewport);
            if (closestHandle) {
                const { ann, index } = closestHandle;
                console.log('Hit closest handle, enabling point drag');
                pushToUndoStack();
                globals.selectedAnnotation = ann;
                globals.selectedPointIndex = index;
                globals.isDragging = true;
                globals.lastX = canvasX;
                globals.lastY = canvasY;
                drawImage();
                return;
            }

            const ann = findAnnotationByPoint(imgPoint, globals.annotations);
            if (ann) {
                console.log('Hit existing annotation (no handle), enabling translation');
                pushToUndoStack();
                globals.selectedAnnotation = ann;
                globals.isTranslating = true;
                globals.lastX = canvasX;
                globals.lastY = canvasY;
                drawImage();
                return;  // Skip mode-specific logic
            }

            // No hit: handle mode-specific actions or deselection
            if (globals.mode === 'select') {
                console.log('In select mode - no hit, deselecting');
                globals.selectedAnnotation = null;
            } else if (globals.mode === 'rect') {
                console.log('In rect mode - starting rect');
                if (!globals.selectedClass) {
                    console.warn('Cannot start rect: No class selected');
                    return;
                }
                pushToUndoStack();
                globals.selectedAnnotation = null;  // Deselect any previous
                globals.currentAnnotation = { type: 'rect', x: imgPoint.x, y: imgPoint.y, width: 0, height: 0, label: globals.selectedClass };
                globals.annotations.push(globals.currentAnnotation);
                globals.isDrawing = true;
                // Record starting image coords for total extent calculation
                globals.startImgX = imgPoint.x;
                globals.startImgY = imgPoint.y;
                globals.lastX = canvasX;
                globals.lastY = canvasY;
            } else if (globals.mode === 'polygon') {
                console.log('In polygon mode - adding point');
                if (!globals.selectedClass) {
                    console.warn('Cannot add polygon point: No class selected');
                    return;
                }
                const isNewAnnotation = !globals.currentAnnotation;
                if (isNewAnnotation) {
                    console.log('Creating new polygon annotation');
                    pushToUndoStack();  // Only on first point
                    globals.selectedAnnotation = null;  // Deselect any previous
                    globals.currentAnnotation = { type: 'polygon', points: [], closed: false, label: globals.selectedClass };
                }
                globals.currentAnnotation.points.push(imgPoint);
                console.log('Added point to polygon (total points now:', globals.currentAnnotation.points.length, '):', { x: imgPoint.x.toFixed(1), y: imgPoint.y.toFixed(1) });
                globals.lastX = canvasX;
                globals.lastY = canvasY;

                // Check for closure if at least 3 points
                if (globals.currentAnnotation.points.length >= 3) {
                    const firstPoint = globals.currentAnnotation.points[0];
                    const dist = Math.hypot(imgPoint.x - firstPoint.x, imgPoint.y - firstPoint.y);
                    console.log('Checking closure: dist to first point =', dist.toFixed(1));
                    if (dist < 15) {  // Increased threshold for smoother closure
                        console.log('Closing polygon!');
                        globals.currentAnnotation.closed = true;
                        globals.annotations.push(globals.currentAnnotation);
                        globals.currentAnnotation = null;
                        globals.previewPoint = null;
                        // Update map and timeline after completion
                        if (globals.currentFrameIndex !== undefined) {
                            globals.annotationMap[globals.currentFrameIndex] = JSON.parse(JSON.stringify(globals.annotations));
                        }
                        globals.annotations.forEach(anno => {
                            if (anno.label && !(anno.label in globals.classToRow)) {
                                globals.classToRow[anno.label] = globals.nextRow++;
                            }
                        });
                        drawTimeline();
                    }
                }
                globals.previewPoint = null;
            } else {
                console.log('Unhandled mode in mousedown:', globals.mode);
            }
        }
        drawImage();
        console.log('=== Mousedown end ===');
    });

    canvas.addEventListener('mousemove', e => {
        const rect = canvas.getBoundingClientRect();
        const canvasX = e.clientX - rect.left;
        const canvasY = e.clientY - rect.top;
        let imgPoint = toImageCoords(canvasX, canvasY, globals.viewport);
        imgPoint = clampToImageBounds(imgPoint, globals.currentVideo);

        if (globals.isDrawing && globals.currentAnnotation) {
            if (globals.currentAnnotation.type === 'rect') {
                const dx = imgPoint.x - globals.startImgX;
                const dy = imgPoint.y - globals.startImgY;
                globals.currentAnnotation.x = Math.min(globals.startImgX, imgPoint.x);
                globals.currentAnnotation.y = Math.min(globals.startImgY, imgPoint.y);
                globals.currentAnnotation.width = Math.abs(dx);
                globals.currentAnnotation.height = Math.abs(dy);
                clampAnnotationToBounds(globals.currentAnnotation, globals.currentVideo);
            }
            drawImage();
        } else if (globals.mode === 'polygon' && globals.currentAnnotation && !globals.currentAnnotation.closed) {
            // Set preview point for line preview to mouse
            globals.previewPoint = imgPoint;
            drawImage();
        } else if (globals.isDragging && globals.selectedAnnotation) {
            const dx = (canvasX - globals.lastX) / globals.viewport.zoom;
            const dy = (canvasY - globals.lastY) / globals.viewport.zoom;
            const handleIndex = globals.selectedPointIndex;
            resizeAnnotation(globals.selectedAnnotation, handleIndex, dx, dy);
            if (globals.selectedAnnotation.type === 'polygon' && handleIndex >= 0) {
                globals.selectedAnnotation.points[handleIndex] = clampToImageBounds(globals.selectedAnnotation.points[handleIndex], globals.currentVideo);
            } else {
                clampPosition(globals.selectedAnnotation, globals.currentVideo);
            }
            globals.lastX = canvasX;
            globals.lastY = canvasY;
            drawImage();
        } else if (globals.isTranslating && globals.selectedAnnotation) {
            const dx = (canvasX - globals.lastX) / globals.viewport.zoom;
            const dy = (canvasY - globals.lastY) / globals.viewport.zoom;
            if (globals.selectedAnnotation.type === 'rect') {
                globals.selectedAnnotation.x += dx;
                globals.selectedAnnotation.y += dy;
                // Inline clamping to prevent shrinking: adjust position only, keep size
                const vw = globals.currentVideo.videoWidth;
                const vh = globals.currentVideo.videoHeight;
                const w = globals.selectedAnnotation.width;
                const h = globals.selectedAnnotation.height;
                if (globals.selectedAnnotation.x < 0) {
                    globals.selectedAnnotation.x = 0;
                }
                if (globals.selectedAnnotation.y < 0) {
                    globals.selectedAnnotation.y = 0;
                }
                if (globals.selectedAnnotation.x + w > vw) {
                    globals.selectedAnnotation.x = vw - w;
                }
                if (globals.selectedAnnotation.y + h > vh) {
                    globals.selectedAnnotation.y = vh - h;
                }
            } else if (globals.selectedAnnotation.type === 'polygon') {
                // Translate all points
                globals.selectedAnnotation.points.forEach(p => {
                    p.x += dx;
                    p.y += dy;
                });
                // Aggregate shift to keep shape intact, no deformation
                const vw = globals.currentVideo.videoWidth;
                const vh = globals.currentVideo.videoHeight;
                let minX = Math.min(...globals.selectedAnnotation.points.map(p => p.x));
                let maxX = Math.max(...globals.selectedAnnotation.points.map(p => p.x));
                let minY = Math.min(...globals.selectedAnnotation.points.map(p => p.y));
                let maxY = Math.max(...globals.selectedAnnotation.points.map(p => p.y));
                if (minX < 0) {
                    const shiftX = -minX;
                    globals.selectedAnnotation.points.forEach(p => p.x += shiftX);
                }
                if (maxX > vw) {
                    const shiftX = vw - maxX;
                    globals.selectedAnnotation.points.forEach(p => p.x += shiftX);
                }
                if (minY < 0) {
                    const shiftY = -minY;
                    globals.selectedAnnotation.points.forEach(p => p.y += shiftY);
                }
                if (maxY > vh) {
                    const shiftY = vh - maxY;
                    globals.selectedAnnotation.points.forEach(p => p.y += shiftY);
                }
            }
            globals.lastX = canvasX;
            globals.lastY = canvasY;
            drawImage();
        }
        globals.lastX = canvasX;
        globals.lastY = canvasY;
    });

    window.addEventListener('mouseup', () => {
        if (globals.isDrawing) {
            if (globals.currentAnnotation && globals.currentAnnotation.type === 'rect') {
                clampAnnotationToBounds(globals.currentAnnotation, globals.currentVideo);
                if (globals.currentAnnotation.width < 1 || globals.currentAnnotation.height < 1) {
                    const index = globals.annotations.indexOf(globals.currentAnnotation);
                    if (index > -1) globals.annotations.splice(index, 1);
                } else {
                    // Only push to undo after successful draw (post-resize)
                    pushToUndoStack();
                }
                // Update map and timeline after completion
                if (globals.currentFrameIndex !== undefined) {
                    globals.annotationMap[globals.currentFrameIndex] = JSON.parse(JSON.stringify(globals.annotations));
                }
                globals.annotations.forEach(anno => {
                    if (anno.label && !(anno.label in globals.classToRow)) {
                        globals.classToRow[anno.label] = globals.nextRow++;
                    }
                });
                drawTimeline();
            }
            // Clean up start vars
            globals.startImgX = null;
            globals.startImgY = null;
            globals.currentAnnotation = null;
            globals.isDrawing = false;
            drawImage();
        }
        if (globals.isDragging) {
            globals.isDragging = false;
            globals.isRightClickEditing = false;
        }
        if (globals.isTranslating) {
            globals.isTranslating = false;
        }
    });

    // Zoom with wheel
    canvas.addEventListener('wheel', e => {
        e.preventDefault();
        const rect = canvas.getBoundingClientRect();
        const mouseX = e.clientX - rect.left;
        const mouseY = e.clientY - rect.top;
        const oldZoom = globals.viewport.zoom;
        globals.viewport.zoom *= e.deltaY < 0 ? 1.1 : 0.9;
        globals.viewport.zoom = Math.min(Math.max(globals.viewport.minZoom, globals.viewport.zoom), globals.viewport.maxZoom);
        const factor = globals.viewport.zoom / oldZoom;
        globals.viewport.x = mouseX - (mouseX - globals.viewport.x) * factor;
        globals.viewport.y = mouseY - (mouseY - globals.viewport.y) * factor;
        clampView();
        drawImage();
    });

    canvas.addEventListener('contextmenu', e => e.preventDefault());
}