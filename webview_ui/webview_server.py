import os
import json
from flask import Flask, jsonify, request, render_template
from tkinter import filedialog
import sys

# Add the parent directory to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from epub_parser import EpubParser

from flask import send_file

app = Flask(__name__, static_folder="static", template_folder="templates")
# I'll keep the epub_parser in memory to avoid reloading it
epub_parser = None
cover_image_path = None

@app.route("/")
def index():
    """Render the main HTML page."""
    return render_template("index.html")

@app.route("/api/select_epub", methods=["POST"])
def select_epub():
    """Open a file dialog to select an EPUB file."""
    filepath = filedialog.askopenfilename(
        title="Select EPUB File",
        filetypes=(("EPUB files", "*.epub"), ("All files", "*.*")),
    )
    if not filepath:
        return jsonify({"error": "No file selected."}), 400

    global epub_parser, cover_image_path
    try:
        epub_parser = EpubParser(filepath)
        chapters = epub_parser.get_chapters()
        cover_image_path = epub_parser.get_cover_image_path()
        book_info = {
            "title": epub_parser.get_book_title(),
            "author": epub_parser.get_book_author(),
            "cover_image": "/api/cover_image" if cover_image_path else None,
            "filepath": filepath,
            "chapters": [
                {"title": str(ch.title), "size": len(ch.content)}
                for ch in chapters
            ],
        }
        return jsonify(book_info)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/cover_image")
def cover_image():
    """Serve the cover image file."""
    if cover_image_path and os.path.exists(cover_image_path):
        return send_file(cover_image_path)
    return "", 404

@app.route("/api/select_output_dir", methods=["POST"])
def select_output_dir():
    """Open a directory dialog to select the output folder."""
    directory = filedialog.askdirectory(title="Select Output Directory")
    if not directory:
        return jsonify({"error": "No directory selected."}), 400
    return jsonify({"output_dir": directory})

@app.route("/api/generate", methods=["POST"])
def generate_audiobook():
    """Generate the audiobook with the selected chapters."""
    data = request.get_json()
    if not data or "chapters" not in data or epub_parser is None:
        return jsonify({"error": "Invalid request."}), 400

    # In a real implementation, this is where the audiobook generation
    # would be triggered. For now, it's a placeholder.
    print(f"Generating audiobook for {len(data['chapters'])} chapters...")
    return jsonify({"status": "success", "message": "Generation started."})

if __name__ == "__main__":
    app.run(port=5000)
