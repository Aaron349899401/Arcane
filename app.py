from flask import Flask, flash, render_template, request, redirect, url_for, session, send_file, send_from_directory
import sqlite3
import os
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from io import BytesIO
from datetime import date

# looks for folders "templates"(HTML) and "static"(CSS) by default in the ARCANE folder
# basically just creates a path to folders or files within its current directory (for security reasons)
app = Flask(__name__) # tells Flask "look for my files in the same folder this program is located in"
app.secret_key = os.urandom(24) # the secret key signs your userID, and turns it into a long gibberish string (the cookie; 24 chars)

# Upload folder
UPLOAD_FOLDER = "uploads"
# just makes a folder named "uploads" basically
os.makedirs(UPLOAD_FOLDER, exist_ok=True) # exist_ok=True, means if the folder already exists, dont crash


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
            date DATE NOT NULL,
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

    # Settings table
    c.execute("""
        CREATE TABLE IF NOT EXISTS Settings (
            userID INTEGER PRIMARY KEY,
            max_percentage REAL DEFAULT 30,
            monthly_budget_goal INTEGER NOT NULL
        );
    """)

    conn.commit()
    conn.close()

init_db()

def login_required(func):
    from functools import wraps
    @wraps(func)
    def wrapper(*args, **kwargs):
        if 'userID' not in session:
            return redirect(url_for('login'))
        return func(*args, **kwargs)
    return wrapper


# LOGIN
@app.route('/', methods=['GET','POST']) # IF you dont define both and a user tries to submit somting, the server throws a 405 Method not allowed error
def login():
    error = None
    if request.method == 'POST':
        # retrieves/fetchs the data they "POST"ed or submitted after clicking submit
        # request.form is a dictionary containing POST form data
        username = request.form['username'] 
        password = request.form['password'] # In real world apps, you dont store passwords in real text, you use a hash via something like Werkzeug
        conn = sqlite3.connect("database.db")
        c = conn.cursor() # cursor object: what actually executes SQL commands
        # compares the username and password from the submission with that of the database
        c.execute("SELECT userID, password FROM Users WHERE username=?", (username,)) # SQLite returns rows as tuples by default
        # gets the first matching userID from the query executed above; the ? are replaced by the tuple on the right using Flask (?=placeholder)
        # the ? prevents SQL injection, if a hacker puts "admin" or "1"="1" as their username, it will always evaluate to True, the ? treats every inputs as plain text not commands
        # there will only ever be one row, or none since usernames and passwords are all unique
        user = c.fetchone() # user is either a tuple holding one userID or it is None (no username/password matches the POST in the database.db)
        conn.close() # frees resources for other tasks

        if user and check_password_hash(user[1], password): # checks if the user exists in the database/has an account
            session['userID'] = user[0] # session is initiated via imports from Flask
            # by nature the internet is stateless, meaning when you click a link to go to a diff page, the server completly forgets who you are, 
            # session solves this by creating a key (stored as a cookie in their browser)
            return redirect(url_for('dashboard'))
        else:
            error = "Incorrect Username or Password"
            # if user == False, error is no longer None and is then returned/served down below
    return render_template('login.html', error=error) # elif GET, serves the empty login form: safe, idempotent (API request that produces the same result regardless of how many times it is executed: deleting user 1 mutiple times)
    # if the error else blokc was activated, error will no longer be None, meaning the kwarg, error, will be displayed as "Incorrect U..."

# REGISTER
@app.route('/register', methods=['GET','POST']) 
def register():
    error = None
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        hashed_pw = generate_password_hash(password)
        conn = sqlite3.connect("database.db")
        c = conn.cursor()
        try: # this try except block is just to see if the username already exists in the databse.db
            # if the username is unique, the insertion will succeed, if not then it will raise an IntegrityError
            c.execute("INSERT INTO Users (username, password) VALUES (?,?)", (username, hashed_pw))
            conn.commit() # saves the changes to the database, without this, the new user wouldn't actually be remembred
            conn.close() # always make sure to free up memory by closing the connection
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            error = "Username or Password is already in use"
            conn.close()

    return render_template("register.html", error=error)

# LOGOUT
@app.route('/logout') # tells Flask, whenever someone visits this URL, run this function
def logout():
    session.clear() # removes the userID from the session dict
    # each browser (user) has thier own personal session, 
    # Flask identifies users by a session cookie stored in thier browser
    # session can hold more then userIDs, for example: (in this code it is only used for userIDs)
    #   session["language"] = "eng", or session["theme"] = "dark"
    return redirect(url_for('login'))

# DASHBOARD
@app.route('/dashboard')
@login_required
def dashboard():
    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    # All transactions
    c.execute("SELECT * FROM Transactions WHERE userID=?", (session["userID"],))
    data = c.fetchall()

    # Totals
    c.execute("SELECT SUM(amount) FROM Transactions WHERE type='Income' AND userID=?", (session['userID'],))
    total_income = c.fetchone()[0] or 0

    c.execute("SELECT SUM(amount) FROM Transactions WHERE type='Expense' AND userID=?", (session['userID'],))
    total_expense = c.fetchone()[0] or 0

    # Category breakdown
    c.execute("""
        SELECT category, SUM(amount) 
        FROM Transactions 
        WHERE type='Expense' AND userID=?
        GROUP BY category
    """, (session['userID'],))
    category_expenses = c.fetchall()

    percentages = []
    for category, amount in category_expenses:
        pct = (amount / total_expense) * 100 if total_expense > 0 else 0
        percentages.append((category, amount, pct))

    # Get settings
    c.execute("SELECT max_percentage, monthly_budget_goal FROM Settings WHERE userID=?", (session['userID'],))
    row = c.fetchone()

    if row is None:
        c.execute("""
            INSERT INTO Settings (userID, max_percentage, monthly_budget_goal) 
            VALUES (?, ?, ?)
        """, (session['userID'], 30, 1000))
        conn.commit()
        max_pct = 30
        monthly_budget_goal = 1000
    else:
        max_pct = row[0]
        monthly_budget_goal = row[1] or 1

    # Monthly expense progress
    today = date.today()
    first_day = today.replace(day=1)
    first_day_str = first_day.isoformat()
    c.execute("""
        SELECT amount FROM Transactions 
        WHERE date >= ? AND type='Expense' AND userID=?
    """, (first_day_str, session['userID']))

    rows = c.fetchall()
    expenses_this_month = [row[0] for row in rows]
    monthly_total = sum(expenses_this_month)

    progress = (monthly_total / monthly_budget_goal) * 100 if monthly_budget_goal > 0 else 0

    net_worth = total_income - total_expense

    conn.close()

    return render_template(
        'dashboard.html',
        data=data,
        total_income=total_income,
        total_expense=total_expense,
        net_worth=net_worth,
        percentages=percentages,
        max_pct=max_pct,
        progress=progress, 
        monthly_budget_goal=monthly_budget_goal)

# ADD 
@app.route('/add', methods=['GET','POST'])
@login_required
def add():
    if request.method == 'POST':
        ttype = request.form['type']
        category = request.form['category']
        amount = request.form['amount']

        # Validate amount is numeric
        try:
            amount = float(amount)
        except ValueError:
            flash("Amount must be a number.", "danger")
            return redirect("/add")

        # Validate amount is positive
        if amount <= 0:
            flash("Amount must be greater than zero.", "danger")
            return redirect("/add")

        # Validate category is not empty
        if not category.strip():
            flash("Category cannot be empty.", "danger")
            return redirect("/add")

        # now we can save the transaction data
        userID = session['userID']
        conn = sqlite3.connect("database.db")
        c = conn.cursor()
        today = date.today().isoformat()

        c.execute("""
            INSERT INTO Transactions (type, category, amount, date, userID)
            VALUES (?, ?, ?, ?, ?)
        """, (ttype, category, amount, today, userID))
        amount = request.form.get("amount")
        conn.commit()
        conn.close()
        return redirect(url_for('dashboard'))

    return render_template('add.html')

# EDIT 
@app.route('/edit/<int:id>', methods=['GET','POST']) # the var, id, is the transactionID of the row you are editing in the table
@login_required
def edit(id):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    if request.method == 'POST': # actually updates the data changed
        category = request.form['category']
        amount = float(request.form['amount'])
        c.execute("UPDATE Transactions SET category=?, amount=? WHERE transactionID=? AND userID=?",
                  (category, amount, id, session['userID'])) 
        # updates the category and amount values in the transaction table to what was posted(entered) 
        # at the row where the transactionID matchs the one being edited currently by the user in session
        conn.commit()
        conn.close()
        return redirect(url_for('dashboard'))

    c.execute("SELECT * FROM Transactions WHERE transactionID=? AND userID=?", (id, session['userID']))
    data = c.fetchone() # data represents all the columns/values in that row of the transactions table
    conn.close()
    return render_template('edit.html', data=data)

# SKBIDI DELETE
@app.route('/delete/<int:id>')
@login_required
def delete(id):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("DELETE FROM Transactions WHERE transactionID=? AND userID=?", (id, session['userID']))
    # deletes row in the table based on the matching transactionID and userID in session
    conn.commit()
    conn.close()
    return redirect(url_for('dashboard'))

# UPLOAD THE EPSTEIN FILES
@app.route('/uploadFile', methods=['GET','POST'])
@login_required
def upload():
    if request.method == 'POST':
        uploaded_files = request.files.getlist('file') # returns the files submitted by the user in session
        conn = sqlite3.connect("database.db")
        c = conn.cursor()

        for file in uploaded_files:
            if file:
                filename = secure_filename(file.filename)
                file.save(os.path.join(UPLOAD_FOLDER, filename)) # saves the file in the uploads folder
                c.execute("INSERT INTO Files (filename, userID) VALUES (?, ?)", (filename, session['userID']))

        conn.commit()
        conn.close()
        return redirect(url_for('view_files')) 
        # after saving the files submitted by the user in the database and uploads folder, they are immediatly sent to view the files

    return render_template('upload.html')

# VIEW THE EPTEIN FILES
@app.route('/viewFiles')
@login_required
def view_files():
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("SELECT filename FROM Files WHERE userID=?", (session['userID'],))
    files = c.fetchall()
    conn.close()
    return render_template('view_files.html', files=files)

# DELETE FILE
@app.route('/delete_file/<filename>', methods=['POST'])
@login_required
def delete_file(filename):
    file_path = os.path.join(UPLOAD_FOLDER, filename)
    if os.path.exists(file_path):
        os.remove(file_path)

    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("DELETE FROM Files WHERE userID=? AND fileID=?", (session["userID"], fileID))
    conn.commit()
    conn.close()

    return redirect(url_for('view_files'))

# SERVE UPLOADED FILES
@app.route('/uploads/<filename>')
@login_required
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename) # returns the file from the uploads folder based on it s filename

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
    """, (session['userID'],)) # all rows with the same category are grouped together, and the amounts are summed
    data = c.fetchall()
    conn.close()

    categories = [d[0] for d in data]
    amounts = [d[1] for d in data]

    # BAR CHART
    plt.figure() # creates a figure
    plt.bar(categories, amounts) # creates a bar graph
    plt.title("Monthly Expenses") # adds the title
    bar_buffer = BytesIO()
    plt.savefig(bar_buffer, format='png')
    plt.close()
    bar_buffer.seek(0)

    # PIE CHART
    colors = plt.cm.tab20(np.linspace(0, 1, len(categories)))
    plt.figure()
    plt.pie(amounts, labels=categories, colors=colors, autopct="%1.1f%%")
    plt.title("Expense Breakdown")
    pie_buffer = BytesIO()
    plt.savefig(pie_buffer, format='png')
    plt.close()
    pie_buffer.seek(0)

    # PDF BUILDER
    pdf_buffer = BytesIO()
    doc = SimpleDocTemplate(pdf_buffer)
    elements = []
    styles = getSampleStyleSheet()

    elements.append(Paragraph("Monthly Expense Report", styles['Heading1']))
    elements.append(Spacer(1, 0.5 * inch))

    # Add bar chart
    elements.append(Image(bar_buffer, width=400, height=300))
    elements.append(Spacer(1, 0.5 * inch))

    # Add pie chart
    elements.append(Image(pie_buffer, width=400, height=300))

    doc.build(elements)
    pdf_buffer.seek(0)

    return send_file(pdf_buffer, as_attachment=False, download_name="report.pdf")

# SETTINGs
@app.route('/settings', methods=['POST'])
@login_required
def settings():
    userID = session['userID']

    # Always clear the flag at the start of a new request
    session.pop("open_settings_modal", None)

    new_max = request.form.get('max_percentage')
    monthly_budget_goal = request.form.get('monthly_budget_goal')

    # Validate max percentage
    try:
        new_max = float(new_max)
    except (ValueError, TypeError):
        session["open_settings_modal"] = True
        flash("Max percentage must be a number.", "danger")
        return redirect("/dashboard")

    if new_max <= 0 or new_max > 100:
        session["open_settings_modal"] = True
        flash("Max percentage must be between 1 and 100.", "danger")
        return redirect("/dashboard")

    # Validate monthly budget goal
    try:
        monthly_budget_goal = float(monthly_budget_goal)
    except (ValueError, TypeError):
        session["open_settings_modal"] = True
        flash("Monthly budget goal must be a number.", "danger")
        return redirect("/dashboard")

    if monthly_budget_goal <= 0:
        session["open_settings_modal"] = True
        flash("Monthly budget goal must be greater than zero.", "danger")
        return redirect("/dashboard")

    # Save settings
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("""
        UPDATE Settings
        SET max_percentage=?, monthly_budget_goal=?
        WHERE userID=?
    """, (new_max, monthly_budget_goal, userID))
    conn.commit()
    conn.close()

    flash("Settings updated!", "success")
    return redirect("/dashboard")

# RUN APP
if __name__ == '__main__': # name is a built in python var that is automatically set to the string "__main__" when its is run
    app.run(debug=True) # but, if the file is imported as a module, __name__ will not be set to the files actual name, and thus will not run.
# if an error occurs, debug displays a detailed traceback and an interactive console in your browser to help fix the issue 