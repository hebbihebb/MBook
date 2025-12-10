"""
Maya1 Audiobook Converter - GUI

Full-featured GUI with:
- Chapter selection from EPUB TOC
- Cover preview
- Start/Pause/Cancel controls
- Crash-resume capability
- Voice prompt editor
- Progress and time estimates
"""

import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from ttkbootstrap.widgets.scrolled import ScrolledText
import threading
import os
import time
from datetime import datetime, timedelta
from PIL import Image, ImageTk
from io import BytesIO

# Import project modules
try:
    from epub_parser import parse_epub_with_chapters, get_cover_extension, ParsedEpub, Chapter
    from progress_manager import (
        ConversionProgress, save_progress, load_progress,
        has_resumable_job, get_resumable_info, cleanup_progress, cleanup_temp_chunks
    )
except ImportError as e:
    print(f"Warning: Missing dependencies: {e}")


class VoicePromptDialog(tk.Toplevel):
    """Dialog for editing the Maya1 voice prompt."""
    
    def __init__(self, parent, current_prompt: str):
        super().__init__(parent)
        self.title("Edit Voice Prompt")
        self.geometry("500x300")
        self.resizable(True, True)
        self.result = None
        
        # Make modal
        self.transient(parent)
        self.grab_set()
        
        # Instructions
        lbl = ttk.Label(
            self,
            text="Describe the voice characteristics for the narrator:",
            font=("Helvetica", 10)
        )
        lbl.pack(pady=(15, 5), padx=15, anchor=W)
        
        # Text area
        self.text = tk.Text(self, wrap=tk.WORD, height=10)
        self.text.pack(fill=BOTH, expand=True, padx=15, pady=5)
        self.text.insert("1.0", current_prompt)
        
        # Example hint
        hint = ttk.Label(
            self,
            text="Example: Male narrator voice in his 40s with an American accent. "
                 "Warm baritone, calm pacing, clear diction.",
            font=("Helvetica", 8),
            bootstyle="secondary"
        )
        hint.pack(pady=5, padx=15, anchor=W)
        
        # Buttons
        btn_frame = ttk.Frame(self)
        btn_frame.pack(pady=10)
        
        ttk.Button(btn_frame, text="Save", command=self.save, bootstyle="success").pack(side=LEFT, padx=5)
        ttk.Button(btn_frame, text="Cancel", command=self.cancel, bootstyle="secondary").pack(side=LEFT, padx=5)
        
        # Center on parent
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - self.winfo_width()) // 2
        y = parent.winfo_y() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")
        
    def save(self):
        self.result = self.text.get("1.0", tk.END).strip()
        self.destroy()
        
    def cancel(self):
        self.destroy()


class AudiobookApp(ttk.Window):
    """Main application window."""
    
    DEFAULT_VOICE_PROMPT = (
        "Male narrator voice in his 40s with an American accent. "
        "Warm baritone, calm pacing, clear diction, conversational delivery."
    )
    
    def __init__(self):
        super().__init__(themename="darkly")
        self.title("Maya1 Audiobook Converter")
        self.geometry("900x700")
        self.minsize(800, 600)
        
        # State variables
        self.epub_path = tk.StringVar()
        self.output_dir = tk.StringVar(value=os.path.expanduser("~/Audiobooks"))
        self.status_var = tk.StringVar(value="Ready")
        self.progress_var = tk.DoubleVar(value=0)
        self.elapsed_var = tk.StringVar(value="00:00:00")
        self.remaining_var = tk.StringVar(value="--:--:--")
        
        # Parsed EPUB data
        self.parsed_epub: ParsedEpub = None
        self.chapter_selection = {}  # chapter_order -> BooleanVar
        self.cover_photo = None  # Keep reference to prevent garbage collection
        
        # Conversion state
        self.voice_prompt = self.DEFAULT_VOICE_PROMPT
        self.conversion_thread = None
        self.cancel_event = threading.Event()
        self.pause_event = threading.Event()
        self.is_converting = False
        self.is_paused = False
        self.start_time = None
        self.timer_id = None
        
        # Resume state
        self.resumable_progress: ConversionProgress = None
        
        self.create_widgets()
        
    def create_widgets(self):
        """Build the complete GUI layout."""
        
        # ===== HEADER =====
        header_frame = ttk.Frame(self)
        header_frame.pack(fill=X, padx=20, pady=(15, 10))
        
        lbl_header = ttk.Label(
            header_frame,
            text="🎧 Maya1 Audiobook Generator",
            font=("Helvetica", 20, "bold"),
            bootstyle="primary"
        )
        lbl_header.pack(side=LEFT)
        
        # ===== FILE SELECTION =====
        file_frame = ttk.Frame(self)
        file_frame.pack(fill=X, padx=20, pady=5)
        
        # EPUB row
        ttk.Label(file_frame, text="EPUB:", width=8).grid(row=0, column=0, sticky=W, pady=3)
        ttk.Entry(file_frame, textvariable=self.epub_path, width=60).grid(row=0, column=1, padx=5, pady=3, sticky=EW)
        ttk.Button(file_frame, text="Browse", command=self.browse_epub, bootstyle="secondary-outline", width=10).grid(row=0, column=2, padx=5)
        
        # Output row
        ttk.Label(file_frame, text="Output:", width=8).grid(row=1, column=0, sticky=W, pady=3)
        ttk.Entry(file_frame, textvariable=self.output_dir, width=60).grid(row=1, column=1, padx=5, pady=3, sticky=EW)
        ttk.Button(file_frame, text="Browse", command=self.browse_output_dir, bootstyle="secondary-outline", width=10).grid(row=1, column=2, padx=5)
        
        file_frame.columnconfigure(1, weight=1)
        
        # ===== MAIN CONTENT AREA =====
        content_frame = ttk.Frame(self)
        content_frame.pack(fill=BOTH, expand=True, padx=20, pady=10)
        
        # Left panel: Chapter list
        left_frame = ttk.Labelframe(content_frame, text="📖 Chapters", padding=10)
        left_frame.pack(side=LEFT, fill=BOTH, expand=True, padx=(0, 10))
        
        # Select buttons
        btn_row = ttk.Frame(left_frame)
        btn_row.pack(fill=X, pady=(0, 5))
        ttk.Button(btn_row, text="☑ Select All", command=self.select_all_chapters, bootstyle="info-outline", width=12).pack(side=LEFT, padx=2)
        ttk.Button(btn_row, text="☐ Clear All", command=self.deselect_all_chapters, bootstyle="secondary-outline", width=12).pack(side=LEFT, padx=2)
        
        # Chapter treeview with checkboxes
        tree_frame = ttk.Frame(left_frame)
        tree_frame.pack(fill=BOTH, expand=True)
        
        self.chapter_tree = ttk.Treeview(
            tree_frame,
            columns=("selected", "title", "chars"),
            show="headings",
            selectmode="browse",
            height=12
        )
        self.chapter_tree.heading("selected", text="☑")
        self.chapter_tree.heading("title", text="Chapter")
        self.chapter_tree.heading("chars", text="Size")
        self.chapter_tree.column("selected", width=30, anchor=CENTER)
        self.chapter_tree.column("title", width=200)
        self.chapter_tree.column("chars", width=60, anchor=E)
        
        scrollbar = ttk.Scrollbar(tree_frame, orient=VERTICAL, command=self.chapter_tree.yview)
        self.chapter_tree.configure(yscrollcommand=scrollbar.set)
        
        self.chapter_tree.pack(side=LEFT, fill=BOTH, expand=True)
        scrollbar.pack(side=RIGHT, fill=Y)
        
        # Bind click to toggle checkbox
        self.chapter_tree.bind("<Button-1>", self.on_chapter_click)
        self.chapter_tree.bind("<<TreeviewSelect>>", self.on_chapter_select)
        
        # Right panel: Preview + Info + Cover
        right_frame = ttk.Frame(content_frame, width=320)
        right_frame.pack(side=RIGHT, fill=BOTH, padx=(10, 0))
        right_frame.pack_propagate(False)
        
        # Chapter preview
        preview_frame = ttk.Labelframe(right_frame, text="📄 Chapter Preview", padding=10)
        preview_frame.pack(fill=BOTH, expand=True, pady=(0, 10))
        
        self.preview_text = ScrolledText(preview_frame, height=8, wrap=tk.WORD, autohide=True)
        self.preview_text.pack(fill=BOTH, expand=True)
        
        # Info + Cover row
        info_cover_frame = ttk.Frame(right_frame)
        info_cover_frame.pack(fill=X)
        
        # Book info
        info_frame = ttk.Labelframe(info_cover_frame, text="📊 Info", padding=10)
        info_frame.pack(side=LEFT, fill=BOTH, expand=True, padx=(0, 5))
        
        self.info_author = ttk.Label(info_frame, text="Author: --", font=("Helvetica", 9))
        self.info_author.pack(anchor=W)
        self.info_chapters = ttk.Label(info_frame, text="Chapters: --", font=("Helvetica", 9))
        self.info_chapters.pack(anchor=W)
        self.info_selected = ttk.Label(info_frame, text="Selected: --", font=("Helvetica", 9))
        self.info_selected.pack(anchor=W)
        self.info_estimate = ttk.Label(info_frame, text="Est. Time: --", font=("Helvetica", 9))
        self.info_estimate.pack(anchor=W)
        
        # Cover image
        cover_frame = ttk.Labelframe(info_cover_frame, text="🖼 Cover", padding=5)
        cover_frame.pack(side=RIGHT, fill=Y, padx=(5, 0))
        
        self.cover_label = ttk.Label(cover_frame, text="No Cover", width=12)
        self.cover_label.pack()
        
        # ===== CONTROL BAR =====
        control_frame = ttk.Frame(self)
        control_frame.pack(fill=X, padx=20, pady=10)
        
        # Buttons
        btn_frame = ttk.Frame(control_frame)
        btn_frame.pack(side=LEFT)
        
        self.btn_start = ttk.Button(btn_frame, text="▶ Start", command=self.start_conversion, bootstyle="success", width=10)
        self.btn_start.pack(side=LEFT, padx=3)
        
        self.btn_pause = ttk.Button(btn_frame, text="⏸ Pause", command=self.pause_conversion, bootstyle="warning", width=10, state=DISABLED)
        self.btn_pause.pack(side=LEFT, padx=3)
        
        self.btn_cancel = ttk.Button(btn_frame, text="⏹ Cancel", command=self.cancel_conversion, bootstyle="danger", width=10, state=DISABLED)
        self.btn_cancel.pack(side=LEFT, padx=3)
        
        self.btn_voice = ttk.Button(btn_frame, text="⚙ Voice", command=self.edit_voice_prompt, bootstyle="info-outline", width=10)
        self.btn_voice.pack(side=LEFT, padx=10)
        
        # Progress bar
        self.progressbar = ttk.Progressbar(control_frame, variable=self.progress_var, maximum=100, bootstyle="striped", length=250)
        self.progressbar.pack(side=RIGHT, padx=10)
        
        # ===== STATUS BAR =====
        status_frame = ttk.Frame(self)
        status_frame.pack(fill=X, padx=20, pady=(0, 5))
        
        ttk.Label(status_frame, textvariable=self.status_var, font=("Helvetica", 10)).pack(side=LEFT)
        
        time_frame = ttk.Frame(status_frame)
        time_frame.pack(side=RIGHT)
        ttk.Label(time_frame, text="Elapsed:", font=("Helvetica", 9), bootstyle="secondary").pack(side=LEFT)
        ttk.Label(time_frame, textvariable=self.elapsed_var, font=("Helvetica", 9, "bold")).pack(side=LEFT, padx=(2, 15))
        ttk.Label(time_frame, text="Remaining:", font=("Helvetica", 9), bootstyle="secondary").pack(side=LEFT)
        ttk.Label(time_frame, textvariable=self.remaining_var, font=("Helvetica", 9, "bold")).pack(side=LEFT, padx=2)
        
        # ===== LOG PANEL (Collapsible) =====
        self.log_frame = ttk.Labelframe(self, text="▼ Log", padding=5)
        self.log_frame.pack(fill=X, padx=20, pady=(5, 15))
        
        self.log_text = ScrolledText(self.log_frame, height=5, wrap=tk.WORD, autohide=True)
        self.log_text.pack(fill=X)
        
    def browse_epub(self):
        """Open file dialog to select EPUB."""
        path = filedialog.askopenfilename(
            filetypes=[("EPUB Files", "*.epub"), ("All Files", "*.*")]
        )
        if path:
            self.epub_path.set(path)
            self.load_epub(path)
    
    def browse_output_dir(self):
        """Open directory dialog to select output location."""
        path = filedialog.askdirectory()
        if path:
            self.output_dir.set(path)
            self.check_resume()
    
    def load_epub(self, epub_path: str):
        """Parse EPUB and populate chapter list."""
        try:
            self.log(f"Loading: {os.path.basename(epub_path)}")
            self.parsed_epub = parse_epub_with_chapters(epub_path)
            
            # Clear existing items
            self.chapter_tree.delete(*self.chapter_tree.get_children())
            self.chapter_selection.clear()
            
            # Populate chapter list
            for chapter in self.parsed_epub.chapters:
                var = tk.BooleanVar(value=True)
                self.chapter_selection[chapter.order] = var
                
                # Format character count
                chars = len(chapter.content)
                if chars >= 1000:
                    char_str = f"{chars/1000:.1f}k"
                else:
                    char_str = str(chars)
                
                self.chapter_tree.insert(
                    "",
                    tk.END,
                    iid=str(chapter.order),
                    values=("☑", chapter.title, char_str)
                )
            
            # Update info panel
            self.info_author.config(text=f"Author: {self.parsed_epub.author}")
            self.info_chapters.config(text=f"Chapters: {len(self.parsed_epub.chapters)}")
            self.update_selection_info()
            
            # Load cover image
            self.load_cover_image()
            
            # Check for resumable conversion
            self.check_resume()
            
            self.log(f"Loaded {len(self.parsed_epub.chapters)} chapters")
            
        except Exception as e:
            self.log(f"Error loading EPUB: {e}")
            messagebox.showerror("Error", f"Failed to load EPUB:\n{e}")
    
    def load_cover_image(self):
        """Load and display cover image from EPUB."""
        if not self.parsed_epub or not self.parsed_epub.cover_image:
            self.cover_label.config(image="", text="No Cover")
            self.cover_photo = None
            return
        
        try:
            # Load image from bytes
            img_data = BytesIO(self.parsed_epub.cover_image)
            img = Image.open(img_data)
            
            # Resize to fit (max 100x150)
            img.thumbnail((100, 150), Image.Resampling.LANCZOS)
            
            self.cover_photo = ImageTk.PhotoImage(img)
            self.cover_label.config(image=self.cover_photo, text="")
            
        except Exception as e:
            self.log(f"Failed to load cover: {e}")
            self.cover_label.config(image="", text="No Cover")
            self.cover_photo = None
    
    def on_chapter_click(self, event):
        """Handle click on chapter list to toggle checkbox."""
        region = self.chapter_tree.identify_region(event.x, event.y)
        if region == "cell":
            column = self.chapter_tree.identify_column(event.x)
            item = self.chapter_tree.identify_row(event.y)
            
            if item and column == "#1":  # Clicked on checkbox column
                self.toggle_chapter(item)
    
    def toggle_chapter(self, item_id: str):
        """Toggle chapter selection."""
        order = int(item_id)
        if order in self.chapter_selection:
            var = self.chapter_selection[order]
            var.set(not var.get())
            
            # Update display
            current = self.chapter_tree.item(item_id, "values")
            new_check = "☑" if var.get() else "☐"
            self.chapter_tree.item(item_id, values=(new_check, current[1], current[2]))
            
            self.update_selection_info()
    
    def on_chapter_select(self, event):
        """Handle chapter selection to show preview."""
        selection = self.chapter_tree.selection()
        if not selection or not self.parsed_epub:
            return
        
        order = int(selection[0])
        for chapter in self.parsed_epub.chapters:
            if chapter.order == order:
                # Show first 500 chars
                preview = chapter.content[:500]
                if len(chapter.content) > 500:
                    preview += "..."
                
                self.preview_text.delete("1.0", tk.END)
                self.preview_text.insert("1.0", preview)
                break
    
    def select_all_chapters(self):
        """Select all chapters."""
        for order, var in self.chapter_selection.items():
            var.set(True)
            self.chapter_tree.item(str(order), values=(
                "☑",
                self.chapter_tree.item(str(order), "values")[1],
                self.chapter_tree.item(str(order), "values")[2]
            ))
        self.update_selection_info()
    
    def deselect_all_chapters(self):
        """Deselect all chapters."""
        for order, var in self.chapter_selection.items():
            var.set(False)
            self.chapter_tree.item(str(order), values=(
                "☐",
                self.chapter_tree.item(str(order), "values")[1],
                self.chapter_tree.item(str(order), "values")[2]
            ))
        self.update_selection_info()
    
    def update_selection_info(self):
        """Update the selection count and time estimate."""
        selected = [o for o, v in self.chapter_selection.items() if v.get()]
        self.info_selected.config(text=f"Selected: {len(selected)}")
        
        if not self.parsed_epub:
            self.info_estimate.config(text="Est. Time: --")
            return
        
        # Estimate based on selected chapters
        total_chars = 0
        for chapter in self.parsed_epub.chapters:
            if chapter.order in selected:
                total_chars += len(chapter.content)
        
        # Rough estimate: ~15 chars/second spoken
        estimated_seconds = total_chars / 15
        if estimated_seconds < 3600:
            est_str = f"~{int(estimated_seconds/60)} min"
        else:
            est_str = f"~{estimated_seconds/3600:.1f} hr"
        
        self.info_estimate.config(text=f"Est. Time: {est_str}")
    
    def check_resume(self):
        """Check if there's a resumable conversion."""
        epub = self.epub_path.get()
        output = self.output_dir.get()
        
        if not epub or not output:
            return
        
        if has_resumable_job(epub, output):
            info = get_resumable_info(output)
            if info:
                result = messagebox.askyesno(
                    "Resume Conversion?",
                    f"Found incomplete conversion:\n\n"
                    f"Progress: {info['completed']}/{info['total']} chunks\n"
                    f"Started: {info['started_at'][:19]}\n\n"
                    f"Resume from where you left off?"
                )
                if result:
                    self.resumable_progress = load_progress(output)
                    self.voice_prompt = info.get('voice_prompt', self.DEFAULT_VOICE_PROMPT)
                    self.log(f"Ready to resume from chunk {info['completed']}")
                else:
                    # User chose not to resume, clean up
                    cleanup_temp_chunks(output)
                    self.resumable_progress = None
    
    def edit_voice_prompt(self):
        """Open dialog to edit voice prompt."""
        dialog = VoicePromptDialog(self, self.voice_prompt)
        self.wait_window(dialog)
        
        if dialog.result is not None:
            self.voice_prompt = dialog.result
            self.log("Voice prompt updated")
    
    def start_conversion(self):
        """Start or resume the conversion."""
        if not self.epub_path.get():
            messagebox.showerror("Error", "Please select an EPUB file.")
            return
        
        if not self.output_dir.get():
            messagebox.showerror("Error", "Please select an output directory.")
            return
        
        selected = [o for o, v in self.chapter_selection.items() if v.get()]
        if not selected:
            messagebox.showerror("Error", "Please select at least one chapter.")
            return
        
        # Update UI state
        self.is_converting = True
        self.is_paused = False
        self.cancel_event.clear()
        self.pause_event.clear()
        
        self.btn_start.config(state=DISABLED)
        self.btn_pause.config(state=NORMAL)
        self.btn_cancel.config(state=NORMAL)
        self.btn_voice.config(state=DISABLED)
        
        # Start timer
        self.start_time = time.time()
        self.update_timer()
        
        # Run conversion in background thread
        self.conversion_thread = threading.Thread(
            target=self.run_conversion,
            args=(selected,),
            daemon=True
        )
        self.conversion_thread.start()
    
    def pause_conversion(self):
        """Toggle pause state."""
        if self.is_paused:
            # Resume
            self.is_paused = False
            self.pause_event.clear()
            self.btn_pause.config(text="⏸ Pause")
            self.log("Resuming...")
        else:
            # Pause (after current chunk)
            self.is_paused = True
            self.pause_event.set()
            self.btn_pause.config(text="▶ Resume")
            self.log("Pausing after current chunk...")
    
    def cancel_conversion(self):
        """Cancel the conversion."""
        if messagebox.askyesno("Cancel", "Cancel conversion?\n\nProgress will be saved for later resume."):
            self.cancel_event.set()
            self.log("Cancelling...")
    
    def run_conversion(self, selected_chapters: list):
        """Run the actual conversion (in background thread)."""
        try:
            self.update_status("Importing modules...")
            
            # Import heavy modules here to not slow down startup
            from convert_epub_to_audiobook import Maya1TTSEngine, clean_text, chunk_text_for_quality
            from assembler import stitch_audio_with_chapter_tracking, generate_chapter_metadata, export_m4b, create_audiobookshelf_folder
            import soundfile as sf
            
            epub_path = self.epub_path.get()
            output_dir = self.output_dir.get()
            os.makedirs(output_dir, exist_ok=True)
            
            temp_dir = os.path.join(output_dir, "temp_chunks")
            os.makedirs(temp_dir, exist_ok=True)
            
            # Prepare chunks from selected chapters
            self.update_status("Processing chapters...")
            
            all_chunks = []
            chunk_to_chapter = []
            chapter_titles = []
            
            for chapter in self.parsed_epub.chapters:
                if chapter.order not in selected_chapters:
                    continue
                
                chapter_titles.append(chapter.title)
                chapter_idx = len(chapter_titles) - 1
                
                cleaned = clean_text(chapter.content)
                chunks = chunk_text_for_quality(cleaned, max_words=50, min_words=15)
                
                for chunk in chunks:
                    all_chunks.append(chunk)
                    chunk_to_chapter.append(chapter_idx)
            
            total_chunks = len(all_chunks)
            self.log(f"Total chunks: {total_chunks}")
            
            # Check for resume
            start_idx = 0
            chunk_files = {}
            
            if self.resumable_progress:
                for idx, path in self.resumable_progress.chunk_files.items():
                    if os.path.exists(path):
                        chunk_files[idx] = path
                        start_idx = max(start_idx, idx + 1)
                
                self.log(f"Resuming from chunk {start_idx}")
                self.resumable_progress = None
            
            # Initialize progress
            progress = ConversionProgress(
                epub_path=epub_path,
                output_dir=output_dir,
                selected_chapters=selected_chapters,
                voice_prompt=self.voice_prompt,
                total_chunks=total_chunks,
                completed_chunks=list(chunk_files.keys()),
                chunk_files=chunk_files,
                chunk_to_chapter=chunk_to_chapter,
                chapter_titles=chapter_titles
            )
            
            # Load TTS engine
            self.update_status("Loading model...")
            self.update_progress(5)
            
            from convert_epub_to_audiobook import LOCAL_MODEL_DIR
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"
            
            engine = Maya1TTSEngine(LOCAL_MODEL_DIR, device)
            engine.load()
            
            self.log("Model loaded")
            self.update_status("Generating audio...")
            
            # Generate chunks
            for i in range(start_idx, total_chunks):
                if self.cancel_event.is_set():
                    save_progress(output_dir, progress)
                    self.log("Cancelled - progress saved")
                    break
                
                # Wait if paused
                while self.pause_event.is_set() and not self.cancel_event.is_set():
                    time.sleep(0.5)
                
                if self.cancel_event.is_set():
                    save_progress(output_dir, progress)
                    break
                
                chunk = all_chunks[i]
                chapter_title = chapter_titles[chunk_to_chapter[i]]
                
                self.update_status(f"Chunk {i+1}/{total_chunks} | {chapter_title}")
                
                try:
                    audio = engine.generate_audio(chunk, self.voice_prompt, max_duration_sec=60)
                    
                    if audio is not None and len(audio) > 0:
                        chunk_path = os.path.join(temp_dir, f"chunk_{i:04d}.wav")
                        sf.write(chunk_path, audio, 24000)
                        
                        progress.completed_chunks.append(i)
                        progress.chunk_files[i] = chunk_path
                        
                        # Save progress after each chunk
                        save_progress(output_dir, progress)
                    else:
                        self.log(f"Warning: Empty audio for chunk {i}")
                        
                except Exception as e:
                    self.log(f"Error on chunk {i}: {e}")
                
                # Update progress (10% to 85%)
                pct = 10 + (i / total_chunks) * 75
                self.update_progress(pct)
            
            # Check if cancelled
            if self.cancel_event.is_set():
                self.finish_conversion(False, "Cancelled")
                return
            
            # Stitch audio
            self.update_status("Stitching audio...")
            self.update_progress(86)
            
            audio_files = [progress.chunk_files[i] for i in sorted(progress.chunk_files.keys())]
            chunk_mapping = [chunk_to_chapter[i] for i in sorted(progress.chunk_files.keys())]
            
            output_wav, chapters_info = stitch_audio_with_chapter_tracking(
                audio_files,
                chunk_mapping,
                chapter_titles,
                output_path=os.path.join(output_dir, "temp_combined.wav")
            )
            
            # Generate chapters
            self.update_status("Adding chapters...")
            self.update_progress(90)
            
            chapters_file = generate_chapter_metadata(
                chapters_info,
                os.path.join(output_dir, "chapters.txt")
            )
            
            # Save cover
            cover_path = None
            if self.parsed_epub.cover_image:
                ext = get_cover_extension(self.parsed_epub.cover_media_type or "image/jpeg")
                cover_path = os.path.join(output_dir, f"temp_cover{ext}")
                with open(cover_path, 'wb') as f:
                    f.write(self.parsed_epub.cover_image)
            
            # Export M4B
            self.update_status("Exporting M4B...")
            self.update_progress(92)
            
            temp_m4b = os.path.join(output_dir, "temp_output.m4b")
            meta = {'title': self.parsed_epub.title, 'author': self.parsed_epub.author}
            
            export_m4b(output_wav, temp_m4b, metadata=meta, cover_art_path=cover_path, chapters_file=chapters_file)
            
            # Create Audiobookshelf folder
            self.update_status("Organizing files...")
            self.update_progress(95)
            
            final_path = create_audiobookshelf_folder(
                output_dir=output_dir,
                author=self.parsed_epub.author,
                title=self.parsed_epub.title,
                m4b_path=temp_m4b,
                cover_image_bytes=self.parsed_epub.cover_image,
                cover_extension=get_cover_extension(self.parsed_epub.cover_media_type or "image/jpeg")
            )
            
            # Cleanup
            self.update_status("Cleaning up...")
            self.update_progress(98)
            
            for path in audio_files:
                try:
                    os.remove(path)
                except:
                    pass
            
            for temp in [output_wav, chapters_file, cover_path]:
                if temp and os.path.exists(temp):
                    try:
                        os.remove(temp)
                    except:
                        pass
            
            try:
                os.rmdir(temp_dir)
            except:
                pass
            
            cleanup_progress(output_dir)
            
            self.update_progress(100)
            self.finish_conversion(True, final_path)
            
        except Exception as e:
            import traceback
            self.log(f"Error: {e}")
            traceback.print_exc()
            self.finish_conversion(False, str(e))
    
    def update_status(self, status: str):
        """Update status bar (thread-safe)."""
        self.after(0, lambda: self.status_var.set(status))
    
    def update_progress(self, value: float):
        """Update progress bar (thread-safe)."""
        self.after(0, lambda: self.progress_var.set(value))
    
    def log(self, message: str):
        """Add message to log (thread-safe)."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        def _log():
            self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
            self.log_text.see(tk.END)
        
        self.after(0, _log)
    
    def update_timer(self):
        """Update elapsed time display."""
        if not self.is_converting:
            return
        
        elapsed = time.time() - self.start_time
        elapsed_str = str(timedelta(seconds=int(elapsed)))
        self.elapsed_var.set(elapsed_str)
        
        # Estimate remaining time based on progress
        progress = self.progress_var.get()
        if progress > 10:  # Only estimate after initial loading
            total_estimated = elapsed / (progress / 100)
            remaining = total_estimated - elapsed
            remaining_str = str(timedelta(seconds=int(remaining)))
            self.remaining_var.set(f"~{remaining_str}")
        
        self.timer_id = self.after(1000, self.update_timer)
    
    def finish_conversion(self, success: bool, message: str):
        """Called when conversion finishes (thread-safe)."""
        def _finish():
            self.is_converting = False
            self.is_paused = False
            
            # Stop timer
            if self.timer_id:
                self.after_cancel(self.timer_id)
                self.timer_id = None
            
            # Reset UI
            self.btn_start.config(state=NORMAL)
            self.btn_pause.config(state=DISABLED, text="⏸ Pause")
            self.btn_cancel.config(state=DISABLED)
            self.btn_voice.config(state=NORMAL)
            
            if success:
                self.status_var.set("Complete!")
                self.log(f"Audiobook saved: {message}")
                messagebox.showinfo("Success", f"Audiobook saved to:\n{message}")
            else:
                self.status_var.set("Stopped")
                if "Cancel" not in message:
                    messagebox.showerror("Error", message)
        
        self.after(0, _finish)


if __name__ == "__main__":
    app = AudiobookApp()
    app.mainloop()
