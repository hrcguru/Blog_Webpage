from flask import Flask, render_template, request, redirect, url_for, flash, session, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import sqlite3
import os
from datetime import datetime
import html

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif'}
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # 5MB max file size

# Database initialization
def init_db():
    conn = sqlite3.connect('blog.db')
    c = conn.cursor()
    
    # Users table
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  username TEXT UNIQUE NOT NULL,
                  email TEXT UNIQUE NOT NULL,
                  password TEXT NOT NULL,
                  is_admin BOOLEAN DEFAULT FALSE,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    # Posts table
    c.execute('''CREATE TABLE IF NOT EXISTS posts
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  title TEXT NOT NULL,
                  content TEXT NOT NULL,
                  category TEXT NOT NULL,
                  image_path TEXT,
                  author_id INTEGER,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  FOREIGN KEY (author_id) REFERENCES users (id))''')
    
    # Messages table
    c.execute('''CREATE TABLE IF NOT EXISTS messages
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  name TEXT NOT NULL,
                  email TEXT NOT NULL,
                  message TEXT NOT NULL,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  is_read BOOLEAN DEFAULT FALSE)''')
    
    # Create default admin user
    try:
        admin_password = generate_password_hash('admin123')
        c.execute("INSERT OR IGNORE INTO users (username, email, password, is_admin) VALUES (?, ?, ?, ?)",
                  ('admin', 'admin@blog.com', admin_password, True))
        print("✅ Default admin user created")
    except:
        pass
    
    conn.commit()
    conn.close()
    print("✅ SQLite database initialized successfully!")

def get_db_connection():
    conn = sqlite3.connect('blog.db')
    conn.row_factory = sqlite3.Row
    return conn

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
        user = conn.execute('SELECT is_admin FROM users WHERE id = ?', (session['user_id'],)).fetchone()
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
    count = conn.execute('SELECT COUNT(*) as count FROM messages WHERE is_read = 0').fetchone()['count']
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
    posts = conn.execute('''
        SELECT p.*, u.username 
        FROM posts p 
        JOIN users u ON p.author_id = u.id 
        ORDER BY p.created_at DESC 
        LIMIT 6
    ''').fetchall()
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
        try:
            conn.execute('INSERT INTO users (username, email, password) VALUES (?, ?, ?)',
                        (username, email, hashed_password))
            conn.commit()
            flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Username or email already exists!', 'error')
        finally:
            conn.close()
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
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
    posts = conn.execute('''
        SELECT p.*, u.username 
        FROM posts p 
        JOIN users u ON p.author_id = u.id 
        ORDER BY p.created_at DESC
    ''').fetchall()
    
    # Get stats for dashboard
    total_posts = conn.execute('SELECT COUNT(*) as count FROM posts').fetchone()['count']
    total_messages = conn.execute('SELECT COUNT(*) as count FROM messages').fetchone()['count']
    unread_messages = conn.execute('SELECT COUNT(*) as count FROM messages WHERE is_read = 0').fetchone()['count']
    
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
        try:
            conn.execute('INSERT INTO posts (title, content, category, image_path, author_id) VALUES (?, ?, ?, ?, ?)',
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
    
    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']
        category = request.form['category']
        image = request.files['image']
        remove_image = request.form.get('remove_image')
        
        content = html.escape(content)
        
        current_post = conn.execute('SELECT * FROM posts WHERE id = ?', (post_id,)).fetchone()
        
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
        conn.execute('''
            UPDATE posts 
            SET title = ?, content = ?, category = ?, image_path = ?
            WHERE id = ?
        ''', (title, content, category, image_path, post_id))
        conn.commit()
        conn.close()
        
        flash('Post updated successfully!', 'success')
        return redirect(url_for('admin_dashboard'))
    
    # GET request - show edit form
    post = conn.execute('SELECT * FROM posts WHERE id = ?', (post_id,)).fetchone()
    conn.close()
    
    if not post:
        flash('Post not found!', 'error')
        return redirect(url_for('admin_dashboard'))
    
    return render_template('edit_post.html', post=post, categories=categories)

@app.route('/admin/delete-post/<int:post_id>', methods=['POST'])
@admin_required
def delete_post(post_id):
    conn = get_db_connection()
    
    # Get post to check for image
    post = conn.execute('SELECT * FROM posts WHERE id = ?', (post_id,)).fetchone()
    
    if post and post['image_path']:
        # Delete the image file
        image_path = os.path.join(app.config['UPLOAD_FOLDER'], post['image_path'])
        if os.path.exists(image_path):
            os.remove(image_path)
    
    # Delete the post
    conn.execute('DELETE FROM posts WHERE id = ?', (post_id,))
    conn.commit()
    conn.close()
    
    flash('Post deleted successfully!', 'success')
    return redirect(url_for('admin_dashboard'))

# Messages Management Routes
@app.route('/admin/messages')
@admin_required
def view_messages():
    conn = get_db_connection()
    messages = conn.execute('''
        SELECT * FROM messages 
        ORDER BY created_at DESC
    ''').fetchall()
    conn.close()
    return render_template('messages.html', messages=messages)

@app.route('/admin/messages/<int:message_id>/delete', methods=['POST'])
@admin_required
def delete_message(message_id):
    conn = get_db_connection()
    conn.execute('DELETE FROM messages WHERE id = ?', (message_id,))
    conn.commit()
    conn.close()
    flash('Message deleted successfully!', 'success')
    return redirect(url_for('view_messages'))

@app.route('/admin/messages/<int:message_id>/toggle-read', methods=['POST'])
@admin_required
def toggle_message_read(message_id):
    conn = get_db_connection()
    message = conn.execute('SELECT is_read FROM messages WHERE id = ?', (message_id,)).fetchone()
    new_status = not message['is_read']
    conn.execute('UPDATE messages SET is_read = ? WHERE id = ?', (new_status, message_id))
    conn.commit()
    conn.close()
    flash('Message status updated!', 'success')
    return redirect(url_for('view_messages'))

@app.route('/admin/messages/mark-all-read', methods=['POST'])
@admin_required
def mark_all_messages_read():
    conn = get_db_connection()
    conn.execute('UPDATE messages SET is_read = 1 WHERE is_read = 0')
    conn.commit()
    conn.close()
    flash('All messages marked as read!', 'success')
    return redirect(url_for('view_messages'))

@app.route('/post/<int:post_id>')
@login_required
def view_post(post_id):
    conn = get_db_connection()
    post = conn.execute('''
        SELECT p.*, u.username 
        FROM posts p 
        JOIN users u ON p.author_id = u.id 
        WHERE p.id = ?
    ''', (post_id,)).fetchone()
    conn.close()
    
    if not post:
        flash('Post not found!', 'error')
        return redirect(url_for('index'))
    
    return render_template('post.html', post=post)

@app.route('/category/<category_name>')
@login_required
def category_posts(category_name):
    conn = get_db_connection()
    posts = conn.execute('''
        SELECT p.*, u.username 
        FROM posts p 
        JOIN users u ON p.author_id = u.id 
        WHERE p.category = ? 
        ORDER BY p.created_at DESC
    ''', (category_name,)).fetchall()
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
        conn.execute('INSERT INTO messages (name, email, message) VALUES (?, ?, ?)',
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
    print("🚀 Blog Website Starting with SQLite Database")
    print("📝 Admin Login: username 'admin', password 'admin123'")
    print("📧 Messages System: Enabled")
    print("📝 Rich Text Editor: Enabled")
    print("🌐 Access: http://127.0.0.1:5000")
    print("="*50)
    app.run(debug=True)