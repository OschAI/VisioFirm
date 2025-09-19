import { 
    ctx, 
    setupType, 
    currentImage,
    viewport, 
    annotations, 
    confidenceThreshold,
    selectedAnnotation,
    selectedPointIndex,
    classColors,
    gridEnabled,
    gridSize,
    canvas,
    currentAnnotation,
    isDrawing
} from './globals.js';
import { toCanvasCoords } from './annotationCore.js';

let hoveredAnnotation = null;
let dashOffset = 0;
let lastTimestamp = 0;
let animationFrameId = null;

export function setHoveredAnnotation(annotation) {
    hoveredAnnotation = annotation;
}

function animateDashedBorders(timestamp) {
    if (!lastTimestamp) lastTimestamp = timestamp;
    const delta = timestamp - lastTimestamp;
    dashOffset = (dashOffset + delta * 0.05) % 40;
    lastTimestamp = timestamp;
    if (!isDrawing) {
        drawImage();
    }
    animationFrameId = requestAnimationFrame(animateDashedBorders);
}

requestAnimationFrame(animateDashedBorders);

if (typeof window !== 'undefined') {
    window.addEventListener('unload', () => {
        if (animationFrameId) {
            cancelAnimationFrame(animationFrameId);
        }
    });
}

export function drawImage() {
    if (!currentImage) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    const drawWidth = currentImage.width * viewport.zoom;
    const drawHeight = currentImage.height * viewport.zoom;
    if (drawWidth < canvas.width) {
        viewport.x = (canvas.width - drawWidth) / 2;
    } else {
        viewport.x = Math.max(canvas.width - drawWidth, Math.min(0, viewport.x));
    }
    if (drawHeight < canvas.height) {
        viewport.y = (canvas.height - drawHeight) / 2;
    } else {
        viewport.y = Math.max(canvas.height - drawHeight, Math.min(0, viewport.y));
    }
    ctx.drawImage(currentImage, viewport.x, viewport.y, drawWidth, drawHeight);
    drawAnnotations();
    if (currentAnnotation) {
        if (currentAnnotation.type === 'rect' || currentAnnotation.type === 'obbox') {
            drawRectAnnotation(currentAnnotation);
        } else if (currentAnnotation.type === 'polygon') {
            drawPolygonAnnotation(currentAnnotation);
        }
    }
    if (gridEnabled) {
        ctx.save();
        ctx.beginPath();
        ctx.strokeStyle = 'rgba(0, 0, 0, 0.2)';
        for (let x = 0; x < currentImage.width; x += gridSize) {
            const canvasX = toCanvasCoords(x, 0).x;
            ctx.moveTo(canvasX, viewport.y);
            ctx.lineTo(canvasX, viewport.y + currentImage.height * viewport.zoom);
        }
        for (let y = 0; y < currentImage.height; y += gridSize) {
            const canvasY = toCanvasCoords(0, y).y;
            ctx.moveTo(viewport.x, canvasY);
            ctx.lineTo(viewport.x + currentImage.width * viewport.zoom, canvasY);
        }
        ctx.stroke();
        ctx.restore();
    }
    if (selectedAnnotation) {
        drawSelectionHandles(selectedAnnotation);
    }
    if (hoveredAnnotation) {
        drawTooltip(hoveredAnnotation);
    }
}

function drawAnnotations() {
    annotations
        .filter(anno => anno.type !== 'classification' && (!anno.isPreannotation || (anno.confidence >= confidenceThreshold)))
        .forEach(anno => {
            if (anno.type === 'rect' || anno.type === 'obbox') {
                drawRectAnnotation(anno);
            } else if (anno.type === 'polygon') {
                drawPolygonAnnotation(anno);
            }
        });
}

function drawRectAnnotation(anno) {
    ctx.save();
    const centerX = anno.x + anno.width / 2;
    const centerY = anno.y + anno.height / 2;
    const canvasCenter = toCanvasCoords(centerX, centerY);
    ctx.translate(canvasCenter.x, canvasCenter.y);
    if (anno.rotation) ctx.rotate(anno.rotation * Math.PI / 180);
    const topLeft = { x: -anno.width * viewport.zoom / 2, y: -anno.height * viewport.zoom / 2 };
    const size = { width: anno.width * viewport.zoom, height: anno.height * viewport.zoom };
    ctx.beginPath();
    ctx.rect(topLeft.x, topLeft.y, size.width, size.height);
    if (anno.isPreannotation) {
        ctx.globalAlpha = 0.7;
        ctx.setLineDash([10, 10]);
        ctx.lineDashOffset = dashOffset;
    } else {
        ctx.globalAlpha = 0.7;
        ctx.setLineDash([]);
    }
    ctx.fillStyle = classColors[anno.label] || '#0000ff33';
    ctx.fill();
    ctx.lineWidth = 2;
    ctx.strokeStyle = 'black';
    ctx.stroke();
    ctx.restore();
}

function drawPolygonAnnotation(anno) {
    if (!anno.points || anno.points.length < 1) return;
    ctx.save();
    ctx.beginPath();
    const firstPoint = toCanvasCoords(anno.points[0].x, anno.points[0].y);
    ctx.moveTo(firstPoint.x, firstPoint.y);
    for (let i = 1; i < anno.points.length; i++) {
        const p = toCanvasCoords(anno.points[i].x, anno.points[i].y);
        ctx.lineTo(p.x, p.y);
    }
    if (anno.closed) ctx.closePath();
    if (anno.isPreannotation) {
        ctx.globalAlpha = 0.7;
        ctx.setLineDash([10, 10]);
        ctx.lineDashOffset = dashOffset;
    } else {
        ctx.globalAlpha = 0.7;
        ctx.setLineDash([]);
    }
    ctx.fillStyle = classColors[anno.label] || '#fbff0033';
    if (anno.closed) ctx.fill();
    ctx.lineWidth = 2;
    ctx.strokeStyle = 'black';
    ctx.stroke();
    
    // Draw points for in-progress polygon
    if (!anno.closed) {
        anno.points.forEach(point => {
            const p = toCanvasCoords(point.x, point.y);
            ctx.beginPath();
            ctx.arc(p.x, p.y, 3, 0, Math.PI * 2);
            ctx.fillStyle = 'red';
            ctx.fill();
        });
    }
    ctx.restore();
}

function drawTooltip(anno) {
    ctx.save();
    let x, y;
    if (anno.type === 'rect' || anno.type === 'obbox') {
        const centerX = anno.x + anno.width / 2;
        const centerY = anno.y + anno.height / 2;
        const canvasCenter = toCanvasCoords(centerX, centerY);
        x = canvasCenter.x - (anno.width * viewport.zoom) / 2;
        y = canvasCenter.y - (anno.height * viewport.zoom) / 2 - 20;
    } else if (anno.type === 'polygon') {
        const firstPoint = toCanvasCoords(anno.points[0].x, anno.points[0].y);
        x = firstPoint.x;
        y = firstPoint.y - 20;
    }
    ctx.fillStyle = 'black';
    ctx.font = '12px Arial';
    const textWidth = ctx.measureText(anno.label).width;
    const padding = 5;
    ctx.fillRect(x - padding, y - 15, textWidth + 2 * padding, 20);
    ctx.fillStyle = 'white';
    ctx.fillText(anno.label, x, y);
    ctx.restore();
}

function drawSelectionHandles(anno) {
    const shakerRadius = 2;
    const selectedHandleRadius = 14;
    if (anno.type === 'rect' || anno.type === 'obbox') {
        ctx.save();
        const centerX = anno.x + anno.width / 2;
        const centerY = anno.y + anno.height / 2;
        const canvasCenter = toCanvasCoords(centerX, centerY);
        ctx.translate(canvasCenter.x, canvasCenter.y);
        if (anno.rotation) ctx.rotate(anno.rotation * Math.PI / 180);
        const halfWidth = anno.width * viewport.zoom / 2;
        const halfHeight = anno.height * viewport.zoom / 2;
        const handles = [
            { x: -halfWidth, y: -halfHeight },
            { x: halfWidth, y: -halfHeight },
            { x: -halfWidth, y: halfHeight },
            { x: halfWidth, y: halfHeight },
            { x: 0, y: -halfHeight },
            { x: 0, y: halfHeight },
            { x: -halfWidth, y: 0 },
            { x: halfWidth, y: 0 }
        ];
        ctx.fillStyle = 'red';
        handles.forEach((handle, index) => {
            ctx.beginPath();
            ctx.arc(handle.x, handle.y, shakerRadius, 0, Math.PI * 2);
            ctx.fill();
            if (index === selectedPointIndex) {
                ctx.beginPath();
                ctx.arc(handle.x, handle.y, selectedHandleRadius, 0, Math.PI * 2);
                ctx.strokeStyle = 'blue';
                ctx.lineWidth = 3;
                ctx.stroke();
            }
        });
        if (setupType === "Oriented Bounding Box") {
            const rotationHandle = { x: 0, y: -halfHeight - 20 / viewport.zoom };
            ctx.fillStyle = 'blue';
            ctx.beginPath();
            ctx.arc(rotationHandle.x, rotationHandle.y, shakerRadius * 2, 0, Math.PI * 2);
            ctx.fill();
            ctx.strokeStyle = 'white';
            ctx.fillStyle = 'white';
            ctx.lineWidth = 2;
            ctx.beginPath();
            ctx.arc(rotationHandle.x, rotationHandle.y, 8, -Math.PI / 2, Math.PI / 3);
            ctx.stroke();
            const angle = Math.PI / 3;
            const arrowSize = 5;
            const arrowX = rotationHandle.x + 8 * Math.cos(angle);
            const arrowY = rotationHandle.y + 8 * Math.sin(angle);
            ctx.beginPath();
            ctx.moveTo(arrowX, arrowY);
            ctx.lineTo(arrowX - arrowSize * 0.8, arrowY - arrowSize * 0.6);
            ctx.lineTo(arrowX - arrowSize * 0.3, arrowY - arrowSize * 0.3);
            ctx.lineTo(arrowX + arrowSize * 0.4, arrowY - arrowSize * 1.2);
            ctx.fill();
        }
        ctx.restore();
    } else if (anno.type === 'polygon') {
        ctx.fillStyle = 'red';
        anno.points.forEach((point, index) => {
            const p = toCanvasCoords(point.x, point.y);
            ctx.beginPath();
            ctx.arc(p.x, p.y, shakerRadius, 0, Math.PI * 2);
            ctx.fill();
            if (index === selectedPointIndex) {
                ctx.beginPath();
                ctx.arc(p.x, p.y, selectedHandleRadius, 0, Math.PI * 2);
                ctx.strokeStyle = 'blue';
                ctx.lineWidth = 3;
                ctx.stroke();
            }
        });
    }
}

export function resetView() {
    viewport.zoom = viewport.minZoom;
    viewport.x = (canvas.width - currentImage.width * viewport.zoom) / 2;
    viewport.y = (canvas.height - currentImage.height * viewport.zoom) / 2;
    drawImage();
}