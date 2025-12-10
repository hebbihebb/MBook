import tkinter as tk
from tkinter import filedialog, messagebox
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
import threading
import os
import time

# Import pipeline components
# Note: Ensure requirements.txt deps are installed.
try:
    from pipeline import Maya1Pipeline, clean_text, chunk_text, validate_audio
    from assembler import stitch_audio, export_m4b
    import ebooklib
    from ebooklib import epub
    from bs4 import BeautifulSoup
except ImportError as e:
    # If running in environment without deps, this will fail. 
    # For coding purposes, we assume deps will be present in user env.
    print(f"Warning: Missing dependencies: {e}")

class AudiobookApp(ttk.Window):
    def __init__(self):
        super().__init__(themename="darkly")
        self.title("Maya1 Audiobook Converter")
        self.geometry("600x450")
        
        # Variables
        self.epub_path = tk.StringVar()
        self.status_var = tk.StringVar(value="Ready")
        self.progress_var = tk.DoubleVar(value=0)
        
        self.create_widgets()
        
    def create_widgets(self):
        # Header
        lbl_header = ttk.Label(self, text="Maya1 Audiobook Generator", font=("Helvetica", 18, "bold"), bootstyle="primary")
        lbl_header.pack(pady=20)
        
        # File Selection Frame
        frm_files = ttk.Frame(self)
        frm_files.pack(fill=X, padx=20, pady=10)
        
        # EPUB Selection
        lbl_epub = ttk.Label(frm_files, text="EPUB File:")
        lbl_epub.grid(row=0, column=0, sticky=W, pady=5)
        
        ent_epub = ttk.Entry(frm_files, textvariable=self.epub_path, width=50)
        ent_epub.grid(row=0, column=1, padx=5, pady=5)
        
        btn_epub = ttk.Button(frm_files, text="Browse", command=self.browse_epub, bootstyle="secondary-outline")
        btn_epub.grid(row=0, column=2, padx=5)
        

        
        # Convert Button
        btn_convert = ttk.Button(self, text="Start Conversion", command=self.start_conversion, bootstyle="success-lg")
        btn_convert.pack(pady=20)
        
        # Progress
        self.progressbar = ttk.Progressbar(self, variable=self.progress_var, maximum=100, bootstyle="striped-animated")
        self.progressbar.pack(fill=X, padx=20, pady=10)
        
        lbl_status = ttk.Label(self, textvariable=self.status_var, font=("Helvetica", 10))
        lbl_status.pack(pady=5)
        
    def browse_epub(self):
        path = filedialog.askopenfilename(filetypes=[("EPUB Files", "*.epub"), ("All Files", "*.*")])
        if path:
            self.epub_path.set(path)
            


    def start_conversion(self):
        if not self.epub_path.get():
            messagebox.showerror("Error", "Please select an EPUB file.")
            return
            
        # Run in thread to keep GUI responsive
        threading.Thread(target=self.run_pipeline, daemon=True).start()

    def run_pipeline(self):
        try:
            epub_file = self.epub_path.get()

            self.status_var.set("Loading Model...")
            self.update_progress(5)
            
            pipeline = Maya1Pipeline()
            pipeline.load_model()
            
            self.status_var.set("Reading EPUB...")
            self.update_progress(10)
            
            # Extract text from EPUB
            book = epub.read_epub(epub_file)
            full_text = ""
            for item in book.get_items():
                if item.get_type() == ebooklib.ITEM_DOCUMENT:
                    soup = BeautifulSoup(item.get_content(), 'html.parser')
                    full_text += soup.get_text() + "\n"
            
            self.status_var.set("Cleaning and Chunking...")
            self.update_progress(15)
            
            cleaned_text = clean_text(full_text)
            chunks = chunk_text(cleaned_text)
            
            total_chunks = len(chunks)
            if total_chunks == 0:
                self.status_var.set("No text found!")
                return

            generated_audio_chunks = []
            
            self.status_var.set(f"Generating Audio ({total_chunks} chunks)...")
            
            for i, chunk in enumerate(chunks):
                # Retry logic for hallucination handling
                max_retries = 3
                valid_audio = None
                
                for attempt in range(max_retries):
                    audio_tensor = pipeline.generate_chunk(chunk, None)
                    
                    if audio_tensor is None:
                        # Should not happen if model loaded, unless mocked
                        # Create dummy silence if mocking
                        import torch
                        audio_tensor = torch.zeros((1, 24000))
                    
                    # Estimate char count
                    # Chunk includes "..." padding, but we should count content?
                    # validate_audio expects char count.
                    char_count = len(chunk)
                    
                    is_valid, trimmed_audio = validate_audio(audio_tensor, char_count)
                    
                    if is_valid:
                        valid_audio = trimmed_audio
                        break
                    else:
                        print(f"Chunk {i} failed validation (Attempt {attempt+1})")
                
                if valid_audio is not None:
                    # Convert tensor to AudioSegment for pydub
                    # Assuming 24khz sample rate from Maya1
                    # tensor [1, T] -> numpy -> pydub
                    import numpy as np
                    from pydub import AudioSegment
                    import scipy.io.wavfile
                    
                    # Convert to numpy
                    audio_np = valid_audio.squeeze().numpy()
                    
                    # export to temp wav then load (safest for pydub)
                    temp_chunk_path = f"temp_chunk_{i}.wav"
                    scipy.io.wavfile.write(temp_chunk_path, 24000, audio_np)
                    generated_audio_chunks.append(temp_chunk_path)
                else:
                    print(f"Skipping chunk {i} after max retries.")
                
                # Update progress
                # Map 15 -> 90
                percent = 15 + (i / total_chunks) * 75
                self.update_progress(percent)
                self.status_var.set(f"Generating: {int((i+1)/total_chunks*100)}%")

            self.status_var.set("Stitching Audio...")
            output_wav = stitch_audio(generated_audio_chunks, output_path="final_output.wav")
            
            self.status_var.set("Exporting M4B...")
            # Extract simple metadata
            meta = {'title': book.title, 'author': book.get_metadata('DC', 'creator')[0][0]}
            
            output_m4b = epub_file.replace(".epub", ".m4b")
            export_m4b(output_wav, output_m4b, metadata=meta)
            
            # Cleanup temp files
            for temp in generated_audio_chunks:
                try:
                    os.remove(temp)
                except:
                    pass
            os.remove(output_wav)
            
            self.update_progress(100)
            self.status_var.set("Complete!")
            messagebox.showinfo("Success", f"Audiobook saved to:\n{output_m4b}")
            
        except Exception as e:
            self.status_var.set("Error!")
            print(e)
            messagebox.showerror("Error", str(e))

    def update_progress(self, val):
        self.progress_var.set(val)
        self.update_idletasks()

if __name__ == "__main__":
    app = AudiobookApp()
    app.mainloop()
