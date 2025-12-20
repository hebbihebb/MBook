// Fallback API wrapper for browser access (when Electron API not available)
const API = {
    async apiRequest(url, options = {}) {
        if (window.electronAPI) {
            // Use Electron API if available
            return await window.electronAPI.apiRequest(url, options);
        } else {
            // Fallback to direct fetch for browser access
            const fetchOptions = {
                method: options.method || 'GET',
                headers: {
                    'Content-Type': 'application/json',
                }
            };

            // Add CSRF token header for non-GET requests
            const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
            if (csrfToken && fetchOptions.method !== 'GET') {
                fetchOptions.headers['X-CSRFToken'] = csrfToken;
            }

            if (options.body) {
                fetchOptions.body = JSON.stringify(options.body);
            }
            const response = await fetch(url, fetchOptions);
            return await response.json();
        }
    },
    async openFileDialog() {
        if (window.electronAPI) {
            return await window.electronAPI.openFileDialog();
        } else {
            // Browser fallback: prompt for file path
            return prompt('Enter EPUB file path:');
        }
    },
    async openFolderDialog() {
        if (window.electronAPI) {
            return await window.electronAPI.openFolderDialog();
        } else {
            // Browser fallback: prompt for folder path
            return prompt('Enter output directory path:');
        }
    }
};

document.addEventListener("DOMContentLoaded", () => {
    const epubPathInput = document.getElementById("epub-path");
    const outputDirInput = document.getElementById("output-dir");
    const serverOutputSelect = document.getElementById("server-output-select");
    const epubDropZone = document.getElementById("epub-drop-zone");
    const uploadOverlay = document.getElementById("upload-overlay");
    const browseEpubBtn = document.getElementById("browse-epub");
    const browseOutputBtn = document.getElementById("browse-output");
    const chapterCountSpan = document.getElementById("chapter-count");
    const chapterTable = document.getElementById("chapter-table");
    const selectAllBtn = document.getElementById("select-all");
    const clearAllBtn = document.getElementById("clear-all");
    const selectAllCheckbox = document.getElementById("select-all-checkbox");
    const generateBtn = document.getElementById("generate-btn");
    const pauseBtn = document.getElementById("pause-btn");
    const cancelBtn = document.getElementById("cancel-btn");
    const consoleOutput = document.getElementById("console-output");
    const voiceSelect = document.querySelector(".terminal-select");

    const bookTitleInfo = document.getElementById("book-title-info");
    const bookCoverText = document.getElementById("book-cover-text");
    const bookCoverImg = document.getElementById("book-cover-img");
    const bookAuthor = document.getElementById("book-author");
    const bookChapters = document.getElementById("book-chapters");
    const bookEstTime = document.getElementById("book-est-time");
    const bookStatus = document.getElementById("book-status");
    const progressBar = document.getElementById("progress-bar");
    const progressLabel = document.getElementById("progress-label");
    const chunkLabel = document.getElementById("chunk-label");

    // Preview elements
    const previewTitle = document.getElementById("preview-title");
    const previewSubtitle = document.getElementById("preview-subtitle");
    const previewContent = document.getElementById("preview-content");

    let chapters = [];
    let eventSource = null;
    let displayedLogs = new Set();
    let isPaused = false;

    const logToConsole = (message, level = "info") => {
        const timestamp = new Date().toLocaleTimeString();
        const levelColors = {
            info: "text-console-info",
            success: "text-console-success",
            warning: "text-console-warning",
            error: "text-console-error",
        };
        const color = levelColors[level] || "text-console-info";
        consoleOutput.innerHTML += `<div>[${timestamp}] <span class="${color}">${level.toUpperCase()}:</span> ${message}</div>`;
        consoleOutput.scrollTop = consoleOutput.scrollHeight;
    };

    // Load voice presets on page load
    async function loadVoicePresets() {
        try {
            const data = await API.apiRequest('/api/voice_presets', { method: 'GET' });

            voiceSelect.innerHTML = '';
            data.presets.forEach(preset => {
                const option = document.createElement('option');
                option.value = preset.id;  // Fixed: Use preset ID instead of prompt
                option.textContent = preset.label;
                voiceSelect.appendChild(option);
            });
        } catch (error) {
            logToConsole(`Failed to load voice presets: ${error}`, "error");
        }
    }

    // Load available output directories
    async function loadOutputDirs() {
        try {
            const data = await API.apiRequest('/api/get_output_dirs', { method: 'GET' });

            if (data.dirs && data.dirs.length > 0) {
                // Remove hidden class and hide manual input/button if running in browser/remote mode
                // For now, we'll just show the select if we get directories back
                if (!window.electronAPI) {
                    serverOutputSelect.classList.remove("hidden");
                    outputDirInput.classList.add("hidden");
                    browseOutputBtn.classList.add("hidden");

                    serverOutputSelect.innerHTML = '<option value="" disabled selected>Select server output directory...</option>';
                    data.dirs.forEach(dir => {
                        const option = document.createElement('option');
                        option.value = dir;
                        option.textContent = dir;
                        serverOutputSelect.appendChild(option);
                    });

                    // Add change listener
                    serverOutputSelect.addEventListener("change", () => {
                        outputDirInput.value = serverOutputSelect.value;
                        logToConsole(`Selected output directory: ${serverOutputSelect.value}`, "info");
                    });

                    // Select first one by default if available
                    if (data.dirs.length > 0) {
                        serverOutputSelect.value = data.dirs[0];
                        outputDirInput.value = data.dirs[0];
                    }
                }
            }
        } catch (error) {
            // endpoint might not exist yet or error
            // logToConsole(`Note: Server directories not available`, "info");
        }
    }

    // Function to load EPUB from filepath (used by both browse and manual entry)
    async function loadEpubFromPath(filepath) {
        try {
            const data = await API.apiRequest("/api/select_epub", {
                method: "POST",
                body: { filepath: filepath }
            });
            if (data.error) {
                logToConsole(`Error: ${data.error}`, "error");
                return;
            }
            epubPathInput.value = data.filepath;
            chapters = data.chapters;
            updateChapterTable();
            updateBookInfo(data);
            logToConsole(`Loaded ${data.chapters.length} chapters from ${data.title}`, "success");
        } catch (error) {
            logToConsole(`Error loading EPUB: ${error}`, "error");
        }
    }

    browseEpubBtn.addEventListener("click", async () => {
        try {
            // Use Electron's native file dialog
            const filepath = await API.openFileDialog();
            if (filepath) {
                logToConsole(`Loading EPUB from: ${filepath}`, "info");
                await loadEpubFromPath(filepath);
            }
        } catch (error) {
            logToConsole(`Error selecting EPUB: ${error}`, "error");
        }
    });

    // Handle manual path entry with Enter key for EPUB
    epubPathInput.addEventListener("keypress", async (e) => {
        if (e.key === "Enter") {
            const filepath = epubPathInput.value.trim();
            if (filepath && filepath !== "Type path or click Browse...") {
                logToConsole(`Loading EPUB from: ${filepath}`, "info");
                await loadEpubFromPath(filepath);
            }
        }
    });

    // Drag and Drop handlers
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        epubDropZone.addEventListener(eventName, preventDefaults, false);
    });

    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }

    ['dragenter', 'dragover'].forEach(eventName => {
        epubDropZone.addEventListener(eventName, highlight, false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
        epubDropZone.addEventListener(eventName, unhighlight, false);
    });

    function highlight(e) {
        epubDropZone.classList.add('drag-over');
    }

    function unhighlight(e) {
        epubDropZone.classList.remove('drag-over');
    }

    epubDropZone.addEventListener('drop', handleDrop, false);

    async function handleDrop(e) {
        const dt = e.dataTransfer;
        const files = dt.files;

        if (files.length > 0) {
            const file = files[0];
            if (file.name.toLowerCase().endsWith('.epub')) {
                await uploadFile(file);
            } else {
                logToConsole("Only EPUB files are allowed.", "error");
            }
        }
    }

    async function uploadFile(file) {
        // Show loading overlay
        uploadOverlay.classList.remove("hidden");

        const formData = new FormData();
        formData.append('file', file);

        try {
            logToConsole(`Uploading ${file.name}...`, "info");

            // Use fetch directly for file upload since it's multipart/form-data
            const response = await fetch('/api/upload_epub', {
                method: 'POST',
                body: formData
            });

            const data = await response.json();

            if (response.ok) {
                logToConsole("Upload complete.", "success");
                await loadEpubFromPath(data.filepath);
            } else {
                logToConsole(`Upload failed: ${data.error}`, "error");
            }
        } catch (error) {
            logToConsole(`Upload error: ${error}`, "error");
        } finally {
            uploadOverlay.classList.add("hidden");
        }
    }

    // Function to set output directory (used by both browse and manual entry)
    async function setOutputDirectory(dirpath) {
        try {
            const data = await API.apiRequest("/api/select_output_dir", {
                method: "POST",
                body: { output_dir: dirpath }
            });
            if (data.error) {
                logToConsole(`Error: ${data.error}`, "error");
                return;
            }
            outputDirInput.value = data.output_dir;
            logToConsole(`Output directory set to: ${data.output_dir}`, "info");
        } catch (error) {
            logToConsole(`Error setting output directory: ${error}`, "error");
        }
    }

    browseOutputBtn.addEventListener("click", async () => {
        try {
            // Use Electron's native folder dialog
            const dirpath = await API.openFolderDialog();
            if (dirpath) {
                logToConsole(`Setting output directory to: ${dirpath}`, "info");
                await setOutputDirectory(dirpath);
            }
        } catch (error) {
            logToConsole(`Error selecting output directory: ${error}`, "error");
        }
    });

    // Handle manual path entry with Enter key for output directory
    outputDirInput.addEventListener("keypress", async (e) => {
        if (e.key === "Enter") {
            const dirpath = outputDirInput.value.trim();
            if (dirpath && dirpath !== "Type path or click Browse...") {
                logToConsole(`Setting output directory to: ${dirpath}`, "info");
                await setOutputDirectory(dirpath);
            }
        }
    });

    // Function to load chapter preview
    async function loadChapterPreview(index) {
        try {
            const data = await API.apiRequest("/api/get_chapter_content", {
                method: "POST",
                body: { index: index }
            });

            if (data.error) {
                logToConsole(`Error loading preview: ${data.error}`, "error");
                return;
            }

            previewTitle.textContent = `CH ${index + 1}`;
            previewSubtitle.textContent = data.title;
            // Simple text formatting for preview
            previewContent.innerHTML = data.content
                .split('\n')
                .map(para => para.trim())
                .filter(para => para)
                .map(para => `<p class="mb-2">${para}</p>`)
                .join('');

        } catch (error) {
            logToConsole(`Failed to load preview: ${error}`, "error");
        }
    }

    const updateChapterTable = () => {
        chapterTable.innerHTML = "";
        chapterCountSpan.textContent = chapters.length;
        chapters.forEach((chapter, index) => {
            const row = document.createElement("tr");
            row.className = "hover:bg-chapter-hover transition-colors group cursor-pointer";
            row.innerHTML = `
                <td class="py-1 px-1 text-center" onclick="event.stopPropagation()">
                    <input type="checkbox" class="rounded-none border-slate-600 chapter-checkbox" data-index="${index}" checked />
                </td>
                <td class="py-1 px-1 text-slate-300 group-hover:text-primary transition-colors">${chapter.title}</td>
                <td class="py-1 px-1 text-right text-slate-500 text-xs">${(chapter.size / 1024).toFixed(1)}k</td>
            `;

            // Add click listener for preview
            row.addEventListener("click", () => {
                // Highlight active row
                document.querySelectorAll("#chapter-table tr").forEach(r => r.classList.remove("bg-surface-dark"));
                row.classList.add("bg-surface-dark");
                loadChapterPreview(index);
            });

            chapterTable.appendChild(row);
        });
    };

    const updateBookInfo = (data) => {
        bookTitleInfo.textContent = data.title;
        bookCoverText.textContent = data.title;
        if (data.cover_image) {
            // Add timestamp to bust cache and prepend server URL
            bookCoverImg.src = `http://127.0.0.1:5000${data.cover_image}?t=${new Date().getTime()}`;
            bookCoverImg.classList.add("opacity-100");
        }
        bookAuthor.textContent = data.author;
        bookChapters.textContent = data.chapters.length;
        if (data.estimated_hours) {
            bookEstTime.textContent = `~${data.estimated_hours} hr`;
        }
        bookStatus.textContent = "READY";
        progressLabel.textContent = "Idle";
        chunkLabel.textContent = "0 / 0";
        progressBar.style.width = "0%";
    };

    selectAllBtn.addEventListener("click", () => {
        document.querySelectorAll(".chapter-checkbox").forEach(cb => cb.checked = true);
        selectAllCheckbox.checked = true;
    });

    clearAllBtn.addEventListener("click", () => {
        document.querySelectorAll(".chapter-checkbox").forEach(cb => cb.checked = false);
        selectAllCheckbox.checked = false;
    });

    selectAllCheckbox.addEventListener("change", (e) => {
        document.querySelectorAll(".chapter-checkbox").forEach(cb => cb.checked = e.target.checked);
    });

    function startEventStream() {
        if (eventSource) {
            eventSource.close();
        }

        eventSource = new EventSource('/api/events');

        eventSource.onmessage = (e) => {
            const data = JSON.parse(e.data);

            if (data.event === "progress") {
                // Update progress display and chunk info
                const pct = data.progress !== undefined ? Math.round(data.progress) : 0;
                const current = data.current_chunk || 0;
                const total = data.total_chunks || 0;
                const statusText = data.status_text || "";
                progressBar.style.width = `${pct}%`;
                progressLabel.textContent = data.status === "running"
                    ? (statusText ? `${statusText}` : `Running (${pct}%)`)
                    : data.status?.toUpperCase() || "Idle";
                chunkLabel.textContent = total ? `${current} / ${total}` : `${current} / ?`;
                if (data.status === "running") {
                    bookStatus.textContent = `GENERATING (${pct}%)`;
                    bookStatus.className = "text-console-info font-medium";
                }

                // Sync pause button state
                if (data.status === "paused") {
                    isPaused = true;
                    pauseBtn.innerHTML = '<span class="material-symbols-outlined text-sm">play_arrow</span> RES';
                    bookStatus.textContent = "PAUSED";
                    bookStatus.className = "text-console-warning font-medium";
                } else if (data.status === "running" && isPaused) {
                    isPaused = false;
                    pauseBtn.innerHTML = '<span class="material-symbols-outlined text-sm">pause</span> PAU';
                }
            } else if (data.event === "log") {
                // Display new log
                if (!displayedLogs.has(data.timestamp)) {
                    logToConsole(data.message, data.level);
                    displayedLogs.add(data.timestamp);
                }
            } else if (data.event === "idle") {
                progressBar.style.width = "0%";
                progressLabel.textContent = "Idle";
                chunkLabel.textContent = "0 / 0";
            } else if (data.event === "completed") {
                logToConsole(`Completed! Output: ${data.final_path}`, "success");
                bookStatus.textContent = "COMPLETED";
                bookStatus.className = "text-console-success font-medium";
                progressBar.style.width = "100%";
                progressLabel.textContent = "Completed";
                stopEventStream();
            } else if (data.event === "error") {
                logToConsole(`Error: ${data.error}`, "error");
                bookStatus.textContent = "ERROR";
                bookStatus.className = "text-console-error font-medium";
                progressLabel.textContent = "Error";
                stopEventStream();
            } else if (data.event === "cancelled") {
                logToConsole("Conversion cancelled", "warning");
                bookStatus.textContent = "CANCELLED";
                bookStatus.className = "text-console-warning font-medium";
                progressLabel.textContent = "Cancelled";
                stopEventStream();
            }
        };

        eventSource.onerror = (error) => {
            console.error("SSE error:", error);
            stopEventStream();
        };
    }

    function stopEventStream() {
        if (eventSource) {
            eventSource.close();
            eventSource = null;
        }
    }

    generateBtn.addEventListener("click", async () => {
        const selectedChapters = [];
        document.querySelectorAll(".chapter-checkbox:checked").forEach(cb => {
            selectedChapters.push(chapters[cb.dataset.index]);
        });

        if (selectedChapters.length === 0) {
            logToConsole("No chapters selected for generation.", "warning");
            return;
        }

        if (!outputDirInput.value) {
            logToConsole("Please select an output directory first.", "warning");
            return;
        }

        logToConsole(`Starting generation of ${selectedChapters.length} chapters...`, "info");
        bookStatus.textContent = "STARTING...";
        bookStatus.className = "text-console-info font-medium";
        progressLabel.textContent = "Starting...";
        chunkLabel.textContent = "0 / ?";
        progressBar.style.width = "5%";

        // Clear previous logs
        displayedLogs.clear();

        // Reset pause state
        isPaused = false;
        pauseBtn.innerHTML = '<span class="material-symbols-outlined text-sm">pause</span> PAU';

        // Get selected voice preset ID
        const voicePresetId = voiceSelect.value;

        try {
            const data = await API.apiRequest("/api/generate", {
                method: "POST",
                body: {
                    chapters: selectedChapters,
                    output_dir: outputDirInput.value,
                    voice_preset_id: voicePresetId  // Fixed: Use correct parameter name
                }
            });
            if (data.status === "started") {
                logToConsole("Conversion started successfully", "success");
                startEventStream();
            } else if (data.error) {
                logToConsole(`Error: ${data.error}`, "error");
                bookStatus.textContent = "ERROR";
                bookStatus.className = "text-console-error font-medium";
            }
        } catch (error) {
            logToConsole(`Failed to start: ${error}`, "error");
            bookStatus.textContent = "ERROR";
            bookStatus.className = "text-console-error font-medium";
        }
    });

    pauseBtn.addEventListener("click", async () => {
        const action = isPaused ? "resume" : "pause";

        try {
            const data = await API.apiRequest("/api/pause", {
                method: "POST",
                body: { action }
            });

            if (data.status === "paused") {
                isPaused = true;
                pauseBtn.innerHTML = '<span class="material-symbols-outlined text-sm">play_arrow</span> RES';
                logToConsole("Conversion paused", "info");
                bookStatus.textContent = "PAUSED";
                bookStatus.className = "text-console-warning font-medium";
            } else if (data.status === "running") {
                isPaused = false;
                pauseBtn.innerHTML = '<span class="material-symbols-outlined text-sm">pause</span> PAU';
                logToConsole("Conversion resumed", "info");
                bookStatus.textContent = "RESUMING...";
                bookStatus.className = "text-console-info font-medium";
            }
        } catch (error) {
            logToConsole(`Failed to ${action}: ${error}`, "error");
        }
    });

    cancelBtn.addEventListener("click", async () => {
        if (!confirm("Cancel conversion? Progress will be saved and you can resume later.")) {
            return;
        }

        try {
            const data = await API.apiRequest("/api/cancel", { method: "POST" });

            if (data.status === "cancelling") {
                logToConsole("Cancellation requested...", "warning");
            }
        } catch (error) {
            logToConsole(`Failed to cancel: ${error}`, "error");
        }
    });

    // Load voice presets on startup
    loadVoicePresets();
    loadOutputDirs();

    logToConsole("System initialized. Ready for command...", "info");
});
