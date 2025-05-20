from flask import Flask, jsonify

app = Flask(__name__)

@app.route('/healthz')
def healthz():
    return jsonify({"status": "ok"}) 