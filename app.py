import os
import uuid
import sqlite3
from datetime import datetime
from functools import wraps
from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, send_from_directory, abort
)
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "invitepro-secret-key-change-in-production")

PASSWORD      = os.environ.get("INVITEPRO_PASSWORD", "invite2024")
DB_PATH       = "invitepro.db"
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads")
ALLOWED_EXT   = {"png", "jpg", "jpeg", "gif", "webp", "svg"}
MAX_CONTENT_LENGTH = 5 * 1024 * 1024

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS invitations (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                token        TEXT UNIQUE NOT NULL,
                event_type   TEXT NOT NULL,
                title        TEXT NOT NULL,
                organizer    TEXT NOT NULL,
                event_date   TEXT NOT NULL,
                event_time   TEXT NOT NULL,
                location     TEXT NOT NULL,
                description  TEXT,
                image_file   TEXT,
                color        TEXT DEFAULT '#6C63FF',
                style        TEXT DEFAULT 'elegant',
                created_at   TEXT NOT NULL,
                dress_code   TEXT,
                rsvp_contact TEXT,
                rsvp_date    TEXT,
                website      TEXT,
                special_msg  TEXT,
                parking      TEXT,
                gift_info    TEXT
            )
        """)
        # Add new columns to existing DBs gracefully
        existing = [r[1] for r in db.execute("PRAGMA table_info(invitations)").fetchall()]
        extras = [
            ("dress_code",   "TEXT"),
            ("rsvp_contact", "TEXT"),
            ("rsvp_date",    "TEXT"),
            ("website",      "TEXT"),
            ("special_msg",  "TEXT"),
            ("parking",      "TEXT"),
            ("gift_info",    "TEXT"),
        ]
        for col, typ in extras:
            if col not in existing:
                db.execute(f"ALTER TABLE invitations ADD COLUMN {col} {typ}")
        db.commit()

init_db()

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("authenticated"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT

@app.route("/", methods=["GET", "POST"])
def login():
    if session.get("authenticated"):
        return redirect(url_for("dashboard"))
    error = None
    if request.method == "POST":
        if request.form.get("password") == PASSWORD:
            session["authenticated"] = True
            return redirect(url_for("dashboard"))
        error = "Mot de passe incorrect."
    return render_template("login.html", error=error)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/dashboard")
@login_required
def dashboard():
    with get_db() as db:
        invitations = db.execute("SELECT * FROM invitations ORDER BY created_at DESC").fetchall()
    return render_template("dashboard.html", invitations=invitations)

def save_image(field_name, old_file=None):
    """Handle image upload, return new filename or old_file."""
    if field_name not in request.files:
        return old_file
    f = request.files[field_name]
    if not f or not f.filename or not allowed_file(f.filename):
        return old_file
    if old_file:
        old_path = os.path.join(app.config["UPLOAD_FOLDER"], old_file)
        if os.path.exists(old_path):
            os.remove(old_path)
    ext = f.filename.rsplit(".", 1)[1].lower()
    name = f"{uuid.uuid4().hex}.{ext}"
    f.save(os.path.join(app.config["UPLOAD_FOLDER"], name))
    return name

def form_data(image_file=None):
    return (
        request.form.get("event_type", ""),
        request.form.get("title", ""),
        request.form.get("organizer", ""),
        request.form.get("event_date", ""),
        request.form.get("event_time", ""),
        request.form.get("location", ""),
        request.form.get("description", "") or None,
        save_image("image", image_file),
        request.form.get("color", "#6C63FF"),
        request.form.get("style", "elegant"),
        request.form.get("dress_code", "") or None,
        request.form.get("rsvp_contact", "") or None,
        request.form.get("rsvp_date", "") or None,
        request.form.get("website", "") or None,
        request.form.get("special_msg", "") or None,
        request.form.get("parking", "") or None,
        request.form.get("gift_info", "") or None,
    )

@app.route("/create", methods=["GET", "POST"])
@login_required
def create():
    if request.method == "POST":
        token = uuid.uuid4().hex
        data = form_data()
        with get_db() as db:
            db.execute("""
                INSERT INTO invitations
                  (token, event_type, title, organizer, event_date, event_time,
                   location, description, image_file, color, style,
                   dress_code, rsvp_contact, rsvp_date, website, special_msg,
                   parking, gift_info, created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (token,) + data + (datetime.now().isoformat(timespec="seconds"),))
            db.commit()
        flash("Invitation créée avec succès !", "success")
        return redirect(url_for("public_invite", token=token))
    return render_template("create.html")

@app.route("/edit/<token>", methods=["GET", "POST"])
@login_required
def edit(token):
    with get_db() as db:
        inv = db.execute("SELECT * FROM invitations WHERE token=?", (token,)).fetchone()
    if not inv:
        abort(404)
    if request.method == "POST":
        data = form_data(inv["image_file"])
        with get_db() as db:
            db.execute("""
                UPDATE invitations SET
                  event_type=?, title=?, organizer=?, event_date=?, event_time=?,
                  location=?, description=?, image_file=?, color=?, style=?,
                  dress_code=?, rsvp_contact=?, rsvp_date=?, website=?,
                  special_msg=?, parking=?, gift_info=?
                WHERE token=?
            """, data + (token,))
            db.commit()
        flash("Invitation mise à jour !", "success")
        return redirect(url_for("public_invite", token=token))
    return render_template("create.html", inv=inv)

@app.route("/delete/<token>", methods=["POST"])
@login_required
def delete(token):
    with get_db() as db:
        inv = db.execute("SELECT * FROM invitations WHERE token=?", (token,)).fetchone()
        if inv and inv["image_file"]:
            path = os.path.join(app.config["UPLOAD_FOLDER"], inv["image_file"])
            if os.path.exists(path):
                os.remove(path)
        db.execute("DELETE FROM invitations WHERE token=?", (token,))
        db.commit()
    flash("Invitation supprimée.", "info")
    return redirect(url_for("dashboard"))

@app.route("/i/<token>")
def public_invite(token):
    with get_db() as db:
        inv = db.execute("SELECT * FROM invitations WHERE token=?", (token,)).fetchone()
    if not inv:
        abort(404)
    return render_template("invite_public.html", inv=inv)

@app.route("/uploads/<filename>")
def uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

@app.errorhandler(404)
def not_found(e):
    return render_template("404.html"), 404

if __name__ == "__main__":
    app.run(debug=True, port=5000)
