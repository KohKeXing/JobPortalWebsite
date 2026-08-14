from functools import wraps

from flask import jsonify, redirect, request, session, url_for


JOB_SEEKER_ROLE = "job_seeker"


def _login_required_response():
    if request.path.startswith("/api/"):
        return jsonify({"error": "Login required"}), 401
    return redirect(url_for("login_page"))


def login_required(view_function):
    @wraps(view_function)
    def decorated_function(*args, **kwargs):
        if not session.get("user_id"):
            return _login_required_response()
        return view_function(*args, **kwargs)

    return decorated_function


def seeker_required(view_function):
    @wraps(view_function)
    def decorated_function(*args, **kwargs):
        if not session.get("user_id"):
            return _login_required_response()

        if session.get("role") != JOB_SEEKER_ROLE:
            if request.path.startswith("/api/"):
                return jsonify({"error": "Job seeker access required"}), 403
            return redirect(url_for("login_page"))

        return view_function(*args, **kwargs)

    return decorated_function


def employer_required(view_function):
    @wraps(view_function)
    def decorated_function(*args, **kwargs):
        if not session.get("user_id"):
            return _login_required_response()

        if session.get("role") != "employer":
            if request.path.startswith("/api/"):
                return jsonify({"error": "Employer access required"}), 403
            return redirect(url_for("index"))

        return view_function(*args, **kwargs)

    return decorated_function
