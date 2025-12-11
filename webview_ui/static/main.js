document.addEventListener("DOMContentLoaded", () => {
    const epubPathInput = document.getElementById("epub-path");
    const outputDirInput = document.getElementById("output-dir");
    const browseEpubBtn = document.getElementById("browse-epub");
    const browseOutputBtn = document.getElementById("browse-output");
    const chapterCountSpan = document.getElementById("chapter-count");
    const chapterTable = document.getElementById("chapter-table");
    const selectAllBtn = document.getElementById("select-all");
    const clearAllBtn = document.getElementById("clear-all");
    const selectAllCheckbox = document.getElementById("select-all-checkbox");
    const generateBtn = document.getElementById("generate-btn");
    const consoleOutput = document.getElementById("console-output");

    const bookTitleInfo = document.getElementById("book-title-info");
    const bookCoverText = document.getElementById("book-cover-text");
    const bookCoverImg = document.getElementById("book-cover-img");
    const bookAuthor = document.getElementById("book-author");
    const bookChapters = document.getElementById("book-chapters");
    const bookStatus = document.getElementById("book-status");

    let chapters = [];
    let pollInterval = null;
    let displayedLogs = new Set();

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

    browseEpubBtn.addEventListener("click", async () => {
        try {
            const response = await fetch("/api/select_epub", { method: "POST" });
            const data = await response.json();
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
            logToConsole(`Error selecting EPUB: ${error}`, "error");
        }
    });

    browseOutputBtn.addEventListener("click", async () => {
        try {
            const response = await fetch("/api/select_output_dir", { method: "POST" });
            const data = await response.json();
            if (data.error) {
                logToConsole(`Error: ${data.error}`, "error");
                return;
            }
            outputDirInput.value = data.output_dir;
            logToConsole(`Output directory set to: ${data.output_dir}`, "info");
        } catch (error) {
            logToConsole(`Error selecting output directory: ${error}`, "error");
        }
    });

    const updateChapterTable = () => {
        chapterTable.innerHTML = "";
        chapterCountSpan.textContent = chapters.length;
        chapters.forEach((chapter, index) => {
            const row = document.createElement("tr");
            row.className = "hover:bg-chapter-hover transition-colors group cursor-pointer";
            row.innerHTML = `
                <td class="py-1 px-1 text-center">
                    <input type="checkbox" class="rounded-none border-slate-600 chapter-checkbox" data-index="${index}" checked />
                </td>
                <td class="py-1 px-1 text-slate-300 group-hover:text-primary transition-colors">${chapter.title}</td>
                <td class="py-1 px-1 text-right text-slate-500 text-xs">${(chapter.size / 1024).toFixed(1)}k</td>
            `;
            chapterTable.appendChild(row);
        });
    };

    const updateBookInfo = (data) => {
        bookTitleInfo.textContent = data.title;
        bookCoverText.textContent = data.title;
        if (data.cover_image) {
            bookCoverImg.src = data.cover_image;
            bookCoverImg.classList.add("opacity-100");
        }
        bookAuthor.textContent = data.author;
        bookChapters.textContent = data.chapters.length;
        bookStatus.textContent = "READY";
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

    async function startPolling() {
        if (pollInterval) clearInterval(pollInterval);

        pollInterval = setInterval(async () => {
            try {
                const response = await fetch('/api/status');
                const data = await response.json();

                // Update progress display
                if (data.progress !== undefined) {
                    bookStatus.textContent = `GENERATING (${Math.round(data.progress)}%)`;
                }

                // Display new logs
                if (data.logs) {
                    data.logs.forEach(log => {
                        if (!displayedLogs.has(log.timestamp)) {
                            logToConsole(log.message, log.level);
                            displayedLogs.add(log.timestamp);
                        }
                    });
                }

                // Handle completion/error
                if (data.status === "completed") {
                    logToConsole(`Completed! Output: ${data.final_path}`, "success");
                    bookStatus.textContent = "COMPLETED";
                    bookStatus.className = "text-console-success font-medium";
                    stopPolling();
                } else if (data.status === "error") {
                    logToConsole(`Error: ${data.error}`, "error");
                    bookStatus.textContent = "ERROR";
                    bookStatus.className = "text-console-error font-medium";
                    stopPolling();
                } else if (data.status === "cancelled") {
                    logToConsole("Conversion cancelled", "warning");
                    bookStatus.textContent = "CANCELLED";
                    bookStatus.className = "text-console-warning font-medium";
                    stopPolling();
                }
            } catch (error) {
                console.error("Polling error:", error);
            }
        }, 1000); // Poll every 1 second
    }

    function stopPolling() {
        if (pollInterval) {
            clearInterval(pollInterval);
            pollInterval = null;
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

        // Clear previous logs
        displayedLogs.clear();

        try {
            const response = await fetch("/api/generate", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    chapters: selectedChapters,
                    output_dir: outputDirInput.value,
                    voice_prompt: "Male narrator voice in his 40s with an American accent. Warm baritone, calm pacing, clear diction."
                }),
            });
            const data = await response.json();
            if (data.status === "started") {
                logToConsole("Conversion started successfully", "success");
                startPolling();
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

    logToConsole("System initialized. Ready for command...", "info");
});
