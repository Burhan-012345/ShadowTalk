from models import db
from flask import Flask

def init_db(app):
    if not hasattr(db, 'get_app') or db.get_app() is None:
        db.init_app(app)
    
    with app.app_context():
        db.create_all()
        
        from werkzeug.security import generate_password_hash
        from models import Admin
        
        admin = Admin.query.filter_by(username='admin').first()
        if not admin:
            admin = Admin(
                username='admin',
                password=generate_password_hash('admin123')
            )
            db.session.add(admin)
            db.session.commit()