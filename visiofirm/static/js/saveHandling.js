import { annotationCache, currentImageKey, annotations, confidenceThreshold } from './globals.js';
import { saveCacheToStorage } from './storageHandling.js';
import { updateAnnotationSummary } from './imageHandling.js';

export function initSaveHandling(updateAnnotationStatus) {
    document.getElementById('approve-btn').addEventListener('click', async function(e) {
        if (e) e.preventDefault();

        if (!currentImageKey) {
            alert('No image selected for annotation');
            return;
        }

        // Filter annotations to include only regular annotations and pre-annotations above confidence threshold
        const filteredAnnotations = annotations.filter(anno => {
            if (anno.isPreannotation) {
                return anno.confidence >= confidenceThreshold;
            }
            return true; // Include all non-pre-annotations
        }).map(anno => ({
            ...anno,
            isPreannotation: false // Convert kept pre-annotations to regular annotations
        }));

        // Update the annotations array
        annotations.length = 0;
        annotations.push(...filteredAnnotations);

        // Update the annotation cache
        annotationCache[currentImageKey] = [...filteredAnnotations];
        const isAnnotated = true; // Always true for manual saves
        updateAnnotationSummary();

        // Update both grid and list views
        updateAnnotationStatus(currentImageKey, isAnnotated);
        saveCacheToStorage();

        const cocoAnnotations = filteredAnnotations
            .filter(anno => anno.type === 'rect' || anno.type === 'obbox' || anno.type === 'polygon')
            .map(anno => {
                const base = {
                    image_id: currentImageKey,
                    category_name: anno.label,
                    score: 1.0
                };
                if (anno.type === 'rect' || anno.type === 'obbox') {
                    return {
                        ...base,
                        bbox: [anno.x, anno.y, anno.width, anno.height],
                        rotation: anno.rotation || 0,
                        segmentation: [],
                        area: anno.width * anno.height
                    };
                }
                if (anno.type === 'polygon') {
                    const seg = anno.points.flatMap(p => [p.x, p.y]);
                    const xs = seg.filter((_, i) => i % 2 === 0);
                    const ys = seg.filter((_, i) => i % 2 === 1);
                    const bbox = [
                        Math.min(...xs),
                        Math.min(...ys),
                        Math.max(...xs) - Math.min(...xs),
                        Math.max(...ys) - Math.min(...ys)
                    ];
                    return {
                        ...base,
                        bbox,
                        segmentation: [seg],
                        area: polygonArea(anno.points)
                    };
                }
            });

        try {
            const config = JSON.parse(document.getElementById('app-config').textContent);
            const imageFilename = currentImageKey.split('/').pop();
            const response = await fetch('/annotation/save_annotations', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    project: config.projectName,
                    image: imageFilename,
                    annotations: cocoAnnotations,
                    approve: true
                })
            });

            const result = await response.json();
            if (!response.ok || !result.success) {
                throw new Error(result.error || `Server error: ${response.status}`);
            }

            const modal = document.getElementById('save-modal');
            if (modal) {
                modal.style.display = 'flex';
                setTimeout(() => {
                    modal.style.display = 'none';
                }, 3000);
            }
        } catch (error) {
            console.error('Save error:', error);
            alert(`Failed to save annotations: ${error.message}`);
        }
    });
}

function polygonArea(points) {
    let area = 0;
    for (let i = 0, j = points.length - 1; i < points.length; j = i++) {
        area += (points[j].x + points[i].x) * (points[j].y - points[i].y);
    }
    return Math.abs(area / 2);
}
