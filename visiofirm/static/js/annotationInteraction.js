import { 
    canvas,
    viewport,
    currentImage,
    mode,
    annotations,
    currentAnnotation,
    isDrawing,
    isDragging,
    startX,
    startY,
    selectedAnnotation,
    selectedPointIndex,
    isRightClickEditing,
    setupType,
    setIsDrawing,
    setCurrentAnnotation,
    setIsDragging,
    setStartX,
    setStartY,
    setSelectedAnnotation,
    setSelectedPointIndex,
    setIsRightClickEditing,
    setInitialRotation,
    isRotating,
    setIsRotating,
    selectedClass,
    updateTagHighlights,
    confidenceThreshold,
    isAnnotationLabelHidden
} from './globals.js';
import { drawImage } from './annotationDrawing.js';
import { setHoveredAnnotation } from './annotationDrawing.js';
import { toImageCoords, toCanvasCoords, clampToImageBounds, pushToUndoStack, clampAnnotationToBounds } from './annotationCore.js';
import { segmentArea } from './sam.js';

export function getMousePos(canvas, e) {
    const rect = canvas.getBoundingClientRect();
    return { x: e.clientX - rect.left, y: e.clientY - rect.top };
}

export function isPointInAnnotation(point, annotation) {
    const imgPoint = toImageCoords(point.x, point.y);
    if (annotation.type === 'rect' || annotation.type === 'obbox') {
        const centerX = annotation.x + annotation.width / 2;
        const centerY = annotation.y + annotation.height / 2;
        const dx = imgPoint.x - centerX;
        const dy = imgPoint.y - centerY;
        const rad = (annotation.rotation || 0) * Math.PI / 180;
        const cos = Math.cos(rad);
        const sin = Math.sin(rad);
        const localX = dx * cos - dy * sin;
        const localY = dx * sin + dy * cos;
        const halfW = annotation.width / 2;
        const halfH = annotation.height / 2;
        return localX >= -halfW && localX <= halfW && localY >= -halfH && localY <= halfH;
    } else if (annotation.type === 'polygon') {
        let inside = false;
        for (let i = 0, j = annotation.points.length - 1; i < annotation.points.length; j = i++) {
            const xi = annotation.points[i].x, yi = annotation.points[i].y;
            const xj = annotation.points[j].x, yj = annotation.points[j].y;
            const intersect = ((yi > imgPoint.y) !== (yj > imgPoint.y)) &&
                (imgPoint.x < (xj - xi) * (imgPoint.y - yi) / (yj - yi) + xi);
            if (intersect) inside = !inside;
        }
        return inside;
    }
    return false;
}

function isAnnotationVisible(anno) {
    return (
        (!anno.isPreannotation || anno.confidence >= confidenceThreshold) &&
        !isAnnotationLabelHidden(anno.label)
    );
}

export function findSelectedAnnotation(point) {
    for (let i = annotations.length - 1; i >= 0; i--) {
        const annotation = annotations[i];
        if (!isAnnotationVisible(annotation)) continue; // Skip invisible annotations
        if (annotation.type === 'rect' || annotation.type === 'obbox') {
            const centerX = annotation.x + annotation.width / 2;
            const centerY = annotation.y + annotation.height / 2;
            const canvasCenter = toCanvasCoords(centerX, centerY);
            const halfWidth = annotation.width * viewport.zoom / 2;
            const halfHeight = annotation.height * viewport.zoom / 2;
            const rad = (annotation.rotation || 0) * Math.PI / 180;
            const corners = [
                { x: -halfWidth, y: -halfHeight },
                { x: halfWidth, y: -halfHeight },
                { x: -halfWidth, y: halfHeight },
                { x: halfWidth, y: halfHeight }
            ].map(corner => {
                const cos = Math.cos(rad);
                const sin = Math.sin(rad);
                const x = canvasCenter.x + (corner.x * cos - corner.y * sin);
                const y = canvasCenter.y + (corner.x * sin + corner.y * cos);
                return { x, y };
            });
            const edges = [
                { x: 0, y: -halfHeight },
                { x: 0, y: halfHeight },
                { x: -halfWidth, y: 0 },
                { x: halfWidth, y: 0 }
            ].map(edge => {
                const cos = Math.cos(rad);
                const sin = Math.sin(rad);
                const x = canvasCenter.x + (edge.x * cos - edge.y * sin);
                const y = canvasCenter.y + (edge.x * sin + edge.y * cos);
                return { x, y };
            });
            if (setupType === "Oriented Bounding Box") {
                const rotationHandle = { x: 0, y: -halfHeight - 20/viewport.zoom };
                const cos = Math.cos(rad);
                const sin = Math.sin(rad);
                const rotX = canvasCenter.x + (rotationHandle.x * cos - rotationHandle.y * sin);
                const rotY = canvasCenter.y + (rotationHandle.x * sin + rotationHandle.y * cos);
                const distance = Math.sqrt(Math.pow(point.x - rotX, 2) + Math.pow(point.y - rotY, 2));
                if (distance < 12) {
                    setSelectedAnnotation(annotation);
                    updateTagHighlights();
                    setSelectedPointIndex(-2);
                    setIsRotating(true);
                    return annotation;
                }
            }
            for (let j = 0; j < corners.length; j++) {
                const distance = Math.sqrt(Math.pow(point.x - corners[j].x, 2) + Math.pow(point.y - corners[j].y, 2));
                if (distance < 12) {
                    setSelectedAnnotation(annotation);
                    updateTagHighlights();
                    setSelectedPointIndex(j);
                    return annotation;
                }
            }
            for (let j = 0; j < edges.length; j++) {
                const distance = Math.sqrt(Math.pow(point.x - edges[j].x, 2) + Math.pow(point.y - edges[j].y, 2));
                if (distance < 12) {
                    setSelectedAnnotation(annotation);
                    updateTagHighlights();
                    setSelectedPointIndex(j + 4);
                    return annotation;
                }
            }
        } else if (annotation.type === 'polygon') {
            for (let j = 0; j < annotation.points.length; j++) {
                const p = toCanvasCoords(annotation.points[j].x, annotation.points[j].y);
                const distance = Math.sqrt(Math.pow(point.x - p.x, 2) + Math.pow(point.y - p.y, 2));
                if (distance < 12) {
                    setSelectedAnnotation(annotation);
                    updateTagHighlights();
                    setSelectedPointIndex(j);
                    return annotation;
                }
            }
        }
    }
    for (let i = annotations.length - 1; i >= 0; i--) {
        const annotation = annotations[i];
        if (!isAnnotationVisible(annotation)) continue; // Skip invisible annotations
        if (isPointInAnnotation(point, annotation)) {
            setSelectedAnnotation(annotation);
            updateTagHighlights();
            setSelectedPointIndex(-1);
            return annotation;
        }
    }
    return null;
}

function findHoveredAnnotation(point) {
    for (let i = annotations.length - 1; i >= 0; i--) {
        const annotation = annotations[i];
        if (!isAnnotationVisible(annotation)) continue; // Skip invisible annotations
        if (isPointInAnnotation(point, annotation)) {
            return annotation;
        }
    }
    return null;
}

function findClosestPolygonSegment(polygon, point) {
    let minDist = Infinity;
    let closestSegment = -1;
    for (let i = 0; i < polygon.points.length - 1; i++) {
        const p1 = polygon.points[i];
        const p2 = polygon.points[i + 1];
        const dist = pointLineDistance(point, p1, p2);
        if (dist < minDist) {
            minDist = dist;
            closestSegment = i;
        }
    }
    if (polygon.closed && polygon.points.length > 2) {
        const dist = pointLineDistance(point, polygon.points[polygon.points.length - 1], polygon.points[0]);
        if (dist < minDist) {
            minDist = dist;
            closestSegment = polygon.points.length - 1;
        }
    }
    return closestSegment;
}

function pointLineDistance(point, lineStart, lineEnd) {
    const dx = lineEnd.x - lineStart.x;
    const dy = lineEnd.y - lineStart.y;
    const lenSquared = dx * dx + dy * dy;
    if (lenSquared === 0) return Math.sqrt(Math.pow(point.x - lineStart.x, 2) + Math.pow(point.y - lineStart.y, 2));
    let t = ((point.x - lineStart.x) * dx + (point.y - lineStart.y) * dy) / lenSquared;
    t = Math.max(0, Math.min(1, t));
    const nearestX = lineStart.x + t * dx;
    const nearestY = lineStart.y + t * dy;
    return Math.sqrt(Math.pow(point.x - nearestX, 2) + Math.pow(point.y - nearestY, 2));
}

function handleMouseDown(e) {
    const pos = getMousePos(canvas, e);
    const imgPos = toImageCoords(pos.x, pos.y);

    if (mode === 'magic' && e.button === 0) {
        const clampedPos = clampToImageBounds(imgPos);
        segmentArea(clampedPos);
        return;
    }

    if (e.button === 2 && !e.shiftKey) {
        const clickedAnnotation = findSelectedAnnotation(pos);
        if (clickedAnnotation) {
            setSelectedAnnotation(clickedAnnotation);
            updateTagHighlights();
            setIsDragging(true);
            setIsRightClickEditing(true);
            setStartX(pos.x);
            setStartY(pos.y);
            pushToUndoStack();
            drawImage();
            return;
        } else if (selectedAnnotation && e.ctrlKey && selectedAnnotation.type === 'polygon') {
            const segmentIndex = findClosestPolygonSegment(selectedAnnotation, imgPos);
            if (segmentIndex >= 0) {
                pushToUndoStack();
                selectedAnnotation.points.splice(segmentIndex + 1, 0, clampToImageBounds(imgPos));
            } else {
                pushToUndoStack();
                selectedAnnotation.points.push(clampToImageBounds(imgPos));
            }
            drawImage();
            return;
        }
    }

    if (e.shiftKey) {
        setIsDragging(true);
        setSelectedAnnotation(null);
        updateTagHighlights();
        setStartX(pos.x - viewport.x);
        setStartY(pos.y - viewport.y);
        return;
    }

    if (mode === 'rect' && e.button === 0) {
        setIsDrawing(true);
        const clampedPos = clampToImageBounds(imgPos);
        if (e.altKey && setupType === "Oriented Bounding Box") {
            if (selectedAnnotation && (selectedAnnotation.type === 'rect' || selectedAnnotation.type === 'obbox')) {
                setIsDragging(true);
                setStartX(pos.x);
                setStartY(pos.y);
                return;
            }
        } else if (e.ctrlKey && e.shiftKey) {
            const defaultSize = 50;
            const newAnnotation = {
                type: setupType === "Oriented Bounding Box" ? 'obbox' : 'rect',
                x: clampedPos.x - defaultSize / 2,
                y: clampedPos.y - defaultSize / 2,
                width: defaultSize,
                height: defaultSize,
                rotation: 0,
                label: selectedClass
            };
            pushToUndoStack();
            annotations.push(newAnnotation);
            updateTagHighlights();
            setCurrentAnnotation(null);
            setIsDrawing(false);
            drawImage();
        } else {
            setCurrentAnnotation({
                type: setupType === "Oriented Bounding Box" ? 'obbox' : 'rect',
                origX: clampedPos.x,
                origY: clampedPos.y,
                x: clampedPos.x,
                y: clampedPos.y,
                width: 0,
                height: 0,
                rotation: 0,
                label: selectedClass
            });
        }
    }

    else if (mode === 'polygon' && e.button === 0) {
        if (!currentAnnotation) {
            setCurrentAnnotation({
                type: 'polygon',
                points: [clampToImageBounds(imgPos)],
                closed: false,
                label: selectedClass
            });
        } else {
            const firstPoint = currentAnnotation.points[0];
            const firstCanvasPoint = toCanvasCoords(firstPoint.x, firstPoint.y);
            if (Math.abs(pos.x - firstCanvasPoint.x) < 10 && Math.abs(pos.y - firstCanvasPoint.y) < 10) {
                currentAnnotation.closed = true;
                if (currentAnnotation.points.length > 2) {
                    pushToUndoStack();
                    annotations.push(currentAnnotation);
                    updateTagHighlights();
                }
                setCurrentAnnotation(null);
            } else {
                currentAnnotation.points.push(clampToImageBounds(imgPos));
            }
        }
        drawImage();
    }

    else if (mode === 'select' && e.button === 0) {
        const clickedAnnotation = findSelectedAnnotation(pos);
        if (clickedAnnotation) {
            setSelectedAnnotation(clickedAnnotation);
            updateTagHighlights();
            setIsDragging(true);
            setStartX(pos.x);
            setStartY(pos.y);
            pushToUndoStack();
            if ((clickedAnnotation.type === 'rect' || clickedAnnotation.type === 'obbox') && selectedPointIndex >= 0) {
                const theta = (clickedAnnotation.rotation || 0) * Math.PI / 180;
                const cosTheta = Math.cos(theta);
                const sinTheta = Math.sin(theta);
                const centerX = clickedAnnotation.x + clickedAnnotation.width / 2;
                const centerY = clickedAnnotation.y + clickedAnnotation.height / 2;
                const localCorners = [
                    { x: -clickedAnnotation.width / 2, y: -clickedAnnotation.height / 2 },
                    { x: clickedAnnotation.width / 2, y: -clickedAnnotation.height / 2 },
                    { x: clickedAnnotation.width / 2, y: clickedAnnotation.height / 2 },
                    { x: -clickedAnnotation.width / 2, y: clickedAnnotation.height / 2 }
                ];
                const imageCorners = localCorners.map(local => {
                    const dx = local.x * cosTheta - local.y * sinTheta;
                    const dy = local.x * sinTheta + local.y * cosTheta;
                    return { x: centerX + dx, y: centerY + dy };
                });
                setInitialCorners(imageCorners);
                setInitialRotation(clickedAnnotation.rotation || 0);
            }
        } else {
            setSelectedAnnotation(null);
            updateTagHighlights();
            setSelectedPointIndex(-1);
        }
        drawImage();
    }
}

function handleMouseMove(e) {
    const pos = getMousePos(canvas, e);
    const imgPos = toImageCoords(pos.x, pos.y);

    // Update hovered annotation for tooltip
    const hovered = findHoveredAnnotation(pos);
    setHoveredAnnotation(hovered);
    drawImage();

    if (isRotating && selectedAnnotation && (selectedAnnotation.type === 'rect' || selectedAnnotation.type === 'obbox')) {
        const center = {
            x: selectedAnnotation.x + selectedAnnotation.width / 2,
            y: selectedAnnotation.y + selectedAnnotation.height / 2
        };
        const angle = Math.atan2(imgPos.y - center.y, imgPos.x - center.x) * 180 / Math.PI + 90;
        selectedAnnotation.rotation = angle;
        drawImage();
        return;
    }
    else if (e.shiftKey && isDragging) {
        viewport.x = pos.x - startX;
        viewport.y = pos.y - startY;
        drawImage();
    }
    else if (mode === 'rect' && isDrawing && currentAnnotation) {
        const clampedPos = clampToImageBounds(imgPos);
        const newX = Math.min(currentAnnotation.origX, clampedPos.x);
        const newY = Math.min(currentAnnotation.origY, clampedPos.y);
        const newWidth = Math.abs(clampedPos.x - currentAnnotation.origX);
        const newHeight = Math.abs(clampedPos.y - currentAnnotation.origY);
        currentAnnotation.x = newX;
        currentAnnotation.y = newY;
        currentAnnotation.width = newWidth;
        currentAnnotation.height = newHeight;
        drawImage();
    }
    else if (isDragging && selectedAnnotation) {
        const dx = (pos.x - startX) / viewport.zoom;
        const dy = (pos.y - startY) / viewport.zoom;

        if (isRightClickEditing || mode === 'select') {
            if (selectedAnnotation.type === 'rect' || selectedAnnotation.type === 'obbox') {
                if (selectedPointIndex >= 0) {
                    const clampedPos = clampToImageBounds(imgPos);

                    if (setupType === "Oriented Bounding Box") {
                        const centerX = selectedAnnotation.x + selectedAnnotation.width / 2;
                        const centerY = selectedAnnotation.y + selectedAnnotation.height / 2;
                        const rad = (selectedAnnotation.rotation || 0) * Math.PI / 180;
                        const cos = Math.cos(rad);
                        const sin = Math.sin(rad);
                    
                        const dxMouse = clampedPos.x - centerX;
                        const dyMouse = clampedPos.y - centerY;
                        const localX = dxMouse * cos + dyMouse * sin;
                        const localY = -dxMouse * sin + dyMouse * cos;
                    
                        const halfW = selectedAnnotation.width / 2;
                        const halfH = selectedAnnotation.height / 2;
                        const corners = [
                            { x: -halfW, y: -halfH },
                            { x: halfW, y: -halfH },
                            { x: halfW, y: halfH },
                            { x: -halfW, y: halfH }
                        ];
                    
                        let newWidth = selectedAnnotation.width;
                        let newHeight = selectedAnnotation.height;
                        let oppositePoint;
                    
                        if (selectedPointIndex < 4) {
                            let effectiveIndex;
                            if (selectedPointIndex === 2) {
                                effectiveIndex = 3;
                            } else if (selectedPointIndex === 3) {
                                effectiveIndex = 2;
                            } else {
                                effectiveIndex = selectedPointIndex;
                            }
                    
                            const oppositeIndex = (effectiveIndex + 2) % 4;
                            oppositePoint = corners[oppositeIndex];
                    
                            switch (effectiveIndex) {
                                case 0:
                                    newWidth = oppositePoint.x - localX;
                                    newHeight = oppositePoint.y - localY;
                                    break;
                                case 1:
                                    newWidth = localX - oppositePoint.x;
                                    newHeight = oppositePoint.y - localY;
                                    break;
                                case 2:
                                    newWidth = localX - oppositePoint.x;
                                    newHeight = localY - oppositePoint.y;
                                    break;
                                case 3:
                                    newWidth = oppositePoint.x - localX;
                                    newHeight = localY - oppositePoint.y;
                                    break;
                            }
                            
                            newWidth = Math.max(1, newWidth);
                            newHeight = Math.max(1, newHeight);
                            selectedAnnotation.width = newWidth;
                            selectedAnnotation.height = newHeight;
                            
                            const newHalfW = newWidth / 2;
                            const newHalfH = newHeight / 2;
                            const newCorners = [
                                { x: -newHalfW, y: -newHalfH },
                                { x: newHalfW, y: -newHalfH },
                                { x: newHalfW, y: newHalfH },
                                { x: -newHalfW, y: newHalfH }
                            ];
                            const newOppositeCornerLocal = newCorners[oppositeIndex];
                            const oppositeGlobalX = oppositePoint.x * cos - oppositePoint.y * sin + centerX;
                            const oppositeGlobalY = oppositePoint.x * sin + oppositePoint.y * cos + centerY;
                            const newCenterX = oppositeGlobalX - (newOppositeCornerLocal.x * cos - newOppositeCornerLocal.y * sin);
                            const newCenterY = oppositeGlobalY - (newOppositeCornerLocal.x * sin + newOppositeCornerLocal.y * cos);
                    
                            selectedAnnotation.x = newCenterX - newWidth / 2;
                            selectedAnnotation.y = newCenterY - newHeight / 2;
                        } else {
                            switch (selectedPointIndex) {
                                case 4:
                                    oppositePoint = { x: 0, y: halfH };
                                    newHeight = oppositePoint.y - localY;
                                    break;
                                case 5:
                                    oppositePoint = { x: 0, y: -halfH };
                                    newHeight = localY - oppositePoint.y;
                                    break;
                                case 6:
                                    oppositePoint = { x: halfW, y: 0 };
                                    newWidth = oppositePoint.x - localX;
                                    break;
                                case 7:
                                    oppositePoint = { x: -halfW, y: 0 };
                                    newWidth = localX - oppositePoint.x;
                                    break;
                            }
                    
                            if (selectedPointIndex === 4 || selectedPointIndex === 5) {
                                newHeight = Math.max(1, newHeight);
                                selectedAnnotation.height = newHeight;
                            } else {
                                newWidth = Math.max(1, newWidth);
                                selectedAnnotation.width = newWidth;
                            }
                    
                            const newHalfW = selectedAnnotation.width / 2;
                            const newHalfH = selectedAnnotation.height / 2;
                            const newEdges = [
                                { x: 0, y: -newHalfH },
                                { x: 0, y: newHalfH },
                                { x: -newHalfW, y: 0 },
                                { x: newHalfW, y: 0 }
                            ];
                            
                            const oppositeEdgeIndex = selectedPointIndex - 4;
                            const newOppositeEdgeLocal = newEdges[oppositeEdgeIndex ^ 1];
                            
                            const oppositeGlobalX = oppositePoint.x * cos - oppositePoint.y * sin + centerX;
                            const oppositeGlobalY = oppositePoint.x * sin + oppositePoint.y * cos + centerY;
                            const newCenterX = oppositeGlobalX - (newOppositeEdgeLocal.x * cos - newOppositeEdgeLocal.y * sin);
                            const newCenterY = oppositeGlobalY - (newOppositeEdgeLocal.x * sin + newOppositeEdgeLocal.y * cos);
                    
                            selectedAnnotation.x = newCenterX - newWidth / 2;
                            selectedAnnotation.y = newCenterY - newHeight / 2;
                        }
                    
                        clampAnnotationToBounds(selectedAnnotation);
                    } else {
                        const initialWidth = selectedAnnotation.width;
                        const initialHeight = selectedAnnotation.height;
                        const initialX = selectedAnnotation.x;
                        const initialY = selectedAnnotation.y;

                        switch (selectedPointIndex) {
                            case 0:
                                selectedAnnotation.x = clampedPos.x;
                                selectedAnnotation.y = clampedPos.y;
                                selectedAnnotation.width = initialWidth + (initialX - clampedPos.x);
                                selectedAnnotation.height = initialHeight + (initialY - clampedPos.y);
                                break;
                            case 1:
                                selectedAnnotation.y = clampedPos.y;
                                selectedAnnotation.width = clampedPos.x - initialX;
                                selectedAnnotation.height = initialHeight + (initialY - clampedPos.y);
                                break;
                            case 2:
                                selectedAnnotation.x = clampedPos.x;
                                selectedAnnotation.width = initialWidth + (initialX - clampedPos.x);
                                selectedAnnotation.height = clampedPos.y - initialY;
                                break;
                            case 3:
                                selectedAnnotation.width = clampedPos.x - initialX;
                                selectedAnnotation.height = clampedPos.y - initialY;
                                break;
                            case 4:
                                selectedAnnotation.y = Math.max(0, Math.min(clampedPos.y, initialY + initialHeight));
                                selectedAnnotation.height = Math.abs(selectedAnnotation.y - (initialY + initialHeight));
                                break;
                            case 5:
                                selectedAnnotation.height = Math.max(0, clampedPos.y - initialY);
                                break;
                            case 6:
                                selectedAnnotation.x = Math.max(0, Math.min(clampedPos.x, initialX + initialWidth));
                                selectedAnnotation.width = Math.abs(selectedAnnotation.x - (initialX + initialWidth));
                                break;
                            case 7:
                                selectedAnnotation.width = Math.max(0, clampedPos.x - initialX);
                                break;
                        }

                        if (selectedAnnotation.width < 0) {
                            selectedAnnotation.x += selectedAnnotation.width;
                            selectedAnnotation.width = Math.abs(selectedAnnotation.width);
                        }
                        if (selectedAnnotation.height < 0) {
                            selectedAnnotation.y += selectedAnnotation.height;
                            selectedAnnotation.height = Math.abs(selectedAnnotation.height);
                        }
                    }
                } else {
                    selectedAnnotation.x += dx;
                    selectedAnnotation.y += dy;
                    clampAnnotationToBounds(selectedAnnotation);
                }
            } else if (selectedAnnotation.type === 'polygon') {
                if (selectedPointIndex >= 0) {
                    selectedAnnotation.points[selectedPointIndex] = clampToImageBounds(imgPos);
                } else {
                    const xs = selectedAnnotation.points.map(p => p.x);
                    const ys = selectedAnnotation.points.map(p => p.y);
                    const minX = Math.min(...xs);
                    const maxX = Math.max(...xs);
                    const minY = Math.min(...ys);
                    const maxY = Math.max(...ys);
                    const bboxWidth = maxX - minX;
                    const bboxHeight = maxY - minY;
            
                    const newMinX = minX + dx;
                    const newMinY = minY + dy;
                    const clampedMinX = Math.max(0, Math.min(newMinX, currentImage.width - bboxWidth));
                    const clampedMinY = Math.max(0, Math.min(newMinY, currentImage.height - bboxHeight));
                    const adjustedDx = clampedMinX - minX;
                    const adjustedDy = clampedMinY - minY;
            
                    selectedAnnotation.points = selectedAnnotation.points.map(p => ({
                        x: p.x + adjustedDx,
                        y: p.y + adjustedDy
                    }));
                }
            }
            setStartX(pos.x);
            setStartY(pos.y);
            drawImage();
        } else if (mode === 'rect' && setupType === "Oriented Bounding Box") {
            const centerX = toCanvasCoords(selectedAnnotation.x + selectedAnnotation.width / 2, selectedAnnotation.y + selectedAnnotation.height / 2).x;
            const centerY = toCanvasCoords(selectedAnnotation.x + selectedAnnotation.width / 2, selectedAnnotation.y + selectedAnnotation.height / 2).y;
            const dx = pos.x - centerX;
            const dy = pos.y - centerY;
            selectedAnnotation.rotation = Math.atan2(dy, dx) * 180 / Math.PI + 90;
            drawImage();
        }
    } else {
        canvas.style.cursor = 'default';
        if (selectedAnnotation && (selectedAnnotation.type === 'rect' || selectedAnnotation.type === 'obbox')) {
            const centerX = selectedAnnotation.x + selectedAnnotation.width / 2;
            const centerY = selectedAnnotation.y + selectedAnnotation.height / 2;
            const canvasCenter = toCanvasCoords(centerX, centerY);
            const halfWidth = selectedAnnotation.width * viewport.zoom / 2;
            const halfHeight = selectedAnnotation.height * viewport.zoom / 2;
            const rad = selectedAnnotation.rotation ? selectedAnnotation.rotation * Math.PI / 180 : 0;
            const corners = [
                { x: -halfWidth, y: -halfHeight },
                { x: halfWidth, y: -halfHeight },
                { x: -halfWidth, y: halfHeight },
                { x: halfWidth, y: halfHeight }
            ].map(corner => {
                const cos = Math.cos(rad);
                const sin = Math.sin(rad);
                const x = canvasCenter.x + (corner.x * cos - corner.y * sin);
                const y = canvasCenter.y + (corner.x * sin + corner.y * cos);
                return { x, y };
            });
            const edges = [
                { x: 0, y: -halfHeight },
                { x: 0, y: halfHeight },
                { x: -halfWidth, y: 0 },
                { x: halfWidth, y: 0 }
            ].map(edge => {
                const cos = Math.cos(rad);
                const sin = Math.sin(rad);
                const x = canvasCenter.x + (edge.x * cos - edge.y * sin);
                const y = canvasCenter.y + (edge.x * sin + edge.y * cos);
                return { x, y };
            });
            for (let j = 0; j < corners.length; j++) {
                const distance = Math.sqrt(Math.pow(pos.x - corners[j].x, 2) + Math.pow(pos.y - corners[j].y, 2));
                if (distance < 12) {
                    canvas.style.cursor = 'all-scroll';
                    break;
                }
            }
            for (let j = 0; j < edges.length; j++) {
                const distance = Math.sqrt(Math.pow(pos.x - edges[j].x, 2) + Math.pow(pos.y - edges[j].y, 2));
                if (distance < 12) {
                    if (j === 0 || j === 1) {
                        canvas.style.cursor = 'ns-resize';
                    } else {
                        canvas.style.cursor = 'ew-resize';
                    }
                    break;
                }
            }
            if (setupType === "Oriented Bounding Box") {
                const rotationHandle = { x: 0, y: -halfHeight - 20/viewport.zoom };
                const cos = Math.cos(rad);
                const sin = Math.sin(rad);
                const rotX = canvasCenter.x + (rotationHandle.x * cos - rotationHandle.y * sin);
                const rotY = canvasCenter.y + (rotationHandle.x * sin + rotationHandle.y * cos);
                const distance = Math.sqrt(Math.pow(pos.x - rotX, 2) + Math.pow(pos.y - rotY, 2));
                if (distance < 12) {
                    canvas.style.cursor = 'grab';
                }
            }
        }
    }
}

function handleMouseUp(e) {
    if (mode === 'rect' && isDrawing && currentAnnotation) {
        if (Math.abs(currentAnnotation.width) > 5 && Math.abs(currentAnnotation.height) > 5) {
            pushToUndoStack();
            annotations.push(currentAnnotation);
            updateTagHighlights();
        }
        setCurrentAnnotation(null);
        setIsDrawing(false);
        drawImage();
    }
    setIsDragging(false);
    setIsRightClickEditing(false);
    setIsRotating(false);
}

function handleWheel(e) {
    e.preventDefault();
    const pos = getMousePos(canvas, e);
    const imgPos = toImageCoords(pos.x, pos.y);
    let zoomFactor = e.altKey ? (e.deltaY > 0 ? 0.99 : 1.01) : (e.deltaY > 0 ? 0.9 : 1.1);
    const newZoom = Math.max(viewport.minZoom, Math.min(viewport.maxZoom, viewport.zoom * zoomFactor));
    viewport.x = pos.x - imgPos.x * newZoom;
    viewport.y = pos.y - imgPos.y * newZoom;
    viewport.zoom = newZoom;
    drawImage();
}

export function initAnnotationInteraction() {
    if (!canvas) {
        console.error('Canvas not initialized. Call initGlobals() first.');
        return;
    }
    canvas.addEventListener('mousedown', handleMouseDown);
    canvas.addEventListener('mousemove', handleMouseMove);
    canvas.addEventListener('mouseup', handleMouseUp);
    canvas.addEventListener('wheel', handleWheel);
    canvas.addEventListener('contextmenu', (e) => e.preventDefault());
}
