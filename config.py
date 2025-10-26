import os
from datetime import timedelta

class Config:
    SECRET_KEY = 'your-secret-key-here-change-in-production'
    SQLALCHEMY_DATABASE_URI = 'sqlite:///shadowtalk.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Session configuration
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)
    SESSION_TYPE = 'filesystem'
    
    # Email configuration
    MAIL_SERVER = 'smtp.gmail.com'
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USERNAME = 'devil160907@gmail.com'
    MAIL_PASSWORD = 'zmvp pvxe ctfm ubwi'
    MAIL_DEFAULT_SENDER = 'devil160907@gmail.com'
    
    # OTP configuration
    OTP_EXPIRY_MINUTES = 10
    
    # File upload
    UPLOAD_FOLDER = 'static/uploads'
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size