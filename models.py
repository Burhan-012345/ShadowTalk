from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
import uuid

# Create SQLAlchemy instance once
db = SQLAlchemy()

def generate_uuid():
    return str(uuid.uuid4())

class User(UserMixin, db.Model):
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=True)
    username = db.Column(db.String(80), unique=True, nullable=True)
    is_verified = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    
    # Profile fields
    display_name = db.Column(db.String(80))
    bio = db.Column(db.Text)
    age = db.Column(db.Integer)
    gender = db.Column(db.String(20))
    interests = db.Column(db.Text)  # JSON string of interests
    profile_picture = db.Column(db.String(200))
    is_profile_complete = db.Column(db.Boolean, default=False)
    
    # Preferences
    theme = db.Column(db.String(20), default='dark')
    notifications_enabled = db.Column(db.Boolean, default=True)

class OTP(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), nullable=False)
    otp = db.Column(db.String(6), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)

class ChatSession(db.Model):
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    user1_id = db.Column(db.String(36), db.ForeignKey('user.id'))
    user2_id = db.Column(db.String(36), db.ForeignKey('user.id'))
    session_type = db.Column(db.String(20), nullable=False)  # 'text' or 'video'
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    ended_at = db.Column(db.DateTime)
    duration = db.Column(db.Integer)  # in seconds
    
    user1 = db.relationship('User', foreign_keys=[user1_id], backref='initiated_chats')
    user2 = db.relationship('User', foreign_keys=[user2_id], backref='received_chats')

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    chat_session_id = db.Column(db.String(36), db.ForeignKey('chat_session.id'), nullable=False)
    sender_id = db.Column(db.String(36), db.ForeignKey('user.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    is_read = db.Column(db.Boolean, default=False)
    
    chat_session = db.relationship('ChatSession', backref='messages')
    sender = db.relationship('User', backref='sent_messages')

class Connection(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user1_id = db.Column(db.String(36), db.ForeignKey('user.id'), nullable=False)
    user2_id = db.Column(db.String(36), db.ForeignKey('user.id'), nullable=False)
    chat_count = db.Column(db.Integer, default=1)
    last_chat = db.Column(db.DateTime, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user1 = db.relationship('User', foreign_keys=[user1_id])
    user2 = db.relationship('User', foreign_keys=[user2_id])

class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(36), db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    notification_type = db.Column(db.String(50))  # 'connection_request', 'message', etc.
    related_user_id = db.Column(db.String(36), db.ForeignKey('user.id'))
    
    user = db.relationship('User', foreign_keys=[user_id], backref='notifications')
    related_user = db.relationship('User', foreign_keys=[related_user_id])

class Report(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    reporter_id = db.Column(db.String(36), db.ForeignKey('user.id'))
    reported_user_id = db.Column(db.String(36), db.ForeignKey('user.id'))
    chat_session_id = db.Column(db.String(36), db.ForeignKey('chat_session.id'))
    reason = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='pending')  # pending, reviewed, resolved
    
    reporter = db.relationship('User', foreign_keys=[reporter_id])
    reported_user = db.relationship('User', foreign_keys=[reported_user_id])
    chat_session = db.relationship('ChatSession')

class Admin(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
class PasswordResetRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), nullable=False)
    ip_address = db.Column(db.String(45), nullable=False)
    user_agent = db.Column(db.Text)
    requested_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_used = db.Column(db.Boolean, default=False)
    
    def __repr__(self):
        return f'<PasswordResetRequest {self.email} {self.requested_at}>'

# In models.py, update these foreign key references:

class AuditLog(db.Model):
    __tablename__ = 'audit_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(db.Integer, db.ForeignKey('admin.id'))  # Changed from 'admins.id'
    action = db.Column(db.String(200), nullable=False)
    target_type = db.Column(db.String(50))  # 'user', 'chat', 'report'
    target_id = db.Column(db.String(50))
    details = db.Column(db.Text)
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class ModerationQueue(db.Model):
    __tablename__ = 'moderation_queue'
    
    id = db.Column(db.Integer, primary_key=True)
    chat_session_id = db.Column(db.Integer, db.ForeignKey('chat_session.id'))
    message_id = db.Column(db.Integer, db.ForeignKey('message.id'))
    reason = db.Column(db.String(200))  # 'toxic', 'spam', 'harassment', etc.
    confidence_score = db.Column(db.Float)  # AI confidence score
    status = db.Column(db.String(20), default='pending')  # pending, reviewed, action_taken
    reviewed_by = db.Column(db.Integer, db.ForeignKey('admin.id'))  # Changed from 'admins.id'
    reviewed_at = db.Column(db.DateTime)
    action_taken = db.Column(db.String(100))  # 'warning', 'ban', 'message_deleted'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class UserWarning(db.Model):
    __tablename__ = 'user_warnings'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    admin_id = db.Column(db.Integer, db.ForeignKey('admin.id'))  # Changed from 'admins.id'
    reason = db.Column(db.Text, nullable=False)
    severity = db.Column(db.String(20), default='low')  # low, medium, high
    is_acknowledged = db.Column(db.Boolean, default=False)
    expires_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class EmailAlert(db.Model):
    __tablename__ = 'email_alerts'
    
    id = db.Column(db.Integer, primary_key=True)
    alert_type = db.Column(db.String(100), nullable=False)
    recipient = db.Column(db.String(200))
    subject = db.Column(db.String(200))
    message = db.Column(db.Text)
    sent_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='sent')  # sent, failed, pending
