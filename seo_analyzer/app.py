# seo_analyzer/app.py
import os
import argparse
import flask
from flask_cors import CORS
from functools import wraps
from .tasks import run_analysis_task 
import tempfile
import uuid

app = flask.Flask(__name__, static_folder='../assets', static_url_path='/assets')
CORS(app)

SECRET_API_KEY = "my-secret-dev-key" 

def require_api_key(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if flask.request.headers.get('X-API-KEY') != SECRET_API_KEY:
            return flask.jsonify({"error": "Invalid or missing API key"}), 403
        return f(*args, **kwargs)
    return decorated_function

@app.route("/")
def index():
    """Serve the main HTML file."""
    return flask.send_from_directory('..', 'range-gap-finder.html')

@app.route("/range-gap-finder.html")
def main_page():
    """Serve the main HTML file."""
    return flask.send_from_directory('..', 'range-gap-finder.html')

@app.route("/process", methods=["POST"])
@require_api_key
def start_processing():
    try:
        if 'ourFile' not in flask.request.files or 'competitorFiles' not in flask.request.files:
            return flask.jsonify({"error": "Missing required files."}), 400
        
        our_file = flask.request.files['ourFile']
        competitor_files = flask.request.files.getlist('competitorFiles')
        onsite_file = flask.request.files.get('onsiteFile')
        options = flask.request.form['options']

        temp_dir = tempfile.mkdtemp()
        our_file_path = os.path.join(temp_dir, f"{uuid.uuid4()}.csv")
        our_file.save(our_file_path)

        competitor_file_paths = []
        for f in competitor_files:
            path = os.path.join(temp_dir, f"{uuid.uuid4()}.csv")
            f.save(path)
            competitor_file_paths.append(path)

        onsite_file_path = None
        if onsite_file:
            onsite_file_path = os.path.join(temp_dir, f"{uuid.uuid4()}.csv")
            onsite_file.save(onsite_file_path)

        task = run_analysis_task.delay(
            our_file_path, competitor_file_paths, onsite_file_path, options, temp_dir
        )
        return flask.jsonify({"task_id": task.id}), 202
    except Exception as e:
        return flask.jsonify({"error": f"Failed to start task: {e}"}), 400

@app.route("/status/<task_id>", methods=["GET"])
@require_api_key
def task_status(task_id):
    """Poll this endpoint with a task ID to get the status of a running task."""
    task = run_analysis_task.AsyncResult(task_id)
    
    if task.state == 'PENDING':
        response = {'state': task.state, 'status': 'Task is pending...'}
    # --- THIS IS THE NEW BLOCK ---
    elif task.state == 'PROGRESS':
        response = {
            'state': task.state,
            'info': task.info # Pass the whole meta dictionary
        }
    # --- END OF NEW BLOCK ---
    elif task.state == 'SUCCESS':
        response = {'state': task.state, 'result': task.result}
    elif task.state != 'FAILURE':
        response = {'state': task.state, 'status': 'In progress...'}
    else: # Handle failure
        response = {
            'state': task.state,
            'error': str(task.info)
        }
    return flask.jsonify(response)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Run Flask app.')
    parser.add_argument('--port', type=int, default=5001, help='Port to run on.')
    args = parser.parse_args()
    app.run(debug=True, port=args.port)