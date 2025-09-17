export function getColorForClass(className) {
    let hash = 0;
    for (let i = 0; i < className.length; i++) {
        hash = className.charCodeAt(i) + ((hash << 5) - hash);
    }
    let color = '#';
    for (let i = 0; i < 3; i++) {
        const value = (hash >> (i * 8)) & 0xff;
        color += ('00' + value.toString(16)).substr(-2);
    }
    return color;
}

export function getTextColor(bgColor) {
    const r = parseInt(bgColor.substr(1, 2), 16);
    const g = parseInt(bgColor.substr(3, 2), 16);
    const b = parseInt(bgColor.substr(5, 2), 16);
    const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
    return luminance > 0.5 ? '#000' : '#fff';
}

export function darkenColor(hex, percent = 20) {
    let r = parseInt(hex.slice(1, 3), 16);
    let g = parseInt(hex.slice(3, 5), 16);
    let b = parseInt(hex.slice(5, 7), 16);
    r = Math.floor(r * (1 - percent / 100));
    g = Math.floor(g * (1 - percent / 100));
    b = Math.floor(b * (1 - percent / 100));
    return `#${r.toString(16).padStart(2, '0')}${g.toString(16).padStart(2, '0')}${b.toString(16).padStart(2, '0')}`;
}

export function formatTime(seconds) {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
}

export function pointLineDistance(point, lineStart, lineEnd) {
    const dx = lineEnd.x - lineStart.x;
    const dy = lineEnd.y - lineStart.y;
    const lenSquared = dx * dx + dy * dy;
    if (lenSquared === 0) return Math.sqrt((point.x - lineStart.x) ** 2 + (point.y - lineStart.y) ** 2);
    let t = ((point.x - lineStart.x) * dx + (point.y - lineStart.y) * dy) / lenSquared;
    t = Math.max(0, Math.min(1, t));
    const nearestX = lineStart.x + t * dx;
    const nearestY = lineStart.y + t * dy;
    return Math.sqrt((point.x - nearestX) ** 2 + (point.y - nearestY) ** 2);
}

export function toImageCoords(canvasX, canvasY, viewport) {
    return { x: (canvasX - viewport.x) / viewport.zoom, y: (canvasY - viewport.y) / viewport.zoom };
}

export function toCanvasCoords(x, y, viewport) {
    return { x: viewport.x + x * viewport.zoom, y: viewport.y + y * viewport.zoom };
}

export function clampToImageBounds(point, currentVideo) {
    if (!currentVideo) return point;
    return {
        x: Math.max(0, Math.min(point.x, currentVideo.videoWidth)),
        y: Math.max(0, Math.min(point.y, currentVideo.videoHeight))
    };
}

export function clampAnnotationToBounds(annotation, currentVideo) {
    if (!currentVideo || annotation.type !== 'rect') return;
    annotation.x = Math.max(0, annotation.x);
    annotation.y = Math.max(0, annotation.y);
    annotation.width = Math.min(annotation.width, currentVideo.videoWidth - annotation.x);
    annotation.height = Math.min(annotation.height, currentVideo.videoHeight - annotation.y);
}

export function clampPosition(annotation, currentVideo) {
    if (!currentVideo || annotation.type !== 'rect') return;
    annotation.x = Math.max(0, Math.min(annotation.x, currentVideo.videoWidth - annotation.width));
    annotation.y = Math.max(0, Math.min(annotation.y, currentVideo.videoHeight - annotation.height));
}

export function isPointInAnnotation(imgPoint, annotation) {
    if (annotation.type === 'rect') {
        return imgPoint.x >= annotation.x && imgPoint.x <= annotation.x + annotation.width &&
               imgPoint.y >= annotation.y && imgPoint.y <= annotation.y + annotation.height;
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

export function findAnnotationByPoint(imgPoint, annotations) {
    for (let i = annotations.length - 1; i >= 0; i--) {
        const annotation = annotations[i];
        if (isPointInAnnotation(imgPoint, annotation)) {
            return annotation;
        }
    }
    return null;
}

export function findHandleIndex(canvasX, canvasY, anno, viewport) {
    if (!anno) return -1;
    if (anno.type === 'rect') {
        const x = viewport.x + anno.x * viewport.zoom;
        const y = viewport.y + anno.y * viewport.zoom;
        const w = anno.width * viewport.zoom;
        const h = anno.height * viewport.zoom;
        const handles = [
            {x: x, y: y}, // 0: top-left
            {x: x + w, y: y}, // 1: top-right
            {x: x, y: y + h}, // 2: bottom-left
            {x: x + w, y: y + h}, // 3: bottom-right
            {x: x + w / 2, y: y}, // 4: top-mid
            {x: x + w / 2, y: y + h}, // 5: bottom-mid
            {x: x, y: y + h / 2}, // 6: left-mid
            {x: x + w, y: y + h / 2} // 7: right-mid
        ];
        for (let i = 0; i < handles.length; i++) {
            const hx = handles[i].x;
            const hy = handles[i].y;
            const dist = Math.sqrt((canvasX - hx) ** 2 + (canvasY - hy) ** 2);
            if (dist < 10) return i;
        }
        return -1;
    } else if (anno.type === 'polygon') {
        for (let i = 0; i < anno.points.length; i++) {
            const p = toCanvasCoords(anno.points[i].x, anno.points[i].y, viewport);
            const dist = Math.sqrt((canvasX - p.x) ** 2 + (canvasY - p.y) ** 2);
            if (dist < 10) return i;
        }
        return -1;
    }
    return -1;
}

export function resizeAnnotation(anno, index, dx, dy) {
    if (anno.type === 'rect') {
        switch (index) {
            case 0: // top-left
                anno.x += dx;
                anno.y += dy;
                anno.width -= dx;
                anno.height -= dy;
                break;
            case 1: // top-right
                anno.y += dy;
                anno.width += dx;
                anno.height -= dy;
                break;
            case 2: // bottom-left
                anno.x += dx;
                anno.width -= dx;
                anno.height += dy;
                break;
            case 3: // bottom-right
                anno.width += dx;
                anno.height += dy;
                break;
            case 4: // top-mid
                anno.y += dy;
                anno.height -= dy;
                break;
            case 5: // bottom-mid
                anno.height += dy;
                break;
            case 6: // left-mid
                anno.x += dx;
                anno.width -= dx;
                break;
            case 7: // right-mid
                anno.width += dx;
                break;
        }
        if (anno.width < 0) {
            anno.x += anno.width;
            anno.width = Math.abs(anno.width);
        }
        if (anno.height < 0) {
            anno.y += anno.height;
            anno.height = Math.abs(anno.height);
        }
        anno.width = Math.max(1, anno.width);
        anno.height = Math.max(1, anno.height);
        // clampAnnotationToBounds would be called externally if needed
    } else if (anno.type === 'polygon' && index >= 0) {
        anno.points[index].x += dx;
        anno.points[index].y += dy;
        // clampToImageBounds would be called externally if needed
    }
}

export function findClosestPolygonSegment(polygon, point) {
    let minDist = Infinity;
    let closestSegment = -1;
    for (let i = 0; i < polygon.points.length - 1; i++) {
        const dist = pointLineDistance(point, polygon.points[i], polygon.points[i + 1]);
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
    return minDist < 10 ? closestSegment : -1; // Threshold for closeness
}