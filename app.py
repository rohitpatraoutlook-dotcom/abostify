from flask import Flask, jsonify, render_template

app = Flask(__name__)

@app.get("/")
def home():
    return render_template("index.html")

@app.get("/health")
def health():
    return jsonify(
        app="ABOSTIFY",
        status="healthy",
        version="toy-0.1"
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
