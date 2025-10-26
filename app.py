from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from flask_socketio import SocketIO, join_room, leave_room, emit
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_mail import Mail
from werkzeug.security import generate_password_hash, check_password_hash
import json
import random
from datetime import datetime, timedelta
import uuid

from config import Config
from models import db, User, OTP, ChatSession, Message, Connection, Notification, Report, Admin
from database import init_db
from email_utils import mail, send_otp_email, send_notification_email
from flask_mail import Message as MailMessage
app = Flask(__name__)
app.config.from_object(Config)

# In app.py, update the SocketIO initialization:
try:
    import eventlet
    async_mode = 'eventlet'
except ImportError:
    try:
        import gevent
        async_mode = 'gevent'
    except ImportError:
        async_mode = 'threading'

socketio = SocketIO(
    app, 
    cors_allowed_origins="*", 
    async_mode=async_mode,
    logger=True,
    engineio_logger=True
)

# Initialize extensions - ONLY ONCE
db.init_app(app)  # Initialize db with app here
mail.init_app(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Global variables for matchmaking
waiting_users = {
    'text': [],
    'video': []
}
active_chats = {}

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(user_id)

# Authentication Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        remember = bool(request.form.get('remember'))
        
        user = User.query.filter_by(email=email).first()
        
        if user and check_password_hash(user.password, password):
            if user.is_verified:
                login_user(user, remember=remember)
                user.last_login = datetime.utcnow()
                db.session.commit()
                
                # Redirect to profile setup if profile not complete
                if not user.is_profile_complete:
                    return redirect(url_for('profile_setup'))
                
                return redirect(url_for('dashboard'))
            else:
                return render_template('login.html', error='Please verify your email first')
        else:
            return render_template('login.html', error='Invalid email or password')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        if password != confirm_password:
            return render_template('register.html', error='Passwords do not match')
        
        if User.query.filter_by(email=email).first():
            return render_template('register.html', error='Email already registered')
        
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
            return render_template('register.html', error='Failed to send verification email')
    
    return render_template('register.html')

@app.route('/verify-otp', methods=['GET', 'POST'])
def verify_otp():
    email = session.get('verify_email')
    if not email:
        return redirect(url_for('register'))
    
    if request.method == 'POST':
        otp = request.form.get('otp')
        
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
            return render_template('verify_otp.html', error='Invalid or expired OTP')
    
    return render_template('verify_otp.html')

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

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('index.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

# Password Reset Routes
@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email')
        user = User.query.filter_by(email=email).first()
        
        if user:
            # Generate reset token
            reset_token = str(uuid.uuid4())
            session['reset_token'] = reset_token
            session['reset_email'] = email
            session['reset_expires'] = datetime.utcnow() + timedelta(hours=1)
            
            # Send reset email with button
            if send_reset_email(email, reset_token):
                return render_template('forgot_password.html', 
                                     success='Password reset link has been sent to your email')
            else:
                return render_template('forgot_password.html', 
                                     error='Failed to send reset email. Please try again.')
        else:
            return render_template('forgot_password.html', 
                                 error='No account found with that email address')
    
    return render_template('forgot_password.html')

@app.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    # Get token from URL parameters or session
    token = request.args.get('token')
    
    if not token or 'reset_token' not in session or session['reset_token'] != token:
        return render_template('reset_password.html', 
                             error='Invalid or expired reset token')
    
    if session['reset_expires'] < datetime.utcnow():
        return render_template('reset_password.html', 
                             error='Reset token has expired')
    
    if request.method == 'POST':
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        if password != confirm_password:
            return render_template('reset_password.html', 
                                 error='Passwords do not match')
        
        user = User.query.filter_by(email=session['reset_email']).first()
        if user:
            user.password = generate_password_hash(password)
            db.session.commit()
            
            # Clear reset session
            session.pop('reset_token', None)
            session.pop('reset_email', None)
            session.pop('reset_expires', None)
            
            return render_template('reset_password.html', 
                                 success='Password has been reset successfully')
    
    return render_template('reset_password.html')

# Admin Routes
@app.route('/admin')
@login_required
def admin_dashboard():
    # Simple admin check - in production, use proper role-based authentication
    if current_user.email != 'admin@shadowtalk.com':
        return redirect(url_for('index'))
    
    # Get statistics
    stats = {
        'total_users': User.query.count(),
        'active_chats': len(active_chats) // 2,
        'pending_reports': Report.query.filter_by(status='pending').count(),
        'banned_users': 0,
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
        ).scalar() or 0
    }
    
    # Get recent reports
    reports = Report.query.filter_by(status='pending').order_by(
        Report.created_at.desc()
    ).all()
    
    # Get users
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
    
    # Recent activity (mock data)
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
                         recent_activity=recent_activity)

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
    # Admin check
    if current_user.email != 'admin@shadowtalk.com':
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    data = request.get_json()
    user_id = data.get('user_id')
    
    user = User.query.get(user_id)
    if user:
        # In a real application, you would set a 'banned' field to True
        # For now, we'll just return success
        return jsonify({'success': True, 'message': 'User banned successfully'})
    
    return jsonify({'success': False, 'error': 'User not found'})

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

# SocketIO Events
@socketio.on('connect')
def handle_connect():
    if current_user.is_authenticated:
        join_room(current_user.id)
        emit('connection_status', {'status': 'connected'})

@socketio.on('disconnect')
def handle_disconnect():
    if current_user.is_authenticated:
        leave_room(current_user.id)
        # Remove from waiting lists
        for chat_type in ['text', 'video']:
            if current_user.id in waiting_users[chat_type]:
                waiting_users[chat_type].remove(current_user.id)

@socketio.on('join_chat')
def handle_join_chat(data):
    chat_type = data.get('type', 'text')
    interests = data.get('interests', [])
    
    # Add user to waiting list
    if current_user.id not in waiting_users[chat_type]:
        waiting_users[chat_type].append(current_user.id)
    
    # Try to match users
    if len(waiting_users[chat_type]) >= 2:
        user1_id = waiting_users[chat_type].pop(0)
        user2_id = waiting_users[chat_type].pop(0)
        
        # Create chat session
        chat_session = ChatSession(
            user1_id=user1_id,
            user2_id=user2_id,
            session_type=chat_type
        )
        db.session.add(chat_session)
        db.session.commit()
        
        # Store active chat
        active_chats[user1_id] = {'session_id': chat_session.id, 'partner': user2_id}
        active_chats[user2_id] = {'session_id': chat_session.id, 'partner': user1_id}
        
        # Notify both users
        emit('match_found', {
            'session_id': chat_session.id,
            'partner_id': user2_id
        }, room=user1_id)
        
        emit('match_found', {
            'session_id': chat_session.id,
            'partner_id': user1_id
        }, room=user2_id)
        
        # Create connection record
        connection = Connection.query.filter(
            ((Connection.user1_id == user1_id) & (Connection.user2_id == user2_id)) |
            ((Connection.user1_id == user2_id) & (Connection.user2_id == user1_id))
        ).first()
        
        if connection:
            connection.chat_count += 1
            connection.last_chat = datetime.utcnow()
        else:
            connection = Connection(
                user1_id=user1_id,
                user2_id=user2_id
            )
            db.session.add(connection)
        
        db.session.commit()
    else:
        emit('searching', {'count': len(waiting_users[chat_type])})

@socketio.on('send_message')
def handle_send_message(data):
    session_id = data.get('session_id')
    message_content = data.get('message')
    
    chat_session = ChatSession.query.get(session_id)
    if not chat_session:
        return
    
    # Create message
    message = Message(
        chat_session_id=session_id,
        sender_id=current_user.id,
        content=message_content
    )
    db.session.add(message)
    db.session.commit()
    
    # Send to partner
    partner_id = chat_session.user2_id if chat_session.user1_id == current_user.id else chat_session.user1_id
    
    emit('receive_message', {
        'message': message_content,
        'sender_id': current_user.id,
        'timestamp': message.timestamp.isoformat()
    }, room=partner_id)

@socketio.on('leave_chat')
def handle_leave_chat(data):
    session_id = data.get('session_id')
    
    if current_user.id in active_chats:
        partner_id = active_chats[current_user.id]['partner']
        del active_chats[current_user.id]
        
        if partner_id in active_chats:
            del active_chats[partner_id]
            emit('partner_left', room=partner_id)
    
    # Update chat session end time
    chat_session = ChatSession.query.get(session_id)
    if chat_session:
        chat_session.ended_at = datetime.utcnow()
        if chat_session.started_at:
            duration = (chat_session.ended_at - chat_session.started_at).total_seconds()
            chat_session.duration = int(duration)
        db.session.commit()

@socketio.on('webrtc_signal')
def handle_webrtc_signal(data):
    partner_id = active_chats.get(current_user.id, {}).get('partner')
    if partner_id:
        emit('webrtc_signal', data, room=partner_id)

# Add this before running the app
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        
        # Create default admin user if not exists
        from werkzeug.security import generate_password_hash
        admin = Admin.query.filter_by(username='admin').first()
        if not admin:
            admin = Admin(
                username='admin',
                password=generate_password_hash('admin123')
            )
            db.session.add(admin)
            db.session.commit()
    
    # Use eventlet for better WebRTC support
    socketio.run(
        app, 
        debug=True, 
        host='0.0.0.0', 
        port=5000,
        allow_unsafe_werkzeug=True
    )