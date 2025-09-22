import {
    initGlobals,
    currentImage,
    classColors,
    setSelectedClass,
    selectedAnnotation,
    updateTagHighlights,
    setupType,
    setAnnotationCache,
    selectedLabel,
    setSelectedLabel,
    annotations,
    setAnnotations
} from './globals.js';
import { initializeGridView, switchToAnnotationView, switchToGridView, sortImages, toggleView } from './viewManagement.js';
import { initToolControls } from './toolControls.js';
import { initAnnotationInteraction } from './annotationInteraction.js';
import { initKeyboardShortcuts } from './keyboardShortcuts.js';
import { initShortcutsSidebar, updateShortcutsNotice } from './shortcutsHelp.js';
import { initSaveHandling } from './saveHandling.js';
import { selectImage, resizeCanvas } from './imageHandling.js';
import { drawImage } from './annotationDrawing.js';
import { pushToUndoStack } from './annotationCore.js';
import { setConfidenceThreshold } from '/static/js/globals.js';
import { initImportModal } from '/static/js/importHandler.js';
import { showLoadingOverlay, hideLoadingOverlay } from '/static/js/spinnerLoader.js';
import { initializeSegmentor } from './sam.js';

function hideLoadingAnimation() {
    const loadingOverlay = document.getElementById('loading-overlay');
    const vfLoader = document.getElementById('vf-loader');
    if (loadingOverlay && vfLoader) {
        loadingOverlay.classList.remove('active');
        vfLoader.classList.remove('active');
    }
}

// In main.js
export function updateAnnotationStatus(imagePath, isAnnotated, isPreannotated) {
    const filename = imagePath.split('/').pop();
    const gridCard = document.querySelector(`#grid-thumbnails .image-checkbox[data-path="${imagePath}"]`)?.closest('.grid-card');
    if (gridCard) {
        const statusSpan = gridCard.querySelector('.image-status');
        const checkSpan = gridCard.querySelector('.annotated-check');
        gridCard.dataset.annotated = isAnnotated;
        gridCard.dataset.preannotated = isPreannotated ? 'true' : 'false';
        if (statusSpan) {
            statusSpan.textContent = isAnnotated ? 'Annotated' : (isPreannotated ? 'Pre-Annotated' : 'Not Annotated');
            statusSpan.dataset.annotated = isAnnotated ? 'true' : 'false';
            statusSpan.dataset.preannotated = isPreannotated ? 'true' : 'false';
        }
        if (isAnnotated) {
            if (!checkSpan) {
                const newCheck = document.createElement('span');
                newCheck.className = 'annotated-check';
                newCheck.innerHTML = '<i class="fas fa-check"></i>';
                gridCard.querySelector('.card-image-container').appendChild(newCheck);
            }
        } else if (checkSpan) {
            checkSpan.remove();
        }
    }
    const listRow = document.querySelector(`#list-table .image-checkbox[data-path="${imagePath}"]`)?.closest('tr');
    if (listRow) {
        listRow.dataset.annotated = isAnnotated;
        listRow.dataset.preannotated = isPreannotated ? 'true' : 'false';
        const statusCell = listRow.cells[4];
        const annotatorCell = listRow.cells[5];
        if (statusCell) {
            statusCell.textContent = isAnnotated ? 'Annotated' : (isPreannotated ? 'Pre-Annotated' : 'Not Annotated');
            statusCell.dataset.annotated = isAnnotated ? 'true' : 'false';
            statusCell.dataset.preannotated = isPreannotated ? 'true' : 'false';
        }
        if (isAnnotated && annotatorCell) {
            const appConfig = document.getElementById('app-config');
            const currentUserAvatar = appConfig.dataset.currentUserAvatar || '';
            listRow.dataset.annotator = currentUserAvatar;
            annotatorCell.innerHTML = currentUserAvatar ? `<div class="avatar">${currentUserAvatar}</div>` : '-';
        } else if (annotatorCell) {
            listRow.dataset.annotator = 'null';
            annotatorCell.innerHTML = '-';
        }
    }
    const thumbnailRow = document.querySelector(`.thumbnail-row[data-id="${filename}"]`);
    if (thumbnailRow) {
        thumbnailRow.dataset.annotated = isAnnotated;
        thumbnailRow.dataset.preannotated = isPreannotated ? 'true' : 'false'; 
    }
}

function updateBulkActionsState() {
    const checkboxes = document.querySelectorAll('.image-checkbox:checked');
    const hasSelections = checkboxes.length > 0;
    document.getElementById('download-btn').disabled = !hasSelections;
    document.getElementById('delete-images-btn').disabled = !hasSelections;
    const totalCheckboxes = document.querySelectorAll('.image-checkbox').length;
    const selectAllBtn = document.getElementById('select-all-btn');
    if (checkboxes.length === totalCheckboxes && totalCheckboxes > 0) {
        selectAllBtn.innerHTML = '<i class="fas fa-check-square"></i> Deselect All';
    } else {
        selectAllBtn.innerHTML = '<i class="fas fa-check-square"></i> Select All';
    }
}

function generateClassTags() {
    const container = document.getElementById('class-tags-container');
    container.innerHTML = '';

    if (setupType === 'Classification') {
        const left = document.createElement('div');
        left.id = 'available-classes';
        left.className = 'classes-left';

        const right = document.createElement('div');
        right.id = 'selected-classes';
        right.className = 'classes-right';

        container.appendChild(left);
        container.appendChild(right);

        updateClassTags(); // Initial population
    } else {
        // Non-classification: render tags directly
        Object.entries(classColors).forEach(([cls, color]) => {
            const tag = document.createElement('span');
            tag.className = 'class-tag';
            tag.dataset.class = cls;
            tag.style.backgroundColor = color;
            tag.textContent = cls;

            tag.addEventListener('click', () => {
                if (selectedAnnotation) {
                    pushToUndoStack();
                    selectedAnnotation.label = cls;
                    drawImage();
                    updateTagHighlights();
                } else {
                    document.querySelectorAll('.class-tag')
                        .forEach(t => t.classList.remove('selected'));
                    tag.classList.add('selected');
                    setSelectedClass(cls);
                }
            });

            container.appendChild(tag);
        });

        // Select the first tag by default
        if (Object.keys(classColors).length > 0) {
            const firstTag = container.querySelector('.class-tag');
            if (firstTag) {
                firstTag.classList.add('selected');
                setSelectedClass(firstTag.dataset.class);
            }
        }
    }

    // 🔍 Attach filtering after tags are rendered
    const searchInput = document.getElementById('class-search-input');
    if (searchInput) {
        searchInput.addEventListener('input', (e) => {
            const search = e.target.value.toLowerCase();
            document.querySelectorAll('#class-tags-container .class-tag').forEach(tag => {
                const text = tag.textContent.toLowerCase();
                tag.style.display = text.includes(search) ? 'flex' : 'none';
            });
        });
    }
}

function generateClassColors(classes) {
    const totalClasses = classes.length;
    const goldenAngle = 180 * (3 - Math.sqrt(5));
    let hue = 0;
    classes.forEach((cls, index) => {
        hue = (hue + goldenAngle) % 360;
        const saturation = 80 + Math.random() * 10;
        const lightness = 50 + Math.random() * 5;
        const color = hslToHex(hue, saturation, lightness);
        classColors[cls] = color + 'FF';
    });
}

function hslToHex(h, s, l) {
    h /= 360;
    s /= 100;
    l /= 100;
    let r, g, b;
    if (s === 0) {
        r = g = b = l;
    } else {
        const hue2rgb = (p, q, t) => {
            if (t < 0) t += 1;
            if (t > 1) t -= 1;
            if (t < 1/6) return p + (q - p) * 6 * t;
            if (t < 1/2) return q;
            if (t < 2/3) return p + (q - p) * (2/3 - t) * 6;
            return p;
        };
        const q = l < 0.5 ? l * (1 + s) : l + s - l * s;
        const p = 2 * l - q;
        r = hue2rgb(p, q, h + 1/3);
        g = hue2rgb(p, q, h);
        b = hue2rgb(p, q, h - 1/3);
    }
    const toHex = x => {
        const hex = Math.round(x * 255).toString(16);
        return hex.length === 1 ? '0' + hex : hex;
    };
    return `#${toHex(r)}${toHex(g)}${toHex(b)}`;
}

function showSuccessModal(message) {
    const modal = document.getElementById('save-modal');
    const saveMessage = modal.querySelector('.save-message');
    saveMessage.textContent = message;
    const modalContent = modal.querySelector('.modal-content');
    modalContent.classList.add('blue-theme');
    modal.style.display = 'block';
    setTimeout(() => {
        modal.style.display = 'none';
        modalContent.classList.remove('blue-theme');
    }, 3000);
}

document.addEventListener('DOMContentLoaded', function() {
    initGlobals();
    const config = JSON.parse(document.getElementById('app-config').textContent);
    const projectName = config.projectName; 
    const setupType = config.setupType;
    const classes = config.classes;
    generateClassColors(classes);
    generateClassTags();
    initializeGridView();
    hideLoadingAnimation();

    function handleCheckboxChange(e) {
        const checkbox = e.target;
        const path = checkbox.dataset.path;
        document.querySelectorAll(`.image-checkbox[data-path="${path}"]`).forEach(cb => {
            cb.checked = checkbox.checked;
        });
        updateBulkActionsState();
    }

    document.querySelectorAll('.image-checkbox').forEach(checkbox => {
        checkbox.addEventListener('change', handleCheckboxChange);
        checkbox.addEventListener('click', e => e.stopPropagation());
    });

    document.querySelectorAll('#list-table tbody tr').forEach(row => {
        row.addEventListener('click', (e) => {
            if (!e.target.closest('.image-checkbox')) {
                const img = row.querySelector('img');
                if (img) switchToAnnotationView(img);
            }
        });
    });

    document.querySelectorAll('#grid-thumbnails .grid-card img').forEach(img => {
        img.addEventListener('click', (e) => {
            if (!e.target.closest('.card-checkbox')) {
                switchToAnnotationView(img);
            }
        });
    });

    document.getElementById('viewport-btn-grid').addEventListener('click', () => switchToAnnotationView());
    document.getElementById('viewport-btn-annotation').addEventListener('click', switchToGridView);

    document.querySelectorAll('.thumbnail-row').forEach(row => {
        row.addEventListener('click', () => {
            const img = row.querySelector('img');
            const index = parseInt(row.dataset.index, 10);
            selectImage(img, index);
        });
    });

    ['sort-btn', 'sort-btn-annotation'].forEach(btnId => {
        const btn = document.getElementById(btnId);
        if (btn) {
            btn.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                const dropdownContent = btn.nextElementSibling; // .dropdown-content is next sibling
                if (dropdownContent && dropdownContent.classList.contains('dropdown-content')) {
                    // Close other dropdowns
                    document.querySelectorAll('.dropdown-content').forEach(d => {
                        if (d !== dropdownContent) d.style.display = 'none';
                    });
                    // Toggle current
                    dropdownContent.style.display = dropdownContent.style.display === 'block' ? 'none' : 'block';
                }
            });
        }
    });

    document.addEventListener('click', (e) => {
        if (!e.target.closest('.dropdown')) {
            document.querySelectorAll('.dropdown-content').forEach(d => d.style.display = 'none');
        }
    });

    document.querySelectorAll('.thumbnail-row').forEach(row => {
        row.addEventListener('click', () => {
            const img = row.querySelector('img');
            const index = parseInt(row.dataset.index, 10);
            if (img && !img.src) {
                img.src = img.dataset.src;
            }
            selectImage(img, index);
        });
    });

    document.getElementById('grid-toggle-btn').addEventListener('click', () => toggleView('grid'));
    document.getElementById('list-toggle-btn').addEventListener('click', () => toggleView('list'));

    document.getElementById('delete-images-btn').addEventListener('click', () => {
        const checkedBoxes = document.querySelectorAll('.image-checkbox:checked');
        if (checkedBoxes.length === 0) {
            alert('No images selected for deletion');
            return;
        }

        const imageUrls = [...new Set(Array.from(checkedBoxes).map(cb => cb.dataset.path))];

        const deleteModal = document.getElementById('delete-images-confirm-modal');
        const deleteMessage = document.getElementById('delete-images-message');
        deleteMessage.textContent = `Are you sure you want to delete ${imageUrls.length} selected image${imageUrls.length > 1 ? 's' : ''}?`;
        deleteModal.style.display = 'flex';

        document.getElementById('confirm-delete-images').onclick = async () => {
            try {
                const response = await fetch('/annotation/delete_images', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        project: config.projectName,
                        images: imageUrls
                    })
                });

                const result = await response.json();
                if (result.success) {
                    imageUrls.forEach(url => {
                        const filename = url.split('/').pop();
                        document.querySelectorAll(`#grid-thumbnails .grid-card .image-checkbox[data-path="${url}"]`)
                            .forEach(cb => cb.closest('.grid-card').remove());
                        document.querySelectorAll(`#list-table .image-checkbox[data-path="${url}"]`)
                            .forEach(cb => cb.closest('tr').remove());
                        document.querySelectorAll(`.thumbnail-row[data-id="${filename}"]`)
                            .forEach(row => row.remove());
                    });

                    document.querySelectorAll('#grid-thumbnails .grid-card').forEach((card, index) => {
                        const idSpan = card.querySelector('.image-id');
                        if (idSpan) idSpan.textContent = index;
                    });

                    document.querySelectorAll('#list-table tbody tr').forEach((row, index) => {
                        const idCell = row.cells[1];
                        if (idCell) idCell.textContent = index;
                        row.dataset.id = index;
                    });

                    document.querySelectorAll('.thumbnail-row').forEach((row, index) => {
                        const idCell = row.querySelector('.thumbnail-id');
                        if (idCell) idCell.textContent = index;
                        row.dataset.index = index;
                    });

                    deleteModal.style.display = 'none';
                    updateBulkActionsState();
                } else {
                    alert(result.error || 'Failed to delete images');
                }
            } catch (error) {
                console.error('Delete error:', error);
                alert('Failed to delete images');
            }
        };

        document.getElementById('cancel-delete-images').onclick = () => {
            deleteModal.style.display = 'none';
        };
        document.getElementById('cancel-delete-images-footer').onclick = () => {
            deleteModal.style.display = 'none';
        };
    });

    if (config.setupType !== 'Classification') {
        initToolControls();
    }
    initAnnotationInteraction();
    initKeyboardShortcuts();
    initShortcutsSidebar();
    updateShortcutsNotice();
    initSaveHandling(updateAnnotationStatus);
    initializeSegmentor();

    const selectAllBtn = document.getElementById('select-all-btn');
    const downloadBtn = document.getElementById('download-btn');
    const deleteBtn = document.getElementById('delete-images-btn');
    const exportBtn = document.getElementById('export-btn');
    const exportModal = document.getElementById('export-modal');
    const exportCloseBtn = document.querySelector('.export-close-btn');
    const cancelExportBtn = document.getElementById('cancel-export');
    const confirmExportBtn = document.getElementById('confirm-export');
    const formatCards = document.querySelectorAll('.format-card');
    const nextExportBtn = document.getElementById('next-export-button');
    const backExportBtn = document.getElementById('back-export-button');
    const enableSplitting = document.getElementById('enable-splitting');
    const splitCheckboxes = document.querySelectorAll('input[name="split"]');
    const ratioControls = document.querySelectorAll('.ratio-control');
    const ratioTotal = document.getElementById('ratio-total-value');
    const ratioError = document.getElementById('ratio-error');
    const tabLinks = document.querySelectorAll('.tab-link');
    const tabContents = document.querySelectorAll('.tab-content');

    if (config.setupType !== 'Classification') {
        const confidenceSlider = document.getElementById('confidence-slider');
        const confidenceValue = document.getElementById('confidence-value');
        const hidePredictionBtn = document.getElementById('hide-prediction-btn');
        let lastConfidenceValue = 0.4;

        if (hidePredictionBtn) {
            hidePredictionBtn.addEventListener('click', () => {
                const slider = document.getElementById('confidence-slider');
                const confidenceValueSpan = document.getElementById('confidence-value');
                if (slider.classList.contains('disabled')) {
                    slider.classList.remove('disabled');
                    setConfidenceThreshold(lastConfidenceValue);
                    confidenceValueSpan.textContent = lastConfidenceValue.toFixed(2);
                    hidePredictionBtn.textContent = 'Hide Pred.';
                } else {
                    lastConfidenceValue = parseFloat(slider.value);
                    slider.classList.add('disabled');
                    setConfidenceThreshold(1.01);
                    confidenceValueSpan.textContent = '1.01';
                    hidePredictionBtn.textContent = 'Show Pred.';
                }
                drawImage();
            });
        }

        if (confidenceSlider) {
            confidenceSlider.addEventListener('input', () => {
                const value = parseFloat(confidenceSlider.value);
                lastConfidenceValue = value;
                setConfidenceThreshold(value);
                confidenceValue.textContent = value.toFixed(2);
                drawImage();
            });
        }
    }

    document.querySelectorAll('.dropdown-content a').forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            sortImages(e.target.dataset.sort);
            e.target.closest('.dropdown-content').style.display = 'none';
        });
    });

    function updateButtonStates() {
        const checkedCount = document.querySelectorAll('.image-checkbox:checked').length;
        const isAnyChecked = checkedCount > 0;
        downloadBtn.disabled = !isAnyChecked;
        deleteBtn.disabled = !isAnyChecked;
    }

    updateButtonStates();

    tabLinks.forEach(link => {
        link.addEventListener('click', () => {
            const tabId = link.getAttribute('data-tab');
            tabLinks.forEach(l => l.classList.remove('active'));
            link.classList.add('active');
            tabContents.forEach(content => content.classList.remove('active'));
            document.getElementById(tabId).classList.add('active');
        });
    });

    enableSplitting.addEventListener('change', function() {
        const isEnabled = this.checked;
        document.querySelectorAll('.split-choice input:not(#train-split)').forEach(checkbox => {
            checkbox.disabled = !isEnabled;
        });
        updateRatioControls();
    });

    splitCheckboxes.forEach(checkbox => {
        checkbox.addEventListener('change', function() {
            updateRatioControls();
            adjustRatios();
        });
    });

    document.querySelectorAll('input[type="range"], input[type="number"]').forEach(input => {
        input.addEventListener('input', function() {
            const split = this.closest('.ratio-control').dataset.split;
            const value = parseInt(this.value);

            if (this.type === 'range') {
                document.getElementById(`${split}-ratio-value`).value = value;
            } else {
                document.getElementById(`${split}-ratio`).value = value;
            }

            ratios[split] = value;
            adjustRatios();
        });
    });

    function updateRatioControls() {
        const isEnabled = enableSplitting.checked;
        const selectedSplits = Array.from(splitCheckboxes)
            .filter(cb => cb.checked)
            .map(cb => cb.value);

        ratioControls.forEach(control => {
            const split = control.dataset.split;
            if (selectedSplits.includes(split) && isEnabled) {
                control.style.display = 'flex';
            } else {
                control.style.display = 'none';
            }
        });

        if (isEnabled) {
            document.querySelector('.ratio-control[data-split="train"]').style.display = 'flex';
        }
    }

    function adjustRatios() {
        if (!enableSplitting.checked) {
            ratios = { train: 100, test: 0, val: 0 };
            updateRatioInputs();
            ratioTotal.textContent = '100';
            ratioError.style.display = 'none';
            document.getElementById('confirm-export').disabled = false;
            return;
        }

        const selectedSplits = Array.from(splitCheckboxes)
            .filter(cb => cb.checked)
            .map(cb => cb.value);

        if (selectedSplits.length === 1 && selectedSplits[0] === 'train') {
            ratios.train = 100;
            ratios.test = 0;
            ratios.val = 0;
            updateRatioInputs();
            ratioTotal.textContent = '100';
            ratioError.style.display = 'none';
            document.getElementById('confirm-export').disabled = false;
            return;
        }

        const total = selectedSplits.reduce((sum, split) => sum + ratios[split], 0);

        ratioTotal.textContent = total;

        if (total !== 100) {
            ratioError.style.display = 'flex';
            document.getElementById('confirm-export').disabled = true;
        } else {
            ratioError.style.display = 'none';
            document.getElementById('confirm-export').disabled = false;
        }
    }

    function updateRatioInputs() {
        for (const split in ratios) {
            document.getElementById(`${split}-ratio`).value = ratios[split];
            document.getElementById(`${split}-ratio-value`).value = ratios[split];
        }
    }

    let ratios = {
        train: 70,
        test: 15,
        val: 15
    };

    selectAllBtn.addEventListener('click', () => {
        const allChecked = document.querySelectorAll('.image-checkbox:checked').length === document.querySelectorAll('.image-checkbox').length;
        document.querySelectorAll('.image-checkbox').forEach(checkbox => {
            checkbox.checked = !allChecked;
        });
        updateButtonStates();
    });

    document.querySelectorAll('.image-checkbox').forEach(checkbox => {
        checkbox.addEventListener('change', updateButtonStates);
    });

    const importModalElement = document.getElementById('import-images-modal');
    const importForm = document.getElementById('import-images-form');
    const importDropZone = document.getElementById('import-images-drop-zone');
    const importFileInput = document.getElementById('import-images-file-input');
    const importFileList = document.getElementById('import-images-file-list');
    const importCloseBtn = document.querySelector('.import-close-btn');
    const importCompressMsg = document.getElementById('import-images-compress-message');
    const importProgressContainer = document.getElementById('import-images-progress-container');
    const importBtn = document.getElementById('import-images-btn');
    const importSubmitBtn = importForm.querySelector('.create-btn');

    const importModal = initImportModal(
        importModalElement,
        importForm,
        importDropZone,
        importFileInput,
        importFileList,
        importCloseBtn,
        importCompressMsg,
        importProgressContainer,
        importSubmitBtn,
        true
    );

    importBtn.addEventListener('click', () => {
        importModalElement.style.display = 'flex';
        importModal.reset();
        importSubmitBtn.disabled = true;
    });

    importForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const uploadId = importModal.getStoredUploadId();
        if (!uploadId) {
            alert('Please select at least one image to import');
            return;
        }
        try {
            showLoadingOverlay('Importing images...');

            const formData = new FormData();
            formData.append('project_name', projectName);
            formData.append('upload_id', uploadId);
            const response = await fetch('/import_images', {
                method: 'POST',
                body: formData
            });
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            const result = await response.json();
            if (result.success) {
                importProgressContainer.innerHTML = '<p>Upload complete!</p>';
                setTimeout(() => {
                    importModalElement.style.display = 'none';
                    location.reload();
                }, 1000);
            } else {
                alert(result.error || 'Failed to import images');
                importProgressContainer.innerHTML = '';
                importFileList.innerHTML = '';
                importFileList.style.display = 'none';
                importDropZone.querySelector('.drop-icon').classList.remove('loaded');
                importCompressMsg.style.display = 'none';
                importSubmitBtn.disabled = true;
            }
        } catch (error) {
            console.error('Import error:', error);
            alert('Failed to import images: ' + error.message);
            importProgressContainer.innerHTML = '';
            importFileList.innerHTML = '';
            importFileList.style.display = 'none';
            importDropZone.querySelector('.drop-icon').classList.remove('loaded');
            importCompressMsg.style.display = 'none';
            importSubmitBtn.disabled = true;
        } finally {
            hideLoadingOverlay();
        }
    });

    const downloadModal = document.getElementById('download-modal');
    const downloadCloseBtn = document.querySelector('#download-modal .close-btn');
    const cancelDownloadBtn = document.getElementById('cancel-download');
    const confirmDownloadBtn = document.getElementById('confirm-download');

    downloadBtn.addEventListener('click', () => {
        const selectedCheckboxes = document.querySelectorAll('.image-checkbox:checked');
        if (selectedCheckboxes.length === 0) {
            alert('No images selected for download');
            return;
        }
        downloadModal.style.display = 'flex';
    });

    if (downloadCloseBtn) {
        downloadCloseBtn.addEventListener('click', () => {
            downloadModal.style.display = 'none';
        });
    }

    cancelDownloadBtn.addEventListener('click', () => {
        downloadModal.style.display = 'none';
    });

    document.getElementById('download-direct').addEventListener('change', () => {
        document.getElementById('dl-path-container').style.display = 'none';
    });

    document.getElementById('download-path').addEventListener('change', () => {
        document.getElementById('dl-path-container').style.display = 'block';
    });

    confirmDownloadBtn.addEventListener('click', async () => {
        const option = document.querySelector('input[name="dl_option"]:checked').value;
        const filenames = [...new Set(Array.from(document.querySelectorAll('.image-checkbox:checked')).map(cb => cb.dataset.path.split('/').pop()))];
        let data = {
            project: projectName,
            images: filenames
        };
        if (option === 'path') {
            const savePath = document.getElementById('dl-path-input').value.trim();
            if (!savePath) {
                alert('Please enter the save path');
                return;
            }
            data.save_path = savePath;
        }
        showLoadingOverlay('Downloading...');
        try {
            const response = await fetch('/annotation/download_images', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });
            if (!response.ok) {
                throw new Error(response.statusText);
            }
            const contentType = response.headers.get('content-type');
            if (contentType && contentType.includes('application/json')) {
                const result = await response.json();
                if (result.success) {
                    showSuccessModal(`Images saved to ${result.saved_file}`);
                } else {
                    throw new Error(result.error || 'Unknown error');
                }
            } else {
                const blob = await response.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `${projectName}_images.zip`;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                window.URL.revokeObjectURL(url);
            }
            downloadModal.style.display = 'none';
        } catch (error) {
            console.error('Download error:', error);
            alert('Failed to download/save images: ' + error.message);
        } finally {
            hideLoadingOverlay();
        }
    });

    let selectedFormat = null;
    exportBtn.addEventListener('click', () => {
        exportModal.style.display = 'flex';
        selectedFormat = null;
        confirmExportBtn.disabled = true;
        nextExportBtn.disabled = true;
        formatCards.forEach(card => card.classList.remove('selected'));
        tabLinks[0].click();
        enableSplitting.checked = true;
        splitCheckboxes.forEach(cb => {
            if (cb.id === 'train-split') {
                cb.checked = true;
                cb.disabled = true;
            } else {
                cb.checked = true;
                cb.disabled = false;
            }
        });
        ratios = { train: 70, test: 15, val: 15 };
        updateRatioInputs();
        updateRatioControls();
        adjustRatios();
        const setupType = document.getElementById('app-config').dataset.setupType;
        formatCards.forEach(card => {
            const format = card.dataset.format;
            if ((setupType === "Oriented Bounding Box" && !['CSV', 'YOLO'].includes(format)) ||
                (setupType === "Segmentation" && !['COCO', 'YOLO'].includes(format))) {
                card.style.display = 'none';
            } else {
                card.style.display = 'flex';
            }
        });
        // Check for unannotated images and show warning
        const allCards = document.querySelectorAll('.grid-card');
        const hasUnannotated = Array.from(allCards).some(card => card.dataset.annotated === 'false');
        const warningEl = document.getElementById('export-warning');
        if (hasUnannotated && warningEl) {
            warningEl.style.display = 'block';
            warningEl.innerHTML = '⚠️ Warning: Some images are not annotated or only pre-annotated. Consider completing annotations before exporting.';
        } else if (warningEl) {
            warningEl.style.display = 'none';
        }
    });
    exportCloseBtn.addEventListener('click', () => {
        exportModal.style.display = 'none';
        const warningEl = document.getElementById('export-warning');
        if (warningEl) warningEl.style.display = 'none';
    });
    cancelExportBtn.addEventListener('click', () => {
        exportModal.style.display = 'none';
        const warningEl = document.getElementById('export-warning');
        if (warningEl) warningEl.style.display = 'none';
    });
    nextExportBtn.addEventListener('click', () => {
        tabLinks[1].click();
    });
    backExportBtn.addEventListener('click', () => {
        tabLinks[0].click();
    });
    formatCards.forEach(card => {
        card.addEventListener('click', () => {
            formatCards.forEach(c => c.classList.remove('selected'));
            card.classList.add('selected');
            selectedFormat = card.dataset.format;
            nextExportBtn.disabled = false;
        });
    });
    document.getElementById('export-download').addEventListener('change', () => {
        document.getElementById('export-path-container').style.display = 'none';
    });
    document.getElementById('export-path').addEventListener('change', () => {
        document.getElementById('export-path-container').style.display = 'block';
    });
    confirmExportBtn.addEventListener('click', async () => {
        if (!selectedFormat) {
            alert('Please select an export format');
            return;
        }
        const selectedCheckboxes = document.querySelectorAll('.image-checkbox:checked');
        const imagePaths = Array.from(selectedCheckboxes).map(cb => cb.dataset.path);
        const splitChoices = [];
        const splitRatios = {};
        if (enableSplitting.checked) {
            splitCheckboxes.forEach(checkbox => {
                if (checkbox.checked) {
                    splitChoices.push(checkbox.value);
                    splitRatios[checkbox.value] = ratios[checkbox.value];
                }
            });
            if (splitChoices.length === 1 && splitChoices[0] === 'train') {
                splitRatios.train = 100;
            }
        } else {
            splitChoices.push('train');
            splitRatios.train = 100;
        }
        let data = {
            format: selectedFormat,
            images: imagePaths,
            split_choices: splitChoices,
            split_ratios: splitRatios
        };
        const option = document.querySelector('input[name="export_option"]:checked').value;
        if (option === 'path') {
            const savePath = document.getElementById('export-path-input').value.trim();
            if (!savePath) {
                alert('Please enter the save path');
                return;
            }
            data.local_export = true;
            data.export_path = savePath;
        }
        showLoadingOverlay('Exporting...');
        try {
            const response = await fetch(`/annotation/export/${projectName}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });
            if (!response.ok) {
                throw new Error(response.statusText);
            }
            const contentType = response.headers.get('content-type');
            if (contentType && contentType.includes('application/json')) {
                const result = await response.json();
                if (result.success) {
                    showSuccessModal(`Export saved to ${result.saved_path}`);
                } else {
                    throw new Error(result.error || 'Unknown error');
                }
            } else {
                const blob = await response.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `${projectName}_${selectedFormat}.zip`;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                window.URL.revokeObjectURL(url);
            }
            exportModal.style.display = 'none';
        } catch (error) {
            console.error('Export error:', error);
            alert('Export failed: ' + error.message);
        } finally {
            hideLoadingOverlay();
        }
    });

    const lazyImages = document.querySelectorAll('.lazy-load');
    const observer = new IntersectionObserver((entries, observer) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const img = entry.target;
                if (!img.src) {
                    img.src = img.dataset.src;
                    img.onload = () => {
                        img.classList.add('loaded');
                    };
                    img.onerror = () => {
                        console.error('Failed to load image:', img.dataset.src);
                    };
                }
                observer.unobserve(img);
            }
        });
    }, {
        root: null,
        rootMargin: '100px',
        threshold: 0.1
    });

    lazyImages.forEach(img => {
        observer.observe(img);
    });

    document.querySelectorAll('#grid-thumbnails .grid-card img.lazy-load').forEach(img => {
        img.addEventListener('click', (e) => {
            if (!e.target.closest('.card-checkbox')) {
                switchToAnnotationView(img);
            }
        });
    });

    document.querySelectorAll('#list-table tbody tr img.lazy-load').forEach(img => {
        img.addEventListener('click', (e) => {
            if (!e.target.closest('.image-checkbox')) {
                switchToAnnotationView(img);
            }
        });
    });

    document.querySelectorAll('.thumbnail-row img.lazy-load').forEach((img, index) => {
        img.addEventListener('click', () => {
            selectImage(img, index);
        });
    });

    const aiPreannotatorBtn = document.getElementById('ai-preannotator-btn');
    const aiPreannotatorModal = document.getElementById('ai-preannotator-modal');
    const aiPreannotatorForm = document.getElementById('ai-preannotator-form');
    const closeBtn = aiPreannotatorModal.querySelector('.close-btn');
    const modeButtons = document.querySelectorAll('.mode-btn');
    const modeInput = document.getElementById('mode');
    let statusInterval;

    async function checkPreannotationStatus() {
        const response = await fetch(`/annotation/check_preannotation_status?project_name=${config.projectName}`);
        const data = await response.json();
        return data.status;
    }

    function updateUI(status) {
        const applyButton = aiPreannotatorForm.querySelector('.create-btn');

        if (status === 'running') {
            applyButton.disabled = true;
            applyButton.textContent = 'Processing...';
        } else {
            applyButton.disabled = false;
            applyButton.textContent = 'Apply';
            if (statusInterval) {
                clearInterval(statusInterval);
                statusInterval = null;
            }
        }
    }

    aiPreannotatorBtn.addEventListener('click', async () => {
        aiPreannotatorModal.style.display = 'flex';
        try {
            const status = await checkPreannotationStatus();
            updateUI(status);
            if (status === 'running' && !statusInterval) {
                statusInterval = setInterval(async () => {
                    const newStatus = await checkPreannotationStatus();
                    updateUI(newStatus);
                    if (newStatus !== 'running') {
                        clearInterval(statusInterval);
                        statusInterval = null;
                        if (newStatus === 'completed') {
                            showSuccessModal('Pre-annotation completed successfully');
                            setTimeout(() => location.reload(), 3000);
                        } else if (newStatus === 'failed') {
                            alert('Pre-annotation failed');
                        }
                    }
                }, 2000);
            }
            const response = await fetch('/annotation/check_gpu');
            const data = await response.json();
            const processingUnitSelect = document.getElementById('processing-unit');
            const cpuWarning = document.getElementById('cpu-warning');
            if (data.success && data.has_gpu) {
                processingUnitSelect.value = 'cuda';
                processingUnitSelect.disabled = false;
                cpuWarning.style.display = 'none';
            } else {
                processingUnitSelect.value = 'cpu';
                processingUnitSelect.disabled = true;
                cpuWarning.style.display = 'block';
            }
        } catch (error) {
            console.error('Error checking status or GPU:', error);
        }
    });

    closeBtn.addEventListener('click', () => {
        aiPreannotatorModal.style.display = 'none';
        if (statusInterval) {
            clearInterval(statusInterval);
            statusInterval = null;
        }
    });

    modeButtons.forEach(button => {
        button.addEventListener('click', () => {
            modeButtons.forEach(btn => btn.classList.remove('active'));
            button.classList.add('active');
            const mode = button.dataset.mode;
            modeInput.value = mode;
            if (mode === 'custom-model') {
                document.getElementById('custom-model-path').style.display = 'block';
                document.getElementById('zero-shot-options').style.display = 'none';
            } else {
                document.getElementById('custom-model-path').style.display = 'none';
                document.getElementById('zero-shot-options').style.display = 'block';
            }
        });
    });

    aiPreannotatorForm.addEventListener('submit', async (e) => {
        e.preventDefault();

        const applyButton = aiPreannotatorForm.querySelector('.create-btn');
        applyButton.disabled = true;
        applyButton.textContent = 'Processing...';
        const formData = new FormData();
        const mode = modeInput.value;
        formData.append('mode', mode);
        formData.append('project_name', projectName);

        if (mode === 'zero-shot') {
            const dinoModel = document.getElementById('dino-model').value;
            formData.append('dino_model', dinoModel);
        } else if (mode === 'custom-model') {
            const modelPath = document.getElementById('model-path-input').value.trim();
            formData.append('model_path', modelPath || 'yolov10x.pt');
        }

        const processingUnit = document.getElementById('processing-unit').value;
        formData.append('processing_unit', processingUnit);
        const boxThreshold = document.getElementById('box-threshold').value;
        formData.append('box_threshold', boxThreshold);
        try {
            const response = await fetch('/annotation/ai_preannotator_config', {
                method: 'POST',
                body: formData
            });
            const result = await response.json();
            if (result.success) {
                statusInterval = setInterval(async () => {
                    const newStatus = await checkPreannotationStatus();
                    updateUI(newStatus);
                    if (newStatus !== 'running') {
                        clearInterval(statusInterval);
                        statusInterval = null;
                        if (newStatus === 'completed') {
                            showSuccessModal('Pre-annotation completed successfully');
                            aiPreannotatorModal.style.display = 'none';
                            setTimeout(() => location.reload(), 3000);
                        } else if (newStatus === 'failed') {
                            alert('Pre-annotation failed');
                        }
                    }
                }, 2000);
            } else {
                alert(`Failed to start pre-annotation: ${result.error || 'Unknown error'}`);
                updateUI('not_started');
            }
        } catch (error) {
            console.error('Error running pre-annotation:', error);
            alert(`Error running pre-annotation: ${error.message}`);
            updateUI('not_started');
        }
    });

    const blindTrustBtn = document.getElementById('ai-blind-trust');
    const blindTrustModal = document.getElementById('blind-trust-modal');
    const blindTrustForm = document.getElementById('blind-trust-form');
    const blindTrustCloseBtn = blindTrustModal.querySelector('.close-btn');
    let blindTrustStatusInterval;

    async function checkBlindTrustStatus() {
        const response = await fetch(`/annotation/check_blind_trust_status?project_name=${projectName}`);
        const data = await response.json();
        return data.status;
    }

    function updateBlindTrustUI(status) {
        const applyButton = blindTrustForm.querySelector('.create-btn');

        if (status === 'running') {
            applyButton.disabled = true;
            applyButton.textContent = 'Processing...';
        } else {
            applyButton.disabled = false;
            applyButton.textContent = 'Apply';
            if (blindTrustStatusInterval) {
                clearInterval(blindTrustStatusInterval);
                blindTrustStatusInterval = null;
            }
        }
    }

    blindTrustBtn.addEventListener('click', async () => {
        blindTrustModal.style.display = 'flex';
        try {
            const status = await checkBlindTrustStatus();
            updateBlindTrustUI(status);
            if (status === 'running' && !blindTrustStatusInterval) {
                blindTrustStatusInterval = setInterval(async () => {
                    const newStatus = await checkBlindTrustStatus();
                    updateBlindTrustUI(newStatus);
                    if (newStatus !== 'running') {
                        clearInterval(blindTrustStatusInterval);
                        blindTrustStatusInterval = null;
                        if (newStatus === 'completed') {
                            showSuccessModal('Blind Trust completed successfully');
                            blindTrustModal.style.display = 'none';
                            setTimeout(() => location.reload(), 3000);
                        } else if (newStatus === 'failed') {
                            alert('Blind Trust failed');
                        }
                    }
                }, 2000);
            }
        } catch (error) {
            console.error('Error checking blind trust status:', error);
        }
    });

    blindTrustCloseBtn.addEventListener('click', () => {
        blindTrustModal.style.display = 'none';
        if (blindTrustStatusInterval) {
            clearInterval(blindTrustStatusInterval);
            blindTrustStatusInterval = null;
        }
    });

    blindTrustForm.addEventListener('submit', async (e) => {
        e.preventDefault();

        const applyButton = blindTrustForm.querySelector('.create-btn');
        applyButton.disabled = true;
        applyButton.textContent = 'Processing...';
        const formData = new FormData();
        formData.append('project_name', projectName);
        const confidenceThreshold = document.getElementById('confidence-threshold').value;
        formData.append('confidence_threshold', confidenceThreshold);
        try {
            const response = await fetch('/annotation/blind_trust', {
                method: 'POST',
                body: formData
            });
            const result = await response.json();
            if (result.success) {
                blindTrustStatusInterval = setInterval(async () => {
                    const newStatus = await checkBlindTrustStatus();
                    updateBlindTrustUI(newStatus);
                    if (newStatus !== 'running') {
                        clearInterval(blindTrustStatusInterval);
                        blindTrustStatusInterval = null;
                        if (newStatus === 'completed') {
                            showSuccessModal('Blind Trust completed successfully');
                            blindTrustModal.style.display = 'none';
                            setTimeout(() => location.reload(), 3000);
                        } else if (newStatus === 'failed') {
                            alert('Blind Trust failed');
                        }
                    }
                }, 2000);
            } else {
                alert(`Failed to start Blind Trust: ${result.error || 'Unknown error'}`);
                updateBlindTrustUI('not_started');
            }
        } catch (error) {
            console.error('Error running Blind Trust:', error);
            alert(`Error running Blind Trust: ${error.message}`);
            updateBlindTrustUI('not_started');
        }
    });

    window.addEventListener('resize', () => {
        if (currentImage) {
            resizeCanvas();
        }
    });

    setAnnotationCache({});
    console.log('Annotation Cache Cleared on Load');

    function addSparkles() {
        const sparkle = document.createElement('span');
        sparkle.className = 'sparkle';
        sparkle.style.left = `${Math.random() * 100}%`;
        sparkle.style.animationDelay = `${Math.random() * 1}s`;
        aiPreannotatorBtn.appendChild(sparkle);
        setTimeout(() => sparkle.remove(), 2000);
    }

    setInterval(addSparkles, 500);
});

export function updateClassTags() {
    if (setupType !== 'Classification') return;
    const container = document.getElementById('class-tags-container');
    if (!container) return;

    const left = document.getElementById('available-classes');
    const right = document.getElementById('selected-classes');
    if (!left || !right) return;

    left.innerHTML = '';
    right.innerHTML = '';

    const available = Object.keys(classColors).filter(cls => cls !== selectedLabel);
    available.forEach(cls => {
        const tag = document.createElement('span');
        tag.className = 'class-tag';
        tag.dataset.class = cls;
        tag.style.backgroundColor = classColors[cls];
        tag.textContent = cls;

        const plus = document.createElement('button');
        plus.textContent = '+';
        plus.className = 'add-btn';
        plus.addEventListener('click', () => {
            pushToUndoStack();
            setSelectedLabel(cls);
            updateClassTags();
            annotations = [{ type: 'classification', label: cls }];
            drawImage(); // Redraw if needed, though no visual annotations
        });
        tag.appendChild(plus);
        left.appendChild(tag);
    });

    if (selectedLabel) {
        const tag = document.createElement('span');
        tag.className = 'class-tag selected-label';
        tag.dataset.class = selectedLabel;
        tag.style.backgroundColor = classColors[selectedLabel];
        tag.textContent = selectedLabel;

        const minus = document.createElement('button');
        minus.textContent = '-';
        minus.className = 'remove-btn';
        minus.addEventListener('click', () => {
            pushToUndoStack();
            setSelectedLabel(null);
            updateClassTags();
            annotations = [];
            drawImage();
        });
        tag.appendChild(minus);
        right.appendChild(tag);
    }
}