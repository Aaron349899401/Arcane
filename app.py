from flask import Flask, render_template
app = Flask(__name__)

@app.route("/")
def index():
    return "Skibidi Sigmas Are Welcome!"

if __name__ == "__main__":
    app.run(debug=True)