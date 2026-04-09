# init_db.py
from database import init_db, add_user,create_organization

if __name__ == "__main__":
    # Initialize database
    init_db()

    # Create sample users (you can change usernames and passwords later)


    # First create organization
    org_code = create_organization("Sample_school", "vivek@gmail.com")

    # Since this is first org created → id will be 1
    add_user("admin", "admin123", org_id=1, role="admin", subject=None)

    add_user("teacher1", "teach123", org_id=1, role="teacher", subject="Math")

    add_user("platform_admin", "admin1234", org_id=None, role="super_admin", subject=None)

    print("Database initialized successfully.")

    print("✅ Database initialized and sample users added:")
    print("   - Admin -> username: admin | password: admin123 | role: admin")
    print("   - Teacher -> username: teacher1 | password: teach123 | role: teacher (Math)")
