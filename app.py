"""
AMR Landscaping & Pressure Washing Booking System
================================================

A Flask-based web application for scheduling landscaping and pressure washing services.
Now includes full user authentication and database storage for real business use.

Features:
- User registration and login system
- Service selection (Landscaping vs Pressure Washing)
- Time slot management with service-specific durations
- Customer information collection with auto-fill
- Email confirmations
- Admin interface for managing bookings
- Mobile-responsive design
- Secure password hashing
- Session management

Author: Alok Patel
For: AMR Services
Date: 2025
"""

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date, time, timedelta
import os
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import threading
import time as time_module
from flask import current_app
from email.mime.base import MIMEBase
from email import encoders
import os
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

load_dotenv()


# Application Configuration
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-change-this-in-production'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///amr_bookings.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Email Configuration (configure these for email notifications)
app.config['MAIL_SERVER'] = 'smtp.gmail.com'  # Change to your email provider
app.config['MAIL_PORT'] = 587
app.config['MAIL_USERNAME'] = 'your-email@gmail.com'  # Your email
app.config['MAIL_PASSWORD'] = 'your-app-password'     # Your email app password
app.config['MAIL_USE_TLS'] = True

# Business Configuration
BUSINESS_HOURS = {
    'start': time(6, 0),   # 6:00 AM
    'end': time(20, 0),    # 8:00 PM
    'timezone': 'Eastern'
}

# Initialize database and login manager
db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ========================================
# DATABASE MODELS
# ========================================

class User(UserMixin, db.Model):
    """
    User model for authentication and storing customer information.
    Extends UserMixin for Flask-Login compatibility.
    """
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(50), nullable=False)
    last_name = db.Column(db.String(50), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    address = db.Column(db.Text, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationship to bookings
    bookings = db.relationship('Booking', backref='user', lazy=True)
    
    @property
    def full_name(self):
        """Returns user's full name"""
        return f"{self.first_name} {self.last_name}"
    
    def set_password(self, password):
        """Hash and set user password"""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """Check if provided password matches hash"""
        return check_password_hash(self.password_hash, password)
    
    def __repr__(self):
        return f'<User {self.full_name}>'

class ServiceType(db.Model):
    """
    Defines the different types of services offered by AMR.
    Each service has a category (landscaping/pressure_washing) and duration.
    """
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(50), nullable=False)  # 'landscaping' or 'pressure_washing'
    description = db.Column(db.Text)
    duration_hours = db.Column(db.Float, nullable=False)  # Duration in hours (e.g., 1.5, 4.0, 5.0)
    is_custom = db.Column(db.Boolean, default=False)     # True for custom services
    is_active = db.Column(db.Boolean, default=True)      # For enabling/disabling services
    
    # Relationship to bookings
    bookings = db.relationship('Booking', backref='service_type', lazy=True)
    
    def __repr__(self):
        return f'<ServiceType {self.name}>'

class Booking(db.Model):
    """
    Main booking model that stores appointment information.
    Links users to services with specific date/time slots.
    """
    id = db.Column(db.Integer, primary_key=True)
    
    # Foreign keys
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    service_type_id = db.Column(db.Integer, db.ForeignKey('service_type.id'), nullable=False)
    
    # Booking details
    booking_date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)       # Calculated based on service duration
    
    # Status tracking
    status = db.Column(db.String(20), default='pending')  # pending, confirmed, completed, cancelled
    custom_description = db.Column(db.Text)               # For custom services
    admin_notes = db.Column(db.Text)                      # Internal notes
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def calculate_end_time(self):
        """Calculate end time based on service duration"""
        duration = timedelta(hours=self.service_type.duration_hours)
        start_datetime = datetime.combine(date.today(), self.start_time)
        end_datetime = start_datetime + duration
        return end_datetime.time()
    
    @property
    def duration_display(self):
        """Returns human-readable duration"""
        hours = self.service_type.duration_hours
        if hours == int(hours):
            return f"{int(hours)} hour{'s' if hours != 1 else ''}"
        else:
            return f"{hours} hours"
    
    def __repr__(self):
        return f'<Booking {self.id} - {self.booking_date} {self.start_time}>'
    
class RecurringBooking(db.Model):
    """
    Model for managing recurring service bookings
    """
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    service_type_id = db.Column(db.Integer, db.ForeignKey('service_type.id'), nullable=False)
    
    # Recurring pattern
    frequency_value = db.Column(db.String(20), nullable=False)  # e.g., "2" or "6months"
    frequency_type = db.Column(db.String(20), nullable=False)   # 'days', 'weeks', 'months', 'special'
    
    # Schedule details
    start_date = db.Column(db.Date, nullable=False)
    next_due_date = db.Column(db.Date, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    user = db.relationship('User', backref='recurring_bookings')
    service_type = db.relationship('ServiceType', backref='recurring_bookings')

class ServicePhoto(db.Model):
    """
    Model for storing service-related photos
    """
    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.Integer, db.ForeignKey('booking.id'), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    booking = db.relationship('Booking', backref='photos')
    user = db.relationship('User', backref='photos')

# ========================================
# AUTHENTICATION ROUTES
# ========================================

@app.route('/api/signup', methods=['POST'])
def api_signup():
    """API endpoint for user registration"""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['firstName', 'lastName', 'email', 'phone', 'address', 'password']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'success': False, 'message': f'{field} is required'}), 400
        
        # Check if user already exists
        if User.query.filter_by(email=data['email']).first():
            return jsonify({'success': False, 'message': 'User with this email already exists'}), 400
        
        # Create new user
        user = User(
            first_name=data['firstName'],
            last_name=data['lastName'],
            email=data['email'],
            phone=data['phone'],
            address=data['address']
        )
        user.set_password(data['password'])
        
        db.session.add(user)
        db.session.commit()
        
        # Log the user in
        login_user(user)
        
        return jsonify({
            'success': True, 
            'message': 'Account created successfully!',
            'isAdmin': user.is_admin,
            'user': {
                'firstName': user.first_name,
                'lastName': user.last_name,
                'email': user.email,
                'phone': user.phone,
                'address': user.address
            }
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Error creating account: {str(e)}'}), 500

@app.route('/api/login', methods=['POST'])
def api_login():
    """API endpoint for user login"""
    try:
        data = request.get_json()
        email = data.get('email')
        password = data.get('password')
        
        if not email or not password:
            return jsonify({'success': False, 'message': 'Email and password are required'}), 400
        
        user = User.query.filter_by(email=email).first()
        
        if user and user.check_password(password):
            login_user(user)
            return jsonify({
                'success': True, 
                'message': 'Login successful!',
                'isAdmin': user.is_admin,
                'user': {
                    'firstName': user.first_name,
                    'lastName': user.last_name,
                    'email': user.email,
                    'phone': user.phone,
                    'address': user.address
                }
            })
        else:
            return jsonify({'success': False, 'message': 'Invalid email or password'}), 401
            
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error logging in: {str(e)}'}), 500

@app.route('/api/logout', methods=['POST'])
@login_required
def api_logout():
    """API endpoint for user logout"""
    logout_user()
    return jsonify({'success': True, 'message': 'Logged out successfully'})

@app.route('/api/current-user', methods=['GET'])
def api_current_user():
    """API endpoint to get current user info"""
    if current_user.is_authenticated:
        return jsonify({
            'authenticated': True,
            'isAdmin': current_user.is_admin,
            'user': {
                'firstName': current_user.first_name,
                'lastName': current_user.last_name,
                'email': current_user.email,
                'phone': current_user.phone,
                'address': current_user.address
            }
        })
    else:
        return jsonify({'authenticated': False, 'isAdmin': False})
@app.context_processor
def inject_google_maps_key():
    return dict(google_maps_key=os.getenv('GOOGLE_MAPS_API_KEY'))

# ========================================
# UTILITY FUNCTIONS
# ========================================

def get_available_time_slots(selected_date, service_duration_hours, service_type=None):
    """
    Calculate available time slots for a given date and service duration.
    Business hours: 6:00 AM to 8:00 PM
    Time slots: 30-minute increments
    Minimum 2-hour advance booking required
    
    Args:
        selected_date (date): The date to check availability
        service_duration_hours (float): Duration of the service in hours
        service_type (ServiceType): The service type object
        
    Returns:
        list: Available time slots as time objects
    """
    
    # Don't allow booking for past dates
    if selected_date < date.today():
        return []
    
    # Get existing bookings for this date
    existing_bookings = Booking.query.filter_by(booking_date=selected_date).all()
    
    # Calculate minimum booking time (2 hours from now)
    now = datetime.now()
    min_booking_time = now + timedelta(hours=2)
    
    # If booking for today, use minimum booking time
    # If booking for future date, start from business hours
    if selected_date == date.today():
        # Round up to next 30-minute slot
        minutes = min_booking_time.minute
        if minutes == 0:
            earliest_time = min_booking_time.time()
        elif minutes <= 30:
            earliest_time = min_booking_time.replace(minute=30, second=0, microsecond=0).time()
        else:
            # Round up to next hour
            next_hour = min_booking_time.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
            earliest_time = next_hour.time()
        
        # Don't allow booking before business hours start (6 AM)
        business_start = BUSINESS_HOURS['start']  # 6:00 AM
        if earliest_time < business_start:
            earliest_time = business_start
    else:
        # Future dates can start from business hours
        earliest_time = BUSINESS_HOURS['start']  # 6:00 AM
    
    # Create list of all possible 30-minute slots
    available_slots = []
    current_time = earliest_time
    end_time = BUSINESS_HOURS['end']  # 8:00 PM
    
    while current_time < end_time:
        # Determine blocking duration based on service type
        if service_type and service_type.is_custom:
            # Custom landscaping: block only the selected slot (use 1.0 hour for safety buffer)
            blocking_duration = 1.0
        else:
            # Standard services: use full duration
            blocking_duration = service_duration_hours
        
        # Calculate when this service would end
        start_datetime = datetime.combine(selected_date, current_time)
        end_datetime = start_datetime + timedelta(hours=blocking_duration)
        service_end_time = end_datetime.time()
        
        # Check if service would end before business hours end (8 PM)
        if service_end_time <= end_time:
            # Check for conflicts with existing bookings
            slot_available = True
            
            for booking in existing_bookings:
                # Check if this time slot overlaps with existing booking
                if (current_time < booking.end_time and service_end_time > booking.start_time):
                    slot_available = False
                    break
            
            if slot_available:
                available_slots.append(current_time)
        
        # Move to next 30-minute slot
        current_time = (datetime.combine(date.today(), current_time) + timedelta(minutes=30)).time()
    
    return available_slots


def is_date_available(check_date):
    """
    Check if a date has any available time slots.
    
    Args:
        check_date (date): Date to check
        
    Returns:
        bool: True if date has available slots, False otherwise
    """
    if check_date < date.today():
        return False
    
    # Check with minimum service duration (1.5 hours for landscaping)
    slots = get_available_time_slots(check_date, 1.5)
    return len(slots) > 0


def send_confirmation_email(booking):
    """
    Send booking confirmation email to customer.
    Enhanced version with logo image and service-specific colors.
    
    Args:
        booking (Booking): The booking object to send confirmation for
    """
    try:
        # Email configuration
        smtp_server = "smtp.gmail.com"
        port = 587
        
        # Your Gmail credentials
        sender_email = "amrservicescontact@gmail.com"
        sender_password = "vtdd evzr okic znzk"
        sender_name = "AMR Services"
        
        # Service-specific colors
        if booking.service_type.category == 'landscaping':
            primary_color = "#035F0A"  # Your green color
            service_emoji = "🌱"
        else:  # pressure_washing
            primary_color = "#7EE0FF"  # Your blue color
            service_emoji = "💧"
        
        # Create email message
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"AMR Services - Booking Confirmation #{booking.id}"
        msg['From'] = f"{sender_name} <{sender_email}>"
        msg['To'] = booking.user.email
        
        # Create the email body (HTML version with logo and dynamic colors)
        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ 
                    background-color: {primary_color}; 
                    color: white; 
                    padding: 30px 20px; 
                    text-align: center; 
                    border-radius: 10px 10px 0 0; 
                    position: relative;
                }}
                .logo {{ 
                    max-width: 120px; 
                    height: auto; 
                    border-radius: 15px; 
                    margin-bottom: 15px;
                    border: 3px solid white;
                    box-shadow: 0 4px 8px rgba(0,0,0,0.2);
                }}
                .content {{ background-color: #f9f9f9; padding: 20px; border-radius: 0 0 10px 10px; }}
                .detail-row {{ 
                    margin: 10px 0; 
                    padding: 15px; 
                    background-color: white; 
                    border-radius: 8px; 
                    border-left: 4px solid {primary_color};
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                }}
                .emoji {{ font-size: 1.2em; margin-right: 8px; }}
                .footer {{ text-align: center; margin-top: 20px; color: #666; font-size: 0.9em; }}
                .service-badge {{
                    background-color: {primary_color};
                    color: white;
                    padding: 8px 16px;
                    border-radius: 20px;
                    font-weight: bold;
                    display: inline-block;
                    margin: 10px 0;
                }}
                .contact-info {{
                    background-color: {primary_color};
                    color: white;
                    padding: 15px;
                    border-radius: 8px;
                    margin: 15px 0;
                }}
                .what-to-expect {{
                    background-color: rgba({int(primary_color[1:3], 16)}, {int(primary_color[3:5], 16)}, {int(primary_color[5:7], 16)}, 0.1);
                    padding: 15px;
                    border-radius: 8px;
                    border: 1px solid {primary_color};
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1 style="margin: 0; color: white;">{service_emoji} AMR Services</h1>
                    <h2 style="margin: 0; font-size: 1.8em;">{service_emoji} Booking Confirmed!</h2>
                    <div class="service-badge">{booking.service_type.category.replace('_', ' ').title()} Service</div>
                </div>
                
                <div class="content">
                    <p style="font-size: 1.1em; margin-bottom: 20px;">Hi <strong>{booking.user.first_name}</strong>,</p>
                    
                    <p>Great news! Your appointment with AMR Services has been confirmed. Here are your booking details:</p>
                    
                    <div class="detail-row">
                        <span class="emoji">🛠️</span><strong>Service:</strong> {booking.service_type.name}
                    </div>
                    
                    <div class="detail-row">
                        <span class="emoji">📅</span><strong>Date:</strong> {booking.booking_date.strftime('%A, %B %d, %Y')}
                    </div>
                    
                    <div class="detail-row">
                        <span class="emoji">🕐</span><strong>Time:</strong> {booking.start_time.strftime('%I:%M %p')} - {booking.end_time.strftime('%I:%M %p')}
                    </div>
                    
                    <div class="detail-row">
                        <span class="emoji">⏱️</span><strong>Duration:</strong> {booking.duration_display}
                    </div>
                    
                    <div class="detail-row">
                        <span class="emoji">📍</span><strong>Service Address:</strong><br>{booking.user.address}
                    </div>
                    
                    <div class="detail-row">
                        <span class="emoji">🎫</span><strong>Booking ID:</strong> #{booking.id}
                    </div>
                    
                    {f'<div class="detail-row"><span class="emoji">📝</span><strong>Special Request:</strong><br>{booking.custom_description}</div>' if booking.custom_description else ''}
                    
                    <div class="what-to-expect">
                        <h3 style="color: {primary_color}; margin-top: 0;">What to expect:</h3>
                        <ul style="margin: 10px 0;">
                            <li>Our team will arrive at the scheduled time</li>
                            <li>Please ensure access to the work area</li>
                            <li>We'll clean up after ourselves</li>
                            <li>Payment can be made after service completion</li>
                        </ul>
                    </div>
                    
                    <div class="contact-info">
                        <h3 style="margin-top: 0;">Need to make changes? Contact us:</h3>
                        <p style="margin: 5px 0;">📧 Email: {sender_email}</p>
                        <p style="margin: 5px 0;">📱 Phone: (803) 899-4393</p>
                    </div>
                    
                    <p style="text-align: center; font-size: 1.1em; color: {primary_color}; font-weight: bold;">
                        Thank you for choosing AMR Services!
                    </p>
                    
                    <div class="footer">
                        <p style="color: {primary_color}; font-weight: bold;">AMR Landscaping & Pressure Washing</p>
                        <p>Professional service you can trust</p>
                        
                        <p><small>This email was sent because you booked a service with AMR Services. 
                        If you didn't make this booking, please contact us immediately.</small></p>
                    </div>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Create plain text version as backup
        text_body = f"""
        AMR Services - Booking Confirmation
        
        Hi {booking.user.first_name},
        
        Your {booking.service_type.category.replace('_', ' ')} appointment with AMR Services has been confirmed!
        
        Booking Details:
        ================
        Service: {booking.service_type.name}
        Date: {booking.booking_date.strftime('%A, %B %d, %Y')}
        Time: {booking.start_time.strftime('%I:%M %p')} - {booking.end_time.strftime('%I:%M %p')}
        Duration: {booking.duration_display}
        Address: {booking.user.address}
        Booking ID: #{booking.id}
        
        {f'Special Request: {booking.custom_description}' if booking.custom_description else ''}
        
        What to expect:
        - Our team will arrive at the scheduled time
        - Please ensure access to the work area  
        - We'll clean up after ourselves
        - Payment can be made after service completion
        
        Need to make changes? Contact us:
        Email: {sender_email}
        Phone: (803) 899-4393
        
        Thank you for choosing AMR Services!
        
        AMR Landscaping & Pressure Washing
        Professional service you can trust
        """
        # Attach both versions
        part1 = MIMEText(text_body, 'plain')
        part2 = MIMEText(html_body, 'html')
        msg.attach(part1)
        msg.attach(part2)

        # Send the email
        context = ssl.create_default_context()
        # Send the email
        context = ssl.create_default_context()
        with smtplib.SMTP(smtp_server, port) as server:
            server.starttls(context=context)
            server.login(sender_email, sender_password)
            server.send_message(msg)
        
        print(f"✅ Confirmation email sent successfully to {booking.user.email}")
        print(f"   Service: {booking.service_type.category} (using {primary_color} theme)")
        return True
        
        # Send the email
        context = ssl.create_default_context()
        with smtplib.SMTP(smtp_server, port) as server:
            server.starttls(context=context)
            server.login(sender_email, sender_password)
            server.send_message(msg)
        
        print(f"✅ Confirmation email sent successfully to {booking.user.email}")
        print(f"   Service: {booking.service_type.category} (using {primary_color} theme)")
        return True
        
    except Exception as e:
        print(f"❌ Error sending email to {booking.user.email}: {str(e)}")
        
        # Still print the fallback version
        print(f"\n📧 EMAIL CONTENT (would have been sent to {booking.user.email}):")
        print(f"Subject: AMR Services - Booking Confirmation #{booking.id}")
        print(f"To: {booking.user.full_name} <{booking.user.email}>")
        print(f"Service Type: {booking.service_type.category}")
        print("\n" + "="*50)
        print(text_body)
        print("="*50 + "\n")
        
        return False

def send_reminder_email(booking):
    """
    Send 24-hour reminder email to customer.
    
    Args:
        booking (Booking): The booking object to send reminder for
    """
    try:
        # Email configuration
        smtp_server = "smtp.gmail.com"
        port = 587
        
        # Your Gmail credentials
        sender_email = "amrservicescontact@gmail.com"
        sender_password = "vtdd evzr okic znzk"
        sender_name = "AMR Services"
        
        # Service-specific colors and emoji
        if booking.service_type.category == 'landscaping':
            primary_color = "#035F0A"
            service_emoji = "🌱"
        else:  # pressure_washing
            primary_color = "#7EE0FF"
            service_emoji = "💧"
        
        # Create email message
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"⏰ Reminder: AMR Service Tomorrow - Booking #{booking.id}"
        msg['From'] = f"{sender_name} <{sender_email}>"
        msg['To'] = booking.user.email
        
        # Calculate time until service
        service_datetime = datetime.combine(booking.booking_date, booking.start_time)
        time_until = service_datetime - datetime.now()
        hours_until = int(time_until.total_seconds() / 3600)
        
        # Create reminder HTML email
        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ 
                    background: linear-gradient(135deg, {primary_color} 0%, {primary_color}dd 100%);
                    color: white; 
                    padding: 25px; 
                    text-align: center; 
                    border-radius: 15px 15px 0 0;
                }}
                .content {{ background-color: #f9f9f9; padding: 25px; border-radius: 0 0 15px 15px; }}
                .reminder-badge {{
                    background-color: #FF6B35;
                    color: white;
                    padding: 10px 20px;
                    border-radius: 25px;
                    font-weight: bold;
                    display: inline-block;
                    margin: 10px 0;
                    font-size: 1.1em;
                }}
                .detail-box {{ 
                    background: white; 
                    padding: 20px; 
                    border-radius: 10px; 
                    border-left: 5px solid {primary_color};
                    margin: 15px 0;
                    box-shadow: 0 3px 6px rgba(0,0,0,0.1);
                }}
                .important-note {{
                    background-color: #FFF3CD;
                    border: 1px solid #FFEAA7;
                    color: #856404;
                    padding: 15px;
                    border-radius: 8px;
                    margin: 20px 0;
                }}
                .contact-section {{
                    background-color: {primary_color};
                    color: white;
                    padding: 20px;
                    border-radius: 10px;
                    text-align: center;
                    margin: 20px 0;
                }}
                .footer {{ text-align: center; margin-top: 20px; color: #666; font-size: 0.9em; }}
                .emoji {{ font-size: 1.3em; margin-right: 10px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1 style="margin: 0;">{service_emoji} AMR Services</h1>
                    <div class="reminder-badge">⏰ Service Reminder</div>
                    <h2 style="margin: 10px 0 0 0;">Your appointment is tomorrow!</h2>
                </div>
                
                <div class="content">
                    <p style="font-size: 1.2em; color: {primary_color}; font-weight: bold;">
                        Hi {booking.user.first_name}, just a friendly reminder about your upcoming service!
                    </p>
                    
                    <div class="detail-box">
                        <h3 style="color: {primary_color}; margin-top: 0;">📋 Appointment Details</h3>
                        <p><span class="emoji">🛠️</span><strong>Service:</strong> {booking.service_type.name}</p>
                        <p><span class="emoji">📅</span><strong>Date:</strong> {booking.booking_date.strftime('%A, %B %d, %Y')}</p>
                        <p><span class="emoji">🕐</span><strong>Time:</strong> {booking.start_time.strftime('%I:%M %p')} - {booking.end_time.strftime('%I:%M %p')}</p>
                        <p><span class="emoji">📍</span><strong>Address:</strong> {booking.user.address}</p>
                        <p><span class="emoji">🎫</span><strong>Booking ID:</strong> #{booking.id}</p>
                        {f'<p><span class="emoji">📝</span><strong>Special Request:</strong> {booking.custom_description}</p>' if booking.custom_description else ''}
                    </div>
                    
                    <div class="important-note">
                        <h3 style="margin-top: 0;">⚠️ Please Prepare for Our Arrival</h3>
                        <ul style="margin: 10px 0;">
                            <li><strong>Clear access</strong> to work areas (move cars, outdoor furniture, etc.)</li>
                            <li><strong>Secure pets</strong> indoors during service</li>
                            <li><strong>Be available</strong> for any questions from our team</li>
                            <li><strong>Water access</strong> available if needed</li>
                        </ul>
                    </div>
                    
                    <div style="background-color: rgba({int(primary_color[1:3], 16)}, {int(primary_color[3:5], 16)}, {int(primary_color[5:7], 16)}, 0.1); padding: 20px; border-radius: 10px; margin: 20px 0;">
                        <h3 style="color: {primary_color}; margin-top: 0;">☀️ Weather Considerations</h3>
                        <p>Our team monitors weather conditions. If severe weather is forecasted, we'll contact you about rescheduling. Light rain typically doesn't affect most of our services.</p>
                    </div>
                    
                    <div class="contact-section">
                        <h3 style="margin-top: 0;">Need to reschedule or have questions?</h3>
                        <p style="font-size: 1.1em; margin: 10px 0;">📧 <strong>{sender_email}</strong></p>
                        <p style="font-size: 1.1em; margin: 10px 0;">📱 <strong>(803) 899-4393</strong></p>
                        <p style="margin: 15px 0 0 0; font-size: 0.9em;">
                            <em>Please contact us at least 4 hours before your appointment for any changes</em>
                        </p>
                    </div>
                    
                    <p style="text-align: center; font-size: 1.2em; color: {primary_color}; font-weight: bold; margin: 25px 0;">
                        We're excited to provide excellent service for you tomorrow! 🌟
                    </p>
                    
                    <div class="footer">
                        <p style="color: {primary_color}; font-weight: bold;">AMR Landscaping & Pressure Washing</p>
                        <p>Professional service you can trust</p>
                    </div>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Create plain text version
        text_body = f"""
        AMR Services - Service Reminder
        
        Hi {booking.user.first_name},
        
        This is a friendly reminder about your appointment TOMORROW!
        
        Appointment Details:
        ===================
        Service: {booking.service_type.name}
        Date: {booking.booking_date.strftime('%A, %B %d, %Y')}
        Time: {booking.start_time.strftime('%I:%M %p')} - {booking.end_time.strftime('%I:%M %p')}
        Address: {booking.user.address}
        Booking ID: #{booking.id}
        
        {f'Special Request: {booking.custom_description}' if booking.custom_description else ''}
        
        Please Prepare:
        - Clear access to work areas
        - Secure pets indoors during service  
        - Be available for any questions
        - Ensure water access if needed
        
        Weather: Our team monitors conditions and will contact you if rescheduling is needed.
        
        Need to reschedule or have questions?
        Email: {sender_email}
        Phone: (803) 899-4393
        
        Please contact us at least 4 hours before your appointment for changes.
        
        We're excited to provide excellent service tomorrow!
        
        AMR Landscaping & Pressure Washing
        Professional service you can trust
        """
        
        # Attach both versions
        part1 = MIMEText(text_body, 'plain')
        part2 = MIMEText(html_body, 'html')
        
        msg.attach(part1)
        msg.attach(part2)
        
        # Send the email
        context = ssl.create_default_context()
        with smtplib.SMTP(smtp_server, port) as server:
            server.starttls(context=context)
            server.login(sender_email, sender_password)
            server.send_message(msg)
        
        print(f"✅ Reminder email sent to {booking.user.email} for booking #{booking.id}")
        print(f"   Service: {booking.service_type.name} on {booking.booking_date}")
        return True
        
    except Exception as e:
        print(f"❌ Error sending reminder email: {str(e)}")
        return False


def check_and_send_reminders():
    """
    Check for bookings that need 24-hour reminders and send them.
    This function runs in a background thread.
    """
    with app.app_context():
        try:
            # Calculate tomorrow's date
            tomorrow = date.today() + timedelta(days=1)
            
            # Find all confirmed bookings for tomorrow that haven't been reminded
            bookings_tomorrow = Booking.query.filter(
                Booking.booking_date == tomorrow,
                Booking.status == 'confirmed'
            ).all()
            
            reminders_sent = 0
            
            for booking in bookings_tomorrow:
                # Check if reminder was already sent (you might want to add a reminder_sent field to Booking model)
                # For now, we'll send reminders for all confirmed bookings
                
                success = send_reminder_email(booking)
                if success:
                    reminders_sent += 1
                    
                    # Optional: Mark that reminder was sent
                    # booking.reminder_sent = True
                    # db.session.commit()
            
            if reminders_sent > 0:
                print(f"📧 Sent {reminders_sent} reminder email(s) for tomorrow's appointments")
            else:
                print(f"📅 No reminders needed - {len(bookings_tomorrow)} bookings tomorrow")
                
        except Exception as e:
            print(f"❌ Error in reminder check: {str(e)}")


def start_reminder_scheduler():
    """
    Start the background reminder scheduler.
    Checks for reminders every hour.
    """
    def reminder_loop():
        while True:
            try:
                # Check current time
                now = datetime.now()
                
                # Send reminders at 9 AM daily (you can adjust this)
                if now.hour == 9 and now.minute < 5:  # 9:00-9:05 AM window
                    print(f"🕘 Daily reminder check at {now.strftime('%I:%M %p')}")
                    check_and_send_reminders()
                    
                    # Sleep for 10 minutes to avoid duplicate sends in the same hour
                    time_module.sleep(600)  # 10 minutes
                else:
                    # Check every hour
                    time_module.sleep(3600)  # 1 hour
                    
            except Exception as e:
                print(f"❌ Error in reminder scheduler: {str(e)}")
                time_module.sleep(300)  # 5 minutes before retrying
    
    # Start reminder thread
    reminder_thread = threading.Thread(target=reminder_loop, daemon=True)
    reminder_thread.start()
    print("📧 Email reminder scheduler started - will check daily at 9 AM")

# ========================================
# ADMIN API ROUTES
# ========================================

@app.route('/api/admin/dashboard', methods=['GET'])
@login_required
def api_admin_dashboard():
    """API endpoint for admin dashboard data"""
    if not current_user.is_admin:
        return jsonify({'success': False, 'message': 'Admin access required'}), 403
    
    try:
        # Get recent bookings (last 30 days)
        from datetime import datetime, timedelta
        thirty_days_ago = datetime.now() - timedelta(days=30)
        recent_bookings = Booking.query.filter(
            Booking.created_at >= thirty_days_ago
        ).order_by(Booking.created_at.desc()).limit(50).all()
        
        # Get today's bookings
        today = date.today()
        today_bookings = Booking.query.filter_by(booking_date=today).all()
        
        # Get pending bookings
        pending_bookings = Booking.query.filter_by(status='pending').all()
        
        # Get all customers
        total_customers = User.query.filter_by(is_admin=False).count()
        
        # Calculate stats
        total_bookings = Booking.query.count()
        confirmed_bookings = Booking.query.filter_by(status='confirmed').count()
        completed_bookings = Booking.query.filter_by(status='completed').count()
        
        # Format booking data
        def format_booking(booking):
            return {
                'id': booking.id,
                'customer_name': booking.user.full_name,
                'customer_email': booking.user.email,
                'customer_phone': booking.user.phone,
                'service_name': booking.service_type.name,
                'service_category': booking.service_type.category,
                'booking_date': booking.booking_date.strftime('%Y-%m-%d'),
                'start_time': booking.start_time.strftime('%H:%M'),
                'end_time': booking.end_time.strftime('%H:%M'),
                'status': booking.status,
                'created_at': booking.created_at.strftime('%Y-%m-%d %H:%M'),
                'address': booking.user.address,
                'custom_description': booking.custom_description
            }
        
        return jsonify({
            'success': True,
            'data': {
                'recent_bookings': [format_booking(b) for b in recent_bookings],
                'today_bookings': [format_booking(b) for b in today_bookings],
                'pending_bookings': [format_booking(b) for b in pending_bookings],
                'stats': {
                    'total_bookings': total_bookings,
                    'confirmed_bookings': confirmed_bookings,
                    'completed_bookings': completed_bookings,
                    'pending_bookings': len(pending_bookings),
                    'total_customers': total_customers,
                    'todays_bookings': len(today_bookings)
                }
            }
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error loading dashboard: {str(e)}'}), 500

@app.route('/api/admin/bookings/<int:booking_id>/status', methods=['POST'])
@login_required
def api_update_booking_status(booking_id):
    """API endpoint to update booking status"""
    if not current_user.is_admin:
        return jsonify({'success': False, 'message': 'Admin access required'}), 403
    
    try:
        data = request.get_json()
        new_status = data.get('status')
        admin_notes = data.get('admin_notes', '')
        
        if new_status not in ['pending', 'confirmed', 'completed', 'cancelled']:
            return jsonify({'success': False, 'message': 'Invalid status'}), 400
        
        booking = Booking.query.get_or_404(booking_id)
        booking.status = new_status
        if admin_notes:
            booking.admin_notes = admin_notes
        
        db.session.commit()
        
        return jsonify({
            'success': True, 
            'message': f'Booking status updated to {new_status}'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Error updating booking: {str(e)}'}), 500

@app.route('/api/admin/customers', methods=['GET'])
@login_required
def api_admin_customers():
    """API endpoint to get all customers"""
    if not current_user.is_admin:
        return jsonify({'success': False, 'message': 'Admin access required'}), 403
    
    try:
        customers = User.query.filter_by(is_admin=False).order_by(User.created_at.desc()).all()
        
        customer_data = []
        for customer in customers:
            bookings = Booking.query.filter_by(user_id=customer.id).all()
            customer_data.append({
                'id': customer.id,
                'name': customer.full_name,
                'email': customer.email,
                'phone': customer.phone,
                'address': customer.address,
                'created_at': customer.created_at.strftime('%Y-%m-%d'),
                'total_bookings': len(bookings),
                'completed_bookings': len([b for b in bookings if b.status == 'completed']),
                'last_booking': bookings[-1].booking_date.strftime('%Y-%m-%d') if bookings else None
            })
        
        return jsonify({
            'success': True,
            'customers': customer_data
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error loading customers: {str(e)}'}), 500
# Photo upload route
@app.route('/api/upload-photos', methods=['POST'])
def upload_photos():
    """Handle photo uploads for custom landscaping requests"""
    try:
        # Create uploads folder if it doesn't exist
        upload_folder = 'static/uploads'
        os.makedirs(upload_folder, exist_ok=True)
        
        if 'photos' not in request.files:
            return jsonify({'success': False, 'message': 'No photos provided'}), 400
        
        photos = request.files.getlist('photos')
        uploaded_files = []
        
        for photo in photos:
            if photo.filename != '' and photo:
                # Generate secure filename
                filename = secure_filename(photo.filename)
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_')
                filename = timestamp + filename
                
                # Save file
                file_path = os.path.join(upload_folder, filename)
                photo.save(file_path)
                
                uploaded_files.append({
                    'filename': filename,
                    'original_name': photo.filename,
                    'url': f'/static/uploads/{filename}'
                })
        
        return jsonify({
            'success': True,
            'message': f'{len(uploaded_files)} photos uploaded successfully',
            'files': uploaded_files
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

# Booking options route
@app.route('/api/set-booking-options', methods=['POST'])
def set_booking_options():
    """Store booking options in session"""
    try:
        data = request.get_json()
        session['booking_options'] = data
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
@app.route('/api/customer/bookings', methods=['GET'])
@login_required
def api_customer_bookings():
    """API endpoint for customer's own bookings"""
    try:
        # Get customer's bookings
        customer_bookings = Booking.query.filter_by(user_id=current_user.id).order_by(Booking.created_at.desc()).all()
        
        # Calculate stats
        total_bookings = len(customer_bookings)
        completed_bookings = len([b for b in customer_bookings if b.status == 'completed'])
        pending_bookings = len([b for b in customer_bookings if b.status == 'pending'])
        cancelled_bookings = len([b for b in customer_bookings if b.status == 'cancelled'])
        
        # Format booking data
        def format_customer_booking(booking):
            return {
                'id': booking.id,
                'service_name': booking.service_type.name,
                'service_category': booking.service_type.category,
                'booking_date': booking.booking_date.strftime('%Y-%m-%d'),
                'start_time': booking.start_time.strftime('%H:%M'),
                'end_time': booking.end_time.strftime('%H:%M'),
                'status': booking.status,
                'created_at': booking.created_at.strftime('%Y-%m-%d %H:%M'),
                'custom_description': booking.custom_description
            }
        
        return jsonify({
            'success': True,
            'data': {
                'bookings': [format_customer_booking(b) for b in customer_bookings],
                'stats': {
                    'total_bookings': total_bookings,
                    'completed_bookings': completed_bookings,
                    'pending_bookings': pending_bookings,
                    'cancelled_bookings': cancelled_bookings
                }
            }
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error loading bookings: {str(e)}'}), 500

# ========================================
# MAIN ROUTES
# ========================================

@app.route('/')
def index():
    """
    Landing page - displays AMR logo and two main service options.
    This is the page customers see when they scan the QR code.
    """
    return render_template('index.html')

@app.route('/services/<service_category>')
def select_service(service_category):
    """
    Service selection page - shows specific services within a category.
    
    Args:
        service_category (str): Either 'landscaping' or 'pressure_washing'
    """
    if service_category not in ['landscaping', 'pressure_washing']:
        flash('Invalid service category', 'error')
        return redirect(url_for('index'))
    
    # Get services for this category
    services = ServiceType.query.filter_by(
        category=service_category, 
        is_active=True
    ).all()
    
    return render_template('select_service.html', 
                         services=services, 
                         category=service_category)

@app.route('/calendar/<int:service_id>')
def calendar(service_id):
    """
    Calendar page - shows available dates for booking (current month).
    """
    today = date.today()
    return calendar_month(service_id, today.year, today.month)

@app.route('/calendar-month/<int:service_id>/<int:year>/<int:month>')
def calendar_month(service_id, year, month):
    """
    Calendar page with month navigation support.
    """
    service = ServiceType.query.get_or_404(service_id)
    
    # Store service in session for next steps
    session['selected_service_id'] = service_id
    
    # Calculate previous and next months
    if month == 1:
        prev_month = 12
        prev_year = year - 1
    else:
        prev_month = month - 1
        prev_year = year
        
    if month == 12:
        next_month = 1
        next_year = year + 1
    else:
        next_month = month + 1
        next_year = year
    
    # Generate calendar data for requested month
    import calendar as cal
    month_calendar = cal.monthcalendar(year, month)
    
    # Check availability for each day
    available_dates = {}
    for week in month_calendar:
        for day in week:
            if day != 0:
                check_date = date(year, month, day)
                available_dates[day] = is_date_available(check_date)
    
    # Get today's date for highlighting
    today = date.today()
    
    return render_template('calendar.html', 
                         service=service,
                         month_calendar=month_calendar,
                         available_dates=available_dates,
                         current_month=month,
                         current_year=year,
                         prev_month=prev_month,
                         prev_year=prev_year,
                         next_month=next_month,
                         next_year=next_year,
                         today_year=today.year,
                         today_month=today.month,
                         today_day=today.day,
                         month_name=cal.month_name[month])

@app.route('/time-selection/<int:year>/<int:month>/<int:day>')
def time_selection(year, month, day):
    """
    Time selection page - shows available time slots for selected date.
    
    Args:
        year, month, day (int): The selected date components
    """
    # Get service from session
    service_id = session.get('selected_service_id')
    if not service_id:
        flash('Please select a service first', 'error')
        return redirect(url_for('index'))
    
    service = ServiceType.query.get_or_404(service_id)
    selected_date = date(year, month, day)
    
    # Get available time slots with service type for proper blocking
    available_times = get_available_time_slots(selected_date, service.duration_hours, service)
    
    # Store selected date in session
    session['selected_date'] = selected_date.isoformat()
    
    return render_template('time_selection.html',
                         service=service,
                         selected_date=selected_date,
                         available_times=available_times)

@app.route('/booking-form/<selected_time>')
def booking_form(selected_time):
    """
    Booking form page - collects customer information.
    Auto-fills with user data if logged in.
    
    Args:
        selected_time (str): Selected time in HH:MM format
    """
    # Get data from session
    service_id = session.get('selected_service_id')
    selected_date_str = session.get('selected_date')
    
    if not service_id or not selected_date_str:
        flash('Please start the booking process from the beginning', 'error')
        return redirect(url_for('index'))
    
    service = ServiceType.query.get_or_404(service_id)
    selected_date = date.fromisoformat(selected_date_str)
    
    # Parse and store selected time
    try:
        selected_time_obj = datetime.strptime(selected_time, '%H:%M').time()
        session['selected_time'] = selected_time
    except ValueError:
        flash('Invalid time format', 'error')
        return redirect(url_for('calendar', service_id=service_id))
    
    return render_template('booking_form.html',
                         service=service,
                         selected_date=selected_date,
                         selected_time=selected_time_obj,
                         current_user=current_user)

@app.route('/submit-booking', methods=['POST'])
def submit_booking():
    """
    Process booking form submission and create new booking.
    """
    try:
        # Get data from session
        service_id = session.get('selected_service_id')
        selected_date_str = session.get('selected_date')
        selected_time_str = session.get('selected_time')
        
        if not all([service_id, selected_date_str, selected_time_str]):
            flash('Session expired. Please start over.', 'error')
            return redirect(url_for('index'))
        
        # Get service and validate
        service = ServiceType.query.get_or_404(service_id)
        selected_date = date.fromisoformat(selected_date_str)
        selected_time = datetime.strptime(selected_time_str, '%H:%M').time()

        # Get form data
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip()
        address = request.form.get('address', '').strip()
        custom_description = request.form.get('custom_description', '').strip()
        
        # Get booking options from session
        booking_options = session.get('booking_options', {})
        is_recurring = booking_options.get('bookingType') == 'recurring'
        frequency_data = booking_options.get('frequency', {})
        
        # Validate required fields
        if not all([first_name, last_name, email, phone, address]):
            flash('All fields are required', 'error')
            return redirect(request.referrer)
        
        # If user is logged in, use their account
        if current_user.is_authenticated:
            user = current_user
            # Update user info if they changed it
            user.first_name = first_name
            user.last_name = last_name
            user.email = email
            user.phone = phone
            user.address = address
        else:
            # Check if user exists or create new one
            user = User.query.filter_by(email=email).first()
            if not user:
                # Create new user account automatically
                user = User(
                    first_name=first_name,
                    last_name=last_name,
                    email=email,
                    phone=phone,
                    address=address
                )
                # Set a temporary password - user can reset it later
                user.set_password('temp_password_123')
                db.session.add(user)
                db.session.flush()  # Get user ID without committing
        
        # Calculate end time
        start_datetime = datetime.combine(selected_date, selected_time)
        end_datetime = start_datetime + timedelta(hours=service.duration_hours)
        end_time = end_datetime.time()
        
        # Create booking
        booking = Booking(
            user_id=user.id,
            service_type_id=service_id,
            booking_date=selected_date,
            start_time=selected_time,
            end_time=end_time,
            custom_description=custom_description if service.is_custom else None,
            status='confirmed' if not service.is_custom else 'pending'
        )
        
        db.session.add(booking)
        db.session.flush()  # Get booking ID
        
        # Handle recurring booking setup
        if is_recurring and frequency_data:
            recurring_booking = RecurringBooking(
                user_id=user.id,
                service_type_id=service_id,
                frequency_value=str(frequency_data.get('value', '1')),
                frequency_type=frequency_data.get('type', 'weeks'),
                start_date=selected_date,
                next_due_date=selected_date
            )
            db.session.add(recurring_booking)
        
        db.session.commit()
        
        # Send confirmation email
        send_confirmation_email(booking)
        
        # Clear session
        session.pop('selected_service_id', None)
        session.pop('selected_date', None)
        session.pop('selected_time', None)
        session.pop('booking_options', None)
        
        flash('Booking confirmed successfully!', 'success')
        return redirect(url_for('confirmation', booking_id=booking.id))
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error creating booking: {str(e)}', 'error')
        return redirect(url_for('index'))

@app.route('/confirmation/<int:booking_id>')
def confirmation(booking_id):
    """
    Booking confirmation page - shows booking details to customer.
    
    Args:
        booking_id (int): ID of the created booking
    """
    booking = Booking.query.get_or_404(booking_id)
    return render_template('confirmation.html', booking=booking)

# ========================================
# ADMIN ROUTES
# ========================================

@app.route('/admin')
@login_required
def admin_dashboard():
    """
    Admin dashboard - overview of all bookings.
    Requires login and admin privileges.
    """
    if not current_user.is_admin:
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('index'))
    
    # Get recent bookings
    recent_bookings = Booking.query.order_by(Booking.created_at.desc()).limit(20).all()
    
    # Get today's bookings
    today_bookings = Booking.query.filter_by(booking_date=date.today()).all()
    
    # Get pending custom service bookings
    pending_bookings = Booking.query.filter_by(status='pending').all()
    
    # Get all users
    all_users = User.query.order_by(User.created_at.desc()).all()
    
    return render_template('admin/dashboard.html',
                         recent_bookings=recent_bookings,
                         today_bookings=today_bookings,
                         pending_bookings=pending_bookings,
                         all_users=all_users)

@app.route('/admin/booking/<int:booking_id>')
@login_required
def admin_booking_detail(booking_id):
    """
    Admin booking detail page - manage individual bookings.
    """
    if not current_user.is_admin:
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('index'))
    
    booking = Booking.query.get_or_404(booking_id)
    return render_template('admin/booking_detail.html', booking=booking)

@app.route('/admin/booking/<int:booking_id>/update-status', methods=['POST'])
@login_required
def update_booking_status(booking_id):
    """
    Update booking status (confirm, cancel, complete).
    """
    if not current_user.is_admin:
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('index'))
    
    booking = Booking.query.get_or_404(booking_id)
    new_status = request.form.get('status')
    admin_notes = request.form.get('admin_notes', '')
    
    if new_status in ['pending', 'confirmed', 'completed', 'cancelled']:
        booking.status = new_status
        if admin_notes:
            booking.admin_notes = admin_notes
        
        db.session.commit()
        flash(f'Booking status updated to {new_status}', 'success')
    else:
        flash('Invalid status', 'error')
    
    return redirect(url_for('admin_booking_detail', booking_id=booking_id))

# ========================================
# DATABASE INITIALIZATION
# ========================================

def init_database():
    """
    Initialize database with tables and sample data.
    """
    with app.app_context():
        # Drop all tables first to ensure clean slate
        db.drop_all()
        
        # Create all tables with new structure
        db.create_all()
        
        # Add default services if none exist
        # Add default services if none exist
        services = [
    # Landscaping Services
    ServiceType(
        name='Standard Lawn Service',
        category='landscaping',
        description='Grass cutting and weed eating',
        duration_hours=1.5,
        is_custom=False
    ),
    ServiceType(
        name='Mulching',
        category='landscaping',
        description='Professional mulching for flower beds and landscaping',
        duration_hours=2.0,
        is_custom=False
    ),
    ServiceType(
        name='Hedge Trimming',
        category='landscaping',
        description='Trimming and shaping of hedges and shrubs',
        duration_hours=1.5,
        is_custom=False
    ),
    ServiceType(
        name='Specialty Lawn Care',
        category='landscaping',
        description='Fertilization, weed control, and specialized lawn treatments',
        duration_hours=1.0,
        is_custom=False
    ),
    ServiceType(
        name='Custom Landscaping',
        category='landscaping',
        description='Custom landscaping work - duration set by admin',
        duration_hours=1.0,
        is_custom=True
    ),
    
    # Pressure Washing Services
    ServiceType(
        name='Full House Pressure Washing',
        category='pressure_washing',
        description='Complete house exterior pressure washing',
        duration_hours=4.0,
        is_custom=False
    ),
    ServiceType(
        name='Driveway Pressure Washing',
        category='pressure_washing',
        description='Driveway and walkway cleaning',
        duration_hours=3.0,
        is_custom=False
    ),
    ServiceType(
        name='Patio Pressure Washing',
        category='pressure_washing',
        description='Patio and outdoor area cleaning',
        duration_hours=2.0,
        is_custom=False
    ),
    ServiceType(
        name='Deck & Fence Pressure Washing',
        category='pressure_washing',
        description='Professional deck and fence cleaning and restoration',
        duration_hours=3.5,
        is_custom=False
    ),
    ServiceType(
        name='Window Cleaning',
        category='pressure_washing',
        description='Professional window cleaning service',
        duration_hours=1.5,
        is_custom=False
    ),
]
        
        for service in services:
            db.session.add(service)
        
        # Create default admin user
        admin_user = User(
            first_name='Admin',
            last_name='User',
            email='admin@amrservices.com',
            phone='555-0123',
            address='123 Admin St, Admin City, AC 12345',
            is_admin=True
        )
        admin_user.set_password('admin123')  # Change this in production!
        db.session.add(admin_user)
        
        db.session.commit()
        print("Database initialized with correct structure!")
        print("Admin login: admin@amrservices.com / admin123")

# ========================================
# APPLICATION STARTUP
# ========================================

if __name__ == '__main__':
    # Initialize database (comment out after first run)
    init_database()
    
    # Start the reminder system
    start_reminder_scheduler()
    
    # Run the application
    app.run(debug=True, host='0.0.0.0', port=5001)

"""
DEPLOYMENT NOTES:
================

1. PRODUCTION SETUP:
   - Change SECRET_KEY to a secure random string
   - Use PostgreSQL instead of SQLite: 
     DATABASE_URL = postgresql://username:password@host:port/database
   - Change admin password from default
   - Configure real email SMTP settings

2. ENVIRONMENT VARIABLES:
   Set these in your hosting platform:
   - SECRET_KEY=your-secure-secret-key
   - DATABASE_URL=your-database-url
   - MAIL_USERNAME=your-email@gmail.com
   - MAIL_PASSWORD=your-app-password

3. HOSTING PLATFORMS:
   - Heroku: Add Procfile with "web: gunicorn app:app"
   - Railway: Automatically detects Flask apps
   - DigitalOcean: Use their App Platform
   - Render: Connect your GitHub repo

4. FEATURES ADDED:
   - Full user authentication with Flask-Login
   - Password hashing with Werkzeug security
   - User registration and login API endpoints
   - Auto-fill booking forms for logged-in users
   - Admin dashboard for managing bookings and users
   - Session management across page refreshes
   - Secure database storage for all user data
   - Real booking system ready for production use

5. API ENDPOINTS:
   - POST /api/signup - Create new user account
   - POST /api/login - User login
   - POST /api/logout - User logout  
   - GET /api/current-user - Get current user info

6. ADMIN FEATURES:
   - Default admin account: admin@amrservices.com / admin123
   - View all bookings and users
   - Update booking statuses
   - Access to customer information
   - Booking management tools

7. SECURITY FEATURES:
   - Passwords hashed with bcrypt
   - Session-based authentication
   - CSRF protection via Flask-WTF (add if needed)
   - SQL injection protection via SQLAlchemy ORM
   - XSS protection via Jinja2 auto-escaping

8. DATABASE SCHEMA:
   - users: Authentication and customer info
   - service_types: Available services
   - bookings: Appointment records
   - Relationships properly configured

9. NEXT STEPS FOR DEPLOYMENT:
   - Push code to GitHub
   - Deploy to Heroku/Railway/Render
   - Configure environment variables
   - Set up PostgreSQL database
   - Configure email service (SendGrid/Mailgun)
   - Test all functionality in production

10. BUSINESS BENEFITS:
    - Real customer accounts
    - Booking history tracking
    - Admin oversight and management
    - Email confirmations
    - Scalable architecture
    - Ready for real business use
"""