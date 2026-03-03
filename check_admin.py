"""Quick script to check admin account status"""
from app import app, db, User

with app.app_context():
    admin = User.query.filter_by(username='admin').first()
    
    if admin:
        print(f"✅ Admin account exists")
        print(f"   Username: {admin.username}")
        print(f"   Email: {admin.email}")
        print(f"   Is Admin: {admin.is_admin}")
        print(f"   Is Approved: {admin.is_approved}")
        print(f"   Email Verified: {admin.is_email_verified}")
        print(f"   Minutes Balance: {admin.minutes_balance}")
    else:
        print("❌ Admin account NOT found!")
    
    # Also check example@gmail.com user
    print("\n" + "="*50)
    user = User.query.filter_by(email='example@gmail.com').first()
    if user:
        print(f"✅ User example@gmail.com exists")
        print(f"   Username: {user.username}")
        print(f"   Email: {user.email}")
        print(f"   Is Admin: {user.is_admin}")
        print(f"   Is Approved: {user.is_approved}")
        print(f"   Email Verified: {user.is_email_verified}")
        print(f"   Minutes Balance: {user.minutes_balance}")
    else:
        print("❌ User example@gmail.com NOT found!")
