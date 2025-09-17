import { state } from './sharedState.js';
import { selectImage } from './imageHandling.js';

export function switchToAnnotationView(imgElement = null) {
    console.log('Switching to annotation view');
    const gridView = document.getElementById('grid-view');
    const annotationView = document.getElementById('annotation-view');

    gridView.classList.remove('show');
    gridView.classList.add('hide');
    gridView.addEventListener('transitionend', function handler() {
        gridView.style.display = 'none';
        gridView.removeEventListener('transitionend', handler);
    }, { once: true });

    annotationView.style.display = 'flex';
    annotationView.classList.remove('hide');
    annotationView.classList.add('show');

    document.querySelectorAll('#annotation-view .lazy-load').forEach(img => {
        if (!img.src) {
            img.src = img.dataset.src;
        }
    });

    setTimeout(() => {
        annotationView.classList.add('show');
    }, 10);

    let index = 0; // Default to first

    if (imgElement) {
        const gridCard = imgElement.closest('.grid-card');
        const listRow = imgElement.closest('#list-table tbody tr');

        if (gridCard) {
            index = Array.from(document.querySelectorAll('.grid-card')).indexOf(gridCard);
        } else if (listRow) {
            index = Array.from(document.querySelectorAll('#list-table tbody tr')).indexOf(listRow);
        } else {
            console.error('Could not determine parent element for image:', imgElement);
        }

        if (index === -1) {
            console.error('Image element not found in current view:', imgElement);
            index = 0; // Fallback to first
        }
    }

    const allThumbnails = document.querySelectorAll('#annotation-view .thumbnail-row img'); // Fresh query for current order
    const targetImg = allThumbnails[index];
    if (targetImg) {
        // Ensure src is set (redundant after force-load, but safe)
        if (!targetImg.src) {
            targetImg.src = targetImg.dataset.src;
        }
        selectImage(targetImg, index);
    } else if (allThumbnails.length > 0) {
        // Fallback for button click or invalid index
        const firstImg = allThumbnails[0];
        if (!firstImg.src) {
            firstImg.src = firstImg.dataset.src;
        }
        selectImage(firstImg, 0);
    } else {
        console.error('No thumbnails available in annotation view');
    }
}

export function switchToGridView() {
    console.log('Switching to grid view');
    const gridView = document.getElementById('grid-view');
    const annotationView = document.getElementById('annotation-view');

    annotationView.classList.remove('show');
    annotationView.classList.add('hide');
    annotationView.addEventListener('transitionend', function handler() {
        annotationView.style.display = 'none';
        annotationView.removeEventListener('transitionend', handler);
    }, { once: true });

    gridView.style.display = 'block';
    gridView.classList.remove('hide');
    setTimeout(() => {
        gridView.classList.add('show');
    }, 10);
    annotationView.classList.add('hide');
    document.getElementById('grid-view').classList.remove('hide');

}

export function initializeGridView() {
    const gridView = document.getElementById('grid-view');
    const annotationView = document.getElementById('annotation-view');
    gridView.style.display = 'block';
    annotationView.style.display = 'none';
    gridView.classList.add('show');
    gridView.classList.remove('hide');
    annotationView.classList.add('hide');
    annotationView.classList.remove('show');
}

export function sortImages(sortType) {
    const gridCards = Array.from(document.querySelectorAll('.grid-card'));
    const listRows = Array.from(document.querySelectorAll('#list-table tbody tr'));
    const thumbnailRows = Array.from(document.querySelectorAll('.thumbnail-row'));

    let sortedGrid = gridCards;
    let sortedList = listRows;
    let sortedThumbnails = thumbnailRows;

    switch(sortType) {
        case 'name-asc':
            sortedGrid = gridCards.sort((a, b) => a.dataset.id.localeCompare(b.dataset.id));
            sortedList = listRows.sort((a, b) => {
                const aPath = a.querySelector('.image-checkbox')?.dataset.path || '';
                const bPath = b.querySelector('.image-checkbox')?.dataset.path || '';
                return aPath.split('/').pop().localeCompare(bPath.split('/').pop());
            });
            sortedThumbnails = thumbnailRows.sort((a, b) => a.dataset.id.localeCompare(b.dataset.id));
            break;
        case 'name-desc':
            sortedGrid = gridCards.sort((a, b) => b.dataset.id.localeCompare(a.dataset.id));
            sortedList = listRows.sort((a, b) => {
                const aPath = a.querySelector('.image-checkbox')?.dataset.path || '';
                const bPath = b.querySelector('.image-checkbox')?.dataset.path || '';
                return bPath.split('/').pop().localeCompare(aPath.split('/').pop());
            });
            sortedThumbnails = thumbnailRows.sort((a, b) => b.dataset.id.localeCompare(a.dataset.id));
            break;
        case 'date-asc':
            sortedGrid = gridCards.sort((a, b) => new Date(a.dataset.date) - new Date(b.dataset.date));
            sortedList = listRows.sort((a, b) => new Date(a.dataset.date) - new Date(b.dataset.date));
            sortedThumbnails = thumbnailRows.sort((a, b) => new Date(a.dataset.date) - new Date(b.dataset.date));
            break;
        case 'date-desc':
            sortedGrid = gridCards.sort((a, b) => new Date(b.dataset.date) - new Date(a.dataset.date));
            sortedList = listRows.sort((a, b) => new Date(b.dataset.date) - new Date(a.dataset.date));
            sortedThumbnails = thumbnailRows.sort((a, b) => new Date(b.dataset.date) - new Date(a.dataset.date));
            break;
        case 'status-asc':
            sortedGrid = gridCards.sort((a, b) => {
                const aStatus = a.dataset.annotated === 'true' ? 0 : (a.dataset.preannotated === 'true' ? 1 : 2);
                const bStatus = b.dataset.annotated === 'true' ? 0 : (b.dataset.preannotated === 'true' ? 1 : 2);
                return aStatus - bStatus;  // Annotated (0) first, then Pre-annotated (1), then Not (2)
            });
            sortedList = listRows.sort((a, b) => {
                const aStatus = a.dataset.annotated === 'true' ? 0 : (a.dataset.preannotated === 'true' ? 1 : 2);
                const bStatus = b.dataset.annotated === 'true' ? 0 : (b.dataset.preannotated === 'true' ? 1 : 2);
                return aStatus - bStatus;
            });
            sortedThumbnails = thumbnailRows.sort((a, b) => {
                const aStatus = a.dataset.annotated === 'true' ? 0 : (a.dataset.preannotated === 'true' ? 1 : 2);
                const bStatus = b.dataset.annotated === 'true' ? 0 : (b.dataset.preannotated === 'true' ? 1 : 2);
                return aStatus - bStatus;
            });
            break;
        case 'status-desc':
            sortedGrid = gridCards.sort((a, b) => {
                const aStatus = a.dataset.annotated === 'true' ? 0 : (a.dataset.preannotated === 'true' ? 1 : 2);
                const bStatus = b.dataset.annotated === 'true' ? 0 : (b.dataset.preannotated === 'true' ? 1 : 2);
                return bStatus - aStatus;  // Not (2) first, then Pre-annotated (1), then Annotated (0)
            });
            sortedList = listRows.sort((a, b) => {
                const aStatus = a.dataset.annotated === 'true' ? 0 : (a.dataset.preannotated === 'true' ? 1 : 2);
                const bStatus = b.dataset.annotated === 'true' ? 0 : (b.dataset.preannotated === 'true' ? 1 : 2);
                return bStatus - aStatus;
            });
            sortedThumbnails = thumbnailRows.sort((a, b) => {
                const aStatus = a.dataset.annotated === 'true' ? 0 : (a.dataset.preannotated === 'true' ? 1 : 2);
                const bStatus = b.dataset.annotated === 'true' ? 0 : (b.dataset.preannotated === 'true' ? 1 : 2);
                return bStatus - aStatus;
            });
            break;
        default:
            return;
    }

    // Re-append sorted elements
    const gridContainer = document.getElementById('grid-thumbnails');
    gridContainer.innerHTML = '';
    sortedGrid.forEach(card => gridContainer.appendChild(card));

    const listBody = document.querySelector('#list-table tbody');
    listBody.innerHTML = '';
    sortedList.forEach(row => listBody.appendChild(row));

    const thumbnailsTbody = document.querySelector('.thumbnail-table tbody');
    thumbnailsTbody.innerHTML = '';
    sortedThumbnails.forEach(row => thumbnailsTbody.appendChild(row));

    // REMOVED: Reindexing loops - these override the database image_id with positional indices
    // document.querySelectorAll('#grid-thumbnails .grid-card').forEach((card, index) => { ... });
    // document.querySelectorAll('#list-table tbody tr').forEach((row, index) => { ... });
    // document.querySelectorAll('.thumbnail-row').forEach((row, index) => { ... });
}

export function toggleView(viewType) {
    if (viewType === 'grid') {
        document.getElementById('grid-thumbnails').style.display = 'grid';
        document.getElementById('list-table').style.display = 'none';
        document.getElementById('grid-toggle-btn').classList.add('active');
        document.getElementById('list-toggle-btn').classList.remove('active');
    } else {
        document.getElementById('grid-thumbnails').style.display = 'none';
        document.getElementById('list-table').style.display = 'table';
        document.getElementById('grid-toggle-btn').classList.remove('active');
        document.getElementById('list-toggle-btn').classList.add('active');
    }

    document.querySelectorAll('.image-checkbox').forEach(checkbox => {
        const path = checkbox.dataset.path;
        const otherViewCheckbox = document.querySelector(
            `.image-checkbox[data-path="${path}"]:not([checked="${checkbox.checked}"])`
        );
        if (otherViewCheckbox) {
            otherViewCheckbox.checked = checkbox.checked;
        }
    });
}