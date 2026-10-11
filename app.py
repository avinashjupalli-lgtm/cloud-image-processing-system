import os
import uuid
from io import BytesIO

from flask import Flask, render_template, request, send_from_directory, flash, redirect, url_for
from PIL import Image, ImageEnhance, UnidentifiedImageError
from werkzeug.utils import secure_filename

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
PROCESSED_FOLDER = os.path.join(BASE_DIR, "processed")
ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10 MB

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret-before-production")
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["PROCESSED_FOLDER"] = PROCESSED_FOLDER
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(PROCESSED_FOLDER, exist_ok=True)


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def format_size(num_bytes):
    return f"{num_bytes / 1024:.1f} KB"


@app.errorhandler(413)
def file_too_large(_error):
    flash("The image is too large. Please upload an image smaller than 10 MB.", "error")
    return redirect(url_for("index"))


@app.route("/", methods=["GET", "POST"])
def index():
    result = None

    if request.method == "POST":
        uploaded = request.files.get("image")
        operation = request.form.get("operation", "grayscale")

        if not uploaded or uploaded.filename == "":
            flash("Please choose an image to upload.", "error")
            return redirect(url_for("index"))

        if not allowed_file(uploaded.filename):
            flash("Unsupported file type. Use JPG, JPEG, PNG, or WEBP.", "error")
            return redirect(url_for("index"))

        if operation not in {"grayscale", "compress", "brightness", "resize"}:
            flash("Please select a valid processing operation.", "error")
            return redirect(url_for("index"))

        original_name = secure_filename(uploaded.filename)
        extension = original_name.rsplit(".", 1)[1].lower()
        unique_id = uuid.uuid4().hex
        original_filename = f"{unique_id}_original.{extension}"
        uploaded_path = os.path.join(UPLOAD_FOLDER, original_filename)

        try:
            uploaded.save(uploaded_path)

            # Verify the uploaded content is actually a readable image.
            with Image.open(uploaded_path) as check_image:
                check_image.verify()

            with Image.open(uploaded_path) as source:
                image = source.copy()

            original_size = os.path.getsize(uploaded_path)
            output_format = "JPEG" if extension in {"jpg", "jpeg"} else (
                "PNG" if extension == "png" else "WEBP"
            )

            if operation == "grayscale":
                image = image.convert("L").convert("RGB")
            elif operation == "brightness":
                try:
                    brightness = float(request.form.get("brightness", "1.2"))
                except ValueError:
                    brightness = 1.2
                brightness = max(0.2, min(brightness, 2.0))
                if image.mode not in ("RGB", "L"):
                    image = image.convert("RGB")
                image = ImageEnhance.Brightness(image).enhance(brightness)
            elif operation == "resize":
                try:
                    width = int(request.form.get("width", "800"))
                    height = int(request.form.get("height", "600"))
                except ValueError:
                    width, height = 800, 600
                if not (1 <= width <= 4000 and 1 <= height <= 4000):
                    flash("Width and height must be between 1 and 4000 pixels.", "error")
                    return redirect(url_for("index"))
                image.thumbnail((width, height), Image.Resampling.LANCZOS)
            elif operation == "compress":
                # Compression is saved at a lower JPEG/WEBP quality.
                if image.mode not in ("RGB", "L"):
                    image = image.convert("RGB")
                output_format = "JPEG"

            output_filename = f"{unique_id}_processed.{ 'jpg' if output_format == 'JPEG' else extension }"
            output_path = os.path.join(PROCESSED_FOLDER, output_filename)

            save_options = {}
            if output_format in {"JPEG", "WEBP"}:
                save_options["quality"] = 65 if operation == "compress" else 90
                save_options["optimize"] = True
            elif output_format == "PNG":
                save_options["optimize"] = True

            image.save(output_path, format=output_format, **save_options)
            processed_size = os.path.getsize(output_path)

            result = {
                "original_url": url_for("uploaded_file", filename=original_filename),
                "processed_url": url_for("processed_file", filename=output_filename),
                "download_url": url_for("download_file", filename=output_filename),
                "original_size": format_size(original_size),
                "processed_size": format_size(processed_size),
                "operation": operation.replace("_", " ").title(),
                "saved_percent": max(0, round((original_size - processed_size) / original_size * 100))
                    if original_size else 0,
            }

        except (UnidentifiedImageError, OSError, ValueError):
            flash("This file could not be processed as an image. Please try another image.", "error")
            if os.path.exists(uploaded_path):
                os.remove(uploaded_path)

    return render_template("index.html", result=result)


@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)


@app.route("/processed/<path:filename>")
def processed_file(filename):
    return send_from_directory(PROCESSED_FOLDER, filename)


@app.route("/download/<path:filename>")
def download_file(filename):
    return send_from_directory(PROCESSED_FOLDER, filename, as_attachment=True)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
