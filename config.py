import os
from datetime import timedelta

class Config:
    SECRET_KEY = 'your-secret-key-here-change-in-production'
    SQLALCHEMY_DATABASE_URI = 'sqlite:///shadowtalk.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    PERMANENT_SESSION_LIFETIME = timedelta(days=7)
    SESSION_TYPE = 'filesystem'
    SESSION_COOKIE_SECURE = False  # Set to True in production with HTTPS
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax

    # Email configuration - Updated with better settings
    MAIL_SERVER = 'smtp.gmail.com'
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USE_SSL = False
    MAIL_USERNAME = 'devil160907@gmail.com'
    MAIL_PASSWORD = 'zmvp pvxe ctfm ubwi'  # Consider using app password
    MAIL_DEFAULT_SENDER = 'devil160907@gmail.com'
    MAIL_DEBUG = False

    # Timeout settings
    MAIL_TIMEOUT = 30

    # OTP configuration
    OTP_EXPIRY_MINUTES = 10

    # File upload
    UPLOAD_FOLDER = 'static/uploads'
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
