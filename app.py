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
import uuid
import time
from sqlalchemy import desc

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
from email_utils import mail, send_otp_email, send_notification_email, send_password_reset_email
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
        print(f"Password reset requested for: {email}")

        # Rate limiting - check if too many requests from this IP
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

            # Set session data with consistent datetime format
            session['reset_token'] = reset_token
            session['reset_email'] = email
            session['reset_expires'] = (datetime.utcnow() + timedelta(hours=1)).strftime('%Y-%m-%d %H:%M:%S')

            # Log the reset request
            reset_request = PasswordResetRequest(
                email=email,
                ip_address=client_ip,
                user_agent=request.headers.get('User-Agent')
            )
            db.session.add(reset_request)

            print(f"Generated reset token: {reset_token}")
            print(f"Reset expires: {session['reset_expires']}")

            # Send reset email
            try:
                if send_password_reset_email(email, reset_token):
                    db.session.commit()
                    print("Password reset email sent successfully")
                    return render_template('auth/forgot_password.html',
                                         success='Password reset link has been sent to your email')
                else:
                    db.session.rollback()
                    print("Failed to send password reset email")
                    return render_template('auth/forgot_password.html',
                                         error='Failed to send reset email. Please try again.')
            except Exception as e:
                db.session.rollback()
                print(f"Error in forgot_password route: {str(e)}")
                return render_template('auth/forgot_password.html',
                                     error='An error occurred. Please try again.')
        else:
            print(f"No user found with email: {email}")
            # Still return success to prevent email enumeration
            return render_template('auth/forgot_password.html',
                                 success='If an account with that email exists, a reset link has been sent.')

    return render_template('auth/forgot_password.html')

@app.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    """Complete password reset functionality"""
    from datetime import datetime  # Import at function level to avoid conflicts
    
    # Get token from URL parameters
    token = request.args.get('token')

    # Debug information
    print(f"Reset password attempt - Token: {token}")
    print(f"Session reset_token: {session.get('reset_token')}")
    print(f"Session reset_expires: {session.get('reset_expires')}")
    print(f"Session reset_email: {session.get('reset_email')}")

    if not token:
        flash('Invalid or missing reset token', 'error')
        return render_template('auth/reset_password.html',
                             error='Invalid or missing reset token')

    # Check if token matches session
    if session.get('reset_token') != token:
        flash('Invalid reset token', 'error')
        return render_template('auth/reset_password.html',
                             error='Invalid reset token')

    # Check if token is expired
    reset_expires_str = session.get('reset_expires')
    if not reset_expires_str:
        flash('Reset token has expired', 'error')
        return render_template('auth/reset_password.html',
                             error='Reset token has expired')

    try:
        # Convert string to datetime (handling both naive and aware datetimes)
        if 'T' in reset_expires_str:
            # ISO format with timezone info
            reset_expires = datetime.fromisoformat(reset_expires_str.replace('Z', '+00:00'))
        else:
            # Simple format
            reset_expires = datetime.strptime(reset_expires_str, '%Y-%m-%d %H:%M:%S')

        # Make both datetimes naive for comparison
        reset_expires_naive = reset_expires.replace(tzinfo=None) if reset_expires.tzinfo else reset_expires
        current_time_naive = datetime.utcnow()

        print(f"Reset expires: {reset_expires_naive}")
        print(f"Current time: {current_time_naive}")
        print(f"Is expired: {reset_expires_naive < current_time_naive}")

        if reset_expires_naive < current_time_naive:
            flash('Reset token has expired', 'error')
            return render_template('auth/reset_password.html',
                                 error='Reset token has expired. Please request a new one.')

    except (ValueError, TypeError, AttributeError) as e:
        print(f"Error parsing reset expiration: {e}")
        flash('Invalid reset token format', 'error')
        return render_template('auth/reset_password.html',
                             error='Invalid reset token')

    if request.method == 'POST':
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        print(f"Password reset form submitted")
        print(f"Email from session: {session.get('reset_email')}")

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
            print(f"Error resetting password: {str(e)}")
            return render_template('auth/reset_password.html',
                                 error='Error updating password. Please try again.',
                                 token=token)

    # For GET request, show the reset form with token
    return render_template('auth/reset_password.html', token=token)

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

@app.route('/update-profile', methods=['POST'])
@login_required
def update_profile():
    if request.method == 'POST':
        current_user.display_name = request.form.get('display_name')
        current_user.username = request.form.get('username')
        current_user.age = request.form.get('age')
        current_user.gender = request.form.get('gender')
        current_user.bio = request.form.get('bio')

        interests = request.form.getlist('interests')
        current_user.interests = json.dumps(interests)

        # Handle avatar upload
        if 'avatar' in request.files:
            avatar_file = request.files['avatar']
            if avatar_file and avatar_file.filename:
                # Save avatar file and update user's avatar_url
                filename = secure_filename(avatar_file.filename)
                avatar_path = os.path.join('static/avatars', filename)
                avatar_file.save(avatar_path)
                current_user.avatar_url = url_for('static', filename=f'avatars/{filename}')

        db.session.commit()
        flash('Profile updated successfully!', 'success')
        return redirect(url_for('profile'))

    return redirect(url_for('profile'))

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

        # Send ban notification email
        try:
            from email_utils import send_ban_notification_email
            send_ban_notification_email(
                user.email,
                ban_reason,
                ban_duration,
                user.ban_expires_at
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

# Chat Session Management
@socketio.on('start_chat_search')
def handle_start_chat_search(data):
    """Start searching for a chat partner"""
    if not current_user.is_authenticated:
        emit('error', {'message': 'Authentication required'})
        return

    chat_type = data.get('type', 'text')
    user_interests = data.get('interests', [])
    filters = data.get('filters', {})

    # Remove user from any existing queues
    for ctype in ['text', 'video']:
        waiting_users[ctype] = [u for u in waiting_users[ctype] if u.get('user_id') != current_user.id]

    # Add user to waiting list with metadata
    user_data = {
        'user_id': current_user.id,
        'interests': user_interests,
        'filters': filters,
        'joined_at': datetime.utcnow().isoformat(),
        'chat_type': chat_type
    }

    waiting_users[chat_type].append(user_data)

    # Send searching status
    emit('chat_search_started', {
        'chat_type': chat_type,
        'position': len(waiting_users[chat_type]),
        'total_waiting': len(waiting_users[chat_type]),
        'estimated_wait': calculate_estimated_wait(chat_type),
        'timestamp': datetime.utcnow().isoformat()
    }, room=current_user.id)

    # Try to match immediately
    attempt_matchmaking(chat_type)

    print(f"User {current_user.id} started {chat_type} chat search. Position: {len(waiting_users[chat_type])}")

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
