from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session,
    send_from_directory,
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
from datetime import datetime
import html
import uuid

import psycopg2
from psycopg2.extras import RealDictCursor

from supabase import create_client, Client  # supabase-py

# -----------------------------------------------------------------------------
# FLASK APP CONFIG
# -----------------------------------------------------------------------------
app = Flask(__name__)

# Secret key
app.secret_key = os.environ.get("SECRET_KEY", "your-secret-key-here")

# Local upload folder is no longer used for persistence, but keep it for safety
app.config["UPLOAD_FOLDER"] = "static/uploads"
app.config["ALLOWED_EXTENSIONS"] = {"png", "jpg", "jpeg", "gif"}
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # 5MB max file size

os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

# -----------------------------------------------------------------------------
# SUPABASE CONFIG
# -----------------------------------------------------------------------------
SUPABASE_URL = os.environ.get(
    "SUPABASE_URL", "https://japdivjgyqkjougdcahp.supabase.co"
)
SUPABASE_ANON_KEY = os.environ.get(
    "SUPABASE_ANON_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImphcGRpdmpneXFram91Z2RjYWhwIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjM2NDgxMTEsImV4cCI6MjA3OTIyNDExMX0.WO6OttpLkMZNWeQLSOnUYIs9EzjI58GhWvz9iJxJ4no",
)

# Bucket name you must create in Supabase Storage (public bucket)
SUPABASE_BUCKET = os.environ.get("SUPABASE_BUCKET", "blog-images")

# Create Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

# -----------------------------------------------------------------------------
# DATABASE CONFIG (Supabase Postgres)
# -----------------------------------------------------------------------------
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:Adinath72*@db.japdivjgyqkjougdcahp.supabase.co:5432/postgres",
)


def get_db_connection():
    """Get PostgreSQL database connection (Supabase)"""
    conn = psycopg2.connect(
        DATABASE_URL,
        cursor_factory=RealDictCursor,
        sslmode="require",  # important for Supabase
    )
    return conn


# -----------------------------------------------------------------------------
# DATABASE INITIALIZATION
# -----------------------------------------------------------------------------
def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Users table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                is_admin BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # Posts table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS posts (
                id SERIAL PRIMARY KEY,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                category TEXT NOT NULL,
                image_path TEXT,
                author_id INTEGER REFERENCES users(id),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # Messages table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT NOT NULL,
                message TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_read BOOLEAN DEFAULT FALSE
            )
            """
        )

        # Create default admin user
        admin_password = generate_password_hash("admin123")
        cursor.execute(
            """
            INSERT INTO users (username, email, password, is_admin)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (username) DO NOTHING
            """,
            ("admin", "admin@blog.com", admin_password, True),
        )

        conn.commit()
        print("✅ PostgreSQL (Supabase) database initialized successfully!")
        print("✅ Default admin user created (admin / admin123)")

    except Exception as e:
        print(f"❌ Database initialization error: {e}")
        conn.rollback()
    finally:
        conn.close()


# -----------------------------------------------------------------------------
# HELPERS
# -----------------------------------------------------------------------------
def allowed_file(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in app.config["ALLOWED_EXTENSIONS"]
    )


def upload_image_to_supabase(image):
    """
    Uploads a Flask FileStorage object to Supabase Storage.
    Returns the public URL of the uploaded image or None on failure.
    """
    if not image or image.filename == "":
        return None

    if not allowed_file(image.filename):
        raise ValueError("Invalid image format. Allowed: png, jpg, jpeg, gif")

    # Use a unique filename
    filename = secure_filename(image.filename)
    ext = filename.rsplit(".", 1)[1].lower()
    unique_name = f"{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex}.{ext}"

    # Read file bytes
    file_bytes = image.read()

    # Optional: reset stream (not needed later, but safe)
    try:
        image.seek(0)
    except Exception:
        pass

    # Upload to Supabase Storage
    try:
        # path in bucket is just the unique name
        res = supabase.storage.from_(SUPABASE_BUCKET).upload(unique_name, file_bytes)
        # Get public URL
        public_url = supabase.storage.from_(SUPABASE_BUCKET).get_public_url(
            unique_name
        )["signedURL"] if isinstance(
            supabase.storage.from_(SUPABASE_BUCKET).get_public_url(unique_name),
            dict,
        ) else supabase.storage.from_(SUPABASE_BUCKET).get_public_url(unique_name)

        # Newer client sometimes returns string directly; handle both
        if isinstance(public_url, dict) and "publicUrl" in public_url:
            public_url = public_url["publicUrl"]

        return public_url
    except Exception as e:
        print(f"❌ Supabase upload error: {e}")
        return None


# Authentication decorators
def login_required(f):
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to access this page.", "error")
            return redirect(url_for("login"))
        return f(*args, **kwargs)

    decorated_function.__name__ = f.__name__
    return decorated_function


def admin_required(f):
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to access this page.", "error")
            return redirect(url_for("login"))

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT is_admin FROM users WHERE id = %s", (session["user_id"],))
        user = cursor.fetchone()
        conn.close()

        if not user or not user["is_admin"]:
            flash("Admin access required.", "error")
            return redirect(url_for("index"))

        return f(*args, **kwargs)

    decorated_function.__name__ = f.__name__
    return decorated_function


# Helper function to get unread message count
def get_unread_message_count():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as count FROM messages WHERE is_read = FALSE")
    count = cursor.fetchone()["count"]
    conn.close()
    return count


@app.context_processor
def inject_unread_count():
    if session.get("is_admin"):
        return {"unread_count": get_unread_message_count()}
    return {"unread_count": 0}


# Helper function to get image URL
def get_image_url(image_path):
    """
    - If image_path is a full URL (Supabase), return as-is
    - If it's a local filename (old posts), return /static/uploads/...
    """
    if not image_path:
        return None

    if isinstance(image_path, str) and (
        image_path.startswith("http://") or image_path.startswith("https://")
    ):
        return image_path

    # Fallback for old local images
    return url_for("static", filename=f"uploads/{image_path}")


# Helper function to format date
def format_date(date_value, format="%b %d, %Y"):
    if isinstance(date_value, str):
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(date_value, fmt)
                return dt.strftime(format)
            except Exception:
                continue
        return date_value[:10]
    elif isinstance(date_value, datetime):
        return date_value.strftime(format)
    return str(date_value)


# Make the functions available in templates
@app.context_processor
def utility_processor():
    return dict(get_image_url=get_image_url, format_date=format_date)


# -----------------------------------------------------------------------------
# ROUTES
# -----------------------------------------------------------------------------
@app.route("/")
def index():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT p.*, u.username
        FROM posts p
        JOIN users u ON p.author_id = u.id
        ORDER BY p.created_at DESC
        LIMIT 6
    """
    )
    posts = cursor.fetchall()
    conn.close()
    return render_template("index.html", posts=posts)


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        email = request.form["email"]
        password = request.form["password"]
        confirm_password = request.form["confirm_password"]

        if password != confirm_password:
            flash("Passwords do not match!", "error")
            return render_template("register.html")

        hashed_password = generate_password_hash(password)

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO users (username, email, password) VALUES (%s, %s, %s)",
                (username, email, hashed_password),
            )
            conn.commit()
            flash("Registration successful! Please log in.", "success")
            return redirect(url_for("login"))
        except Exception as e:
            flash("Username or email already exists!", "error")
            print(f"Registration error: {e}")
        finally:
            conn.close()

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
        user = cursor.fetchone()
        conn.close()

        if user and check_password_hash(user["password"], password):
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["is_admin"] = user["is_admin"]
            flash(f'Welcome back, {user["username"]}!', "success")
            return redirect(url_for("index"))
        else:
            flash("Invalid username or password!", "error")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out successfully.", "success")
    return redirect(url_for("index"))


@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT p.*, u.username
        FROM posts p
        JOIN users u ON p.author_id = u.id
        ORDER BY p.created_at DESC
    """
    )
    posts = cursor.fetchall()

    cursor.execute("SELECT COUNT(*) as count FROM posts")
    total_posts = cursor.fetchone()["count"]

    cursor.execute("SELECT COUNT(*) as count FROM messages")
    total_messages = cursor.fetchone()["count"]

    cursor.execute("SELECT COUNT(*) as count FROM messages WHERE is_read = FALSE")
    unread_messages = cursor.fetchone()["count"]

    conn.close()

    return render_template(
        "admin_dashboard.html",
        posts=posts,
        total_posts=total_posts,
        total_messages=total_messages,
        unread_messages=unread_messages,
    )


@app.route("/admin/create-post", methods=["GET", "POST"])
@admin_required
def create_post():
    categories = [
        "AboutMe",
        "Esoteric Science",
        "Science and Tech",
        "Indian Culture",
        "Spiritual",
    ]

    if request.method == "POST":
        title = request.form["title"]
        content = request.form["content"]
        category = request.form["category"]
        image = request.files.get("image")

        content = html.escape(content)

        image_path = None
        if image and image.filename != "":
            try:
                image_url = upload_image_to_supabase(image)
                if not image_url:
                    flash("Error uploading image to Supabase.", "error")
                    return render_template("create_post.html", categories=categories)
                image_path = image_url
                flash("Image uploaded successfully!", "success")
            except ValueError as ve:
                flash(str(ve), "error")
                return render_template("create_post.html", categories=categories)
            except Exception as e:
                flash(f"Error saving image: {str(e)}", "error")
                return render_template("create_post.html", categories=categories)

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO posts (title, content, category, image_path, author_id)
                VALUES (%s, %s, %s, %s, %s)
            """,
                (title, content, category, image_path, session["user_id"]),
            )
            conn.commit()
            flash("Post created successfully!", "success")
            return redirect(url_for("admin_dashboard"))
        except Exception as e:
            flash("Error creating post. Please try again.", "error")
            print(f"Database error: {e}")
        finally:
            conn.close()

    return render_template("create_post.html", categories=categories)


@app.route("/admin/edit-post/<int:post_id>", methods=["GET", "POST"])
@admin_required
def edit_post(post_id):
    categories = [
        "AboutMe",
        "Esoteric Science",
        "Science and Tech",
        "Indian Culture",
        "Spiritual",
    ]

    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == "POST":
        title = request.form["title"]
        content = request.form["content"]
        category = request.form["category"]
        image = request.files.get("image")
        remove_image = request.form.get("remove_image")

        content = html.escape(content)

        cursor.execute("SELECT * FROM posts WHERE id = %s", (post_id,))
        current_post = cursor.fetchone()

        if not current_post:
            conn.close()
            flash("Post not found!", "error")
            return redirect(url_for("admin_dashboard"))

        image_path = current_post["image_path"]

        # Handle image removal
        if remove_image == "yes":
            image_path = None  # we won't delete from storage to keep things simple

        # Handle new image upload
        if image and image.filename != "":
            try:
                image_url = upload_image_to_supabase(image)
                if not image_url:
                    flash("Error uploading image to Supabase.", "error")
                    conn.close()
                    return render_template(
                        "edit_post.html", post=current_post, categories=categories
                    )
                image_path = image_url
                flash("Image updated successfully!", "success")
            except ValueError as ve:
                flash(str(ve), "error")
                conn.close()
                return render_template(
                    "edit_post.html", post=current_post, categories=categories
                )
            except Exception as e:
                flash(f"Error saving image: {str(e)}", "error")
                conn.close()
                return render_template(
                    "edit_post.html", post=current_post, categories=categories
                )

        # Update the post
        cursor.execute(
            """
            UPDATE posts
            SET title = %s, content = %s, category = %s, image_path = %s
            WHERE id = %s
        """,
            (title, content, category, image_path, post_id),
        )
        conn.commit()
        conn.close()

        flash("Post updated successfully!", "success")
        return redirect(url_for("admin_dashboard"))

    # GET request - show edit form
    cursor.execute("SELECT * FROM posts WHERE id = %s", (post_id,))
    post = cursor.fetchone()
    conn.close()

    if not post:
        flash("Post not found!", "error")
        return redirect(url_for("admin_dashboard"))

    return render_template("edit_post.html", post=post, categories=categories)


@app.route("/admin/delete-post/<int:post_id>", methods=["POST"])
@admin_required
def delete_post(post_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    # Get post to check for image (we won't delete from Supabase Storage for simplicity)
    cursor.execute("SELECT * FROM posts WHERE id = %s", (post_id,))
    post = cursor.fetchone()

    # Delete the post
    cursor.execute("DELETE FROM posts WHERE id = %s", (post_id,))
    conn.commit()
    conn.close()

    flash("Post deleted successfully!", "success")
    return redirect(url_for("admin_dashboard"))


# ---------------------- Messages Management ----------------------
@app.route("/admin/messages")
@admin_required
def view_messages():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT * FROM messages
        ORDER BY created_at DESC
    """
    )
    messages = cursor.fetchall()
    conn.close()
    return render_template("messages.html", messages=messages)


@app.route("/admin/messages/<int:message_id>/delete", methods=["POST"])
@admin_required
def delete_message(message_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM messages WHERE id = %s", (message_id,))
    conn.commit()
    conn.close()
    flash("Message deleted successfully!", "success")
    return redirect(url_for("view_messages"))


@app.route("/admin/messages/<int:message_id>/toggle-read", methods=["POST"])
@admin_required
def toggle_message_read(message_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT is_read FROM messages WHERE id = %s", (message_id,))
    message = cursor.fetchone()
    new_status = not message["is_read"]
    cursor.execute(
        "UPDATE messages SET is_read = %s WHERE id = %s", (new_status, message_id)
    )
    conn.commit()
    conn.close()
    flash("Message status updated!", "success")
    return redirect(url_for("view_messages"))


@app.route("/admin/messages/mark-all-read", methods=["POST"])
@admin_required
def mark_all_messages_read():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE messages SET is_read = TRUE WHERE is_read = FALSE")
    conn.commit()
    conn.close()
    flash("All messages marked as read!", "success")
    return redirect(url_for("view_messages"))


# ---------------------- Public Views ----------------------
@app.route("/post/<int:post_id>")
@login_required
def view_post(post_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT p.*, u.username
        FROM posts p
        JOIN users u ON p.author_id = u.id
        WHERE p.id = %s
    """,
        (post_id,),
    )
    post = cursor.fetchone()
    conn.close()

    if not post:
        flash("Post not found!", "error")
        return redirect(url_for("index"))

    return render_template("post.html", post=post)


@app.route("/category/<category_name>")
@login_required
def category_posts(category_name):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT p.*, u.username
        FROM posts p
        JOIN users u ON p.author_id = u.id
        WHERE p.category = %s
        ORDER BY p.created_at DESC
    """,
        (category_name,),
    )
    posts = cursor.fetchall()
    conn.close()

    return render_template("categories.html", posts=posts, category=category_name)


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        message_text = request.form["message"]

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO messages (name, email, message) VALUES (%s, %s, %s)",
            (name, email, message_text),
        )
        conn.commit()
        conn.close()

        flash("Thank you for your message! We will get back to you soon.", "success")
        return redirect(url_for("contact"))

    return render_template("contact.html")


# This route is mostly legacy now (images come from Supabase URLs),
# but we keep it in case something still refers to /uploads/...
@app.route("/uploads/<filename>")
def uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)


# -----------------------------------------------------------------------------
# MAIN ENTRY
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    init_db()
    print("\n" + "=" * 50)
    print("🚀 Blog Website Starting with Supabase (PostgreSQL + Storage)")
    print("📝 Admin Login: username 'admin', password 'admin123'")
    print("📧 Messages System: Enabled")
    print("🖼  Images stored in Supabase Storage bucket:", SUPABASE_BUCKET)
    print("🌐 Access: http://127.0.0.1:5000")
    print("=" * 50)
    app.run(debug=True)
