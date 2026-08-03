from functools import wraps
from flask import session, jsonify, redirect, url_for, request

def employer_required(view_function):
    @wraps(view_function)
    def decorated_function(*args, **kwargs):
        # Check session first
        if session.get('employer_id') and session.get('employer_token'):
            return view_function(*args, **kwargs)
        
        # Check headers (for API calls)
        employer_id = request.headers.get("X-Employer-ID")
        api_key = request.headers.get("X-API-Key")
        
        if employer_id and api_key:
            from employer_main import verify_employer
            if verify_employer(employer_id, api_key):
                return view_function(*args, **kwargs)
        
        if request.path.startswith("/api/"):
            return jsonify({"error": "Employer authentication required"}), 401
        return redirect(url_for('employer_login'))
    
    return decorated_function