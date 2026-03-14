import { drawImage } from './annotationDrawing.js';
import {
    getCurrentStyleConfig,
    getDefaultStyleConfig,
    getResolvedClassStyle,
    normalizeStyleConfig,
    setCurrentStyleConfig,
} from './annotationStyles.js';

function clone(value) {
    return typeof structuredClone === 'function'
        ? structuredClone(value)
        : JSON.parse(JSON.stringify(value));
}

function hexToRgba(hex, opacity) {
    const safeHex = `${hex}`.slice(0, 7);
    const r = parseInt(safeHex.slice(1, 3), 16);
    const g = parseInt(safeHex.slice(3, 5), 16);
    const b = parseInt(safeHex.slice(5, 7), 16);
    return `rgba(${r}, ${g}, ${b}, ${opacity})`;
}

export function initAnnotationStyleSettings(config) {
    const openBtn = document.getElementById('annotation-style-settings-btn');
    const modal = document.getElementById('annotation-style-modal');
    if (!openBtn || !modal) return;

    const classes = Array.isArray(config.classes) ? config.classes : [];
    let draftConfig = normalizeStyleConfig(config.annotationStyleConfig, classes);
    setCurrentStyleConfig(draftConfig, classes);

    const closeBtn = document.getElementById('annotation-style-close-btn');
    const saveBtn = document.getElementById('annotation-style-save-btn');
    const resetBtn = document.getElementById('annotation-style-reset-btn');
    const errorBox = document.getElementById('annotation-style-error');
    const jsonEditor = document.getElementById('annotation-style-json-editor');
    const classRows = document.getElementById('annotation-style-class-rows');
    const defaultRenderMode = document.getElementById('style-default-render-mode');
    const defaultStrokeWidth = document.getElementById('style-default-stroke-width');
    const defaultFillOpacity = document.getElementById('style-default-fill-opacity');
    const selectedStrokeWidth = document.getElementById('style-selected-stroke-width');
    const selectedStrokeColor = document.getElementById('style-selected-stroke-color');
    const preannotationFillOpacity = document.getElementById('style-preannotation-fill-opacity');
    const tabButtons = Array.from(document.querySelectorAll('.style-tab-btn'));
    const tabPanels = Array.from(document.querySelectorAll('.style-tab-panel'));

    function setError(message = '') {
        errorBox.textContent = message;
        errorBox.style.display = message ? 'block' : 'none';
    }

    function updateJsonEditor() {
        jsonEditor.value = JSON.stringify(draftConfig, null, 2);
    }

    function updateColorFieldPreview(input) {
        const field = input.closest('.style-color-field');
        if (!field) return;
        field.style.setProperty('--style-color-preview', input.value);
    }

    function updatePreview(row, cls) {
        const style = getResolvedClassStyle(cls);
        const preview = row.querySelector('.style-preview-outline');
        preview.style.border = `${style.strokeWidth}px solid ${style.strokeColor}`;
        preview.style.background = style.renderMode === 'outline'
            ? 'transparent'
            : hexToRgba(style.fillColor, style.fillOpacity);
        if (style.renderMode === 'fill') {
            preview.style.borderColor = 'transparent';
        }
    }

    function refreshResolvedStyles() {
        setCurrentStyleConfig(draftConfig, classes);
        classRows.querySelectorAll('tr').forEach(row => updatePreview(row, row.dataset.className));
    }

    function syncGlobalInputs() {
        defaultRenderMode.value = draftConfig.defaults.render_mode;
        defaultStrokeWidth.value = draftConfig.defaults.stroke_width;
        defaultFillOpacity.value = draftConfig.defaults.fill_opacity;
        selectedStrokeWidth.value = draftConfig.selected.stroke_width;
        selectedStrokeColor.value = draftConfig.selected.stroke_color;
        preannotationFillOpacity.value = draftConfig.preannotation.fill_opacity;
    }

    function attachRowHandlers(row, cls) {
        row.querySelector('[data-field="stroke_color"]').addEventListener('input', e => {
            draftConfig.classes[cls] = draftConfig.classes[cls] || {};
            draftConfig.classes[cls].stroke_color = e.target.value;
            updateColorFieldPreview(e.target);
            refreshResolvedStyles();
            updateJsonEditor();
        });
        row.querySelector('[data-field="fill_color"]').addEventListener('input', e => {
            draftConfig.classes[cls] = draftConfig.classes[cls] || {};
            draftConfig.classes[cls].fill_color = e.target.value;
            updateColorFieldPreview(e.target);
            refreshResolvedStyles();
            updateJsonEditor();
        });
        row.querySelector('[data-field="stroke_width"]').addEventListener('input', e => {
            draftConfig.classes[cls] = draftConfig.classes[cls] || {};
            draftConfig.classes[cls].stroke_width = Number(e.target.value);
            refreshResolvedStyles();
            updateJsonEditor();
        });
        row.querySelector('[data-field="fill_opacity"]').addEventListener('input', e => {
            draftConfig.classes[cls] = draftConfig.classes[cls] || {};
            draftConfig.classes[cls].fill_opacity = Number(e.target.value);
            refreshResolvedStyles();
            updateJsonEditor();
        });
        row.querySelector('[data-field="render_mode"]').addEventListener('change', e => {
            draftConfig.classes[cls] = draftConfig.classes[cls] || {};
            draftConfig.classes[cls].render_mode = e.target.value;
            refreshResolvedStyles();
            updateJsonEditor();
        });
    }

    function renderClassRows() {
        classRows.innerHTML = '';
        classes.forEach(cls => {
            const style = getResolvedClassStyle(cls);
            const row = document.createElement('tr');
            row.dataset.className = cls;
            row.innerHTML = `
                <td>${cls}</td>
                <td>
                    <label class="style-color-field style-color-field-stroke" style="--style-color-preview: ${style.strokeColor};">
                        <span class="style-color-preview" aria-hidden="true"></span>
                        <input data-field="stroke_color" type="color" value="${style.strokeColor}">
                    </label>
                </td>
                <td>
                    <label class="style-color-field style-color-field-fill" style="--style-color-preview: ${style.fillColor};">
                        <span class="style-color-preview" aria-hidden="true"></span>
                        <input data-field="fill_color" type="color" value="${style.fillColor}">
                    </label>
                </td>
                <td><input data-field="stroke_width" type="number" min="1" max="24" step="1" value="${style.strokeWidth}"></td>
                <td><input data-field="fill_opacity" type="number" min="0" max="1" step="0.01" value="${style.fillOpacity}"></td>
                <td>
                    <select data-field="render_mode">
                        <option value="outline"${style.renderMode === 'outline' ? ' selected' : ''}>Outline</option>
                        <option value="fill"${style.renderMode === 'fill' ? ' selected' : ''}>Fill</option>
                        <option value="outline_fill"${style.renderMode === 'outline_fill' ? ' selected' : ''}>Both</option>
                    </select>
                </td>
                <td>
                    <div class="style-preview-box">
                        <div class="style-preview-outline"></div>
                    </div>
                </td>
            `;
            classRows.appendChild(row);
            attachRowHandlers(row, cls);
            updatePreview(row, cls);
        });
    }

    function renderVisualEditor() {
        refreshResolvedStyles();
        syncGlobalInputs();
        updateColorFieldPreview(selectedStrokeColor);
        renderClassRows();
        updateJsonEditor();
    }

    function parseJsonEditor() {
        try {
            draftConfig = normalizeStyleConfig(JSON.parse(jsonEditor.value), classes);
            setError('');
            renderVisualEditor();
            return true;
        } catch (error) {
            setError(`Invalid JSON: ${error.message}`);
            return false;
        }
    }

    function switchTab(tabName) {
        if (tabName === 'visual' && !parseJsonEditor()) return;
        if (tabName === 'json') updateJsonEditor();
        tabButtons.forEach(btn => btn.classList.toggle('active', btn.dataset.styleTab === tabName));
        tabPanels.forEach(panel => panel.classList.toggle('active', panel.dataset.stylePanel === tabName));
    }

    defaultRenderMode.addEventListener('change', e => {
        draftConfig.defaults.render_mode = e.target.value;
        renderVisualEditor();
    });
    defaultStrokeWidth.addEventListener('input', e => {
        draftConfig.defaults.stroke_width = Number(e.target.value);
        renderVisualEditor();
    });
    defaultFillOpacity.addEventListener('input', e => {
        draftConfig.defaults.fill_opacity = Number(e.target.value);
        renderVisualEditor();
    });
    selectedStrokeWidth.addEventListener('input', e => {
        draftConfig.selected.stroke_width = Number(e.target.value);
        updateJsonEditor();
    });
    selectedStrokeColor.addEventListener('input', e => {
        draftConfig.selected.stroke_color = e.target.value;
        updateColorFieldPreview(e.target);
        updateJsonEditor();
    });
    preannotationFillOpacity.addEventListener('input', e => {
        draftConfig.preannotation.fill_opacity = Number(e.target.value);
        updateJsonEditor();
    });

    tabButtons.forEach(btn => btn.addEventListener('click', () => switchTab(btn.dataset.styleTab)));

    resetBtn.addEventListener('click', () => {
        draftConfig = normalizeStyleConfig(getDefaultStyleConfig(), classes);
        renderVisualEditor();
    });

    openBtn.addEventListener('click', () => {
        draftConfig = normalizeStyleConfig(config.annotationStyleConfig || getCurrentStyleConfig(), classes);
        renderVisualEditor();
        setError('');
        switchTab('visual');
        updateColorFieldPreview(selectedStrokeColor);
        modal.style.display = 'flex';
    });

    function closeModal() {
        modal.style.display = 'none';
        setError('');
    }

    closeBtn.addEventListener('click', closeModal);
    modal.addEventListener('click', e => {
        if (e.target === modal) closeModal();
    });

    saveBtn.addEventListener('click', async () => {
        const jsonPanelVisible = document.querySelector('.style-tab-panel.active')?.dataset.stylePanel === 'json';
        if (jsonPanelVisible && !parseJsonEditor()) return;

        saveBtn.disabled = true;
        setError('');
        try {
            const response = await fetch(`/annotation/style_config/${encodeURIComponent(config.projectName)}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ styleConfig: draftConfig }),
            });
            const payload = await response.json();
            if (!response.ok || !payload.success) {
                throw new Error(payload.detail || payload.error || 'Failed to save style settings');
            }
            config.annotationStyleConfig = clone(draftConfig);
            setCurrentStyleConfig(draftConfig, classes);
            drawImage();
            closeModal();
        } catch (error) {
            setError(error.message);
        } finally {
            saveBtn.disabled = false;
        }
    });
}
