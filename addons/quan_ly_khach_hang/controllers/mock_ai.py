from flask import Flask, request, jsonify
app = Flask(__name__)

@app.route('/api/sentiment', methods=['POST'])
def sentiment():
    data = request.get_json() or {}
    text = (data.get('text','') or '').lower()
    if any(w in text for w in ['bad','hate','ngu','tệ']):
        return jsonify({'label':'negative','score':0.92})
    if any(w in text for w in ['ok','fine','khá']):
        return jsonify({'label':'neutral','score':0.5})
    return jsonify({'label':'positive','score':0.9})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)