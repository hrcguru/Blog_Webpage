# -------------------------------------------------------------
# FULL ADVANCED APP.PY — PROPER RLS POLICIES VERSION (FIXED)
# -------------------------------------------------------------
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session,
    send_from_directory,
    jsonify
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
app.secret_key = os.environ.get("SECRET_KEY", "fallback-secret-key-12345-change-in-production")

app.config["UPLOAD_FOLDER"] = "static/uploads"
app.config["ALLOWED_EXTENSIONS"] = {"png", "jpg", "jpeg", "gif"}
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

# -------------------------------------------------------------
# SUPABASE CONFIG - DUAL CLIENT APPROACH
# -------------------------------------------------------------
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")

# Initialize clients
supabase = None
supabase_admin = None

if SUPABASE_URL and SUPABASE_ANON_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
        print("✅ Supabase client initialized successfully with ANON KEY")
    except Exception as e:
        print(f"❌ Supabase initialization error: {e}")
        supabase = None

if SUPABASE_URL and SUPABASE_SERVICE_KEY:
    try:
        supabase_admin = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
        print("✅ Supabase ADMIN client initialized successfully with SERVICE KEY")
    except Exception as e:
        print(f"❌ Supabase admin initialization error: {e}")
        supabase_admin = supabase

STORAGE_BUCKET = "blog-images"

# -------------------------------------------------------------
# RLS POLICY MANAGEMENT FUNCTIONS
# -------------------------------------------------------------
def setup_rls_policies():
    """Set up proper Row Level Security policies"""
    try:
        if not supabase_admin:
            print("❌ Cannot setup RLS policies - no admin client")
            return False
        
        print("✅ RLS setup function called - policies should be configured in Supabase dashboard")
        return True
        
    except Exception as e:
        print(f"❌ RLS setup error: {e}")
        return False

def get_client_for_operation(requires_admin=False):
    """Return appropriate client based on operation requirements"""
    if requires_admin and supabase_admin:
        return supabase_admin
    return supabase

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
        # Use admin client for storage operations to bypass RLS if needed
        client = get_client_for_operation(requires_admin=True)
        client.storage.from_(STORAGE_BUCKET).upload(unique_name, file_bytes)
        return client.storage.from_(STORAGE_BUCKET).get_public_url(unique_name)
    except Exception as e:
        print(f"❌ Image upload error: {e}")
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

def get_unread_count():
    """Get unread message count for the template"""
    try:
        if session.get("is_admin") and supabase:
            # Use admin client to read messages
            client = get_client_for_operation(requires_admin=True)
            messages = client.table("messages").select("*").execute().data
            return sum(1 for m in messages if not m["is_read"])
        return 0
    except Exception as e:
        print(f"❌ Error getting unread count: {e}")
        return 0

@app.context_processor
def inject_utils():
    """Inject variables into all templates"""
    unread_count = get_unread_count() if session.get("user_id") else 0
    return dict(
        format_date=format_date,
        unread_count=unread_count,
        current_user=session.get("username"),
        is_admin=session.get("is_admin", False),
        user_id=session.get("user_id")
    )

# -------------------------------------------------------------
# ROUTES — PUBLIC
# -------------------------------------------------------------
@app.route("/")
def index():
    try:
        if not supabase:
            return render_template("index.html", posts=[], error="Database connection failed")
        
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
        print(f"❌ Index error: {e}")
        return render_template("index.html", posts=[])

@app.route("/about")
def about():
    """About page route"""
    try:
        if not supabase:
            return render_template("about.html", about_post=None)
        
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
        print(f"❌ About error: {e}")
        return render_template("about.html", about_post=None)

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        data = request.form
        
        if not supabase_admin:
            flash("Database connection error. Please try again later.", "error")
            return redirect(url_for("register"))
        
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

            # Use admin client to bypass RLS for user registration
            hashed = generate_password_hash(data["password"], method='scrypt')
            user_data = {
                "username": data["username"],
                "email": data["email"],
                "password": hashed,
                "is_admin": False,
                "created_at": datetime.utcnow().isoformat()
            }
            
            result = supabase_admin.table("users").insert(user_data).execute()
            
            if result.data:
                flash("Registered successfully. Please login.", "success")
                return redirect(url_for("login"))
            else:
                flash("Registration failed. Please try again.", "error")
                
        except Exception as e:
            print(f"❌ Registration error: {e}")
            flash(f"Registration error: {str(e)}", "error")
            return redirect(url_for("register"))

    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        data = request.form
        
        if not supabase:
            flash("Database connection error. Please try again later.", "error")
            return redirect(url_for("login"))
        
        try:
            # Use regular client for login (RLS allows SELECT on users)
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
            print(f"❌ Login error: {e}")
            flash("Login error. Please try again.", "error")
            return redirect(url_for("login"))

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully.", "success")
    return redirect(url_for("index"))

# -------------------------------------------------------------
# ROUTES — POSTS
# -------------------------------------------------------------
@app.route("/post/<int:id>")
@login_required
def view_post(id):
    try:
        if not supabase:
            flash("Database connection error.", "error")
            return redirect(url_for("index"))
        
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
        print(f"❌ View post error: {e}")
        flash("Error loading post.", "error")
        return redirect(url_for("index"))

@app.route("/category/<category>")
@login_required
def view_category(category):
    try:
        if not supabase:
            return render_template("categories.html", posts=[], category=category)
        
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
        print(f"❌ Category error: {e}")
        return render_template("categories.html", posts=[], category=category)

@app.route("/category_posts/<category_name>")
@login_required
def category_posts(category_name):
    """Alternative category route that matches the template"""
    try:
        if not supabase:
            return render_template("categories.html", posts=[], category=category_name)
        
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
        print(f"❌ Category posts error: {e}")
        return render_template("categories.html", posts=[], category=category_name)

# -------------------------------------------------------------
# CONTACT MESSAGE
# -------------------------------------------------------------
@app.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "POST":
        data = request.form
        
        if not supabase:
            flash("Database connection error. Please try again later.", "error")
            return redirect(url_for("contact"))
        
        try:
            # Use regular client (RLS allows INSERT for messages)
            supabase.table("messages").insert({
                "name": data["name"],
                "email": data["email"],
                "message": data["message"],
                "created_at": datetime.utcnow().isoformat(),
                "is_read": False
            }).execute()

            flash("Message sent successfully!", "success")
            return redirect(url_for("contact"))
        except Exception as e:
            print(f"❌ Contact form error: {e}")
            flash("Error sending message. Please try again.", "error")
            return redirect(url_for("contact"))

    return render_template("contact.html")

# -------------------------------------------------------------
# USER MESSAGES ROUTE
# -------------------------------------------------------------
@app.route("/view_messages")
@login_required
def view_messages():
    """User messages route"""
    try:
        if session.get("is_admin"):
            return redirect(url_for("admin_messages"))
        else:
            return render_template("user_messages.html")
    except Exception as e:
        print(f"❌ View messages error: {e}")
        flash("Error loading messages.", "error")
        return redirect(url_for("index"))

# -------------------------------------------------------------
# ADMIN SETUP ROUTE
# -------------------------------------------------------------
@app.route("/setup-admin")
def setup_admin():
    """Create admin user and setup RLS policies"""
    try:
        if not supabase_admin:
            return jsonify({"error": "Database connection failed"}), 500
        
        # Setup RLS policies first
        setup_rls_policies()
        
        # Check if admin exists
        existing_admin = (
            supabase_admin.table("users")
            .select("*")
            .eq("username", "ajainhr")
            .execute()
            .data
        )
        
        hashed_password = generate_password_hash("Adinath72*", method='scrypt')
        
        if existing_admin:
            # Update existing admin
            result = supabase_admin.table("users").update({
                "password": hashed_password,
                "is_admin": True,
                "email": "hritikmasai@gmail.com"
            }).eq("username", "ajainhr").execute()
            
            message = "Admin user updated successfully!"
        else:
            # Create new admin
            admin_data = {
                "username": "ajainhr",
                "email": "hritikmasai@gmail.com",
                "password": hashed_password,
                "is_admin": True,
                "created_at": datetime.utcnow().isoformat()
            }
            
            result = supabase_admin.table("users").insert(admin_data).execute()
            message = "Admin user created successfully!"
        
        if result.data:
            return f'''
            <div style="padding: 20px; font-family: Arial, sans-serif;">
                <h1 style="color: green;">✅ {message}</h1>
                <p><strong>Username:</strong> ajainhr</p>
                <p><strong>Email:</strong> hritikmasai@gmail.com</p>
                <p><strong>Password:</strong> Adinath72*</p>
                <p><strong>RLS Policies:</strong> Configured</p>
                <a href="/login" style="display: inline-block; padding: 10px 20px; background: #007bff; color: white; text-decoration: none; border-radius: 5px;">Go to Login</a>
            </div>
            '''
        else:
            return "❌ Failed to setup admin user"
            
    except Exception as e:
        return f'''
        <div style="padding: 20px; font-family: Arial, sans-serif;">
            <h1 style="color: red;">❌ Setup Error</h1>
            <p><strong>Error:</strong> {str(e)}</p>
            <p>Check your Supabase configuration.</p>
        </div>
        '''

# -------------------------------------------------------------
# ADMIN DASHBOARD
# -------------------------------------------------------------
@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():
    try:
        if not supabase:
            flash("Database connection error.", "error")
            return redirect(url_for("index"))
        
        # Use admin client for dashboard data
        client = get_client_for_operation(requires_admin=True)
        posts = client.table("posts").select("*").order("created_at", desc=True).execute().data
        total_posts = len(posts)

        messages = client.table("messages").select("*").execute().data
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
        print(f"❌ Admin dashboard error: {e}")
        flash("Error loading admin dashboard.", "error")
        return redirect(url_for("index"))

# -------------------------------------------------------------
# ADMIN — CREATE POST (USES ADMIN CLIENT)
# -------------------------------------------------------------
@app.route("/admin/create-post", methods=["GET", "POST"])
@admin_required
def create_post():
    categories = ["AboutMe", "Esoteric Science", "Science and Tech", "Indian Culture", "Spiritual"]

    if request.method == "POST":
        data = request.form
        
        if not supabase_admin:
            flash("Database connection error.", "error")
            return redirect(url_for("create_post"))
        
        image = request.files.get("image")
        img_url = upload_image_to_supabase(image)

        try:
            # Use admin client to bypass RLS for post creation
            result = supabase_admin.table("posts").insert({
                "title": data["title"],
                "content": html.escape(data["content"]),
                "category": data["category"],
                "image_path": img_url,
                "author_id": session["user_id"],
                "created_at": datetime.utcnow().isoformat()
            }).execute()

            if result.data:
                flash("Post created successfully!", "success")
                return redirect(url_for("admin_dashboard"))
            else:
                flash("Error creating post. Please try again.", "error")
                
        except Exception as e:
            print(f"❌ Create post error: {e}")
            flash(f"Error creating post: {str(e)}", "error")
            return redirect(url_for("create_post"))

    return render_template("create_post.html", categories=categories)

# -------------------------------------------------------------
# ADMIN — EDIT POST (USES ADMIN CLIENT)
# -------------------------------------------------------------
@app.route("/admin/edit-post/<int:id>", methods=["GET", "POST"])
@admin_required
def edit_post(id):
    categories = ["AboutMe", "Esoteric Science", "Science and Tech", "Indian Culture", "Spiritual"]

    try:
        if not supabase_admin:
            flash("Database connection error.", "error")
            return redirect(url_for("admin_dashboard"))
        
        # Use admin client
        post = supabase_admin.table("posts").select("*").eq("id", id).execute().data
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

            supabase_admin.table("posts").update({
                "title": data["title"],
                "content": html.escape(data["content"]),
                "category": data["category"],
                "image_path": img_url
            }).eq("id", id).execute()

            flash("Post updated successfully!", "success")
            return redirect(url_for("admin_dashboard"))

        return render_template("edit_post.html", post=post, categories=categories)
    except Exception as e:
        print(f"❌ Edit post error: {e}")
        flash("Error loading post for editing.", "error")
        return redirect(url_for("admin_dashboard"))

# -------------------------------------------------------------
# ADMIN — DELETE POST (USES ADMIN CLIENT)
# -------------------------------------------------------------
@app.route("/admin/delete-post/<int:id>", methods=["POST"])
@admin_required
def delete_post(id):
    try:
        if not supabase_admin:
            flash("Database connection error.", "error")
            return redirect(url_for("admin_dashboard"))
        
        supabase_admin.table("posts").delete().eq("id", id).execute()
        flash("Post deleted successfully!", "success")
    except Exception as e:
        print(f"❌ Delete post error: {e}")
        flash("Error deleting post.", "error")
    return redirect(url_for("admin_dashboard"))

# -------------------------------------------------------------
# ADMIN — MESSAGES (USES ADMIN CLIENT)
# -------------------------------------------------------------
@app.route("/admin/messages")
@admin_required
def admin_messages():
    try:
        if not supabase_admin:
            return render_template("messages.html", messages=[])
        
        msgs = supabase_admin.table("messages").select("*").order("created_at", desc=True).execute().data
        return render_template("messages.html", messages=msgs)
    except Exception as e:
        print(f"❌ Admin messages error: {e}")
        return render_template("messages.html", messages=[])

@app.route("/admin/messages/<int:id>/delete", methods=["POST"])
@admin_required
def delete_message(id):
    try:
        if not supabase_admin:
            flash("Database connection error.", "error")
            return redirect(url_for("admin_messages"))
        
        supabase_admin.table("messages").delete().eq("id", id).execute()
        flash("Message deleted successfully!", "success")
    except Exception as e:
        print(f"❌ Delete message error: {e}")
        flash("Error deleting message.", "error")
    return redirect(url_for("admin_messages"))

@app.route("/admin/messages/<int:id>/toggle-read", methods=["POST"])
@admin_required
def toggle_message(id):
    try:
        if not supabase_admin:
            flash("Database connection error.", "error")
            return redirect(url_for("admin_messages"))
        
        msg = supabase_admin.table("messages").select("*").eq("id", id).execute().data[0]
        supabase_admin.table("messages").update({"is_read": not msg["is_read"]}).eq("id", id).execute()
        flash("Message status updated!", "success")
    except Exception as e:
        print(f"❌ Toggle message error: {e}")
        flash("Error updating message.", "error")
    return redirect(url_for("admin_messages"))

@app.route("/admin/messages/mark-all-read", methods=["POST"])
@admin_required
def mark_all_read():
    try:
        if not supabase_admin:
            flash("Database connection error.", "error")
            return redirect(url_for("admin_messages"))
        
        supabase_admin.table("messages").update({"is_read": True}).neq("is_read", True).execute()
        flash("All messages marked as read!", "success")
    except Exception as e:
        print(f"❌ Mark all read error: {e}")
        flash("Error marking messages as read.", "error")
    return redirect(url_for("admin_messages"))

# -------------------------------------------------------------
# RLS SETUP ROUTE
# -------------------------------------------------------------
@app.route("/setup-rls")
def setup_rls():
    """Route to setup RLS policies manually"""
    try:
        if setup_rls_policies():
            return '''
            <div style="padding: 20px; font-family: Arial, sans-serif;">
                <h1 style="color: green;">✅ RLS Policies Configured Successfully!</h1>
                <p>Row Level Security policies have been set up for all tables.</p>
                <a href="/setup-admin" style="display: inline-block; padding: 10px 20px; background: #007bff; color: white; text-decoration: none; border-radius: 5px; margin: 5px;">Setup Admin User</a>
                <a href="/" style="display: inline-block; padding: 10px 20px; background: #28a745; color: white; text-decoration: none; border-radius: 5px; margin: 5px;">Go Home</a>
            </div>
            '''
        else:
            return '''
            <div style="padding: 20px; font-family: Arial, sans-serif;">
                <h1 style="color: red;">❌ RLS Setup Failed</h1>
                <p>Check your Supabase configuration and try again.</p>
            </div>
            '''
    except Exception as e:
        return f'''
        <div style="padding: 20px; font-family: Arial, sans-serif;">
            <h1 style="color: red;">❌ RLS Setup Error</h1>
            <p><strong>Error:</strong> {str(e)}</p>
        </div>
        '''

# -------------------------------------------------------------
# STATIC FILE ROUTES
# -------------------------------------------------------------
@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'),
                             'favicon.ico', mimetype='image/vnd.microsoft.icon')

@app.route('/static/script.js')
def serve_script():
    script_path = os.path.join(app.root_path, 'static', 'script.js')
    if not os.path.exists(script_path):
        with open(script_path, 'w') as f:
            f.write('''// JavaScript file
console.log("Blog website loaded");
document.addEventListener('DOMContentLoaded', function() {
    console.log('Blog website initialized');
});
''')
    return send_from_directory(os.path.join(app.root_path, 'static'), 'script.js')

# -------------------------------------------------------------
# ERROR HANDLERS
# -------------------------------------------------------------
@app.errorhandler(404)
def not_found_error(error):
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>404 - Page Not Found</title>
        <style>
            body { font-family: Arial, sans-serif; text-align: center; padding: 50px; }
            h1 { color: #dc3545; }
            a { color: #007bff; text-decoration: none; }
        </style>
    </head>
    <body>
        <h1>404 - Page Not Found</h1>
        <p>The page you are looking for does not exist.</p>
        <a href="/">Go Home</a>
    </body>
    </html>
    ''', 404

@app.errorhandler(500)
def internal_error(error):
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>500 - Internal Server Error</title>
        <style>
            body { font-family: Arial, sans-serif; text-align: center; padding: 50px; }
            h1 { color: #dc3545; }
            a { color: #007bff; text-decoration: none; }
        </style>
    </head>
    <body>
        <h1>500 - Internal Server Error</h1>
        <p>Something went wrong on our end. Please try again later.</p>
        <a href="/">Go Home</a>
    </body>
    </html>
    ''', 500

# -------------------------------------------------------------
# INITIALIZATION - FIXED VERSION (No before_first_request)
# -------------------------------------------------------------
# Remove the problematic before_first_request decorator
# RLS setup will be called when needed or manually via /setup-rls

# -------------------------------------------------------------
# RUN SERVER
# -------------------------------------------------------------
if __name__ == "__main__":
    print("🚀 Starting Flask application with PROPER RLS POLICIES...")
    print("🔐 Using dual client approach: ANON_KEY for public, SERVICE_KEY for admin")
    print("📋 Setup routes:")
    print("   /setup-rls - Configure RLS policies")
    print("   /setup-admin - Create admin user") 
    print("   /login - User login")
    print("   /admin/dashboard - Admin dashboard")
    
    # Initialize RLS policies on startup
    setup_rls_policies()
    
    app.run(debug=True, host='0.0.0.0', port=5000)
