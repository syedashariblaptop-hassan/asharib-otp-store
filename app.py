import os
import base64
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.pool import QueuePool
from datetime import datetime, timezone
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'asharib_tech_official_key')

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
    password = db.Column(db.String(255), nullable=False)  # Increased length for hash
    is_blocked = db.Column(db.Boolean, default=False)
    balance = db.Column(db.Numeric(10, 2), default=0.0)  # Safe numeric data type for currency
    deposites = db.relationship('Deposit', backref='user', lazy=True)
    orders = db.relationship('Order', backref='user', lazy=True)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    old_price = db.Column(db.String(20))
    price = db.Column(db.String(20))
    stock = db.Column(db.Integer, default=0) 
    keys = db.Column(db.Text, default="") 
    desc = db.Column(db.Text)
    pic = db.Column(db.String(300))
    rating = db.Column(db.String(10), default="4.9")
    reviews = db.Column(db.String(10), default="128")

class Deposit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    proof_url = db.Column(db.Text, nullable=False) 
    status = db.Column(db.String(20), default="Pending")
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    product_name = db.Column(db.String(100), nullable=False)
    delivered_data = db.Column(db.Text, nullable=False) 
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

class SupportChat(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    sender = db.Column(db.String(10), nullable=False) 
    is_read = db.Column(db.Boolean, default=False)     
    status = db.Column(db.String(15), default="Active") 
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    user_rel = db.relationship('User', backref='chats', lazy=True)

with app.app_context():
    try:
        db.create_all()
        print("Database Synchronized Safely!")
    except Exception as e:
        print(f"Error syncing DB: {e}")

# --- Helper function for robust formatting ---
def format_products_safe(products_list):
    processed = []
    for p in products_list:
        try:
            clean_price = float(p.price) if p.price else 0.0
        except ValueError:
            clean_price = 0.0
            
        try:
            clean_old_price = float(p.old_price) if p.old_price else (clean_price * 1.4)
        except ValueError:
            clean_old_price = clean_price * 1.4
            
        processed.append({
            'id': p.id,
            'name': p.name,
            'price': f"{clean_price:.2f}",
            'old_price': f"{clean_old_price:.2f}",
            'stock': p.stock,
            'desc': p.desc,
            'pic': p.pic,
            'rating': p.rating,
            'reviews': p.reviews,
            'keys': p.keys
        })
    return processed

# --- Routes ---

@app.route('/')
def home():
    if not session.get('user_id'): return redirect(url_for('user_auth'))
    user = User.query.get(session['user_id'])
    if not user or user.is_blocked:
        session.clear()
        return redirect(url_for('user_auth'))
    
    search_query = request.args.get('search', '').strip()
    if search_query:
        db_products = Product.query.filter(Product.name.ilike(f'%{search_query}%')).all()
    else:
        db_products = Product.query.all()
        
    safe_products = format_products_safe(db_products)
    user_balance_formatted = f"{float(user.balance or 0.0):.2f}"
    
    try:
        user_deposits = Deposit.query.filter_by(user_id=user.id).order_by(Deposit.timestamp.desc()).all()
        user_orders = Order.query.filter_by(user_id=user.id).order_by(Order.timestamp.desc()).all()
    except Exception:
        user_deposits = []
        user_orders = []
        
    return render_template('store.html', products=safe_products, user=user, user_balance=user_balance_formatted, user_deposits=user_deposits, user_orders=user_orders)

# --- SECURE AUTO BUY ROUTE WITH DATABASE LOCKING ---
@app.route('/buy_product/<int:product_id>', methods=['POST'])
def buy_product(product_id):
    if not session.get('user_id'): return jsonify({"status": "error", "message": "Unauthorized"}), 401
    
    try:
        # Using with_for_update() locks rows in PostgreSQL to prevent race conditions
        user = User.query.with_for_update().get(session['user_id'])
        product = Product.query.with_for_update().get(product_id)
        
        if not user or user.is_blocked: return jsonify({"status": "error", "message": "Account restriction active"}), 403
        if not product: return jsonify({"status": "error", "message": "Product not found"}), 404
        
        try:
            prod_price = float(product.price)
        except ValueError:
            return jsonify({"status": "error", "message": "Product price configuration error"}), 500

        if float(user.balance or 0.0) < prod_price:
            return jsonify({"status": "error", "message": "Low wallet balance! Please recharge first."}), 400
            
        key_lines = [line.strip() for line in (product.keys or "").split('\n') if line.strip()]
        
        if not key_lines or product.stock <= 0:
            return jsonify({"status": "error", "message": "Sorry, this product is temporarily out of stock!"}), 400
            
        delivered_item = key_lines.pop(0)
        product.keys = "\n".join(key_lines)
        product.stock = len(key_lines) 
        
        user.balance = float(user.balance or 0.0) - prod_price
        
        new_order = Order(
            user_id=user.id,
            product_name=product.name,
            delivered_data=delivered_item
        )
        
        db.session.add(new_order)
        db.session.commit()
        
        return jsonify({
            "status": "success", 
            "message": f"Successfully purchased {product.name}!", 
            "delivered_data": delivered_item
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": f"Transaction aborted: {str(e)}"}), 500

@app.route('/deposit', methods=['GET', 'POST'])
def deposit():
    if not session.get('user_id'): return redirect(url_for('user_auth'))
    user = User.query.get(session['user_id'])
    
    if not user:
        session.clear()
        return redirect(url_for('user_auth'))
        
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
        
    user_balance_formatted = f"{float(user.balance or 0.0):.2f}"
    return render_template('deposit.html', user=user, user_balance=user_balance_formatted)

# --- ADMIN ROUTES ---

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if not session.get('admin'): return redirect(url_for('admin_login'))
    
    if request.method == 'POST':
        try:
            name = request.form.get('name')
            old_price = request.form.get('old_price')
            price = request.form.get('price')
            keys_input = request.form.get('keys', '')
            pic = request.form.get('pic')
            desc = request.form.get('desc')
            
            parsed_keys = [k.strip() for k in keys_input.split('\n') if k.strip()]
            calculated_stock = len(parsed_keys)
            
            new_product = Product(
                name=name, old_price=old_price, price=price,
                stock=calculated_stock, keys=keys_input, pic=pic, desc=desc
            )
            db.session.add(new_product)
            db.session.commit()
            return redirect(url_for('admin'))
        except Exception as e:
            db.session.rollback()
            print(f"Product upload error: {e}")
            
    try:
        pending_count = Deposit.query.filter_by(status="Pending").count()
        pending_exists = (pending_count > 0)
    except Exception:
        pending_exists = False
        
    unread_chats = SupportChat.query.filter_by(is_read=False, sender='user').count() > 0
    safe_products = format_products_safe(Product.query.all())
    
    return render_template('admin.html', products=safe_products, users=User.query.all(), pending_exists=pending_exists, edit_product=None, unread_chats=unread_chats)

@app.route('/admin/edit_product/<int:product_id>', methods=['GET', 'POST'])
def edit_product(product_id):
    if not session.get('admin'): return redirect(url_for('admin_login'))
    product = Product.query.get(product_id)
    if not product: return redirect('/admin')
        
    if request.method == 'POST':
        try:
            product.name = request.form.get('name')
            product.old_price = request.form.get('old_price')
            product.price = request.form.get('price')
            product.keys = request.form.get('keys', '')
            
            parsed_keys = [k.strip() for k in product.keys.split('\n') if k.strip()]
            product.stock = len(parsed_keys)
            
            product.pic = request.form.get('pic')
            product.desc = request.form.get('desc')
            db.session.commit()
            return redirect('/admin')
        except Exception as e:
            db.session.rollback()
            print(f"Product edit error: {e}")
            
    pending_exists = Deposit.query.filter_by(status="Pending").count() > 0
    unread_chats = SupportChat.query.filter_by(is_read=False, sender='user').count() > 0
    safe_products = format_products_safe(Product.query.all())
    
    return render_template('admin.html', products=safe_products, users=User.query.all(), pending_exists=pending_exists, edit_product=product, unread_chats=unread_chats)

@app.route('/admin/delete_product/<int:product_id>', methods=['GET', 'POST'])
def delete_product(product_id):
    if not session.get('admin'): return redirect(url_for('admin_login'))
    product = Product.query.get(product_id)
    if product:
        try:
            db.session.delete(product)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print(f"Product delete error: {e}")
    return redirect('/admin')

@app.route('/admin/toggle_block/<int:user_id>', methods=['GET', 'POST'])
def toggle_block(user_id):
    if not session.get('admin'): return redirect(url_for('admin_login'))
    user = User.query.get(user_id)
    if user:
        try:
            user.is_blocked = not user.is_blocked
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print(f"Toggle block error: {e}")
    return redirect('/admin')

@app.route('/admin/delete_user/<int:user_id>', methods=['GET', 'POST'])
def delete_user(user_id):
    if not session.get('admin'): return redirect(url_for('admin_login'))
    user = User.query.get(user_id)
    if user:
        try:
            db.session.delete(user)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print(f"Delete user error: {e}")
    return redirect('/admin')

@app.route('/admin/update_balance/<int:user_id>/<string:amount>', methods=['GET', 'POST'])
def update_balance(user_id, amount):
    if not session.get('admin'): return redirect(url_for('admin_login'))
    user = User.query.get(user_id)
    if user:
        try:
            user.balance = float(amount)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print(f"Update balance error: {e}")
    return redirect('/admin')

@app.route('/admin/deposits')
def admin_deposits():
    if not session.get('admin'): return redirect(url_for('admin_login'))
    all_requests = Deposit.query.order_by(Deposit.timestamp.desc()).all()
    return render_template('admin_deposits.html', requests=all_requests)

@app.route('/admin/approve_deposit/<int:id>')
def approve_deposit(id):
    if not session.get('admin'): return jsonify({"status": "unauthorized"}), 401
    try:
        dep = Deposit.query.with_for_update().get(id)
        if dep and dep.status == "Pending":
            user = User.query.with_for_update().get(dep.user_id)
            user.balance = float(user.balance or 0.0) + float(dep.amount)
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


# --- LIVE SUPPORT CHAT SYSTEM ---

@app.route('/api/chat/send', methods=['POST'])
def chat_send_user():
    if not session.get('user_id'): return jsonify({"status": "unauthorized"}), 401
    data = request.get_json()
    msg_text = data.get('message', '').strip()
    
    if not msg_text: return jsonify({"status": "error", "message": "Empty message"}), 400
    
    new_msg = SupportChat(
        user_id=session['user_id'], message=msg_text, sender='user', is_read=False, status='Active'
    )
    db.session.add(new_msg)
    db.session.commit()
    return jsonify({"status": "success"})

@app.route('/api/chat/admin_send/<int:user_id>', methods=['POST'])
def chat_send_admin(user_id):
    if not session.get('admin'): return jsonify({"status": "unauthorized"}), 401
    data = request.get_json()
    msg_text = data.get('message', '').strip()
    
    if not msg_text: return jsonify({"status": "error", "message": "Empty message"}), 400

    if msg_text.lower() == '.close':
        SupportChat.query.filter_by(user_id=user_id, status='Active').update({SupportChat.status: 'Closed'})
        close_msg = SupportChat(
            user_id=user_id, message="SYSTEM_NOTIFICATION: Chat has been closed by admin.",
            sender='admin', is_read=True, status='Closed'
        )
        db.session.add(close_msg)
        db.session.commit()
        return jsonify({"status": "closed", "message": "Chat closed successfully."})

    new_msg = SupportChat(
        user_id=user_id, message=msg_text, sender='admin', is_read=True, status='Active'
    )
    db.session.add(new_msg)
    db.session.commit()
    return jsonify({"status": "success"})

@app.route('/api/chat/fetch/<int:user_id>')
def chat_fetch(user_id):
    if not session.get('admin') and session.get('user_id') != user_id:
        return jsonify({"status": "unauthorized"}), 401
        
    chats = SupportChat.query.filter_by(user_id=user_id).order_by(SupportChat.timestamp.asc()).all()
    
    if session.get('admin'):
        SupportChat.query.filter_by(user_id=user_id, is_read=False).update({SupportChat.is_read: True})
        db.session.commit()
        
    messages_list = []
    chat_status = "Active"
    if chats:
        chat_status = chats[-1].status  
    
    for c in chats:
        messages_list.append({
            "sender": c.sender,
            "message": c.message,
            "time": c.timestamp.strftime('%I:%M %p')
        })
        
    return jsonify({"messages": messages_list, "chat_status": chat_status})

@app.route('/api/chat/unread_check')
def chat_unread_check():
    if not session.get('admin'): return jsonify({"unread": False})
    unread_exists = SupportChat.query.filter_by(is_read=False, sender='user').count() > 0
    return jsonify({"unread": unread_exists})

@app.route('/api/chat/reset', methods=['POST'])
def chat_reset():
    if not session.get('user_id'): return jsonify({"status": "unauthorized"}), 401
    try:
        user_id = session['user_id']
        SupportChat.query.filter_by(user_id=user_id).update({SupportChat.status: 'Closed'})
        
        init_msg = SupportChat(
            user_id=user_id, message="SYSTEM_NOTIFICATION: User has started a new support session.",
            sender='user', is_read=False, status='Active'
        )
        db.session.add(init_msg)
        db.session.commit()
        
        return jsonify({"status": "success", "message": "New support session initialized."})
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500


# --- USER AUTHENTICATION (SECURED) ---

@app.route('/auth', methods=['GET', 'POST'])
@app.route('/login', methods=['GET', 'POST'])
def user_auth():
    if request.method == 'POST':
        login_email = request.form.get('email')
        login_password = request.form.get('password')
        user = User.query.filter_by(username=login_email).first()
        
        # Verify hash match safely
        if user and check_password_hash(user.password, login_password):
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
            
        # Creating a secure cryptographic string hash
        hashed_password = generate_password_hash(reg_password)
        new_user = User(username=reg_email, password=hashed_password, balance=0.0)
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

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('user_auth'))

if __name__ == "__main__":
    app.run(debug=True)
