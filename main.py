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
import json
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
    from voice_presets import (
        DEFAULT_VOICE_PROMPT as DEFAULT_VOICE_PROMPT_TEXT,
        VOICE_PRESETS,
        get_voice_preset,
        validate_voice_preset,
    )
except ImportError as e:
    print(f"Warning: Missing dependencies: {e}")
    DEFAULT_VOICE_PROMPT_TEXT = ""
    VOICE_PRESETS = []
    def get_voice_preset(_voice_id: str) -> dict:
        raise ValueError("Voice presets unavailable")
    def validate_voice_preset(_voice_id: str) -> dict:
        raise ValueError("Voice presets unavailable")

# Check for optional batch processing support
# NOTE: Batch mode is DISABLED as of 2024-12-10
# Reason: lmdeploy 0.11.0 CUDA kernels don't support Blackwell GPUs (RTX 50 series, sm_120)
# Error: "no kernel image is available for execution on the device"
# Re-enable when lmdeploy releases updated pre-built wheels with Blackwell support.
# To re-enable: set BATCH_MODE_AVAILABLE = is_lmdeploy_available() below
BATCH_MODE_AVAILABLE = False  # Disabled - see note above
# try:
#     from fast_maya_engine import is_lmdeploy_available
#     BATCH_MODE_AVAILABLE = is_lmdeploy_available()
# except ImportError:
#     BATCH_MODE_AVAILABLE = False


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
        result = self.text.get("1.0", tk.END).strip()

        # Validate voice prompt
        if not result:
            import tkinter.messagebox as messagebox
            messagebox.showwarning("Invalid Input", "Voice prompt cannot be empty.")
            return

        if len(result) > 1000:
            import tkinter.messagebox as messagebox
            messagebox.showwarning("Invalid Input", "Voice prompt is too long (max 1000 characters).")
            return

        self.result = result
        self.destroy()
        
    def cancel(self):
        self.destroy()


class AudiobookApp(ttk.Window):
    """Main application window."""

    SETTINGS_PATH = os.path.join(os.path.expanduser("~"), ".mbook_settings.json")
    
    DEFAULT_VOICE_PROMPT = DEFAULT_VOICE_PROMPT_TEXT
    
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
        self.progress_detail_var = tk.StringVar(value="Idle")
        self.chunk_progress_var = tk.StringVar(value="0 / 0")
        
        # New: Selection info string
        self.info_selected_var = tk.StringVar(value="0 selected")
        
        # Parsed EPUB data
        self.parsed_epub: ParsedEpub = None
        self.chapter_selection = {}  # chapter_order -> BooleanVar
        self.cover_photo = None  # Keep reference to prevent garbage collection
        
        # Conversion state
        self.voice_prompt = self.DEFAULT_VOICE_PROMPT
        self.voice_preset_id = tk.StringVar()
        self.voice_detail_label_var = tk.StringVar(value="Voice Prompt:")
        self.voice_detail_var = tk.StringVar(value="")
        self.reference_audio_var = tk.StringVar(value="")
        self.reference_audio_custom = False
        self.conversion_thread = None
        self.cancel_event = threading.Event()
        self.pause_event = threading.Event()
        self.is_converting = False
        self.is_paused = False
        self.start_time = None
        self.timer_id = None
        
        # Resume state
        self.resumable_progress: ConversionProgress = None
        
        # Batch processing state
        self.use_batch_mode = tk.BooleanVar(value=False)
        self.batch_size_var = tk.IntVar(value=4)  # Process 4 chunks at a time
        
        self.create_widgets()
        self.init_voice_presets()
        self.load_settings()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        
    def create_widgets(self):
        """Build the complete GUI layout."""
        
        # ===== HEADER =====
        # Cleaner header with better spacing
        header_frame = ttk.Frame(self)
        header_frame.pack(fill=X, padx=20, pady=(20, 15))
        
        lbl_header = ttk.Label(
            header_frame,
            text="🎧 Maya1 Audiobook Converter",
            font=("Segoe UI", 24, "bold"),
            bootstyle="primary"
        )
        lbl_header.pack(side=LEFT)
        
        # ===== PROJECT SETUP =====
        # Group file controls into a clean section
        setup_frame = ttk.Labelframe(self, text="Project Setup", padding=15)
        setup_frame.pack(fill=X, padx=20, pady=(0, 15))
        
        # Grid layout for setup
        setup_frame.columnconfigure(1, weight=1)
        
        # Row 0: EPUB Input
        ttk.Label(setup_frame, text="EPUB File:", font=("Segoe UI", 10)).grid(row=0, column=0, sticky=W, pady=5)
        ttk.Entry(setup_frame, textvariable=self.epub_path).grid(row=0, column=1, sticky=EW, padx=10, pady=5)
        ttk.Button(setup_frame, text="📂 Browse", command=self.browse_epub, bootstyle="secondary-outline").grid(row=0, column=2, padx=5)
        
        # Row 1: Output Directory
        ttk.Label(setup_frame, text="Output Folder:", font=("Segoe UI", 10)).grid(row=1, column=0, sticky=W, pady=5)
        ttk.Entry(setup_frame, textvariable=self.output_dir).grid(row=1, column=1, sticky=EW, padx=10, pady=5)
        ttk.Button(setup_frame, text="📂 Browse", command=self.browse_output_dir, bootstyle="secondary-outline").grid(row=1, column=2, padx=5)

        # Row 2: Voice Preset
        ttk.Label(setup_frame, text="Voice Preset:", font=("Segoe UI", 10)).grid(row=2, column=0, sticky=W, pady=5)
        self.voice_preset_combo = ttk.Combobox(setup_frame, state="readonly")
        self.voice_preset_combo.grid(row=2, column=1, sticky=EW, padx=10, pady=5)
        self.btn_voice_edit = ttk.Button(
            setup_frame,
            text="✎ Edit Prompt",
            command=self.edit_voice_prompt,
            bootstyle="info-outline"
        )
        self.btn_voice_edit.grid(row=2, column=2, padx=5)

        # Row 3: Voice Details
        ttk.Label(setup_frame, textvariable=self.voice_detail_label_var, font=("Segoe UI", 10)).grid(row=3, column=0, sticky=W, pady=5)
        ttk.Entry(setup_frame, textvariable=self.voice_detail_var, state="readonly").grid(row=3, column=1, sticky=EW, padx=10, pady=5)
        self.btn_reference_browse = ttk.Button(
            setup_frame,
            text="🎧 Browse",
            command=self.browse_reference_audio,
            bootstyle="secondary-outline"
        )
        self.btn_reference_browse.grid(row=3, column=2, padx=5)
        
        # ===== MAIN CONTENT =====
        # Split view: Chapters (Left) vs Details (Right)
        content_frame = ttk.Frame(self)
        content_frame.pack(fill=BOTH, expand=True, padx=20, pady=5)
        
        # --- Right Panel: Book Details & Preview ---
        # Pack Right Panel FIRST to ensure it reserves space
        right_panel = ttk.Frame(content_frame, width=350)
        right_panel.pack(side=RIGHT, fill=BOTH)
        right_panel.pack_propagate(False)
        
        # 1. Book Info Card
        info_card = ttk.Labelframe(right_panel, text="Book Details", padding=10)
        info_card.pack(fill=X, pady=(0, 15))
        
        # Inner layout for Info Card
        info_inner = ttk.Frame(info_card)
        info_inner.pack(fill=X)
        
        # Cover Image (Left side of card)
        self.cover_label = ttk.Label(info_inner, text="No Cover\nPreview", relief="flat", anchor=CENTER, foreground="#888")
        self.cover_label.pack(side=LEFT, padx=(0, 15))
        
        # Stats (Right side of card)
        stats_frame = ttk.Frame(info_inner)
        stats_frame.pack(side=LEFT, fill=BOTH, expand=True)
        
        self.lbl_author = ttk.Label(stats_frame, text="Unknown Author", font=("Segoe UI", 11, "bold"))
        self.lbl_author.pack(anchor=W, pady=(0, 5))
        
        self.lbl_chapter_count = ttk.Label(stats_frame, text="0 Chapters", font=("Segoe UI", 9))
        self.lbl_chapter_count.pack(anchor=W)
        
        self.lbl_est_time = ttk.Label(stats_frame, text="Est. Time: --", font=("Segoe UI", 9), bootstyle="info")
        self.lbl_est_time.pack(anchor=W, pady=(5, 0))

        # 2. Text Preview
        preview_frame = ttk.Labelframe(right_panel, text="Text Preview", padding=10)
        preview_frame.pack(fill=BOTH, expand=True)
        
        self.preview_text = ScrolledText(preview_frame, height=10, wrap=tk.WORD, autohide=True, font=("Consolas", 9))
        self.preview_text.pack(fill=BOTH, expand=True)

        # --- Left Panel: Chapters ---
        left_panel = ttk.Labelframe(content_frame, text="Chapter Selection", padding=10)
        left_panel.pack(side=LEFT, fill=BOTH, expand=True, padx=(0, 10))
        
        # Toolbar for chapters
        toolbar = ttk.Frame(left_panel)
        toolbar.pack(fill=X, pady=(0, 5))
        
        ttk.Button(toolbar, text="✓ All", command=self.select_all_chapters, bootstyle="link", width=6).pack(side=LEFT)
        ttk.Button(toolbar, text="✗ None", command=self.deselect_all_chapters, bootstyle="link", width=6).pack(side=LEFT)
        ttk.Label(toolbar, textvariable=self.info_selected_var, font=("Segoe UI", 9), bootstyle="secondary").pack(side=RIGHT)
        
        # Treeview
        tree_frame = ttk.Frame(left_panel)
        tree_frame.pack(fill=BOTH, expand=True)
        
        self.chapter_tree = ttk.Treeview(
            tree_frame,
            columns=("selected", "title", "chars"),
            show="headings",
            selectmode="browse",
            height=10,
            bootstyle="primary"
        )
        self.chapter_tree.heading("selected", text="✓")
        self.chapter_tree.heading("title", text="Chapter Title")
        self.chapter_tree.heading("chars", text="Length")
        
        self.chapter_tree.column("selected", width=40, anchor=CENTER)
        self.chapter_tree.column("title", width=250)
        self.chapter_tree.column("chars", width=80, anchor=E)
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(tree_frame, orient=VERTICAL, command=self.chapter_tree.yview)
        self.chapter_tree.configure(yscrollcommand=scrollbar.set)
        
        self.chapter_tree.pack(side=LEFT, fill=BOTH, expand=True)
        scrollbar.pack(side=RIGHT, fill=Y)
        
        self.chapter_tree.bind("<Button-1>", self.on_chapter_click)
        self.chapter_tree.bind("<<TreeviewSelect>>", self.on_chapter_select)
        
        # ===== CONTROL BAR =====
        control_panel = ttk.Frame(self)
        control_panel.pack(fill=X, padx=20, pady=15)
        
        # Top Row: Progress
        progress_frame = ttk.Frame(control_panel)
        progress_frame.pack(fill=X, pady=(0, 10))
        
        # Status Label & Time
        status_row = ttk.Frame(progress_frame)
        status_row.pack(fill=X, pady=(0, 5))
        ttk.Label(status_row, textvariable=self.status_var, font=("Segoe UI", 10, "italic")).pack(side=LEFT)
        
        time_display = ttk.Frame(status_row)
        time_display.pack(side=RIGHT)
        ttk.Label(time_display, text="Elapsed: ", bootstyle="secondary").pack(side=LEFT)
        ttk.Label(time_display, textvariable=self.elapsed_var, font=("Segoe UI", 10, "bold")).pack(side=LEFT, padx=(0, 15))
        ttk.Label(time_display, text="Remaining: ", bootstyle="secondary").pack(side=LEFT)
        ttk.Label(time_display, textvariable=self.remaining_var, font=("Segoe UI", 10, "bold"), bootstyle="warning").pack(side=LEFT)
        
        # The Bar
        self.progressbar = ttk.Progressbar(progress_frame, variable=self.progress_var, maximum=100, bootstyle="striped-success", length=200)
        self.progressbar.pack(fill=X)

        detail_row = ttk.Frame(progress_frame)
        detail_row.pack(fill=X, pady=(4, 0))
        ttk.Label(detail_row, textvariable=self.progress_detail_var, font=("Segoe UI", 9), bootstyle="secondary").pack(side=LEFT)
        ttk.Label(detail_row, textvariable=self.chunk_progress_var, font=("Segoe UI", 9), bootstyle="secondary").pack(side=RIGHT)
        
        # Bottom Row: Buttons
        btn_frame = ttk.Frame(control_panel)
        btn_frame.pack(fill=X)
        
        # Main Action Button (Big)
        self.btn_start = ttk.Button(btn_frame, text="▶ START CONVERSION", command=self.start_conversion, bootstyle="success", width=25)
        self.btn_start.pack(side=LEFT)
        
        ttk.Separator(btn_frame, orient=VERTICAL).pack(side=LEFT, fill=Y, padx=20)
        
        # Transport Controls
        self.btn_pause = ttk.Button(btn_frame, text="⏸ Pause", command=self.pause_conversion, state=DISABLED, bootstyle="warning-outline", width=10)
        self.btn_pause.pack(side=LEFT, padx=5)
        
        self.btn_cancel = ttk.Button(btn_frame, text="⏹ Cancel", command=self.cancel_conversion, state=DISABLED, bootstyle="danger-outline", width=10)
        self.btn_cancel.pack(side=LEFT, padx=5)
        
        # Batch mode checkbox (only show if lmdeploy available)
        if BATCH_MODE_AVAILABLE:
            self.chk_batch = ttk.Checkbutton(
                btn_frame,
                text="⚡ Batch Mode",
                variable=self.use_batch_mode,
                bootstyle="success-round-toggle"
            )
            self.chk_batch.pack(side=RIGHT, padx=15)
            
            # Tooltip-like label
            ttk.Label(btn_frame, text="(Faster)", font=("Segoe UI", 8), bootstyle="secondary").pack(side=RIGHT)
        
        # ===== LOG PANEL =====
        self.log_expander = ttk.Labelframe(self, text="Log Output", padding=5)
        self.log_expander.pack(fill=X, padx=20, pady=(0, 20))

        log_controls = ttk.Frame(self.log_expander)
        log_controls.pack(fill=X, padx=5, pady=(0, 5))
        ttk.Button(log_controls, text="📋 Copy Log", command=self.copy_log, bootstyle="secondary-outline").pack(side=LEFT)
        ttk.Button(log_controls, text="📂 Open Output Folder", command=self.open_output_folder, bootstyle="secondary-outline").pack(side=LEFT, padx=5)
        
        self.log_text = ScrolledText(self.log_expander, height=6, wrap=tk.WORD, autohide=True, font=("Consolas", 8))
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

    def load_settings(self):
        """Load persisted UI settings."""
        if not os.path.exists(self.SETTINGS_PATH):
            return
        try:
            with open(self.SETTINGS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return

        epub_path = data.get("epub_path")
        if epub_path and os.path.exists(epub_path):
            self.epub_path.set(epub_path)
            self.load_epub(epub_path)

        output_dir = data.get("output_dir")
        if output_dir and os.path.isdir(output_dir):
            self.output_dir.set(output_dir)

        self.voice_prompt = data.get("voice_prompt", self.voice_prompt)
        ref_audio = data.get("reference_audio")
        if ref_audio:
            self.reference_audio_var.set(ref_audio)
        self.reference_audio_custom = bool(data.get("reference_audio_custom", False))

        voice_preset_id = data.get("voice_preset_id")
        if voice_preset_id:
            try:
                self.apply_voice_preset(voice_preset_id, keep_prompt=True)
            except ValueError:
                pass

    def save_settings(self):
        """Persist UI settings to disk."""
        data = {
            "epub_path": self.epub_path.get(),
            "output_dir": self.output_dir.get(),
            "voice_preset_id": self.voice_preset_id.get(),
            "voice_prompt": self.voice_prompt,
            "reference_audio": self.reference_audio_var.get(),
            "reference_audio_custom": self.reference_audio_custom,
        }
        try:
            with open(self.SETTINGS_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except OSError:
            pass

    def on_close(self):
        """Save settings before closing the app."""
        self.save_settings()
        self.destroy()
    
    def load_epub(self, epub_path: str):
        """Parse EPUB and populate chapter list."""
        try:
            self.log(f"Loading: {os.path.basename(epub_path)}")

            # Validate EPUB file
            if not os.path.exists(epub_path):
                raise FileNotFoundError(f"EPUB file not found: {epub_path}")

            if not os.access(epub_path, os.R_OK):
                raise PermissionError(f"Cannot read EPUB file (permission denied): {epub_path}")

            # Check file size (warn if > 100MB, fail if > 500MB)
            file_size_mb = os.path.getsize(epub_path) / (1024 * 1024)
            if file_size_mb > 500:
                raise ValueError(f"EPUB file too large ({file_size_mb:.1f}MB). Maximum supported size is 500MB.")
            elif file_size_mb > 100:
                self.log(f"Warning: Large EPUB file ({file_size_mb:.1f}MB) may take longer to process")

            # Validate it's actually an EPUB file (basic check)
            if not epub_path.lower().endswith('.epub'):
                self.log("Warning: File does not have .epub extension, attempting to parse anyway")

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
            self.lbl_author.config(text=f"{self.parsed_epub.author}")
            self.lbl_chapter_count.config(text=f"{len(self.parsed_epub.chapters)} Chapters")
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
        self.info_selected_var.set(f"{len(selected)} selected")
        
        if not self.parsed_epub:
            self.lbl_est_time.config(text="Est. Time: --")
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
        
        self.lbl_est_time.config(text=f"Est. Time: {est_str}")
    
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
                    voice_preset_id = info.get('voice_preset_id') or self.voice_preset_id.get()
                    try:
                        preset = get_voice_preset(voice_preset_id)
                        if preset.get("engine") == "chatterbox" and info.get("voice_prompt"):
                            self.reference_audio_var.set(info.get("voice_prompt"))
                            self.reference_audio_custom = True
                    except ValueError:
                        pass
                    self.apply_voice_preset(voice_preset_id, keep_prompt=True)
                    self.log(f"Ready to resume from chunk {info['completed']}")
                else:
                    # User chose not to resume, clean up
                    cleanup_temp_chunks(output)
                    self.resumable_progress = None

    def init_voice_presets(self):
        """Initialize voice preset UI and defaults."""
        self.voice_preset_ids = [p["id"] for p in VOICE_PRESETS]
        self.voice_preset_labels = [p["label"] for p in VOICE_PRESETS]
        self.voice_preset_combo.configure(values=self.voice_preset_labels)
        if self.voice_preset_labels:
            self.voice_preset_combo.current(0)
            self.apply_voice_preset(self.voice_preset_ids[0], keep_prompt=False)
        self.voice_preset_combo.bind("<<ComboboxSelected>>", self.on_voice_preset_change)

    def on_voice_preset_change(self, _event=None):
        """Update voice config when a new preset is selected."""
        label = self.voice_preset_combo.get()
        if label in self.voice_preset_labels:
            idx = self.voice_preset_labels.index(label)
            self.apply_voice_preset(self.voice_preset_ids[idx], keep_prompt=False)

    def apply_voice_preset(self, preset_id: str, keep_prompt: bool):
        """Apply preset settings to the UI and internal state."""
        preset = get_voice_preset(preset_id)
        self.voice_preset_id.set(preset_id)
        if preset_id in getattr(self, "voice_preset_ids", []):
            idx = self.voice_preset_ids.index(preset_id)
            if self.voice_preset_combo.current() != idx:
                self.voice_preset_combo.current(idx)

        engine = preset.get("engine", "maya1")

        if engine == "maya1":
            self.voice_detail_label_var.set("Voice Prompt:")
            if not keep_prompt:
                self.voice_prompt = preset.get("prompt", self.DEFAULT_VOICE_PROMPT)
            self.voice_detail_var.set(self._truncate_prompt(self.voice_prompt))
            self.btn_voice_edit.config(state=NORMAL)
            self.btn_reference_browse.config(state=DISABLED)
        else:
            self.voice_detail_label_var.set("Reference Audio:")
            if not keep_prompt:
                self.reference_audio_custom = False
                self.reference_audio_var.set(preset.get("reference_audio", ""))
            elif not self.reference_audio_var.get():
                self.reference_audio_var.set(preset.get("reference_audio", ""))
            self.voice_detail_var.set(self.reference_audio_var.get())
            self.btn_voice_edit.config(state=DISABLED)
            self.btn_reference_browse.config(state=NORMAL)

    def browse_reference_audio(self):
        """Pick a reference audio file for Chatterbox."""
        path = filedialog.askopenfilename(
            title="Select reference audio",
            filetypes=[("Audio files", "*.wav *.mp3 *.flac"), ("All Files", "*.*")]
        )
        if path:
            self.reference_audio_var.set(path)
            self.voice_detail_var.set(path)
            self.reference_audio_custom = True
            self.log("Reference audio updated")

    def _truncate_prompt(self, prompt: str, limit: int = 80) -> str:
        prompt = prompt.strip()
        if len(prompt) <= limit:
            return prompt
        return prompt[:limit - 3].rstrip() + "..."

    def set_voice_controls_state(self, state: str):
        """Enable or disable voice controls based on engine type."""
        combo_state = "readonly" if state != "disabled" else "disabled"
        self.voice_preset_combo.config(state=combo_state)
        button_state = NORMAL if state != "disabled" else DISABLED
        if self.voice_preset_id.get():
            try:
                preset = get_voice_preset(self.voice_preset_id.get())
            except ValueError:
                self.btn_voice_edit.config(state=DISABLED)
                self.btn_reference_browse.config(state=DISABLED)
                return
            if preset.get("engine") == "maya1":
                self.btn_voice_edit.config(state=button_state)
                self.btn_reference_browse.config(state=DISABLED)
            else:
                self.btn_voice_edit.config(state=DISABLED)
                self.btn_reference_browse.config(state=button_state)
    
    def edit_voice_prompt(self):
        """Open dialog to edit voice prompt."""
        dialog = VoicePromptDialog(self, self.voice_prompt)
        self.wait_window(dialog)
        
        if dialog.result is not None:
            self.voice_prompt = dialog.result
            self.voice_detail_var.set(self._truncate_prompt(self.voice_prompt))
            self.log("Voice prompt updated")
    
    def start_conversion(self):
        """Start or resume the conversion."""
        if not self.epub_path.get():
            messagebox.showerror("Error", "Please select an EPUB file.")
            return
        
        if not self.output_dir.get():
            messagebox.showerror("Error", "Please select an output directory.")
            return

        if not self.voice_preset_id.get():
            messagebox.showerror("Error", "No voice preset selected.")
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
        self.set_voice_controls_state("disabled")
        self.progress_detail_var.set("Starting...")
        self.chunk_progress_var.set("0 / ?")
        
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
            self.progress_detail_var.set("Running")
            self.log("Resuming...")
        else:
            # Pause (after current chunk)
            self.is_paused = True
            self.pause_event.set()
            self.btn_pause.config(text="▶ Resume")
            self.progress_detail_var.set("Paused")
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

            # Create and validate output directory
            os.makedirs(output_dir, exist_ok=True)

            # Test if directory is writable
            test_file = os.path.join(output_dir, ".write_test")
            try:
                with open(test_file, 'w') as f:
                    f.write("test")
                os.remove(test_file)
            except (OSError, PermissionError) as e:
                raise PermissionError(f"Output directory is not writable: {output_dir}. Error: {e}")

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
                chunks = chunk_text_for_quality(cleaned, max_words=40, min_words=15)
                
                for chunk in chunks:
                    all_chunks.append(chunk)
                    chunk_to_chapter.append(chapter_idx)
            
            total_chunks = len(all_chunks)
            self.log(f"Total chunks: {total_chunks}")
            self.update_chunk_progress(0, total_chunks)
            
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
                self.update_chunk_progress(start_idx, total_chunks)

            # Resolve voice preset and engine config
            voice_preset_id = self.voice_preset_id.get() or (VOICE_PRESETS[0]["id"] if VOICE_PRESETS else "")
            preset = get_voice_preset(voice_preset_id)
            engine_type = preset.get("engine", "maya1")
            voice_prompt = self.voice_prompt or preset.get("prompt", self.DEFAULT_VOICE_PROMPT)

            if engine_type == "chatterbox":
                reference_audio = self.reference_audio_var.get().strip()
                if reference_audio:
                    if not os.path.exists(reference_audio):
                        raise FileNotFoundError(f"Reference audio not found: {reference_audio}")
                else:
                    validate_voice_preset(voice_preset_id)
                    reference_audio = preset.get("reference_audio", "")
                voice_config = reference_audio
            else:
                if not voice_prompt:
                    raise ValueError("Voice prompt is empty. Please edit the prompt or select a preset.")
                voice_config = voice_prompt
            
            # Initialize progress
            progress = ConversionProgress(
                epub_path=epub_path,
                output_dir=output_dir,
                selected_chapters=selected_chapters,
                voice_prompt=voice_config,
                total_chunks=total_chunks,
                voice_preset_id=voice_preset_id,
                completed_chunks=list(chunk_files.keys()),
                chunk_files=chunk_files,
                chunk_to_chapter=chunk_to_chapter,
                chapter_titles=chapter_titles
            )
            
            # Load TTS engine
            self.update_status("Loading model...")
            self.update_progress(5)
            
            # Determine which engine to use
            use_batch = self.use_batch_mode.get() and BATCH_MODE_AVAILABLE and engine_type == "maya1"
            batch_size = self.batch_size_var.get()

            # Validate batch size
            if batch_size < 1:
                raise ValueError(f"Batch size must be at least 1, got: {batch_size}")
            if batch_size > 64:
                raise ValueError(f"Batch size too large (max 64), got: {batch_size}")
            if batch_size > 32:
                self.log(f"Warning: Large batch size ({batch_size}) may cause memory issues")
            
            if engine_type == "chatterbox":
                from chatterbox_engine import ChatterboxTurboEngine
                import torch
                device = "cuda" if torch.cuda.is_available() else "cpu"
                self.log("Loading Chatterbox Turbo...")
                engine = ChatterboxTurboEngine(device=device)
                engine.load()
                sample_rate = 22050
            elif use_batch:
                self.log("Using FastMaya batch engine...")
                from fast_maya_engine import FastMaya1Engine
                engine = FastMaya1Engine(memory_util=0.5, use_upsampler=True)
                engine.load()
                sample_rate = engine.sample_rate
            else:
                from convert_epub_to_audiobook import LOCAL_MODEL_DIR
                import torch
                device = "cuda" if torch.cuda.is_available() else "cpu"
                engine = Maya1TTSEngine(LOCAL_MODEL_DIR, device)
                engine.load()
                sample_rate = 24000
            
            self.log("Model loaded")
            self.update_status("Generating audio...")
            self.update_progress_detail("Running")
            
            # Generate chunks - batch or sequential
            if use_batch:
                # Batch processing mode
                i = start_idx
                while i < total_chunks:
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
                    
                    # Get batch of chunks
                    batch_end = min(i + batch_size, total_chunks)
                    batch_texts = all_chunks[i:batch_end]
                    batch_chapters = [chapter_titles[chunk_to_chapter[j]] for j in range(i, batch_end)]
                    
                    status_text = f"Batch {i+1}-{batch_end}/{total_chunks} | {batch_chapters[0]}"
                    self.update_status(status_text)
                    self.update_progress_detail(status_text)
                    self.update_chunk_progress(batch_end, total_chunks)
                    
                    try:
                        # Generate batch
                        audios = engine.batch_generate(batch_texts, voice_prompt, return_concatenated=False)
                        
                        # Save each audio
                        for batch_idx, audio in enumerate(audios):
                            chunk_idx = i + batch_idx
                            if audio is not None and len(audio) > 0:
                                chunk_path = os.path.join(temp_dir, f"chunk_{chunk_idx:04d}.wav")
                                sf.write(chunk_path, audio, sample_rate)
                                
                                progress.completed_chunks.append(chunk_idx)
                                progress.chunk_files[chunk_idx] = chunk_path
                            else:
                                self.log(f"Warning: Empty audio for chunk {chunk_idx}")
                        
                        # Save progress after each batch
                        save_progress(output_dir, progress)
                        
                    except Exception as e:
                        self.log(f"Error on batch {i}-{batch_end}: {e}")
                        import traceback
                        traceback.print_exc()
                    
                    # Update progress (10% to 85%)
                    pct = 10 + (batch_end / total_chunks) * 75
                    self.update_progress(pct)
                    
                    i = batch_end
            else:
                # Sequential processing (original behavior)
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
                    status_text = f"Chunk {i+1}/{total_chunks} | {chapter_title}"
                    
                    self.update_status(status_text)
                    self.update_progress_detail(status_text)
                    self.update_chunk_progress(i + 1, total_chunks)
                    
                    try:
                        if engine_type == "chatterbox":
                            audio = engine.generate_audio(
                                text=chunk,
                                reference_audio_path=reference_audio,
                                max_duration_sec=60
                            )
                        else:
                            audio = engine.generate_audio(chunk, voice_prompt, max_duration_sec=60)
                        
                        if audio is not None and len(audio) > 0:
                            chunk_path = os.path.join(temp_dir, f"chunk_{i:04d}.wav")
                            sf.write(chunk_path, audio, sample_rate)
                            
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

            # Validate all chunks are present
            if len(progress.chunk_files) != total_chunks:
                missing_chunks = sorted([i for i in range(total_chunks) if i not in progress.chunk_files])

                # Format a readable error message
                missing_str = ", ".join(map(str, missing_chunks[:10]))
                if len(missing_chunks) > 10:
                    missing_str += f", ... (+{len(missing_chunks)-10} more)"

                error_msg = f"Conversion failed: {len(missing_chunks)} chunks failed to generate.\nMissing chunks: {missing_str}"
                self.log(error_msg)

                # Do NOT proceed to stitching. This prevents silent content loss.
                self.finish_conversion(False, error_msg)
                return
            
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
                except OSError as e:
                    self.log(f"Warning: Failed to remove {path}: {e}")

            for temp in [output_wav, chapters_file, cover_path]:
                if temp and os.path.exists(temp):
                    try:
                        os.remove(temp)
                    except OSError as e:
                        self.log(f"Warning: Failed to remove {temp}: {e}")

            try:
                os.rmdir(temp_dir)
            except OSError as e:
                self.log(f"Warning: Failed to remove temp directory: {e}")
            
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

    def update_progress_detail(self, detail: str):
        """Update progress detail label (thread-safe)."""
        self.after(0, lambda: self.progress_detail_var.set(detail))

    def update_chunk_progress(self, current: int, total: int):
        """Update chunk counter label (thread-safe)."""
        label = f"{current} / {total}" if total else f"{current} / ?"
        self.after(0, lambda: self.chunk_progress_var.set(label))
    
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

    def copy_log(self):
        """Copy log contents to clipboard."""
        log_text = self.log_text.get("1.0", tk.END).strip()
        self.clipboard_clear()
        self.clipboard_append(log_text)
        self.log("Log copied to clipboard")

    def open_output_folder(self):
        """Open the output folder in the system file manager."""
        output_dir = self.output_dir.get()
        if not output_dir or not os.path.isdir(output_dir):
            messagebox.showwarning("Open Folder", "Output directory is not set or does not exist.")
            return

        try:
            if sys.platform.startswith("win"):
                os.startfile(output_dir)
            elif sys.platform == "darwin":
                os.system(f"open \"{output_dir}\"")
            else:
                os.system(f"xdg-open \"{output_dir}\"")
        except Exception as e:
            messagebox.showerror("Open Folder", f"Failed to open output folder: {e}")
    
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
            self.set_voice_controls_state("readonly")
            self.progress_detail_var.set("Idle")
            self.chunk_progress_var.set("0 / 0")
            
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
