from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import requests
from bs4 import BeautifulSoup
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key_here'  # Change this to a random secret key
login_manager = LoginManager(app)
login_manager.login_view = 'login'

class User(UserMixin):
    def __init__(self, id, username, password):
        self.id = id
        self.username = username
        self.password = password

@login_manager.user_loader
def load_user(user_id):
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    conn.close()
    if user:
        return User(user['id'], user['username'], user['password'])
    return None

def get_db_connection():
    conn = sqlite3.connect('scraper.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS scrapes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            url TEXT NOT NULL,
            title TEXT,
            description TEXT,
            h1 TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    conn.commit()
    conn.close()

def scrape_website(url, user_id):
    try:
        response = requests.get(url, timeout=5)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        title = soup.title.string if soup.title else "No title found"
        description = soup.find('meta', attrs={'name': 'description'})
        description = description['content'] if description else "No description found"
        h1 = soup.find('h1')
        h1_text = h1.text if h1 else "No H1 found"
        
        conn = get_db_connection()
        conn.execute('INSERT INTO scrapes (user_id, url, title, description, h1) VALUES (?, ?, ?, ?, ?)',
                     (user_id, url, title, description, h1_text))
        conn.commit()
        conn.close()
        
        return {
            'url': url,
            'title': title,
            'description': description,
            'h1': h1_text,
            'status': 'success'
        }
    except requests.RequestException as e:
        return {
            'url': url,
            'status': 'error',
            'message': f"Error: {str(e)}"
        }

@app.route('/', methods=['GET', 'POST'])
@login_required
def index():
    if request.method == 'POST':
        url = request.form['url']
        data = [scrape_website(url, current_user.id)]
    else:
        data = []
    
    conn = get_db_connection()
    history = conn.execute('SELECT * FROM scrapes WHERE user_id = ? ORDER BY timestamp DESC LIMIT 10',
                           (current_user.id,)).fetchall()
    conn.close()
    
    return render_template('index.html', data=data, history=history)

@app.route('/search')
@login_required
def search():
    query = request.args.get('query', '')
    conn = get_db_connection()
    results = conn.execute('SELECT * FROM scrapes WHERE user_id = ? AND (url LIKE ? OR title LIKE ?) ORDER BY timestamp DESC',
                           (current_user.id, f'%{query}%', f'%{query}%')).fetchall()
    conn.close()
    return render_template('search.html', results=results, query=query)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        conn.close()
        if user and check_password_hash(user['password'], password):
            user_obj = User(user['id'], user['username'], user['password'])
            login_user(user_obj)
            return redirect(url_for('index'))
        flash('Invalid username or password')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = get_db_connection()
        if conn.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone():
            flash('Username already exists')
        else:
            hashed_password = generate_password_hash(password)
            conn.execute('INSERT INTO users (username, password) VALUES (?, ?)', (username, hashed_password))
            conn.commit()
            flash('Registration successful. Please log in.')
            return redirect(url_for('login'))
        conn.close()
    return render_template('register.html')

if __name__ == '__main__':
    init_db()
    app.run(debug=True)