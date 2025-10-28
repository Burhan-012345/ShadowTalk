from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
import uuid
import json

db = SQLAlchemy()

def generate_uuid():
    return str(uuid.uuid4())

class User(UserMixin, db.Model):
    __tablename__ = 'users' 

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
    interests = db.Column(db.Text)
    profile_picture = db.Column(db.String(200))
    is_profile_complete = db.Column(db.Boolean, default=False)

    # Online status fields
    is_online = db.Column(db.Boolean, default=False)
    last_seen = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='online')
    custom_status = db.Column(db.String(100))
    last_heartbeat = db.Column(db.DateTime, default=datetime.utcnow)
    avatar_url = db.Column(db.String(255))
    
    is_banned = db.Column(db.Boolean, default=False)
    ban_reason = db.Column(db.Text)
    banned_at = db.Column(db.DateTime)
    banned_by = db.Column(db.String(36), db.ForeignKey('users.id'))  # Changed to reference users.id
    ban_expires_at = db.Column(db.DateTime)
    
    
    # Preferences
    theme = db.Column(db.String(20), default='dark')
    notifications_enabled = db.Column(db.Boolean, default=True)

    banned_by_admin_rel = db.relationship('User', foreign_keys=[banned_by], remote_side=[id])

    @property
    def interests_list(self):
        if self.interests:
            try:
                # Handle both string JSON and already parsed lists
                if isinstance(self.interests, str):
                    return json.loads(self.interests)
                elif isinstance(self.interests, list):
                    return self.interests
                else:
                    return []
            except (json.JSONDecodeError, TypeError, ValueError):
                return []
        return []

class OTP(db.Model):
    __tablename__ = 'otps'
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), nullable=False)
    otp = db.Column(db.String(6), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    is_used = db.Column(db.Boolean, default=False)

class ChatSession(db.Model):
    __tablename__ = 'chat_sessions'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    user1_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False)
    user2_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False)
    session_type = db.Column(db.String(20), nullable=False)  # 'text' or 'video'
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    ended_at = db.Column(db.DateTime)
    duration = db.Column(db.Integer)  # in seconds
    end_reason = db.Column(db.String(50))
    last_activity = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships with explicit foreign keys
    user1 = db.relationship('User', foreign_keys=[user1_id], backref='initiated_chats')
    user2 = db.relationship('User', foreign_keys=[user2_id], backref='received_chats')

class Message(db.Model):
    __tablename__ = 'messages'
    
    id = db.Column(db.Integer, primary_key=True)
    chat_session_id = db.Column(db.String(36), db.ForeignKey('chat_sessions.id'), nullable=False)
    sender_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    message_type = db.Column(db.String(20), default='text')  # text, media, system
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    is_read = db.Column(db.Boolean, default=False)
    delivered_at = db.Column(db.DateTime)
    read_at = db.Column(db.DateTime)
    
    # Media fields (optional)
    media_data = db.Column(db.Text)  # Base64 encoded or file path
    media_type = db.Column(db.String(50))  # image, video, audio, file
    media_name = db.Column(db.String(255))
    
    # Relationships
    chat_session = db.relationship('ChatSession', backref='messages')
    sender = db.relationship('User', backref='sent_messages')

class Connection(db.Model):
    __tablename__ = 'connections'
    
    id = db.Column(db.Integer, primary_key=True)
    user1_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False)
    user2_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False)
    chat_count = db.Column(db.Integer, default=1)
    last_chat = db.Column(db.DateTime, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    user1 = db.relationship('User', foreign_keys=[user1_id], backref='connections_as_user1')
    user2 = db.relationship('User', foreign_keys=[user2_id], backref='connections_as_user2')

class Notification(db.Model):
    __tablename__ = 'notifications'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    notification_type = db.Column(db.String(50))  # 'connection_request', 'message', 'system'
    related_user_id = db.Column(db.String(36), db.ForeignKey('users.id'))
    
    # Relationships
    user = db.relationship('User', foreign_keys=[user_id], backref='notifications')
    related_user = db.relationship('User', foreign_keys=[related_user_id], backref='related_notifications')

class Report(db.Model):
    __tablename__ = 'reports'
    
    id = db.Column(db.Integer, primary_key=True)
    reporter_id = db.Column(db.String(36), db.ForeignKey('users.id'))
    reported_user_id = db.Column(db.String(36), db.ForeignKey('users.id'))
    chat_session_id = db.Column(db.String(36), db.ForeignKey('chat_sessions.id'))
    reason = db.Column(db.Text, nullable=False)
    report_type = db.Column(db.String(50), default='inappropriate_behavior')  # inappropriate_behavior, spam, harassment, other
    status = db.Column(db.String(20), default='pending')  # pending, resolved, dismissed
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    additional_info = db.Column(db.Text)
    
    # Relationships
    reporter = db.relationship('User', foreign_keys=[reporter_id], backref='reports_filed')
    reported_user = db.relationship('User', foreign_keys=[reported_user_id], backref='reports_against')
    chat_session = db.relationship('ChatSession', backref='reports')

class Admin(db.Model):
    __tablename__ = 'admins'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_super_admin = db.Column(db.Boolean, default=False)
    last_login = db.Column(db.DateTime)

class PasswordResetRequest(db.Model):
    __tablename__ = 'password_reset_requests'
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), nullable=False)
    ip_address = db.Column(db.String(45), nullable=False)
    user_agent = db.Column(db.Text)
    requested_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_used = db.Column(db.Boolean, default=False)
    
    def __repr__(self):
        return f'<PasswordResetRequest {self.email} {self.requested_at}>'

class AuditLog(db.Model):
    __tablename__ = 'audit_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(db.Integer, db.ForeignKey('admins.id'))
    action = db.Column(db.String(200), nullable=False)
    target_type = db.Column(db.String(50))  # 'user', 'chat', 'report'
    target_id = db.Column(db.String(50))
    details = db.Column(db.Text)
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    admin = db.relationship('Admin', backref='audit_logs')

class ModerationQueue(db.Model):
    __tablename__ = 'moderation_queue'
    
    id = db.Column(db.Integer, primary_key=True)
    chat_session_id = db.Column(db.String(36), db.ForeignKey('chat_sessions.id'))
    message_id = db.Column(db.Integer, db.ForeignKey('messages.id'))
    reason = db.Column(db.String(200))  # 'toxic', 'spam', 'harassment', etc.
    confidence_score = db.Column(db.Float)  # AI confidence score
    status = db.Column(db.String(20), default='pending')  # pending, reviewed, action_taken
    reviewed_by = db.Column(db.Integer, db.ForeignKey('admins.id'))
    reviewed_at = db.Column(db.DateTime)
    action_taken = db.Column(db.String(100))  # 'warning', 'ban', 'message_deleted'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    chat_session = db.relationship('ChatSession')
    message = db.relationship('Message')
    reviewer = db.relationship('Admin', backref='moderation_actions')

class UserWarningLog(db.Model):
    __tablename__ = 'user_warnings'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'))
    admin_id = db.Column(db.Integer, db.ForeignKey('admins.id'))
    reason = db.Column(db.Text, nullable=False)
    severity = db.Column(db.String(20), default='low')  # low, medium, high
    is_acknowledged = db.Column(db.Boolean, default=False)
    expires_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    user = db.relationship('User', backref='warnings')
    admin = db.relationship('Admin', backref='warnings_issued')

class EmailAlert(db.Model):
    __tablename__ = 'email_alerts'
    
    id = db.Column(db.Integer, primary_key=True)
    alert_type = db.Column(db.String(100), nullable=False)
    recipient = db.Column(db.String(200))
    subject = db.Column(db.String(200))
    message = db.Column(db.Text)
    sent_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='sent')  # sent, failed, pending

class BlockedUser(db.Model):
    __tablename__ = 'blocked_users'
    
    id = db.Column(db.Integer, primary_key=True)
    blocker_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False)
    blocked_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False)
    reason = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    blocker = db.relationship('User', foreign_keys=[blocker_id], backref='blocked_users')
    blocked = db.relationship('User', foreign_keys=[blocked_id], backref='blocked_by')

class UserSession(db.Model):
    __tablename__ = 'user_sessions'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False)
    session_token = db.Column(db.String(255), nullable=False)
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    
    # Relationships
    user = db.relationship('User', backref='sessions')

class SystemSettings(db.Model):
    __tablename__ = 'system_settings'
    
    id = db.Column(db.Integer, primary_key=True)
    setting_key = db.Column(db.String(100), unique=True, nullable=False)
    setting_value = db.Column(db.Text, nullable=False)
    description = db.Column(db.Text)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by = db.Column(db.Integer, db.ForeignKey('admins.id'))
    
    # Relationships
    updated_by_admin = db.relationship('Admin', backref='system_settings')

# Initialize database
def init_db():
    db.create_all()
    
    # Create default admin user if not exists
    from werkzeug.security import generate_password_hash
    admin_user = Admin.query.filter_by(username='admin').first()
    if not admin_user:
        admin_user = Admin(
            username='admin',
            password=generate_password_hash('admin123'),
            is_super_admin=True
        )
        db.session.add(admin_user)
        db.session.commit()
