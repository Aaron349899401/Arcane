from flask import Flask, render_template, request, redirect, url_for, session, send_file, send_from_directory
import sqlite3
import os
from werkzeug.utils import secure_filename
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from io import BytesIO
from functools import wraps

app = Flask(__name__)
app.secret_key = "supersecretkey"

# Upload folder
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# -----------------------
# Database initialization
# -----------------------
def init_db():
    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    # Users table
    c.execute("""
        CREATE TABLE IF NOT EXISTS Users (
            userID INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    """)

    # Transactions table
    c.execute("""
        CREATE TABLE IF NOT EXISTS Transactions (
            transactionID INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL,
            category TEXT NOT NULL,
            amount REAL NOT NULL,
            userID INTEGER,
            FOREIGN KEY (userID) REFERENCES Users(userID)
        )
    """)

    # Files table
    c.execute("""
        CREATE TABLE IF NOT EXISTS Files (
            fileID INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            userID INTEGER,
            FOREIGN KEY (userID) REFERENCES Users(userID)
        )
    """)

    conn.commit()
    conn.close()

init_db()

# -----------------------
# Login required decorator
# -----------------------
def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if 'userID' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return wrapper

# -----------------------
# Routes
# -----------------------

# LOGIN
@app.route('/', methods=['GET','POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = sqlite3.connect("database.db")
        c = conn.cursor()
        c.execute("SELECT userID FROM Users WHERE username=? AND password=?", (username, password))
        user = c.fetchone()
        conn.close()

        if user:
            session['userID'] = user[0]
            return redirect(url_for('dashboard'))
        else:
            error = "Incorrect Username or Password"

    return render_template('login.html', error=error)

# REGISTER
@app.route('/register', methods=['GET','POST'])
def register():
    error = None
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = sqlite3.connect("database.db")
        c = conn.cursor()
        try:
            c.execute("INSERT INTO Users (username, password) VALUES (?,?)", (username, password))
            conn.commit()
            conn.close()
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            error = "Username already exists."
            conn.close()

    return render_template("register.html", error=error)

# LOGOUT
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# DASHBOARD
@app.route('/dashboard')
@login_required
def dashboard():
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("SELECT * FROM Transactions WHERE userID=?", (session['userID'],))
    data = c.fetchall()
    conn.close()
    return render_template('dashboard.html', data=data)

# ADD TRANSACTION
@app.route('/addNewData', methods=['GET','POST'])
@login_required
def add():
    if request.method == 'POST':
        ttype = request.form['type']
        category = request.form['category']
        amount = float(request.form['amount'])

        conn = sqlite3.connect("database.db")
        c = conn.cursor()
        c.execute("INSERT INTO Transactions (type, category, amount, userID) VALUES (?, ?, ?, ?)",
                  (ttype, category, amount, session['userID']))
        conn.commit()
        conn.close()

        return redirect(url_for('dashboard'))

    return render_template('add.html')

# EDIT TRANSACTION
@app.route('/editdata/<int:id>', methods=['GET','POST'])
@login_required
def edit(id):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    if request.method == 'POST':
        category = request.form['category']
        amount = float(request.form['amount'])
        c.execute("UPDATE Transactions SET category=?, amount=? WHERE transactionID=? AND userID=?",
                  (category, amount, id, session['userID']))
        conn.commit()
        conn.close()
        return redirect(url_for('dashboard'))

    c.execute("SELECT * FROM Transactions WHERE transactionID=? AND userID=?", (id, session['userID']))
    data = c.fetchone()
    conn.close()
    return render_template('edit.html', data=data)

# DELETE TRANSACTION
@app.route('/deletedata/<int:id>')
@login_required
def delete(id):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("DELETE FROM Transactions WHERE transactionID=? AND userID=?", (id, session['userID']))
    conn.commit()
    conn.close()
    return redirect(url_for('dashboard'))

# UPLOAD FILES
@app.route('/uploadFile', methods=['GET','POST'])
@login_required
def upload():
    if request.method == 'POST':
        uploaded_files = request.files.getlist('file')
        conn = sqlite3.connect("database.db")
        c = conn.cursor()

        for file in uploaded_files:
            if file:
                filename = secure_filename(file.filename)
                file.save(os.path.join(UPLOAD_FOLDER, filename))
                c.execute("INSERT INTO Files (filename, userID) VALUES (?, ?)", (filename, session['userID']))

        conn.commit()
        conn.close()
        return redirect(url_for('view_files'))

    return render_template('upload.html')

# VIEW FILES
@app.route('/viewFile')
@login_required
def view_files():
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("SELECT filename FROM Files WHERE userID=?", (session['userID'],))
    files = c.fetchall()
    conn.close()
    return render_template('view_files.html', files=files)

# SERVE UPLOADED FILES
@app.route('/uploads/<filename>')
@login_required
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

# VIEW REPORT
@app.route('/viewReport')
@login_required
def view_report():
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("""
        SELECT category, SUM(amount)
        FROM Transactions
        WHERE type='Expense' AND userID=?
        GROUP BY category
    """, (session['userID'],))
    data = c.fetchall()
    conn.close()

    categories = [d[0] for d in data]
    amounts = [d[1] for d in data]

    plt.figure()
    plt.bar(categories, amounts)
    plt.title("Monthly Expenses")

    img_buffer = BytesIO()
    plt.savefig(img_buffer, format='png')
    plt.close()
    img_buffer.seek(0)

    pdf_buffer = BytesIO()
    doc = SimpleDocTemplate(pdf_buffer)
    elements = []
    styles = getSampleStyleSheet()
    elements.append(Paragraph("Monthly Expense Report", styles['Heading1']))
    elements.append(Spacer(1, 0.5 * inch))
    elements.append(Image(img_buffer, width=400, height=300))
    doc.build(elements)
    pdf_buffer.seek(0)

    return send_file(pdf_buffer, as_attachment=False, download_name="report.pdf")

# RUN APP
if __name__ == '__main__':
    app.run(debug=True)
