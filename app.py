import os
from flask import Flask, flash, render_template, request, jsonify, redirect, url_for, session
from flask_socketio import SocketIO, join_room, leave_room, emit
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_mail import Mail
from werkzeug.security import generate_password_hash, check_password_hash
import json
import random
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename
from flask import current_app
import uuid
import time
from sqlalchemy import desc
from flask import send_file
import csv
import io
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
import tempfile
from weasyprint import HTML
import base64


# Flask-Admin imports (comment out if not installed)
try:
    from flask_admin import Admin
    from flask_admin.contrib.sqla import ModelView
    from flask_admin.base import BaseView, expose
    from flask_admin.form import SecureForm
    from flask_admin import AdminIndexView
    from flask_admin.menu import MenuLink
    FLASK_ADMIN_AVAILABLE = True
except ImportError:
    FLASK_ADMIN_AVAILABLE = False
    print("Flask-Admin not installed. Admin features disabled.")

from config import Config
from models import AuditLog, PasswordResetRequest, UserWarningLog, db, User, OTP, ChatSession, Message, Connection, Notification, Report, Admin
from email_utils import mail, send_otp_email, send_notification_email, send_password_reset_email, send_ban_notification_email
from flask_mail import Message as MailMessage

app = Flask(__name__)
app.config.from_object(Config)

db.init_app(app)
mail.init_app(app)

# Initialize Login Manager
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Initialize SocketIO with threading only (for PythonAnywhere compatibility)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

online_users = set()  
active_chats = {}     
waiting_users = {    
    'text': [],       
    'video': []       
}

def attempt_gender_based_matchmaking(chat_type):
    """Enhanced gender-based matchmaking with global support"""
    if len(waiting_users[chat_type]) < 2:
        return

    # Group users by gender with enhanced categorization
    male_users = []
    female_users = []
    other_users = []
    
    for user_data in waiting_users[chat_type]:
        user = User.query.get(user_data['user_id'])
        if user and user.gender:
            gender_lower = user.gender.lower().strip()
            
            # Enhanced gender categorization
            if gender_lower in ['male', 'm', 'man', 'boy', 'gentleman']:
                male_users.append(user_data)
            elif gender_lower in ['female', 'f', 'woman', 'girl', 'lady', 'female']:
                female_users.append(user_data)
            else:
                other_users.append(user_data)
        else:
            other_users.append(user_data)

    print(f"Matchmaking: {len(male_users)} male, {len(female_users)} female, {len(other_users)} other users waiting")

    # Priority 1: Male-Female matching
    matches_found = 0
    while male_users and female_users:
        male_data = male_users.pop(0)
        female_data = female_users.pop(0)
        
        # Remove from main waiting list
        waiting_users[chat_type] = [u for u in waiting_users[chat_type] 
                                  if u['user_id'] not in [male_data['user_id'], female_data['user_id']]]
        
        create_chat_session(male_data, female_data, chat_type)
        matches_found += 1
        print(f"✓ Gender-based match: Male {male_data['user_id']} + Female {female_data['user_id']}")

    # Priority 2: If no gender matches, use interest-based matching for remaining users
    if len(waiting_users[chat_type]) >= 2 and matches_found == 0:
        print("No gender matches found, using interest-based matching")
        attempt_interest_based_matchmaking(chat_type)

def attempt_interest_based_matchmaking(chat_type):
    """Match users based on common interests when gender matching isn't possible"""
    if len(waiting_users[chat_type]) < 2:
        return

    # Create a copy of waiting users for matching
    available_users = waiting_users[chat_type][:]
    
    # Try to find users with common interests
    matched_pairs = []
    
    for i, user1_data in enumerate(available_users):
        if user1_data.get('matched'):
            continue
            
        user1_interests = set(user1_data.get('interests', []))
        best_match_index = -1
        best_match_score = 0
        
        # Find best match based on interests
        for j, user2_data in enumerate(available_users[i+1:], i+1):
            if user2_data.get('matched'):
                continue
                
            user2_interests = set(user2_data.get('interests', []))
            common_interests = user1_interests.intersection(user2_interests)
            match_score = len(common_interests)
            
            # Bonus for different genders even in interest-based matching
            user1 = User.query.get(user1_data['user_id'])
            user2 = User.query.get(user2_data['user_id'])
            
            if user1 and user2 and user1.gender and user2.gender:
                gender1 = user1.gender.lower()
                gender2 = user2.gender.lower()
                
                # Add bonus for male-female pairs
                if (gender1 in ['male', 'm', 'man'] and gender2 in ['female', 'f', 'woman']) or \
                   (gender1 in ['female', 'f', 'woman'] and gender2 in ['male', 'm', 'man']):
                    match_score += 3
            
            if match_score > best_match_score:
                best_match_score = match_score
                best_match_index = j
        
        if best_match_index != -1:
            user2_data = available_users[best_match_index]
            matched_pairs.append((user1_data, user2_data))
            user1_data['matched'] = True
            user2_data['matched'] = True
    
    # Create sessions for matched pairs
    for user1_data, user2_data in matched_pairs:
        waiting_users[chat_type] = [u for u in waiting_users[chat_type] 
                                  if u['user_id'] not in [user1_data['user_id'], user2_data['user_id']]]
        create_chat_session(user1_data, user2_data, chat_type)
        print(f"✓ Interest-based match: {user1_data['user_id']} + {user2_data['user_id']}")

def create_chat_session(user1_data, user2_data, chat_type):
    """Create a chat session between two users with enhanced matching info"""
    user1_id = user1_data['user_id']
    user2_id = user2_data['user_id']

    # Create chat session
    chat_session = ChatSession(
        user1_id=user1_id,
        user2_id=user2_id,
        session_type=chat_type,
        started_at=datetime.utcnow()
    )
    db.session.add(chat_session)
    db.session.commit()

    # Store in active chats
    active_chats[user1_id] = {
        'session_id': chat_session.id,
        'partner': user2_id,
        'start_time': datetime.utcnow(),
        'chat_type': chat_type
    }
    active_chats[user2_id] = {
        'session_id': chat_session.id,
        'partner': user1_id,
        'start_time': datetime.utcnow(),
        'chat_type': chat_type
    }

    # Get user info for notification
    user1 = User.query.get(user1_id)
    user2 = User.query.get(user2_id)

    # Calculate common interests
    interests1 = set(user1_data.get('interests', []))
    interests2 = set(user2_data.get('interests', []))
    common_interests = list(interests1.intersection(interests2))

    # Get location info if available
    user1_location = user1_data.get('location', 'Unknown')
    user2_location = user2_data.get('location', 'Unknown')

    # Notify both users with enhanced match details
    match_data = {
        'session_id': chat_session.id,
        'partner_id': user2_id,
        'partner_name': user2.display_name if user2 else 'Anonymous',
        'partner_gender': user2.gender if user2 else 'Not specified',
        'partner_interests': user2_data.get('interests', []),
        'partner_location': user2_location,
        'common_interests': common_interests,
        'chat_type': chat_type,
        'match_type': 'gender_based' if user1 and user2 and 
                       ((user1.gender and user1.gender.lower() in ['male', 'm', 'man'] and 
                         user2.gender and user2.gender.lower() in ['female', 'f', 'woman']) or
                        (user1.gender and user1.gender.lower() in ['female', 'f', 'woman'] and 
                         user2.gender and user2.gender.lower() in ['male', 'm', 'man'])) else 'interest_based',
        'timestamp': datetime.utcnow().isoformat()
    }

    emit('chat_match_found', match_data, room=user1_id)

    # Prepare data for user2
    match_data['partner_id'] = user1_id
    match_data['partner_name'] = user1.display_name if user1 else 'Anonymous'
    match_data['partner_gender'] = user1.gender if user1 else 'Not specified'
    match_data['partner_interests'] = user1_data.get('interests', [])
    match_data['partner_location'] = user1_location

    emit('chat_match_found', match_data, room=user2_id)

    # Log the match
    user1_gender = user1.gender if user1 else 'Unknown'
    user2_gender = user2.gender if user2 else 'Unknown'
    print(f"✓ Matched users {user1_id} ({user1_gender}) from {user1_location} and {user2_id} ({user2_gender}) from {user2_location} for {chat_type} chat. Session: {chat_session.id}")

def attempt_video_matchmaking():
    """Attempt to match users in video chat queue with gender preferences"""
    if len(waiting_users['video']) < 2:
        return

    # Group users by gender and media readiness
    male_users = []
    female_users = []
    other_users = []
    
    for user_data in waiting_users['video']:
        user = User.query.get(user_data['user_id'])
        if user and user.gender:
            gender_lower = user.gender.lower()
            if gender_lower in ['male', 'm', 'man']:
                male_users.append(user_data)
            elif gender_lower in ['female', 'f', 'woman', 'female']:
                female_users.append(user_data)
            else:
                other_users.append(user_data)
        else:
            other_users.append(user_data)

    # Prioritize users with media ready
    ready_males = [u for u in male_users if u.get('media_ready', False)]
    ready_females = [u for u in female_users if u.get('media_ready', False)]
    
    # Try to match ready male with ready female first
    while ready_males and ready_females:
        male_data = ready_males.pop(0)
        female_data = ready_females.pop(0)
        
        # Remove from original lists
        male_users = [u for u in male_users if u['user_id'] != male_data['user_id']]
        female_users = [u for u in female_users if u['user_id'] != female_data['user_id']]
        
        # Remove from waiting list
        waiting_users['video'] = [u for u in waiting_users['video'] 
                                if u['user_id'] not in [male_data['user_id'], female_data['user_id']]]
        
        create_video_chat_session(male_data, female_data)
        return

    # If no ready matches, try any male-female combination
    while male_users and female_users:
        male_data = male_users.pop(0)
        female_data = female_users.pop(0)
        
        waiting_users['video'] = [u for u in waiting_users['video'] 
                                if u['user_id'] not in [male_data['user_id'], female_data['user_id']]]
        
        create_video_chat_session(male_data, female_data)
        return

    # Fallback to original matching if no gender-based matches possible
    if len(waiting_users['video']) >= 2:
        ready_users = [u for u in waiting_users['video'] if u.get('media_ready', False)]
        if len(ready_users) < 2:
            ready_users = waiting_users['video'][:2]

        user1_data = ready_users[0]
        user2_data = ready_users[1]

        waiting_users['video'] = [u for u in waiting_users['video'] 
                                if u['user_id'] not in [user1_data['user_id'], user2_data['user_id']]]

        create_video_chat_session(user1_data, user2_data)

def create_video_chat_session(user1_data, user2_data):
    """Create a video chat session between two users"""
    user1_id = user1_data['user_id']
    user2_id = user2_data['user_id']

    # Create video chat session
    chat_session = ChatSession(
        user1_id=user1_id,
        user2_id=user2_id,
        session_type='video',
        started_at=datetime.utcnow()
    )
    db.session.add(chat_session)
    db.session.commit()

    # Store in active chats
    active_chats[user1_id] = {
        'session_id': chat_session.id,
        'partner': user2_id,
        'start_time': datetime.utcnow(),
        'chat_type': 'video',
        'media_ready': user1_data.get('media_ready', False)
    }
    active_chats[user2_id] = {
        'session_id': chat_session.id,
        'partner': user1_id,
        'start_time': datetime.utcnow(),
        'chat_type': 'video',
        'media_ready': user2_data.get('media_ready', False)
    }

    # Get user info for notification
    user1 = User.query.get(user1_id)
    user2 = User.query.get(user2_id)

    # Calculate common interests
    interests1 = set(user1_data.get('interests', []))
    interests2 = set(user2_data.get('interests', []))
    common_interests = list(interests1.intersection(interests2))

    # Notify both users
    match_data = {
        'session_id': chat_session.id,
        'partner_id': user2_id,
        'partner_name': user2.display_name if user2 else 'Anonymous',
        'partner_gender': user2.gender if user2 else 'Not specified',
        'partner_interests': user2_data.get('interests', []),
        'common_interests': common_interests,
        'chat_type': 'video',
        'timestamp': datetime.utcnow().isoformat()
    }

    emit('video_chat_match_found', match_data, room=user1_id)

    match_data['partner_id'] = user1_id
    match_data['partner_name'] = user1.display_name if user1 else 'Anonymous'
    match_data['partner_gender'] = user1.gender if user1 else 'Not specified'
    match_data['partner_interests'] = user1_data.get('interests', [])

    emit('video_chat_match_found', match_data, room=user2_id)

    print(f"Matched users {user1_id} ({user1.gender if user1 else 'Unknown'}) and {user2_id} ({user2.gender if user2 else 'Unknown'}) for video chat. Session: {chat_session.id}")

def cleanup_inactive_sessions():
    """Periodically clean up inactive sessions"""
    global active_chats, waiting_users, online_users
    
    try:
        with app.app_context():
            # Clean up abandoned waiting users (older than 10 minutes)
            cutoff_time = datetime.utcnow() - timedelta(minutes=10)

            for chat_type in ['text', 'video']:
                original_count = len(waiting_users[chat_type])
                waiting_users[chat_type] = [
                    u for u in waiting_users[chat_type]
                    if datetime.fromisoformat(u.get('joined_at', datetime.utcnow().isoformat())) > cutoff_time
                ]
                if len(waiting_users[chat_type]) != original_count:
                    print(f"Cleaned up {original_count - len(waiting_users[chat_type])} inactive waiting users from {chat_type} queue")

            # Clean up stale active chats (no activity for 5 minutes)
            stale_cutoff = datetime.utcnow() - timedelta(minutes=5)
            users_to_remove = []

            for user_id, chat_data in active_chats.items():
                if chat_data.get('start_time', datetime.utcnow()) < stale_cutoff:
                    users_to_remove.append(user_id)

            for user_id in users_to_remove:
                cleanup_user_sessions(user_id)
                print(f"Cleaned up stale chat session for user {user_id}")

            # Special cleanup for video sessions without media
            cleanup_video_sessions()

            # Clean up users who haven't sent heartbeat in 2 minutes
            heartbeat_cutoff = datetime.utcnow() - timedelta(minutes=2)
            stale_users = User.query.filter(
                User.is_online == True,
                User.last_heartbeat < heartbeat_cutoff
            ).all()

            for user in stale_users:
                user.is_online = False
                if user.id in online_users:
                    online_users.remove(user.id)
                print(f"Marked user {user.id} as offline due to inactivity")

            if stale_users:
                db.session.commit()

    except Exception as e:
        print(f"Error in cleanup_inactive_sessions: {str(e)}")

def cleanup_video_sessions():
    """Clean up abandoned video sessions"""
    cutoff_time = datetime.utcnow() - timedelta(minutes=2)
    
    for user_id, chat_data in list(active_chats.items()):
        if chat_data['chat_type'] == 'video' and chat_data.get('start_time', datetime.utcnow()) < cutoff_time:
            print(f"Cleaning up stale video session for user {user_id}")
            cleanup_user_sessions(user_id)

def calculate_estimated_wait(chat_type):
    """Calculate estimated wait time based on queue length"""
    base_wait = 10  # seconds
    wait_per_user = 5  # seconds
    return base_wait + (len(waiting_users[chat_type]) * wait_per_user)

def cleanup_user_sessions(user_id):
    """Clean up user sessions on disconnect"""
    # Remove from waiting lists
    for chat_type in ['text', 'video']:
        waiting_users[chat_type] = [u for u in waiting_users[chat_type] if u.get('user_id') != user_id]

    # Handle active chat cleanup
    if user_id in active_chats:
        chat_data = active_chats[user_id]
        partner_id = chat_data['partner']
        session_id = chat_data['session_id']

        # Notify partner
        if partner_id in active_chats:
            emit('partner_disconnected', {
                'session_id': session_id,
                'timestamp': datetime.utcnow().isoformat()
            }, room=partner_id)
            del active_chats[partner_id]

        # Update chat session
        chat_session = ChatSession.query.get(session_id)
        if chat_session and not chat_session.ended_at:
            chat_session.ended_at = datetime.utcnow()
            chat_session.end_reason = 'user_disconnected'
            if chat_session.started_at:
                duration = (chat_session.ended_at - chat_session.started_at).total_seconds()
                chat_session.duration = int(duration)
            db.session.commit()

        del active_chats[user_id]

def start_background_tasks():
    """Start background maintenance tasks"""
    def periodic_cleanup():
        while True:
            socketio.sleep(60)  # Run every minute
            cleanup_inactive_sessions()

    socketio.start_background_task(periodic_cleanup)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(user_id)

# Create database tables - with proper error handling
with app.app_context():
    try:
        db.create_all()
        print("Database tables created successfully!")

        # Create default admin user if not exists
        admin_user = User.query.filter_by(email='admin@shadowtalk.com').first()
        if not admin_user:
            admin_user = User(
                email='admin@shadowtalk.com',
                password=generate_password_hash('admin123'),
                username='admin',
                display_name='Administrator',
                is_verified=True,
                is_profile_complete=True
            )
            db.session.add(admin_user)
            db.session.commit()
            print("Default admin user created!")

    except Exception as e:
        print(f"Error creating database: {e}")
        # If there's an error, try to identify the problem
        import traceback
        traceback.print_exc()

from flask_admin import Admin as FlaskAdmin

# Custom Admin Index View
class MyAdminIndexView(AdminIndexView):
    def is_accessible(self):
        return current_user.is_authenticated and (
            current_user.email == 'admin@shadowtalk.com' or
            current_user.username == 'admin@shadowtalk.com' or  # Added this line
            hasattr(current_user, 'is_admin') and current_user.is_admin
        )

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for('login', next=request.url))

    @expose('/')
    def index(self):
        if not current_user.is_authenticated:
            return redirect(url_for('login'))

        # Admin dashboard statistics
        stats = {
            'total_users': User.query.count(),
            'online_users': len(online_users),
            'active_chats': len(active_chats) // 2,
            'pending_reports': Report.query.filter_by(status='pending').count(),
            'waiting_text': len(waiting_users['text']),
            'waiting_video': len(waiting_users['video']),
            'total_messages': Message.query.count(),
            'total_sessions': ChatSession.query.count()
        }

        # Recent activity
        recent_users = User.query.order_by(User.created_at.desc()).limit(5).all()
        recent_reports = Report.query.order_by(Report.created_at.desc()).limit(5).all()
        recent_sessions = ChatSession.query.order_by(ChatSession.started_at.desc()).limit(5).all()

        return self.render('admin/index.html',
                         stats=stats,
                         recent_users=recent_users,
                         recent_reports=recent_reports,
                         recent_sessions=recent_sessions)

class SecureModelView(ModelView):
    page_size = 20
    page_size_options = (20, 50, 100)
    can_export = True
    can_view_details = True
    can_set_page_size = True

    def is_accessible(self):
        return current_user.is_authenticated and (
            current_user.email == 'admin@shadowtalk.com' or
            current_user.username == 'admin@shadowtalk.com' or  # Added this line
            hasattr(current_user, 'is_admin') and current_user.is_admin
        )
class UserAdminView(SecureModelView):
    column_list = ['id', 'email', 'display_name', 'username', 'is_verified',
                   'is_profile_complete', 'created_at', 'last_login']
    column_searchable_list = ['email', 'display_name', 'username']
    column_filters = ['is_verified', 'is_profile_complete', 'created_at', 'gender']
    column_editable_list = ['is_verified', 'is_profile_complete']
    
    # Only include fields that actually exist and are safe
    form_columns = ['email', 'display_name', 'username', 'age', 'gender', 'bio',
                   'interests', 'is_verified', 'is_profile_complete']
    
    # Exclude problematic fields from create and edit forms
    form_excluded_columns = ['is_online', 'last_seen', 'status', 'custom_status', 
                           'last_heartbeat', 'avatar_url', 'is_banned', 'ban_reason',
                           'banned_at', 'banned_by', 'ban_expires_at', 'theme',
                           'notifications_enabled', 'password', 'profile_picture']

    def on_model_change(self, form, model, is_created):
        if is_created and 'password' in form:
            model.password = generate_password_hash(form.password.data)

class ChatSessionAdminView(SecureModelView):
    column_list = ['id', 'user1_id', 'user2_id', 'session_type', 'started_at',
                   'ended_at', 'duration', 'end_reason', 'last_activity']
    column_searchable_list = ['session_type', 'end_reason']
    column_filters = ['session_type', 'started_at', 'ended_at', 'end_reason']
    form_columns = ['user1_id', 'user2_id', 'session_type', 'started_at', 'ended_at',
                   'duration', 'end_reason', 'last_activity']

class MessageAdminView(SecureModelView):
    column_list = ['id', 'chat_session_id', 'sender_id', 'content', 'message_type',
                   'timestamp', 'delivered_at', 'read_at']
    column_searchable_list = ['content']
    column_filters = ['message_type', 'timestamp', 'delivered_at', 'read_at']
    form_columns = ['chat_session_id', 'sender_id', 'content', 'message_type',
                   'timestamp', 'delivered_at', 'read_at']

class ReportAdminView(SecureModelView):
    column_list = ['id', 'reporter_id', 'reported_user_id', 'chat_session_id', 'reason',
                   'report_type', 'status', 'created_at', 'additional_info']
    column_searchable_list = ['reason', 'additional_info']
    column_filters = ['report_type', 'status', 'created_at']
    column_editable_list = ['status']
    form_columns = ['reporter_id', 'reported_user_id', 'chat_session_id', 'reason',
                   'report_type', 'status', 'additional_info']
    form_choices = {
        'status': [
            ('pending', 'Pending'),
            ('resolved', 'Resolved'),
            ('dismissed', 'Dismissed')
        ],
        'report_type': [
            ('inappropriate_behavior', 'Inappropriate Behavior'),
            ('spam', 'Spam'),
            ('harassment', 'Harassment'),
            ('other', 'Other')
        ]
    }

class ConnectionAdminView(SecureModelView):
    column_list = ['id', 'user1_id', 'user2_id', 'chat_count', 'last_chat', 'created_at']
    column_filters = ['created_at', 'last_chat']
    form_columns = ['user1_id', 'user2_id', 'chat_count', 'last_chat']

class NotificationAdminView(SecureModelView):
    column_list = ['id', 'user_id', 'title', 'message', 'notification_type',
                   'is_read', 'created_at', 'related_user_id']
    column_searchable_list = ['title', 'message']
    column_filters = ['notification_type', 'is_read', 'created_at']
    column_editable_list = ['is_read']
    form_columns = ['user_id', 'title', 'message', 'notification_type', 'is_read', 'related_user_id']

class OTPAdminView(SecureModelView):
    column_list = ['id', 'email', 'otp', 'created_at', 'expires_at', 'is_used']
    column_filters = ['created_at', 'expires_at', 'is_used']
    form_columns = ['email', 'otp', 'created_at', 'expires_at', 'is_used']

class PasswordResetRequestAdminView(SecureModelView):
    column_list = ['id', 'email', 'ip_address', 'user_agent', 'requested_at', 'is_used']
    column_filters = ['requested_at', 'ip_address', 'is_used']
    form_columns = ['email', 'ip_address', 'user_agent', 'requested_at', 'is_used']

# Custom Admin Views
class AnalyticsView(BaseView):
    @expose('/')
    def index(self):
        # User growth statistics
        total_users = User.query.count()
        today = datetime.utcnow().date()

        # Daily stats
        users_today = User.query.filter(db.func.date(User.created_at) == today).count()
        users_week = User.query.filter(User.created_at >= today - timedelta(days=7)).count()
        users_month = User.query.filter(User.created_at >= today - timedelta(days=30)).count()

        # Chat statistics
        total_sessions = ChatSession.query.count()
        text_sessions = ChatSession.query.filter_by(session_type='text').count()
        video_sessions = ChatSession.query.filter_by(session_type='video').count()

        # Message statistics
        total_messages = Message.query.count()
        messages_today = Message.query.filter(db.func.date(Message.timestamp) == today).count()

        # Report statistics
        total_reports = Report.query.count()
        pending_reports = Report.query.filter_by(status='pending').count()
        resolved_reports = Report.query.filter_by(status='resolved').count()

        return self.render('admin/analytics.html',
                         total_users=total_users,
                         users_today=users_today,
                         users_week=users_week,
                         users_month=users_month,
                         total_sessions=total_sessions,
                         text_sessions=text_sessions,
                         video_sessions=video_sessions,
                         total_messages=total_messages,
                         messages_today=messages_today,
                         total_reports=total_reports,
                         pending_reports=pending_reports,
                         resolved_reports=resolved_reports)

class SystemMonitorView(BaseView):
    @expose('/')
    def index(self):
        # Real-time system statistics
        stats = {
            'online_users': len(online_users),
            'active_chats': len(active_chats) // 2,
            'waiting_text': len(waiting_users['text']),
            'waiting_video': len(waiting_users['video']),
            'total_connections': Connection.query.count(),
            'active_sessions': ChatSession.query.filter(ChatSession.ended_at.is_(None)).count(),
            'unread_notifications': Notification.query.filter_by(is_read=False).count(),
            'server_time': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        }

        # System health
        database_size = "Operational"
        socket_status = "Connected"
        mail_status = "Operational"

        # Recent activities
        recent_users = User.query.order_by(User.created_at.desc()).limit(10).all()
        recent_reports = Report.query.order_by(Report.created_at.desc()).limit(10).all()

        return self.render('admin/system_monitor.html',
                         stats=stats,
                         recent_users=recent_users,
                         recent_reports=recent_reports,
                         database_size=database_size,
                         socket_status=socket_status,
                         mail_status=mail_status)

class UserManagementView(BaseView):
    @expose('/')
    def index(self):
        users = User.query.order_by(User.created_at.desc()).all()
        return self.render('admin/user_management.html', users=users)

    @expose('/toggle-verification/<int:user_id>', methods=['POST'])
    def toggle_verification(self, user_id):
        user = User.query.get_or_404(user_id)
        user.is_verified = not user.is_verified
        db.session.commit()
        flash(f'User verification status updated for {user.email}', 'success')
        return redirect(url_for('user_management.index'))

    @expose('/delete-user/<int:user_id>', methods=['POST'])
    def delete_user(self, user_id):
        user = User.query.get_or_404(user_id)
        email = user.email
        db.session.delete(user)
        db.session.commit()
        flash(f'User {email} has been deleted', 'success')
        return redirect(url_for('user_management.index'))

# Initialize Flask-Admin with correct parameters
admin = FlaskAdmin(
    app,
    name='ShadowTalk Admin',
    index_view=MyAdminIndexView(),
    url='/admin-panel'
)

# Add model views
admin.add_view(UserAdminView(User, db.session, name='Users', category='Database'))
admin.add_view(ChatSessionAdminView(ChatSession, db.session, name='Chat Sessions', category='Database'))
admin.add_view(MessageAdminView(Message, db.session, name='Messages', category='Database'))
admin.add_view(ReportAdminView(Report, db.session, name='Reports', category='Database'))
admin.add_view(ConnectionAdminView(Connection, db.session, name='Connections', category='Database'))
admin.add_view(NotificationAdminView(Notification, db.session, name='Notifications', category='Database'))
admin.add_view(OTPAdminView(OTP, db.session, name='OTP Codes', category='Database'))
admin.add_view(PasswordResetRequestAdminView(PasswordResetRequest, db.session, name='Password Resets', category='Database'))

# Add custom views
admin.add_view(AnalyticsView(name='Analytics', endpoint='analytics', category='Reports'))
admin.add_view(SystemMonitorView(name='System Monitor', endpoint='system-monitor', category='Monitoring'))
admin.add_view(UserManagementView(name='User Management', endpoint='user-management', category='Management'))

# Add menu links
admin.add_link(MenuLink(name='Back to Site', url='/'))
admin.add_link(MenuLink(name='Logout', url='/logout'))

# Add this route before the existing index route
@app.route('/intro')
def intro():
    """Introduction page for first-time visitors"""
    return render_template('intro.html')

# Update the main index route
@app.route('/')
def index():
    # If user is authenticated, redirect to dashboard
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    # Otherwise, show intro page
    return redirect(url_for('intro'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    from datetime import datetime
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        remember = bool(request.form.get('remember'))

        user = User.query.filter_by(email=email).first()

        if user:
            # Enhanced ban checking
            if user.is_banned:
                # Check if ban has expired
                current_time = datetime.utcnow()
                if user.ban_expires_at and user.ban_expires_at < current_time:
                    # Ban has expired, unban the user
                    user.is_banned = False
                    user.ban_reason = None
                    user.banned_at = None
                    user.banned_by = None
                    user.ban_expires_at = None
                    db.session.commit()
                    
                    # Log the auto-unban
                    print(f"Auto-unbanned user {user.email} - ban expired")
                else:
                    # User is still banned
                    ban_info = "Your account has been suspended"
                    if user.ban_reason:
                        ban_info += f" for: {user.ban_reason}"
                    
                    if user.ban_expires_at:
                        remaining_time = user.ban_expires_at - current_time
                        days = remaining_time.days
                        hours = remaining_time.seconds // 3600
                        minutes = (remaining_time.seconds % 3600) // 60
                        
                        if days > 0:
                            ban_info += f". Suspension ends in {days} day(s), {hours} hour(s)"
                        elif hours > 0:
                            ban_info += f". Suspension ends in {hours} hour(s), {minutes} minute(s)"
                        else:
                            ban_info += f". Suspension ends in {minutes} minute(s)"
                    else:
                        ban_info += ". This is a permanent suspension."
                    
                    ban_info += ". If you believe this is a mistake, please contact our support team."
                    
                    return render_template('auth/login.html', 
                                         error=ban_info,
                                         show_contact_link=True)

        if user and check_password_hash(user.password, password):
            # Final check if user got unbanned between checks
            if user.is_banned:
                return render_template('auth/login.html', 
                                     error='Your account has been suspended. Please contact support.',
                                     show_contact_link=True)
            
            if user.is_verified:
                login_user(user, remember=remember)
                user.last_login = datetime.utcnow()
                db.session.commit()

                # Redirect to profile setup if profile not complete
                if not user.is_profile_complete:
                    return redirect(url_for('profile_setup'))

                return redirect(url_for('dashboard'))
            else:
                return render_template('auth/login.html', error='Please verify your email first')
        else:
            return render_template('auth/login.html', error='Invalid email or password')

    return render_template('auth/login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        if password != confirm_password:
            return render_template('auth/register.html', error='Passwords do not match')

        if User.query.filter_by(email=email).first():
            return render_template('auth/register.html', error='Email already registered')

        # Create user
        user = User(
            email=email,
            password=generate_password_hash(password),
            is_verified=False
        )
        db.session.add(user)
        db.session.commit()

        # Send OTP
        if send_otp_email(email):
            session['verify_email'] = email
            return redirect(url_for('verify_otp'))
        else:
            return render_template('auth/register.html', error='Failed to send verification email')

    return render_template('auth/register.html')

@app.route('/verify-otp', methods=['GET', 'POST'])
def verify_otp():
    email = session.get('verify_email')
    if not email:
        return redirect(url_for('register'))

    if request.method == 'POST':
        # Handle both individual OTP inputs and combined OTP
        otp_individual = [request.form.get(f'otp{i}') for i in range(1, 7)]
        otp_combined = request.form.get('otp')

        # Use combined OTP if available, otherwise combine individual inputs
        if otp_combined:
            otp = otp_combined
        else:
            otp = ''.join(otp_individual) if all(otp_individual) else None

        if not otp or len(otp) != 6:
            return render_template('auth/verify_otp.html', error='Please enter a valid 6-digit OTP')

        otp_record = OTP.query.filter_by(email=email, otp=otp).first()

        if otp_record and otp_record.expires_at > datetime.utcnow():
            user = User.query.filter_by(email=email).first()
            user.is_verified = True
            db.session.delete(otp_record)
            db.session.commit()

            login_user(user)
            session.pop('verify_email', None)

            return redirect(url_for('profile_setup'))
        else:
            return render_template('auth/verify_otp.html', error='Invalid or expired OTP')

    return render_template('auth/verify_otp.html')

# Add OTP resend endpoint
@app.route('/resend-otp', methods=['POST'])
def resend_otp():
    email = session.get('verify_email')
    if not email:
        return jsonify({'success': False, 'error': 'Session expired'})

    # Delete existing OTP for this email
    OTP.query.filter_by(email=email).delete()

    # Generate and send new OTP
    if send_otp_email(email):
        return jsonify({'success': True, 'message': 'New OTP sent successfully'})
    else:
        return jsonify({'success': False, 'error': 'Failed to send OTP'})

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email')
        print(f"🔐 Password reset requested for: {email}")

        # Rate limiting
        client_ip = request.remote_addr
        recent_requests = PasswordResetRequest.query.filter(
            PasswordResetRequest.ip_address == client_ip,
            PasswordResetRequest.requested_at >= datetime.utcnow() - timedelta(hours=1)
        ).count()

        if recent_requests >= 5:
            return render_template('auth/forgot_password.html',
                                 error='Too many reset attempts. Please try again later.')

        user = User.query.filter_by(email=email).first()

        if user:
            # Generate reset token
            reset_token = str(uuid.uuid4())

            # Set session data with proper expiration
            session['reset_token'] = reset_token
            session['reset_email'] = email
            session['reset_expires'] = (datetime.utcnow() + timedelta(hours=1)).isoformat()
            
            # Make sure session is saved
            session.modified = True

            # Log the reset request
            reset_request = PasswordResetRequest(
                email=email,
                ip_address=client_ip,
                user_agent=request.headers.get('User-Agent')
            )
            db.session.add(reset_request)

            print(f"✅ Generated reset token: {reset_token}")
            print(f"✅ Session data set for: {email}")

            # Send reset email with better error handling
            try:
                if send_password_reset_email(email, reset_token):
                    db.session.commit()
                    print("✅ Password reset email sent successfully")
                    return render_template('auth/forgot_password.html',
                                         success='Password reset link has been sent to your email')
                else:
                    db.session.rollback()
                    print("❌ Failed to send password reset email")
                    # Provide manual reset option
                    reset_url = url_for('reset_password', token=reset_token, _external=True)
                    return render_template('auth/forgot_password.html',
                                         error=f'Email service temporarily unavailable. Please use this link manually: {reset_url}')
            except Exception as e:
                db.session.rollback()
                print(f"❌ Error sending password reset email: {str(e)}")
                reset_url = url_for('reset_password', token=reset_token, _external=True)
                return render_template('auth/forgot_password.html',
                                     error=f'Email service error. Please use this link manually: {reset_url}')
        else:
            # Still return success to prevent email enumeration
            return render_template('auth/forgot_password.html',
                                 success='If an account with that email exists, a reset link has been sent.')

    return render_template('auth/forgot_password.html')

@app.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    """Complete password reset functionality with proper token handling"""
    from datetime import datetime
    
    # Get token from URL parameters
    token = request.args.get('token')
    
    print(f"🔑 Reset password attempt - Token from URL: {token}")
    print(f"🔑 Session reset_token: {session.get('reset_token')}")
    print(f"🔑 Session reset_email: {session.get('reset_email')}")
    print(f"🔑 Session reset_expires: {session.get('reset_expires')}")

    # For GET requests, validate the token first
    if request.method == 'GET':
        if not token:
            flash('Invalid or missing reset token', 'error')
            return render_template('auth/reset_password.html',
                                 error='Invalid or missing reset token')

        # Check if token matches session
        session_token = session.get('reset_token')
        if not session_token or session_token != token:
            print(f"❌ Token mismatch: Session has {session_token}, URL has {token}")
            flash('Invalid reset token', 'error')
            return render_template('auth/reset_password.html',
                                 error='Invalid reset token. Please request a new password reset link.')

        # Check if token is expired
        reset_expires_str = session.get('reset_expires')
        if not reset_expires_str:
            flash('Reset token has expired', 'error')
            return render_template('auth/reset_password.html',
                                 error='Reset token has expired. Please request a new one.')

        try:
            # Convert string to datetime
            if 'T' in reset_expires_str:
                reset_expires = datetime.fromisoformat(reset_expires_str.replace('Z', '+00:00'))
            else:
                reset_expires = datetime.strptime(reset_expires_str, '%Y-%m-%d %H:%M:%S')

            # Make both datetimes naive for comparison
            reset_expires_naive = reset_expires.replace(tzinfo=None) if reset_expires.tzinfo else reset_expires
            current_time_naive = datetime.utcnow()

            print(f"⏰ Reset expires: {reset_expires_naive}")
            print(f"⏰ Current time: {current_time_naive}")
            print(f"⏰ Is expired: {reset_expires_naive < current_time_naive}")

            if reset_expires_naive < current_time_naive:
                flash('Reset token has expired', 'error')
                return render_template('auth/reset_password.html',
                                     error='Reset token has expired. Please request a new one.')

        except (ValueError, TypeError, AttributeError) as e:
            print(f"❌ Error parsing reset expiration: {e}")
            flash('Invalid reset token format', 'error')
            return render_template('auth/reset_password.html',
                                 error='Invalid reset token. Please request a new password reset link.')

        # Token is valid, show the reset form
        return render_template('auth/reset_password.html', token=token)

    # Handle POST requests
    elif request.method == 'POST':
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        # Get token from form or URL
        token = request.form.get('token') or request.args.get('token')

        print(f"🔄 Password reset form submitted")
        print(f"📧 Email from session: {session.get('reset_email')}")
        print(f"🔑 Token from form: {token}")

        if not token:
            return render_template('auth/reset_password.html',
                                 error='Invalid reset token',
                                 token=token)

        # Validate token again for POST request
        session_token = session.get('reset_token')
        if not session_token or session_token != token:
            return render_template('auth/reset_password.html',
                                 error='Invalid reset token. Please request a new password reset link.',
                                 token=token)

        if not password or not confirm_password:
            return render_template('auth/reset_password.html',
                                 error='Please fill in all fields',
                                 token=token)

        if password != confirm_password:
            return render_template('auth/reset_password.html',
                                 error='Passwords do not match',
                                 token=token)

        # Enhanced password validation
        if len(password) < 8:
            return render_template('auth/reset_password.html',
                                 error='Password must be at least 8 characters long',
                                 token=token)

        # Check for common passwords
        common_passwords = [
            'password', '123456', '12345678', '1234', 'qwerty', 'abc123',
            'password1', '12345', '123456789', 'admin', 'welcome', 'shadowtalk'
        ]

        if password.lower() in common_passwords:
            return render_template('auth/reset_password.html',
                                 error='Password is too common. Please choose a stronger password.',
                                 token=token)

        # Check password strength requirements
        has_upper = any(c.isupper() for c in password)
        has_lower = any(c.islower() for c in password)
        has_digit = any(c.isdigit() for c in password)
        has_special = any(not c.isalnum() for c in password)

        if not all([has_upper, has_lower, has_digit, has_special]):
            return render_template('auth/reset_password.html',
                                 error='Password must include uppercase letters, lowercase letters, numbers, and special characters',
                                 token=token)

        # Find user by email from session
        user_email = session.get('reset_email')
        if not user_email:
            return render_template('auth/reset_password.html',
                                 error='Session expired. Please request a new reset link.',
                                 token=token)

        user = User.query.filter_by(email=user_email).first()
        if not user:
            return render_template('auth/reset_password.html',
                                 error='User not found',
                                 token=token)

        try:
            # Check if new password is same as old password
            if check_password_hash(user.password, password):
                return render_template('auth/reset_password.html',
                                     error='New password cannot be the same as your current password',
                                     token=token)

            # Update password
            user.password = generate_password_hash(password)
            user.last_login = datetime.utcnow()

            # Mark password reset request as used
            reset_request = PasswordResetRequest.query.filter_by(
                email=user_email,
                is_used=False
            ).order_by(PasswordResetRequest.requested_at.desc()).first()

            if reset_request:
                reset_request.is_used = True

            db.session.commit()

            # Clear reset session data
            session.pop('reset_token', None)
            session.pop('reset_email', None)
            session.pop('reset_expires', None)

            # Send confirmation email
            try:
                send_notification_email(
                    user_email,
                    'Password Reset Successful',
                    'Your ShadowTalk password has been successfully reset. If you did not make this change, please contact support immediately.'
                )
            except Exception as email_error:
                print(f"Error sending confirmation email: {email_error}")
                # Continue anyway - password was reset successfully

            flash('Password has been reset successfully! You can now login with your new password.', 'success')
            return render_template('auth/reset_password.html',
                                 success='Password has been reset successfully! You can now login with your new password.')

        except Exception as e:
            db.session.rollback()
            print(f"❌ Error resetting password: {str(e)}")
            return render_template('auth/reset_password.html',
                                 error='Error updating password. Please try again.',
                                 token=token)

@app.route('/profile-setup', methods=['GET', 'POST'])
@login_required
def profile_setup():
    if request.method == 'POST':
        current_user.display_name = request.form.get('display_name')
        current_user.username = request.form.get('username')
        current_user.age = request.form.get('age')
        current_user.gender = request.form.get('gender')
        current_user.bio = request.form.get('bio')

        interests = request.form.getlist('interests')
        current_user.interests = json.dumps(interests)

        # Handle avatar if provided
        avatar_data = request.form.get('avatar')
        if avatar_data:
            pass

        current_user.is_profile_complete = True
        db.session.commit()

        return redirect(url_for('dashboard'))

    return render_template('profile_setup.html')

@app.route('/profile')
@login_required
def profile():
    # Get user's connections
    connections = Connection.query.filter(
        (Connection.user1_id == current_user.id) |
        (Connection.user2_id == current_user.id)
    ).all()

    connection_users = []
    for conn in connections:
        if conn.user1_id == current_user.id:
            other_user = conn.user2
        else:
            other_user = conn.user1
        connection_users.append({
            'user': other_user,
            'chat_count': conn.chat_count,
            'last_chat': conn.last_chat
        })

    return render_template('profile.html', connections=connection_users)

@app.route('/update_profile', methods=['POST'])
@login_required
def update_profile():
    try:
        print("Updating profile for user:", current_user.id)
        
        # Ensure avatars directory exists
        avatars_dir = os.path.join(current_app.root_path, 'static', 'avatars')
        os.makedirs(avatars_dir, exist_ok=True)
        
        # Handle avatar removal first
        remove_avatar = request.form.get('remove_avatar') == 'true'
        if remove_avatar:
            print("Removing avatar for user:", current_user.id)
            # Remove existing avatar file if it exists
            if current_user.avatar_url and current_user.avatar_url.startswith('/static/avatars/'):
                old_filename = current_user.avatar_url.split('/')[-1]
                old_path = os.path.join(avatars_dir, old_filename)
                if os.path.exists(old_path):
                    os.remove(old_path)
                    print("Removed old avatar file:", old_filename)
            current_user.avatar_url = None
        
        # Handle avatar data URL (AI avatars)
        avatar_data = request.form.get('avatar_data')
        if avatar_data and avatar_data.startswith('data:image') and not remove_avatar:
            print("Processing avatar data URL")
            try:
                import base64
                # Extract the base64 data
                header, encoded = avatar_data.split(',', 1)
                file_extension = header.split('/')[1].split(';')[0]
                
                # Generate unique filename
                unique_filename = f"{current_user.id}_{int(time.time())}_ai_avatar.{file_extension}"
                file_path = os.path.join(avatars_dir, unique_filename)
                
                # Decode and save the image
                image_data = base64.b64decode(encoded)
                with open(file_path, 'wb') as f:
                    f.write(image_data)
                
                # Update user's avatar URL
                current_user.avatar_url = f"/static/avatars/{unique_filename}"
                print("Saved AI avatar:", unique_filename)
                
            except Exception as e:
                print(f"Error processing avatar data URL: {e}")
                # Don't fail the entire update if avatar processing fails
                if not current_user.avatar_url:
                    current_user.avatar_url = None
        
        # Handle file upload
        if 'avatar' in request.files and not remove_avatar:
            file = request.files['avatar']
            if file and file.filename != '':
                print("Processing uploaded avatar file")
                # Secure the filename and create unique name
                filename = secure_filename(file.filename)
                unique_filename = f"{current_user.id}_{int(time.time())}_{filename}"
                file_path = os.path.join(avatars_dir, unique_filename)
                
                # Remove old avatar if exists
                if current_user.avatar_url and current_user.avatar_url.startswith('/static/avatars/'):
                    old_filename = current_user.avatar_url.split('/')[-1]
                    old_path = os.path.join(avatars_dir, old_filename)
                    if os.path.exists(old_path):
                        os.remove(old_path)
                        print("Removed old avatar file:", old_filename)
                
                # Save the new file
                file.save(file_path)
                
                # Update user's avatar URL
                current_user.avatar_url = f"/static/avatars/{unique_filename}"
                print("Saved uploaded avatar:", unique_filename)
        
        # Update other profile fields
        current_user.display_name = request.form.get('display_name', current_user.display_name)
        current_user.username = request.form.get('username', current_user.username)
        current_user.bio = request.form.get('bio', current_user.bio)
        
        # Handle age (can be empty)
        age = request.form.get('age')
        current_user.age = int(age) if age and age.isdigit() and 13 <= int(age) <= 100 else None
        
        current_user.gender = request.form.get('gender', current_user.gender)
        
        # Handle interests
        interests = request.form.getlist('interests')
        current_user.interests = ','.join(interests) if interests else None
        
        # Ensure profile is marked as complete
        current_user.is_profile_complete = True
        
        db.session.commit()
        print("Profile updated successfully for user:", current_user.id)
        
        if remove_avatar:
            flash('Avatar removed successfully!', 'success')
        elif avatar_data or 'avatar' in request.files:
            flash('Profile updated with new avatar!', 'success')
        else:
            flash('Profile updated successfully!', 'success')
            
        return redirect(url_for('profile'))
        
    except Exception as e:
        db.session.rollback()
        print(f'Error updating profile: {str(e)}')
        flash(f'Error updating profile: {str(e)}', 'error')
        return redirect(url_for('profile'))
    
@app.route('/api/check-username')
@login_required
def check_username():
    try:
        # Try multiple ways to get the username parameter
        username = request.args.get('username', '').strip()
        
        # If empty, try form data
        if not username:
            username = request.form.get('username', '').strip()
        
        # If still empty, try JSON data
        if not username and request.is_json:
            data = request.get_json()
            username = data.get('username', '').strip()
        
        print(f"🔍 Checking username: '{username}'")
        print(f"🔍 Request args: {dict(request.args)}")
        print(f"🔍 Request form: {dict(request.form)}")
        print(f"🔍 Request JSON: {request.get_json() if request.is_json else 'Not JSON'}")
        
        if not username:
            print("❌ Username is empty after all attempts")
            return jsonify({'available': False, 'error': 'Username is required'}), 400
        
        if len(username) < 3:
            return jsonify({'available': False, 'error': 'Username must be at least 3 characters'}), 400
        
        import re
        if not re.match(r'^[a-zA-Z0-9_]+$', username):
            return jsonify({'available': False, 'error': 'Username can only contain letters, numbers, and underscores'}), 400
        
        # Check if username is the same as current user (allowed)
        if username.lower() == current_user.username.lower():
            return jsonify({'available': True})
        
        # Check if username exists (case-insensitive)
        existing_user = User.query.filter(
            db.func.lower(User.username) == username.lower()
        ).first()
        
        if existing_user:
            return jsonify({'available': False, 'error': 'Username already taken'}), 400
        
        return jsonify({'available': True})
        
    except Exception as e:
        print(f"🔥 Error in check_username: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'available': False, 'error': 'Server error checking username'}), 500

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('index.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

# In the admin dashboard route, update the user_warnings_count calculation:

@app.route('/admin')
@login_required
def admin_dashboard():
    if current_user.email != 'admin@shadowtalk.com':
        return redirect(url_for('index'))

    # Get statistics
    stats = {
        'total_users': User.query.count(),
        'active_chats': len(active_chats) // 2,
        'pending_reports': Report.query.filter_by(status='pending').count(),
        'banned_users': User.query.filter_by(is_banned=True).count(),
        'moderation_queue': 0,
        'text_chats': ChatSession.query.filter_by(session_type='text').count(),
        'video_chats': ChatSession.query.filter_by(session_type='video').count(),
        'daily_active_users': User.query.filter(
            User.last_login >= datetime.utcnow() - timedelta(days=1)
        ).count(),
        'weekly_active_users': User.query.filter(
            User.last_login >= datetime.utcnow() - timedelta(days=7)
        ).count(),
        'avg_chat_duration': db.session.query(
            db.func.avg(ChatSession.duration)
        ).scalar() or 0,
        'ai_flagged_today': 0,
        'manual_actions_today': 0
    }

    # Get recent reports
    reports = Report.query.filter_by(status='pending').order_by(
        Report.created_at.desc()
    ).all()

    # Get all users for user management
    users = User.query.order_by(User.created_at.desc()).limit(50).all()

    # Get chat sessions
    chat_sessions = ChatSession.query.order_by(
        ChatSession.started_at.desc()
    ).limit(50).all()

    # Get user reports count
    user_reports_count = {}
    for report in Report.query.all():
        if report.reported_user_id:
            user_reports_count[report.reported_user_id] = \
                user_reports_count.get(report.reported_user_id, 0) + 1

    # Get user warnings count - UPDATED
    user_warnings_count = {}
    for warning in UserWarningLog.query.all():  # Changed from UserWarning
        if warning.user_id:
            user_warnings_count[warning.user_id] = \
                user_warnings_count.get(warning.user_id, 0) + 1

    # Get moderation queue
    moderation_queue = []

    # Get live sessions (active chats)
    live_sessions = ChatSession.query.filter(
        ChatSession.ended_at.is_(None)
    ).order_by(ChatSession.started_at.desc()).all()

    # Get audit logs
    audit_logs = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(50).all()

    # Recent activity
    recent_activity = [
        {
            'icon': 'user-plus',
            'message': 'New user registered',
            'timestamp': '2 minutes ago'
        },
        {
            'icon': 'flag',
            'message': 'New report submitted',
            'timestamp': '5 minutes ago'
        },
        {
            'icon': 'comments',
            'message': 'Video chat session started',
            'timestamp': '10 minutes ago'
        }
    ]

    return render_template('admin.html',
                         stats=stats,
                         reports=reports,
                         users=users,
                         chat_sessions=chat_sessions,
                         user_reports_count=user_reports_count,
                         user_warnings_count=user_warnings_count,
                         moderation_queue=moderation_queue,
                         live_sessions=live_sessions,
                         audit_logs=audit_logs,
                         recent_activity=recent_activity,
                         current_user_id=current_user.id)

@app.route('/admin/resolve-report/<int:report_id>', methods=['POST'])
@login_required
def resolve_report(report_id):
    # Admin check
    if current_user.email != 'admin@shadowtalk.com':
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403

    report = Report.query.get_or_404(report_id)
    report.status = 'resolved'
    db.session.commit()
    return jsonify({'success': True})

@app.route('/admin/ban-user', methods=['POST'])
@login_required
def ban_user():
    """Ban a user with detailed options"""
    # Admin check
    if current_user.email != 'admin@shadowtalk.com' and not (hasattr(current_user, 'is_admin') and current_user.is_admin):
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403

    data = request.get_json()
    user_id = data.get('user_id')
    ban_reason = data.get('reason', 'Violation of terms of service')
    ban_duration = data.get('duration', 'permanent')  # 'permanent' or number of days
    report_id = data.get('report_id')

    if not user_id:
        return jsonify({'success': False, 'error': 'User ID is required'})

    user = User.query.get(user_id)
    if not user:
        return jsonify({'success': False, 'error': 'User not found'})

    if user.id == current_user.id:
        return jsonify({'success': False, 'error': 'Cannot ban yourself'})

    try:
        # Set ban details
        user.is_banned = True
        user.ban_reason = ban_reason
        user.banned_at = datetime.utcnow()
        user.banned_by = current_user.id
        
        if ban_duration != 'permanent' and isinstance(ban_duration, int):
            user.ban_expires_at = datetime.utcnow() + timedelta(days=ban_duration)
        else:
            user.ban_expires_at = None  # Permanent ban

        # Mark report as resolved if provided
        if report_id:
            report = Report.query.get(report_id)
            if report:
                report.status = 'resolved'

        # End any active chats for the banned user
        active_sessions = ChatSession.query.filter(
            (ChatSession.user1_id == user_id) | (ChatSession.user2_id == user_id),
            ChatSession.ended_at.is_(None)
        ).all()

        for session in active_sessions:
            session.ended_at = datetime.utcnow()
            session.end_reason = 'user_banned'
            if session.started_at:
                duration = (session.ended_at - session.started_at).total_seconds()
                session.duration = int(duration)

        # Remove from waiting lists and active chats
        global waiting_users, active_chats
        
        for chat_type in ['text', 'video']:
            waiting_users[chat_type] = [u for u in waiting_users[chat_type] if u.get('user_id') != user_id]
        
        if user_id in active_chats:
            partner_id = active_chats[user_id]['partner']
            if partner_id in active_chats:
                # Notify partner
                emit('chat_ended', {
                    'session_id': active_chats[user_id]['session_id'],
                    'reason': 'partner_banned',
                    'partner_left': True,
                    'timestamp': datetime.utcnow().isoformat()
                }, room=partner_id)
                del active_chats[partner_id]
            del active_chats[user_id]

        db.session.commit()

        try:
            send_ban_notification_email(
                email=user.email,
                ban_reason=ban_reason,
                ban_duration=ban_duration,
                ban_expires_at=user.ban_expires_at
            )
        except Exception as e:
            print(f"Error sending ban notification: {e}")

        # Create audit log
        try:
            audit_log = AuditLog(
                admin_id=current_user.id,
                action=f'Banned user {user.email}',
                target_type='user',
                target_id=user_id,
                details=f'Reason: {ban_reason}, Duration: {ban_duration}',
                ip_address=request.remote_addr,
                user_agent=request.headers.get('User-Agent')
            )
            db.session.add(audit_log)
            db.session.commit()
        except Exception as e:
            print(f"Error creating audit log: {e}")

        return jsonify({
            'success': True, 
            'message': f'User {user.email} has been banned successfully'
        })

    except Exception as e:
        db.session.rollback()
        print(f"Error banning user: {str(e)}")
        return jsonify({'success': False, 'error': 'Failed to ban user'})

@app.route('/admin/report/<int:report_id>')
@login_required
def get_report_details(report_id):
    # Admin check
    if current_user.email != 'admin@shadowtalk.com':
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403

    report = Report.query.get_or_404(report_id)
    return jsonify({
        'success': True,
        'report': {
            'id': report.id,
            'reporter_name': report.reporter.display_name if report.reporter else 'Anonymous',
            'reported_user_name': report.reported_user.display_name if report.reported_user else 'Anonymous',
            'reason': report.reason,
            'created_at': report.created_at.isoformat(),
            'status': report.status
        }
    })

@app.route('/admin/user/<user_id>')
@login_required
def get_user_details(user_id):
    # Admin check
    if current_user.email != 'admin@shadowtalk.com':
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403

    user = User.query.get_or_404(user_id)

    # Get user statistics
    chat_count = ChatSession.query.filter(
        (ChatSession.user1_id == user_id) | (ChatSession.user2_id == user_id)
    ).count()

    report_count = Report.query.filter_by(reported_user_id=user_id).count()

    return jsonify({
        'success': True,
        'user': {
            'id': user.id,
            'display_name': user.display_name,
            'email': user.email,
            'is_verified': user.is_verified,
            'created_at': user.created_at.isoformat(),
            'last_login': user.last_login.isoformat() if user.last_login else None,
            'chat_count': chat_count,
            'report_count': report_count
        }
    })

# Chat Routes
@app.route('/chat/text')
@login_required
def text_chat():
    return render_template('chat.html', chat_type='text')

@app.route('/chat/video')
@login_required
def video_chat():
    return render_template('video_chat.html', chat_type='video')

# API Routes
@app.route('/api/notifications')
@login_required
def get_notifications():
    notifications = Notification.query.filter_by(
        user_id=current_user.id,
        is_read=False
    ).order_by(Notification.created_at.desc()).all()

    return jsonify([{
        'id': n.id,
        'title': n.title,
        'message': n.message,
        'type': n.notification_type,
        'created_at': n.created_at.isoformat()
    } for n in notifications])

@app.route('/api/notifications/<int:notification_id>/read', methods=['POST'])
@login_required
def mark_notification_read(notification_id):
    notification = Notification.query.get_or_404(notification_id)
    if notification.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403

    notification.is_read = True
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/send-connection-request/<user_id>', methods=['POST'])
@login_required
def send_connection_request(user_id):
    target_user = User.query.get_or_404(user_id)

    # Check if connection already exists
    existing_connection = Connection.query.filter(
        ((Connection.user1_id == current_user.id) & (Connection.user2_id == user_id)) |
        ((Connection.user1_id == user_id) & (Connection.user2_id == current_user.id))
    ).first()

    if existing_connection:
        return jsonify({'error': 'Connection already exists'}), 400

    # Create notification
    notification = Notification(
        user_id=user_id,
        title='Connection Request',
        message=f'{current_user.display_name} wants to connect with you again',
        notification_type='connection_request',
        related_user_id=current_user.id
    )
    db.session.add(notification)
    db.session.commit()

    # Send email notification if enabled
    if target_user.notifications_enabled:
        send_notification_email(
            target_user.email,
            'Connection Request',
            f'{current_user.display_name} wants to connect with you again on ShadowTalk'
        )

    return jsonify({'success': True})

@app.route('/api/accept-connection-request/<int:notification_id>', methods=['POST'])
@login_required
def accept_connection_request(notification_id):
    notification = Notification.query.get_or_404(notification_id)

    if notification.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403

    # Create connection
    connection = Connection(
        user1_id=current_user.id,
        user2_id=notification.related_user_id
    )
    db.session.add(connection)

    # Mark notification as read
    notification.is_read = True
    db.session.commit()

    return jsonify({'success': True})

# Helper functions
def generate_otp():
    return ''.join(random.choices('0123456789', k=6))

def send_reset_email(email, token):
    reset_url = url_for('reset_password', token=token, _external=True)

    html_content = f'''
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{
                background: linear-gradient(135deg, #2c2c2c 0%, #1a1a1a 100%);
                color: #e0e0e0;
                font-family: 'Arial', sans-serif;
                margin: 0;
                padding: 0;
            }}
            .container {{
                max-width: 600px;
                margin: 0 auto;
                background: #2c2c2c;
                border-radius: 15px;
                overflow: hidden;
                box-shadow: 0 10px 30px rgba(0,0,0,0.3);
            }}
            .header {{
                background: linear-gradient(135deg, #8b5cf6 0%, #a855f7 100%);
                padding: 30px;
                text-align: center;
            }}
            .header h1 {{
                color: white;
                margin: 0;
                font-size: 28px;
                font-weight: bold;
            }}
            .content {{
                padding: 40px;
                text-align: center;
            }}
            .reset-button {{
                display: inline-block;
                background: #8b5cf6;
                color: white;
                padding: 15px 40px;
                text-decoration: none;
                border-radius: 25px;
                margin: 25px 0;
                font-weight: bold;
                font-size: 16px;
                border: none;
                cursor: pointer;
            }}
            .reset-link {{
                display: inline-block;
                background: #8b5cf6;
                color: white;
                padding: 15px 40px;
                text-decoration: none;
                border-radius: 25px;
                margin: 25px 0;
                font-weight: bold;
                font-size: 16px;
            }}
            .footer {{
                background: #1a1a1a;
                padding: 20px;
                text-align: center;
                color: #888;
                font-size: 12px;
            }}
            .text-link {{
                color: #a855f7;
                word-break: break-all;
                margin: 20px 0;
                padding: 10px;
                background: #3c3c3c;
                border-radius: 5px;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>ShadowTalk</h1>
                <p>Password Reset Request</p>
            </div>
            <div class="content">
                <h2>Reset Your Password</h2>
                <p>You requested to reset your password. Click the button below to set a new password:</p>

                <a href="{reset_url}" class="reset-link">Reset Password</a>

                <p>Or copy and paste this link in your browser:</p>
                <div class="text-link">{reset_url}</div>

                <p>This link will expire in 1 hour.</p>
                <p>If you didn't request this, please ignore this email.</p>
            </div>
            <div class="footer">
                <p>&copy; 2024 ShadowTalk. All rights reserved.</p>
            </div>
        </div>
    </body>
    </html>
    '''

    msg = MailMessage(  # Changed from Message to MailMessage
        subject='ShadowTalk - Password Reset',
        recipients=[email],
        html=html_content
    )

    try:
        mail.send(msg)
        return True
    except Exception as e:
        print(f"Error sending reset email: {e}")
        return False

@app.route('/api/chat/stats')
@login_required
def chat_stats():
    """Get chat statistics for dashboard"""
    total_chats = ChatSession.query.filter(
        (ChatSession.user1_id == current_user.id) |
        (ChatSession.user2_id == current_user.id)
    ).count()

    total_messages = Message.query.join(ChatSession).filter(
        (ChatSession.user1_id == current_user.id) |
        (ChatSession.user2_id == current_user.id)
    ).count()

    return jsonify({
        'total_chats': total_chats,
        'total_messages': total_messages,
        'online_users': len(online_users)
    })

@app.route('/api/chat/history')
@login_required
def chat_history():
    """Get user's chat history"""
    page = request.args.get('page', 1, type=int)
    per_page = 10

    chat_sessions = ChatSession.query.filter(
        (ChatSession.user1_id == current_user.id) |
        (ChatSession.user2_id == current_user.id)
    ).order_by(desc(ChatSession.started_at)).paginate(
        page=page, per_page=per_page, error_out=False
    )

    sessions_data = []
    for session in chat_sessions.items:
        partner = session.user2 if session.user1_id == current_user.id else session.user1
        last_message = Message.query.filter_by(
            chat_session_id=session.id
        ).order_by(desc(Message.timestamp)).first()

        sessions_data.append({
            'session_id': session.id,
            'partner_display_name': partner.display_name if partner else 'Anonymous',
            'session_type': session.session_type,
            'started_at': session.started_at.isoformat() if session.started_at else None,
            'duration': session.duration,
            'last_message': last_message.content if last_message else None,
            'message_count': Message.query.filter_by(chat_session_id=session.id).count()
        })

    return jsonify({
        'sessions': sessions_data,
        'total_pages': chat_sessions.pages,
        'current_page': page
    })

@app.route('/api/chat/session/<int:session_id>')
@login_required
def chat_session_details(session_id):
    """Get details and messages for a specific chat session"""
    chat_session = ChatSession.query.get_or_404(session_id)

    # Check if user is part of this chat session
    if current_user.id not in [chat_session.user1_id, chat_session.user2_id]:
        return jsonify({'error': 'Unauthorized'}), 403

    partner = chat_session.user2 if chat_session.user1_id == current_user.id else chat_session.user1

    # Get messages for this session
    messages = Message.query.filter_by(
        chat_session_id=session_id
    ).order_by(Message.timestamp.asc()).all()

    messages_data = []
    for message in messages:
        messages_data.append({
            'id': message.id,
            'content': message.content,
            'sender_id': message.sender_id,
            'timestamp': message.timestamp.isoformat(),
            'is_own': message.sender_id == current_user.id
        })

    return jsonify({
        'session': {
            'id': chat_session.id,
            'session_type': chat_session.session_type,
            'started_at': chat_session.started_at.isoformat() if chat_session.started_at else None,
            'ended_at': chat_session.ended_at.isoformat() if chat_session.ended_at else None,
            'duration': chat_session.duration
        },
        'partner': {
            'display_name': partner.display_name if partner else 'Anonymous',
            'interests': partner.interests_list if partner else []
        },
        'messages': messages_data
    })

# Service Pages Routes
@app.route('/privacy-policy')
def privacy_policy():
    return render_template('service/privacy_policy.html')

@app.route('/terms-of-service')
def terms_of_service():
    return render_template('service/terms_of_service.html')

@app.route('/safety-guidelines')
def safety_guidelines():
    return render_template('service/safety_guidelines.html')

@app.route('/contact')
def contact():
    return render_template('service/contact.html')

@app.route('/help-center')
def help_center():
    return render_template('service/help_center.html')

@socketio.on('connect')
def handle_connect():
    """Handle user connection"""
    global online_users, active_chats, waiting_users
    
    try:
        if current_user.is_authenticated:
            user_id = current_user.id
            join_room(user_id)
            online_users.add(user_id)

            # Update user online status in database
            current_user.is_online = True
            current_user.last_seen = datetime.utcnow()
            current_user.last_heartbeat = datetime.utcnow()
            db.session.commit()

            # Broadcast user online status to all users
            emit('user_online_status', {
                'user_id': user_id,
                'display_name': current_user.display_name,
                'status': 'online',
                'timestamp': datetime.utcnow().isoformat()
            }, broadcast=True)

            # Send online count to all users
            emit('online_count_update', {
                'count': len(online_users),
                'timestamp': datetime.utcnow().isoformat()
            }, broadcast=True)

            # Send connection success to the connected user
            emit('connection_established', {
                'user_id': user_id,
                'online_users': len(online_users),
                'waiting_text': len(waiting_users['text']),
                'waiting_video': len(waiting_users['video']),
                'active_chats': len(active_chats),
                'server_time': datetime.utcnow().isoformat()
            }, room=user_id)

            print(f"User {current_user.display_name} ({user_id}) connected. Online users: {len(online_users)}")

        else:
            # Handle unauthenticated connections
            emit('connection_error', {
                'message': 'Authentication required',
                'timestamp': datetime.utcnow().isoformat()
            })
            return False  # Reject the connection

    except Exception as e:
        print(f"Error in handle_connect: {str(e)}")
        emit('connection_error', {
            'message': 'Internal server error',
            'timestamp': datetime.utcnow().isoformat()
        })
        return False

@socketio.on('disconnect')
def handle_disconnect():
    """Handle user disconnection"""
    global online_users, active_chats, waiting_users
    
    try:
        if current_user.is_authenticated:
            user_id = current_user.id
            leave_room(user_id)

            # Remove from online users
            if user_id in online_users:
                online_users.remove(user_id)

            # Update user offline status in database
            current_user.is_online = False
            current_user.last_seen = datetime.utcnow()
            db.session.commit()

            # Clean up any active chat sessions for this user
            cleanup_user_sessions(user_id)

            # Broadcast user offline status to all users
            emit('user_online_status', {
                'user_id': user_id,
                'display_name': current_user.display_name,
                'status': 'offline',
                'timestamp': datetime.utcnow().isoformat()
            }, broadcast=True)

            # Update online count for all users
            emit('online_count_update', {
                'count': len(online_users),
                'timestamp': datetime.utcnow().isoformat()
            }, broadcast=True)

            print(f"User {current_user.display_name} ({user_id}) disconnected. Online users: {len(online_users)}")

    except Exception as e:
        print(f"Error in handle_disconnect: {str(e)}")

@socketio.on('heartbeat')
def handle_heartbeat(data):
    """Handle client heartbeat to track active connection"""
    global online_users
    
    try:
        if current_user.is_authenticated:
            user_id = current_user.id
            
            # Update last heartbeat timestamp
            current_user.last_heartbeat = datetime.utcnow()
            db.session.commit()

            # Send acknowledgment back to client
            emit('heartbeat_ack', {
                'server_time': datetime.utcnow().isoformat(),
                'user_status': 'active'
            }, room=user_id)

    except Exception as e:
        print(f"Error in handle_heartbeat: {str(e)}")

@socketio.on('start_chat_search')
def handle_start_chat_search(data):
    """Start searching for a chat partner with location and gender preferences"""
    if not current_user.is_authenticated:
        emit('error', {'message': 'Authentication required'})
        return

    chat_type = data.get('type', 'text')
    user_interests = data.get('interests', [])
    filters = data.get('filters', {})
    
    # Get user location from IP or client data
    user_location = get_user_location(request)
    user_gender = current_user.gender

    print(f"User {current_user.id} ({user_gender}) from {user_location} starting {chat_type} chat search")

    # Remove user from any existing queues
    for ctype in ['text', 'video']:
        waiting_users[ctype] = [u for u in waiting_users[ctype] if u.get('user_id') != current_user.id]

    # Add user to waiting list with enhanced metadata
    user_data = {
        'user_id': current_user.id,
        'interests': user_interests,
        'filters': filters,
        'location': user_location,
        'gender': user_gender,
        'joined_at': datetime.utcnow().isoformat(),
        'chat_type': chat_type,
        'language': data.get('language', 'en')
    }

    waiting_users[chat_type].append(user_data)

    # Send searching status with enhanced info
    emit('chat_search_started', {
        'chat_type': chat_type,
        'position': len(waiting_users[chat_type]),
        'total_waiting': len(waiting_users[chat_type]),
        'estimated_wait': calculate_estimated_wait(chat_type),
        'searching_globally': True,
        'gender_preference': 'opposite',
        'timestamp': datetime.utcnow().isoformat()
    }, room=current_user.id)

    # Try to match immediately with gender-based approach
    attempt_gender_based_matchmaking(chat_type)

    print(f"User {current_user.id} ({user_gender}) from {user_location} started {chat_type} chat search. Position: {len(waiting_users[chat_type])}")

def get_user_location(request):
    """Get user location from IP address or client data"""
    try:
        # Get IP-based location (simplified - in production use a geoIP service)
        ip_address = request.remote_addr
        
        # Mock location data based on IP (in production, use geoIP database)
        locations = {
            '127.0.0.1': 'Localhost',
            '192.168.': 'Private Network',
            '10.': 'Private Network',
        }
        
        for prefix, location in locations.items():
            if ip_address.startswith(prefix):
                return location
        
        # Return continent-based mock locations for demonstration
        continents = ['North America', 'Europe', 'Asia', 'South America', 'Africa', 'Australia']
        return f"{random.choice(continents)}"
        
    except Exception as e:
        print(f"Error getting user location: {e}")
        return 'Global'

@socketio.on('cancel_chat_search')
def handle_cancel_chat_search(data):
    """Cancel ongoing chat search"""
    if not current_user.is_authenticated:
        return

    chat_type = data.get('type', 'text')

    # Remove from waiting list
    waiting_users[chat_type] = [u for u in waiting_users[chat_type] if u.get('user_id') != current_user.id]

    emit('chat_search_cancelled', {
        'chat_type': chat_type,
        'timestamp': datetime.utcnow().isoformat()
    }, room=current_user.id)

    print(f"User {current_user.id} cancelled {chat_type} chat search")

@socketio.on('get_chat_status')
def handle_get_chat_status(data):
    """Get current chat status and waiting position"""
    if not current_user.is_authenticated:
        return

    chat_type = data.get('type', 'text')
    position = None

    # Find user position in queue
    for i, user_data in enumerate(waiting_users[chat_type]):
        if user_data.get('user_id') == current_user.id:
            position = i + 1
            break

    in_chat = current_user.id in active_chats

    emit('chat_status_update', {
        'in_queue': position is not None,
        'position': position,
        'total_waiting': len(waiting_users[chat_type]),
        'in_chat': in_chat,
        'chat_type': chat_type,
        'estimated_wait': calculate_estimated_wait(chat_type),
        'timestamp': datetime.utcnow().isoformat()
    }, room=current_user.id)

# Messaging System
@socketio.on('send_message')
def handle_send_message(data):
    """Send a message to chat partner"""
    if not current_user.is_authenticated:
        emit('error', {'message': 'Authentication required'})
        return

    session_id = data.get('session_id')
    message_content = data.get('message')
    message_type = data.get('type', 'text')
    temporary_id = data.get('temp_id')

    if not session_id or not message_content:
        emit('message_error', {
            'temp_id': temporary_id,
            'error': 'Missing session ID or message content'
        })
        return

    # Verify user is in this chat session
    chat_session = ChatSession.query.get(session_id)
    if not chat_session or current_user.id not in [chat_session.user1_id, chat_session.user2_id]:
        emit('message_error', {
            'temp_id': temporary_id,
            'error': 'Invalid chat session'
        })
        return

    # Check if chat is still active
    if chat_session.ended_at:
        emit('message_error', {
            'temp_id': temporary_id,
            'error': 'Chat session has ended'
        })
        return

    # Create message record
    message = Message(
        chat_session_id=session_id,
        sender_id=current_user.id,
        content=message_content,
        message_type=message_type,
        timestamp=datetime.utcnow()
    )
    db.session.add(message)
    db.session.commit()

    # Get partner ID
    partner_id = chat_session.user2_id if chat_session.user1_id == current_user.id else chat_session.user1_id

    # Prepare message data for delivery
    message_data = {
        'id': message.id,
        'session_id': session_id,
        'sender_id': current_user.id,
        'sender_name': current_user.display_name,
        'content': message_content,
        'type': message_type,
        'timestamp': message.timestamp.isoformat(),
        'temp_id': temporary_id
    }

    # Send to partner
    emit('new_message', message_data, room=partner_id)

    # Confirm delivery to sender
    emit('message_sent', {
        'temp_id': temporary_id,
        'message_id': message.id,
        'timestamp': message.timestamp.isoformat()
    }, room=current_user.id)

    # Update chat session last activity
    chat_session.last_activity = datetime.utcnow()
    db.session.commit()

    print(f"Message sent in session {session_id} from {current_user.id} to {partner_id}")

@socketio.on('message_delivered')
def handle_message_delivered(data):
    """Confirm message delivery to recipient"""
    message_id = data.get('message_id')
    session_id = data.get('session_id')

    message = Message.query.get(message_id)
    if message and message.sender_id != current_user.id:
        # Mark as delivered
        message.delivered_at = datetime.utcnow()
        db.session.commit()

        # Notify sender
        emit('message_delivery_status', {
            'message_id': message_id,
            'status': 'delivered',
            'timestamp': datetime.utcnow().isoformat()
        }, room=message.sender_id)

@socketio.on('message_read')
def handle_message_read(data):
    """Confirm message read by recipient"""
    message_id = data.get('message_id')
    session_id = data.get('session_id')

    message = Message.query.get(message_id)
    if message and message.sender_id != current_user.id:
        # Mark as read
        message.read_at = datetime.utcnow()
        db.session.commit()

        # Notify sender
        emit('message_delivery_status', {
            'message_id': message_id,
            'status': 'read',
            'timestamp': datetime.utcnow().isoformat()
        }, room=message.sender_id)

# Typing Indicators
@socketio.on('start_typing')
def handle_start_typing(data):
    """Notify partner that user is typing"""
    session_id = data.get('session_id')

    chat_session = ChatSession.query.get(session_id)
    if chat_session and current_user.id in [chat_session.user1_id, chat_session.user2_id]:
        partner_id = chat_session.user2_id if chat_session.user1_id == current_user.id else chat_session.user1_id

        emit('partner_typing', {
            'session_id': session_id,
            'user_id': current_user.id,
            'user_name': current_user.display_name,
            'timestamp': datetime.utcnow().isoformat()
        }, room=partner_id)

@socketio.on('stop_typing')
def handle_stop_typing(data):
    """Notify partner that user stopped typing"""
    session_id = data.get('session_id')

    chat_session = ChatSession.query.get(session_id)
    if chat_session and current_user.id in [chat_session.user1_id, chat_session.user2_id]:
        partner_id = chat_session.user2_id if chat_session.user1_id == current_user.id else chat_session.user1_id

        emit('partner_stopped_typing', {
            'session_id': session_id,
            'user_id': current_user.id,
            'timestamp': datetime.utcnow().isoformat()
        }, room=partner_id)

# Chat Session Control
@socketio.on('end_chat')
def handle_end_chat(data):
    """End current chat session"""
    if not current_user.is_authenticated:
        return

    session_id = data.get('session_id')
    reason = data.get('reason', 'user_left')

    if current_user.id in active_chats:
        chat_data = active_chats[current_user.id]
        partner_id = chat_data['partner']
        session_id = chat_data['session_id']

        # Remove from active chats
        del active_chats[current_user.id]

        # Update chat session
        chat_session = ChatSession.query.get(session_id)
        if chat_session and not chat_session.ended_at:
            chat_session.ended_at = datetime.utcnow()
            chat_session.end_reason = reason
            if chat_session.started_at:
                duration = (chat_session.ended_at - chat_session.started_at).total_seconds()
                chat_session.duration = int(duration)
            db.session.commit()

        # Notify partner
        if partner_id in active_chats:
            emit('chat_ended', {
                'session_id': session_id,
                'reason': reason,
                'partner_left': True,
                'timestamp': datetime.utcnow().isoformat()
            }, room=partner_id)
            del active_chats[partner_id]

        # Notify user
        emit('chat_ended', {
            'session_id': session_id,
            'reason': reason,
            'partner_left': False,
            'timestamp': datetime.utcnow().isoformat()
        }, room=current_user.id)

        print(f"Chat session {session_id} ended by user {current_user.id}. Reason: {reason}")

@socketio.on('next_chat')
def handle_next_chat(data):
    """End current chat and start searching for next partner"""
    # First end current chat
    handle_end_chat(data)

    # Then start new search after a delay
    def start_new_search():
        chat_type = data.get('type', 'text')
        interests = data.get('interests', [])

        handle_start_chat_search({
            'type': chat_type,
            'interests': interests
        })

    # Small delay to ensure clean state
    socketio.sleep(1)
    start_new_search()

# Video Chat Specific SocketIO Handlers
@socketio.on('join_video_chat')
def handle_join_video_chat(data):
    """Handle user joining video chat queue"""
    if not current_user.is_authenticated:
        emit('error', {'message': 'Authentication required'})
        return

    chat_type = 'video'
    user_interests = data.get('interests', [])
    filters = data.get('filters', {})

    # Remove user from any existing queues
    for ctype in ['text', 'video']:
        waiting_users[ctype] = [u for u in waiting_users[ctype] if u.get('user_id') != current_user.id]

    # Add user to video waiting list
    user_data = {
        'user_id': current_user.id,
        'interests': user_interests,
        'filters': filters,
        'joined_at': datetime.utcnow().isoformat(),
        'chat_type': chat_type,
        'media_ready': False
    }

    waiting_users[chat_type].append(user_data)

    # Send searching status
    emit('video_chat_search_started', {
        'position': len(waiting_users[chat_type]),
        'total_waiting': len(waiting_users[chat_type]),
        'estimated_wait': calculate_estimated_wait(chat_type),
        'timestamp': datetime.utcnow().isoformat()
    }, room=current_user.id)

    # Try to match immediately
    attempt_video_matchmaking()

    print(f"User {current_user.id} joined video chat queue. Position: {len(waiting_users[chat_type])}")

@socketio.on('leave_video_chat')
def handle_leave_video_chat(data):
    """Handle user leaving video chat queue"""
    if not current_user.is_authenticated:
        return

    # Remove from waiting list
    waiting_users['video'] = [u for u in waiting_users['video'] if u.get('user_id') != current_user.id]

    emit('video_chat_search_cancelled', {
        'timestamp': datetime.utcnow().isoformat()
    }, room=current_user.id)

    print(f"User {current_user.id} left video chat queue")

@socketio.on('webrtc_signal')
def handle_webrtc_signal(data):
    """Handle WebRTC signaling for video chat"""
    if not current_user.is_authenticated:
        return

    session_id = data.get('session_id')
    signal_data = data.get('signal')
    signal_type = data.get('type')  # offer, answer, ice_candidate

    # Verify user is in this video chat session
    if current_user.id not in active_chats:
        emit('error', {'message': 'Not in active video chat'})
        return

    chat_data = active_chats[current_user.id]
    if chat_data['session_id'] != session_id:
        emit('error', {'message': 'Invalid session'})
        return

    partner_id = chat_data['partner']

    # Forward signal to partner
    emit('webrtc_signal', {
        'session_id': session_id,
        'from_user_id': current_user.id,
        'signal': signal_data,
        'type': signal_type,
        'timestamp': datetime.utcnow().isoformat()
    }, room=partner_id)

    print(f"WebRTC {signal_type} signal forwarded from {current_user.id} to {partner_id}")

@socketio.on('media_ready')
def handle_media_ready(data):
    """Handle user media readiness notification"""
    if not current_user.is_authenticated:
        return

    session_id = data.get('session_id')
    media_type = data.get('media_type')  # video, audio, both

    # Update user's media status in waiting list
    for user_data in waiting_users['video']:
        if user_data['user_id'] == current_user.id:
            user_data['media_ready'] = True
            user_data['media_type'] = media_type
            break

    # If in active chat, notify partner
    if current_user.id in active_chats:
        chat_data = active_chats[current_user.id]
        partner_id = chat_data['partner']

        emit('partner_media_ready', {
            'session_id': session_id,
            'media_type': media_type,
            'timestamp': datetime.utcnow().isoformat()
        }, room=partner_id)

    print(f"User {current_user.id} media ready: {media_type}")

@socketio.on('video_chat_ended')
def handle_video_chat_ended(data):
    """Handle video chat session end"""
    if not current_user.is_authenticated:
        return

    session_id = data.get('session_id')
    reason = data.get('reason', 'user_left')

    if current_user.id in active_chats:
        chat_data = active_chats[current_user.id]
        partner_id = chat_data['partner']

        # Remove from active chats
        del active_chats[current_user.id]

        # Update chat session
        chat_session = ChatSession.query.get(session_id)
        if chat_session and not chat_session.ended_at:
            chat_session.ended_at = datetime.utcnow()
            chat_session.end_reason = reason
            if chat_session.started_at:
                duration = (chat_session.ended_at - chat_session.started_at).total_seconds()
                chat_session.duration = int(duration)
            db.session.commit()

        # Notify partner
        if partner_id in active_chats:
            emit('video_chat_ended', {
                'session_id': session_id,
                'reason': reason,
                'partner_left': True,
                'timestamp': datetime.utcnow().isoformat()
            }, room=partner_id)
            del active_chats[partner_id]

        # Notify user
        emit('video_chat_ended', {
            'session_id': session_id,
            'reason': reason,
            'partner_left': False,
            'timestamp': datetime.utcnow().isoformat()
        }, room=current_user.id)

        print(f"Video chat session {session_id} ended by user {current_user.id}. Reason: {reason}")

# Video Chat Matching Function
def attempt_video_matchmaking():
    """Attempt to match users in video chat queue with media readiness"""
    if len(waiting_users['video']) < 2:
        return

    # Find users who have media ready or at least one media type
    ready_users = [u for u in waiting_users['video'] if u.get('media_ready', False)]
    
    if len(ready_users) < 2:
        # Try to match any users if queue is long enough
        if len(waiting_users['video']) >= 2:
            ready_users = waiting_users['video'][:2]
        else:
            return

    # Simple FIFO matching for now - enhance with interest matching later
    user1_data = ready_users[0]
    user2_data = ready_users[1]

    # Remove from waiting list
    waiting_users['video'] = [u for u in waiting_users['video'] 
                             if u['user_id'] not in [user1_data['user_id'], user2_data['user_id']]]

    user1_id = user1_data['user_id']
    user2_id = user2_data['user_id']

    # Create video chat session
    chat_session = ChatSession(
        user1_id=user1_id,
        user2_id=user2_id,
        session_type='video',
        started_at=datetime.utcnow()
    )
    db.session.add(chat_session)
    db.session.commit()

    # Store in active chats
    active_chats[user1_id] = {
        'session_id': chat_session.id,
        'partner': user2_id,
        'start_time': datetime.utcnow(),
        'chat_type': 'video',
        'media_ready': user1_data.get('media_ready', False)
    }
    active_chats[user2_id] = {
        'session_id': chat_session.id,
        'partner': user1_id,
        'start_time': datetime.utcnow(),
        'chat_type': 'video',
        'media_ready': user2_data.get('media_ready', False)
    }

    # Get user info for notification
    user1 = User.query.get(user1_id)
    user2 = User.query.get(user2_id)

    # Calculate common interests
    interests1 = set(user1_data.get('interests', []))
    interests2 = set(user2_data.get('interests', []))
    common_interests = list(interests1.intersection(interests2))

    # Notify both users
    match_data = {
        'session_id': chat_session.id,
        'partner_id': user2_id,
        'partner_name': user2.display_name if user2 else 'Anonymous',
        'partner_interests': user2_data.get('interests', []),
        'common_interests': common_interests,
        'chat_type': 'video',
        'timestamp': datetime.utcnow().isoformat()
    }

    emit('video_chat_match_found', match_data, room=user1_id)

    match_data['partner_id'] = user1_id
    match_data['partner_name'] = user1.display_name if user1 else 'Anonymous'
    match_data['partner_interests'] = user1_data.get('interests', [])

    emit('video_chat_match_found', match_data, room=user2_id)

    print(f"Matched users {user1_id} and {user2_id} for video chat. Session: {chat_session.id}")

# Enhanced cleanup function for video chats
def cleanup_video_sessions():
    """Clean up abandoned video sessions"""
    cutoff_time = datetime.utcnow() - timedelta(minutes=2)
    
    for user_id, chat_data in list(active_chats.items()):
        if chat_data['chat_type'] == 'video' and chat_data.get('start_time', datetime.utcnow()) < cutoff_time:
            print(f"Cleaning up stale video session for user {user_id}")
            cleanup_user_sessions(user_id)

# User Status and Presence
@socketio.on('update_user_status')
def handle_update_user_status(data):
    """Update user status (online, away, busy, etc.)"""
    if not current_user.is_authenticated:
        return

    status = data.get('status', 'online')
    custom_status = data.get('custom_status')

    # Update user status
    current_user.status = status
    current_user.custom_status = custom_status
    db.session.commit()

    # Broadcast status update
    emit('user_status_updated', {
        'user_id': current_user.id,
        'display_name': current_user.display_name,
        'status': status,
        'custom_status': custom_status,
        'timestamp': datetime.utcnow().isoformat()
    }, broadcast=True)

@socketio.on('heartbeat')
def handle_heartbeat(data):
    """Handle client heartbeat to track active connection"""
    if current_user.is_authenticated:
        current_user.last_heartbeat = datetime.utcnow()
        db.session.commit()

        emit('heartbeat_ack', {
            'server_time': datetime.utcnow().isoformat()
        }, room=current_user.id)

# Media and File Sharing
@socketio.on('send_media')
def handle_send_media(data):
    """Handle media file sharing"""
    if not current_user.is_authenticated:
        return

    session_id = data.get('session_id')
    file_data = data.get('file_data')
    file_name = data.get('file_name')
    file_type = data.get('file_type')
    file_size = data.get('file_size')

    # Validate file size (5MB limit)
    if file_size and file_size > 5 * 1024 * 1024:
        emit('media_error', {'error': 'File too large. Maximum size is 5MB.'})
        return

    chat_session = ChatSession.query.get(session_id)
    if not chat_session or current_user.id not in [chat_session.user1_id, chat_session.user2_id]:
        emit('media_error', {'error': 'Invalid chat session'})
        return

    partner_id = chat_session.user2_id if chat_session.user1_id == current_user.id else chat_session.user1_id

    # Create media message
    message = Message(
        chat_session_id=session_id,
        sender_id=current_user.id,
        content=f"[Media: {file_name}]",
        message_type='media',
        media_data=file_data,
        media_type=file_type,
        media_name=file_name,
        timestamp=datetime.utcnow()
    )
    db.session.add(message)
    db.session.commit()

    # Send to partner
    emit('media_message', {
        'message_id': message.id,
        'session_id': session_id,
        'sender_id': current_user.id,
        'sender_name': current_user.display_name,
        'file_name': file_name,
        'file_type': file_type,
        'file_size': file_size,
        'timestamp': message.timestamp.isoformat(),
        'preview_url': file_data  # In production, this would be a proper CDN URL
    }, room=partner_id)

    # Confirm to sender
    emit('media_sent', {
        'message_id': message.id,
        'file_name': file_name,
        'timestamp': message.timestamp.isoformat()
    }, room=current_user.id)

# Voice Chat Features
@socketio.on('voice_chat_request')
def handle_voice_chat_request(data):
    """Request voice chat with partner"""
    session_id = data.get('session_id')

    chat_session = ChatSession.query.get(session_id)
    if chat_session and current_user.id in [chat_session.user1_id, chat_session.user2_id]:
        partner_id = chat_session.user2_id if chat_session.user1_id == current_user.id else chat_session.user1_id

        emit('voice_chat_invitation', {
            'session_id': session_id,
            'from_user_id': current_user.id,
            'from_user_name': current_user.display_name,
            'timestamp': datetime.utcnow().isoformat()
        }, room=partner_id)

@socketio.on('voice_chat_response')
def handle_voice_chat_response(data):
    """Respond to voice chat request"""
    session_id = data.get('session_id')
    accepted = data.get('accepted', False)

    chat_session = ChatSession.query.get(session_id)
    if chat_session and current_user.id in [chat_session.user1_id, chat_session.user2_id]:
        partner_id = chat_session.user2_id if chat_session.user1_id == current_user.id else chat_session.user1_id

        emit('voice_chat_response', {
            'session_id': session_id,
            'accepted': accepted,
            'responder_id': current_user.id,
            'responder_name': current_user.display_name,
            'timestamp': datetime.utcnow().isoformat()
        }, room=partner_id)

        if accepted:
            # Notify both users to start voice chat
            emit('voice_chat_started', {
                'session_id': session_id,
                'timestamp': datetime.utcnow().isoformat()
            }, room=current_user.id)
            emit('voice_chat_started', {
                'session_id': session_id,
                'timestamp': datetime.utcnow().isoformat()
            }, room=partner_id)

@socketio.on('webrtc_signal')
def handle_webrtc_signal(data):
    """Handle WebRTC signaling for voice/video chat"""
    session_id = data.get('session_id')
    signal_data = data.get('signal')
    signal_type = data.get('type')  # offer, answer, candidate

    chat_session = ChatSession.query.get(session_id)
    if chat_session and current_user.id in [chat_session.user1_id, chat_session.user2_id]:
        partner_id = chat_session.user2_id if chat_session.user1_id == current_user.id else chat_session.user1_id

        emit('webrtc_signal', {
            'session_id': session_id,
            'from_user_id': current_user.id,
            'signal': signal_data,
            'type': signal_type,
            'timestamp': datetime.utcnow().isoformat()
        }, room=partner_id)

# Moderation and Safety
@socketio.on('report_user')
def handle_report_user(data):
    """Report a user for inappropriate behavior"""
    if not current_user.is_authenticated:
        return

    session_id = data.get('session_id')
    reason = data.get('reason')
    report_type = data.get('type', 'inappropriate_behavior')
    additional_info = data.get('additional_info')

    chat_session = ChatSession.query.get(session_id)
    if not chat_session or current_user.id not in [chat_session.user1_id, chat_session.user2_id]:
        return

    reported_user_id = chat_session.user2_id if chat_session.user1_id == current_user.id else chat_session.user1_id

    # Create report
    report = Report(
        reporter_id=current_user.id,
        reported_user_id=reported_user_id,
        chat_session_id=session_id,
        reason=reason,
        report_type=report_type,
        additional_info=additional_info,
        status='pending'
    )
    db.session.add(report)
    db.session.commit()

    # Auto-end chat for reporter
    handle_end_chat({
        'session_id': session_id,
        'reason': 'user_reported'
    })

    emit('report_submitted', {
        'report_id': report.id,
        'timestamp': datetime.utcnow().isoformat()
    }, room=current_user.id)

    print(f"User {reported_user_id} reported by {current_user.id} in session {session_id}")

@socketio.on('block_user')
def handle_block_user(data):
    """Block a user"""
    if not current_user.is_authenticated:
        return

    user_id_to_block = data.get('user_id')
    session_id = data.get('session_id')

    if session_id and current_user.id in active_chats:
        handle_end_chat({
            'session_id': session_id,
            'reason': 'user_blocked'
        })

    emit('user_blocked', {
        'blocked_user_id': user_id_to_block,
        'timestamp': datetime.utcnow().isoformat()
    }, room=current_user.id)

# Admin and Monitoring
@socketio.on('admin_get_stats')
def handle_admin_get_stats(data):
    """Admin: Get real-time system statistics"""
    # Simple admin check
    if not current_user.is_authenticated or current_user.email != 'admin@shadowtalk.com':
        emit('error', {'message': 'Unauthorized'})
        return

    stats = {
        'online_users': len(online_users),
        'active_chats': len(active_chats) // 2,
        'waiting_text': len(waiting_users['text']),
        'waiting_video': len(waiting_users['video']),
        'total_users': User.query.count(),
        'active_sessions': ChatSession.query.filter(ChatSession.ended_at.is_(None)).count(),
        'server_time': datetime.utcnow().isoformat(),
        'system_uptime': get_system_uptime()  # You'd implement this
    }

    emit('admin_stats', stats, room=current_user.id)

def attempt_matchmaking(chat_type):
    """Attempt to match users in the waiting queue"""
    if len(waiting_users[chat_type]) < 2:
        return

    # Simple FIFO matching - you can enhance this with interest-based matching
    user1_data = waiting_users[chat_type].pop(0)
    user2_data = waiting_users[chat_type].pop(0)

    user1_id = user1_data['user_id']
    user2_id = user2_data['user_id']

    # Create chat session
    chat_session = ChatSession(
        user1_id=user1_id,
        user2_id=user2_id,
        session_type=chat_type,
        started_at=datetime.utcnow()
    )
    db.session.add(chat_session)
    db.session.commit()

    # Store in active chats
    active_chats[user1_id] = {
        'session_id': chat_session.id,
        'partner': user2_id,
        'start_time': datetime.utcnow(),
        'chat_type': chat_type
    }
    active_chats[user2_id] = {
        'session_id': chat_session.id,
        'partner': user1_id,
        'start_time': datetime.utcnow(),
        'chat_type': chat_type
    }

    # Get user info for notification
    user1 = User.query.get(user1_id)
    user2 = User.query.get(user2_id)

    # Calculate common interests
    interests1 = set(user1_data.get('interests', []))
    interests2 = set(user2_data.get('interests', []))
    common_interests = list(interests1.intersection(interests2))

    # Notify both users
    match_data = {
        'session_id': chat_session.id,
        'partner_id': user2_id,
        'partner_name': user2.display_name if user2 else 'Anonymous',
        'partner_interests': user2_data.get('interests', []),
        'common_interests': common_interests,
        'chat_type': chat_type,
        'timestamp': datetime.utcnow().isoformat()
    }

    emit('chat_match_found', match_data, room=user1_id)

    match_data['partner_id'] = user1_id
    match_data['partner_name'] = user1.display_name if user1 else 'Anonymous'
    match_data['partner_interests'] = user1_data.get('interests', [])

    emit('chat_match_found', match_data, room=user2_id)

    print(f"Matched users {user1_id} and {user2_id} for {chat_type} chat. Session: {chat_session.id}")

def calculate_estimated_wait(chat_type):
    """Calculate estimated wait time based on queue length"""
    base_wait = 10  # seconds
    wait_per_user = 5  # seconds
    return base_wait + (len(waiting_users[chat_type]) * wait_per_user)

def cleanup_user_sessions(user_id):
    """Clean up user sessions on disconnect"""
    # Remove from waiting lists
    for chat_type in ['text', 'video']:
        waiting_users[chat_type] = [u for u in waiting_users[chat_type] if u.get('user_id') != user_id]

    # Handle active chat cleanup
    if user_id in active_chats:
        chat_data = active_chats[user_id]
        partner_id = chat_data['partner']
        session_id = chat_data['session_id']

        # Notify partner
        if partner_id in active_chats:
            emit('partner_disconnected', {
                'session_id': session_id,
                'timestamp': datetime.utcnow().isoformat()
            }, room=partner_id)
            del active_chats[partner_id]

        # Update chat session
        chat_session = ChatSession.query.get(session_id)
        if chat_session and not chat_session.ended_at:
            chat_session.ended_at = datetime.utcnow()
            chat_session.end_reason = 'user_disconnected'
            if chat_session.started_at:
                duration = (chat_session.ended_at - chat_session.started_at).total_seconds()
                chat_session.duration = int(duration)
            db.session.commit()

        del active_chats[user_id]

def get_system_uptime():
    """Get system uptime (simplified)"""
    return "0 days, 0 hours, 0 minutes"  # Implement actual uptime tracking

def cleanup_inactive_sessions():
    """Periodically clean up inactive sessions"""
    global active_chats, waiting_users, online_users
    
    try:
        with app.app_context():
            # Clean up abandoned waiting users (older than 10 minutes)
            cutoff_time = datetime.utcnow() - timedelta(minutes=10)

            for chat_type in ['text', 'video']:
                original_count = len(waiting_users[chat_type])
                waiting_users[chat_type] = [
                    u for u in waiting_users[chat_type]
                    if datetime.fromisoformat(u.get('joined_at', datetime.utcnow().isoformat())) > cutoff_time
                ]
                if len(waiting_users[chat_type]) != original_count:
                    print(f"Cleaned up {original_count - len(waiting_users[chat_type])} inactive waiting users from {chat_type} queue")

            # Clean up stale active chats (no activity for 5 minutes)
            stale_cutoff = datetime.utcnow() - timedelta(minutes=5)
            users_to_remove = []

            for user_id, chat_data in active_chats.items():
                if chat_data.get('start_time', datetime.utcnow()) < stale_cutoff:
                    users_to_remove.append(user_id)

            for user_id in users_to_remove:
                cleanup_user_sessions(user_id)
                print(f"Cleaned up stale chat session for user {user_id}")

            # Clean up users who haven't sent heartbeat in 2 minutes
            heartbeat_cutoff = datetime.utcnow() - timedelta(minutes=2)
            stale_users = User.query.filter(
                User.is_online == True,
                User.last_heartbeat < heartbeat_cutoff
            ).all()

            for user in stale_users:
                user.is_online = False
                if user.id in online_users:
                    online_users.remove(user.id)
                print(f"Marked user {user.id} as offline due to inactivity")

            if stale_users:
                db.session.commit()

    except Exception as e:
        print(f"Error in cleanup_inactive_sessions: {str(e)}")

def start_background_tasks():
    """Start background maintenance tasks"""
    def periodic_cleanup():
        while True:
            socketio.sleep(60)  # Run every minute
            cleanup_inactive_sessions()

    socketio.start_background_task(periodic_cleanup)

# Initialize background tasks when first client connects
@socketio.on('connect')
def initialize_background_tasks():
    """Initialize background tasks when first client connects"""
    global online_users
    
    if len(online_users) == 1:  # First connection
        print("Starting background tasks...")
        start_background_tasks()

@app.route('/admin/unban-user', methods=['POST'])
@login_required
def unban_user():
    """Unban a user"""
    # Admin check
    if current_user.email != 'admin@shadowtalk.com' and not (hasattr(current_user, 'is_admin') and current_user.is_admin):
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403

    data = request.get_json()
    user_id = data.get('user_id')

    user = User.query.get(user_id)
    if user and user.is_banned:
        try:
            # Remove ban
            user.is_banned = False
            user.ban_reason = None
            user.banned_at = None
            user.banned_by = None
            user.ban_expires_at = None

            db.session.commit()

            # Send unban notification email
            try:
                from email_utils import send_notification_email
                send_notification_email(
                    user.email,
                    'Account Reinstated',
                    'Your ShadowTalk account has been reinstated. You can now login and use the platform normally. Please review our community guidelines to ensure compliance.'
                )
            except Exception as e:
                print(f"Error sending unban notification email: {e}")

            # Create audit log entry
            try:
                audit_log = AuditLog(
                    admin_id=current_user.id,
                    action=f'Unbanned user {user.email}',
                    target_type='user',
                    target_id=user_id,
                    details='User ban removed',
                    ip_address=request.remote_addr,
                    user_agent=request.headers.get('User-Agent')
                )
                db.session.add(audit_log)
                db.session.commit()
            except Exception as e:
                print(f"Error creating audit log: {e}")

            return jsonify({
                'success': True, 
                'message': f'User {user.email} has been unbanned successfully'
            })

        except Exception as e:
            db.session.rollback()
            print(f"Error unbanning user: {str(e)}")
            return jsonify({'success': False, 'error': 'Failed to unban user'})

    return jsonify({'success': False, 'error': 'User not found or not banned'})

@app.route('/admin/banned-users')
@login_required
def get_banned_users():
    """Get list of banned users"""
    if current_user.email != 'admin@shadowtalk.com' and not (hasattr(current_user, 'is_admin') and current_user.is_admin):
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403

    banned_users = User.query.filter_by(is_banned=True).all()
    
    users_data = []
    for user in banned_users:
        users_data.append({
            'id': user.id,
            'email': user.email,
            'display_name': user.display_name,
            'ban_reason': user.ban_reason,
            'banned_at': user.banned_at.isoformat() if user.banned_at else None,
            'ban_expires_at': user.ban_expires_at.isoformat() if user.ban_expires_at else None,
            'banned_by': user.banned_by
        })
    
    return jsonify({'success': True, 'banned_users': users_data})

@app.route('/admin/user/<user_id>/ban-status')
@login_required
def get_user_ban_status(user_id):
    """Get ban status for a specific user"""
    if current_user.email != 'admin@shadowtalk.com' and not (hasattr(current_user, 'is_admin') and current_user.is_admin):
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403

    user = User.query.get(user_id)
    if not user:
        return jsonify({'success': False, 'error': 'User not found'})

    ban_info = {
        'is_banned': user.is_banned,
        'ban_reason': user.ban_reason,
        'banned_at': user.banned_at.isoformat() if user.banned_at else None,
        'ban_expires_at': user.ban_expires_at.isoformat() if user.ban_expires_at else None,
        'banned_by': user.banned_by
    }

    return jsonify({'success': True, 'ban_info': ban_info})

@app.route('/admin/warn-user', methods=['POST'])
@login_required
def warn_user():
    """Issue a warning to a user"""
    # Admin check
    if current_user.email != 'admin@shadowtalk.com' and not (hasattr(current_user, 'is_admin') and current_user.is_admin):
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403

    data = request.get_json()
    user_id = data.get('user_id')
    reason = data.get('reason')
    severity = data.get('severity', 'medium')

    user = User.query.get(user_id)
    if not user:
        return jsonify({'success': False, 'error': 'User not found'})

    try:
        # Create user warning
        warning = UserWarningLog(
            user_id=user_id,
            admin_id=current_user.id,
            reason=reason,
            severity=severity
        )
        db.session.add(warning)

        # Create notification for the user
        notification = Notification(
            user_id=user_id,
            title=f'Warning Issued ({severity.upper()} Severity)',
            message=f'You have received a warning: {reason}',
            notification_type='warning',
            related_user_id=current_user.id
        )
        db.session.add(notification)

        # Send email notification
        try:
            from email_utils import send_notification_email
            send_notification_email(
                user.email,
                f'ShadowTalk - Warning Issued ({severity.upper()} Severity)',
                f'You have received a warning from ShadowTalk moderators.\n\nReason: {reason}\n\nSeverity: {severity.upper()}\n\nPlease review our community guidelines to ensure this does not happen again.'
            )
        except Exception as e:
            print(f"Error sending warning email: {e}")

        # Create audit log
        audit_log = AuditLog(
            admin_id=current_user.id,
            action=f'Warning issued to user {user.email}',
            target_type='user',
            target_id=user_id,
            details=f'Reason: {reason}, Severity: {severity}',
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent')
        )
        db.session.add(audit_log)

        db.session.commit()

        return jsonify({
            'success': True, 
            'message': f'Warning issued to {user.email} successfully'
        })

    except Exception as e:
        db.session.rollback()
        print(f"Error warning user: {str(e)}")
        return jsonify({'success': False, 'error': 'Failed to issue warning'})

@app.route('/admin/extend-ban', methods=['POST'])
@login_required
def extend_ban():
    """Extend an existing ban"""
    # Admin check
    if current_user.email != 'admin@shadowtalk.com' and not (hasattr(current_user, 'is_admin') and current_user.is_admin):
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403

    data = request.get_json()
    user_id = data.get('user_id')
    duration = data.get('duration')
    reason = data.get('reason', '')

    user = User.query.get(user_id)
    if not user or not user.is_banned:
        return jsonify({'success': False, 'error': 'User not found or not banned'})

    try:
        current_time = datetime.utcnow()
        
        if duration == 'permanent':
            user.ban_expires_at = None
            duration_display = 'permanent'
        else:
            # Calculate new expiration
            if user.ban_expires_at and user.ban_expires_at > current_time:
                # Extend from current expiration
                new_expiration = user.ban_expires_at + timedelta(days=int(duration))
            else:
                # Start from now
                new_expiration = current_time + timedelta(days=int(duration))
            
            user.ban_expires_at = new_expiration
            duration_display = f'{duration} days extension'

        # Update ban reason if additional reason provided
        if reason:
            user.ban_reason = f"{user.ban_reason or 'Previous ban'}. Additional reason: {reason}"

        # Create audit log
        audit_log = AuditLog(
            admin_id=current_user.id,
            action=f'Extended ban for user {user.email}',
            target_type='user',
            target_id=user_id,
            details=f'Extended by: {duration_display}, Additional reason: {reason}',
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent')
        )
        db.session.add(audit_log)

        db.session.commit()

        return jsonify({
            'success': True, 
            'message': f'Ban extended for {user.email} successfully'
        })

    except Exception as e:
        db.session.rollback()
        print(f"Error extending ban: {str(e)}")
        return jsonify({'success': False, 'error': 'Failed to extend ban'})
    
def update_database_schema():
    """Update database schema for the renamed UserWarningLog model"""
    try:
    
        db.create_all()
        print("Database schema updated successfully!")
    except Exception as e:
        print(f"Error updating database schema: {e}")

@app.route('/admin/export/reports')
@login_required
def export_reports():
    """Export reports in PDF or CSV format"""
    if current_user.email != 'admin@shadowtalk.com':
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403

    format_type = request.args.get('format', 'pdf')
    reports = Report.query.filter_by(status='pending').order_by(Report.created_at.desc()).all()

    if format_type == 'pdf':
        return export_reports_pdf(reports)
    elif format_type == 'csv':
        return export_reports_csv(reports)
    else:
        return jsonify({'error': 'Invalid format'}), 400

def export_reports_pdf(reports):
    """Export reports as styled PDF using WeasyPrint"""
    try:
        # Calculate report type distribution
        report_types = {
            'inappropriate_behavior': 0,
            'spam': 0,
            'harassment': 0,
            'other': 0
        }
        
        for report in reports:
            if report.report_type in report_types:
                report_types[report.report_type] += 1

        # Prepare template data
        template_data = {
            'report_title': 'Pending Reports',
            'generated_date': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
            'reports': reports,
            'report_types': report_types,
            'time_period': 'All Time',
            'summary_stats': [
                {'label': 'Total Reports', 'value': len(reports)},
                {'label': 'Pending', 'value': len(reports)},
                {'label': 'Inappropriate', 'value': report_types['inappropriate_behavior']},
                {'label': 'Spam', 'value': report_types['spam']}
            ]
        }

        # Render HTML template
        html_content = render_template('export/reports_pdf.html', **template_data)
        
        # Generate PDF using WeasyPrint
        pdf_file = HTML(string=html_content, base_url=request.base_url).write_pdf()
        
        return send_file(
            io.BytesIO(pdf_file),
            as_attachment=True,
            download_name=f'shadowtalk_reports_{datetime.utcnow().strftime("%Y%m%d_%H%M%S")}.pdf',
            mimetype='application/pdf'
        )
        
    except Exception as e:
        print(f"Error generating PDF with WeasyPrint: {e}")
        # Return error response instead of falling back to CSV
        return jsonify({'error': f'Failed to generate PDF: {str(e)}'}), 500

def export_users_pdf(users):
    """Export users as styled PDF using WeasyPrint"""
    try:
        # Calculate user statistics
        verified_count = sum(1 for user in users if user.is_verified)
        banned_count = sum(1 for user in users if user.is_banned)
        active_count = len(users) - banned_count

        template_data = {
            'report_title': 'Users Management Report',
            'generated_date': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
            'users': users,
            'verified_count': verified_count,
            'banned_count': banned_count,
            'active_count': active_count,
            'summary_stats': [
                {'label': 'Total Users', 'value': len(users)},
                {'label': 'Verified', 'value': verified_count},
                {'label': 'Banned', 'value': banned_count},
                {'label': 'Active', 'value': active_count}
            ]
        }

        html_content = render_template('export/users_pdf.html', **template_data)
        
        # Generate PDF using WeasyPrint
        pdf_file = HTML(string=html_content, base_url=request.base_url).write_pdf()
        
        return send_file(
            io.BytesIO(pdf_file),
            as_attachment=True,
            download_name=f'shadowtalk_users_{datetime.utcnow().strftime("%Y%m%d_%H%M%S")}.pdf',
            mimetype='application/pdf'
        )
        
    except Exception as e:
        print(f"Error generating users PDF: {e}")
        return jsonify({'error': f'Failed to generate PDF: {str(e)}'}), 500

def export_banned_users_pdf(banned_users):
    """Export banned users as styled PDF using WeasyPrint"""
    try:
        # Calculate ban statistics
        permanent_bans = sum(1 for user in banned_users if not user.ban_expires_at)
        temporary_bans = len(banned_users) - permanent_bans
        active_bans = sum(1 for user in banned_users if user.ban_expires_at is None or user.ban_expires_at > datetime.utcnow())

        template_data = {
            'report_title': 'Banned Users Report',
            'generated_date': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
            'banned_users': banned_users,
            'permanent_bans': permanent_bans,
            'temporary_bans': temporary_bans,
            'active_bans': active_bans,
            'datetime': datetime,
            'summary_stats': [
                {'label': 'Total Banned', 'value': len(banned_users)},
                {'label': 'Permanent', 'value': permanent_bans},
                {'label': 'Temporary', 'value': temporary_bans},
                {'label': 'Active', 'value': active_bans}
            ]
        }

        html_content = render_template('export/banned_users_pdf.html', **template_data)
        
        # Generate PDF using WeasyPrint
        pdf_file = HTML(string=html_content, base_url=request.base_url).write_pdf()
        
        return send_file(
            io.BytesIO(pdf_file),
            as_attachment=True,
            download_name=f'shadowtalk_banned_users_{datetime.utcnow().strftime("%Y%m%d_%H%M%S")}.pdf',
            mimetype='application/pdf'
        )
        
    except Exception as e:
        print(f"Error generating banned users PDF: {e}")
        return jsonify({'error': f'Failed to generate PDF: {str(e)}'}), 500

def export_chats_pdf(chat_sessions):
    """Export chat sessions as styled PDF using WeasyPrint"""
    try:
        # Calculate chat statistics
        active_sessions = sum(1 for session in chat_sessions if not session.ended_at)
        text_sessions = sum(1 for session in chat_sessions if session.session_type == 'text')
        video_sessions = sum(1 for session in chat_sessions if session.session_type == 'video')
        total_messages = sum(len(session.messages) for session in chat_sessions)

        template_data = {
            'report_title': 'Chat Sessions Report',
            'generated_date': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
            'chat_sessions': chat_sessions,
            'active_sessions': active_sessions,
            'text_sessions': text_sessions,
            'video_sessions': video_sessions,
            'total_messages': total_messages,
            'summary_stats': [
                {'label': 'Total Sessions', 'value': len(chat_sessions)},
                {'label': 'Active', 'value': active_sessions},
                {'label': 'Text Chats', 'value': text_sessions},
                {'label': 'Video Chats', 'value': video_sessions}
            ]
        }

        html_content = render_template('export/chats_pdf.html', **template_data)
        
        # Generate PDF using WeasyPrint
        pdf_file = HTML(string=html_content, base_url=request.base_url).write_pdf()
        
        return send_file(
            io.BytesIO(pdf_file),
            as_attachment=True,
            download_name=f'shadowtalk_chats_{datetime.utcnow().strftime("%Y%m%d_%H%M%S")}.pdf',
            mimetype='application/pdf'
        )
        
    except Exception as e:
        print(f"Error generating chats PDF: {e}")
        return jsonify({'error': f'Failed to generate PDF: {str(e)}'}), 500

def export_reports_csv(reports):
    """Export reports as CSV"""
    try:
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow(['ID', 'Reporter', 'Reported User', 'Reason', 'Report Type', 'Status', 'Created At'])
        
        # Write data
        for report in reports:
            reporter_name = report.reporter.display_name if report.reporter else 'Anonymous'
            reported_name = report.reported_user.display_name if report.reported_user else 'Anonymous'
            
            writer.writerow([
                report.id,
                reporter_name,
                reported_name,
                report.reason,
                report.report_type,
                report.status,
                report.created_at.strftime('%Y-%m-%d %H:%M:%S')
            ])
        
        output.seek(0)
        
        return send_file(
            io.BytesIO(output.getvalue().encode('utf-8')),
            as_attachment=True,
            download_name=f'reports_{datetime.utcnow().strftime("%Y%m%d_%H%M%S")}.csv',
            mimetype='text/csv'
        )
        
    except Exception as e:
        print(f"Error generating CSV: {e}")
        return jsonify({'error': 'Failed to generate CSV'}), 500

@app.route('/admin/export/users')
@login_required
def export_users():
    """Export users data"""
    if current_user.email != 'admin@shadowtalk.com':
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403

    users = User.query.order_by(User.created_at.desc()).all()
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow(['ID', 'Email', 'Display Name', 'Username', 'Status', 'Verified', 'Banned', 'Created At', 'Last Login'])
    
    # Write data
    for user in users:
        status = 'Banned' if user.is_banned else 'Active'
        
        writer.writerow([
            user.id[:8] + '...',
            user.email,
            user.display_name or 'N/A',
            user.username or 'N/A',
            status,
            'Yes' if user.is_verified else 'No',
            'Yes' if user.is_banned else 'No',
            user.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            user.last_login.strftime('%Y-%m-%d %H:%M:%S') if user.last_login else 'Never'
        ])
    
    output.seek(0)
    
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8')),
        as_attachment=True,
        download_name=f'users_{datetime.utcnow().strftime("%Y%m%d_%H%M%S")}.csv',
        mimetype='text/csv'
    )

@app.route('/admin/export/banned-users')
@login_required
def export_banned_users():
    """Export banned users data"""
    if current_user.email != 'admin@shadowtalk.com':
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403

    banned_users = User.query.filter_by(is_banned=True).order_by(User.banned_at.desc()).all()
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow(['ID', 'Email', 'Display Name', 'Ban Reason', 'Banned At', 'Ban Expires', 'Banned By'])
    
    # Write data
    for user in banned_users:
        banned_by_admin = User.query.get(user.banned_by) if user.banned_by else None
        banned_by_name = banned_by_admin.display_name if banned_by_admin else 'System'
        
        writer.writerow([
            user.id[:8] + '...',
            user.email,
            user.display_name or 'N/A',
            user.ban_reason or 'No reason provided',
            user.banned_at.strftime('%Y-%m-%d %H:%M:%S') if user.banned_at else 'N/A',
            user.ban_expires_at.strftime('%Y-%m-%d %H:%M:%S') if user.ban_expires_at else 'Permanent',
            banned_by_name
        ])
    
    output.seek(0)
    
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8')),
        as_attachment=True,
        download_name=f'banned_users_{datetime.utcnow().strftime("%Y%m%d_%H%M%S")}.csv',
        mimetype='text/csv'
    )

@app.route('/admin/export/chats')
@login_required
def export_chats():
    """Export chat sessions data"""
    if current_user.email != 'admin@shadowtalk.com':
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403

    chat_sessions = ChatSession.query.order_by(ChatSession.started_at.desc()).all()
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow(['Session ID', 'User 1', 'User 2', 'Type', 'Start Time', 'End Time', 'Duration', 'Status', 'Message Count'])
    
    # Write data
    for session in chat_sessions:
        user1_name = session.user1.display_name if session.user1 else 'Unknown'
        user2_name = session.user2.display_name if session.user2 else 'Unknown'
        status = 'Ended' if session.ended_at else 'Active'
        message_count = len(session.messages)
        
        writer.writerow([
            session.id[:8] + '...',
            user1_name,
            user2_name,
            session.session_type,
            session.started_at.strftime('%Y-%m-%d %H:%M:%S') if session.started_at else 'N/A',
            session.ended_at.strftime('%Y-%m-%d %H:%M:%S') if session.ended_at else 'Ongoing',
            f"{session.duration}s" if session.duration else 'N/A',
            status,
            message_count
        ])
    
    output.seek(0)
    
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8')),
        as_attachment=True,
        download_name=f'chat_sessions_{datetime.utcnow().strftime("%Y%m%d_%H%M%S")}.csv',
        mimetype='text/csv'
    )

@app.route('/admin/export/moderation')
@login_required
def export_moderation_queue():
    """Export moderation queue data"""
    if current_user.email != 'admin@shadowtalk.com':
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403

    moderation_items = []  # This would be your actual moderation queue data
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow(['ID', 'Chat Session', 'Message Preview', 'Reason', 'Confidence', 'Status', 'Created At'])
    
    # Write data
    for item in moderation_items:
        writer.writerow([
            item.id,
            item.chat_session_id[:8] + '...' if item.chat_session_id else 'N/A',
            item.message.content[:50] + '...' if item.message and item.message.content else 'N/A',
            item.reason,
            f"{item.confidence_score * 100:.1f}%" if item.confidence_score else 'N/A',
            item.status,
            item.created_at.strftime('%Y-%m-%d %H:%M:%S') if item.created_at else 'N/A'
        ])
    
    output.seek(0)
    
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8')),
        as_attachment=True,
        download_name=f'moderation_queue_{datetime.utcnow().strftime("%Y%m%d_%H%M%S")}.csv',
        mimetype='text/csv'
    )

@app.route('/admin/export/audit-logs')
@login_required
def export_audit_logs():
    """Export audit logs data"""
    if current_user.email != 'admin@shadowtalk.com':
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403

    audit_logs = AuditLog.query.order_by(AuditLog.created_at.desc()).all()
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow(['Timestamp', 'Admin', 'Action', 'Target Type', 'Target ID', 'Details', 'IP Address'])
    
    # Write data
    for log in audit_logs:
        admin_name = log.admin.username if log.admin else 'System'
        
        writer.writerow([
            log.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            admin_name,
            log.action,
            log.target_type or 'N/A',
            log.target_id or 'N/A',
            log.details or 'N/A',
            log.ip_address or 'N/A'
        ])
    
    output.seek(0)
    
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8')),
        as_attachment=True,
        download_name=f'audit_logs_{datetime.utcnow().strftime("%Y%m%d_%H%M%S")}.csv',
        mimetype='text/csv'
    )

def export_reports_pdf(reports):
    """Export reports as styled PDF using WeasyPrint"""
    try:
        # Calculate report type distribution
        report_types = {
            'inappropriate_behavior': 0,
            'spam': 0,
            'harassment': 0,
            'other': 0
        }
        
        for report in reports:
            if report.report_type in report_types:
                report_types[report.report_type] += 1

        # Prepare template data
        template_data = {
            'report_title': 'Pending Reports',
            'generated_date': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
            'reports': reports,
            'report_types': report_types,
            'time_period': 'All Time',
            'summary_stats': [
                {'label': 'Total Reports', 'value': len(reports)},
                {'label': 'Pending', 'value': len(reports)},
                {'label': 'Inappropriate', 'value': report_types['inappropriate_behavior']},
                {'label': 'Spam', 'value': report_types['spam']}
            ]
        }

        # Render HTML template
        html_content = render_template('export/reports_pdf.html', **template_data)
        
        # Generate PDF using WeasyPrint
        pdf_file = HTML(string=html_content, base_url=request.base_url).write_pdf()
        
        return send_file(
            io.BytesIO(pdf_file),
            as_attachment=True,
            download_name=f'shadowtalk_reports_{datetime.utcnow().strftime("%Y%m%d_%H%M%S")}.pdf',
            mimetype='application/pdf'
        )
        
    except Exception as e:
        print(f"Error generating PDF with WeasyPrint: {e}")
        # Fallback to CSV
        return export_reports_csv(reports)

def export_users_pdf(users):
    """Export users as styled PDF using WeasyPrint"""
    try:
        # Calculate user statistics
        verified_count = sum(1 for user in users if user.is_verified)
        banned_count = sum(1 for user in users if user.is_banned)
        active_count = len(users) - banned_count

        template_data = {
            'report_title': 'Users Management Report',
            'generated_date': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
            'users': users,
            'verified_count': verified_count,
            'banned_count': banned_count,
            'active_count': active_count,
            'summary_stats': [
                {'label': 'Total Users', 'value': len(users)},
                {'label': 'Verified', 'value': verified_count},
                {'label': 'Banned', 'value': banned_count},
                {'label': 'Active', 'value': active_count}
            ]
        }

        html_content = render_template('export/users_pdf.html', **template_data)
        
        # Generate PDF using WeasyPrint
        pdf_file = HTML(string=html_content, base_url=request.base_url).write_pdf()
        
        return send_file(
            io.BytesIO(pdf_file),
            as_attachment=True,
            download_name=f'shadowtalk_users_{datetime.utcnow().strftime("%Y%m%d_%H%M%S")}.pdf',
            mimetype='application/pdf'
        )
        
    except Exception as e:
        print(f"Error generating users PDF: {e}")
        return export_users_pdf(users)

def export_banned_users_pdf(banned_users):
    """Export banned users as styled PDF using WeasyPrint"""
    try:
        # Calculate ban statistics
        permanent_bans = sum(1 for user in banned_users if not user.ban_expires_at)
        temporary_bans = len(banned_users) - permanent_bans
        active_bans = sum(1 for user in banned_users if user.ban_expires_at is None or user.ban_expires_at > datetime.utcnow())

        template_data = {
            'report_title': 'Banned Users Report',
            'generated_date': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
            'banned_users': banned_users,
            'permanent_bans': permanent_bans,
            'temporary_bans': temporary_bans,
            'active_bans': active_bans,
            'datetime': datetime,
            'summary_stats': [
                {'label': 'Total Banned', 'value': len(banned_users)},
                {'label': 'Permanent', 'value': permanent_bans},
                {'label': 'Temporary', 'value': temporary_bans},
                {'label': 'Active', 'value': active_bans}
            ]
        }

        html_content = render_template('export/banned_users_pdf.html', **template_data)
        
        # Generate PDF using WeasyPrint
        pdf_file = HTML(string=html_content, base_url=request.base_url).write_pdf()
        
        return send_file(
            io.BytesIO(pdf_file),
            as_attachment=True,
            download_name=f'shadowtalk_banned_users_{datetime.utcnow().strftime("%Y%m%d_%H%M%S")}.pdf',
            mimetype='application/pdf'
        )
        
    except Exception as e:
        print(f"Error generating banned users PDF: {e}")
        return export_banned_users_pdf(banned_users)

def export_chats_pdf(chat_sessions):
    """Export chat sessions as styled PDF using WeasyPrint"""
    try:
        # Calculate chat statistics
        active_sessions = sum(1 for session in chat_sessions if not session.ended_at)
        text_sessions = sum(1 for session in chat_sessions if session.session_type == 'text')
        video_sessions = sum(1 for session in chat_sessions if session.session_type == 'video')
        total_messages = sum(len(session.messages) for session in chat_sessions)

        template_data = {
            'report_title': 'Chat Sessions Report',
            'generated_date': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
            'chat_sessions': chat_sessions,
            'active_sessions': active_sessions,
            'text_sessions': text_sessions,
            'video_sessions': video_sessions,
            'total_messages': total_messages,
            'summary_stats': [
                {'label': 'Total Sessions', 'value': len(chat_sessions)},
                {'label': 'Active', 'value': active_sessions},
                {'label': 'Text Chats', 'value': text_sessions},
                {'label': 'Video Chats', 'value': video_sessions}
            ]
        }

        html_content = render_template('export/chats_pdf.html', **template_data)
        
        # Generate PDF using WeasyPrint
        pdf_file = HTML(string=html_content, base_url=request.base_url).write_pdf()
        
        return send_file(
            io.BytesIO(pdf_file),
            as_attachment=True,
            download_name=f'shadowtalk_chats_{datetime.utcnow().strftime("%Y%m%d_%H%M%S")}.pdf',
            mimetype='application/pdf'
        )
        
    except Exception as e:
        print(f"Error generating chats PDF: {e}")
        return export_chats_pdf(chat_sessions)
    
if __name__ == '__main__':
    with app.app_context():
        try:
            # Try to create tables if they don't exist
            db.create_all()
            print("Database tables checked/created successfully!")

            # Create default admin user if not exists
            from werkzeug.security import generate_password_hash
            admin_user = Admin.query.filter_by(username='admin@shadowtalk.com').first()
            if not admin_user:
                print("Creating default admin user...")
                admin_user = Admin(
                    username='admin@shadowtalk.com',
                    password=generate_password_hash('admin123'),
                    is_super_admin=True
                )
                db.session.add(admin_user)
                db.session.commit()
                print("✓ Default admin user created: admin@shadowtalk.com / admin123")
            else:
                print("✓ Admin user already exists")

        except Exception as e:
            print(f"Error during setup: {e}")

    socketio.run(
        app,
        debug=True,
        host='0.0.0.0',
        port=5000,
        allow_unsafe_werkzeug=True
    )
