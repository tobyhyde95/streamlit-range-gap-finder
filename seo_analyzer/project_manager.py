import sqlite3
import json
import os
from datetime import datetime
from typing import Dict, List, Optional, Any
import pandas as pd
import tempfile
import shutil

class ProjectManager:
    """Manages saving and loading of project states for Taxonomy & Architecture analysis."""
    
    def __init__(self, db_path: str = None):
        """Initialize the project manager with database path."""
        if db_path is None:
            db_path = os.path.join(os.path.dirname(__file__), 'projects.db')
        
        self.db_path = db_path
        self.projects_dir = os.path.join(os.path.dirname(__file__), 'projects')
        
        # Ensure projects directory exists
        os.makedirs(self.projects_dir, exist_ok=True)
        
        # Initialize database
        self._init_database()
    
    def _init_database(self):
        """Initialize the projects database with required tables."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS projects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status TEXT DEFAULT 'active',
                    analysis_type TEXT DEFAULT 'taxonomy_architecture'
                )
            ''')
            
            conn.execute('''
                CREATE TABLE IF NOT EXISTS project_files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL,
                    file_type TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    original_filename TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (project_id) REFERENCES projects (id) ON DELETE CASCADE
                )
            ''')
            
            conn.execute('''
                CREATE TABLE IF NOT EXISTS project_state (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL,
                    state_data TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (project_id) REFERENCES projects (id) ON DELETE CASCADE
                )
            ''')
            
            conn.commit()
    
    def create_project(self, name: str, description: str = "", analysis_type: str = "taxonomy_architecture") -> Dict[str, Any]:
        """Create a new project."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute('''
                INSERT INTO projects (name, description, analysis_type)
                VALUES (?, ?, ?)
            ''', (name, description, analysis_type))
            
            project_id = cursor.lastrowid
            
            return {
                "id": project_id,
                "name": name,
                "description": description,
                "analysis_type": analysis_type,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "status": "active"
            }
    
    def save_project_files(self, project_id: int, files: Dict[str, Any]) -> Dict[str, Any]:
        """Save uploaded files for a project."""
        saved_files = {}
        
        with sqlite3.connect(self.db_path) as conn:
            # Create project directory
            project_dir = os.path.join(self.projects_dir, str(project_id))
            os.makedirs(project_dir, exist_ok=True)
            
            # Save our file
            if 'our_file' in files and files['our_file']:
                our_file_path = os.path.join(project_dir, 'our_data.csv')
                files['our_file'].save(our_file_path)
                
                conn.execute('''
                    INSERT INTO project_files (project_id, file_type, file_path, original_filename)
                    VALUES (?, ?, ?, ?)
                ''', (project_id, 'our_file', our_file_path, files['our_file'].filename))
                
                saved_files['our_file'] = our_file_path
            
            # Save competitor files
            if 'competitor_files' in files and files['competitor_files']:
                competitor_paths = []
                for i, file in enumerate(files['competitor_files']):
                    file_path = os.path.join(project_dir, f'competitor_{i+1}.csv')
                    file.save(file_path)
                    
                    conn.execute('''
                        INSERT INTO project_files (project_id, file_type, file_path, original_filename)
                        VALUES (?, ?, ?, ?)
                    ''', (project_id, 'competitor_file', file_path, file.filename))
                    
                    competitor_paths.append(file_path)
                
                saved_files['competitor_files'] = competitor_paths
            
            # Save onsite file
            if 'onsite_file' in files and files['onsite_file']:
                onsite_file_path = os.path.join(project_dir, 'onsite_data.csv')
                files['onsite_file'].save(onsite_file_path)
                
                conn.execute('''
                    INSERT INTO project_files (project_id, file_type, file_path, original_filename)
                    VALUES (?, ?, ?, ?)
                ''', (project_id, 'onsite_file', onsite_file_path, files['onsite_file'].filename))
                
                saved_files['onsite_file'] = onsite_file_path
            
            # Save PIM file
            if 'pim_file' in files and files['pim_file']:
                pim_file_path = os.path.join(project_dir, 'pim_data.csv')
                files['pim_file'].save(pim_file_path)
                
                conn.execute('''
                    INSERT INTO project_files (project_id, file_type, file_path, original_filename)
                    VALUES (?, ?, ?, ?)
                ''', (project_id, 'pim_file', pim_file_path, files['pim_file'].filename))
                
                saved_files['pim_file'] = pim_file_path
            
            conn.commit()
        
        return saved_files

    def delete_pim_data(self, project_id: int) -> bool:
        """Remove saved PIM files and metadata for a project."""
        try:
            pim_paths = []
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute('''
                    SELECT file_path 
                    FROM project_files 
                    WHERE project_id = ? AND file_type = 'pim_file'
                ''', (project_id,))
                
                pim_paths = [row[0] for row in cursor.fetchall()]
                
                conn.execute('''
                    DELETE FROM project_files 
                    WHERE project_id = ? AND file_type = 'pim_file'
                ''', (project_id,))
                
                conn.execute('''
                    UPDATE projects 
                    SET updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (project_id,))
                
                conn.commit()
            
            for path in pim_paths:
                try:
                    if path and os.path.exists(path):
                        os.remove(path)
                except Exception:
                    # Continue even if file removal fails
                    pass
            
            return True
        except Exception as e:
            print(f"Error deleting PIM data for project {project_id}: {e}")
            return False
    
    def save_project_state(self, project_id: int, state_data: Dict[str, Any]) -> bool:
        """Save the current state of a project."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                # Convert state data to JSON
                state_json = json.dumps(state_data, default=str)
                
                # Save state
                conn.execute('''
                    INSERT INTO project_state (project_id, state_data)
                    VALUES (?, ?)
                ''', (project_id, state_json))
                
                # Update project timestamp
                conn.execute('''
                    UPDATE projects 
                    SET updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (project_id,))
                
                conn.commit()
                return True
        except Exception as e:
            print(f"Error saving project state: {e}")
            return False
    
    def get_projects(self, analysis_type: str = "taxonomy_architecture") -> List[Dict[str, Any]]:
        """Get all projects of a specific type."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute('''
                SELECT id, name, description, created_at, updated_at, status, analysis_type
                FROM projects 
                WHERE analysis_type = ? AND status = 'active'
                ORDER BY updated_at DESC
            ''', (analysis_type,))
            
            projects = []
            for row in cursor.fetchall():
                projects.append({
                    "id": row[0],
                    "name": row[1],
                    "description": row[2],
                    "created_at": row[3],
                    "updated_at": row[4],
                    "status": row[5],
                    "analysis_type": row[6]
                })
            
            return projects
    
    def get_project(self, project_id: int) -> Optional[Dict[str, Any]]:
        """Get a specific project by ID."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute('''
                SELECT id, name, description, created_at, updated_at, status, analysis_type
                FROM projects 
                WHERE id = ?
            ''', (project_id,))
            
            row = cursor.fetchone()
            if row:
                return {
                    "id": row[0],
                    "name": row[1],
                    "description": row[2],
                    "created_at": row[3],
                    "updated_at": row[4],
                    "status": row[5],
                    "analysis_type": row[6]
                }
            return None
    
    def get_project_files(self, project_id: int) -> Dict[str, Any]:
        """Get file paths for a project."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute('''
                SELECT file_type, file_path, original_filename
                FROM project_files 
                WHERE project_id = ?
                ORDER BY created_at
            ''', (project_id,))
            
            files = {}
            competitor_count = 0
            for row in cursor.fetchall():
                file_type = row[0]
                file_path = row[1]
                original_filename = row[2]
                
                if file_type == 'our_file':
                    files['our_file'] = file_path
                    files['our_file_original_name'] = original_filename
                elif file_type == 'competitor_file':
                    if 'competitor_files' not in files:
                        files['competitor_files'] = []
                    files['competitor_files'].append(file_path)
                    competitor_count += 1
                    files[f'competitor_file_{competitor_count}_original_name'] = original_filename
                elif file_type == 'onsite_file':
                    files['onsite_file'] = file_path
                    files['onsite_file_original_name'] = original_filename
                elif file_type == 'pim_file':
                    files['pim_file'] = file_path
                    files['pim_file_original_name'] = original_filename
            
            return files
    
    def get_latest_project_state(self, project_id: int) -> Optional[Dict[str, Any]]:
        """Get the latest state data for a project."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute('''
                SELECT state_data
                FROM project_state 
                WHERE project_id = ?
                ORDER BY created_at DESC
                LIMIT 1
            ''', (project_id,))
            
            row = cursor.fetchone()
            if row:
                return json.loads(row[0])
            return None
    
    def update_project(self, project_id: int, name: str = None, description: str = None) -> bool:
        """Update project details."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                updates = []
                params = []
                
                if name is not None:
                    updates.append("name = ?")
                    params.append(name)
                
                if description is not None:
                    updates.append("description = ?")
                    params.append(description)
                
                if updates:
                    updates.append("updated_at = CURRENT_TIMESTAMP")
                    params.append(project_id)
                    
                    query = f"UPDATE projects SET {', '.join(updates)} WHERE id = ?"
                    conn.execute(query, params)
                    conn.commit()
                    return True
                
                return False
        except Exception as e:
            print(f"Error updating project: {e}")
            return False
    
    def delete_project(self, project_id: int) -> bool:
        """Delete a project and all its associated files."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                # Mark project as deleted
                conn.execute('''
                    UPDATE projects 
                    SET status = 'deleted', updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (project_id,))
                
                conn.commit()
            
            # Remove project directory
            project_dir = os.path.join(self.projects_dir, str(project_id))
            if os.path.exists(project_dir):
                shutil.rmtree(project_dir)
            
            return True
        except Exception as e:
            print(f"Error deleting project: {e}")
            return False
    
    def load_project_for_analysis(self, project_id: int) -> Dict[str, Any]:
        """Load a project with all its files and state for analysis."""
        project = self.get_project(project_id)
        if not project:
            raise ValueError(f"Project {project_id} not found")
        
        files = self.get_project_files(project_id)
        state = self.get_latest_project_state(project_id)
        
        # Add file metadata for frontend restoration
        file_metadata = {}
        if files.get('our_file'):
            file_metadata['our_file'] = {
                'path': files['our_file'],
                'original_name': files.get('our_file_original_name', 'our_data.csv')
            }
        if files.get('competitor_files'):
            file_metadata['competitor_files'] = []
            for i, path in enumerate(files['competitor_files']):
                original_name = files.get(f'competitor_file_{i+1}_original_name', f'competitor_{i+1}.csv')
                file_metadata['competitor_files'].append({
                    'path': path,
                    'original_name': original_name
                })
        if files.get('onsite_file'):
            file_metadata['onsite_file'] = {
                'path': files['onsite_file'],
                'original_name': files.get('onsite_file_original_name', 'onsite_data.csv')
            }
        if files.get('pim_file'):
            file_metadata['pim_file'] = {
                'path': files['pim_file'],
                'original_name': files.get('pim_file_original_name', 'pim_data.csv')
            }
        
        return {
            "project": project,
            "files": files,
            "file_metadata": file_metadata,
            "state": state
        }
