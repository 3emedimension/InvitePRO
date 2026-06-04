import os
import uuid
import hashlib
import secrets
from datetime import datetime, timedelta
from functools import wraps

import cloudinary
import cloudinary.uploader
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, abort, jsonify, make_response
)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "invitepro-secret-key-change-in-production")
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=30)

SITE_PASSWORD      = os.environ.get("SITE_PASSWORD", "IP2026")
DATABASE_URL       = os.environ.get("DATABASE_URL")
MAX_CONTENT_LENGTH = 5 * 1024 * 1024
ALLOWED_EXT        = {"png", "jpg", "jpeg", "gif", "webp", "svg"}
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH

cloudinary.config(
    cloud_name = os.environ.get("CLOUDINARY_CLOUD_NAME"),
    api_key    = os.environ.get("CLOUDINARY_API_KEY"),
    api_secret = os.environ.get("CLOUDINARY_API_SECRET"),
    secure     = True,
)

# ── DB ────────────────────────────────────────────────────────────────────────
def get_db():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

def init_db():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id            SERIAL PRIMARY KEY,
                    username      TEXT UNIQUE NOT NULL,
                    display_name  TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at    TEXT NOT NULL
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS invitations (
                    id           SERIAL PRIMARY KEY,
                    user_id      INTEGER REFERENCES users(id) ON DELETE CASCADE,
                    token        TEXT UNIQUE NOT NULL,
                    event_type   TEXT NOT NULL,
                    title        TEXT NOT NULL,
                    organizer    TEXT NOT NULL,
                    event_date   TEXT NOT NULL,
                    event_time   TEXT NOT NULL,
                    location     TEXT NOT NULL,
                    description  TEXT,
                    image_url    TEXT,
                    image_pub_id TEXT,
                    color        TEXT DEFAULT '#6C63FF',
                    style        TEXT DEFAULT 'elegant',
                    status       TEXT DEFAULT 'published',
                    views        INTEGER DEFAULT 0,
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
            cur.execute("""
                CREATE TABLE IF NOT EXISTS rsvps (
                    id            SERIAL PRIMARY KEY,
                    invitation_id INTEGER REFERENCES invitations(id) ON DELETE CASCADE,
                    name          TEXT NOT NULL,
                    created_at    TEXT NOT NULL
                )
            """)
            # Migrations colonnes manquantes
            existing = [r["column_name"] for r in cur.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name='invitations'"
            ) or []]
            cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='invitations'")
            existing = [r["column_name"] for r in cur.fetchall()]
            for col, typ, default in [
                ("status", "TEXT", "'published'"),
                ("views",  "INTEGER", "0"),
            ]:
                if col not in existing:
                    cur.execute(f"ALTER TABLE invitations ADD COLUMN {col} {typ} DEFAULT {default}")
        conn.commit()

init_db()

# ── Auth ──────────────────────────────────────────────────────────────────────
def hash_password(password, salt=None):
    if salt is None:
        salt = secrets.token_hex(16)
    h = hashlib.sha256((salt + password).encode()).hexdigest()
    return f"{salt}:{h}"

def check_password(stored, provided):
    salt, _ = stored.split(":", 1)
    return stored == hash_password(provided, salt)

def site_ok():
    return request.cookies.get("site_ok") == "1"

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not site_ok() or not session.get("user_id"):
            return redirect(url_for("index"))
        return f(*args, **kwargs)
    return decorated

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT

# ── Cloudinary ────────────────────────────────────────────────────────────────
def upload_image(file_storage, old_pub_id=None):
    if not file_storage or not file_storage.filename or not allowed_file(file_storage.filename):
        return None, None
    try:
        if old_pub_id:
            try: cloudinary.uploader.destroy(old_pub_id)
            except: pass
        file_storage.seek(0)
        result = cloudinary.uploader.upload(
            file_storage, folder="invitepro", resource_type="image",
            transformation=[{"width": 1200, "height": 600, "crop": "limit", "quality": "auto:good"}],
        )
        return result["secure_url"], result["public_id"]
    except Exception as e:
        app.logger.error(f"Cloudinary upload error: {e}")
        return None, None

def delete_image(pub_id):
    if pub_id:
        try: cloudinary.uploader.destroy(pub_id)
        except: pass

def collect_form(old_url=None, old_pub_id=None):
    f = request.files.get("image")
    if f and f.filename and allowed_file(f.filename):
        img_url, img_pub_id = upload_image(f, old_pub_id)
    else:
        img_url, img_pub_id = old_url, old_pub_id
    return {
        "event_type":   request.form.get("event_type", ""),
        "title":        request.form.get("title", ""),
        "organizer":    request.form.get("organizer", ""),
        "event_date":   request.form.get("event_date", ""),
        "event_time":   request.form.get("event_time", ""),
        "location":     request.form.get("location", ""),
        "description":  request.form.get("description") or None,
        "image_url":    img_url,
        "image_pub_id": img_pub_id,
        "color":        request.form.get("color", "#6C63FF"),
        "style":        request.form.get("style", "elegant"),
        "status":       request.form.get("status", "published"),
        "dress_code":   request.form.get("dress_code") or None,
        "rsvp_contact": request.form.get("rsvp_contact") or None,
        "rsvp_date":    request.form.get("rsvp_date") or None,
        "website":      request.form.get("website") or None,
        "special_msg":  request.form.get("special_msg") or None,
        "parking":      request.form.get("parking") or None,
        "gift_info":    request.form.get("gift_info") or None,
    }

# ── Route principale ──────────────────────────────────────────────────────────
@app.route("/", methods=["GET", "POST"])
def index():
    if site_ok() and session.get("user_id"):
        return redirect(url_for("dashboard"))
    error_gate = error_login = error_register = None
    mode = request.form.get("mode", "login")
    if request.method == "POST":
        action = request.form.get("action")
        if action == "gate":
            if request.form.get("site_password") == SITE_PASSWORD:
                resp = make_response(redirect(url_for("index")))
                resp.set_cookie("site_ok", "1", max_age=60*60*24*365, httponly=True, samesite="Lax")
                return resp
            error_gate = "Mot de passe incorrect."
        elif action == "login" and site_ok():
            username = request.form.get("username", "").strip().lower()
            password = request.form.get("password", "")
            with get_db() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT * FROM users WHERE username=%s", (username,))
                    user = cur.fetchone()
            if user and check_password(user["password_hash"], password):
                session.permanent = True
                session["user_id"]      = user["id"]
                session["display_name"] = user["display_name"]
                return redirect(url_for("dashboard"))
            error_login = "Identifiant ou mot de passe incorrect."
            mode = "login"
        elif action == "register" and site_ok():
            username     = request.form.get("username", "").strip().lower()
            display_name = request.form.get("display_name", "").strip()
            password     = request.form.get("password", "")
            password2    = request.form.get("password2", "")
            if not username or not display_name or not password:
                error_register = "Tous les champs sont obligatoires."
            elif len(username) < 3:
                error_register = "L'identifiant doit faire au moins 3 caractères."
            elif len(password) < 6:
                error_register = "Le mot de passe doit faire au moins 6 caractères."
            elif password != password2:
                error_register = "Les mots de passe ne correspondent pas."
            else:
                try:
                    with get_db() as conn:
                        with conn.cursor() as cur:
                            cur.execute("INSERT INTO users (username, display_name, password_hash, created_at) VALUES (%s,%s,%s,%s)",
                                (username, display_name, hash_password(password), datetime.now().isoformat(timespec="seconds")))
                        conn.commit()
                    flash("Compte créé ! Connecte-toi.", "success")
                    return redirect(url_for("index"))
                except psycopg2.errors.UniqueViolation:
                    error_register = "Cet identifiant est déjà utilisé."
            mode = "register"
    return render_template("login.html", site_unlocked=site_ok(),
        error_gate=error_gate, error_login=error_login, error_register=error_register, mode=mode)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

# ── Dashboard ─────────────────────────────────────────────────────────────────
@app.route("/dashboard")
@login_required
def dashboard():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT i.*, COUNT(r.id) AS rsvp_count
                FROM invitations i
                LEFT JOIN rsvps r ON r.invitation_id = i.id
                WHERE i.user_id = %s
                GROUP BY i.id
                ORDER BY i.created_at DESC
            """, (session["user_id"],))
            invitations = cur.fetchall()
            # Stats globales
            cur.execute("SELECT COUNT(*) as total, COALESCE(SUM(views),0) as total_views FROM invitations WHERE user_id=%s", (session["user_id"],))
            stats = cur.fetchone()
            cur.execute("SELECT COUNT(*) as total_rsvps FROM rsvps r JOIN invitations i ON r.invitation_id=i.id WHERE i.user_id=%s", (session["user_id"],))
            rsvp_stats = cur.fetchone()
    return render_template("dashboard.html", invitations=invitations, stats=stats, rsvp_stats=rsvp_stats)

# ── Create / Edit ─────────────────────────────────────────────────────────────
@app.route("/create", methods=["GET", "POST"])
@login_required
def create():
    if request.method == "POST":
        token = uuid.uuid4().hex
        d = collect_form()
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO invitations
                      (user_id, token, event_type, title, organizer, event_date, event_time,
                       location, description, image_url, image_pub_id, color, style, status,
                       dress_code, rsvp_contact, rsvp_date, website, special_msg, parking, gift_info, created_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """, (session["user_id"], token, d["event_type"], d["title"], d["organizer"],
                    d["event_date"], d["event_time"], d["location"], d["description"],
                    d["image_url"], d["image_pub_id"], d["color"], d["style"], d["status"],
                    d["dress_code"], d["rsvp_contact"], d["rsvp_date"], d["website"],
                    d["special_msg"], d["parking"], d["gift_info"], datetime.now().isoformat(timespec="seconds")))
            conn.commit()
        flash("Invitation créée avec succès !", "success")
        return redirect(url_for("public_invite", token=token))
    return render_template("create.html")

@app.route("/edit/<token>", methods=["GET", "POST"])
@login_required
def edit(token):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM invitations WHERE token=%s AND user_id=%s", (token, session["user_id"]))
            inv = cur.fetchone()
    if not inv: abort(404)
    if request.method == "POST":
        d = collect_form(inv["image_url"], inv["image_pub_id"])
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE invitations SET
                      event_type=%s, title=%s, organizer=%s, event_date=%s, event_time=%s,
                      location=%s, description=%s, image_url=%s, image_pub_id=%s, color=%s,
                      style=%s, status=%s, dress_code=%s, rsvp_contact=%s, rsvp_date=%s,
                      website=%s, special_msg=%s, parking=%s, gift_info=%s
                    WHERE token=%s AND user_id=%s
                """, (d["event_type"], d["title"], d["organizer"], d["event_date"], d["event_time"],
                    d["location"], d["description"], d["image_url"], d["image_pub_id"], d["color"],
                    d["style"], d["status"], d["dress_code"], d["rsvp_contact"], d["rsvp_date"],
                    d["website"], d["special_msg"], d["parking"], d["gift_info"], token, session["user_id"]))
            conn.commit()
        flash("Invitation mise à jour !", "success")
        return redirect(url_for("public_invite", token=token))
    return render_template("create.html", inv=inv)

@app.route("/delete/<token>", methods=["POST"])
@login_required
def delete(token):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT image_pub_id FROM invitations WHERE token=%s AND user_id=%s", (token, session["user_id"]))
            row = cur.fetchone()
            if row: delete_image(row["image_pub_id"])
            cur.execute("DELETE FROM invitations WHERE token=%s AND user_id=%s", (token, session["user_id"]))
        conn.commit()
    flash("Invitation supprimée.", "info")
    return redirect(url_for("dashboard"))

# ── Toggle statut brouillon/publié ────────────────────────────────────────────
@app.route("/toggle-status/<token>", methods=["POST"])
@login_required
def toggle_status(token):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT status FROM invitations WHERE token=%s AND user_id=%s", (token, session["user_id"]))
            row = cur.fetchone()
            if not row: abort(404)
            new_status = "draft" if row["status"] == "published" else "published"
            cur.execute("UPDATE invitations SET status=%s WHERE token=%s AND user_id=%s", (new_status, token, session["user_id"]))
        conn.commit()
    return jsonify({"status": new_status})

# ── Page publique ─────────────────────────────────────────────────────────────
@app.route("/i/<token>")
def public_invite(token):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM invitations WHERE token=%s", (token,))
            inv = cur.fetchone()
            if not inv: abort(404)
            if inv["status"] == "draft" and inv["user_id"] != session.get("user_id"):
                abort(404)
            # Incrémenter les vues
            cur.execute("UPDATE invitations SET views = COALESCE(views,0) + 1 WHERE id=%s", (inv["id"],))
            cur.execute("SELECT name, created_at FROM rsvps WHERE invitation_id=%s ORDER BY created_at ASC", (inv["id"],))
            rsvps = cur.fetchall()
        conn.commit()
    return render_template("invite_public.html", inv=inv, rsvps=rsvps)

# ── RSVP ──────────────────────────────────────────────────────────────────────
@app.route("/i/<token>/rsvp", methods=["POST"])
def rsvp(token):
    name = request.form.get("name", "").strip()
    if not name:
        return jsonify({"error": "Nom requis"}), 400
    if len(name) > 60:
        return jsonify({"error": "Nom trop long"}), 400
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM invitations WHERE token=%s", (token,))
            inv = cur.fetchone()
            if not inv: abort(404)
            cur.execute("SELECT id FROM rsvps WHERE invitation_id=%s AND LOWER(name)=%s", (inv["id"], name.lower()))
            if cur.fetchone():
                return jsonify({"error": "Ce nom est déjà inscrit !"}), 409
            cur.execute("INSERT INTO rsvps (invitation_id, name, created_at) VALUES (%s,%s,%s) RETURNING id",
                (inv["id"], name, datetime.now().isoformat(timespec="seconds")))
            new_id = cur.fetchone()["id"]
        conn.commit()
    return jsonify({"ok": True, "name": name, "id": new_id})

# ── Liste présents ────────────────────────────────────────────────────────────
@app.route("/dashboard/rsvps/<token>")
@login_required
def view_rsvps(token):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM invitations WHERE token=%s AND user_id=%s", (token, session["user_id"]))
            inv = cur.fetchone()
            if not inv: abort(404)
            cur.execute("SELECT * FROM rsvps WHERE invitation_id=%s ORDER BY created_at ASC", (inv["id"],))
            rsvps = cur.fetchall()
    return render_template("rsvps.html", inv=inv, rsvps=rsvps)

@app.route("/dashboard/rsvps/<token>/delete/<int:rsvp_id>", methods=["POST"])
@login_required
def delete_rsvp(token, rsvp_id):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM invitations WHERE token=%s AND user_id=%s", (token, session["user_id"]))
            inv = cur.fetchone()
            if not inv: abort(404)
            cur.execute("DELETE FROM rsvps WHERE id=%s AND invitation_id=%s", (rsvp_id, inv["id"]))
        conn.commit()
    return jsonify({"ok": True})

@app.errorhandler(404)
def not_found(e):
    return render_template("404.html"), 404

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
