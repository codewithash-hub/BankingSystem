from sqlite3 import IntegrityError
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_bcrypt import Bcrypt
from flask_migrate import Migrate
from datetime import datetime
from models import User, db

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///banking.db'
app.config['SECRET_KEY'] = '12345'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
migrate = Migrate(app, db)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), nullable=False, unique=True)
    email = db.Column(db.String(150), nullable=False, unique=True)
    password = db.Column(db.String(256), nullable=False)
    balance = db.Column(db.Float, default=0.0)

class Transaction(db.Model):
    __tablename__ = 'transaction'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    transaction_type = db.Column(db.String(20), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    recipient_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)

    recipient = db.relationship("User", foreign_keys=[recipient_id], backref="received_transactions")


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route('/')
def home():
    return render_template('index.html')

# Function to register
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')

        # Check if username or email already exists
        if User.query.filter_by(username=username).first():
            flash("Username already taken. Please choose another one.", "danger")
            return redirect(url_for('register'))

        if User.query.filter_by(email=email).first():
            flash("Email is already registered. Please use a different email.", "danger")
            return redirect(url_for('register'))

        try:
            # Hash the password and create a new user
            hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
            new_user = User(username=username, email=email, password=hashed_password)

            db.session.add(new_user)
            db.session.commit()

            flash("Registration successful! Please log in.", "success")
            return redirect(url_for('login'))

        except IntegrityError:
            db.session.rollback()  # Rollback changes if an error occurs
            flash("An error occurred during registration. Please try again.", "danger")

    return render_template('register.html')

# Function to login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        user = User.query.filter_by(email=email).first()
        if user and bcrypt.check_password_hash(user.password, password):
            login_user(user)
            flash("Login successful!", "success")
            return redirect(url_for('dashboard'))

        flash("Invalid credentials. Try again.", "danger")

    return render_template('login.html')

# Function to display the dashboard
@app.route('/dashboard')
@login_required
def dashboard():
    user = User.query.get(current_user.id)
    return render_template('dashboard.html', user=user)

# Function to logout
@app.route('/logout')
@login_required
def logout():
    logout_user()
    return render_template('logout.html')

# Function to deposit
@app.route('/deposit', methods=['POST'])
@login_required
def deposit():
    amount = float(request.form['amount'])
    current_user.balance += amount

    transaction = Transaction(user_id=current_user.id, amount=amount, transaction_type='deposit')
    db.session.add(transaction)
    db.session.commit()

    print(f"Transaction Added: {transaction.transaction_type} of {transaction.amount}")

    flash("Deposit successful!", "success")
    return redirect(url_for('dashboard'))

# Function to withdraw money
@app.route('/withdraw', methods=['POST'])
@login_required
def withdraw():
    amount = float(request.form['amount'])

    if amount > current_user.balance:
        flash("Insufficient funds!", "danger")
    else:
        current_user.balance -= amount
        transaction = Transaction(
            user_id=current_user.id, 
            amount=-amount, 
            transaction_type='withdraw',
            recipient_id=current_user.id
        )
        db.session.add(transaction)
        db.session.commit()
        flash("Withdrawal successful!", "success")

    return redirect(url_for('dashboard'))

# Function to show transaction
@app.route('/transactions')
@login_required
def transactions():
    user_transactions = Transaction.query.filter_by(user_id=current_user.id).order_by(Transaction.timestamp.desc()).all()
    return render_template('transactions.html', transactions=user_transactions)

# Function to handle transfer
@app.route('/transfer', methods=['POST'])
@login_required
def transfer():
    recipient_username = request.form.get('recipient')
    amount = float(request.form.get('amount'))

    recipient = User.query.filter_by(username=recipient_username).first()

    if not recipient:
        flash("Recipient not found!", "danger")
        return redirect(url_for('dashboard'))

    if amount <= 0:
        flash("Invalid transfer amount!", "danger")
        return redirect(url_for('dashboard'))

    if current_user.balance < amount:
        flash("Insufficient funds!", "danger")
        return redirect(url_for('dashboard'))

    print(f"Before Transfer: Sender({current_user.username}) = {current_user.balance}, Recipient({recipient.username}) = {recipient.balance}")

    # Deduct from sender
    current_user.balance -= amount
    sender_transaction = Transaction(
        user_id=current_user.id, 
        amount=-amount, 
        transaction_type='transfer', 
        recipient_id=recipient.id
    )

    # Add to recipient
    recipient.balance += amount
    recipient_transaction = Transaction(
        user_id=recipient.id, 
        amount=amount, 
        transaction_type='received', 
        recipient_id=current_user.id
    )

    # Save changes
    db.session.add(sender_transaction)
    db.session.add(recipient_transaction)
    db.session.commit()
    print(f"Sender Transaction: user_id={current_user.id}, amount={-amount}, recipient_id={recipient.id}")
    print(f"Recipient Transaction: user_id={recipient.id}, amount={amount}, recipient_id={current_user.id}")
    print(f"After Transfer: Sender({current_user.username}) = {current_user.balance}, Recipient({recipient.username}) = {recipient.balance}")
        
    flash(f"Successfully transferred R {amount} to {recipient.username}!", "success")
    return redirect(url_for('dashboard'))



if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
