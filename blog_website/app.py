from flask import Flask, render_template, request, redirect, url_for, flash, session, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
from datetime import datetime
import html
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your-secret-key-here')
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif'}
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # 5MB max file size

# Database configuration
DATABASE_URL = "postgresql://blog_website_cktc_user:RVixdA5vQjOCpwT13gkFAycZf2fLRQ81@dpg-d4fcl0f5r7bs73ckt360-a.oregon-postgres.render.com/blog_website_cktc"

def get_db_connection():
    """Get PostgreSQL database connection"""
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    return conn

# Database initialization
def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Users table
        cursor.execute('''CREATE TABLE IF NOT EXISTS users
                     (id SERIAL PRIMARY KEY,
                      username TEXT UNIQUE NOT NULL,
                      email TEXT UNIQUE NOT NULL,
                      password TEXT NOT NULL,
                      is_admin BOOLEAN DEFAULT FALSE,
                      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        
        # Posts table
        cursor.execute('''CREATE TABLE IF NOT EXISTS posts
                     (id SERIAL PRIMARY KEY,
                      title TEXT NOT NULL,
                      content TEXT NOT NULL,
                      category TEXT NOT NULL,
                      image_path TEXT,
                      author_id INTEGER REFERENCES users(id),
                      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        
        # Messages table
        cursor.execute('''CREATE TABLE IF NOT EXISTS messages
                     (id SERIAL PRIMARY KEY,
                      name TEXT NOT NULL,
                      email TEXT NOT NULL,
                      message TEXT NOT NULL,
                      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                      is_read BOOLEAN DEFAULT FALSE)''')
        
        # Create default admin user
        admin_password = generate_password_hash('admin123')
        cursor.execute('''INSERT INTO users (username, email, password, is_admin) 
                       VALUES (%s, %s, %s, %s)
                       ON CONFLICT (username) DO NOTHING''',
                    ('admin', 'admin@blog.com', admin_password, True))
        
        conn.commit()
        print("✅ PostgreSQL database initialized successfully!")
        print("✅ Default admin user created")
        
    except Exception as e:
        print(f"❌ Database initialization error: {e}")
        conn.rollback()
    finally:
        conn.close()

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

# Authentication decorators
def login_required(f):
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

def admin_required(f):
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'error')
            return redirect(url_for('login'))
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT is_admin FROM users WHERE id = %s', (session['user_id'],))
        user = cursor.fetchone()
        conn.close()
        
        if not user or not user['is_admin']:
            flash('Admin access required.', 'error')
            return redirect(url_for('index'))
        
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

# Helper function to get unread message count
def get_unread_message_count():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) as count FROM messages WHERE is_read = FALSE')
    count = cursor.fetchone()['count']
    conn.close()
    return count

@app.context_processor
def inject_unread_count():
    if session.get('is_admin'):
        return {'unread_count': get_unread_message_count()}
    return {'unread_count': 0}

# Helper function to get image URL
def get_image_url(image_path):
    if image_path:
        return url_for('static', filename=f'uploads/{image_path}')
    return None

# Helper function to format date
def format_date(date_string, format='%b %d, %Y'):
    if isinstance(date_string, str):
        try:
            # Try to parse the date string
            dt = datetime.strptime(date_string, '%Y-%m-%d %H:%M:%S')
            return dt.strftime(format)
        except:
            try:
                # Try alternative format
                dt = datetime.strptime(date_string, '%Y-%m-%d')
                return dt.strftime(format)
            except:
                return date_string[:10]  # Return first 10 characters if parsing fails
    elif isinstance(date_string, datetime):
        return date_string.strftime(format)
    return str(date_string)

# Make the functions available in templates
@app.context_processor
def utility_processor():
    return dict(
        get_image_url=get_image_url,
        format_date=format_date
    )

@app.route('/')
def index():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT p.*, u.username 
        FROM posts p 
        JOIN users u ON p.author_id = u.id 
        ORDER BY p.created_at DESC 
        LIMIT 6
    ''')
    posts = cursor.fetchall()
    conn.close()
    return render_template('index.html', posts=posts)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        
        if password != confirm_password:
            flash('Passwords do not match!', 'error')
            return render_template('register.html')
        
        hashed_password = generate_password_hash(password)
        
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('INSERT INTO users (username, email, password) VALUES (%s, %s, %s)',
                        (username, email, hashed_password))
            conn.commit()
            flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            flash('Username or email already exists!', 'error')
            print(f"Registration error: {e}")
        finally:
            conn.close()
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE username = %s', (username,))
        user = cursor.fetchone()
        conn.close()
        
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['is_admin'] = user['is_admin']
            flash(f'Welcome back, {user["username"]}!', 'success')
            
            # FIXED: Always redirect to index after login so users can see posts
            return redirect(url_for('index'))
        else:
            flash('Invalid username or password!', 'error')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out successfully.', 'success')
    return redirect(url_for('index'))

@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT p.*, u.username 
        FROM posts p 
        JOIN users u ON p.author_id = u.id 
        ORDER BY p.created_at DESC
    ''')
    posts = cursor.fetchall()
    
    # Get stats for dashboard
    cursor.execute('SELECT COUNT(*) as count FROM posts')
    total_posts = cursor.fetchone()['count']
    
    cursor.execute('SELECT COUNT(*) as count FROM messages')
    total_messages = cursor.fetchone()['count']
    
    cursor.execute('SELECT COUNT(*) as count FROM messages WHERE is_read = FALSE')
    unread_messages = cursor.fetchone()['count']
    
    conn.close()
    
    return render_template('admin_dashboard.html', 
                         posts=posts, 
                         total_posts=total_posts,
                         total_messages=total_messages,
                         unread_messages=unread_messages)

@app.route('/admin/create-post', methods=['GET', 'POST'])
@admin_required
def create_post():
    categories = ['AboutMe', 'Esoteric Science', 'Science and Tech', 'Indian Culture', 'Spiritual']
    
    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']
        category = request.form['category']
        image = request.files['image']
        
        content = html.escape(content)
        
        image_path = None
        if image and image.filename != '':
            if allowed_file(image.filename):
                filename = secure_filename(image.filename)
                unique_filename = f"{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{filename}"
                # Store only the filename, not the full path
                image_path = unique_filename
                
                # Ensure upload directory exists
                os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
                
                try:
                    # Save the file
                    full_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                    image.save(full_path)
                    print(f"✅ Image saved: {full_path}")
                    flash('Image uploaded successfully!', 'success')
                except Exception as e:
                    flash(f'Error saving image: {str(e)}', 'error')
                    return render_template('create_post.html', categories=categories)
            else:
                flash('Invalid image format! Please use PNG, JPG, JPEG, or GIF.', 'error')
                return render_template('create_post.html', categories=categories)
        
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('INSERT INTO posts (title, content, category, image_path, author_id) VALUES (%s, %s, %s, %s, %s)',
                        (title, content, category, image_path, session['user_id']))
            conn.commit()
            flash('Post created successfully!', 'success')
            return redirect(url_for('admin_dashboard'))
        except Exception as e:
            flash('Error creating post. Please try again.', 'error')
            print(f"Database error: {e}")
        finally:
            conn.close()
    
    return render_template('create_post.html', categories=categories)

@app.route('/admin/edit-post/<int:post_id>', methods=['GET', 'POST'])
@admin_required
def edit_post(post_id):
    categories = ['AboutMe', 'Esoteric Science', 'Science and Tech', 'Indian Culture', 'Spiritual']
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']
        category = request.form['category']
        image = request.files['image']
        remove_image = request.form.get('remove_image')
        
        content = html.escape(content)
        
        cursor.execute('SELECT * FROM posts WHERE id = %s', (post_id,))
        current_post = cursor.fetchone()
        
        image_path = current_post['image_path']
        
        # Handle image removal
        if remove_image == 'yes' and current_post['image_path']:
            # Delete the old image file
            old_image_path = os.path.join(app.config['UPLOAD_FOLDER'], current_post['image_path'])
            if os.path.exists(old_image_path):
                os.remove(old_image_path)
            image_path = None
        
        # Handle new image upload
        if image and image.filename != '':
            if allowed_file(image.filename):
                # Delete old image if exists
                if current_post['image_path']:
                    old_image_path = os.path.join(app.config['UPLOAD_FOLDER'], current_post['image_path'])
                    if os.path.exists(old_image_path):
                        os.remove(old_image_path)
                
                # Create unique filename
                filename = secure_filename(image.filename)
                unique_filename = f"{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{filename}"
                image_path = unique_filename
                
                # Save the new file
                image.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_filename))
                flash('Image updated successfully!', 'success')
            else:
                flash('Invalid image format! Please use PNG, JPG, JPEG, or GIF.', 'error')
                return render_template('edit_post.html', post=current_post, categories=categories)
        
        # Update the post
        cursor.execute('''
            UPDATE posts 
            SET title = %s, content = %s, category = %s, image_path = %s
            WHERE id = %s
        ''', (title, content, category, image_path, post_id))
        conn.commit()
        conn.close()
        
        flash('Post updated successfully!', 'success')
        return redirect(url_for('admin_dashboard'))
    
    # GET request - show edit form
    cursor.execute('SELECT * FROM posts WHERE id = %s', (post_id,))
    post = cursor.fetchone()
    conn.close()
    
    if not post:
        flash('Post not found!', 'error')
        return redirect(url_for('admin_dashboard'))
    
    return render_template('edit_post.html', post=post, categories=categories)

@app.route('/admin/delete-post/<int:post_id>', methods=['POST'])
@admin_required
def delete_post(post_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get post to check for image
    cursor.execute('SELECT * FROM posts WHERE id = %s', (post_id,))
    post = cursor.fetchone()
    
    if post and post['image_path']:
        # Delete the image file
        image_path = os.path.join(app.config['UPLOAD_FOLDER'], post['image_path'])
        if os.path.exists(image_path):
            os.remove(image_path)
    
    # Delete the post
    cursor.execute('DELETE FROM posts WHERE id = %s', (post_id,))
    conn.commit()
    conn.close()
    
    flash('Post deleted successfully!', 'success')
    return redirect(url_for('admin_dashboard'))

# Messages Management Routes
@app.route('/admin/messages')
@admin_required
def view_messages():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM messages 
        ORDER BY created_at DESC
    ''')
    messages = cursor.fetchall()
    conn.close()
    return render_template('messages.html', messages=messages)

@app.route('/admin/messages/<int:message_id>/delete', methods=['POST'])
@admin_required
def delete_message(message_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM messages WHERE id = %s', (message_id,))
    conn.commit()
    conn.close()
    flash('Message deleted successfully!', 'success')
    return redirect(url_for('view_messages'))

@app.route('/admin/messages/<int:message_id>/toggle-read', methods=['POST'])
@admin_required
def toggle_message_read(message_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT is_read FROM messages WHERE id = %s', (message_id,))
    message = cursor.fetchone()
    new_status = not message['is_read']
    cursor.execute('UPDATE messages SET is_read = %s WHERE id = %s', (new_status, message_id))
    conn.commit()
    conn.close()
    flash('Message status updated!', 'success')
    return redirect(url_for('view_messages'))

@app.route('/admin/messages/mark-all-read', methods=['POST'])
@admin_required
def mark_all_messages_read():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE messages SET is_read = TRUE WHERE is_read = FALSE')
    conn.commit()
    conn.close()
    flash('All messages marked as read!', 'success')
    return redirect(url_for('view_messages'))

@app.route('/post/<int:post_id>')
@login_required
def view_post(post_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT p.*, u.username 
        FROM posts p 
        JOIN users u ON p.author_id = u.id 
        WHERE p.id = %s
    ''', (post_id,))
    post = cursor.fetchone()
    conn.close()
    
    if not post:
        flash('Post not found!', 'error')
        return redirect(url_for('index'))
    
    return render_template('post.html', post=post)

@app.route('/category/<category_name>')
@login_required
def category_posts(category_name):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT p.*, u.username 
        FROM posts p 
        JOIN users u ON p.author_id = u.id 
        WHERE p.category = %s 
        ORDER BY p.created_at DESC
    ''', (category_name,))
    posts = cursor.fetchall()
    conn.close()
    
    return render_template('categories.html', posts=posts, category=category_name)

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        message_text = request.form['message']
        
        # Store message in database
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('INSERT INTO messages (name, email, message) VALUES (%s, %s, %s)',
                    (name, email, message_text))
        conn.commit()
        conn.close()
        
        flash('Thank you for your message! We will get back to you soon.', 'success')
        return redirect(url_for('contact'))
    
    return render_template('contact.html')

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

if __name__ == '__main__':
    init_db()
    print("\n" + "="*50)
    print("🚀 Blog Website Starting with PostgreSQL Database")
    print("📝 Admin Login: username 'admin', password 'admin123'")
    print("📧 Messages System: Enabled")
    print("📝 Rich Text Editor: Enabled")
    print("🌐 Access: http://127.0.0.1:5000")
    print("="*50)
    app.run(debug=True)
