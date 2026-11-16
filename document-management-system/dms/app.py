import os, sqlite3, uuid
from datetime import datetime
from functools import wraps
from flask import (Flask, g, render_template, request, redirect, url_for,
                   session, flash, send_from_directory, abort)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

BASE = os.path.abspath(os.path.dirname(__file__))
UPLOAD_DIR = os.path.join(BASE, "uploads")
DB_PATH = os.path.join(BASE, "dms.db")
ALLOWED = {"pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "txt", "csv", "png", "jpg", "jpeg"}

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY", "change-this-in-production"),
    MAX_CONTENT_LENGTH=16 * 1024 * 1024,  # 16 MB
)
os.makedirs(UPLOAD_DIR, exist_ok=True)

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS documents(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id),
  title TEXT NOT NULL,
  category TEXT NOT NULL DEFAULT 'General',
  original_name TEXT NOT NULL,
  stored_name TEXT NOT NULL,
  size INTEGER NOT NULL,
  uploaded_at TEXT NOT NULL);
"""

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(_):
    db = g.pop("db", None)
    if db:
        db.close()

def init_db():
    with sqlite3.connect(DB_PATH) as c:
        c.executescript(SCHEMA)

def login_required(view):
    @wraps(view)
    def wrapped(*a, **kw):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return view(*a, **kw)
    return wrapped

def allowed(name):
    return "." in name and name.rsplit(".", 1)[1].lower() in ALLOWED

# ---------- Auth ----------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        u = request.form["username"].strip()
        p = request.form["password"]
        if not u or len(p) < 6:
            flash("Username required and password must be at least 6 characters.")
        else:
            try:
                get_db().execute("INSERT INTO users(username,password_hash) VALUES(?,?)",
                                 (u, generate_password_hash(p)))
                get_db().commit()
                flash("Account created. Please log in.")
                return redirect(url_for("login"))
            except sqlite3.IntegrityError:
                flash("Username already taken.")
    return render_template("auth.html", title="Register")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        row = get_db().execute("SELECT * FROM users WHERE username=?",
                               (request.form["username"].strip(),)).fetchone()
        if row and check_password_hash(row["password_hash"], request.form["password"]):
            session.clear()
            session["user_id"], session["username"] = row["id"], row["username"]
            return redirect(url_for("index"))
        flash("Invalid username or password.")
    return render_template("auth.html", title="Login")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ---------- Documents ----------
@app.route("/")
@login_required
def index():
    q = request.args.get("q", "").strip()
    cat = request.args.get("category", "").strip()
    sql = "SELECT * FROM documents WHERE user_id=?"
    args = [session["user_id"]]
    if q:
        sql += " AND (title LIKE ? OR original_name LIKE ?)"
        args += [f"%{q}%", f"%{q}%"]
    if cat:
        sql += " AND category=?"
        args.append(cat)
    docs = get_db().execute(sql + " ORDER BY uploaded_at DESC", args).fetchall()
    cats = [r[0] for r in get_db().execute(
        "SELECT DISTINCT category FROM documents WHERE user_id=?", (session["user_id"],))]
    return render_template("index.html", docs=docs, cats=cats, q=q, cat=cat)

@app.route("/upload", methods=["POST"])
@login_required
def upload():
    f = request.files.get("file")
    if not f or not f.filename:
        flash("Choose a file to upload.")
        return redirect(url_for("index"))
    if not allowed(f.filename):
        flash("File type not allowed.")
        return redirect(url_for("index"))
    original = secure_filename(f.filename)
    stored = f"{uuid.uuid4().hex}_{original}"
    path = os.path.join(UPLOAD_DIR, stored)
    f.save(path)
    db = get_db()
    db.execute("""INSERT INTO documents(user_id,title,category,original_name,stored_name,size,uploaded_at)
                  VALUES(?,?,?,?,?,?,?)""",
               (session["user_id"],
                request.form.get("title", "").strip() or original,
                request.form.get("category", "").strip() or "General",
                original, stored, os.path.getsize(path),
                datetime.now().strftime("%Y-%m-%d %H:%M")))
    db.commit()
    flash("Document uploaded.")
    return redirect(url_for("index"))

def own_doc(doc_id):
    d = get_db().execute("SELECT * FROM documents WHERE id=? AND user_id=?",
                         (doc_id, session["user_id"])).fetchone()
    if not d:
        abort(404)
    return d

@app.route("/download/<int:doc_id>")
@login_required
def download(doc_id):
    d = own_doc(doc_id)
    return send_from_directory(UPLOAD_DIR, d["stored_name"], as_attachment=True,
                               download_name=d["original_name"])

@app.route("/delete/<int:doc_id>", methods=["POST"])
@login_required
def delete(doc_id):
    d = own_doc(doc_id)
    try:
        os.remove(os.path.join(UPLOAD_DIR, d["stored_name"]))
    except FileNotFoundError:
        pass
    get_db().execute("DELETE FROM documents WHERE id=?", (doc_id,))
    get_db().commit()
    flash("Document deleted.")
    return redirect(url_for("index"))

@app.template_filter("filesize")
def filesize(n):
    for unit in ("B", "KB", "MB"):
        if n < 1024:
            return f"{n:.0f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"

init_db()
if __name__ == "__main__":
    app.run(debug=True)
