from flask import Flask, render_template, request, redirect, url_for, session, send_file
import sqlite3
import os
from werkzeug.utils import secure_filename
import matplotlib.pyplot as plt
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import Table
from io import BytesIO

app = Flask(__name__)
app.secret_key = "supersecretkey"
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# database
def init_db():
    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT
    )
    """)
    c.execute("SELECT * FROM users WHERE username='Steve'")
    if not c.fetchone():
        c.execute("INSERT INTO users (username, password) VALUES (?, ?)", 
                  ("Aaron", "Skibidi Ohio Rizz"))

    c.execute("""
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        type TEXT,
        category TEXT,
        amount REAL,
        user_id INTEGER
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS files (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filename TEXT,
        user_id INTEGER
    )
    """)

    conn.commit()
    conn.close()

init_db()

# logn
def login_required(func):
    from functools import wraps
    @wraps(func)
    def wrapper(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return func(*args, **kwargs)
    return wrapper

@app.route('/', methods=['GET','POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = sqlite3.connect("database.db")
        c = conn.cursor()
        c.execute("SELECT id FROM users WHERE username=? AND password=?", (username,password))
        user = c.fetchone()
        conn.close()

        if user:
            session['user_id'] = user[0]
            return redirect(url_for('dashboard'))
        else:
            error = "Incorrect Password"
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# dash
@app.route('/dashboard')
@login_required
def dashboard():
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("SELECT * FROM transactions WHERE user_id=?", (session['user_id'],))
    data = c.fetchall()
    conn.close()
    return render_template('dashboard.html', data=data)

# adding entries
@app.route('/addNewData', methods=['GET','POST'])
@login_required
def add():
    if request.method == 'POST':
        ttype = request.form['type']
        category = request.form['category']
        amount = float(request.form['amount'])

        conn = sqlite3.connect("database.db")
        c = conn.cursor()
        c.execute("INSERT INTO transactions (type, category, amount, user_id) VALUES (?,?,?,?)",
                  (ttype,category,amount,session['user_id']))
        conn.commit()
        conn.close()
        return redirect(url_for('dashboard'))

    return render_template('add.html')

# editing/changing entries
@app.route('/editdata/<int:id>', methods=['GET','POST'])
@login_required
def edit(id):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    if request.method == 'POST':
        category = request.form['category']
        amount = float(request.form['amount'])
        c.execute("UPDATE transactions SET category=?, amount=? WHERE id=?",
                  (category,amount,id))
        conn.commit()
        conn.close()
        return redirect(url_for('dashboard'))

    c.execute("SELECT * FROM transactions WHERE id=?", (id,))
    data = c.fetchone()
    conn.close()
    return render_template('edit.html', data=data)

# deleting stuff
@app.route('/deletedata/<int:id>')
@login_required
def delete(id):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("DELETE FROM transactions WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('dashboard'))

# File upload
@app.route('/uploadFile', methods=['GET','POST'])
@login_required
def upload():
    if request.method == 'POST':
        files = request.files.getlist('file')
        conn = sqlite3.connect("database.db")
        c = conn.cursor()
        for file in files:
            if file:
                filename = secure_filename(file.filename)
                file.save(os.path.join(UPLOAD_FOLDER, filename))
                c.execute("INSERT INTO files (filename,user_id) VALUES (?,?)",
                          (filename,session['user_id']))
        conn.commit()
        conn.close()
        return redirect(url_for('view_files'))
    return render_template('upload.html')

# To Open FIle
@app.route('/viewFile')
@login_required
def view_files():
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("SELECT filename FROM files WHERE user_id=?", (session['user_id'],))
    files = c.fetchall()
    conn.close()
    return render_template('view_files.html', files=files)

# PDF Report Thingy
@app.route('/viewReport')
@login_required
def view_report():
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("SELECT category, SUM(amount) FROM transactions WHERE type='Expense' AND user_id=? GROUP BY category",
              (session['user_id'],))
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
    elements.append(Spacer(1,0.5*inch))

    elements.append(Image(img_buffer, width=400, height=300))

    doc.build(elements)
    pdf_buffer.seek(0)

    return send_file(pdf_buffer, as_attachment=False, download_name="report.pdf")

if __name__ == '__main__':
    app.run(debug=True)