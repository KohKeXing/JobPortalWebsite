from functools import wraps
from flask import session, jsonify, redirect, url_for, request

def employer_required(view_function):
    @wraps(view_function)
    def decorated_function(*args, **kwargs):
        # Employer authentication is established by Supabase email/password
        # login and retained in the server-side Flask session.
        if (
            session.get("auth_user_id")
            and session.get("employer_id")
            and session.get("role") == "employer"
        ):
            return view_function(*args, **kwargs)

        if request.path.startswith("/api/"):
            return jsonify({"error": "Employer authentication required"}), 401
        return redirect(url_for('employer_login'))
    
    return decorated_function