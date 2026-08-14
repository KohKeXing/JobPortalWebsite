# auth.py - Simple JSON version
import uuid
import bcrypt
from datetime import datetime
import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"
USERS_FILE = DATA_DIR / "users.json"

def init_user_storage():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not USERS_FILE.exists():
        with open(USERS_FILE, 'w') as f:
            json.dump({"users": []}, f)

def get_users():
    with open(USERS_FILE, 'r') as f:
        return json.load(f)["users"]

def save_users(users):
    with open(USERS_FILE, 'w') as f:
        json.dump({"users": users}, f)

def find_user_by_email(email):
    for user in get_users():
        if user["email"].lower() == email.lower():
            return user
    return None

def find_user_by_id(user_id):
    for user in get_users():
        if user["id"] == user_id:
            return user
    return None

def create_user(email, password, name, role, company=None):
    if find_user_by_email(email):
        return None, "Email already exists"
    
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    
    new_user = {
        "id": f"user-{uuid.uuid4().hex[:8]}",
        "email": email,
        "password": hashed,
        "name": name,
        "role": role,
        "created_at": datetime.now().isoformat()
    }
    
    if role == "employer":
        new_user["company"] = company or name
        new_user["employer_id"] = company.lower().replace(" ", "_") if company else name.lower().replace(" ", "_")
        new_user["api_key"] = f"emp_key_{uuid.uuid4().hex[:8]}"
    
    users = get_users()
    users.append(new_user)
    save_users(users)
    
    user_data = new_user.copy()
    del user_data["password"]
    return user_data, None

def verify_user(email, password):
    user = find_user_by_email(email)
    if not user:
        return None, "User not found"
    
    if bcrypt.checkpw(password.encode(), user["password"].encode()):
        user_data = user.copy()
        del user_data["password"]
        return user_data, None
    
    return None, "Invalid password"