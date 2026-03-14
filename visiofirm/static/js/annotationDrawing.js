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
import { getResolvedAnnotationStyle } from './annotationStyles.js';

let hoveredAnnotation = null;
let dashOffset = 0;
let neonOffset = 0;
let lastTimestamp = 0;
let animationFrameId = null;
let neonPhase = 0;

export function setHoveredAnnotation(annotation) {
    hoveredAnnotation = annotation;
}

function animateCanvasEffects(timestamp) {
    if (!lastTimestamp) lastTimestamp = timestamp;
    const delta = timestamp - lastTimestamp;
    dashOffset = (dashOffset + delta * 0.05) % 40;
    neonOffset += delta * 0.18;
    neonPhase = (neonPhase + delta * 0.006) % (Math.PI * 2);
    lastTimestamp = timestamp;
    if (!isDrawing) {
        drawImage();
    }
    animationFrameId = requestAnimationFrame(animateCanvasEffects);
}

requestAnimationFrame(animateCanvasEffects);

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

function hexToRgb(hex) {
    const safeHex = `${hex}`.trim().slice(0, 7);
    const normalized = safeHex.startsWith('#') ? safeHex.slice(1) : safeHex;
    if (!/^[0-9a-fA-F]{6}$/.test(normalized)) {
        return { r: 37, g: 99, b: 235 };
    }
    return {
        r: parseInt(normalized.slice(0, 2), 16),
        g: parseInt(normalized.slice(2, 4), 16),
        b: parseInt(normalized.slice(4, 6), 16),
    };
}

function mixWithWhite(hex, ratio = 0.5) {
    const { r, g, b } = hexToRgb(hex);
    const blend = value => Math.round(value + (255 - value) * ratio);
    return `rgb(${blend(r)}, ${blend(g)}, ${blend(b)})`;
}

function alphaColor(hex, alpha = 1) {
    const { r, g, b } = hexToRgb(hex);
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

function clamp(value, min, max) {
    return Math.min(max, Math.max(min, value));
}

function strokeCurrentPath(style, { selected = false, perimeter = 0 } = {}) {
    const baseWidth = style.strokeWidth;
    ctx.lineJoin = 'round';
    ctx.lineCap = 'round';
    ctx.lineWidth = baseWidth;
    ctx.strokeStyle = style.strokeColor;
    ctx.shadowBlur = 0;
    ctx.stroke();

    if (!selected) return;

    const glowStrength = 0.55 + 0.45 * Math.sin(neonPhase);
    const haloColor = alphaColor(style.strokeColor, 0.3 + glowStrength * 0.2);
    const neonColor = mixWithWhite(style.strokeColor, 0.58 + glowStrength * 0.12);
    const neonCore = mixWithWhite(style.strokeColor, 0.82);

    ctx.save();
    ctx.shadowColor = haloColor;
    ctx.shadowBlur = 10 + glowStrength * 18;
    ctx.lineWidth = baseWidth + 1.5 + glowStrength * 2;
    ctx.strokeStyle = alphaColor(style.strokeColor, 0.75);
    ctx.stroke();
    ctx.restore();

    if (perimeter <= 0) return;

    const segmentLength = clamp(perimeter * 0.18, 26, 150);
    const gapLength = Math.max(1, perimeter - segmentLength);
    const travelOffset = -(neonOffset % perimeter);
    const oppositeOffset = travelOffset - perimeter / 2;

    [travelOffset, oppositeOffset].forEach(offset => {
        ctx.save();
        ctx.globalCompositeOperation = 'lighter';
        ctx.setLineDash([segmentLength, gapLength]);
        ctx.lineDashOffset = offset;
        ctx.shadowColor = alphaColor(neonColor, 1);
        ctx.shadowBlur = 24 + glowStrength * 22;
        ctx.lineWidth = baseWidth + 4 + glowStrength * 2;
        ctx.strokeStyle = alphaColor(neonColor, 0.98);
        ctx.stroke();
        ctx.restore();

        ctx.save();
        ctx.globalCompositeOperation = 'lighter';
        ctx.setLineDash([segmentLength * 0.72, Math.max(1, perimeter - segmentLength * 0.72)]);
        ctx.lineDashOffset = offset - segmentLength * 0.08;
        ctx.shadowColor = alphaColor(neonCore, 1);
        ctx.shadowBlur = 14 + glowStrength * 14;
        ctx.lineWidth = baseWidth + 2 + glowStrength;
        ctx.strokeStyle = alphaColor(neonCore, 1);
        ctx.stroke();
        ctx.restore();

        ctx.save();
        ctx.globalCompositeOperation = 'lighter';
        ctx.setLineDash([segmentLength * 0.34, Math.max(1, perimeter - segmentLength * 0.34)]);
        ctx.lineDashOffset = offset - segmentLength * 0.12;
        ctx.shadowColor = 'rgba(255, 255, 255, 1)';
        ctx.shadowBlur = 10 + glowStrength * 10;
        ctx.lineWidth = Math.max(1.5, baseWidth * 0.8 + 0.8);
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.98)';
        ctx.stroke();
        ctx.restore();
    });
}

function drawRectAnnotation(anno) {
    ctx.save();
    const style = getResolvedAnnotationStyle(anno, { selected: anno === selectedAnnotation });
    const centerX = anno.x + anno.width / 2;
    const centerY = anno.y + anno.height / 2;
    const canvasCenter = toCanvasCoords(centerX, centerY);
    ctx.translate(canvasCenter.x, canvasCenter.y);
    if (anno.rotation) ctx.rotate(anno.rotation * Math.PI / 180);
    const topLeft = { x: -anno.width * viewport.zoom / 2, y: -anno.height * viewport.zoom / 2 };
    const size = { width: anno.width * viewport.zoom, height: anno.height * viewport.zoom };
    const perimeter = 2 * (size.width + size.height);
    ctx.beginPath();
    ctx.rect(topLeft.x, topLeft.y, size.width, size.height);
    ctx.globalAlpha = 1;
    ctx.setLineDash(style.dash);
    if (anno.isPreannotation) {
        ctx.lineDashOffset = dashOffset;
    }
    if (style.renderMode === 'fill' || style.renderMode === 'outline_fill') {
        ctx.fillStyle = style.fillColor;
        ctx.fill();
    }
    if (style.renderMode === 'outline' || style.renderMode === 'outline_fill') {
        strokeCurrentPath(style, { selected: anno === selectedAnnotation, perimeter });
    }
    ctx.restore();
}

function drawPolygonAnnotation(anno) {
    if (!anno.points || anno.points.length < 1) return;
    ctx.save();
    const style = getResolvedAnnotationStyle(anno, { selected: anno === selectedAnnotation });
    ctx.beginPath();
    const firstPoint = toCanvasCoords(anno.points[0].x, anno.points[0].y);
    ctx.moveTo(firstPoint.x, firstPoint.y);
    let perimeter = 0;
    let previousPoint = firstPoint;
    for (let i = 1; i < anno.points.length; i++) {
        const p = toCanvasCoords(anno.points[i].x, anno.points[i].y);
        perimeter += Math.hypot(p.x - previousPoint.x, p.y - previousPoint.y);
        ctx.lineTo(p.x, p.y);
        previousPoint = p;
    }
    if (anno.closed) {
        perimeter += Math.hypot(firstPoint.x - previousPoint.x, firstPoint.y - previousPoint.y);
        ctx.closePath();
    }
    ctx.globalAlpha = 1;
    ctx.setLineDash(style.dash);
    if (anno.isPreannotation) {
        ctx.lineDashOffset = dashOffset;
    }
    if ((style.renderMode === 'fill' || style.renderMode === 'outline_fill') && anno.closed) {
        ctx.fillStyle = style.fillColor;
        ctx.fill();
    }
    if (style.renderMode === 'outline' || style.renderMode === 'outline_fill' || !anno.closed) {
        strokeCurrentPath(style, { selected: anno === selectedAnnotation, perimeter });
    }
    
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
    viewport.zoom = viewport.fitZoom || viewport.minZoom;
    viewport.x = (canvas.width - currentImage.width * viewport.zoom) / 2;
    viewport.y = (canvas.height - currentImage.height * viewport.zoom) / 2;
    drawImage();
}
