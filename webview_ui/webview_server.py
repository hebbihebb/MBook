import os
import json
import threading
import uuid
import time
from flask import Flask, jsonify, request, render_template, send_file, Response
from tkinter import filedialog
import sys

# Add the parent directory to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from epub_parser import EpubParser
from conversion_state import ConversionState
from conversion_worker import run_conversion_job

app = Flask(__name__, static_folder="static", template_folder="templates")

# Global state
epub_parser = None
cover_image_path = None
conversion_state = None
state_lock = threading.Lock()

# Default voice prompt
DEFAULT_VOICE_PROMPT = "Male narrator voice in his 40s with an American accent. Warm baritone, calm pacing, clear diction, conversational delivery."

# Voice presets
VOICE_PRESETS = [
    {
        "id": "male_us_warm",
        "label": "EN-US NEURAL (M)",
        "prompt": "Male narrator voice in his 40s with an American accent. Warm baritone, calm pacing, clear diction, conversational delivery."
    },
    {
        "id": "female_us_clear",
        "label": "EN-US NEURAL (F)",
        "prompt": "Female narrator voice in her 30s with an American accent. Professional, clear articulation, warm and engaging tone."
    },
    {
        "id": "male_uk_classic",
        "label": "EN-GB STANDARD",
        "prompt": "Male narrator voice with a British accent in his 40s. Classic BBC style, authoritative and refined tone, measured pacing."
    }
]

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
    """Start audiobook generation."""
    global conversion_state

    data = request.get_json()
    if not data or not epub_parser:
        return jsonify({"error": "No EPUB loaded"}), 400

    # Validate required fields
    if not data.get("output_dir"):
        return jsonify({"error": "No output directory selected"}), 400

    if not data.get("chapters"):
        return jsonify({"error": "No chapters selected"}), 400

    # Check for running conversion
    with state_lock:
        if conversion_state and conversion_state.status in ["running", "paused"]:
            return jsonify({"error": "A conversion is already in progress"}), 409

        # Create new state
        job_id = str(uuid.uuid4())
        conversion_state = ConversionState(
            job_id=job_id,
            status="running",
            progress=0,
            current_chunk=0,
            total_chunks=0,
            current_status_text="Starting..."
        )

    # Extract parameters
    # The chapters come as full chapter objects, extract their order indices
    selected_chapters = []
    for i, ch in enumerate(data.get("chapters", [])):
        # Use the index in the list as the order
        selected_chapters.append(i)

    output_dir = data["output_dir"]
    voice_prompt = data.get("voice_prompt", DEFAULT_VOICE_PROMPT)

    # Start background thread
    thread = threading.Thread(
        target=run_conversion_job,
        args=(epub_parser.epub_path, output_dir, selected_chapters, voice_prompt, conversion_state),
        daemon=True
    )
    thread.start()

    conversion_state.add_log(f"Starting conversion of {len(selected_chapters)} chapters", "info")

    return jsonify({"status": "started", "job_id": job_id})

@app.route("/api/status", methods=["GET"])
def get_status():
    """Get current conversion status (for polling)."""
    if not conversion_state:
        return jsonify({"status": "idle"})

    with conversion_state.lock:
        # Collect logs (make a copy to avoid modifying the deque)
        logs = list(conversion_state.log_messages)

        return jsonify({
            "status": conversion_state.status,
            "progress": conversion_state.progress,
            "current_chunk": conversion_state.current_chunk,
            "total_chunks": conversion_state.total_chunks,
            "status_text": conversion_state.current_status_text,
            "logs": logs,
            "error": conversion_state.error_message,
            "final_path": conversion_state.final_path
        })

@app.route("/api/pause", methods=["POST"])
def pause_conversion():
    """Pause or resume conversion."""
    if not conversion_state:
        return jsonify({"error": "No conversion running"}), 400

    data = request.get_json()
    action = data.get("action", "pause") if data else "pause"

    if action == "pause":
        conversion_state.pause_event.set()
        with conversion_state.lock:
            conversion_state.status = "paused"
        conversion_state.add_log("Conversion paused", "info")
        return jsonify({"status": "paused"})
    else:  # resume
        conversion_state.pause_event.clear()
        with conversion_state.lock:
            conversion_state.status = "running"
        conversion_state.add_log("Conversion resumed", "info")
        return jsonify({"status": "running"})

@app.route("/api/cancel", methods=["POST"])
def cancel_conversion():
    """Cancel conversion."""
    if not conversion_state:
        return jsonify({"error": "No conversion running"}), 400

    conversion_state.cancel_event.set()
    conversion_state.add_log("Cancellation requested...", "warning")
    return jsonify({"status": "cancelling"})

@app.route("/api/voice_presets", methods=["GET"])
def get_voice_presets():
    """Return available voice presets."""
    return jsonify({"presets": VOICE_PRESETS})

@app.route("/api/events")
def events():
    """Server-Sent Events stream for real-time updates."""
    def event_stream():
        """Generator function that yields SSE-formatted events."""
        last_progress = -1
        last_status = None
        sent_logs = set()

        while True:
            if not conversion_state:
                # No conversion running, send idle event
                yield f"data: {json.dumps({'event': 'idle'})}\n\n"
                time.sleep(2)
                continue

            with conversion_state.lock:
                current_status = conversion_state.status
                current_progress = conversion_state.progress

                # Send progress update if changed
                if current_progress != last_progress or current_status != last_status:
                    progress_data = {
                        "event": "progress",
                        "status": current_status,
                        "progress": current_progress,
                        "current_chunk": conversion_state.current_chunk,
                        "total_chunks": conversion_state.total_chunks,
                        "status_text": conversion_state.current_status_text
                    }
                    yield f"data: {json.dumps(progress_data)}\n\n"
                    last_progress = current_progress
                    last_status = current_status

                # Send new logs
                for log in conversion_state.log_messages:
                    log_id = f"{log['timestamp']}:{log['message']}"
                    if log_id not in sent_logs:
                        log_data = {
                            "event": "log",
                            "level": log["level"],
                            "message": log["message"],
                            "timestamp": log["timestamp"]
                        }
                        yield f"data: {json.dumps(log_data)}\n\n"
                        sent_logs.add(log_id)

                # Handle terminal states
                if current_status == "completed":
                    completion_data = {
                        "event": "completed",
                        "final_path": conversion_state.final_path
                    }
                    yield f"data: {json.dumps(completion_data)}\n\n"
                    break
                elif current_status == "error":
                    error_data = {
                        "event": "error",
                        "error": conversion_state.error_message
                    }
                    yield f"data: {json.dumps(error_data)}\n\n"
                    break
                elif current_status == "cancelled":
                    cancel_data = {
                        "event": "cancelled"
                    }
                    yield f"data: {json.dumps(cancel_data)}\n\n"
                    break

            time.sleep(0.5)  # Check every 500ms for smoother updates

    response = Response(event_stream(), mimetype="text/event-stream")
    response.headers["Cache-Control"] = "no-cache"
    response.headers["X-Accel-Buffering"] = "no"
    return response

if __name__ == "__main__":
    app.run(port=5000, threaded=True)  # Enable threading for concurrent requests
