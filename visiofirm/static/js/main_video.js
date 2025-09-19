import { globals } from './video_globals.js';
import {
    getTextColor,
    darkenColor,
    toCanvasCoords,
} from './video_utils.js';
import {
    resizeTimelineCanvas,
    drawTimeline,
    updateFrameFromMouse,
    updatePlayhead,
    updateTimeDisplay,
    goToFirstFrame,
    goToLastFrame,
    goToPrevFrame,
    goToNextFrame,
    setupTimelineEventListeners
} from './timeline_helpers.js';
import { setupAnnotationInteractions } from './videoAnnotationInteraction.js';

document.addEventListener('DOMContentLoaded', async () => {
    const config = JSON.parse(document.getElementById('app-config').textContent);
    const setupType = config.setupType;
    const projectName = config.projectName;
    const classes = config.classes;

    // Precompute distinct colors for each class using a fixed palette
    const palette = [
        '#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7',
        '#DDA0DD', '#98D8C8', '#F7DC6F', '#BB8FCE', '#85C1E9',
        '#FF9F43', '#A8E6CF', '#FFD93D', '#6BCF7F', '#FF8E8E',
        '#B19CD9', '#74B9FF', '#E17055', '#00B894', '#FD79A8'
    ];
    globals.classColors = {};
    classes.forEach((cls, index) => {
        globals.classColors[cls] = palette[index % palette.length];
    });

    // Set DOM elements on globals (now that DOM is ready) - FIXED IDs to match HTML
    globals.canvas = document.getElementById('video-canvas');
    globals.ctx = globals.canvas?.getContext('2d');
    globals.tlCanvas = document.getElementById('timeline-canvas');
    globals.tlCtx = globals.tlCanvas?.getContext('2d');
    globals.playhead = document.getElementById('playhead');
    globals.videoName = document.getElementById('video-name');
    globals.currentTimeInput = document.getElementById('current-time');
    globals.playPauseBtn = document.getElementById('play-pause');
    globals.firstFrameBtn = document.getElementById('first-frame');
    globals.lastFrameBtn = document.getElementById('last-frame');
    globals.prevFrameBtn = document.getElementById('prev-frame');
    globals.nextFrameBtn = document.getElementById('next-frame');
    globals.loopBtn = document.getElementById('loop-btn');
    globals.removeSegmentAnnotationsBtn = document.getElementById('remove-segment-annotations');
    globals.removeSegmentPreannotationsBtn = document.getElementById('remove-segment-preannotations');
    globals.videoItems = document.querySelectorAll('.video-item');

    // FIXED: Use correct IDs from HTML (e.g., rect-mode, polygon-mode)
    globals.rectBtn = document.getElementById('rect-mode');
    globals.polygonBtn = document.getElementById('polygon-mode');
    // Add handlers for other new buttons
    // globals.magicBtn = document.getElementById('magic-mode');
    globals.selectBtn = document.getElementById('select-mode');
    globals.undoBtn = document.getElementById('undo-btn');
    globals.deleteBtn = document.getElementById('delete-btn');
    globals.duplicateBtn = document.getElementById('duplicate-btn');
    globals.gridBtn = document.getElementById('grid-btn');
    globals.resetViewBtn = document.getElementById('reset-view');
    globals.zoomInBtn = document.getElementById('zoom-in-btn');
    globals.zoomOutBtn = document.getElementById('zoom-out-btn');
    globals.saveBtn = document.getElementById('save-btn');
    globals.prevVideoBtn = document.getElementById('prev-video-btn');
    globals.nextVideoBtn = document.getElementById('next-video-btn');
    globals.trackerBtn = document.getElementById('vf-tracker-btn');
    globals.exportBtn = document.getElementById('export-btn');
    globals.classCells = document.querySelectorAll('.classes-bottom td');

    // Set currentVideo
    globals.currentVideo = globals.hiddenVideo;
    globals.mousedownX = undefined; // For drag detection
    globals.lastRightClickTime = 0;
    globals.lastRightClickX = 0;
    globals.isPanning = false;
    globals.panStart = { x: 0, y: 0 };
    // Destructure only non-mutable DOM elements (after setting them)
    const {
        canvas,
        ctx,
        tlCanvas,
        tlCtx,
        playhead,
        videoName,
        currentTimeInput,
        playPauseBtn,
        firstFrameBtn,
        lastFrameBtn,
        prevFrameBtn,
        nextFrameBtn,
        loopBtn,
        removeSegmentAnnotationsBtn,
        removeSegmentPreannotationsBtn,
        videoItems,
        rectBtn,
        polygonBtn,
        classCells,
        magicBtn,
        selectBtn,
        undoBtn,
        deleteBtn,
        duplicateBtn,
        gridBtn,
        resetViewBtn,
        zoomInBtn,
        zoomOutBtn,
        saveBtn,
        prevVideoBtn,
        nextVideoBtn,
        exportBtn
    } = globals;

    globals.copyBuffer = null;
    globals.animationInterval = null;

    function showToast(message, type = 'info') {
        if (type === 'error') {
            alert(message);
            return;
        }
        const container = document.getElementById('toast-container');
        if (!container) return;

        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.textContent = message;
        const icon = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        icon.setAttribute('width', '24');
        icon.setAttribute('height', '24');
        icon.setAttribute('viewBox', '0 0 24 24');
        icon.setAttribute('fill', 'none');
        icon.setAttribute('stroke', 'currentColor');
        icon.setAttribute('stroke-width', '2');
        icon.style.marginRight = '8px';
        icon.style.flexShrink = '0';
        icon.style.verticalAlign = 'middle';

        let path;
        if (type === 'success') {
            path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
            path.setAttribute('d', 'M20 6L9 17l-5-5');
            path.classList.add('checkmark');
        } else if (type === 'warning') {
            path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
            path.setAttribute('d', 'M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z');
            path.classList.add('warning-icon');
        }

        if (path) {
            icon.appendChild(path);
            toast.style.display = 'flex';
            toast.style.alignItems = 'center';
            toast.insertBefore(icon, toast.firstChild);
        }
        container.appendChild(toast);

        // Auto-remove after 4 seconds
        setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transform = 'translateX(100%)';
            setTimeout(() => {
                if (container.contains(toast)) {
                    container.removeChild(toast);
                }
            }, 300);
        }, 4000);
    }

    const confirmModal = document.getElementById('confirm-modal');

    function showConfirm(button, message, onConfirm) {
        if (!confirmModal) return;
        
        const msgEl = document.getElementById('confirm-message');
        if (msgEl) msgEl.textContent = message;
        
        // Reset any custom positioning to use CSS centering
        confirmModal.style.top = '';
        confirmModal.style.left = '';
        confirmModal.style.width = '100%';
        confirmModal.style.height = '100%';
        
        confirmModal.style.display = 'block';
        
        const yesBtn = document.getElementById('confirm-yes');
        const cancelBtn = document.getElementById('confirm-cancel');
        
        const hide = () => {
            confirmModal.style.display = 'none';
        };
        
        const yesHandler = () => {
            hide();
            if (onConfirm) onConfirm();
        };
        
        if (yesBtn) yesBtn.onclick = yesHandler;
        if (cancelBtn) cancelBtn.onclick = hide;
        
        // Close on backdrop click
        confirmModal.onclick = (e) => {
            if (e.target === confirmModal) hide();
        };
    }

    // =========================
    // Class cells setup
    // =========================
    if (classCells) {
        classCells.forEach(td => {
            const cls = td.textContent.trim();
            const color = globals.classColors[cls] || '#cccccc'; 
            td.style.backgroundColor = color;
            td.style.color = getTextColor(color);

            // Hover effect (darken slightly)
            td.addEventListener('mouseenter', () => {
                if (!td.classList.contains('selected')) {
                    td.style.backgroundColor = darkenColor(color, 10);
                }
            });
            td.addEventListener('mouseleave', () => {
                if (!td.classList.contains('selected')) {
                    td.style.backgroundColor = color;
                }
            });

            // Click to select/deselect (single selection, darken more for selected)
            td.addEventListener('click', () => {
                const wasSelected = td.classList.contains('selected');
                classCells.forEach(c => {
                    c.classList.remove('selected');
                    const cCls = c.textContent.trim();
                    const cColor = globals.classColors[cCls] || '#cccccc';
                    c.style.backgroundColor = cColor;
                    c.style.color = getTextColor(cColor);
                });
                if (!wasSelected) {
                    td.classList.add('selected');
                    const dColor = darkenColor(color, 20);
                    td.style.backgroundColor = dColor;
                    td.style.color = getTextColor(dColor);
                    globals.selectedClass = cls;
                } else {
                    globals.selectedClass = null;
                }
            });
        });
    }

    function parseAnnotationLine(line) {
        if (typeof line !== 'string') {
            // Handle JSON object: ensure bbox is array if present
            if (line && line.bbox && !Array.isArray(line.bbox)) {
                console.warn('bbox is not an array:', line.bbox);
                line.bbox = [];
            }
            return line; 
        }
        const fields = line.split('|');
        if (fields.length < 4) {
            console.warn('Invalid annotation line (too few fields):', line);
            return null;
        }
        const id = parseInt(fields[0], 10);
        const frame_id = parseInt(fields[1], 10);
        const type = fields[2];
        const class_name = fields[3];
        let anno = {
            id,
            frame_id,
            type,
            class_name,
            label: class_name
        };

        let seg_index = -1;
        for (let i = 4; i < fields.length; i++) {
            const field = fields[i];
            if (field.startsWith('[') && field.endsWith(']')) {
                seg_index = i;
                break;
            }
        }

        if (type === 'segmentation') {
            if (seg_index === -1) {
                console.warn('No segmentation field found in line:', line);
                return null;
            }
            // Confidence is the previous field
            const conf_index = seg_index - 1;
            anno.confidence = parseFloat(fields[conf_index]) || 0.0;
            // Score is the next field if it exists
            if (seg_index + 1 < fields.length) {
                anno.score = parseFloat(fields[seg_index + 1]) || 1.0;
            }
            anno.segmentation = fields[seg_index];
        } else {
            // For bbox/rect/obbox: 
            if (fields.length < 10) {
                console.warn('Too few fields for non-segmentation annotation:', line);
                return null;
            }
            anno.x = parseFloat(fields[4]) || 0;
            anno.y = parseFloat(fields[5]) || 0;
            anno.width = parseFloat(fields[6]) || 0;
            anno.height = parseFloat(fields[7]) || 0;
            anno.rotation = parseFloat(fields[8]) || 0;
            anno.confidence = parseFloat(fields[9]) || 0.0;
            if (fields.length > 10) anno.score = parseFloat(fields[10]) || 1.0;
            if (anno.width > 0 && anno.height > 0) {
                anno.bbox = [anno.x, anno.y, anno.width, anno.height];
            }
        }
        return anno;
    }

    function updateMapAndTimeline() {
        if (globals.currentFrameIndex === undefined) return;
        globals.annotationMap[globals.currentFrameIndex] = JSON.parse(JSON.stringify(globals.annotations));
        globals.classToRow = {};
        globals.nextRow = 0;
        for (let j = 0; j < globals.frames.length; j++) {
            globals.annotationMap[j].forEach(anno => {
                if (anno.label && !(anno.label in globals.classToRow)) {
                    globals.classToRow[anno.label] = globals.nextRow++;
                }
            });
        }
        drawTimeline();
    }
    
    if (rectBtn) {
        rectBtn.addEventListener('click', () => setMode('rect'));
    }
    if (polygonBtn) {
        polygonBtn.addEventListener('click', () => setMode('polygon'));
    }
    // if (magicBtn) {
    //     magicBtn.addEventListener('click', () => setMode('magic'));
    // }
    if (selectBtn) {
        selectBtn.addEventListener('click', () => setMode('select'));
    }
    if (undoBtn) {
        undoBtn.addEventListener('click', () => {
            if (globals.undoStack[globals.currentFrameIndex]?.length > 0) {
                globals.annotations = globals.undoStack[globals.currentFrameIndex].pop();
                drawImage();
                updateMapAndTimeline();
            }
        });
    }
    if (deleteBtn) {
        deleteBtn.addEventListener('click', () => {
            if (globals.selectedAnnotation) {
                const index = globals.annotations.indexOf(globals.selectedAnnotation);
                if (index > -1) globals.annotations.splice(index, 1);
                globals.selectedAnnotation = null;
                drawImage();
                updateMapAndTimeline();
            }
        });
    }
    if (duplicateBtn) {
        duplicateBtn.addEventListener('click', () => {
            if (globals.selectedAnnotation) {
                const duplicate = JSON.parse(JSON.stringify(globals.selectedAnnotation));
                globals.annotations.push(duplicate);
                drawImage();
                updateMapAndTimeline();
            }
        });
    }
    if (gridBtn) {
        gridBtn.addEventListener('click', () => setGridEnabled(!globals.gridEnabled));
    }
    if (resetViewBtn) {
        resetViewBtn.addEventListener('click', resetView);
    }
    if (zoomInBtn) {
        zoomInBtn.addEventListener('click', () => {
            globals.viewport.zoom = Math.min(globals.viewport.maxZoom, globals.viewport.zoom * 1.2);
            drawImage();
        });
    }
    if (zoomOutBtn) {
        zoomOutBtn.addEventListener('click', () => {
            globals.viewport.zoom = Math.max(globals.viewport.minZoom, globals.viewport.zoom / 1.2);
            drawImage();
        });
    }
    if (saveBtn) {
        saveBtn.addEventListener('click', async () => {
            if (!globals.currentVideoId) {
                alert('No video loaded.');
                return;
            }
            try {
                const response = await fetch(`/annotation/commit_video_preannotations/${projectName}/${globals.currentVideoId}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({})
                });
                if (!response.ok) throw new Error('Commit request failed');
                await reloadAnnotations();
                console.log('Committed all preannotations for video');
                showToast('All preannotations transferred to annotations for this video.', 'success');
            } catch (e) {
                console.error('Commit error:', e);
                alert('Error committing preannotations: ' + e.message);
            }
        });
    }
    if (prevVideoBtn) {
        prevVideoBtn.addEventListener('click', () => navigateVideo(-1));
    }
    if (nextVideoBtn) {
        nextVideoBtn.addEventListener('click', () => navigateVideo(1));
    }

    function getFilenameFromHeaders(headers) {
        const disposition = headers.get('Content-Disposition');
        if (disposition && disposition.includes('filename=')) {
            const filenameMatch = disposition.match(/filename[^;=\s]*=['"]?([^'"\s;]+)/);
            return filenameMatch ? filenameMatch[1] : null;
        }
        return null;
    }

    // Export Modal Setup
    const exportModal = document.getElementById('export-modal');
    const videosCheckboxes = document.getElementById('videos-checkboxes');
    const exportCancel = document.getElementById('export-cancel');
    const exportStart = document.getElementById('export-start');

    let selectedFormat = null;

    function resetExportModal() {
        videosCheckboxes.innerHTML = '';
        selectedFormat = null;
        document.querySelectorAll('.format-option').forEach(opt => {
            opt.classList.remove('selected');
        });
        // Add click listeners to format options
        document.querySelectorAll('#format-options .format-option').forEach(div => {
            div.addEventListener('click', () => {
                document.querySelectorAll('.format-option').forEach(opt => opt.classList.remove('selected'));
                div.classList.add('selected');
                selectedFormat = div.dataset.value;
            });
        });
        // Populate videos checkboxes
        Array.from(videoItems).forEach(item => {
            const checkbox = document.createElement('div');
            checkbox.className = 'video-checkbox-item';
            const videoId = item.dataset.videoPath || item.dataset.videoId || item.dataset.url.split('/').pop();  // Fallback to filename if needed
            checkbox.innerHTML = `
                <input type="checkbox" value="${videoId}" id="video-${item.dataset.videoId}">
                <label for="video-${item.dataset.videoId}">${item.querySelector('p').textContent}</label>
            `;
            videosCheckboxes.appendChild(checkbox);
            const input = checkbox.querySelector('input');
            if (input) input.checked = true;
        });
        // Reset path input and checkboxes
        const exportPathInput = document.getElementById('export-path');
        if (exportPathInput) exportPathInput.value = '';
        const localExportCheckbox = document.getElementById('local-export');
        if (localExportCheckbox) localExportCheckbox.checked = false;
        const extractFramesCheckbox = document.getElementById('extract-frames');
        if (extractFramesCheckbox) extractFramesCheckbox.checked = false;
    }

    if (exportBtn) {
        exportBtn.addEventListener('click', () => {
            resetExportModal();
            if (exportModal) exportModal.style.display = 'block';
        });
    }

    if (exportCancel) {
        exportCancel.addEventListener('click', () => {
            if (exportModal) exportModal.style.display = 'none';
        });
    }

    if (exportStart) {
        exportStart.addEventListener('click', async () => {
            // validation
            if (!selectedFormat) {
                showToast('Please select a format.', 'warning');
                return;
            }
            if (!videosCheckboxes) {
                showToast('No videos available to export.', 'warning');
                return;
            }
            const selectedVideos = Array.from(videosCheckboxes.querySelectorAll('input:checked'))
                .map(cb => cb.value.trim())  // NEW: Trim whitespace
                .filter(v => v);  // NEW: Filter empty/invalid paths
            if (selectedVideos.length === 0) {
                showToast('Please select at least one video.', 'warning');
                return;
            }

            const extractFrames = document.getElementById('extract-frames')?.checked || false;
            const semantic = document.getElementById('semantic-mask')?.checked || false;
            const localExport = document.getElementById('local-export')?.checked || false;
            let exportPath = '/tmp';
            if (localExport) {
                const pathInput = document.getElementById('export-path');
                if (!pathInput || !pathInput.value.trim()) {
                    showToast('Please enter a local path for export.', 'warning');
                    return;
                }
                exportPath = pathInput.value.trim();
                // Basic client-side heuristic to avoid obvious client-side paths
                if (exportPath.startsWith('C:\\') || exportPath.startsWith('/Users/') || exportPath.includes('Downloads')) {
                    showToast('Path appears to be client-side; use a server-accessible directory (e.g., /home/user/exports).', 'warning');
                    return;
                }
                console.log(`sending local path ${exportPath} to backend`);
            }

            const payload = {
                format: selectedFormat,
                videos: selectedVideos,  // Now filtered
                extract_frames: extractFrames,
                semantic: semantic,
                export_path: exportPath,
                local_export: localExport
            };
            console.log('Export payload:', payload);

            try {
                const resp = await fetch(`/annotation/export/${encodeURIComponent(projectName)}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });

                console.log('Export response status:', resp.status);
                console.log('Export response headers:', Object.fromEntries(resp.headers.entries()));

                if (!resp.ok) {
                    let errText = 'Export failed';
                    // FIXED: Check if body already read (e.g., after failed json)
                    if (!resp.bodyUsed) {
                        try {
                            const j = await resp.json();
                            errText = j.detail || j.error || JSON.stringify(j);
                        } catch (_e) {
                            try {
                                errText = await resp.text();
                            } catch (_) {
                                errText = `HTTP ${resp.status}`;
                            }
                        }
                    }
                    throw new Error(errText);
                }

                // Success handling
                if (localExport) {
                    // FIXED: Force JSON for local (ignore content-type; assume backend sends JSON)
                    const data = await resp.json();
                    console.log('Local export data:', data);
                    if (data.success) {
                        showToast(`Export saved to: ${data.saved_path}`, 'success');
                    } else {
                        throw new Error(data.error || 'Export failed');
                    }
                } else {
                    // Non-local: download blob
                    const filename = getFilenameFromHeaders(resp.headers) || `${projectName}_${selectedFormat}.zip`;
                    const blob = await resp.blob();
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = filename;
                    document.body.appendChild(a);
                    a.click();
                    a.remove();
                    URL.revokeObjectURL(url);
                    showToast('Export completed successfully!', 'success');
                }

                if (exportModal) exportModal.style.display = 'none';
            } catch (e) {
                console.error('Export error:', e);
                showToast('Export failed: ' + (e.message || e), 'error');
            }
        });
    }
    
    function handleSegmentRemoval(button, endpoint, action, confirmMsg) {
        if (!globals.selectedRange) {
            showToast('Please select a range on the timeline first.', 'warning');
            return;
        }
        const start_frame = globals.frames[globals.selectedRange.start].frame_number;
        const end_frame = globals.frames[globals.selectedRange.end].frame_number;
        const successMsg = `Removed ${action} from frames ${start_frame}-${end_frame}`;
        showConfirm(button, confirmMsg, async () => {
            const videoId = globals.currentVideoId;
            try {
                const response = await fetch(`/annotation/${endpoint}/${projectName}/${videoId}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ start_frame, end_frame })
                });
                if (!response.ok) throw new Error('Delete request failed');
                const data = await response.json();
                globals.selectedRange = null;
                await reloadAnnotations();
                showToast(successMsg, 'success');
            } catch (e) {
                alert(`Error removing ${action}: ` + e.message);
            }
        });
    }

    if (removeSegmentAnnotationsBtn) {
        removeSegmentAnnotationsBtn.addEventListener('click', () => {
            handleSegmentRemoval(removeSegmentAnnotationsBtn, 'delete_segment_annotations', 'annotations', 'Are you sure you want to remove annotations from the selected segment?');
        });
    }
    if (removeSegmentPreannotationsBtn) {
        removeSegmentPreannotationsBtn.addEventListener('click', () => {
            handleSegmentRemoval(removeSegmentPreannotationsBtn, 'delete_segment_preannotations', 'preannotations', 'Are you sure you want to remove preannotations from the selected segment?');
        });
    }

    function navigateVideo(direction) {
        if (!videoItems || videoItems.length === 0) return;
        const currentIndex = Array.from(videoItems).indexOf(globals.currentItem);
        const newIndex = (currentIndex + direction + videoItems.length) % videoItems.length;
        videoItems[newIndex].click();
    }

    const trackerModal = document.getElementById('tracker-modal');
    const step1 = document.getElementById('step1');
    const step2 = document.getElementById('step2');
    const prevBtn = document.getElementById('prev-step');
    const nextBtn = document.getElementById('next-step');
    const startBtn = document.getElementById('start-tracking');
    const cancelBtn = document.getElementById('cancel-tracking');

    let selectedMethod = null;

    if (document.querySelectorAll('.method-option').length > 0) {
        document.querySelectorAll('.method-option').forEach(option => {
            option.addEventListener('click', () => {
                document.querySelectorAll('.method-option').forEach(opt => {
                    opt.style.border = '2px solid #ccc';
                    opt.classList.remove('selected');
                });
                option.style.border = '2px solid #007bff';
                option.classList.add('selected');
                selectedMethod = option.dataset.method;
            });
        });
    }

    // Cancel button
    if (cancelBtn) {
        cancelBtn.addEventListener('click', () => {
            if (trackerModal) trackerModal.style.display = 'none';
            resetModal();
        });
    }

    function resetModal() {
        if (step1) step1.style.display = 'flex';
        if (step2) step2.style.display = 'none';
        if (prevBtn) prevBtn.style.display = 'none';
        if (nextBtn) nextBtn.style.display = 'block';
        if (startBtn) startBtn.style.display = 'none';
        selectedMethod = null;
        document.querySelectorAll('.method-option').forEach(opt => {
            opt.style.border = '2px solid #ccc';
            opt.classList.remove('selected');
        });
        ['cv2-config', 'interpolate-config', 'sam2-config'].forEach(id => {
            const el = document.getElementById(id);
            if (el) el.style.display = 'none';
        });
    }
    // Function to add option button listeners
    function addOptionListeners(containerId, className = 'option-btn') {
        const container = document.getElementById(containerId);
        if (!container) return;
        container.querySelectorAll(`.${className}`).forEach(btn => {
            btn.addEventListener('click', () => {
                container.querySelectorAll(`.${className}`).forEach(b => {
                    b.classList.remove('selected');
                    b.style.borderColor = '#e0e0e0';
                    b.style.background = '#fafafa';
                    b.style.color = '#555';
                    b.style.transform = 'none';
                    b.style.boxShadow = 'none';
                });
                btn.classList.add('selected');
                btn.style.borderColor = '#007bff';
                btn.style.background = '#e3f2fd';
                btn.style.color = '#0056b3';
            });
        });
    }
    // Next button (proceed to step 2)
    if (nextBtn) {
        nextBtn.addEventListener('click', async () => {
            if (!selectedMethod) {
                showToast('Please select a tracking method.', 'warning');
                return;
            }
            if (step1) step1.style.display = 'none';
            if (step2) step2.style.display = 'flex';
            if (prevBtn) prevBtn.style.display = 'block';
            if (nextBtn) nextBtn.style.display = 'none';
            if (startBtn) startBtn.style.display = 'block';
            const configId = `${selectedMethod}-config`;
            const configEl = document.getElementById(configId);
            if (configEl) configEl.style.display = 'block';
            // Add listeners based on method
            if (selectedMethod === 'cv2') {
                addOptionListeners('tracker-types');
            } else if (selectedMethod === 'sam2') {
                addOptionListeners('device-types');
                addOptionListeners('sam-models');
                // Check GPU availability
                try {
                    const resp = await fetch('/annotation/check_gpu');
                    if (!resp.ok) throw new Error('GPU check failed');
                    const data = await resp.json();
                    const deviceContainer = document.getElementById('device-types');
                    if (data.has_gpu) {
                        const cudaBtn = deviceContainer.querySelector('.option-btn[data-value="cuda"]');
                        if (cudaBtn) cudaBtn.click();
                    } else {
                        const cpuBtn = deviceContainer.querySelector('.option-btn[data-value="cpu"]');
                        if (cpuBtn) cpuBtn.click();
                        const cudaBtn = deviceContainer.querySelector('.option-btn[data-value="cuda"]');
                        if (cudaBtn) {
                            cudaBtn.style.opacity = '0.5';
                            cudaBtn.style.cursor = 'not-allowed';
                            cudaBtn.style.pointerEvents = 'none';
                        }
                    }
                } catch (e) {
                    console.error('GPU check failed:', e);
                    const cpuBtn = document.getElementById('device-types')?.querySelector('.option-btn[data-value="cpu"]');
                    if (cpuBtn) cpuBtn.click();
                }
            }
        });
    }
    // Previous button (back to step 1)
    if (prevBtn) {
        prevBtn.addEventListener('click', () => {
            if (step1) step1.style.display = 'flex';
            if (step2) step2.style.display = 'none';
            if (prevBtn) prevBtn.style.display = 'none';
            if (nextBtn) nextBtn.style.display = 'block';
            if (startBtn) startBtn.style.display = 'none';
            ['cv2-config', 'interpolate-config', 'sam2-config'].forEach(id => {
                const el = document.getElementById(id);
                if (el) el.style.display = 'none';
            });
        });
    }

    // Start tracking button
    if (startBtn) {
        startBtn.addEventListener('click', async () => {
            const method = selectedMethod;
            if (!globals.currentItem || !globals.selectedRange) {
                showToast('No video or range selected.', 'warning');
                return;
            }
            const videoId = globals.currentItem.dataset.videoId;
            if (!videoId) {
                showToast('Missing video ID for tracking.', 'warning');
                return;
            }
            const start_frame = globals.frames[globals.selectedRange.start].frame_number;
            const end_frame = globals.frames[globals.selectedRange.end].frame_number;

            const annotatedFrames = [];
            for (let i = globals.selectedRange.start; i <= globals.selectedRange.end; i++) {
                const annos = globals.annotationMap[i] || [];
                if (annos.length > 0) {
                    annotatedFrames.push({ 
                        index: i, 
                        frame_number: globals.frames[i].frame_number, 
                        annos 
                    });
                }
            }

            if (annotatedFrames.length === 0) {
                showToast('No annotated frames in selected range.', 'warning');
                return;
            }

            let useKeyframes = false;
            let payload = {
                method: method,
                start_frame: start_frame,
                end_frame: end_frame, 
            };

            if (method === 'cv2') {
                const selectedTrackerTypeBtn = document.querySelector('#tracker-types .option-btn.selected');
                if (selectedTrackerTypeBtn) payload.tracker_type = selectedTrackerTypeBtn.dataset.value;
                const useKeyframesEl = document.getElementById('use-keyframes');
                useKeyframes = useKeyframesEl ? useKeyframesEl.checked : false;
                payload.use_keyframes = useKeyframes;
            } else if (method === 'sam2') {
                payload.output_type = setupType === 'Video Segmentation' ? 'mask' : 'bbox';
                const selectedDeviceBtn = document.querySelector('#device-types .option-btn.selected');
                if (selectedDeviceBtn) payload.device = selectedDeviceBtn.dataset.value;
                const selectedSamModelBtn = document.querySelector('#sam-models .option-btn.selected');
                if (selectedSamModelBtn) payload.sam_model = selectedSamModelBtn.dataset.value;
                useKeyframes = false;  // Disable keyframes for SAM2
            } else if (method === 'interpolate') {
                if (annotatedFrames.length < 2) {
                    const annotatedFramesDebug = [];
                    for (let i = globals.selectedRange.start; i <= globals.selectedRange.end; i++) {
                        const annos = globals.annotationMap[i] || [];
                        if (annos.length > 0) annotatedFramesDebug.push(i);
                    }
                    console.log('selectedRange', globals.selectedRange, 'annotated frames in range:', annotatedFramesDebug);
                    showToast('Interpolation requires at least 2 annotated frames in the range.', 'warning');
                    return;
                }
                // REMOVED: Strict start/end check; backend handles any keyframes
                useKeyframes = true;
                payload.use_keyframes = true;
            }

            // Collect initial_annotations
            let initial_annotations = [];
            const collectInitAnno = (anno, frame_number) => { 
                let initAnno;
                // If polygon -> compute bbox (x,y,w,h) and keep segmentation if you want
                if (anno.type === 'polygon') {
                    const xs = anno.points.map(p => p.x);
                    const ys = anno.points.map(p => p.y);
                    const minX = Math.min(...xs);
                    const minY = Math.min(...ys);
                    const maxX = Math.max(...xs);
                    const maxY = Math.max(...ys);
                    const bbox = [minX, minY, maxX - minX, maxY - minY];

                    initAnno = {
                        bbox,
                        label: anno.label,
                        keyframe_frame: frame_number, 
                        // optional: include segmentation (list of [x,y]) for debugging/audit; backend will prefer bbox
                        segmentation: anno.points.map(p => [p.x, p.y])
                    };
                } else {
                    // rect / bbox annotation already available
                    const bbox = [anno.x, anno.y, anno.width, anno.height];
                    initAnno = {
                        bbox,
                        label: anno.label,
                        keyframe_frame: frame_number 
                    };
                }
                initial_annotations.push(initAnno);
            };

            if (useKeyframes) {
                annotatedFrames.forEach(af => {
                    af.annos.forEach(anno => collectInitAnno(anno, af.frame_number));  
                });
            } else {
                const firstAnnotated = annotatedFrames[0] || { annos: globals.annotations, frame_number: start_frame };
                if (firstAnnotated.annos.length === 0) {
                    showToast('At least one frame must be annotated.', 'warning');
                    return;
                }
                firstAnnotated.annos.forEach(anno => collectInitAnno(anno, firstAnnotated.frame_number));
            }
            payload.initial_annotations = initial_annotations;

            if (trackerModal) trackerModal.style.display = 'none';
            resetModal();

            try {
                const response = await fetch(`/annotation/track_objects/${projectName}/${videoId}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                if (!response.ok) throw new Error('Tracking request failed');
                const data = await response.json();
                const key = data.key;

                // Polling
                const interval = setInterval(async () => {
                    const pollResponse = await fetch(`/annotation/check_tracking_status?key=${key}`);
                    const pollData = await pollResponse.json();
                    if (pollData.status === 'completed') {
                        clearInterval(interval);
                        await reloadFrames();
                        await reloadAnnotations();
                        showToast('Tracking completed and applied', 'success');
                    } else if (pollData.status === 'failed') {
                        clearInterval(interval);
                        alert('Tracking failed');
                    }
                }, 2000);
            } catch (e) {
                alert('Error starting tracking: ' + e.message);
            }
        });
    }

    const trackerBtn = document.getElementById('vf-tracker-btn');
    if (trackerBtn) {
        trackerBtn.addEventListener('click', () => {
            if (!globals.currentItem) {
                showToast('No video selected', 'warning');
                return;
            }
            if (!globals.selectedRange) {
                showToast('Please select a range on the timeline first.', 'warning');
                return;
            }

            if (trackerModal) trackerModal.style.display = 'block';
            resetModal();  // Reset state each time modal opens

            // Optional: Restrict methods based on setupType
            if (setupType === 'Video Segmentation') {
                const sam2Option = document.querySelector('.method-option[data-method="sam2"]');
                const cv2Option = document.querySelector('.method-option[data-method="cv2"]');
                const interpolateOption = document.querySelector('.method-option[data-method="interpolate"]');
                if (sam2Option) sam2Option.click();  // Auto-select SAM2
                if (cv2Option) cv2Option.style.display = 'none';
                if (interpolateOption) interpolateOption.style.display = 'none';
            }
        });
    }

    // =========================
    // STATE HELPERS
    // =========================
    function setMode(newMode) { 
        if (globals.mode === 'polygon' && globals.currentAnnotation && !globals.currentAnnotation.closed) {
            // Discard unfinished polygon
            globals.currentAnnotation = null;
            globals.previewPoint = null;
            updateMapAndTimeline();
        }
        globals.mode = newMode; 
        updateButtonStates(); 
        console.log('Mode set to:', newMode); 
    }
    function setGridEnabled(val) { 
        globals.gridEnabled = val; 
        if (gridBtn) gridBtn.classList.toggle('active', val);
        drawImage(); 
    }
    function setSelectedAnnotation(val) { globals.selectedAnnotation = val; drawImage(); }
    function setCurrentAnnotation(val) { globals.currentAnnotation = val; }
    function pushToUndoStack() {
        if (!globals.undoStack[globals.currentFrameIndex]) globals.undoStack[globals.currentFrameIndex] = [];
        globals.undoStack[globals.currentFrameIndex].push(JSON.parse(JSON.stringify(globals.annotations)));
    }

    function updateButtonStates() {
        // FIXED: Use correct button refs
        if (rectBtn) rectBtn.classList.toggle('active', globals.mode === 'rect');
        if (polygonBtn) polygonBtn.classList.toggle('active', globals.mode === 'polygon');
        // if (magicBtn) magicBtn.classList.toggle('active', globals.mode === 'magic');
        if (selectBtn) selectBtn.classList.toggle('active', globals.mode === 'select');
    }

    // =========================
    // CANVAS RESIZE
    // =========================
    function resizeCanvas() {
        if (!canvas) return;
        canvas.width = canvas.parentElement.clientWidth;
        canvas.height = canvas.parentElement.clientHeight;
        drawImage();
    }
    window.addEventListener('resize', resizeCanvas);
    resizeCanvas();

    // =========================
    // DRAW VIDEO + ANNOTATIONS (with grid)
    // =========================
    function resetView() {
        if (!globals.currentVideo || !canvas) return;
        const zoomX = canvas.width / globals.currentVideo.videoWidth;
        const zoomY = canvas.height / globals.currentVideo.videoHeight;
        globals.viewport.zoom = Math.min(zoomX, zoomY);
        globals.viewport.x = (canvas.width - globals.currentVideo.videoWidth * globals.viewport.zoom) / 2;
        globals.viewport.y = (canvas.height - globals.currentVideo.videoHeight * globals.viewport.zoom) / 2;
        drawImage();
    }

    function clampView() {
        if (!globals.currentVideo || !canvas) return;
        const scaledW = globals.currentVideo.videoWidth * globals.viewport.zoom;
        const scaledH = globals.currentVideo.videoHeight * globals.viewport.zoom;
        if (scaledW <= canvas.width) {
            globals.viewport.x = (canvas.width - scaledW) / 2;
        } else {
            globals.viewport.x = Math.min(0, Math.max(canvas.width - scaledW, globals.viewport.x));
        }
        if (scaledH <= canvas.height) {
            globals.viewport.y = (canvas.height - scaledH) / 2;
        } else {
            globals.viewport.y = Math.min(0, Math.max(canvas.height - scaledH, globals.viewport.y));
        }
    }

    function drawGrid() {
        if (!globals.gridEnabled || !globals.currentVideo || !ctx) return;
        const { x, y, zoom } = globals.viewport;
        const gridSize = 5 / zoom; 
        ctx.strokeStyle = 'rgba(0,0,0,0.1)';
        ctx.lineWidth = 1 / zoom;
        const startX = Math.max(0, -x / zoom);
        const endX = Math.min(globals.currentVideo.videoWidth, (canvas.width - x) / zoom);
        const startY = Math.max(0, -y / zoom);
        const endY = Math.min(globals.currentVideo.videoHeight, (canvas.height - y) / zoom);
        for (let gx = Math.floor(startX / gridSize) * gridSize; gx < endX; gx += gridSize) {
            const canvasX = x + gx * zoom;
            ctx.beginPath();
            ctx.moveTo(canvasX, y);
            ctx.lineTo(canvasX, y + globals.currentVideo.videoHeight * zoom);
            ctx.stroke();
        }
        for (let gy = Math.floor(startY / gridSize) * gridSize; gy < endY; gy += gridSize) {
            const canvasY = y + gy * zoom;
            ctx.beginPath();
            ctx.moveTo(x, canvasY);
            ctx.lineTo(x + globals.currentVideo.videoWidth * zoom, canvasY);
            ctx.stroke();
        }
    }

    function drawSelectionHandles(anno) {
        if (!anno || !ctx) return;
        if (anno.type === 'rect') {
            const x = globals.viewport.x + anno.x * globals.viewport.zoom;
            const y = globals.viewport.y + anno.y * globals.viewport.zoom;
            const w = anno.width * globals.viewport.zoom;
            const h = anno.height * globals.viewport.zoom;
            const handles = [
                {x: x, y: y},
                {x: x + w, y: y},
                {x: x, y: y + h},
                {x: x + w, y: y + h},
                {x: x + w / 2, y: y},
                {x: x + w / 2, y: y + h},
                {x: x, y: y + h / 2},
                {x: x + w, y: y + h / 2}
            ];
            ctx.fillStyle = 'red';
            handles.forEach(h => {
                ctx.beginPath();
                ctx.arc(h.x, h.y, 5, 0, 2 * Math.PI);
                ctx.fill();
            });
        } else if (anno.type === 'polygon') {
            ctx.fillStyle = 'red';
            anno.points.forEach((point, index) => {
                const p = toCanvasCoords(point.x, point.y, globals.viewport);
                ctx.beginPath();
                ctx.arc(p.x, p.y, 5, 0, 2 * Math.PI);
                ctx.fill();
                if (index === globals.selectedPointIndex) {
                    ctx.beginPath();
                    ctx.arc(p.x, p.y, 10, 0, 2 * Math.PI);
                    ctx.strokeStyle = 'blue';
                    ctx.lineWidth = 3;
                    ctx.stroke();
                }
            });
        }
    }

    function drawImage() {
        if (!globals.currentVideo || !ctx) return;
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        clampView();
        ctx.drawImage(globals.currentVideo, globals.viewport.x, globals.viewport.y, globals.currentVideo.videoWidth * globals.viewport.zoom, globals.currentVideo.videoHeight * globals.viewport.zoom);
        drawGrid();

        // Draw annotations
        globals.annotations.forEach(a => {
            const color = globals.classColors[a.label || ''] || '#cccccc';
            ctx.fillStyle = color + '33';
            ctx.strokeStyle = color;
            const lw = (a === globals.selectedAnnotation) ? 3 : 2;
            ctx.lineWidth = lw;
            const isPre = a.isPreannotation || false;
            if (isPre && !(a === globals.selectedAnnotation)) {
                // Dashed animated for preannotations (unless selected)
                ctx.setLineDash([5, 5]);
                ctx.lineDashOffset = -(Date.now() / 200) % 10;
            } else {
                ctx.setLineDash([]);
            }
            if (a.type === "rect") {
                ctx.fillRect(globals.viewport.x + a.x * globals.viewport.zoom, globals.viewport.y + a.y * globals.viewport.zoom, a.width * globals.viewport.zoom, a.height * globals.viewport.zoom);
                ctx.strokeRect(globals.viewport.x + a.x * globals.viewport.zoom, globals.viewport.y + a.y * globals.viewport.zoom, a.width * globals.viewport.zoom, a.height * globals.viewport.zoom);
            } else if (a.type === "polygon") {
                if (a.points.length < 1) return;
                ctx.beginPath();
                const first = toCanvasCoords(a.points[0].x, a.points[0].y, globals.viewport);
                ctx.moveTo(first.x, first.y);
                for (let i = 1; i < a.points.length; i++) {
                    const p = toCanvasCoords(a.points[i].x, a.points[i].y, globals.viewport);
                    ctx.lineTo(p.x, p.y);
                }
                if (a.closed) {
                    ctx.closePath();
                }
                ctx.fill();
                ctx.stroke();
            }
            // Reset dash after drawing
            ctx.setLineDash([]);
        });

        if (globals.currentAnnotation && globals.currentAnnotation.type === 'polygon' && !globals.currentAnnotation.closed) {
            const a = globals.currentAnnotation;
            const color = globals.classColors[a.label || ''] || '#cccccc';
            ctx.fillStyle = color + '33';
            ctx.strokeStyle = color;
            ctx.lineWidth = 2;
            const hasPoints = a.points.length > 0;
            let first = null;
            if (hasPoints) {
                first = toCanvasCoords(a.points[0].x, a.points[0].y, globals.viewport);
                ctx.beginPath();
                ctx.moveTo(first.x, first.y);
                for (let i = 1; i < a.points.length; i++) {
                    const p = toCanvasCoords(a.points[i].x, a.points[i].y, globals.viewport);
                    ctx.lineTo(p.x, p.y);
                }
                // Draw fixed points as red circles
                a.points.forEach(point => {
                    const p = toCanvasCoords(point.x, point.y, globals.viewport);
                    ctx.beginPath();
                    ctx.arc(p.x, p.y, 5, 0, 2 * Math.PI);
                    ctx.fillStyle = 'red';
                    ctx.fill();
                });
                console.log('Current polygon points:', a.points.map(p => `(${p.x.toFixed(1)}, ${p.y.toFixed(1)})`).join(' -> '));
            }
            if (globals.previewPoint && hasPoints) {
                const lastPoint = a.points[a.points.length - 1];
                const last = toCanvasCoords(lastPoint.x, lastPoint.y, globals.viewport);
                const prev = toCanvasCoords(globals.previewPoint.x, globals.previewPoint.y, globals.viewport);
                ctx.lineTo(prev.x, prev.y);
                // Preview point circle
                ctx.beginPath();
                ctx.arc(prev.x, prev.y, 5, 0, 2 * Math.PI);
                ctx.fillStyle = 'red';
                ctx.fill();
                // Check for closing preview
                const firstImg = a.points[0];
                const dist = Math.hypot(globals.previewPoint.x - firstImg.x, globals.previewPoint.y - firstImg.y);
                if (dist < 10 && a.points.length >= 2) {
                    ctx.lineTo(first.x, first.y);
                    ctx.closePath();
                    ctx.globalAlpha = 0.7;
                    ctx.fill();
                    ctx.globalAlpha = 1.0;
                }
            }
            ctx.stroke();
        }

        // Draw selection handles if selected
        if (globals.selectedAnnotation) { drawSelectionHandles(globals.selectedAnnotation); }
        const hasUnselectedPre = globals.annotations.some(a => a.isPreannotation && a !== globals.selectedAnnotation);
        if (hasUnselectedPre && !globals.isPlaying) {
            if (!globals.animationInterval) {
                globals.animationInterval = setInterval(drawImage, 100);
            }
        } else if (globals.animationInterval) {
            clearInterval(globals.animationInterval);
            globals.animationInterval = null;
        }
    }

    setupAnnotationInteractions(drawImage, pushToUndoStack, setSelectedAnnotation, clampView);
    if (canvas) {
        canvas.addEventListener('mousedown', (e) => {
            if (e.shiftKey && !globals.isPanning) {
                globals.isPanning = true;
                globals.panStart = { x: e.clientX, y: e.clientY };
                e.preventDefault();
            }
        });

        canvas.addEventListener('mousemove', (e) => {
            if (globals.isPanning) {
                const dx = e.clientX - globals.panStart.x;
                const dy = e.clientY - globals.panStart.y;
                globals.viewport.x += dx;
                globals.viewport.y += dy;
                globals.panStart = { x: e.clientX, y: e.clientY };
                drawImage();
                clampView();
                e.preventDefault();
            }
        });

        canvas.addEventListener('mouseup', (e) => {
            if (globals.isPanning) {
                globals.isPanning = false;
                e.preventDefault();
            }
        });

        canvas.addEventListener('mouseleave', (e) => {
            if (globals.isPanning) {
                globals.isPanning = false;
            }
        });
    }
    
    // =========================
    // VIDEO LOADING & THUMBNAILS
    // =========================
    // Load thumbnails in parallel
    if (videoItems && videoItems.length > 0) {
        const thumbPromises = Array.from(videoItems).map(async item => {
            const img = item.querySelector('img');
            if (!img) return;
            const videoUrl = img.dataset.videoUrl; // FIXED: Use videoUrl consistently
            if (!videoUrl) return;
            const video = document.createElement('video');
            video.preload = "auto";   // important: force metadata
            video.src = videoUrl;

            await new Promise((resolve, reject) => {
                let resolved = false;

                video.onloadedmetadata = () => {
                    video.currentTime = 0;
                };

                video.onseeked = () => {
                    if (resolved) return;
                    resolved = true;
                    const tempCanvas = document.createElement('canvas');
                    tempCanvas.width = video.videoWidth;
                    tempCanvas.height = video.videoHeight;
                    tempCanvas.getContext('2d').drawImage(video, 0, 0);
                    img.src = tempCanvas.toDataURL('image/jpeg');
                    resolve();
                };

                video.onerror = e => {
                    if (!resolved) reject(new Error('Thumbnail error: ' + (e.target ? e.target.error.message || e.target.error.code : 'Unknown')));
                };

                // fallback: if `seeked` never fires, resolve anyway
                setTimeout(() => {
                    if (!resolved) {
                        resolved = true;
                        console.warn("Seeked event timed out, capturing anyway.");
                        const tempCanvas = document.createElement('canvas');
                        tempCanvas.width = video.videoWidth || 160;
                        tempCanvas.height = video.videoHeight || 90;
                        tempCanvas.getContext('2d').drawImage(video, 0, 0);
                        img.src = tempCanvas.toDataURL('image/jpeg');
                        resolve();
                    }
                }, 2000);
            });
        });
        await Promise.all(thumbPromises);
    }

    if (videoItems) {
        videoItems.forEach(item => {
            item.addEventListener('click', () => {
                videoItems.forEach(i => i.classList.remove('selected'));
                item.classList.add('selected');
                globals.currentItem = item;
                const videoUrl = item.dataset.url;
                const videoId = item.dataset.videoId;
                if (videoUrl && videoId) {
                    loadVideo(videoUrl, videoId);
                } else {
                    console.error('Video item missing URL or ID:', { url: videoUrl, id: videoId });
                }
            });
        });
    }

    globals.hiddenVideo.style.display = 'none';
    document.body.appendChild(globals.hiddenVideo);

    async function loadVideo(url, videoId) {
        // Safeguard: Check for required params
        if (!url) {
            console.error('Missing video URL');
            return;
        }
        if (!videoId) {
            console.error('Missing video ID:', videoId);
            alert('Cannot load video: Missing ID. Check console for details.');
            return;
        }

        globals.currentVideoId = videoId;

        // Reset state
        if (globals.currentVideo) globals.currentVideo.pause();
        globals.currentVideo.src = url;
        
        // Show loading overlay (it's already visible from HTML, but ensure)
        const loadingOverlay = document.getElementById('loading-overlay');
        if (loadingOverlay) loadingOverlay.style.display = 'flex';

        // Disable buttons during loading
        const buttonsToDisable = [playPauseBtn, firstFrameBtn, lastFrameBtn, prevFrameBtn, nextFrameBtn, loopBtn, trackerBtn, exportBtn];
        buttonsToDisable.forEach(btn => btn && (btn.disabled = true));

        try {
            await new Promise((resolve, reject) => {
                if (!globals.currentVideo) {
                    reject(new Error('No video element available'));
                    return;
                }

                globals.currentVideo.oncanplaythrough = () => {
                    resizeCanvas();
                    resetView();
                    // Hide loading overlay
                    if (loadingOverlay) loadingOverlay.style.display = 'none';
                    // Re-enable buttons
                    buttonsToDisable.forEach(btn => btn && (btn.disabled = false));
                    resolve();
                };

                globals.currentVideo.onstalled = () => console.warn('Video stalled temporarily – waiting for data...');  // Log for debug

                globals.currentVideo.onerror = e => {
                    const errorMsg = e.target ? (e.target.error ? e.target.error.message || `MediaError code ${e.target.error.code}` : 'Unknown video error') : 'Unknown error';
                    reject(new Error('Video load error: ' + errorMsg));
                };

                // Optional: Add timeout (adjust seconds as needed)
                setTimeout(() => {
                    reject(new Error('Video loading timed out after 30 seconds'));
                }, 30000);

                globals.currentVideo.removeEventListener('seeked', handleSeeked);
                globals.currentVideo.load(); // Explicitly trigger loading
            });
        } catch (error) {
            console.error('Video load failed:', error);
            // Hide overlay and re-enable buttons on error to avoid stuck state
            if (loadingOverlay) loadingOverlay.style.display = 'none';
            buttonsToDisable.forEach(btn => btn && (btn.disabled = false));
            alert('Failed to load video: ' + error.message);
            return;  // Exit early on error
        }

        if (!globals.currentItem) return;
        if (videoName) videoName.textContent = globals.currentItem.querySelector('img').alt.replace('First frame of ', '');

        try {
            const response = await fetch(`/annotation/get_frames/${projectName}/${videoId}`);
            const frameData = await response.json();  // {frames: [...], fps: num}
            let rawFrames = frameData.frames || [];
            globals.fps = frameData.fps || globals.currentVideo.fps || 30.0; 
            if (!Array.isArray(rawFrames)) rawFrames = [];
            const normalized = rawFrames.map(f => ({
                frame_number: f.frame_number,
                subsampled: f.subsampled,
                timestamp: Number(f.timestamp)  // Keep ts
            })).filter(f => Number.isFinite(f.timestamp) && f.timestamp >= 0 && f.timestamp <= globals.currentVideo.duration);
            globals.frames = normalized.sort((a, b) => a.frame_number - b.frame_number);  // Sort by frame_number (sequential)
        } catch (e) {
            console.error("Frame fetch error:", e);
            globals.frames = [];
        }

        globals.annotationMap = Array(globals.frames.length).fill().map(() => []);
        globals.undoStack = Array(globals.frames.length).fill().map(() => []);
        globals.classToRow = {};
        globals.nextRow = 0;

        try {
            const annoResp = await fetch(`/annotation/get_video_annotations/${projectName}/${videoId}`);
            const allAnnos = await annoResp.json();

            for (let i = 0; i < globals.frames.length; i++) {
                const fn = globals.frames[i].frame_number;
                const data = allAnnos[fn] || { annotations: [], preannotations: [] };
                
                // Map annotations
                const mappedAnnotations = (() => {
                    try {
                        return data.annotations.map(a => {
                            if (a.type === 'segmentation') {
                                let seg = a.segmentation;
                                if (typeof seg === 'string') {
                                    seg = JSON.parse(seg || '[]');
                                } else if (Array.isArray(seg) && seg.length === 1 && Array.isArray(seg[0])) {
                                    seg = seg[0];
                                } else if (!Array.isArray(seg)) {
                                    console.warn('Invalid segmentation (not array):', seg, 'for anno', a.id || a.preannotation_id);
                                    seg = [];
                                }
                                // Prefer existing points if available and valid
                                let points = a.points || [];
                                if (!Array.isArray(points) || points.length === 0 || !points[0].x) {
                                    // Fall back to computing from seg (now flat)
                                    points = [];
                                    if (Array.isArray(seg)) {
                                        for (let k = 0; k < seg.length; k += 2) {
                                            if (k + 1 < seg.length) {
                                                points.push({ x: seg[k], y: seg[k + 1] });
                                            } else {
                                                console.warn('Odd number of coordinates in segmentation for anno', a.id || a.preannotation_id);
                                                break;
                                            }
                                        }
                                    }
                                }
                                const mapped = {
                                    type: 'polygon',
                                    points,
                                    closed: true,
                                    label: a.label || a.class_name,
                                    isPreannotation: false
                                };
                                return mapped;
                            } else if (a.type === 'bbox' || a.type === 'rect') {
                                let bbox = a.bbox;
                                if (typeof bbox === 'string') {
                                    bbox = JSON.parse(bbox || '[]');
                                } else if (!Array.isArray(bbox)) {
                                    console.warn('Invalid bbox (not array):', bbox, 'for anno', a.id || a.preannotation_id);
                                    bbox = [0, 0, 0, 0];
                                }
                                const mapped = {
                                    type: 'rect',
                                    x: a.x || (bbox ? bbox[0] : 0),
                                    y: a.y || (bbox ? bbox[1] : 0),
                                    width: a.width || (bbox ? bbox[2] : 0),
                                    height: a.height || (bbox ? bbox[3] : 0),
                                    rotation: a.rotation || 0,
                                    label: a.label || a.class_name,
                                    segmentation: a.segmentation,
                                    points: a.points || [],
                                    closed: a.closed || false,
                                    isPreannotation: false
                                };
                                return mapped;
                            } else if (a.type === 'obbox') {
                                let bbox = a.bbox;
                                if (typeof bbox === 'string') {
                                    bbox = JSON.parse(bbox || '[]');
                                } else if (!Array.isArray(bbox)) {
                                    console.warn('Invalid bbox (not array):', bbox, 'for anno', a.id || a.preannotation_id);
                                    bbox = [0, 0, 0, 0];
                                }
                                const mapped = {
                                    type: 'obbox',
                                    x: a.x || (bbox ? bbox[0] : 0),
                                    y: a.y || (bbox ? bbox[1] : 0),
                                    width: a.width || (bbox ? bbox[2] : 0),
                                    height: a.height || (bbox ? bbox[3] : 0),
                                    rotation: a.rotation || 0,
                                    label: a.label || a.class_name,
                                    segmentation: a.segmentation,
                                    points: a.points || [],
                                    closed: a.closed || false,
                                    isPreannotation: false
                                };
                                return mapped;
                            }
                            // Fallback for other types
                            const mapped = {
                                type: a.type || 'rect',
                                x: a.x || 0,
                                y: a.y || 0,
                                width: a.width || 0,
                                height: a.height || 0,
                                rotation: a.rotation || 0,
                                label: a.label || a.class_name,
                                segmentation: a.segmentation,
                                points: a.points || [],
                                closed: a.closed || false,
                                isPreannotation: false
                            };
                            return mapped;
                        }).filter(anno => anno !== null && (anno.type !== 'polygon' || anno.points.length > 0));  // Filter invalid/empty
                    } catch (e) {
                        console.error("Error mapping annotations for frame", i, ":", e);
                        return [];
                    }
                })();

                // Map preannotations
                const mappedPreannotations = (() => {
                    try {
                        return data.preannotations.map(a => {
                            const parsed = parseAnnotationLine(a);
                            if (!parsed) return null;
                            if (parsed.type === 'segmentation') {
                                let seg = parsed.segmentation;
                                if (typeof seg === 'string') {
                                    seg = JSON.parse(seg || '[]');
                                } else if (Array.isArray(seg) && seg.length === 1 && Array.isArray(seg[0])) {
                                    seg = seg[0];
                                } else if (!Array.isArray(seg)) {
                                    console.warn('Invalid segmentation (not array):', seg, 'for anno', a.id || a.preannotation_id);
                                    seg = [];
                                }
                                // Prefer existing points if available and valid
                                let points = parsed.points || [];
                                if (!Array.isArray(points) || points.length === 0 || !points[0].x) {
                                    // Fall back to computing from seg (now flat)
                                    points = [];
                                    if (Array.isArray(seg)) {
                                        for (let k = 0; k < seg.length; k += 2) {
                                            if (k + 1 < seg.length) {
                                                points.push({ x: seg[k], y: seg[k + 1] });
                                            } else {
                                                console.warn('Odd number of coordinates in segmentation for anno', a.id || a.preannotation_id);
                                                break;
                                            }
                                        }
                                    }
                                }
                                const mapped = {
                                    type: 'polygon',
                                    points,
                                    closed: true,
                                    label: parsed.label || parsed.class_name,
                                    isPreannotation: true
                                };
                                return mapped;
                            } else if (parsed.type === 'bbox' || parsed.type === 'rect') {
                                let bbox = parsed.bbox;
                                if (typeof bbox === 'string') {
                                    bbox = JSON.parse(bbox || '[]');
                                } else if (!Array.isArray(bbox)) {
                                    console.warn('Invalid bbox (not array):', bbox, 'for anno', a.id || a.preannotation_id);
                                    bbox = [0, 0, 0, 0];
                                }
                                const mapped = {
                                    type: 'rect',
                                    x: parsed.x || (bbox ? bbox[0] : 0),
                                    y: parsed.y || (bbox ? bbox[1] : 0),
                                    width: parsed.width || (bbox ? bbox[2] : 0),
                                    height: parsed.height || (bbox ? bbox[3] : 0),
                                    rotation: parsed.rotation || 0,
                                    label: parsed.label || parsed.class_name,
                                    segmentation: parsed.segmentation,
                                    points: parsed.points || [],
                                    closed: parsed.closed || false,
                                    isPreannotation: true
                                };
                                return mapped;
                            } else if (parsed.type === 'obbox') {
                                let bbox = parsed.bbox;
                                if (typeof bbox === 'string') {
                                    bbox = JSON.parse(bbox || '[]');
                                } else if (!Array.isArray(bbox)) {
                                    console.warn('Invalid bbox (not array):', bbox, 'for anno', a.id || a.preannotation_id);
                                    bbox = [0, 0, 0, 0];
                                }
                                const mapped = {
                                    type: 'obbox',
                                    x: parsed.x || (bbox ? bbox[0] : 0),
                                    y: parsed.y || (bbox ? bbox[1] : 0),
                                    width: parsed.width || (bbox ? bbox[2] : 0),
                                    height: parsed.height || (bbox ? bbox[3] : 0),
                                    rotation: parsed.rotation || 0,
                                    label: parsed.label || parsed.class_name,
                                    segmentation: parsed.segmentation,
                                    points: parsed.points || [],
                                    closed: parsed.closed || false,
                                    isPreannotation: true
                                };
                                return mapped;
                            }
                            // Fallback for other types
                            const mapped = {
                                type: parsed.type || 'rect',
                                x: parsed.x || 0,
                                y: parsed.y || 0,
                                width: parsed.width || 0,
                                height: parsed.height || 0,
                                rotation: parsed.rotation || 0,
                                label: parsed.label || parsed.class_name,
                                segmentation: parsed.segmentation,
                                points: parsed.points || [],
                                closed: parsed.closed || false,
                                isPreannotation: true
                            };
                            return mapped;
                        }).filter(anno => anno !== null && (anno.type !== 'polygon' || anno.points.length > 0));  // Filter invalid/empty
                    } catch (e) {
                        console.error("Error mapping preannotations for frame", i, ":", e);
                        return [];
                    }
                })();

                globals.annotationMap[i] = [...mappedAnnotations, ...mappedPreannotations];

                globals.annotationMap[i].forEach(anno => {
                    if (anno.label && !(anno.label in globals.classToRow)) {
                        globals.classToRow[anno.label] = globals.nextRow++;
                    }
                });
            }
        } catch (e) {
            console.error("Error loading annotations:", e);
        }

        resizeTimelineCanvas();
        drawTimeline();

        // Make sure listeners aren’t duplicated
        globals.currentVideo.onended = handleVideoEnd;
        globals.currentVideo.ontimeupdate = () => {
            updatePlayhead();
            updateTimeDisplay();
        };

        function handleSeeked() {
            if (!globals.currentVideo || globals.frames.length === 0) return;
            const t = globals.currentVideo.currentTime;
            let closestIndex = 0;
            let minDist = Math.abs(globals.frames[0].timestamp - t);
            for (let i = 1; i < globals.frames.length; i++) {
                const dist = Math.abs(globals.frames[i].timestamp - t);
                if (dist < minDist) {
                    minDist = dist;
                    closestIndex = i;
                }
            }
            if (closestIndex !== globals.currentFrameIndex) {
                globals.currentFrameIndex = closestIndex;
                globals.annotations = globals.annotationMap[closestIndex] || [];
                setSelectedAnnotation(null);
                drawImage();
            }
            updatePlayhead();
            updateTimeDisplay();
        }
        globals.currentVideo.addEventListener('seeked', handleSeeked);

        if (globals.frames.length > 0) {
            globals.currentVideo.currentTime = globals.frames[0].timestamp;
        }
        await playFrame(globals.frames[0].frame_number);


        // Setup timeline events after load (pass playFrame)
        setupTimelineEventListeners(updateFrameFromMouse, drawTimeline, playFrame);
    }

    async function reloadAnnotations() {
        if (!globals.currentItem) return;
        const videoId = globals.currentItem.dataset.videoId;
        if (!videoId) {
            console.error('Missing video ID for reload');
            return;
        }
        try {
            const annoResp = await fetch(`/annotation/get_video_annotations/${projectName}/${videoId}`);
            const allAnnos = await annoResp.json();

            for (let i = 0; i < globals.frames.length; i++) {
                const fn = globals.frames[i].frame_number;
                const data = allAnnos[fn] || { annotations: [], preannotations: [] };
                
                // Map annotations
                const mappedAnnotations = (() => {
                    try {
                        return data.annotations.map(a => {
                            if (a.type === 'segmentation') {
                                let seg = a.segmentation;
                                if (typeof seg === 'string') {
                                    seg = JSON.parse(seg || '[]');
                                } else if (Array.isArray(seg) && seg.length === 1 && Array.isArray(seg[0])) {
                                    seg = seg[0];
                                } else if (!Array.isArray(seg)) {
                                    console.warn('Invalid segmentation (not array):', seg, 'for anno', a.id || a.preannotation_id);
                                    seg = [];
                                }
                                // Prefer existing points if available and valid
                                let points = a.points || [];
                                if (!Array.isArray(points) || points.length === 0 || !points[0].x) {
                                    // Fall back to computing from seg (now flat)
                                    points = [];
                                    if (Array.isArray(seg)) {
                                        for (let k = 0; k < seg.length; k += 2) {
                                            if (k + 1 < seg.length) {
                                                points.push({ x: seg[k], y: seg[k + 1] });
                                            } else {
                                                console.warn('Odd number of coordinates in segmentation for anno', a.id || a.preannotation_id);
                                                break;
                                            }
                                        }
                                    }
                                }
                                const mapped = {
                                    type: 'polygon',
                                    points,
                                    closed: true,
                                    label: a.label || a.class_name,
                                    isPreannotation: false
                                };
                                return mapped;
                            } else if (a.type === 'bbox' || a.type === 'rect') {
                                let bbox = a.bbox;
                                if (typeof bbox === 'string') {
                                    bbox = JSON.parse(bbox || '[]');
                                } else if (!Array.isArray(bbox)) {
                                    console.warn('Invalid bbox (not array):', bbox, 'for anno', a.id || a.preannotation_id);
                                    bbox = [0, 0, 0, 0];
                                }
                                const mapped = {
                                    type: 'rect',
                                    x: a.x || (bbox ? bbox[0] : 0),
                                    y: a.y || (bbox ? bbox[1] : 0),
                                    width: a.width || (bbox ? bbox[2] : 0),
                                    height: a.height || (bbox ? bbox[3] : 0),
                                    rotation: a.rotation || 0,
                                    label: a.label || a.class_name,
                                    segmentation: a.segmentation,
                                    points: a.points || [],
                                    closed: a.closed || false,
                                    isPreannotation: false
                                };
                                return mapped;
                            } else if (a.type === 'obbox') {
                                let bbox = a.bbox;
                                if (typeof bbox === 'string') {
                                    bbox = JSON.parse(bbox || '[]');
                                } else if (!Array.isArray(bbox)) {
                                    console.warn('Invalid bbox (not array):', bbox, 'for anno', a.id || a.preannotation_id);
                                    bbox = [0, 0, 0, 0];
                                }
                                const mapped = {
                                    type: 'obbox',
                                    x: a.x || (bbox ? bbox[0] : 0),
                                    y: a.y || (bbox ? bbox[1] : 0),
                                    width: a.width || (bbox ? bbox[2] : 0),
                                    height: a.height || (bbox ? bbox[3] : 0),
                                    rotation: a.rotation || 0,
                                    label: a.label || a.class_name,
                                    segmentation: a.segmentation,
                                    points: a.points || [],
                                    closed: a.closed || false,
                                    isPreannotation: false
                                };
                                return mapped;
                            }
                            // Fallback for other types
                            const mapped = {
                                type: a.type || 'rect',
                                x: a.x || 0,
                                y: a.y || 0,
                                width: a.width || 0,
                                height: a.height || 0,
                                rotation: a.rotation || 0,
                                label: a.label || a.class_name,
                                segmentation: a.segmentation,
                                points: a.points || [],
                                closed: a.closed || false,
                                isPreannotation: false
                            };
                            return mapped;
                        }).filter(anno => anno !== null && (anno.type !== 'polygon' || anno.points.length > 0));  // Filter invalid/empty
                    } catch (e) {
                        console.error("Error mapping annotations for frame", i, ":", e);
                        return [];
                    }
                })();

                // Map preannotations
                const mappedPreannotations = (() => {
                    try {
                        return data.preannotations.map(a => {
                            const parsed = parseAnnotationLine(a);
                            if (!parsed) return null;
                            if (parsed.type === 'segmentation') {
                                let seg = parsed.segmentation;
                                if (typeof seg === 'string') {
                                    seg = JSON.parse(seg || '[]');
                                } else if (Array.isArray(seg) && seg.length === 1 && Array.isArray(seg[0])) {
                                    seg = seg[0];
                                } else if (!Array.isArray(seg)) {
                                    console.warn('Invalid segmentation (not array):', seg, 'for anno', a.id || a.preannotation_id);
                                    seg = [];
                                }
                                // Prefer existing points if available and valid
                                let points = parsed.points || [];
                                if (!Array.isArray(points) || points.length === 0 || !points[0].x) {
                                    // Fall back to computing from seg (now flat)
                                    points = [];
                                    if (Array.isArray(seg)) {
                                        for (let k = 0; k < seg.length; k += 2) {
                                            if (k + 1 < seg.length) {
                                                points.push({ x: seg[k], y: seg[k + 1] });
                                            } else {
                                                console.warn('Odd number of coordinates in segmentation for anno', a.id || a.preannotation_id);
                                                break;
                                            }
                                        }
                                    }
                                }
                                const mapped = {
                                    type: 'polygon',
                                    points,
                                    closed: true,
                                    label: parsed.label || parsed.class_name,
                                    isPreannotation: true
                                };
                                return mapped;
                            } else if (parsed.type === 'bbox' || parsed.type === 'rect') {
                                let bbox = parsed.bbox;
                                if (typeof bbox === 'string') {
                                    bbox = JSON.parse(bbox || '[]');
                                } else if (!Array.isArray(bbox)) {
                                    console.warn('Invalid bbox (not array):', bbox, 'for anno', a.id || a.preannotation_id);
                                    bbox = [0, 0, 0, 0];
                                }
                                const mapped = {
                                    type: 'rect',
                                    x: parsed.x || (bbox ? bbox[0] : 0),
                                    y: parsed.y || (bbox ? bbox[1] : 0),
                                    width: parsed.width || (bbox ? bbox[2] : 0),
                                    height: parsed.height || (bbox ? bbox[3] : 0),
                                    rotation: parsed.rotation || 0,
                                    label: parsed.label || parsed.class_name,
                                    segmentation: parsed.segmentation,
                                    points: parsed.points || [],
                                    closed: parsed.closed || false,
                                    isPreannotation: true
                                };
                                return mapped;
                            } else if (parsed.type === 'obbox') {
                                let bbox = parsed.bbox;
                                if (typeof bbox === 'string') {
                                    bbox = JSON.parse(bbox || '[]');
                                } else if (!Array.isArray(bbox)) {
                                    console.warn('Invalid bbox (not array):', bbox, 'for anno', a.id || a.preannotation_id);
                                    bbox = [0, 0, 0, 0];
                                }
                                const mapped = {
                                    type: 'obbox',
                                    x: parsed.x || (bbox ? bbox[0] : 0),
                                    y: parsed.y || (bbox ? bbox[1] : 0),
                                    width: parsed.width || (bbox ? bbox[2] : 0),
                                    height: parsed.height || (bbox ? bbox[3] : 0),
                                    rotation: parsed.rotation || 0,
                                    label: parsed.label || parsed.class_name,
                                    segmentation: parsed.segmentation,
                                    points: parsed.points || [],
                                    closed: parsed.closed || false,
                                    isPreannotation: true
                                };
                                return mapped;
                            }
                            // Fallback for other types
                            const mapped = {
                                type: parsed.type || 'rect',
                                x: parsed.x || 0,
                                y: parsed.y || 0,
                                width: parsed.width || 0,
                                height: parsed.height || 0,
                                rotation: parsed.rotation || 0,
                                label: parsed.label || parsed.class_name,
                                segmentation: parsed.segmentation,
                                points: parsed.points || [],
                                closed: parsed.closed || false,
                                isPreannotation: true
                            };
                            return mapped;
                        }).filter(anno => anno !== null && (anno.type !== 'polygon' || anno.points.length > 0));  // Filter invalid/empty
                    } catch (e) {
                        console.error("Error mapping preannotations for frame", i, ":", e);
                        return [];
                    }
                })();

                globals.annotationMap[i] = [...mappedAnnotations, ...mappedPreannotations];
            }
            globals.annotations = globals.annotationMap[globals.currentFrameIndex] || [];
            drawImage();
            drawTimeline();
        } catch (e) {
            console.error("Error reloading annotations/preannotations:", e);
        }
    }

    async function reloadFrames() {
        if (!globals.currentItem) return;
        const videoId = globals.currentItem.dataset.videoId;
        if (!videoId) return;
        const response = await fetch(`/annotation/get_frames/${projectName}/${videoId}`);
        const frameData = await response.json();
        globals.fps = frameData.fps || globals.fps;  // Update FPS
        let rawFrames = frameData.frames || [];
        if (!Array.isArray(rawFrames)) rawFrames = [];
        const normalized = [];
        for (let f of rawFrames) {
            const ts = Number(f.timestamp);
            if (Number.isFinite(ts) && ts >= 0 && ts <= globals.currentVideo.duration) {
                normalized.push({ ...f, timestamp: ts });
            } else {
                console.warn('Skipping invalid frame timestamp:', f);
            }
        }
        globals.frames = normalized.sort((a, b) => a.frame_number - b.frame_number);
        globals.annotationMap = Array(globals.frames.length).fill().map(() => []);
        globals.undoStack = Array(globals.frames.length).fill().map(() => []);
        resizeTimelineCanvas();
        drawTimeline();
    }

    function handleVideoEnd() {
        globals.isPlaying = false;
        if (playPauseBtn) playPauseBtn.innerHTML = '&#9654;';
        if (globals.loop) {
            globals.currentVideo.currentTime = 0;
            globals.currentVideo.play();
            globals.isPlaying = true;
            if (playPauseBtn) playPauseBtn.innerHTML = '&#9646;';
            requestAnimationFrame(updateCanvas);
        }
    }

    async function playFrame(frameNumOrIndex) {
        if (!globals.currentVideo) return;
        let num = Number(frameNumOrIndex);
        if (!Number.isFinite(num)) num = 0;
        // Clamp to valid frame_number range
        const maxFrame = globals.frames.length > 0 ? globals.frames[globals.frames.length - 1].frame_number : 0;
        num = Math.max(0, Math.min(maxFrame, num));
        const index = globals.frames.findIndex(f => f.frame_number === num);
        if (index === -1) return;
        const ts = globals.frames[index].timestamp;
        globals.currentFrameIndex = Math.max(0, Math.min(globals.frames.length - 1, index)); // Robust clamp
        globals.annotations = globals.annotationMap[globals.currentFrameIndex] || [];
        setSelectedAnnotation(null);
        const needsSeek = Math.abs(globals.currentVideo.currentTime - ts) > 1e-3;
        if (needsSeek) {
            globals.currentVideo.currentTime = ts;
            // Don't draw yet—let 'seeked' handler do it for correct video frame
        } else {
            // No seek needed: draw immediately
            drawImage();
        }
        updatePlayhead();
        updateTimeDisplay();
    }

    function updateCanvas() {
        if (globals.isPlaying) {
            const t = globals.currentVideo.currentTime;
            const frameNum = Math.round(t * globals.fps);
            const index = globals.frames.findIndex(f => f.frame_number === frameNum);
            if (index !== -1 && globals.currentFrameIndex !== index) {
                globals.currentFrameIndex = index;
                globals.annotations = globals.annotationMap[index] || [];
                setSelectedAnnotation(null);
            }
            drawImage();
            requestAnimationFrame(updateCanvas);
        }
    }

    if (globals.currentVideo) {
        globals.currentVideo.ontimeupdate = () => {
            updatePlayhead();
            updateTimeDisplay();
        };
    }

    // Navigation button listeners
    if (firstFrameBtn) firstFrameBtn.addEventListener('click', () => { if (!globals.currentVideo) return; goToFirstFrame(playFrame, drawTimeline); });
    if (lastFrameBtn) lastFrameBtn.addEventListener('click', () => { if (!globals.currentVideo) return; goToLastFrame(playFrame, drawTimeline); });
    if (prevFrameBtn) prevFrameBtn.addEventListener('click', () => { if (!globals.currentVideo) return; goToPrevFrame(playFrame, drawTimeline); });
    if (nextFrameBtn) nextFrameBtn.addEventListener('click', () => { if (!globals.currentVideo) return; goToNextFrame(playFrame, drawTimeline); });

    // Play/pause and Loop toggle
    if (playPauseBtn) {
        playPauseBtn.addEventListener('click', () => { 
            if (!globals.currentVideo) return;
            if (globals.currentVideo.paused) { 
                globals.currentVideo.play(); 
                globals.isPlaying = true; 
                playPauseBtn.innerHTML = '&#9646;'; 
                requestAnimationFrame(updateCanvas); 
            } else { 
                globals.currentVideo.pause(); 
                globals.isPlaying = false; 
                playPauseBtn.innerHTML = '&#9654;'; 
                drawImage();
            }
        });
    }

    if (loopBtn) {
        loopBtn.addEventListener('click', () => { 
            globals.loop = !globals.loop; 
            if (globals.loop) {
                loopBtn.style.background = '#1e88e5';
                loopBtn.style.color = '#fff';
                loopBtn.style.borderColor = '#1565c0';
            } else {
                loopBtn.style.background = '';
                loopBtn.style.color = '';
                loopBtn.style.borderColor = '';
            }
        });
    }

    document.addEventListener('keydown', (e) => {
        const t = e.target;
        if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)) {
            return; // don't intercept when user types in form fields
        }

        // Prevent spacebar scrolling only when not focused on form element
        if (e.key === ' ') {
            e.preventDefault();
            resetView();
            return;
        }

        // Ctrl+C: copy selected annotation
        if (e.ctrlKey && e.key && e.key.toLowerCase() === 'c' && globals?.selectedAnnotation) {
            e.preventDefault();
            globals.copyBuffer = (typeof structuredClone === 'function') ? structuredClone(globals.selectedAnnotation) : JSON.parse(JSON.stringify(globals.selectedAnnotation));
            console.log('Annotation copied to buffer');
        }

        // Ctrl+V: paste annotation
        if (e.ctrlKey && e.key && e.key.toLowerCase() === 'v' && globals?.copyBuffer) {
            e.preventDefault();
            const paste = (typeof structuredClone === 'function') ? structuredClone(globals.copyBuffer) : JSON.parse(JSON.stringify(globals.copyBuffer));
            globals.annotations.push(paste);
            pushToUndoStack();
            drawImage();
            updateMapAndTimeline();
            console.log('Annotation pasted');
        }

        // Delete: delete selected annotation
        if (e.key === 'Delete' && globals?.selectedAnnotation) {
            e.preventDefault();
            const index = globals.annotations.indexOf(globals.selectedAnnotation);
            if (index > -1) {
                globals.annotations.splice(index, 1);
                globals.selectedAnnotation = null;
                pushToUndoStack();
                drawImage();
                updateMapAndTimeline();
            }
        }

        // Ctrl+Z: undo
        if (e.ctrlKey && e.key && e.key.toLowerCase() === 'z') {
            e.preventDefault();
            const frameStack = globals.undoStack[globals.currentFrameIndex];
            if (Array.isArray(frameStack) && frameStack.length > 0) {
                // pop previous state and set annotations to it
                globals.annotations = frameStack.pop();
                drawImage();
                updateMapAndTimeline();
            }
        }

        // Ctrl+S: save shortcut
        if (e.ctrlKey && e.key && e.key.toLowerCase() === 's') {
            e.preventDefault();
            if (saveBtn) saveBtn.click();
        }

        // Left/Right arrow navigation
        if (e.key === 'ArrowLeft') {
            e.preventDefault();
            if (prevVideoBtn) prevVideoBtn.click();
        } else if (e.key === 'ArrowRight') {
            e.preventDefault();
            if (nextVideoBtn) nextVideoBtn.click();
        }

        // G: toggle grid
        if (e.key && e.key.toLowerCase() === 'g') {
            e.preventDefault();
            setGridEnabled(!globals.gridEnabled);
        }
    });

    if (videoItems && videoItems.length > 0) {
        const firstItem = videoItems[0];
        videoItems.forEach(i => i.classList.remove('selected'));
        firstItem.classList.add('selected');
        globals.currentItem = firstItem;
        const firstVideoUrl = firstItem.dataset.url; 
        const firstVideoId = firstItem.dataset.videoId;
        if (firstVideoUrl && firstVideoId) {
            await loadVideo(firstVideoUrl, firstVideoId);
        } else {
            console.error('First video missing URL or ID:', { url: firstVideoUrl, id: firstVideoId });
        }
    }
});