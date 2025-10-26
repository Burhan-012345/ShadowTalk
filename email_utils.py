from flask_mail import Mail, Message as MailMessage
from flask import render_template_string
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
    expires_at = datetime.utcnow() + timedelta(minutes=10)
    
    # Save OTP to database
    otp = OTP(email=email, otp=otp_code, expires_at=expires_at)
    db.session.add(otp)
    db.session.commit()
    
    # Create styled email template
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
                background: #8b5cf6;
                color: white;
                font-size: 32px;
                font-weight: bold;
                padding: 20px;
                border-radius: 10px;
                margin: 20px 0;
                letter-spacing: 8px;
            }
            .footer {
                background: #1a1a1a;
                padding: 20px;
                text-align: center;
                color: #888;
                font-size: 12px;
            }
            .button {
                display: inline-block;
                background: #8b5cf6;
                color: white;
                padding: 12px 30px;
                text-decoration: none;
                border-radius: 25px;
                margin: 20px 0;
                font-weight: bold;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>ShadowTalk</h1>
                <p>Your Anonymous Chat Platform</p>
            </div>
            <div class="content">
                <h2>Email Verification</h2>
                <p>Hello! Use the following OTP to verify your email address:</p>
                <div class="otp-code">{{ otp_code }}</div>
                <p>This OTP will expire in 10 minutes.</p>
                <p>If you didn't request this, please ignore this email.</p>
            </div>
            <div class="footer">
                <p>&copy; 2024 ShadowTalk. All rights reserved.</p>
            </div>
        </div>
    </body>
    </html>
    ''', otp_code=otp_code)
    
    # Send email
    msg = MailMessage(
        subject='ShadowTalk - Email Verification OTP',
        recipients=[email],
        html=html_content
    )
    
    try:
        mail.send(msg)
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
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
                padding: 20px;
                border-radius: 10px;
                margin: 20px 0;
            }
            .footer {
                background: #1a1a1a;
                padding: 20px;
                text-align: center;
                color: #888;
                font-size: 12px;
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
                    <p>{{ message }}</p>
                </div>
                <p>Login to ShadowTalk to view more details.</p>
            </div>
            <div class="footer">
                <p>&copy; 2024 ShadowTalk. All rights reserved.</p>
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
        return True
    except Exception as e:
        print(f"Error sending notification email: {e}")
        return False

def send_password_reset_email(email, reset_token):
    reset_url = f"http://localhost:5000/reset-password?token={reset_token}"
    
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
            .reset-link {
                display: inline-block;
                background: #8b5cf6;
                color: white;
                padding: 15px 40px;
                text-decoration: none;
                border-radius: 25px;
                margin: 25px 0;
                font-weight: bold;
                font-size: 16px;
            }
            .footer {
                background: #1a1a1a;
                padding: 20px;
                text-align: center;
                color: #888;
                font-size: 12px;
            }
            .text-link {
                color: #a855f7;
                word-break: break-all;
                margin: 20px 0;
                padding: 10px;
                background: #3c3c3c;
                border-radius: 5px;
                font-size: 14px;
            }
            .instructions {
                margin: 20px 0;
                line-height: 1.6;
            }
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
                <div class="instructions">
                    <p>You requested to reset your password. Click the button below to set a new password:</p>
                </div>
                
                <a href="{{ reset_url }}" class="reset-link">Reset Password</a>
                
                <div class="instructions">
                    <p>Or copy and paste this link in your browser:</p>
                    <div class="text-link">{{ reset_url }}</div>
                    <p>This link will expire in 1 hour.</p>
                    <p>If you didn't request this, please ignore this email.</p>
                </div>
            </div>
            <div class="footer">
                <p>&copy; 2024 ShadowTalk. All rights reserved.</p>
            </div>
        </div>
    </body>
    </html>
    ''', reset_url=reset_url)
    
    msg = MailMessage(
        subject='ShadowTalk - Password Reset',
        recipients=[email],
        html=html_content
    )
    
    try:
        mail.send(msg)
        return True
    except Exception as e:
        print(f"Error sending password reset email: {e}")
        return False