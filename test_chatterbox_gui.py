#!/usr/bin/env python3
"""
Chatterbox Turbo TTS Testing GUI

Simple standalone GUI for testing the Chatterbox Turbo TTS engine.
Allows quick testing of voice cloning with reference audio before
full audiobook conversion.

Features:
- Reference audio file selection
- Text input with paralinguistic tag buttons
- Single-chunk audio generation
- Output to files with timestamps
- Generation time tracking
- Model loading status

Usage:
    python test_chatterbox_gui.py
"""

import tkinter as tk
from tkinter import filedialog, messagebox
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
import threading
import os
import time
from datetime import datetime
import soundfile as sf


class ChatterboxTestGUI(ttk.Window):
    """Simple testing GUI for Chatterbox Turbo TTS engine."""

    def __init__(self):
        super().__init__(themename="darkly")
        self.title("Chatterbox Turbo TTS Testing GUI")
        self.geometry("700x550")
        self.minsize(600, 500)

        # State
        self.engine = None
        self.reference_audio_path = None
        self.is_generating = False

        # Build UI
        self.create_widgets()

        # Center window
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - (self.winfo_width() // 2)
        y = (self.winfo_screenheight() // 2) - (self.winfo_height() // 2)
        self.geometry(f"+{x}+{y}")

    def create_widgets(self):
        """Create all UI widgets."""
        # Header
        header = ttk.Label(
            self,
            text="Chatterbox Turbo TTS Testing",
            font=("Helvetica", 16, "bold"),
            bootstyle="inverse-dark"
        )
        header.pack(pady=(15, 10), padx=15, fill=X)

        # Main container
        main_frame = ttk.Frame(self)
        main_frame.pack(fill=BOTH, expand=True, padx=15, pady=(0, 15))

        # Reference Audio Section
        ref_frame = ttk.LabelFrame(main_frame, text="Reference Audio", padding=10)
        ref_frame.pack(fill=X, pady=(0, 10))

        ref_container = ttk.Frame(ref_frame)
        ref_container.pack(fill=X)

        self.ref_audio_var = tk.StringVar(value="No file selected")
        ref_label = ttk.Label(
            ref_container,
            textvariable=self.ref_audio_var,
            font=("Helvetica", 9),
            bootstyle="secondary"
        )
        ref_label.pack(side=LEFT, fill=X, expand=True, padx=(0, 10))

        ref_btn = ttk.Button(
            ref_container,
            text="Browse...",
            command=self.select_reference_audio,
            bootstyle="secondary",
            width=12
        )
        ref_btn.pack(side=RIGHT)

        # Quick reference audio selection
        quick_ref_frame = ttk.Frame(ref_frame)
        quick_ref_frame.pack(fill=X, pady=(10, 0))

        ttk.Label(
            quick_ref_frame,
            text="Quick Select:",
            font=("Helvetica", 9)
        ).pack(side=LEFT, padx=(0, 5))

        for name, file in [
            ("US Male", "voice_samples/en_us_male_warm.wav"),
            ("US Female", "voice_samples/en_us_female_clear.wav"),
            ("UK Male", "voice_samples/en_gb_male_standard.wav")
        ]:
            btn = ttk.Button(
                quick_ref_frame,
                text=name,
                command=lambda f=file: self.select_quick_reference(f),
                bootstyle="info-outline",
                width=10
            )
            btn.pack(side=LEFT, padx=2)

        # Text Input Section
        text_frame = ttk.LabelFrame(main_frame, text="Text Input", padding=10)
        text_frame.pack(fill=BOTH, expand=True, pady=(0, 10))

        # Text area
        self.text_input = tk.Text(
            text_frame,
            wrap=tk.WORD,
            height=8,
            font=("Helvetica", 10)
        )
        self.text_input.pack(fill=BOTH, expand=True, padx=(0, 5))

        # Placeholder text
        placeholder = (
            "Enter text to generate (up to 500 characters).\n\n"
            "Supports paralinguistic tags like [laugh], [cough], [chuckle].\n\n"
            "Example: Hello there [chuckle], welcome to the testing interface!"
        )
        self.text_input.insert("1.0", placeholder)
        self.text_input.configure(foreground="gray")

        # Bind focus events for placeholder
        self.text_input.bind("<FocusIn>", self.on_text_focus_in)
        self.text_input.bind("<FocusOut>", self.on_text_focus_out)

        # Tag buttons
        tag_frame = ttk.Frame(text_frame)
        tag_frame.pack(fill=X, pady=(10, 0))

        ttk.Label(
            tag_frame,
            text="Insert Tags:",
            font=("Helvetica", 9)
        ).pack(side=LEFT, padx=(0, 5))

        for tag in ["[laugh]", "[cough]", "[chuckle]"]:
            btn = ttk.Button(
                tag_frame,
                text=tag,
                command=lambda t=tag: self.insert_tag(t),
                bootstyle="info-outline",
                width=10
            )
            btn.pack(side=LEFT, padx=2)

        # Control Section
        control_frame = ttk.Frame(main_frame)
        control_frame.pack(fill=X)

        self.generate_btn = ttk.Button(
            control_frame,
            text="Generate Audio",
            command=self.generate_audio,
            bootstyle="success",
            width=20
        )
        self.generate_btn.pack(side=LEFT, padx=(0, 10))

        self.status_var = tk.StringVar(value="Status: Ready")
        status_label = ttk.Label(
            control_frame,
            textvariable=self.status_var,
            font=("Helvetica", 9),
            bootstyle="secondary"
        )
        status_label.pack(side=LEFT, fill=X, expand=True)

        # Output Section
        output_frame = ttk.LabelFrame(main_frame, text="Output", padding=10)
        output_frame.pack(fill=X, pady=(10, 0))

        self.output_var = tk.StringVar(value="Output: output/test_YYYYMMDD_HHMMSS.wav")
        output_label = ttk.Label(
            output_frame,
            textvariable=self.output_var,
            font=("Helvetica", 9, "bold"),
            bootstyle="info"
        )
        output_label.pack(anchor=W, pady=(0, 5))

        self.time_var = tk.StringVar(value="Generation Time: --")
        time_label = ttk.Label(
            output_frame,
            textvariable=self.time_var,
            font=("Helvetica", 9)
        )
        time_label.pack(anchor=W)

    def on_text_focus_in(self, event):
        """Clear placeholder on focus."""
        if self.text_input.get("1.0", "end-1c").startswith("Enter text to generate"):
            self.text_input.delete("1.0", tk.END)
            self.text_input.configure(foreground="white")

    def on_text_focus_out(self, event):
        """Restore placeholder if empty."""
        if not self.text_input.get("1.0", "end-1c").strip():
            placeholder = (
                "Enter text to generate (up to 500 characters).\n\n"
                "Supports paralinguistic tags like [laugh], [cough], [chuckle].\n\n"
                "Example: Hello there [chuckle], welcome to the testing interface!"
            )
            self.text_input.insert("1.0", placeholder)
            self.text_input.configure(foreground="gray")

    def insert_tag(self, tag):
        """Insert a paralinguistic tag at cursor position."""
        # Clear placeholder if present
        if self.text_input.get("1.0", "end-1c").startswith("Enter text to generate"):
            self.text_input.delete("1.0", tk.END)
            self.text_input.configure(foreground="white")

        # Insert tag
        self.text_input.insert(tk.INSERT, tag + " ")
        self.text_input.focus_set()

    def select_reference_audio(self):
        """Open file dialog to select reference audio."""
        filepath = filedialog.askopenfilename(
            title="Select Reference Audio (WAV)",
            filetypes=(("WAV files", "*.wav"), ("All files", "*.*")),
            initialdir="voice_samples" if os.path.exists("voice_samples") else "."
        )

        if filepath:
            self.reference_audio_path = filepath
            self.ref_audio_var.set(os.path.basename(filepath))

    def select_quick_reference(self, filepath):
        """Quick select a default reference audio file."""
        if os.path.exists(filepath):
            self.reference_audio_path = filepath
            self.ref_audio_var.set(os.path.basename(filepath))
        else:
            messagebox.showerror(
                "File Not Found",
                f"Reference audio not found:\n{filepath}\n\n"
                "Run: python generate_voice_samples.py"
            )

    def load_engine(self):
        """Load the Chatterbox Turbo engine (lazy loading)."""
        if self.engine is not None:
            return True

        self.status_var.set("Status: Loading model...")
        self.update_idletasks()

        try:
            from chatterbox_engine import ChatterboxTurboEngine

            self.engine = ChatterboxTurboEngine(device="cuda")
            self.engine.load()

            self.status_var.set("Status: Model loaded successfully")
            return True

        except ImportError as e:
            messagebox.showerror(
                "Dependency Error",
                f"chatterbox-tts not installed.\n\n"
                f"Install with: pip install chatterbox-tts\n\n"
                f"Error: {e}"
            )
            self.status_var.set("Status: Error - Missing dependency")
            return False

        except Exception as e:
            messagebox.showerror(
                "Loading Error",
                f"Failed to load Chatterbox Turbo model:\n\n{e}"
            )
            self.status_var.set("Status: Error loading model")
            return False

    def generate_audio(self):
        """Generate audio in background thread."""
        if self.is_generating:
            messagebox.showwarning("Busy", "Generation already in progress")
            return

        # Validate reference audio
        if not self.reference_audio_path:
            messagebox.showwarning(
                "No Reference Audio",
                "Please select a reference audio file first"
            )
            return

        if not os.path.exists(self.reference_audio_path):
            messagebox.showerror(
                "File Not Found",
                f"Reference audio file not found:\n{self.reference_audio_path}"
            )
            return

        # Get text
        text = self.text_input.get("1.0", "end-1c").strip()
        if text.startswith("Enter text to generate") or not text:
            messagebox.showwarning(
                "No Text",
                "Please enter text to generate"
            )
            return

        if len(text) > 500:
            result = messagebox.askyesno(
                "Long Text",
                f"Text is {len(text)} characters (recommended < 500).\n\n"
                "This may take longer to generate.\n\n"
                "Continue anyway?"
            )
            if not result:
                return

        # Run generation in background
        thread = threading.Thread(
            target=self._generate_audio_thread,
            args=(text,),
            daemon=True
        )
        thread.start()

    def _generate_audio_thread(self, text):
        """Background thread for audio generation."""
        self.is_generating = True
        self.generate_btn.configure(state="disabled")

        try:
            # Load engine if needed
            if not self.load_engine():
                return

            # Generate timestamp for output filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_dir = "output"
            os.makedirs(output_dir, exist_ok=True)
            output_path = os.path.join(output_dir, f"test_{timestamp}.wav")

            self.output_var.set(f"Output: {output_path}")
            self.status_var.set("Status: Generating audio...")
            self.update_idletasks()

            # Generate audio
            start_time = time.time()

            audio = self.engine.generate_audio(
                text=text,
                reference_audio_path=self.reference_audio_path
            )

            if audio is None:
                raise RuntimeError("Audio generation returned None")

            # Save audio
            sf.write(output_path, audio, self.engine.sr)

            elapsed_time = time.time() - start_time

            # Update UI
            self.time_var.set(f"Generation Time: {elapsed_time:.2f}s")
            self.status_var.set(f"Status: Complete! Saved to {output_path}")

            messagebox.showinfo(
                "Success",
                f"Audio generated successfully!\n\n"
                f"Output: {output_path}\n"
                f"Duration: {len(audio) / self.engine.sr:.1f}s\n"
                f"Generation Time: {elapsed_time:.2f}s"
            )

        except Exception as e:
            self.status_var.set("Status: Error during generation")
            messagebox.showerror(
                "Generation Error",
                f"Failed to generate audio:\n\n{e}"
            )

        finally:
            self.is_generating = False
            self.generate_btn.configure(state="normal")


def main():
    """Main entry point."""
    # Check for ttkbootstrap
    try:
        import ttkbootstrap
    except ImportError:
        print("Error: ttkbootstrap not installed")
        print("Install with: pip install ttkbootstrap")
        return 1

    # Create and run GUI
    app = ChatterboxTestGUI()
    app.mainloop()
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
