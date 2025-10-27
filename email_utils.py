from flask_mail import Mail, Message as MailMessage
from flask import render_template_string, url_for
import random
import string
from datetime import datetime, timedelta
from models import OTP, db

mail = Mail()

def generate_otp():
    return ''.join(random.choices(string.digits, k=6))

def send_otp_email(email):
    # Delete any existing OTP for this email
    OTP.query.filter_by(email=email).delete()

    # Generate new OTP
    otp_code = generate_otp()
    expires_at = datetime.utcnow() + timedelta(minutes=5)  # Reduced to 5 minutes for security

    # Save OTP to database
    otp = OTP(email=email, otp=otp_code, expires_at=expires_at)
    db.session.add(otp)
    db.session.commit()

    # Create styled email template with enhanced design
    html_content = render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {
                background: linear-gradient(135deg, #2c2c2c 0%, #1a1a1a 100%);
                color: #e0e0e0;
                font-family: 'Arial', sans-serif;
                margin: 0;
                padding: 0;
            }
            .container {
                max-width: 600px;
                margin: 0 auto;
                background: #2c2c2c;
                border-radius: 15px;
                overflow: hidden;
                box-shadow: 0 10px 30px rgba(0,0,0,0.3);
            }
            .header {
                background: linear-gradient(135deg, #8b5cf6 0%, #a855f7 100%);
                padding: 30px;
                text-align: center;
            }
            .header h1 {
                color: white;
                margin: 0;
                font-size: 28px;
                font-weight: bold;
            }
            .content {
                padding: 40px;
                text-align: center;
            }
            .otp-code {
                background: linear-gradient(135deg, #8b5cf6 0%, #a855f7 100%);
                color: white;
                font-size: 32px;
                font-weight: bold;
                padding: 25px;
                border-radius: 15px;
                margin: 25px 0;
                letter-spacing: 10px;
                box-shadow: 0 5px 15px rgba(139, 92, 246, 0.3);
                animation: pulse 2s infinite;
            }
            .footer {
                background: #1a1a1a;
                padding: 20px;
                text-align: center;
                color: #888;
                font-size: 12px;
            }
            .warning {
                background: #f39c12;
                color: white;
                padding: 12px;
                border-radius: 8px;
                margin: 20px 0;
                font-size: 14px;
                border-left: 4px solid #e67e22;
            }
            .security-tip {
                background: #34495e;
                color: #bdc3c7;
                padding: 12px;
                border-radius: 8px;
                margin: 15px 0;
                font-size: 13px;
                border-left: 4px solid #3498db;
            }
            @keyframes pulse {
                0% { transform: scale(1); }
                50% { transform: scale(1.02); }
                100% { transform: scale(1); }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>ShadowTalk</h1>
                <p>Secure Anonymous Chat Platform</p>
            </div>
            <div class="content">
                <h2>Email Verification Required</h2>
                <p>Hello! To complete your registration, please use the following One-Time Password:</p>

                <div class="otp-code">{{ otp_code }}</div>

                <div class="warning">
                    <strong>⚠️ Important Security Notice</strong><br>
                    This OTP will expire in <strong>5 minutes</strong>. Do not share this code with anyone.
                </div>

                <div class="security-tip">
                    <strong>🔒 Security Tip:</strong> ShadowTalk staff will never ask for your OTP.
                    Keep it confidential at all times.
                </div>

                <p>If you didn't request this verification, please ignore this email and ensure your account security.</p>
            </div>
            <div class="footer">
                <p>&copy; 2024 ShadowTalk. All rights reserved.</p>
                <p>Protecting your privacy and security</p>
            </div>
        </div>
    </body>
    </html>
    ''', otp_code=otp_code)

    # Send email
    msg = MailMessage(
        subject='ShadowTalk - Email Verification OTP (Expires in 5 minutes)',
        recipients=[email],
        html=html_content
    )

    try:
        mail.send(msg)
        print(f"OTP email successfully sent to {email}")
        return True
    except Exception as e:
        print(f"Error sending OTP email to {email}: {str(e)}")
        db.session.rollback()
        return False

def send_notification_email(user_email, title, message):
    html_content = render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {
                background: linear-gradient(135deg, #2c2c2c 0%, #1a1a1a 100%);
                color: #e0e0e0;
                font-family: 'Arial', sans-serif;
                margin: 0;
                padding: 0;
            }
            .container {
                max-width: 600px;
                margin: 0 auto;
                background: #2c2c2c;
                border-radius: 15px;
                overflow: hidden;
                box-shadow: 0 10px 30px rgba(0,0,0,0.3);
            }
            .header {
                background: linear-gradient(135deg, #8b5cf6 0%, #a855f7 100%);
                padding: 30px;
                text-align: center;
            }
            .header h1 {
                color: white;
                margin: 0;
                font-size: 28px;
                font-weight: bold;
            }
            .content {
                padding: 40px;
            }
            .notification {
                background: #3c3c3c;
                padding: 25px;
                border-radius: 12px;
                margin: 20px 0;
                border-left: 5px solid #8b5cf6;
                animation: slideIn 0.5s ease-out;
            }
            .footer {
                background: #1a1a1a;
                padding: 20px;
                text-align: center;
                color: #888;
                font-size: 12px;
            }
            .action-button {
                display: inline-block;
                background: #8b5cf6;
                color: white;
                padding: 12px 30px;
                text-decoration: none;
                border-radius: 25px;
                margin: 15px 0;
                font-weight: bold;
                transition: all 0.3s ease;
            }
            .action-button:hover {
                background: #7c3aed;
                transform: translateY(-2px);
            }
            @keyframes slideIn {
                from {
                    opacity: 0;
                    transform: translateX(-20px);
                }
                to {
                    opacity: 1;
                    transform: translateX(0);
                }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>ShadowTalk</h1>
                <p>New Notification</p>
            </div>
            <div class="content">
                <h2>{{ title }}</h2>
                <div class="notification">
                    <p style="margin: 0; font-size: 16px; line-height: 1.6;">{{ message }}</p>
                </div>
                <p style="text-align: center;">
                    <a href="https://shadow01.pythonanywhere.com/dashboard" class="action-button">
                        View in Dashboard
                    </a>
                </p>
                <p style="color: #888; font-size: 14px; text-align: center;">
                    Login to ShadowTalk to view more details and manage your notifications.
                </p>
            </div>
            <div class="footer">
                <p>&copy; 2024 ShadowTalk. All rights reserved.</p>
                <p>Stay connected, stay anonymous</p>
            </div>
        </div>
    </body>
    </html>
    ''', title=title, message=message)

    msg = MailMessage(
        subject=f'ShadowTalk - {title}',
        recipients=[user_email],
        html=html_content
    )

    try:
        mail.send(msg)
        print(f"Notification email successfully sent to {user_email}")
        return True
    except Exception as e:
        print(f"Error sending notification email to {user_email}: {str(e)}")
        return False

def send_password_reset_email(email, reset_token):
    try:
        # Use your actual domain
        reset_url = f"https://shadow01.pythonanywhere.com/reset-password?token={reset_token}"

        print(f"Sending password reset email to: {email}")
        print(f"Reset URL: {reset_url}")

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
                .reset-link {{
                    display: inline-block;
                    background: linear-gradient(135deg, #8b5cf6 0%, #a855f7 100%);
                    color: white;
                    padding: 18px 45px;
                    text-decoration: none;
                    border-radius: 30px;
                    margin: 25px 0;
                    font-weight: bold;
                    font-size: 18px;
                    box-shadow: 0 5px 15px rgba(139, 92, 246, 0.4);
                    transition: all 0.3s ease;
                    border: none;
                    cursor: pointer;
                }}
                .reset-link:hover {{
                    transform: translateY(-3px);
                    box-shadow: 0 8px 25px rgba(139, 92, 246, 0.6);
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
                    padding: 15px;
                    background: #3c3c3c;
                    border-radius: 8px;
                    font-size: 14px;
                    border: 1px solid #4c4c4c;
                }}
                .warning {{
                    background: #e74c3c;
                    color: white;
                    padding: 15px;
                    border-radius: 8px;
                    margin: 20px 0;
                    font-size: 14px;
                    border-left: 5px solid #c0392b;
                    animation: pulse 2s infinite;
                }}
                .security-info {{
                    background: #34495e;
                    color: #bdc3c7;
                    padding: 15px;
                    border-radius: 8px;
                    margin: 15px 0;
                    font-size: 13px;
                    border-left: 5px solid #3498db;
                }}
                @keyframes pulse {{
                    0% {{ transform: scale(1); }}
                    50% {{ transform: scale(1.02); }}
                    100% {{ transform: scale(1); }}
                }}
                .steps {{
                    text-align: left;
                    margin: 25px 0;
                    background: #3c3c3c;
                    padding: 20px;
                    border-radius: 10px;
                }}
                .step {{
                    margin: 12px 0;
                    display: flex;
                    align-items: center;
                }}
                .step-number {{
                    background: #8b5cf6;
                    color: white;
                    width: 25px;
                    height: 25px;
                    border-radius: 50%;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    margin-right: 15px;
                    font-weight: bold;
                    font-size: 14px;
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
                    <p>You requested to reset your password for your ShadowTalk account.</p>

                    <div class="steps">
                        <div class="step">
                            <div class="step-number">1</div>
                            <span>Click the reset button below</span>
                        </div>
                        <div class="step">
                            <div class="step-number">2</div>
                            <span>Create a new strong password</span>
                        </div>
                        <div class="step">
                            <div class="step-number">3</div>
                            <span>Login with your new password</span>
                        </div>
                    </div>

                    <a href="{reset_url}" class="reset-link">Reset Password Now</a>

                    <p>Or copy and paste this link in your browser:</p>
                    <div class="text-link">{reset_url}</div>

                    <div class="warning">
                        <strong>🚨 URGENT: Link Expires in 1 Hour</strong><br>
                        For security reasons, this password reset link will expire in 60 minutes.
                    </div>

                    <div class="security-info">
                        <strong>🔒 Security Notice</strong><br>
                        • If you didn't request this reset, your account may be compromised<br>
                        • Never share your password or this link with anyone<br>
                        • ShadowTalk will never ask for your password via email
                    </div>

                    <p style="color: #888; font-size: 14px; margin-top: 20px;">
                        Need help? Contact our support team through the app.
                    </p>
                </div>
                <div class="footer">
                    <p>&copy; 2024 ShadowTalk. All rights reserved.</p>
                    <p>This is an automated security message, please do not reply to this email.</p>
                </div>
            </div>
        </body>
        </html>
        '''

        msg = MailMessage(
            subject='ShadowTalk - Password Reset Request (URGENT: Expires in 1 Hour)',
            recipients=[email],
            html=html_content
        )

        mail.send(msg)
        print(f"Password reset email successfully sent to {email}")
        return True

    except Exception as e:
        print(f"Error sending password reset email to {email}: {str(e)}")
        return False

# New function for OTP resend
def resend_otp_email(email):
    """
    Resend OTP email with a new code
    """
    return send_otp_email(email)

# New function for enhanced security notifications
def send_security_alert_email(email, alert_type, details):
    """
    Send security alert emails for suspicious activities
    """
    subject_map = {
        'login_attempt': 'New Login Attempt Detected',
        'password_changed': 'Password Successfully Changed',
        'device_added': 'New Device Connected',
        'suspicious_activity': 'Suspicious Activity Detected'
    }

    html_content = render_template_string('''
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
                background: linear-gradient(135deg, #e74c3c 0%, #c0392b 100%);
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
            }}
            .alert-box {{
                background: #c0392b;
                color: white;
                padding: 20px;
                border-radius: 10px;
                margin: 20px 0;
                text-align: center;
                font-size: 18px;
                font-weight: bold;
            }}
            .details {{
                background: #3c3c3c;
                padding: 20px;
                border-radius: 10px;
                margin: 15px 0;
            }}
            .footer {{
                background: #1a1a1a;
                padding: 20px;
                text-align: center;
                color: #888;
                font-size: 12px;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>ShadowTalk</h1>
                <p>Security Alert</p>
            </div>
            <div class="content">
                <div class="alert-box">
                    ⚠️ SECURITY ALERT: {{ alert_type }}
                </div>
                <div class="details">
                    <p><strong>Details:</strong> {{ details }}</p>
                    <p><strong>Time:</strong> {{ timestamp }}</p>
                    <p><strong>Account:</strong> {{ email }}</p>
                </div>
                <p>If this wasn't you, please secure your account immediately.</p>
            </div>
            <div class="footer">
                <p>&copy; 2024 ShadowTalk. All rights reserved.</p>
                <p>Protecting your digital identity</p>
            </div>
        </div>
    </body>
    </html>
    ''', alert_type=alert_type, details=details,
        timestamp=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"), email=email)

    msg = MailMessage(
        subject=f'ShadowTalk Security Alert: {subject_map.get(alert_type, "Security Notice")}',
        recipients=[email],
        html=html_content
    )

    try:
        mail.send(msg)
        print(f"Security alert email sent to {email}")
        return True
    except Exception as e:
        print(f"Error sending security alert email: {str(e)}")
        return Falsergb(255,255,255)

def send_ban_notification_email(email, ban_reason, ban_duration, ban_expires_at=None, appeal_instructions=None):
    """
    Send ban notification email to user
    """
    # Format ban duration for display
    if ban_duration == 'permanent':
        duration_display = "Permanent"
        duration_note = "This is a permanent ban from the ShadowTalk platform."
    else:
        duration_display = f"{ban_duration} days"
        if ban_expires_at:
            from datetime import datetime
            expires_formatted = ban_expires_at.strftime("%B %d, %Y at %H:%M UTC")
            duration_note = f"Your ban will expire on {expires_formatted}."
        else:
            duration_note = f"Your ban will expire after {ban_duration} days."

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
                background: linear-gradient(135deg, #e74c3c 0%, #c0392b 100%);
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
            .ban-notice {{
                background: linear-gradient(135deg, #e74c3c 0%, #c0392b 100%);
                color: white;
                font-size: 24px;
                font-weight: bold;
                padding: 25px;
                border-radius: 15px;
                margin: 25px 0;
                box-shadow: 0 5px 15px rgba(231, 76, 60, 0.3);
                animation: pulse 2s infinite;
            }}
            .details-box {{
                background: #3c3c3c;
                padding: 25px;
                border-radius: 12px;
                margin: 20px 0;
                text-align: left;
                border-left: 5px solid #e74c3c;
            }}
            .detail-item {{
                margin: 15px 0;
                padding: 10px;
                background: #4c4c4c;
                border-radius: 8px;
            }}
            .detail-label {{
                font-weight: bold;
                color: #e74c3c;
                margin-right: 10px;
            }}
            .appeal-section {{
                background: #34495e;
                padding: 25px;
                border-radius: 12px;
                margin: 25px 0;
                border-left: 5px solid #3498db;
            }}
            .contact-button {{
                display: inline-block;
                background: linear-gradient(135deg, #3498db 0%, #2980b9 100%);
                color: white;
                padding: 15px 35px;
                text-decoration: none;
                border-radius: 25px;
                margin: 15px 0;
                font-weight: bold;
                font-size: 16px;
                transition: all 0.3s ease;
            }}
            .contact-button:hover {{
                background: linear-gradient(135deg, #2980b9 0%, #2471a3 100%);
                transform: translateY(-2px);
            }}
            .footer {{
                background: #1a1a1a;
                padding: 20px;
                text-align: center;
                color: #888;
                font-size: 12px;
            }}
            .warning {{
                background: #c0392b;
                color: white;
                padding: 15px;
                border-radius: 8px;
                margin: 20px 0;
                font-size: 14px;
                border-left: 5px solid #a93226;
            }}
            .steps {{
                text-align: left;
                margin: 20px 0;
                background: #3c3c3c;
                padding: 20px;
                border-radius: 10px;
            }}
            .step {{
                margin: 12px 0;
                display: flex;
                align-items: center;
            }}
            .step-number {{
                background: #3498db;
                color: white;
                width: 25px;
                height: 25px;
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                margin-right: 15px;
                font-weight: bold;
                font-size: 14px;
            }}
            @keyframes pulse {{
                0% {{ transform: scale(1); }}
                50% {{ transform: scale(1.02); }}
                100% {{ transform: scale(1); }}
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>ShadowTalk</h1>
                <p>Account Status Notification</p>
            </div>
            <div class="content">
                <div class="ban-notice">
                    ⚠️ ACCOUNT SUSPENDED
                </div>

                <p>We regret to inform you that your ShadowTalk account has been suspended due to a violation of our terms of service.</p>

                <div class="details-box">
                    <div class="detail-item">
                        <span class="detail-label">Ban Reason:</span>
                        <span>{ban_reason}</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">Ban Duration:</span>
                        <span>{duration_display}</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">Effective Date:</span>
                        <span>{datetime.utcnow().strftime("%B %d, %Y at %H:%M UTC")}</span>
                    </div>
                </div>

                <div class="warning">
                    <strong>🚫 ACCOUNT RESTRICTIONS</strong><br>
                    During this suspension period, you will not be able to:
                    • Access your ShadowTalk account<br>
                    • Participate in chat sessions<br>
                    • Send or receive messages<br>
                    • Use any platform features
                </div>

                <div class="appeal-section">
                    <h3>📧 Appeal Process</h3>
                    <p>If you believe this suspension was made in error, you may appeal the decision.</p>

                    <div class="steps">
                        <div class="step">
                            <div class="step-number">1</div>
                            <span>Contact our support team at <strong>support@shadowtalk.com</strong></span>
                        </div>
                        <div class="step">
                            <div class="step-number">2</div>
                            <span>Include your username and a detailed explanation</span>
                        </div>
                        <div class="step">
                            <div class="step-number">3</div>
                            <span>Wait for our team to review your appeal (typically 24-48 hours)</span>
                        </div>
                    </div>

                    <a href="https://shadow01.pythonanywhere.com/contact" class="contact-button">
                        Contact Support Team
                    </a>
                </div>

                <div class="details-box">
                    <strong>📋 Important Information:</strong><br>
                    • {duration_note}<br>
                    • All appeal decisions are final<br>
                    • Repeated violations may result in permanent bans<br>
                    • Please review our Terms of Service and Community Guidelines
                </div>

                <p style="color: #888; font-size: 14px; margin-top: 20px;">
                    This is an automated notification. Please do not reply to this email.
                </p>
            </div>
            <div class="footer">
                <p>&copy; 2024 ShadowTalk. All rights reserved.</p>
                <p>Committed to maintaining a safe and respectful community</p>
            </div>
        </div>
    </body>
    </html>
    '''

    msg = MailMessage(
        subject=f'ShadowTalk - Account Suspension Notice',
        recipients=[email],
        html=html_content
    )

    try:
        mail.send(msg)
        print(f"Ban notification email successfully sent to {email}")
        return True
    except Exception as e:
        print(f"Error sending ban notification email to {email}: {str(e)}")
        return False
