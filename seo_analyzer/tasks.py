# seo_analyzer/tasks.py
import io
import os
from .celery_app import celery_app
import shutil

@celery_app.task(bind=True)
def run_analysis_task(self, our_file_path, competitor_file_paths, onsite_file_path, options_str, temp_dir):
    """This is the Celery task that performs the analysis, now with progress reporting."""

    from . import services
    
    try:
        # We pass the update_state function to the main logic
        def report_progress(message, current_step, total_steps):
            meta = {
                'status': message,
                'current': current_step,
                'total': total_steps
            }
            self.update_state(state='PROGRESS', meta=meta)

        results = services.run_full_analysis(
            our_file_path=our_file_path,
            competitor_file_paths=competitor_file_paths,
            onsite_file_path=onsite_file_path,
            options_str=options_str,
            progress_reporter=report_progress # Pass the function as an argument
        )
        return {'status': 'SUCCESS', 'result': results}
    except Exception as e:
        import traceback
        traceback.print_exc()
        self.update_state(state='FAILURE', meta={'exc_type': type(e).__name__, 'exc_message': str(e)})
        return {'status': 'FAILURE', 'error': str(e)}
    finally:
        # Clean up the temporary directory
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)