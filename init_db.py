from app import db

# Drop all existing tables and create new ones
db.drop_all()
db.create_all()

print("Database initialized successfully!")
