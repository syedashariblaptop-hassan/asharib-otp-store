import os
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.pool import QueuePool
from datetime import datetime

app = Flask(__name__)
app.secret_key = "asharib_tech_official_key"

# --- DATABASE CONFIGURATION ---
db_url = os.environ.get('POSTGRES_URL') or os.environ.get('DATABASE_URL')

if db_url:
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    if "sslmode" not in db_url:
        db_url += "&sslmode=require" if "?" in db_url else "?sslmode=require"
    app.config['SQLALCHEMY_DATABASE_URI'] = db_url
else:
    basedir = os.path.abspath(os.path.dirname(__file__))
    db_path = os.path.join(basedir, 'database.db')
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + db_path

app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    "pool_pre_ping": True,
    "pool_recycle": 300,
    "poolclass": QueuePool,
}
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# --- Models ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    is_blocked = db.Column(db.Boolean, default=False)
    balance = db.Column(db.Float, default=0.0)
    deposits = db.relationship('Deposit', backref='user', lazy=True)

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

class Deposit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    proof_url = db.Column(db.String(500), nullable=False)
    status = db.Column(db.String(20), default="Pending") # Pending, Approved, Rejected
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    try:
        db.create_all()
        print("Database tables synchronized!")
    except Exception as e:
        print(f"Database Creation Error: {e}")

# --- Routes ---

@app.route('/')
def home():
    if not session.get('user_id'): return redirect(url_for('user_auth'))
    user = User.query.get(session['user_id'])
    if not user or user.is_blocked:
        session.clear()
        return redirect(url_for('user_auth'))
    
    search_query = request.args.get('search', '').strip()
    all_products = Product.query.filter(Product.name.ilike(f'%{search_query}%')).all() if search_query else Product.query.all()
    return render_template('store.html', products=all_products, user=user)

# --- DEPOSIT SYSTEM ---
@app.route('/deposit', methods=['GET', 'POST'])
def deposit():
    if not session.get('user_id'): return redirect(url_for('user_auth'))
    user = User.query.get(session['user_id'])
    
    if request.method == 'POST':
        amount = request.form.get('amount')
        proof = request.form.get('proof_url')
        
        if not amount or not proof:
            flash("All fields are required!")
            return redirect(url_for('deposit'))
            
        new_dep = Deposit(user_id=user.id, amount=float(amount), proof_url=proof)
        db.session.add(new_dep)
        db.session.commit()
        flash("Deposit request submitted! Admin will verify it shortly.")
        return redirect(url_for('home'))
        
    return render_template('deposit.html', user=user)

# --- ADMIN DEPOSIT MANAGEMENT ---
@app.route('/admin/deposits')
def admin_deposits():
    if not session.get('admin'): return redirect(url_for('admin_login'))
    pending_requests = Deposit.query.filter_by(status="Pending").all()
    return render_template('admin_deposits.html', requests=pending_requests)

@app.route('/admin/approve_deposit/<int:id>')
def approve_deposit(id):
    if not session.get('admin'): return redirect(url_for('admin_login'))
    dep = Deposit.query.get(id)
    if dep and dep.status == "Pending":
        user = User.query.get(dep.user_id)
        user.balance += dep.amount
        dep.status = "Approved"
        db.session.commit()
        flash(f"Approved {dep.amount} for {user.username}")
    return redirect(url_for('admin_deposits'))

@app.route('/admin/reject_deposit/<int:id>')
def reject_deposit(id):
    if not session.get('admin'): return redirect(url_for('admin_login'))
    dep = Deposit.query.get(id)
    if dep:
        dep.status = "Rejected"
        db.session.commit()
        flash("Deposit rejected.")
    return redirect(url_for('admin_deposits'))

# (Baqi saaray purane Admin aur Auth routes yahan niche rahenge...)

@app.route('/auth', methods=['GET', 'POST'])
@app.route('/login', methods=['GET', 'POST'])
def user_auth():
    if request.method == 'POST':
        login_email = request.form.get('email')
        login_password = request.form.get('password')
        try:
            user = User.query.filter_by(username=login_email).first()
            if user and user.password == login_password:
                if user.is_blocked:
                    flash("Your account is suspended. Contact Admin.")
                    return redirect(url_for('user_auth'))
                session['user_id'] = user.id
                return redirect(url_for('home'))
            flash("Invalid email or password!")
        except Exception as e:
            flash("Server error during login.")
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
                flash("User already exists!")
                return redirect(url_for('register'))
            new_user = User(username=reg_email, password=reg_password, balance=0.0)
            db.session.add(new_user)
            db.session.commit()
            return f'<script>alert("Account Created! Now Login."); window.location.href = "{url_for("user_auth")}";</script>'
        except Exception as e:
            db.session.rollback()
            flash("Registration Error.")
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
    if not session.get('admin'): return redirect(url_for('admin_login'))
    if request.method == 'POST':
        new_p = Product(
            name=request.form['name'], old_price=request.form['old_price'], 
            price=request.form['price'], stock=request.form['stock'], 
            desc=request.form['desc'], pic=request.form['pic']
        )
        db.session.add(new_p)
        db.session.commit()
        return redirect(url_for('admin'))
    return render_template('admin.html', products=Product.query.all(), users=User.query.all())

@app.route('/admin/update_balance/<int:user_id>/<float:amount>')
def update_balance(user_id, amount):
    if not session.get('admin'): return redirect(url_for('admin_login'))
    user = User.query.get(user_id)
    if user:
        user.balance += amount
        db.session.commit()
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
    if not session.get('admin'): return redirect(url_for('admin_login'))
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
        p.name, p.old_price, p.price, p.stock, p.desc, p.pic = request.form['name'], request.form['old_price'], request.form['price'], request.form['stock'], request.form['desc'], request.form['pic']
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
