import os
import base64
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
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
    proof_url = db.Column(db.Text, nullable=False) 
    status = db.Column(db.String(20), default="Pending")
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

# --- Database Synchronization ---
with app.app_context():
    try:
        db.create_all()
        print("Database Synchronized!")
    except Exception as e:
        print(f"Error syncing DB: {e}")

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
    
    user_deposits = Deposit.query.filter_by(user_id=user.id).order_by(Deposit.timestamp.desc()).all()
    return render_template('store.html', products=all_products, user=user, user_deposits=user_deposits)

@app.route('/deposit', methods=['GET', 'POST'])
def deposit():
    if not session.get('user_id'): return redirect(url_for('user_auth'))
    user = User.query.get(session['user_id'])
    
    if request.method == 'POST':
        try:
            amount = request.form.get('amount')
            file = request.files.get('screenshot')
            
            if not amount or not file:
                return jsonify({"status": "error", "message": "All fields are required!"}), 400
                
            img_stream = file.read()
            img_base64 = base64.b64encode(img_stream).decode('utf-8')
            
            new_dep = Deposit(
                user_id=user.id, 
                amount=float(amount), 
                proof_url=img_base64,
                status="Pending"
            )
            db.session.add(new_dep)
            db.session.commit()
            
            return jsonify({"status": "success", "message": "Request submitted!"})
            
        except Exception as e:
            db.session.rollback()
            return jsonify({"status": "error", "message": str(e)}), 500
        
    return render_template('deposit.html', user=user)

@app.route('/admin/deposits')
def admin_deposits():
    if not session.get('admin'): return redirect(url_for('admin_login'))
    all_requests = Deposit.query.order_by(Deposit.timestamp.desc()).all()
    return render_template('admin_deposits.html', requests=all_requests)

@app.route('/admin/approve_deposit/<int:id>')
def approve_deposit(id):
    if not session.get('admin'): return jsonify({"status": "unauthorized"}), 401
    try:
        dep = Deposit.query.get(id)
        if dep and dep.status == "Pending":
            user = User.query.get(dep.user_id)
            user.balance = float(user.balance or 0) + float(dep.amount)
            dep.status = "Approved"
            db.session.commit()
            return jsonify({"status": "success"})
        return jsonify({"status": "error"}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/admin/reject_deposit/<int:id>')
def reject_deposit(id):
    if not session.get('admin'): return jsonify({"status": "unauthorized"}), 401
    try:
        dep = Deposit.query.get(id)
        if dep:
            dep.status = "Rejected"
            db.session.commit()
            return jsonify({"status": "success"})
        return jsonify({"status": "error"}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/auth', methods=['GET', 'POST'])
@app.route('/login', methods=['GET', 'POST'])
def user_auth():
    if request.method == 'POST':
        login_email = request.form.get('email')
        login_password = request.form.get('password')
        user = User.query.filter_by(username=login_email).first()
        if user and user.password == login_password:
            if user.is_blocked:
                flash("Account suspended.")
                return redirect(url_for('user_auth'))
            session['user_id'] = user.id
            return redirect(url_for('home'))
        flash("Invalid login!")
        return redirect(url_for('user_auth'))
    return render_template('auth.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        reg_email = request.form.get('email')
        reg_password = request.form.get('password')
        if User.query.filter_by(username=reg_email).first():
            flash("User exists!")
            return redirect(url_for('register'))
        new_user = User(username=reg_email, password=reg_password, balance=0.0)
        db.session.add(new_user)
        db.session.commit()
        return redirect(url_for('user_auth'))
    return render_template('register.html')

@app.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        if request.form.get('pass') == 'asharib123':
            session['admin'] = True
            return redirect(url_for('admin'))
        flash("Wrong password!")
    return render_template('admin_login.html')

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if not session.get('admin'): return redirect(url_for('admin_login'))
    # Yahan check ho raha hai ke koi pending request hai ya nahi
    pending_count = Deposit.query.filter_by(status="Pending").count()
    return render_template('admin.html', products=Product.query.all(), users=User.query.all(), pending_exists=(pending_count > 0))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('user_auth'))

if __name__ == "__main__":
    app.run(debug=True)
