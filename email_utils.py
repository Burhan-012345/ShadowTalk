from flask_mail import Mail, Message as MailMessage
from flask import render_template_string, current_app
import random
import string
from datetime import datetime, timedelta
from models import OTP, db
import time
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

mail = Mail()

def generate_otp():
    """Generate a 6-digit OTP"""
    return ''.join(random.choices(string.digits, k=6))

def test_smtp_connection():
    """Test SMTP connection before sending emails"""
    try:
        from flask import current_app
        with current_app.app_context():
            # Test connection to SMTP server
            server = smtplib.SMTP(current_app.config['MAIL_SERVER'], current_app.config['MAIL_PORT'])
            server.starttls()
            server.login(current_app.config['MAIL_USERNAME'], current_app.config['MAIL_PASSWORD'])
            server.quit()
            logger.info("SMTP connection test successful")
            return True
    except Exception as e:
        logger.error(f"SMTP connection test failed: {str(e)}")
        return False

def send_email_with_retry(email, subject, html_content, plain_text=None, max_retries=3):
    """
    Send email with retry logic and fallback options
    """
    # Generate plain text version if not provided
    if not plain_text:
        # Simple HTML to text conversion
        import re
        plain_text = re.sub('<[^<]+?>', '', html_content)
        plain_text = re.sub('\n+', '\n', plain_text).strip()

    for attempt in range(max_retries):
        try:
            logger.info(f"Attempting to send email to {email} (attempt {attempt + 1}/{max_retries})")
            
            # Create message
            msg = MailMessage(
                subject=subject,
                recipients=[email],
                html=html_content,
                body=plain_text
            )
            
            # Send email
            mail.send(msg)
            logger.info(f"✅ Email successfully sent to {email}")
            return True
            
        except Exception as e:
            logger.warning(f"❌ Attempt {attempt + 1} failed for {email}: {str(e)}")
            
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # Exponential backoff: 1, 2, 4 seconds
                logger.info(f"Waiting {wait_time} seconds before retry...")
                time.sleep(wait_time)
            else:
                logger.error(f"❌ All {max_retries} attempts failed for {email}")
                
                # Try fallback SMTP method
                if attempt_fallback_smtp(email, subject, html_content, plain_text):
                    return True
                
                return False
    
    return False

def attempt_fallback_smtp(email, subject, html_content, plain_text):
    """
    Attempt to send email using direct SMTP as fallback
    """
    try:
        from flask import current_app
        
        logger.info("Attempting fallback SMTP send...")
        
        # Create message
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = current_app.config['MAIL_DEFAULT_SENDER']
        msg['To'] = email
        
        # Attach both plain text and HTML versions
        part1 = MIMEText(plain_text, 'plain')
        part2 = MIMEText(html_content, 'html')
        
        msg.attach(part1)
        msg.attach(part2)
        
        # Send using SMTP
        server = smtplib.SMTP(current_app.config['MAIL_SERVER'], current_app.config['MAIL_PORT'])
        server.starttls()
        server.login(current_app.config['MAIL_USERNAME'], current_app.config['MAIL_PASSWORD'])
        server.send_message(msg)
        server.quit()
        
        logger.info(f"✅ Fallback SMTP email sent successfully to {email}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Fallback SMTP also failed: {str(e)}")
        return False

def send_otp_email(email):
    """
    Send OTP verification email with enhanced styling and reliability
    """
    try:
        # Delete any existing OTP for this email
        OTP.query.filter_by(email=email).delete()

        # Generate new OTP
        otp_code = generate_otp()
        expires_at = datetime.utcnow() + timedelta(minutes=10)

        # Save OTP to database
        otp = OTP(email=email, otp=otp_code, expires_at=expires_at)
        db.session.add(otp)
        db.session.commit()

        logger.info(f"Generated OTP for {email}: {otp_code}")

        # Create enhanced email template
        html_content = f'''
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>ShadowTalk - Email Verification</title>
            <style>
                body {{
                    background: linear-gradient(135deg, #2c2c2c 0%, #1a1a1a 100%);
                    color: #e0e0e0;
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    margin: 0;
                    padding: 0;
                    line-height: 1.6;
                }}
                .container {{
                    max-width: 600px;
                    margin: 0 auto;
                    background: #2c2c2c;
                    border-radius: 20px;
                    overflow: hidden;
                    box-shadow: 0 15px 35px rgba(0,0,0,0.4);
                }}
                .header {{
                    background: linear-gradient(135deg, #8b5cf6 0%, #a855f7 100%);
                    padding: 40px 30px;
                    text-align: center;
                }}
                .header h1 {{
                    color: white;
                    margin: 0;
                    font-size: 32px;
                    font-weight: 700;
                    letter-spacing: 1px;
                }}
                .header p {{
                    color: rgba(255,255,255,0.9);
                    margin: 10px 0 0 0;
                    font-size: 16px;
                }}
                .content {{
                    padding: 50px 40px;
                    text-align: center;
                }}
                .otp-code {{
                    background: linear-gradient(135deg, #8b5cf6 0%, #a855f7 100%);
                    color: white;
                    font-size: 42px;
                    font-weight: 800;
                    padding: 30px;
                    border-radius: 20px;
                    margin: 30px 0;
                    letter-spacing: 15px;
                    text-align: center;
                    box-shadow: 0 10px 25px rgba(139, 92, 246, 0.4);
                    animation: pulse 2s infinite ease-in-out;
                    font-family: 'Courier New', monospace;
                }}
                .info-box {{
                    background: #3c3c3c;
                    padding: 25px;
                    border-radius: 15px;
                    margin: 25px 0;
                    text-align: left;
                    border-left: 5px solid #8b5cf6;
                }}
                .warning {{
                    background: linear-gradient(135deg, #f39c12 0%, #e67e22 100%);
                    color: white;
                    padding: 20px;
                    border-radius: 12px;
                    margin: 25px 0;
                    font-size: 15px;
                    text-align: center;
                }}
                .security-tip {{
                    background: #34495e;
                    color: #bdc3c7;
                    padding: 20px;
                    border-radius: 12px;
                    margin: 20px 0;
                    font-size: 14px;
                    border-left: 5px solid #3498db;
                }}
                .footer {{
                    background: #1a1a1a;
                    padding: 30px 20px;
                    text-align: center;
                    color: #888;
                    font-size: 13px;
                }}
                @keyframes pulse {{
                    0% {{ transform: scale(1); box-shadow: 0 10px 25px rgba(139, 92, 246, 0.4); }}
                    50% {{ transform: scale(1.03); box-shadow: 0 15px 35px rgba(139, 92, 246, 0.6); }}
                    100% {{ transform: scale(1); box-shadow: 0 10px 25px rgba(139, 92, 246, 0.4); }}
                }}
                .step {{
                    display: flex;
                    align-items: center;
                    margin: 15px 0;
                    padding: 15px;
                    background: #4c4c4c;
                    border-radius: 10px;
                }}
                .step-number {{
                    background: #8b5cf6;
                    color: white;
                    width: 30px;
                    height: 30px;
                    border-radius: 50%;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    margin-right: 15px;
                    font-weight: bold;
                    font-size: 16px;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🔒 ShadowTalk</h1>
                    <p>Secure Anonymous Chat Platform</p>
                </div>
                <div class="content">
                    <h2 style="margin: 0 0 20px 0; color: #fff; font-size: 28px;">Email Verification Required</h2>
                    <p style="font-size: 16px; color: #ccc; margin-bottom: 30px;">
                        Hello! To complete your registration and secure your account, please use the following One-Time Password:
                    </p>

                    <div class="otp-code">{otp_code}</div>

                    <div class="warning">
                        <strong style="font-size: 16px;">⚠️ URGENT SECURITY NOTICE</strong><br>
                        This verification code will expire in <strong>10 minutes</strong>.<br>
                        <strong>Never share this code with anyone!</strong>
                    </div>

                    <div class="info-box">
                        <h3 style="color: #8b5cf6; margin-top: 0;">📋 Verification Steps:</h3>
                        <div class="step">
                            <div class="step-number">1</div>
                            <span>Copy the 6-digit code above</span>
                        </div>
                        <div class="step">
                            <div class="step-number">2</div>
                            <span>Return to ShadowTalk verification page</span>
                        </div>
                        <div class="step">
                            <div class="step-number">3</div>
                            <span>Enter the code to complete verification</span>
                        </div>
                    </div>

                    <div class="security-tip">
                        <strong>🔒 IMPORTANT SECURITY INFORMATION:</strong><br>
                        • ShadowTalk staff will NEVER ask for this code<br>
                        • This code is for your eyes only<br>
                        • If you didn't request this, please ignore this email<br>
                        • Keep your account credentials secure
                    </div>

                    <p style="color: #999; font-size: 14px; margin-top: 30px;">
                        Having trouble? The code might be in your spam folder.<br>
                        If issues persist, contact our support team.
                    </p>
                </div>
                <div class="footer">
                    <p style="margin: 0 0 10px 0;">&copy; 2024 ShadowTalk. All rights reserved.</p>
                    <p style="margin: 0; font-size: 12px;">Protecting your privacy and security in digital conversations</p>
                    <p style="margin: 10px 0 0 0; font-size: 11px; color: #666;">
                        This is an automated security message. Please do not reply to this email.
                    </p>
                </div>
            </div>
        </body>
        </html>
        '''

        plain_text = f'''
ShadowTalk - Email Verification

Your verification code is: {otp_code}

This code will expire in 10 minutes. Do not share this code with anyone.

If you didn't request this verification, please ignore this email.

---
ShadowTalk - Secure Anonymous Chat Platform
This is an automated message. Please do not reply.
'''

        # Send email with retry logic
        success = send_email_with_retry(
            email=email,
            subject='ShadowTalk - Email Verification Code (Expires in 10 minutes) 🔒',
            html_content=html_content,
            plain_text=plain_text
        )

        if not success:
            # If email fails, clean up the OTP from database
            OTP.query.filter_by(email=email).delete()
            db.session.commit()
            logger.error(f"Failed to send OTP email to {email} after all attempts")
            return False

        return True

    except Exception as e:
        logger.error(f"Error in send_otp_email for {email}: {str(e)}")
        db.session.rollback()
        return False

def send_password_reset_email(email, reset_token):
    """
    Send password reset email with secure token
    """
    try:
        reset_url = f"https://shadow1.pythonanywhere.com/reset-password?token={reset_token}"
        
        logger.info(f"Sending password reset email to {email}")

        html_content = f'''
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Password Reset - ShadowTalk</title>
            <style>
                body {{
                    background: linear-gradient(135deg, #2c2c2c 0%, #1a1a1a 100%);
                    color: #e0e0e0;
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    margin: 0;
                    padding: 0;
                }}
                .container {{
                    max-width: 600px;
                    margin: 0 auto;
                    background: #2c2c2c;
                    border-radius: 20px;
                    overflow: hidden;
                    box-shadow: 0 15px 35px rgba(0,0,0,0.4);
                }}
                .header {{
                    background: linear-gradient(135deg, #e74c3c 0%, #c0392b 100%);
                    padding: 40px 30px;
                    text-align: center;
                }}
                .header h1 {{
                    color: white;
                    margin: 0;
                    font-size: 32px;
                    font-weight: 700;
                }}
                .content {{
                    padding: 50px 40px;
                    text-align: center;
                }}
                .reset-button {{
                    display: inline-block;
                    background: linear-gradient(135deg, #e74c3c 0%, #c0392b 100%);
                    color: white;
                    padding: 20px 50px;
                    text-decoration: none;
                    border-radius: 30px;
                    margin: 30px 0;
                    font-weight: bold;
                    font-size: 18px;
                    box-shadow: 0 8px 25px rgba(231, 76, 60, 0.4);
                    transition: all 0.3s ease;
                    border: none;
                    cursor: pointer;
                }}
                .reset-button:hover {{
                    transform: translateY(-3px);
                    box-shadow: 0 12px 35px rgba(231, 76, 60, 0.6);
                }}
                .url-box {{
                    background: #3c3c3c;
                    padding: 20px;
                    border-radius: 12px;
                    margin: 25px 0;
                    word-break: break-all;
                    border: 1px solid #4c4c4c;
                }}
                .warning {{
                    background: linear-gradient(135deg, #e74c3c 0%, #c0392b 100%);
                    color: white;
                    padding: 20px;
                    border-radius: 12px;
                    margin: 25px 0;
                    font-size: 15px;
                    text-align: center;
                }}
                .security-info {{
                    background: #34495e;
                    color: #bdc3c7;
                    padding: 25px;
                    border-radius: 12px;
                    margin: 20px 0;
                    font-size: 14px;
                    text-align: left;
                    border-left: 5px solid #3498db;
                }}
                .footer {{
                    background: #1a1a1a;
                    padding: 30px 20px;
                    text-align: center;
                    color: #888;
                    font-size: 13px;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🔐 ShadowTalk</h1>
                    <p style="color: rgba(255,255,255,0.9); margin: 10px 0 0 0;">Password Reset Request</p>
                </div>
                <div class="content">
                    <h2 style="color: #fff; font-size: 28px; margin-bottom: 20px;">Reset Your Password</h2>
                    <p style="font-size: 16px; color: #ccc; line-height: 1.6;">
                        You requested to reset your password for your ShadowTalk account. 
                        Click the button below to create a new secure password.
                    </p>

                    <a href="{reset_url}" class="reset-button">Reset Password Now</a>

                    <p style="color: #ccc; margin: 20px 0;">Or copy and paste this link in your browser:</p>
                    <div class="url-box">
                        <code style="color: #e74c3c; font-size: 14px;">{reset_url}</code>
                    </div>

                    <div class="warning">
                        <strong>🚨 URGENT: Link Expires in 1 Hour</strong><br>
                        For security reasons, this password reset link will expire in 60 minutes.
                    </div>

                    <div class="security-info">
                        <strong>🔒 CRITICAL SECURITY NOTICE:</strong><br><br>
                        • If you didn't request this reset, your account may be compromised<br>
                        • Never share your password or this link with anyone<br>
                        • ShadowTalk will never ask for your password via email<br>
                        • Use a strong, unique password for your account<br>
                        • Enable two-factor authentication for added security
                    </div>

                    <p style="color: #999; font-size: 14px; margin-top: 30px;">
                        Need help? Contact our support team through the ShadowTalk app.
                    </p>
                </div>
                <div class="footer">
                    <p style="margin: 0 0 10px 0;">&copy; 2024 ShadowTalk. All rights reserved.</p>
                    <p style="margin: 0; font-size: 12px;">Protecting your digital identity and conversations</p>
                    <p style="margin: 10px 0 0 0; font-size: 11px; color: #666;">
                        This is an automated security message. Please do not reply.
                    </p>
                </div>
            </div>
        </body>
        </html>
        '''

        plain_text = f'''
ShadowTalk - Password Reset Request

To reset your password, click the following link:
{reset_url}

Or copy and paste the link into your browser.

This link will expire in 1 hour.

If you didn't request this password reset, please ignore this email and ensure your account security.

---
ShadowTalk - Secure Anonymous Chat Platform
This is an automated security message.
'''

        return send_email_with_retry(
            email=email,
            subject='ShadowTalk - Password Reset Request (URGENT: Expires in 1 Hour) 🔐',
            html_content=html_content,
            plain_text=plain_text
        )

    except Exception as e:
        logger.error(f"Error in send_password_reset_email for {email}: {str(e)}")
        return False

def send_notification_email(user_email, title, message):
    """
    Send general notification email
    """
    try:
        html_content = f'''
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Notification - ShadowTalk</title>
            <style>
                body {{
                    background: linear-gradient(135deg, #2c2c2c 0%, #1a1a1a 100%);
                    color: #e0e0e0;
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    margin: 0;
                    padding: 0;
                }}
                .container {{
                    max-width: 600px;
                    margin: 0 auto;
                    background: #2c2c2c;
                    border-radius: 20px;
                    overflow: hidden;
                    box-shadow: 0 15px 35px rgba(0,0,0,0.4);
                }}
                .header {{
                    background: linear-gradient(135deg, #8b5cf6 0%, #a855f7 100%);
                    padding: 40px 30px;
                    text-align: center;
                }}
                .header h1 {{
                    color: white;
                    margin: 0;
                    font-size: 32px;
                    font-weight: 700;
                }}
                .content {{
                    padding: 50px 40px;
                }}
                .notification {{
                    background: #3c3c3c;
                    padding: 30px;
                    border-radius: 15px;
                    margin: 25px 0;
                    border-left: 5px solid #8b5cf6;
                }}
                .action-button {{
                    display: inline-block;
                    background: linear-gradient(135deg, #8b5cf6 0%, #a855f7 100%);
                    color: white;
                    padding: 15px 35px;
                    text-decoration: none;
                    border-radius: 25px;
                    margin: 20px 0;
                    font-weight: bold;
                    font-size: 16px;
                    transition: all 0.3s ease;
                }}
                .footer {{
                    background: #1a1a1a;
                    padding: 30px 20px;
                    text-align: center;
                    color: #888;
                    font-size: 13px;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>📢 ShadowTalk</h1>
                    <p style="color: rgba(255,255,255,0.9); margin: 10px 0 0 0;">New Notification</p>
                </div>
                <div class="content">
                    <h2 style="color: #fff; font-size: 26px; margin-bottom: 10px;">{title}</h2>
                    <div class="notification">
                        <p style="margin: 0; font-size: 16px; line-height: 1.6; color: #e0e0e0;">{message}</p>
                    </div>
                    <div style="text-align: center;">
                        <a href="https://shadow01.pythonanywhere.com/dashboard" class="action-button">
                            View in Dashboard
                        </a>
                    </div>
                    <p style="color: #999; font-size: 14px; text-align: center; margin-top: 20px;">
                        Login to ShadowTalk to view more details and manage your notifications.
                    </p>
                </div>
                <div class="footer">
                    <p style="margin: 0 0 10px 0;">&copy; 2024 ShadowTalk. All rights reserved.</p>
                    <p style="margin: 0; font-size: 12px;">Stay connected, stay anonymous</p>
                </div>
            </div>
        </body>
        </html>
        '''

        plain_text = f'''
ShadowTalk Notification

{title}

{message}

Login to your dashboard to view more details: https://shadow01.pythonanywhere.com/dashboard

---
ShadowTalk - Secure Anonymous Chat Platform
'''

        return send_email_with_retry(
            email=user_email,
            subject=f'ShadowTalk - {title}',
            html_content=html_content,
            plain_text=plain_text
        )

    except Exception as e:
        logger.error(f"Error in send_notification_email for {user_email}: {str(e)}")
        return False

def send_ban_notification_email(email, ban_reason, ban_duration, ban_expires_at=None):
    """
    Send ban notification email to user
    """
    try:
        if ban_duration == 'permanent':
            duration_display = "Permanent"
            duration_note = "This is a permanent ban from the ShadowTalk platform."
        else:
            duration_display = f"{ban_duration} days"
            if ban_expires_at:
                expires_formatted = ban_expires_at.strftime("%B %d, %Y at %H:%M UTC")
                duration_note = f"Your ban will expire on {expires_formatted}."
            else:
                duration_note = f"Your ban will expire after {ban_duration} days."

        html_content = f'''
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Account Suspension - ShadowTalk</title>
            <style>
                body {{
                    background: linear-gradient(135deg, #2c2c2c 0%, #1a1a1a 100%);
                    color: #e0e0e0;
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    margin: 0;
                    padding: 0;
                }}
                .container {{
                    max-width: 600px;
                    margin: 0 auto;
                    background: #2c2c2c;
                    border-radius: 20px;
                    overflow: hidden;
                    box-shadow: 0 15px 35px rgba(0,0,0,0.4);
                }}
                .header {{
                    background: linear-gradient(135deg, #e74c3c 0%, #c0392b 100%);
                    padding: 40px 30px;
                    text-align: center;
                }}
                .content {{
                    padding: 50px 40px;
                }}
                .ban-notice {{
                    background: linear-gradient(135deg, #e74c3c 0%, #c0392b 100%);
                    color: white;
                    font-size: 26px;
                    font-weight: bold;
                    padding: 25px;
                    border-radius: 15px;
                    margin: 25px 0;
                    text-align: center;
                }}
                .details-box {{
                    background: #3c3c3c;
                    padding: 25px;
                    border-radius: 12px;
                    margin: 20px 0;
                    border-left: 5px solid #e74c3c;
                }}
                .appeal-section {{
                    background: #34495e;
                    padding: 25px;
                    border-radius: 12px;
                    margin: 25px 0;
                    border-left: 5px solid #3498db;
                }}
                .footer {{
                    background: #1a1a1a;
                    padding: 30px 20px;
                    text-align: center;
                    color: #888;
                    font-size: 13px;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🚫 ShadowTalk</h1>
                    <p style="color: rgba(255,255,255,0.9); margin: 10px 0 0 0;">Account Status Notification</p>
                </div>
                <div class="content">
                    <div class="ban-notice">
                        ⚠️ ACCOUNT SUSPENDED
                    </div>

                    <p style="font-size: 16px; color: #ccc; line-height: 1.6;">
                        We regret to inform you that your ShadowTalk account has been suspended due to a violation of our terms of service.
                    </p>

                    <div class="details-box">
                        <h3 style="color: #e74c3c; margin-top: 0;">Suspension Details:</h3>
                        <p><strong>Reason:</strong> {ban_reason}</p>
                        <p><strong>Duration:</strong> {duration_display}</p>
                        <p><strong>Effective Date:</strong> {datetime.utcnow().strftime("%B %d, %Y at %H:%M UTC")}</p>
                    </div>

                    <div class="appeal-section">
                        <h3 style="color: #3498db;">Appeal Process</h3>
                        <p>If you believe this suspension was made in error, you may contact our support team for review.</p>
                        <p><strong>Email:</strong> support@shadowtalk.com</p>
                    </div>

                    <p style="color: #999; font-size: 14px;">
                        Please review our Terms of Service and Community Guidelines for more information.
                    </p>
                </div>
                <div class="footer">
                    <p style="margin: 0 0 10px 0;">&copy; 2024 ShadowTalk. All rights reserved.</p>
                    <p style="margin: 0; font-size: 12px;">Committed to maintaining a safe and respectful community</p>
                </div>
            </div>
        </body>
        </html>
        '''

        plain_text = f'''
ShadowTalk - Account Suspension Notice

Your account has been suspended.

Reason: {ban_reason}
Duration: {duration_display}
Effective: {datetime.utcnow().strftime("%B %d, %Y at %H:%M UTC")}

{duration_note}

If you believe this was an error, you may appeal by contacting:
support@shadowtalk.com

---
ShadowTalk - Secure Anonymous Chat Platform
'''

        return send_email_with_retry(
            email=email,
            subject='ShadowTalk - Account Suspension Notice',
            html_content=html_content,
            plain_text=plain_text
        )

    except Exception as e:
        logger.error(f"Error in send_ban_notification_email for {email}: {str(e)}")
        return False

def resend_otp_email(email):
    """
    Resend OTP email with a new code
    """
    logger.info(f"Resending OTP email to {email}")
    return send_otp_email(email)

def send_security_alert_email(email, alert_type, details):
    """
    Send security alert emails for suspicious activities
    """
    try:
        subject_map = {
            'login_attempt': 'New Login Attempt Detected',
            'password_changed': 'Password Successfully Changed',
            'device_added': 'New Device Connected',
            'suspicious_activity': 'Suspicious Activity Detected'
        }

        subject = subject_map.get(alert_type, 'Security Notice')

        html_content = f'''
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{
                    background: linear-gradient(135deg, #2c2c2c 0%, #1a1a1a 100%);
                    color: #e0e0e0;
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    margin: 0;
                    padding: 0;
                }}
                .container {{
                    max-width: 600px;
                    margin: 0 auto;
                    background: #2c2c2c;
                    border-radius: 20px;
                    overflow: hidden;
                    box-shadow: 0 15px 35px rgba(0,0,0,0.4);
                }}
                .header {{
                    background: linear-gradient(135deg, #e74c3c 0%, #c0392b 100%);
                    padding: 40px 30px;
                    text-align: center;
                }}
                .content {{
                    padding: 50px 40px;
                }}
                .alert-box {{
                    background: linear-gradient(135deg, #e74c3c 0%, #c0392b 100%);
                    color: white;
                    padding: 25px;
                    border-radius: 15px;
                    margin: 25px 0;
                    text-align: center;
                    font-size: 20px;
                    font-weight: bold;
                }}
                .footer {{
                    background: #1a1a1a;
                    padding: 30px 20px;
                    text-align: center;
                    color: #888;
                    font-size: 13px;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🔒 ShadowTalk</h1>
                    <p style="color: rgba(255,255,255,0.9);">Security Alert</p>
                </div>
                <div class="content">
                    <div class="alert-box">
                        ⚠️ SECURITY ALERT: {subject}
                    </div>
                    <p><strong>Details:</strong> {details}</p>
                    <p><strong>Time:</strong> {datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")}</p>
                    <p><strong>Account:</strong> {email}</p>
                    <p>If this wasn't you, please secure your account immediately.</p>
                </div>
                <div class="footer">
                    <p>&copy; 2024 ShadowTalk. All rights reserved.</p>
                    <p>Protecting your digital identity</p>
                </div>
            </div>
        </body>
        </html>
        '''

        plain_text = f'''
ShadowTalk Security Alert

{alert_type}

Details: {details}
Time: {datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")}
Account: {email}

If this wasn't you, please secure your account immediately.

---
ShadowTalk - Secure Anonymous Chat Platform
'''

        return send_email_with_retry(
            email=email,
            subject=f'ShadowTalk Security Alert: {subject}',
            html_content=html_content,
            plain_text=plain_text
        )

    except Exception as e:
        logger.error(f"Error in send_security_alert_email for {email}: {str(e)}")
        return False

# Initialize email service
def init_email_service(app):
    """
    Initialize email service and test connection
    """
    try:
        mail.init_app(app)
        logger.info("Email service initialized successfully")
        
        # Test SMTP connection
        if test_smtp_connection():
            logger.info("✅ Email service is ready")
            return True
        else:
            logger.warning("⚠️ Email service connection test failed")
            return False
            
    except Exception as e:
        logger.error(f"❌ Failed to initialize email service: {str(e)}")
        return False
