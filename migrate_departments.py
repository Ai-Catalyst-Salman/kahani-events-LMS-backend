import os
import sys
from supabase import create_client, Client

# Add backend directory to path so we can import from app
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from app.core.config import settings

def run_migration():
    """
    Migrate courses to include a department.
    NOTE: Since this project uses Supabase PostgreSQL, not MongoDB,
    we use the Supabase python client. 
    You must first run a SQL migration to add the column:
    ALTER TABLE courses ADD COLUMN IF NOT EXISTS department TEXT DEFAULT 'General';
    """
    url = settings.supabase_url
    key = settings.supabase_service_role_key
    
    if not url or not key:
        print("Missing Supabase credentials.")
        return
        
    supabase: Client = create_client(url, key)
    
    # Fetch all courses
    print("Fetching courses from Supabase...")
    response = supabase.table("courses").select("id, department").execute()
    courses = response.data or []
    
    updated_count = 0
    for course in courses:
        # If department is missing or null, update it to "General"
        if not course.get("department"):
            try:
                update_resp = (
                    supabase.table("courses")
                    .update({"department": "General"})
                    .eq("id", course["id"])
                    .execute()
                )
                if update_resp.data:
                    updated_count += 1
            except Exception as e:
                print(f"Failed to update course {course['id']}: {e}")
                
    print(f"Migration complete! Successfully updated {updated_count} courses to department 'General'.")

if __name__ == "__main__":
    run_migration()
