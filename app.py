import os
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.pool import QueuePool

app = Flask(__name__)
app.secret_key = "asharib_tech_official_key"

# --- DATABASE CONFIGURATION ---
# Neon aur Vercel ke liye optimized config
db_url = os.environ.get('POSTGRES_URL') or os.environ.get('DATABASE_URL')

if db_url:
    # Postgres protocol fix for SQLAlchemy
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    
    # SSL mode forced for Neon taake connection reject na ho
    if "sslmode" not in db_url:
        if "?" in db_url:
            db_url += "&sslmode=require"
        else:
            db_url += "?sslmode=require"
            
    app.config['SQLALCHEMY_DATABASE_URI'] = db_url
else:
    # Local testing ke liye SQLite
    basedir = os.path.abspath(os.path.dirname(__file__))
    db_path = os.path.join(basedir, 'database.db')
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + db_path

# Connection pooling settings taake timeout ya connection errors na aayin
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    "pool_pre_ping": True,
    "pool_recycle": 300,
    "poolclass": QueuePool,
}
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# --- Database Initialization ---
db = SQLAlchemy(app)

# --- Models ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    is_blocked = db.Column(db.Boolean, default=False)
    balance = db.Column(db.Float, default=0.0)

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

# Tables ko auto-create karne ke liye logic
with app.app_context():
    try:
        db.create_all()
        print("Database tables synchronized!")
    except Exception as e:
        print(f"Database Creation Error: {e}")

# --- Routes ---

@app.route('/')
def home():
    if not session.get('user_id'): 
        return redirect(url_for('user_auth'))
    
    user = User.query.get(session['user_id'])
    if not user or user.is_blocked:
        session.clear()
        return redirect(url_for('user_auth'))

    search_query = request.args.get('search', '').strip()
    if search_query:
        all_products = Product.query.filter(Product.name.ilike(f'%{search_query}%')).all()
    else:
        all_products = Product.query.all()
    
    return render_template('store.html', products=all_products, search_query=search_query, user=user)

@app.route('/auth', methods=['GET', 'POST'])
@app.route('/login', methods=['GET', 'POST'])
def user_auth():
    if request.method == 'POST':
        login_email = request.form.get('email')
        login_password = request.form.get('password')
        
        try:
            # Username column mein email hi store hoti hai hamare system mein
            user = User.query.filter_by(username=login_email).first()
            
            if user and user.password == login_password:
                if user.is_blocked:
                    flash("Your account is suspended. Contact Admin.")
                    return redirect(url_for('user_auth'))
                session['user_id'] = user.id
                return redirect(url_for('home'))
            
            flash("Invalid email or password!")
        except Exception as e:
            print(f"Login Database Error: {e}")
            flash("Server error during login. Database might be updating.")
            
        return redirect(url_for('user_auth'))
        
    return render_template('auth.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        reg_email = request.form.get('email')
        reg_password = request.form.get('password')
        
        if not reg_email or not reg_password:
            flash("All fields are required!")
            return redirect(url_for('register'))

        try:
            if User.query.filter_by(username=reg_email).first():
                flash("User already exists with this email!")
                return redirect(url_for('register'))

            new_user = User(username=reg_email, password=reg_password, balance=0.0)
            db.session.add(new_user)
            db.session.commit()
            return f'''<script>
                alert("Account Created! Now Login.");
                window.location.href = "{url_for('user_auth')}";
            </script>'''
        except Exception as e:
            db.session.rollback()
            print(f"Registration Error: {e}")
            flash("Registration Error. Database busy, please try again.")
            return redirect(url_for('register'))

    return render_template('register.html')

@app.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        password = request.form.get('pass')
        if password == 'asharib123':
            session['admin'] = True
            return redirect(url_for('admin'))
        else:
            flash("Wrong Admin Password!")
    return render_template('admin_login.html')

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

@app.route('/admin/update_balance/<int:user_id>/<float:amount>')
def update_balance(user_id, amount):
    if not session.get('admin'): return redirect(url_for('admin_login'))
    user = User.query.get(user_id)
    if user:
        user.balance += amount
        db.session.commit()
        flash(f"Balance updated for {user.username}")
    return redirect(url_for('admin'))

@app.route('/admin/delete_user/<int:user_id>')
def delete_user(user_id):
    if not session.get('admin'): return redirect(url_for('admin_login'))
    user = User.query.get(user_id)
    if user:
        db.session.delete(user)
        db.session.commit()
    return redirect(url_for('admin'))

@app.route('/admin/toggle_block/<int:user_id>')
def toggle_block(user_id):
    if not session.get('admin'): 
        return redirect(url_for('admin_login'))
    user = User.query.get(user_id)
    if user:
        user.is_blocked = not user.is_blocked
        db.session.commit()
    return redirect(url_for('admin'))

@app.route('/admin/edit_product/<int:id>', methods=['GET', 'POST'])
def edit_product(id):
    if not session.get('admin'): return redirect(url_for('admin_login'))
    p = Product.query.get(id)
    if request.method == 'POST':
        p.name = request.form['name']
        p.old_price = request.form['old_price']
        p.price = request.form['price']
        p.stock = request.form['stock']
        p.desc = request.form['desc']
        p.pic = request.form['pic']
        db.session.commit()
        return redirect(url_for('admin'))
    return render_template('edit_product.html', p=p)

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
    app.run()
