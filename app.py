from flask import Flask, render_template, request, redirect, url_for
import sqlite3
import random

app = Flask(__name__)


from datetime import datetime
@app.route('/', methods = ["GET","POST"])
def index():
    if request.method == "POST":
        gender = request.form.get('gender')
        age = request.form.get('gender')
        group = ""
        p = random.random() # 0~1
        if p <=0.5:
            group = "A"
        else:
            group = "B"
        # Save data in to db.
        db = sqlite3.connect('static/research.db')
        cur = db.cursor()
        db.execute(
            """
                INSERT INTO participants (age, gender, group_name, created_at, finished_at) VALUES (?,?,?, ?,?)
            """,
            (gender,age,group, datetime.utcnow().isoformat(), "no")
        )
        db.commit()
        if group == "A":
            return redirect(url_for('taskA'))
        else:
            return redirect(url_for('taskB'))
    return render_template('index.html')

# 1. Access Code
# 2. Gender
# 3. Age

@app.route('/taskA')
def taskA():
    return render_template('taskA.html')

@app.route('/taskB')
def taskB():
    return render_template('taskB.html')

if __name__ == "__main__":
    app.run(debug=True)