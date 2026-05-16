import os
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.secret_key = "asharib_tech_official_key"

# --- DATABASE CONFIGURATION ---
db_url = os.environ.get('DATABASE_URL')
if db_url and db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = db_url or 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# --- Models ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    is_blocked = db.Column(db.Boolean, default=False)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    old_price = db.Column(db.String(20))
    price = db.Column(db.String(20))
    stock = db.Column(db.String(50))
    desc = db.Column(db.Text)
    pic = db.Column(db.String(300))
    rating = db.Column(db.String(10), default="4.9")
    reviews = db.Column(db.String(10), default="128")

with app.app_context():
    db.create_all() 

# --- Routes ---

@app.route('/')
def home():
    if not session.get('user_id'): 
        return redirect(url_for('user_auth'))
    all_products = Product.query.all()
    return render_template('store.html', products=all_products)

# Login Page Route
@app.route('/auth', methods=['GET', 'POST'])
@app.route('/login', methods=['GET', 'POST'])
def user_auth():
    if request.method == 'POST':
        username = request.form.get('email') # Form mein 'email' field name hai
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        
        if user and user.password == password:
            if user.is_blocked:
                flash("Your account is suspended. Contact Admin.")
                return redirect(url_for('user_auth'))
            session['user_id'] = user.id
            return redirect(url_for('home'))
        
        flash("Invalid email or password!")
        return redirect(url_for('user_auth'))
        
    return render_template('auth.html')

# Register Page Route (Naya Add Kiya Hai)
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('email')
        password = request.form.get('password')
        
        if not username or not password:
            flash("All fields are required!")
            return redirect(url_for('register'))

        if User.query.filter_by(username=username).first():
            flash("User already exists with this email!")
            return redirect(url_for('register'))

        new_user = User(username=username, password=password)
        db.session.add(new_user)
        db.session.commit()
        
        return '''<script>
            alert("Account Created! Now Login.");
            window.location.href = "/auth";
        </script>'''

    return render_template('register.html')

# --- Admin Routes ---
@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if not session.get('admin'): 
        return redirect(url_for('admin_login'))
    
    if request.method == 'POST':
        new_p = Product(
            name=request.form['name'], 
            old_price=request.form['old_price'], 
            price=request.form['price'], 
            stock=request.form['stock'], 
            desc=request.form['desc'], 
            pic=request.form['pic'],
            rating=request.form.get('rating', '4.9'),
            reviews=request.form.get('reviews', '128')
        )
        db.session.add(new_p)
        db.session.commit()
        return redirect(url_for('admin'))
    
    all_p = Product.query.all()
    all_u = User.query.all()
    return render_template('admin.html', products=all_p, users=all_u)

@app.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST' and request.form.get('pass') == 'asharib123':
        session['admin'] = True
        return redirect(url_for('admin'))
    return '''<body style="background:#111;color:white;text-align:center;padding-top:100px;">
              <form method="post"><h2>Admin Panel</h2><input type="password" name="pass"><button>Login</button></form></body>'''

@app.route('/admin/toggle_block/<int:user_id>')
def toggle_block(user_id):
    if not session.get('admin'): 
        return redirect(url_for('admin_login'))
    user = User.query.get(user_id)
    if user:
        user.is_blocked = not user.is_blocked
        db.session.commit()
    return redirect(url_for('admin'))

@app.route('/delete/<int:id>')
def delete(id):
    if not session.get('admin'): return redirect(url_for('admin_login'))
    p = Product.query.get(id)
    if p: 
        db.session.delete(p)
        db.session.commit()
    return redirect(url_for('admin'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('user_auth'))

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=10000)
