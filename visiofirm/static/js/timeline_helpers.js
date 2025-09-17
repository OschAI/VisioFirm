import { globals } from './video_globals.js';
import { formatTime } from './video_utils.js';
export function clampTimelineOffset() {
    if (globals.frames.length === 0) return;
    const baseThumbWidth = globals.tlCanvas.width / (globals.frames.length - 1 || 1);
    const contentWidth = baseThumbWidth * (globals.frames.length - 1) * globals.timelineZoom;
    const minOffset = Math.min(0, globals.tlCanvas.width - contentWidth);
    const maxOffset = 0;
    globals.timelineOffset = Math.min(Math.max(globals.timelineOffset, minOffset), maxOffset);
}
export function resizeTimelineCanvas() {
    const tlFrames = document.querySelector('.timeline-frames');
    if (!tlFrames || !globals.tlCanvas) return;
    globals.tlCanvas.width = tlFrames.clientWidth;
    globals.tlCanvas.height = tlFrames.clientHeight;
    globals.timelineVerticalOffset = 0;
    clampTimelineOffset();
    drawTimeline();
}
export function drawTimeline() {
    if (!globals.tlCtx) return;
    globals.tlCtx.clearRect(0, 0, globals.tlCanvas.width, globals.tlCanvas.height);
    if (globals.frames.length === 0 || !globals.currentVideo) return;
    const baseThumbWidth = globals.tlCanvas.width / (globals.frames.length - 1 || 1);
    const duration = globals.currentVideo.duration;
    const fps = globals.fps || 30.0; // Fallback to global fps
    // Calculate pixels per second based on frame numbers
    const totalSeconds = globals.frames.length / fps;
    const pixelsPerSecond = (baseThumbWidth * globals.timelineZoom * (globals.frames.length - 1)) / totalSeconds;
    const framePixSpacing = pixelsPerSecond / fps;
    // Pick spacing for tick labels depending on zoom level & duration
    let labelStepSeconds;
    if (pixelsPerSecond < 3) {
        labelStepSeconds = 60; // Very zoomed out → label every 60s
    } else if (pixelsPerSecond < 10) {
        labelStepSeconds = 30;
    } else if (pixelsPerSecond < 30) {
        labelStepSeconds = 15;
    } else if (pixelsPerSecond < 60) {
        labelStepSeconds = 5;
    } else {
        labelStepSeconds = 1; // Only show per second
    }
    // Hierarchical tick levels: interval in seconds, color, width
    const tickLevels = [
        { interval: 60, color: '#333', width: 2 },
        { interval: 30, color: '#666', width: 1.5 },
        { interval: 15, color: '#999', width: 1 },
        { interval: 5, color: '#bbb', width: 1 },
        { interval: 1, color: '#ddd', width: 1 }
    ];
    const minPixSpacing = 50;

    const rowHeight = 12;
    const baseClassY = 10;
    const totalClassHeight = globals.nextRow * rowHeight;
    const perFrameTickLength = globals.tlCanvas.height * 0.8;
    const availableClassHeight = perFrameTickLength - baseClassY;
    let verticalOffset = globals.timelineVerticalOffset || 0;
    if (totalClassHeight > availableClassHeight) {
        const minVOffset = availableClassHeight - totalClassHeight;
        verticalOffset = Math.max(minVOffset, Math.min(0, verticalOffset));
    } else {
        verticalOffset = 0;
    }

    globals.tlCtx.save();
    globals.tlCtx.translate(globals.timelineOffset, 0);
    // Draw hierarchical interval ticks
    for (const level of tickLevels) {
        const pixelSpacing = level.interval * pixelsPerSecond;
        if (pixelSpacing < minPixSpacing) continue;
        let tickLength = globals.tlCanvas.height;
        if (level.interval < 30) {
            tickLength = globals.tlCanvas.height * 0.7;
        }
        if (level.interval < 5) {
            tickLength = globals.tlCanvas.height * 0.4;
        }
        globals.tlCtx.strokeStyle = level.color;
        globals.tlCtx.lineWidth = level.width;
        for (let t = 0; t <= totalSeconds; t += level.interval) {
            const frameIdx = Math.min(Math.round(t * fps), globals.frames.length - 1);
            const x = frameIdx * baseThumbWidth * globals.timelineZoom;
            globals.tlCtx.beginPath();
            globals.tlCtx.moveTo(x, 0);
            globals.tlCtx.lineTo(x, tickLength);
            globals.tlCtx.stroke();
        }
    }
    if (framePixSpacing >= 5) {
        globals.tlCtx.strokeStyle = '#757575ff';
        globals.tlCtx.lineWidth = 0.5;
        globals.frames.forEach((f, i) => {
            const x = i * baseThumbWidth * globals.timelineZoom;
            globals.tlCtx.beginPath();
            globals.tlCtx.moveTo(x, 0);
            globals.tlCtx.lineTo(x, perFrameTickLength);
            globals.tlCtx.stroke();
        });
    }
    // Draw subsampled indicators (always, for key frames)
    globals.tlCtx.fillStyle = "#ffffffff";
    globals.frames.forEach((f, i) => {
        if (f.subsampled) {
            const x = i * baseThumbWidth * globals.timelineZoom;
            globals.tlCtx.beginPath();
            globals.tlCtx.arc(x, globals.tlCanvas.height - 8, 3, 0, 2 * Math.PI);
            globals.tlCtx.fill();
        }
    });

    globals.tlCtx.translate(0, verticalOffset);

    if (framePixSpacing < 2) {
        for (const [cls, row] of Object.entries(globals.classToRow)) {
            const color = globals.classColors[cls] || '#cccccc';
            globals.tlCtx.fillStyle = color + '90'; 
            let currentStart = -1;
            for (let i = 0; i < globals.frames.length; i++) {
                const frameAnnos = globals.annotationMap[i] || [];
                const hasAnno = frameAnnos.some(anno => anno.label === cls);
                if (hasAnno) {
                    if (currentStart === -1) {
                        currentStart = i;
                    }
                } else {
                    if (currentStart !== -1) {
                        const xStart = currentStart * baseThumbWidth * globals.timelineZoom;
                        const width = (i - currentStart) * baseThumbWidth * globals.timelineZoom;
                        if (width > 1) {
                            const yTop = baseClassY + row * rowHeight - 6;
                            const height = rowHeight;
                            globals.tlCtx.fillRect(xStart, yTop, width, height);
                        }
                        currentStart = -1;
                    }
                }
            }
            if (currentStart !== -1) {
                const i = globals.frames.length;
                const xStart = currentStart * baseThumbWidth * globals.timelineZoom;
                const width = (i - currentStart) * baseThumbWidth * globals.timelineZoom;
                if (width > 1) {
                    const yTop = baseClassY + row * rowHeight - 6;
                    const height = rowHeight;
                    globals.tlCtx.fillRect(xStart, yTop, width, height);
                }
            }
        }
    }

    if (framePixSpacing >= 2) {
        globals.frames.forEach((f, i) => {
            const x = i * baseThumbWidth * globals.timelineZoom;
            const frameAnnos = globals.annotationMap[i] || [];
            let seenClasses = new Set();
            frameAnnos.forEach(anno => {
                const cls = anno.label;
                if (cls && globals.classToRow.hasOwnProperty(cls) && !seenClasses.has(cls)) {
                    seenClasses.add(cls);
                    const color = globals.classColors[cls] || '#cccccc';
                    globals.tlCtx.fillStyle = color;
                    const y = baseClassY + globals.classToRow[cls] * rowHeight;
                    const s = 4;
                    globals.tlCtx.beginPath();
                    globals.tlCtx.moveTo(x, y - s);
                    globals.tlCtx.lineTo(x - s, y);
                    globals.tlCtx.lineTo(x, y + s);
                    globals.tlCtx.lineTo(x + s, y);
                    globals.tlCtx.closePath();
                    globals.tlCtx.fill();
                }
            });
        });
    }

    globals.tlCtx.translate(0, -verticalOffset);

    // Draw time labels
    globals.tlCtx.fillStyle = "#000";
    globals.tlCtx.font = "12px Arial";
    globals.tlCtx.textBaseline = "bottom";
    for (let t = 0; t <= totalSeconds; t += labelStepSeconds) {
        const frameIdx = Math.min(Math.round(t * fps), globals.frames.length - 1);
        const x = frameIdx * baseThumbWidth * globals.timelineZoom;
        globals.tlCtx.fillText(formatTime(t), x + 2, globals.tlCanvas.height - 5);
    }
    globals.tlCtx.restore();
    // Horizontal class rows
    globals.tlCtx.save();
    globals.tlCtx.translate(0, verticalOffset);
    globals.tlCtx.strokeStyle = "#6b6b6bff";
    for (let i = 1; i < globals.nextRow; i++) {
        const y = baseClassY + (i - 0.5) * rowHeight;
        globals.tlCtx.beginPath();
        globals.tlCtx.moveTo(0, y);
        globals.tlCtx.lineTo(globals.tlCanvas.width, y);
        globals.tlCtx.stroke();
    }
    globals.tlCtx.restore();
    // Highlight selected region
    if (globals.isSelecting) {
        const minX = Math.min(globals.selectStartX, globals.selectEndX);
        const width = Math.abs(globals.selectStartX - globals.selectEndX);
        globals.tlCtx.fillStyle = 'rgba(0, 128, 255, 0.2)';
        globals.tlCtx.fillRect(minX, 0, width, globals.tlCanvas.height);
    } else if (globals.selectedRange) {
        const baseThumbWidth = globals.tlCanvas.width / (globals.frames.length - 1 || 1);
        const screenStart = globals.selectedRange.start * baseThumbWidth * globals.timelineZoom + globals.timelineOffset;
        const screenEnd = globals.selectedRange.end * baseThumbWidth * globals.timelineZoom + globals.timelineOffset;
        globals.tlCtx.fillStyle = 'rgba(0, 128, 255, 0.2)';
        globals.tlCtx.fillRect(screenStart, 0, screenEnd - screenStart, globals.tlCanvas.height);
    }
    updatePlayhead();
}
export async function updateFrameFromMouse(mouseX, playFrame) {
    const relativeX = (mouseX - globals.timelineOffset) / globals.timelineZoom;
    const baseThumbWidth = globals.tlCanvas.width / (globals.frames.length - 1 || 1);
    let closestIndex = 0;
    let minDist = Math.abs(relativeX - 0);
    for (let i = 1; i < globals.frames.length; i++) {
        const x = i * baseThumbWidth;
        const dist = Math.abs(x - relativeX);
        if (dist < minDist) { minDist = dist; closestIndex = i; }
    }
    // Use frame_number for playFrame
    const frameNum = globals.frames[closestIndex] && (globals.frames[closestIndex].frame_number || closestIndex);
    if (Number.isFinite(frameNum)) await playFrame(frameNum);
}
export function updatePlayhead() {
    if (!globals.currentVideo || !globals.playhead) return;
    const fps = globals.fps || 30.0;
    if (globals.frames.length < 2) {
        const contentWidth = globals.tlCanvas.width * globals.timelineZoom;
        const relative = (globals.currentVideo.currentTime / Math.max(0.0001, globals.currentVideo.duration)) * contentWidth;
        globals.playhead.style.left = (relative + globals.timelineOffset) + 'px';
        return;
    }
    const baseThumbWidth = globals.tlCanvas.width / (globals.frames.length - 1 || 1);
    const t = globals.currentVideo.currentTime;
    const frameNum = Math.round(t * fps);
    let i = Math.min(frameNum, globals.frames.length - 1);
    const pos = (i * baseThumbWidth * globals.timelineZoom) + globals.timelineOffset;
    globals.playhead.style.left = pos + 'px';
}
export function updateTimeDisplay() {
    if (!globals.currentVideo || !globals.currentTimeInput) return;
    const current = formatTime(globals.currentVideo.currentTime);
    const total = formatTime(globals.currentVideo.duration);
    globals.currentTimeInput.value = `${current} / ${total}`;
}
export async function goToFirstFrame(playFrame, drawTimeline) {
    const frameNum = globals.frames.length > 0 ? globals.frames[0].frame_number : 0;
    await playFrame(frameNum);
    drawTimeline();
}
export async function goToLastFrame(playFrame, drawTimeline) {
    const frameNum = globals.frames.length > 0 ? (globals.frames[globals.frames.length - 1].frame_number || globals.frames.length - 1) : globals.currentVideo.duration * (globals.fps || 30);
    await playFrame(frameNum);
    drawTimeline();
}
export async function goToPrevFrame(playFrame, drawTimeline) {
    const t = globals.currentVideo.currentTime;
    const fps = globals.fps || 30.0;
    const currentFrame = Math.round(t * fps);
    let prevFrame = 0;
    for (let i = globals.frames.length - 1; i >= 0; i--) {
        const fNum = globals.frames[i].frame_number || i;
        if (fNum < currentFrame) { prevFrame = fNum; break; }
    }
    await playFrame(prevFrame);
    drawTimeline();
}
export async function goToNextFrame(playFrame, drawTimeline) {
    const t = globals.currentVideo.currentTime;
    const fps = globals.fps || 30.0;
    const currentFrame = Math.round(t * fps);
    for (let i = 0; i < globals.frames.length; i++) {
        const fNum = globals.frames[i].frame_number || i;
        if (fNum > currentFrame) { await playFrame(fNum); drawTimeline(); return; }
    }
    const lastFrame = (globals.frames.length - 1) || Math.round(globals.currentVideo.duration * fps);
    await playFrame(lastFrame);
    drawTimeline();
}
export function setupTimelineEventListeners(updateFrameFromMouseFn, drawTimelineFn, playFrameFn) {
    if (!globals.tlCanvas) return;
    let lastDrawTime = 0;
    const drawThrottleMs = 16; // ~60 FPS
    let lastSeekTime = 0;
    const seekThrottleMs = 50;

    globals.tlCanvas.addEventListener('contextmenu', e => e.preventDefault());

    globals.tlCanvas.addEventListener('mousedown', async e => {
        if (!globals.frames.length || !globals.currentVideo) return;
        const rect = globals.tlCanvas.getBoundingClientRect();
        const mouseX = e.clientX - rect.left;
        globals.mousedownX = mouseX; // Track for drag detection in click

        if (e.button === 2) {
            e.preventDefault();
            const now = Date.now();
            const dx = Math.abs(mouseX - globals.lastRightClickX);
            if (now - globals.lastRightClickTime < 300 && dx < 5) {
                // Double right click: deselect
                globals.selectedRange = null;
                drawTimelineFn();
            } else {
                // Single right click: start selecting
                globals.isSelecting = true;
                globals.selectStartX = mouseX;
            }
            globals.lastRightClickTime = now;
            globals.lastRightClickX = mouseX;
            return;
        }

        if (e.ctrlKey) {
            globals.isTimelineDragging = true;
            globals.lastTimelineX = e.clientX;
        } else if (e.button === 0) {
            // Left click: prepare for drag seek, but don't seek yet (let click/mousemove handle)
            globals.seekOnDrag = true;
        }
    });

    window.addEventListener('mouseup', () => {
        if (globals.isSelecting) {
            globals.isSelecting = false;
            const minX = Math.min(globals.selectStartX, globals.selectEndX);
            const maxX = Math.max(globals.selectStartX, globals.selectEndX);
            const baseThumbWidth = globals.tlCanvas.width / (globals.frames.length - 1 || 1);
            const rawStart = (minX - globals.timelineOffset) / (globals.timelineZoom * baseThumbWidth);
            const rawEnd = (maxX - globals.timelineOffset) / (globals.timelineZoom * baseThumbWidth);
            let frameStart = Math.floor(rawStart);
            let frameEnd = Math.floor(rawEnd);
            frameStart = Math.max(0, Math.min(globals.frames.length - 1, frameStart));
            frameEnd = Math.max(0, Math.min(globals.frames.length - 1, frameEnd));
            if (frameStart <= frameEnd) {
                globals.selectedRange = { start: frameStart, end: frameEnd };
            } else {
                globals.selectedRange = null;
            }
            drawTimelineFn();
        }
        globals.isTimelineDragging = false;
        globals.seekOnDrag = false;
    });

    window.addEventListener('mousemove', e => {
        if (!globals.frames.length || !globals.currentVideo) return;
        const rect = globals.tlCanvas.getBoundingClientRect();
        const mouseX = e.clientX - rect.left;

        if (globals.isTimelineDragging) {
            const dx = e.clientX - globals.lastTimelineX;
            globals.timelineOffset += dx;
            globals.lastTimelineX = e.clientX;
            clampTimelineOffset();
        }

        if (globals.seekOnDrag) {
            const now = Date.now();
            if (now - lastSeekTime > seekThrottleMs) {
                updateFrameFromMouseFn(mouseX, playFrameFn); // Fire-and-forget (no await)
                lastSeekTime = now;
            }
        }

        if (globals.isSelecting) {
            globals.selectEndX = mouseX;
        }

        // Throttle drawTimeline during interactions
        const now = Date.now();
        if (globals.isTimelineDragging || globals.seekOnDrag || globals.isSelecting) {
            if (now - lastDrawTime > drawThrottleMs) {
                drawTimelineFn();
                lastDrawTime = now;
            }
        }
    });

    // Click handler: seek only if not dragged
    globals.tlCanvas.addEventListener('click', e => {
        if (e.ctrlKey || globals.frames.length === 0) return;
        if (typeof globals.mousedownX === 'undefined') return;
        const rect = globals.tlCanvas.getBoundingClientRect();
        const clickX = e.clientX - rect.left;
        const dx = Math.abs(clickX - globals.mousedownX);
        if (dx > 5) return; // Was a drag, ignore click

        const x = clickX;
        const relativeX = (x - globals.timelineOffset) / globals.timelineZoom;
        const baseThumbWidth = globals.tlCanvas.width / (globals.frames.length - 1 || 1);
        let closestIndex = 0;
        let minDist = Math.abs(relativeX - 0);
        for (let i = 1; i < globals.frames.length; i++) {
            const pos = i * baseThumbWidth;
            const dist = Math.abs(pos - relativeX);
            if (dist < minDist) {
                minDist = dist;
                closestIndex = i;
            }
        }
        const frameNum = globals.frames[closestIndex].frame_number || closestIndex;
        playFrameFn(frameNum); // Fire-and-forget
    });

    // Wheel (unchanged)
    globals.tlCanvas.addEventListener('wheel', e => {
        e.preventDefault();
        const rowHeight = 12;
        const baseClassY = 10;
        const totalClassHeight = globals.nextRow * rowHeight;
        const perFrameTickLength = globals.tlCanvas.height * 0.8;
        const availableClassHeight = perFrameTickLength - baseClassY;
        const sensitivity = 3;
        if (e.ctrlKey) {
            if (globals.frames.length === 0) return;
            const baseThumbWidth = globals.tlCanvas.width / (globals.frames.length - 1 || 1);
            const maxZoom = 50 / baseThumbWidth;
            const zoomFactor = e.deltaY < 0 ? 1.1 : (1 / 1.1);
            const oldZoom = globals.timelineZoom;
            let newZoom = oldZoom * zoomFactor;
            newZoom = Math.max(1, Math.min(maxZoom, newZoom));
            const rect = globals.tlCanvas.getBoundingClientRect();
            const mouseX = e.clientX - rect.left;
            globals.timelineOffset -= (mouseX - globals.timelineOffset) * (newZoom / oldZoom - 1);
            globals.timelineZoom = newZoom;
            clampTimelineOffset();
            drawTimelineFn();
        } else {
            globals.timelineVerticalOffset -= e.deltaY * sensitivity;
            let minOffset = availableClassHeight - totalClassHeight;
            const maxOffset = 0;
            if (totalClassHeight <= availableClassHeight) {
                globals.timelineVerticalOffset = 0;
            } else {
                globals.timelineVerticalOffset = Math.min(maxOffset, Math.max(minOffset, globals.timelineVerticalOffset));
            }
            drawTimelineFn();
        }
    });

    // Double click (unchanged)
    globals.tlCanvas.addEventListener('dblclick', () => { 
        globals.timelineZoom = 1; 
        globals.timelineOffset = 0; 
        globals.timelineVerticalOffset = 0; 
        drawTimelineFn(); 
    });
}