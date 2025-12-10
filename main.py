import tkinter as tk
from tkinter import filedialog, messagebox
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
import threading
import os

# Import pipeline components
try:
    from pipeline import Maya1Pipeline, clean_text, chunk_text, validate_audio
    from assembler import (
        stitch_audio_with_chapter_tracking,
        generate_chapter_metadata,
        export_m4b,
        create_audiobookshelf_folder
    )
    from epub_parser import parse_epub_with_chapters, get_cover_extension
except ImportError as e:
    print(f"Warning: Missing dependencies: {e}")


class AudiobookApp(ttk.Window):
    def __init__(self):
        super().__init__(themename="darkly")
        self.title("Maya1 Audiobook Converter")
        self.geometry("650x500")
        
        # Variables
        self.epub_path = tk.StringVar()
        self.output_dir = tk.StringVar(value=os.path.expanduser("~/Audiobooks"))
        self.status_var = tk.StringVar(value="Ready")
        self.progress_var = tk.DoubleVar(value=0)
        
        self.create_widgets()
        
    def create_widgets(self):
        # Header
        lbl_header = ttk.Label(
            self, 
            text="Maya1 Audiobook Generator", 
            font=("Helvetica", 18, "bold"), 
            bootstyle="primary"
        )
        lbl_header.pack(pady=20)
        
        # File Selection Frame
        frm_files = ttk.Frame(self)
        frm_files.pack(fill=X, padx=20, pady=10)
        
        # EPUB Selection
        lbl_epub = ttk.Label(frm_files, text="EPUB File:")
        lbl_epub.grid(row=0, column=0, sticky=W, pady=5)
        
        ent_epub = ttk.Entry(frm_files, textvariable=self.epub_path, width=50)
        ent_epub.grid(row=0, column=1, padx=5, pady=5)
        
        btn_epub = ttk.Button(
            frm_files, 
            text="Browse", 
            command=self.browse_epub, 
            bootstyle="secondary-outline"
        )
        btn_epub.grid(row=0, column=2, padx=5)
        
        # Output Directory Selection
        lbl_output = ttk.Label(frm_files, text="Output Directory:")
        lbl_output.grid(row=1, column=0, sticky=W, pady=5)
        
        ent_output = ttk.Entry(frm_files, textvariable=self.output_dir, width=50)
        ent_output.grid(row=1, column=1, padx=5, pady=5)
        
        btn_output = ttk.Button(
            frm_files,
            text="Browse",
            command=self.browse_output_dir,
            bootstyle="secondary-outline"
        )
        btn_output.grid(row=1, column=2, padx=5)
        
        # Info label
        lbl_info = ttk.Label(
            self, 
            text="Output: {output_dir}/{Author}/{Title}/{Title}.m4b",
            font=("Helvetica", 9),
            bootstyle="secondary"
        )
        lbl_info.pack(pady=5)
        
        # Convert Button
        btn_convert = ttk.Button(
            self, 
            text="Start Conversion", 
            command=self.start_conversion, 
            bootstyle="success-lg"
        )
        btn_convert.pack(pady=20)
        
        # Progress
        self.progressbar = ttk.Progressbar(
            self, 
            variable=self.progress_var, 
            maximum=100, 
            bootstyle="striped-animated"
        )
        self.progressbar.pack(fill=X, padx=20, pady=10)
        
        lbl_status = ttk.Label(
            self, 
            textvariable=self.status_var, 
            font=("Helvetica", 10)
        )
        lbl_status.pack(pady=5)
        
        # Chapter info label (shows detected chapters)
        self.chapter_info_var = tk.StringVar(value="")
        lbl_chapters = ttk.Label(
            self,
            textvariable=self.chapter_info_var,
            font=("Helvetica", 9),
            bootstyle="info"
        )
        lbl_chapters.pack(pady=5)
        
    def browse_epub(self):
        path = filedialog.askopenfilename(
            filetypes=[("EPUB Files", "*.epub"), ("All Files", "*.*")]
        )
        if path:
            self.epub_path.set(path)
            # Quick preview of chapters
            try:
                from epub_parser import parse_epub_with_chapters
                parsed = parse_epub_with_chapters(path)
                self.chapter_info_var.set(
                    f"Detected: {len(parsed.chapters)} chapters | {parsed.author}"
                )
            except Exception:
                self.chapter_info_var.set("")
                
    def browse_output_dir(self):
        path = filedialog.askdirectory()
        if path:
            self.output_dir.set(path)

    def start_conversion(self):
        if not self.epub_path.get():
            messagebox.showerror("Error", "Please select an EPUB file.")
            return
            
        if not self.output_dir.get():
            messagebox.showerror("Error", "Please select an output directory.")
            return
            
        # Run in thread to keep GUI responsive
        threading.Thread(target=self.run_pipeline, daemon=True).start()

    def run_pipeline(self):
        try:
            epub_file = self.epub_path.get()
            output_dir = self.output_dir.get()

            self.status_var.set("Parsing EPUB...")
            self.update_progress(5)
            
            # Parse EPUB with chapter awareness
            parsed_epub = parse_epub_with_chapters(epub_file)
            
            self.status_var.set(f"Found {len(parsed_epub.chapters)} chapters")
            self.update_progress(8)
            
            self.status_var.set("Loading Model...")
            self.update_progress(10)
            
            pipeline = Maya1Pipeline()
            pipeline.load_model()
            
            self.status_var.set("Processing chapters...")
            self.update_progress(12)
            
            # Process each chapter and track chunk-to-chapter mapping
            all_chunks = []           # List of text chunks
            chunk_to_chapter = []     # Maps chunk index -> chapter index
            chapter_titles = []       # List of chapter titles
            
            for chapter in parsed_epub.chapters:
                chapter_titles.append(chapter.title)
                cleaned_text = clean_text(chapter.content)
                chapter_chunks = chunk_text(cleaned_text)
                
                for chunk in chapter_chunks:
                    all_chunks.append(chunk)
                    chunk_to_chapter.append(chapter.order)
            
            total_chunks = len(all_chunks)
            if total_chunks == 0:
                self.status_var.set("No text found!")
                return
            
            self.status_var.set(f"Generating audio ({total_chunks} chunks)...")
            
            generated_audio_chunks = []
            
            for i, chunk in enumerate(all_chunks):
                # Retry logic for hallucination handling
                max_retries = 3
                valid_audio = None
                
                for attempt in range(max_retries):
                    audio_tensor = pipeline.generate_chunk(chunk, None)
                    
                    if audio_tensor is None:
                        import torch
                        audio_tensor = torch.zeros((1, 24000))
                    
                    char_count = len(chunk)
                    is_valid, trimmed_audio = validate_audio(audio_tensor, char_count)
                    
                    if is_valid:
                        valid_audio = trimmed_audio
                        break
                    else:
                        print(f"Chunk {i} failed validation (Attempt {attempt+1})")
                
                if valid_audio is not None:
                    import numpy as np
                    import scipy.io.wavfile
                    
                    audio_np = valid_audio.squeeze().numpy()
                    temp_chunk_path = f"temp_chunk_{i}.wav"
                    scipy.io.wavfile.write(temp_chunk_path, 24000, audio_np)
                    generated_audio_chunks.append(temp_chunk_path)
                else:
                    print(f"Skipping chunk {i} after max retries.")
                
                # Update progress (12 -> 85)
                percent = 12 + (i / total_chunks) * 73
                self.update_progress(percent)
                
                # Show chapter info in status
                current_chapter = chapter_titles[chunk_to_chapter[i]]
                self.status_var.set(
                    f"Generating: {int((i+1)/total_chunks*100)}% | {current_chapter}"
                )

            self.status_var.set("Stitching audio with chapters...")
            self.update_progress(86)
            
            # Stitch audio and get chapter timing info
            output_wav, chapters_info = stitch_audio_with_chapter_tracking(
                generated_audio_chunks,
                chunk_to_chapter[:len(generated_audio_chunks)],  # Match length if chunks skipped
                chapter_titles,
                output_path="temp_final.wav"
            )
            
            self.status_var.set("Generating chapter metadata...")
            self.update_progress(88)
            
            # Generate FFMETADATA file for chapters
            chapters_file = generate_chapter_metadata(chapters_info, "chapters.txt")
            
            # Save cover image temporarily if present
            cover_path = None
            cover_ext = ".jpg"
            if parsed_epub.cover_image:
                cover_ext = get_cover_extension(parsed_epub.cover_media_type or "image/jpeg")
                cover_path = f"temp_cover{cover_ext}"
                with open(cover_path, 'wb') as f:
                    f.write(parsed_epub.cover_image)
            
            self.status_var.set("Exporting M4B...")
            self.update_progress(90)
            
            # Export to temporary M4B first
            temp_m4b = "temp_output.m4b"
            meta = {
                'title': parsed_epub.title,
                'author': parsed_epub.author
            }
            
            export_m4b(
                output_wav,
                temp_m4b,
                metadata=meta,
                cover_art_path=cover_path,
                chapters_file=chapters_file
            )
            
            self.status_var.set("Creating Audiobookshelf folder...")
            self.update_progress(95)
            
            # Move to Audiobookshelf folder structure
            final_path = create_audiobookshelf_folder(
                output_dir=output_dir,
                author=parsed_epub.author,
                title=parsed_epub.title,
                m4b_path=temp_m4b,
                cover_image_bytes=parsed_epub.cover_image,
                cover_extension=cover_ext
            )
            
            # Cleanup temp files
            self.status_var.set("Cleaning up...")
            self.update_progress(98)
            
            for temp in generated_audio_chunks:
                try:
                    os.remove(temp)
                except:
                    pass
            
            for temp_file in [output_wav, chapters_file, cover_path]:
                if temp_file and os.path.exists(temp_file):
                    try:
                        os.remove(temp_file)
                    except:
                        pass
            
            self.update_progress(100)
            self.status_var.set("Complete!")
            messagebox.showinfo(
                "Success", 
                f"Audiobook saved to:\n{final_path}\n\n"
                f"Chapters: {len(chapters_info)}"
            )
            
        except Exception as e:
            self.status_var.set("Error!")
            import traceback
            traceback.print_exc()
            messagebox.showerror("Error", str(e))

    def update_progress(self, val):
        self.progress_var.set(val)
        self.update_idletasks()


if __name__ == "__main__":
    app = AudiobookApp()
    app.mainloop()

