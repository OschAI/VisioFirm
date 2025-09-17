const CHUNK_SIZE = 10 * 1024 * 1024; // 10MB
const UPLOAD_TIMEOUT = 5000; // 5 seconds
const MAX_CONCURRENT_UPLOADS = 6; // Max 6 concurrent chunk uploads

// Helper function to upload a chunk with retries and timeout
async function uploadChunkWithRetry(formData, maxRetries = 5) {
    let timeoutCount = 0;
    for (let attempt = 0; attempt < maxRetries; attempt++) {
        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), UPLOAD_TIMEOUT);
            
            const response = await fetch('/upload_chunk', {
                method: 'POST',
                body: formData,
                signal: controller.signal
            });
            clearTimeout(timeoutId);
            
            const result = await response.json();
            if (result.success) {
                return result;
            }
            throw new Error(`Chunk upload failed: ${result.error || 'Unknown error'}`);
        } catch (error) {
            if (error.name === 'AbortError') {
                timeoutCount++;
                console.warn(`Chunk upload timed out on attempt ${attempt + 1} after ${UPLOAD_TIMEOUT/1000} seconds`);
                if (timeoutCount >= maxRetries) {
                    throw new Error('Upload failed after multiple timeouts. Server may be slow or unreachable.');
                }
            } else {
                console.warn(`Chunk upload error on attempt ${attempt + 1}: ${error.message}`);
            }
            if (attempt === maxRetries - 1) {
                throw error;
            }
            // Exponential backoff: 500ms, 1s, 2s
            await new Promise(resolve => setTimeout(resolve, 500 * Math.pow(2, attempt)));
            console.warn(`Retrying chunk upload, attempt ${attempt + 2}`);
        }
    }
}

// NEW: Helper for text-only POST (assembly)
async function postFormDataAsUrlEncoded(url, params, timeout = UPLOAD_TIMEOUT) {
    const formBody = new URLSearchParams(params).toString();
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeout);
    
    try {
        const response = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: formBody,
            signal: controller.signal
        });
        clearTimeout(timeoutId);
        return await response.json();
    } catch (error) {
        clearTimeout(timeoutId);
        if (error.name === 'AbortError') {
            throw new Error(`Request timed out after ${timeout/1000} seconds`);
        }
        throw error;
    }
}

export async function uploadFiles(files, endpoint, formDataExtras = {}, onProgress = () => {}) {
    const uploadId = generateUUID();
    const fileProgress = new Map();

    // Initialize progress tracking
    for (const file of files) {
        fileProgress.set(file.name, { uploaded: 0, total: file.size });
    }

    // Process files sequentially
    for (const file of files) {
        const fileId = generateUUID();
        const totalChunks = Math.ceil(file.size / CHUNK_SIZE) || 1;  // Ensure >=1 if size>0
        let startChunk = 0;

        if (file.size === 0) {
            console.warn(`Skipping empty file: ${file.name}`);
            continue;  // Skip empty annotations/images
        }

        // Check upload status to resume if possible
        try {
            const statusResponse = await fetch('/check_upload_status', {
                method: 'POST',
                headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                body: new URLSearchParams({ upload_id: uploadId, file_id: fileId })
            });
            const status = await statusResponse.json();
            startChunk = status.uploaded_chunks || 0;
            console.log(`Resuming upload for ${file.name} at chunk ${startChunk}/${totalChunks}`);
        } catch (error) {
            console.error(`Error checking upload status for ${file.name}:`, error);
            // Continue without resume
        }

        // Upload chunks with limited concurrency (use FormData for files)
        const chunkPromises = [];
        for (let i = startChunk; i < totalChunks; i++) {
            const start = i * CHUNK_SIZE;
            const end = Math.min(start + CHUNK_SIZE, file.size);
            const chunk = file.slice(start, end);
            const formData = new FormData();
            formData.append('chunk', chunk, file.name);
            formData.append('upload_id', uploadId);
            formData.append('file_id', fileId);
            formData.append('chunk_index', i.toString());  // Ensure string
            formData.append('filename', file.name);
            Object.entries(formDataExtras).forEach(([key, value]) => formData.append(key, value));

            chunkPromises.push(async () => {
                try {
                    await uploadChunkWithRetry(formData);
                    fileProgress.get(file.name).uploaded += (end - start);
                    onProgress(fileProgress);
                    console.log(`Uploaded chunk ${i}/${totalChunks} for ${file.name} (${(end - start)} bytes)`);
                } catch (error) {
                    console.error(`Failed to upload chunk ${i} for ${file.name}:`, error);
                    throw new Error(`Chunk ${i} upload failed for ${file.name}: ${error.message}`);
                }
            });
        }

        // Execute chunk uploads with limited concurrency
        for (let i = 0; i < chunkPromises.length; i += MAX_CONCURRENT_UPLOADS) {
            const batch = chunkPromises.slice(i, i + MAX_CONCURRENT_UPLOADS);
            await Promise.all(batch.map(task => task()));
        }

        // NEW: Assembly with URLSearchParams (text-only, avoids multipart parsing issues)
        if (totalChunks > 0) {  // Only if chunks were uploaded
            const assemblyParams = {
                upload_id: uploadId,
                file_id: fileId,
                total_chunks: totalChunks.toString(),  // Ensure string
                filename: file.name
                // Add file_hash if computed in future
            };
            console.log(`Assembling ${file.name} with params:`, assemblyParams);  // NEW: Debug log

            try {
                const result = await postFormDataAsUrlEncoded('/assemble_file', assemblyParams);
                if (!result.success) {
                    throw new Error(`File assembly failed for ${file.name}: ${result.error}`);
                }
                console.log(`Assembled file ${file.name} successfully`);
            } catch (error) {
                console.error(`Assembly failed for ${file.name}:`, error);
                throw error;
            }
        } else {
            console.warn(`No chunks to assemble for ${file.name} (size: ${file.size})`);
        }
    }

    return uploadId;
}

function generateUUID() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
        const r = Math.random() * 16 | 0, v = c === 'x' ? r : (r & 0x3 | 0x8);
        return v.toString(16);
    });
}

export function updateProgressBar(fileProgress, progressBar, progressElement) {
    let totalUploaded = 0;
    let totalSize = 0;

    for (const { uploaded, total } of fileProgress.values()) {
        totalUploaded += uploaded;
        totalSize += total;
    }

    const percentage = totalSize > 0 ? (totalUploaded / totalSize) * 100 : 0;
    progressElement.style.width = `${percentage}%`;
}