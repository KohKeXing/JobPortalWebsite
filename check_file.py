# check_resumes.py
from resume_builder import ResumeStorage

storage = ResumeStorage()
resumes = storage.get_resumes()

print(f"Found {len(resumes)} resumes\n")

for r in resumes:
    print(f"Name: {r.get('name')}")
    print(f"Stored File: {r.get('storedFileName')}")
    print(f"File Format: {r.get('fileFormat')}")
    print("-" * 40)