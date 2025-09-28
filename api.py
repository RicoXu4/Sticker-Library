from flask import Flask, request, render_template, redirect, url_for
import os, sqlite3
from werkzeug.utils import secure_filename
import pytesseract
import requests
import datetime
from PIL import Image, ImageSequence
import tempfile

app = Flask(__name__)
UPLOAD_FOLDER = "static/uploads"
DB = "db.sqlite"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# Helper function to run RapidOCR via HTTP API
def run_rapidocr_http(path):
    import os
    with Image.open(path) as im:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp_file:
            im = im.convert("RGBA")
            im.save(tmp_file.name, "PNG")
            tmp_filename = tmp_file.name
    try:
        with open(tmp_filename, "rb") as f:
            # RapidOCR backend expects the image under the "image_file" field
            files = {"image_file": (os.path.basename(tmp_filename), f, "image/png")}
            response = requests.post("http://localhost:9005/ocr", files=files)
        response.raise_for_status()
        data = response.json()
        # Assume response is a dict keyed by string numbers, each value has "rec_txt"
        texts = [entry.get("rec_txt", "") for entry in data.values() if entry.get("rec_txt", "")]
        return "\n".join(texts)
    finally:
        if os.path.exists(tmp_filename):
            os.remove(tmp_filename)

def ensure_gif_filename(filename):
    if filename.lower().endswith(".gif"):
        return filename, False

    original_abs = os.path.join(UPLOAD_FOLDER, filename)
    if not os.path.exists(original_abs):
        return filename, False

    base, _ = os.path.splitext(filename)
    gif_relative = base + ".gif"
    gif_abs = os.path.join(UPLOAD_FOLDER, gif_relative)
    os.makedirs(os.path.dirname(gif_abs), exist_ok=True)

    try:
        with Image.open(original_abs) as im:
            im = im.convert("RGBA") if im.mode not in ("RGB", "RGBA") else im
            im.save(gif_abs, "GIF")
    except Exception:
        return filename, False

    os.remove(original_abs)
    return gif_relative, True

def fetch_images(query=None):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    if query is None:
        c.execute("SELECT id, filename, ocr_text, lang, uploaded_at FROM images")
    else:
        c.execute("SELECT id, filename, ocr_text, lang, uploaded_at FROM images WHERE ocr_text LIKE ?", ('%' + query + '%',))

    rows = c.fetchall()
    updates = []
    images = []
    for image_id, filename, ocr_text, lang, uploaded_at in rows:
        new_filename, changed = ensure_gif_filename(filename)
        if changed:
            updates.append((new_filename, image_id))
            filename = new_filename
        images.append((filename, ocr_text, lang, uploaded_at))

    if updates:
        c.executemany("UPDATE images SET filename = ? WHERE id = ?", updates)
        conn.commit()

    conn.close()
    return images

# --- DB setup ---
def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS images (
            id INTEGER PRIMARY KEY,
            filename TEXT,
            ocr_text TEXT,
            lang TEXT DEFAULT 'eng',
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Ensure lang column exists in case of older DB schema
    c.execute("PRAGMA table_info(images)")
    columns = [row[1] for row in c.fetchall()]
    if "lang" not in columns:
        c.execute("ALTER TABLE images ADD COLUMN lang TEXT DEFAULT 'eng'")
    if "uploaded_at" not in columns:
        # SQLite does not allow adding a column with DEFAULT CURRENT_TIMESTAMP.
        # So just add as TEXT, and always provide value explicitly when inserting.
        c.execute("ALTER TABLE images ADD COLUMN uploaded_at TEXT")
    conn.commit()
    conn.close()

init_db()

# --- Routes ---
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        file = request.files["file"]
        if file:
            date_folder = datetime.date.today().isoformat()
            save_folder = os.path.join(UPLOAD_FOLDER, date_folder)
            os.makedirs(save_folder, exist_ok=True)

            filename = secure_filename(file.filename)
            path = os.path.join(save_folder, filename)

            # Save the uploaded file
            file.save(path)

            lang = request.form.get("lang", "eng")

            if filename.lower().endswith(".gif"):
                try:
                    with Image.open(path) as im:
                        prev_text = None
                        texts = []
                        for frame in ImageSequence.Iterator(im):
                            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp_frame:
                                frame.convert("RGBA").save(tmp_frame.name)
                                if lang in ["chi_sim", "chi_tra"]:
                                    text = run_rapidocr_http(tmp_frame.name)
                                else:
                                    text = pytesseract.image_to_string(tmp_frame.name, lang=lang)
                            os.remove(tmp_frame.name)
                            if text != prev_text:
                                if prev_text is not None and text.startswith(prev_text):
                                    # Replace last entry with new text
                                    texts[-1] = text
                                else:
                                    texts.append(text)
                                prev_text = text
                        text = "\n".join(texts)
                except Exception:
                    if os.path.exists(path):
                        os.remove(path)
                    raise
                relative_gif_path = os.path.join(date_folder, filename)
            else:
                try:
                    text = pytesseract.image_to_string(path, lang=lang) if lang not in ["chi_sim", "chi_tra"] else run_rapidocr_http(path)
                except Exception:
                    if os.path.exists(path):
                        os.remove(path)
                    raise

                # Convert to GIF using Pillow
                gif_filename = os.path.splitext(filename)[0] + ".gif"
                gif_path = os.path.join(save_folder, gif_filename)
                try:
                    with Image.open(path) as im:
                        im = im.convert("RGBA") if im.mode not in ("RGB", "RGBA") else im
                        im.save(gif_path, "GIF")
                except Exception:
                    # Clean up and re-raise for debugging
                    if os.path.exists(path):
                        os.remove(path)
                    raise

                # Remove the original uploaded file after conversion
                if os.path.exists(path):
                    os.remove(path)

                relative_gif_path = os.path.join(date_folder, gif_filename)

            conn = sqlite3.connect(DB)
            c = conn.cursor()
            c.execute("INSERT INTO images (filename, ocr_text, lang, uploaded_at) VALUES (?, ?, ?, datetime('now'))", (relative_gif_path, text, lang))
            conn.commit()
            conn.close()

            return redirect(url_for("index"))

    images = fetch_images()

    return render_template("index.html", images=images)

@app.route("/search")
def search():
    query = request.args.get("q", "")
    images = fetch_images(query=query)
    return render_template("index.html", images=images, query=query)


# --- Delete Route ---
@app.route("/delete/<path:filename>", methods=["GET", "POST"])
def delete_image(filename):
    # filename is a relative path, e.g., "2025-08-30/54.gif"
    file_path = os.path.join(UPLOAD_FOLDER, filename)
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    if os.path.exists(file_path):
        os.remove(file_path)
    c.execute("DELETE FROM images WHERE filename = ?", (filename,))
    conn.commit()
    conn.close()
    return redirect(url_for("index"))

@app.route("/rescan/<path:filename>", methods=["GET", "POST"])
def rescan_image(filename):
    file_path = os.path.join(UPLOAD_FOLDER, filename)
    if not os.path.exists(file_path):
        return redirect(url_for("index"))

    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT lang FROM images WHERE filename = ?", (filename,))
    row = c.fetchone()
    lang = row[0] if row else "eng"
    conn.close()

    old_filename = filename
    new_filename = filename

    try:
        if filename.lower().endswith(".gif"):
            with Image.open(file_path) as im:
                prev_text = None
                texts = []
                for frame in ImageSequence.Iterator(im):
                    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp_frame:
                        frame.convert("RGBA").save(tmp_frame.name)
                        if lang in ["chi_sim", "chi_tra"]:
                            text = run_rapidocr_http(tmp_frame.name)
                        else:
                            text = pytesseract.image_to_string(tmp_frame.name, lang=lang)
                    os.remove(tmp_frame.name)
                    if text != prev_text:
                        if prev_text is not None and text.startswith(prev_text):
                            texts[-1] = text
                        else:
                            texts.append(text)
                        prev_text = text
                text = "\n".join(texts)
        else:
            if lang in ["chi_sim", "chi_tra"]:
                text = run_rapidocr_http(file_path)
            else:
                text = pytesseract.image_to_string(file_path, lang=lang)

            # Convert to GIF if needed
            if not filename.lower().endswith(".gif"):
                gif_filename = os.path.splitext(filename)[0] + ".gif"
                gif_path = os.path.join(UPLOAD_FOLDER, gif_filename)
                with Image.open(file_path) as im:
                    im = im.convert("RGBA") if im.mode not in ("RGB", "RGBA") else im
                    im.save(gif_path, "GIF")
                # Remove original file after conversion
                os.remove(file_path)
                new_filename = gif_filename
                file_path = gif_path

    except Exception:
        return redirect(url_for("index"))

    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("UPDATE images SET ocr_text = ?, filename = ? WHERE filename = ?", (text, new_filename, old_filename))
    conn.commit()
    conn.close()

    return redirect(url_for("index"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)  # LAN-accessible
