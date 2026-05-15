from flask import Flask, render_template, request, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.secret_key = "asharib_tech_official_key"
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
db = SQLAlchemy(app)

# Database Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(100), unique=True)
    password = db.Column(db.String(100))

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    old_price = db.Column(db.String(20))
    price = db.Column(db.String(20))
    stock = db.Column(db.String(50))
    desc = db.Column(db.Text)
    pic = db.Column(db.String(300))

with app.app_context():
    db.create_all()

@app.route('/')
def home():
    if not session.get('user_logged_in'): return redirect(url_for('user_auth'))
    all_products = Product.query.all()
    return render_template('store.html', products=all_products)

@app.route('/auth')
def user_auth():
    return render_template('auth.html')

@app.route('/register_user', methods=['POST'])
def register_user():
    email = request.form.get('email')
    password = request.form.get('pass')
    if not User.query.filter_by(email=email).first():
        new_user = User(email=email, password=password)
        db.session.add(new_user)
        db.session.commit()
        return render_template('congrats.html')
    return "Email already exists!"

@app.route('/login_user', methods=['POST'])
def login_user():
    user = User.query.filter_by(email=request.form.get('email'), password=request.form.get('pass')).first()
    if user:
        session['user_logged_in'] = True
        return redirect(url_for('home'))
    return "Invalid Credentials!"

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if not session.get('admin'): return redirect(url_for('admin_login'))
    if request.method == 'POST':
        new_p = Product(name=request.form['name'], old_price=request.form['old_price'], price=request.form['price'], stock=request.form['stock'], desc=request.form['desc'], pic=request.form['pic'])
        db.session.add(new_p)
        db.session.commit()
        return redirect(url_for('admin'))
    
    all_p = Product.query.all()
    all_u = User.query.all() # Admin can see users
    return render_template('admin.html', products=all_p, users=all_u)

@app.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST' and request.form.get('pass') == 'asharib123':
        session['admin'] = True
        return redirect(url_for('admin'))
    return '''<body style="background:#111;color:white;text-align:center;padding-top:100px;">
              <form method="post"><h2>Admin Panel</h2><input type="password" name="pass"><button>Login</button></form></body>'''

@app.route('/delete/<int:id>')
def delete(id):
    p = Product.query.get(id)
    if p: db.session.delete(p)
    db.session.commit()
    return redirect(url_for('admin'))

if __name__ == '__main__':
    app.run(debug=True)