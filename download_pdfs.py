# download_all_resumes.py
import requests
import os
from resume_builder import ResumeStorage

BASE_URL = "http://localhost:5001"
HEADERS = {
    "X-Employer-ID": "pixelcraft",
    "X-API-Key": "emp_key_12345"
}

# Get all resumes from database
storage = ResumeStorage()
resumes = storage.get_resumes()

print(f"📥 Found {len(resumes)} resumes to download")
print("=" * 60)

for resume in resumes:
    filename = resume.get('storedFileName')
    name = resume.get('name')
    
    if not filename:
        continue
    
    print(f"\n📄 Downloading: {name}")
    print(f"   File: {filename}")
    print("-" * 40)
    
    response = requests.get(
        f"{BASE_URL}/uploads/{filename}",
        headers=HEADERS
    )
    
    if response.status_code == 200:
        output_name = f"decrypted_{filename}"
        with open(output_name, "wb") as f:
            f.write(response.content)
        
        # Check if it's a valid PDF
        if response.content[:4] == b'%PDF':
            print(f"✅ VALID PDF! Saved as: {output_name}")
        else:
            print(f"⚠️ Downloaded but not PDF format")
    else:
        print(f"❌ Failed: {response.status_code}")

print("\n" + "=" * 60)
print("✅ Done! Check the decrypted_*.pdf files.")