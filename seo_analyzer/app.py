# seo_analyzer/app.py
import os
import argparse
import flask
from flask_cors import CORS
from functools import wraps
try:
    from .tasks import run_analysis_task
    from .synonym_discovery import SynonymDiscovery
    from .project_manager import ProjectManager
except ImportError:
    from tasks import run_analysis_task
    from synonym_discovery import SynonymDiscovery
    from project_manager import ProjectManager
import tempfile
import uuid

app = flask.Flask(__name__, static_folder='../assets', static_url_path='/assets')
CORS(app)

SECRET_API_KEY = "my-secret-dev-key"

# Initialize synonym discovery system
synonym_discovery = SynonymDiscovery()

# Initialize project manager
project_manager = ProjectManager() 

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

@app.route("/suggestions-review.html")
def suggestions_review():
    """Serve the suggestions review HTML file."""
    return flask.send_from_directory('..', 'suggestions-review.html')

@app.route("/config-manager.html")
def config_manager():
    """Serve the configuration manager HTML file."""
    return flask.send_from_directory('..', 'config-manager.html')

@app.route("/process", methods=["POST"])
@require_api_key
def start_processing():
    try:
        # Check if we're using project files
        use_project_files = flask.request.form.get('useProjectFiles') == 'true'
        project_id = flask.request.form.get('projectId')
        
        if use_project_files and project_id:
            # Use files from project
            try:
                project_data = project_manager.load_project_for_analysis(int(project_id))
                files = project_data['files']
                
                temp_dir = tempfile.mkdtemp()
                our_file_path = files.get('our_file')
                competitor_file_paths = files.get('competitor_files', [])
                onsite_file_path = files.get('onsite_file')
                
                # Copy files to temp directory if they exist
                if our_file_path and os.path.exists(our_file_path):
                    temp_our_file = os.path.join(temp_dir, f"{uuid.uuid4()}.csv")
                    import shutil
                    shutil.copy2(our_file_path, temp_our_file)
                    our_file_path = temp_our_file
                
                temp_competitor_paths = []
                for comp_file in competitor_file_paths:
                    if os.path.exists(comp_file):
                        temp_comp_file = os.path.join(temp_dir, f"{uuid.uuid4()}.csv")
                        shutil.copy2(comp_file, temp_comp_file)
                        temp_competitor_paths.append(temp_comp_file)
                
                if onsite_file_path and os.path.exists(onsite_file_path):
                    temp_onsite_file = os.path.join(temp_dir, f"{uuid.uuid4()}.csv")
                    shutil.copy2(onsite_file_path, temp_onsite_file)
                    onsite_file_path = temp_onsite_file
                
                options = flask.request.form['options']
                
                task = run_analysis_task.delay(
                    our_file_path, temp_competitor_paths, onsite_file_path, options, temp_dir
                )
                return flask.jsonify({"task_id": task.id}), 202
                
            except Exception as e:
                return flask.jsonify({"error": f"Failed to load project files: {e}"}), 400
        else:
            # Use uploaded files (original logic)
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

@app.route("/api/suggestions", methods=["GET"])
@require_api_key
def get_suggestions():
    """Get all pending synonym suggestions."""
    try:
        suggestions = synonym_discovery.get_pending_suggestions()
        return flask.jsonify(suggestions)
    except Exception as e:
        return flask.jsonify({"error": f"Failed to get suggestions: {e}"}), 500

@app.route("/api/suggestions/update", methods=["POST"])
@require_api_key
def update_suggestions():
    """Update suggestion statuses (approve or reject)."""
    try:
        data = flask.request.get_json()
        if not data or 'updates' not in data:
            return flask.jsonify({"error": "Missing updates data"}), 400
        
        updates = data['updates']
        if not isinstance(updates, list):
            return flask.jsonify({"error": "Updates must be a list"}), 400
        
        # Validate each update
        for update in updates:
            if not isinstance(update, dict) or 'id' not in update or 'action' not in update:
                return flask.jsonify({"error": "Each update must have 'id' and 'action' fields"}), 400
            if update['action'] not in ['approve', 'reject']:
                return flask.jsonify({"error": "Action must be 'approve' or 'reject'"}), 400
        
        result = synonym_discovery.bulk_update_suggestions(updates)
        return flask.jsonify(result)
        
    except Exception as e:
        return flask.jsonify({"error": f"Failed to update suggestions: {e}"}), 500

@app.route("/api/suggestions/discover", methods=["POST"])
@require_api_key
def discover_synonyms():
    """Discover new synonyms from uploaded URLs."""
    try:
        data = flask.request.get_json()
        if not data or 'urls' not in data:
            return flask.jsonify({"error": "Missing URLs data"}), 400
        
        urls = data['urls']
        if not isinstance(urls, list):
            return flask.jsonify({"error": "URLs must be a list"}), 400
        
        # Discover synonyms
        candidates = synonym_discovery.discover_synonyms_from_urls(urls)
        
        # Store candidates in database
        stored_ids = synonym_discovery.store_candidates(candidates)
        
        return flask.jsonify({
            "discovered_count": len(candidates),
            "stored_count": len(stored_ids),
            "candidates": candidates
        })
        
    except Exception as e:
        return flask.jsonify({"error": f"Failed to discover synonyms: {e}"}), 500

@app.route("/api/config", methods=["GET"])
@require_api_key
def get_config():
    """Get current configuration."""
    try:
        return flask.jsonify(synonym_discovery.url_parser.config)
    except Exception as e:
        return flask.jsonify({"error": f"Failed to get config: {e}"}), 500

@app.route("/api/config", methods=["POST"])
@require_api_key
def update_config():
    """Update configuration with new synonym rules."""
    try:
        data = flask.request.get_json()
        if not data:
            return flask.jsonify({"error": "Missing configuration data"}), 400
        
        # Update the configuration
        synonym_discovery.url_parser.update_config(data)
        
        return flask.jsonify({"message": "Configuration updated successfully"})
        
    except Exception as e:
        return flask.jsonify({"error": f"Failed to update config: {e}"}), 500

@app.route("/api/config/synonyms", methods=["POST"])
@require_api_key
def add_synonym():
    """Add a single synonym rule."""
    try:
        data = flask.request.get_json()
        if not data or 'type' not in data or 'raw_term' not in data or 'canonical_term' not in data:
            return flask.jsonify({"error": "Missing required fields: type, raw_term, canonical_term"}), 400
        
        if data['type'] == 'category':
            synonym_discovery.url_parser.add_category_synonym(data['raw_term'], data['canonical_term'])
        elif data['type'] == 'facet':
            synonym_discovery.url_parser.add_facet_synonym(data['raw_term'], data['canonical_term'])
        else:
            return flask.jsonify({"error": "Type must be 'category' or 'facet'"}), 400
        
        return flask.jsonify({"message": f"Added {data['type']} synonym: {data['raw_term']} -> {data['canonical_term']}"})
        
    except Exception as e:
        return flask.jsonify({"error": f"Failed to add synonym: {e}"}), 500

# Project Management API Endpoints
@app.route("/api/projects", methods=["GET"])
@require_api_key
def get_projects():
    """Get all taxonomy architecture projects."""
    try:
        analysis_type = flask.request.args.get('analysis_type', 'taxonomy_architecture')
        projects = project_manager.get_projects(analysis_type)
        return flask.jsonify(projects)
    except Exception as e:
        return flask.jsonify({"error": f"Failed to get projects: {e}"}), 500

@app.route("/api/projects", methods=["POST"])
@require_api_key
def create_project():
    """Create a new project."""
    try:
        data = flask.request.get_json()
        if not data or 'name' not in data:
            return flask.jsonify({"error": "Project name is required"}), 400
        
        name = data['name']
        description = data.get('description', '')
        analysis_type = data.get('analysis_type', 'taxonomy_architecture')
        
        project = project_manager.create_project(name, description, analysis_type)
        return flask.jsonify(project), 201
    except Exception as e:
        return flask.jsonify({"error": f"Failed to create project: {e}"}), 500

@app.route("/api/projects/<int:project_id>", methods=["GET"])
@require_api_key
def get_project(project_id):
    """Get a specific project."""
    try:
        project = project_manager.get_project(project_id)
        if not project:
            return flask.jsonify({"error": "Project not found"}), 404
        
        return flask.jsonify(project)
    except Exception as e:
        return flask.jsonify({"error": f"Failed to get project: {e}"}), 500

@app.route("/api/projects/<int:project_id>", methods=["PUT"])
@require_api_key
def update_project(project_id):
    """Update project details."""
    try:
        data = flask.request.get_json()
        if not data:
            return flask.jsonify({"error": "No update data provided"}), 400
        
        success = project_manager.update_project(
            project_id,
            name=data.get('name'),
            description=data.get('description')
        )
        
        if success:
            return flask.jsonify({"message": "Project updated successfully"})
        else:
            return flask.jsonify({"error": "Failed to update project"}), 400
    except Exception as e:
        return flask.jsonify({"error": f"Failed to update project: {e}"}), 500

@app.route("/api/projects/<int:project_id>", methods=["DELETE"])
@require_api_key
def delete_project(project_id):
    """Delete a project."""
    try:
        success = project_manager.delete_project(project_id)
        if success:
            return flask.jsonify({"message": "Project deleted successfully"})
        else:
            return flask.jsonify({"error": "Failed to delete project"}), 400
    except Exception as e:
        return flask.jsonify({"error": f"Failed to delete project: {e}"}), 500

@app.route("/api/projects/<int:project_id>/save", methods=["POST"])
@require_api_key
def save_project_state(project_id):
    """Save the current state of a project."""
    try:
        data = flask.request.get_json()
        if not data:
            return flask.jsonify({"error": "No state data provided"}), 400
        
        success = project_manager.save_project_state(project_id, data)
        if success:
            return flask.jsonify({"message": "Project state saved successfully"})
        else:
            return flask.jsonify({"error": "Failed to save project state"}), 400
    except Exception as e:
        return flask.jsonify({"error": f"Failed to save project state: {e}"}), 500

@app.route("/api/projects/<int:project_id>/load", methods=["GET"])
@require_api_key
def load_project(project_id):
    """Load a project with all its files and state."""
    try:
        project_data = project_manager.load_project_for_analysis(project_id)
        return flask.jsonify(project_data)
    except ValueError as e:
        return flask.jsonify({"error": str(e)}), 404
    except Exception as e:
        return flask.jsonify({"error": f"Failed to load project: {e}"}), 500

@app.route("/api/projects/<int:project_id>/files", methods=["POST"])
@require_api_key
def save_project_files(project_id):
    """Save uploaded files for a project."""
    try:
        files = {
            'our_file': flask.request.files.get('ourFile'),
            'competitor_files': flask.request.files.getlist('competitorFiles'),
            'onsite_file': flask.request.files.get('onsiteFile')
        }
        
        # Remove None values
        files = {k: v for k, v in files.items() if v}
        
        if not files:
            return flask.jsonify({"error": "No files provided"}), 400
        
        saved_files = project_manager.save_project_files(project_id, files)
        return flask.jsonify({
            "message": "Files saved successfully",
            "saved_files": saved_files
        })
    except Exception as e:
        return flask.jsonify({"error": f"Failed to save files: {e}"}), 500

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Run Flask app.')
    parser.add_argument('--port', type=int, default=5001, help='Port to run on.')
    args = parser.parse_args()
    app.run(debug=True, port=args.port)