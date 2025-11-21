# -------------------------------------------------------------
# FULL ADVANCED APP.PY — PURE SUPABASE VERSION
# -------------------------------------------------------------
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session,
    send_from_directory
)
from supabase import create_client
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os, uuid, html
from datetime import datetime

# -------------------------------------------------------------
# FLASK APP CORE CONFIG
# -------------------------------------------------------------
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "fallback-secret-key-12345")

app.config["UPLOAD_FOLDER"] = "static/uploads"
app.config["ALLOWED_EXTENSIONS"] = {"png", "jpg", "jpeg", "gif"}
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

# -------------------------------------------------------------
# SUPABASE CONFIG
# -------------------------------------------------------------
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")  # For bypassing RLS

# Initialize Supabase clients
if SUPABASE_URL and SUPABASE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
else:
    # Fallback for development
    supabase = None

# Use service key for admin operations to bypass RLS
if SUPABASE_SERVICE_KEY:
    supabase_admin = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
else:
    supabase_admin = supabase

STORAGE_BUCKET = "blog-images"

# -------------------------------------------------------------
# HELPERS
# -------------------------------------------------------------
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in app.config["ALLOWED_EXTENSIONS"]


def upload_image_to_supabase(image):
    if not image or image.filename == "":
        return None

    if not allowed_file(image.filename):
        raise ValueError("Invalid image format")

    filename = secure_filename(image.filename)
    ext = filename.rsplit(".", 1)[1].lower()

    unique_name = f"{uuid.uuid4().hex}.{ext}"
    file_bytes = image.read()

    try:
        supabase.storage.from_(STORAGE_BUCKET).upload(unique_name, file_bytes)
        return supabase.storage.from_(STORAGE_BUCKET).get_public_url(unique_name)
    except Exception as e:
        print(f"Image upload error: {e}")
        return None


def login_required(f):
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            flash("Please login first.", "error")
            return redirect(url_for("login"))
        return f(*args, **kwargs)

    wrapper.__name__ = f.__name__
    return wrapper


def admin_required(f):
    def wrapper(*args, **kwargs):
        if "user_id" not in session or not session.get("is_admin"):
            flash("Admin access required.", "error")
            return redirect(url_for("index"))
        return f(*args, **kwargs)

    wrapper.__name__ = f.__name__
    return wrapper


def format_date(dt):
    try:
        return datetime.fromisoformat(dt.replace("Z", "")).strftime("%b %d, %Y")
    except:
        return dt


@app.context_processor
def inject_utils():
    return dict(format_date=format_date)


# -------------------------------------------------------------
# ROUTES — PUBLIC
# -------------------------------------------------------------
@app.route("/")
def index():
    try:
        posts = (
            supabase.table("posts")
            .select("*, users(username)")
            .order("created_at", desc=True)
            .limit(6)
            .execute()
            .data
        )
        return render_template("index.html", posts=posts)
    except Exception as e:
        print(f"Index error: {e}")
        return render_template("index.html", posts=[])


@app.route("/about")
def about():
    """About page route"""
    try:
        about_posts = (
            supabase.table("posts")
            .select("*, users(username)")
            .eq("category", "AboutMe")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
            .data
        )
        
        about_post = about_posts[0] if about_posts else None
        return render_template("about.html", about_post=about_post)
    except Exception as e:
        print(f"About error: {e}")
        return render_template("about.html", about_post=None)


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        data = request.form
        
        # Check if username already exists
        try:
            exists = (
                supabase.table("users")
                .select("*")
                .eq("username", data["username"])
                .execute()
                .data
            )
            if exists:
                flash("Username already taken.", "error")
                return redirect(url_for("register"))

            # Use service role key to bypass RLS with updated password method
            hashed = generate_password_hash(data["password"], method='scrypt')
            user_data = {
                "username": data["username"],
                "email": data["email"],
                "password": hashed,
                "is_admin": False,
                "created_at": datetime.utcnow().isoformat()
            }
            
            # Use admin client with service role key to bypass RLS
            result = supabase_admin.table("users").insert(user_data).execute()
            
            if result.data:
                flash("Registered successfully.", "success")
                return redirect(url_for("login"))
            else:
                flash("Registration failed. Please try again.", "error")
                
        except Exception as e:
            flash(f"Registration error: {str(e)}", "error")
            return redirect(url_for("register"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        data = request.form
        
        try:
            # Traditional login method with password fix
            user = (
                supabase.table("users")
                .select("*")
                .eq("username", data["username"])
                .execute()
                .data
            )
            
            if not user:
                flash("Invalid username or password.", "error")
                return redirect(url_for("login"))

            user = user[0]

            # Check password
            if check_password_hash(user["password"], data["password"]):
                session["user_id"] = user["id"]
                session["username"] = user["username"]
                session["is_admin"] = user["is_admin"]
                flash("Login successful!", "success")
                return redirect(url_for("index"))
            else:
                flash("Invalid username or password.", "error")
                return redirect(url_for("login"))
                
        except Exception as e:
            print(f"Login error: {e}")
            flash("Login error. Please try again.", "error")
            return redirect(url_for("login"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out.", "success")
    return redirect(url_for("index"))


# -------------------------------------------------------------
# ROUTES — POSTS
# -------------------------------------------------------------
@app.route("/post/<int:id>")
@login_required
def view_post(id):
    try:
        post = (
            supabase.table("posts")
            .select("*, users(username)")
            .eq("id", id)
            .execute()
            .data
        )

        if not post:
            flash("Post not found.", "error")
            return redirect(url_for("index"))

        return render_template("post.html", post=post[0])
    except Exception as e:
        flash("Error loading post.", "error")
        return redirect(url_for("index"))


@app.route("/category/<category>")
@login_required
def view_category(category):
    try:
        posts = (
            supabase.table("posts")
            .select("*, users(username)")
            .eq("category", category)
            .order("created_at", desc=True)
            .execute()
            .data
        )
        return render_template("categories.html", posts=posts, category=category)
    except Exception as e:
        return render_template("categories.html", posts=[], category=category)


@app.route("/category_posts/<category_name>")
@login_required
def category_posts(category_name):
    """Alternative category route that matches the template"""
    try:
        posts = (
            supabase.table("posts")
            .select("*, users(username)")
            .eq("category", category_name)
            .order("created_at", desc=True)
            .execute()
            .data
        )
        return render_template("categories.html", posts=posts, category=category_name)
    except Exception as e:
        return render_template("categories.html", posts=[], category=category_name)


# -------------------------------------------------------------
# CONTACT MESSAGE
# -------------------------------------------------------------
@app.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "POST":
        data = request.form
        try:
            supabase.table("messages").insert({
                "name": data["name"],
                "email": data["email"],
                "message": data["message"],
                "created_at": datetime.utcnow().isoformat(),
                "is_read": False
            }).execute()

            flash("Message sent!", "success")
            return redirect(url_for("contact"))
        except Exception as e:
            flash("Error sending message.", "error")
            return redirect(url_for("contact"))

    return render_template("contact.html")


# -------------------------------------------------------------
# USER MESSAGES ROUTE (FIXES THE MISSING ROUTE)
# -------------------------------------------------------------
@app.route("/view_messages")
@login_required
def view_messages():
    """User messages route - fixes the missing endpoint"""
    try:
        # For regular users, show their own messages or a simplified view
        if session.get("is_admin"):
            return redirect(url_for("admin_messages"))
        else:
            # For regular users, show a simple message page
            return render_template("user_messages.html")
    except Exception as e:
        flash("Error loading messages.", "error")
        return redirect(url_for("index"))


# -------------------------------------------------------------
# ADMIN FIX ROUTE (TEMPORARY - REMOVE AFTER USE)
# -------------------------------------------------------------
@app.route("/fix-admin")
def fix_admin():
    """Create or update admin user with correct password hash"""
    try:
        # Check if admin already exists
        existing_admin = (
            supabase_admin.table("users")
            .select("*")
            .eq("username", "ajainhr")
            .execute()
            .data
        )
        
        hashed_password = generate_password_hash("Adinath72*", method='scrypt')
        
        if existing_admin:
            # Update existing user
            result = supabase_admin.table("users").update({
                "password": hashed_password,
                "is_admin": True,
                "email": "hritikmasai@gmail.com"
            }).eq("username", "ajainhr").execute()
            
            if result.data:
                return '''
                <h1>Admin user updated successfully!</h1>
                <p><strong>Username:</strong> ajainhr</p>
                <p><strong>Email:</strong> hritikmasai@gmail.com</p>
                <p><strong>Password:</strong> Adinath72*</p>
                <p><strong>Now try logging in again</strong></p>
                <a href="/login">Go to Login</a>
                '''
            else:
                return "Failed to update admin user"
        else:
            # Create new admin user
            admin_data = {
                "username": "ajainhr",
                "email": "hritikmasai@gmail.com",
                "password": hashed_password,
                "is_admin": True,
                "created_at": datetime.utcnow().isoformat()
            }
            
            result = supabase_admin.table("users").insert(admin_data).execute()
            
            if result.data:
                return '''
                <h1>Admin user created successfully!</h1>
                <p><strong>Username:</strong> ajainhr</p>
                <p><strong>Email:</strong> hritikmasai@gmail.com</p>
                <p><strong>Password:</strong> Adinath72*</p>
                <p><strong>Now try logging in</strong></p>
                <a href="/login">Go to Login</a>
                '''
            else:
                return "Failed to create admin user"
            
    except Exception as e:
        return f"Error: {str(e)}"


# -------------------------------------------------------------
# ADMIN DASHBOARD
# -------------------------------------------------------------
@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():
    try:
        posts = supabase.table("posts").select("*").order("created_at", desc=True).execute().data
        total_posts = len(posts)

        messages = supabase.table("messages").select("*").execute().data
        total_messages = len(messages)
        unread_messages = sum(1 for m in messages if not m["is_read"])

        return render_template(
            "admin_dashboard.html",
            posts=posts,
            total_posts=total_posts,
            total_messages=total_messages,
            unread_messages=unread_messages,
        )
    except Exception as e:
        flash("Error loading admin dashboard.", "error")
        return redirect(url_for("index"))


# -------------------------------------------------------------
# ADMIN — CREATE POST
# -------------------------------------------------------------
@app.route("/admin/create-post", methods=["GET", "POST"])
@admin_required
def create_post():
    categories = ["AboutMe", "Esoteric Science", "Science and Tech", "Indian Culture", "Spiritual"]

    if request.method == "POST":
        data = request.form
        image = request.files.get("image")
        img_url = upload_image_to_supabase(image)

        try:
            supabase.table("posts").insert({
                "title": data["title"],
                "content": html.escape(data["content"]),
                "category": data["category"],
                "image_path": img_url,
                "author_id": session["user_id"],
                "created_at": datetime.utcnow().isoformat()
            }).execute()

            flash("Post created!", "success")
            return redirect(url_for("admin_dashboard"))
        except Exception as e:
            flash("Error creating post.", "error")
            return redirect(url_for("create_post"))

    return render_template("create_post.html", categories=categories)


# -------------------------------------------------------------
# ADMIN — EDIT POST
# -------------------------------------------------------------
@app.route("/admin/edit-post/<int:id>", methods=["GET", "POST"])
@admin_required
def edit_post(id):
    categories = ["AboutMe", "Esoteric Science", "Science and Tech", "Indian Culture", "Spiritual"]

    try:
        post = supabase.table("posts").select("*").eq("id", id).execute().data
        if not post:
            flash("Post not found.", "error")
            return redirect(url_for("admin_dashboard"))

        post = post[0]

        if request.method == "POST":
            data = request.form
            image = request.files.get("image")
            img_url = post["image_path"]

            if data.get("remove_image") == "yes":
                img_url = None

            if image and image.filename != "":
                img_url = upload_image_to_supabase(image)

            supabase.table("posts").update({
                "title": data["title"],
                "content": html.escape(data["content"]),
                "category": data["category"],
                "image_path": img_url
            }).eq("id", id).execute()

            flash("Post updated.", "success")
            return redirect(url_for("admin_dashboard"))

        return render_template("edit_post.html", post=post, categories=categories)
    except Exception as e:
        flash("Error loading post for editing.", "error")
        return redirect(url_for("admin_dashboard"))


# -------------------------------------------------------------
# ADMIN — DELETE POST
# -------------------------------------------------------------
@app.route("/admin/delete-post/<int:id>", methods=["POST"])
@admin_required
def delete_post(id):
    try:
        supabase.table("posts").delete().eq("id", id).execute()
        flash("Post deleted.", "success")
    except Exception as e:
        flash("Error deleting post.", "error")
    return redirect(url_for("admin_dashboard"))


# -------------------------------------------------------------
# ADMIN — MESSAGES
# -------------------------------------------------------------
@app.route("/admin/messages")
@admin_required
def admin_messages():
    try:
        msgs = supabase.table("messages").select("*").order("created_at", desc=True).execute().data
        return render_template("messages.html", messages=msgs)
    except Exception as e:
        return render_template("messages.html", messages=[])


@app.route("/admin/messages/<int:id>/delete", methods=["POST"])
@admin_required
def delete_message(id):
    try:
        supabase.table("messages").delete().eq("id", id).execute()
        flash("Message deleted.", "success")
    except Exception as e:
        flash("Error deleting message.", "error")
    return redirect(url_for("admin_messages"))


@app.route("/admin/messages/<int:id>/toggle-read", methods=["POST"])
@admin_required
def toggle_message(id):
    try:
        msg = supabase.table("messages").select("*").eq("id", id).execute().data[0]
        supabase.table("messages").update({"is_read": not msg["is_read"]}).eq("id", id).execute()
        flash("Updated.", "success")
    except Exception as e:
        flash("Error updating message.", "error")
    return redirect(url_for("admin_messages"))


@app.route("/admin/messages/mark-all-read", methods=["POST"])
@admin_required
def mark_all_read():
    try:
        supabase.table("messages").update({"is_read": True}).neq("is_read", True).execute()
        flash("All messages marked read.", "success")
    except Exception as e:
        flash("Error marking messages as read.", "error")
    return redirect(url_for("admin_messages"))


# -------------------------------------------------------------
# STATIC FILE FIXES
# -------------------------------------------------------------
@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'),
                             'favicon.ico', mimetype='image/vnd.microsoft.icon')

@app.route('/static/script.js')
def serve_script():
    # Create a basic script.js if it doesn't exist
    script_path = os.path.join(app.root_path, 'static', 'script.js')
    if not os.path.exists(script_path):
        # Create a minimal script.js file
        with open(script_path, 'w') as f:
            f.write('// JavaScript file\nconsole.log("Blog website loaded");')
    
    return send_from_directory(os.path.join(app.root_path, 'static'), 'script.js')

# -------------------------------------------------------------
# ERROR HANDLERS (FIXED - NO TEMPLATE DEPENDENCY)
# -------------------------------------------------------------
@app.errorhandler(404)
def not_found_error(error):
    return '''
    <h1>404 - Page Not Found</h1>
    <p>The page you are looking for does not exist.</p>
    <a href="/">Go Home</a>
    ''', 404

@app.errorhandler(500)
def internal_error(error):
    return '''
    <h1>500 - Internal Server Error</h1>
    <p>Something went wrong on our end. Please try again later.</p>
    <a href="/">Go Home</a>
    ''', 500

# -------------------------------------------------------------
# RUN SERVER
# -------------------------------------------------------------
if __name__ == "__main__":
    app.run(debug=True)
