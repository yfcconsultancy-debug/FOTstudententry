from flask import Flask, request, jsonify, send_file, render_template
from flask_sqlalchemy import SQLAlchemy
import qrcode
from PIL import Image, ImageDraw, ImageFont
import os
import hashlib
import io
import uuid 
from datetime import datetime
import requests
from vercel_blob import put

app = Flask(__name__, template_folder='.')

# --- DATABASE CONFIGURATION ---
# Vercel provides the POSTGRES_URL environment variable automatically.
# The .replace() is a small fix to make the URL compatible with SQLAlchemy.
db_uri = os.environ.get('POSTGRES_URL', '').replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = db_uri
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)


# --- DATABASE MODEL ---
# This class defines the 'students' table in our database.
class Student(db.Model):
    __tablename__ = 'students'
    id = db.Column(db.Integer, primary_key=True)
    roll_no = db.Column(db.String(255), unique=True, nullable=False)
    student_id = db.Column(db.String(255), unique=True, nullable=False)
    name = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(50), default='Active')
    year = db.Column(db.String(50))
    profile_pic_url = db.Column(db.Text)


# --- FOLDER/FILE CONFIGURATION ---
ASSETS_DIR = 'assets'
FONTS_DIR = os.path.join(ASSETS_DIR, 'fonts')
TEMPLATE_FILE = os.path.join(ASSETS_DIR, 'ticket_template.png')


# --- HELPER FUNCTIONS ---
def generate_unique_student_id():
    """Generates a unique StudentID using a secret key."""
    secret_key = os.environ.get('SECRET_KEY', 'default_local_secret_key')
    unique_string = str(uuid.uuid4()) + secret_key + str(datetime.now())
    hashed_id = hashlib.sha2sh256(unique_string.encode('utf-8')).hexdigest()
    return f"STU-{hashed_id[:8].upper()}"


# --- ROUTES ---
@app.route('/', methods=['GET'])
def serve_homepage():
    """Serves the main registration page."""
    return render_template('index.html')


@app.route('/api/register-student', methods=['POST'])
def register_student_and_generate_ticket():
    """Handles registration, image upload to Blob, data saving to Postgres, and ticket generation."""
    try:
        # 1. Get data from the form
        student_name = request.form.get('studentName')
        roll_no = request.form.get('rollNo')
        study_year = request.form.get('studyYear')
        profile_image_file = request.files.get('profileImage')

        if not all([student_name, roll_no, study_year, profile_image_file]):
            return jsonify({"error": "Missing form data."}), 400

        # 2. Check for duplicate Roll No. in the database
        existing_student = Student.query.filter_by(roll_no=roll_no).first()
        if existing_student:
            return jsonify({"error": f"Roll Number '{roll_no}' already exists."}), 409

        # 3. Generate Unique Student ID
        generated_student_id = generate_unique_student_id()
        
        # 4. Upload Profile Image to Vercel Blob
        filename = f"profile_pics/{generated_student_id}_{profile_image_file.filename}"
        body = profile_image_file.read()
        blob_result = put(blob_name=filename, body=body, access='public')
        profile_pic_url = blob_result['url']

        # 5. Save new student data to the Postgres database
        new_student = Student(
            roll_no=roll_no,
            student_id=generated_student_id,
            name=student_name,
            year=study_year,
            profile_pic_url=profile_pic_url,
            status='Active'
        )
        db.session.add(new_student)
        db.session.commit()

        # 6. Generate the Ticket Image
        template = Image.open(TEMPLATE_FILE).convert("RGBA")
        font_name = ImageFont.truetype(os.path.join(FONTS_DIR, 'Poppins-Bold.ttf'), 48)
        font_details = ImageFont.truetype(os.path.join(FONTS_DIR, 'Poppins-Regular.ttf'), 32)
        
        response = requests.get(profile_pic_url)
        profile_pic_ticket = Image.open(io.BytesIO(response.content)).resize((180, 180))

        qr_img = qrcode.make(generated_student_id).resize((180, 180))
        
        # Drawing logic for the ticket...
        card_layer = Image.new('RGBA', template.size, (255, 255, 255, 0))
        draw = ImageDraw.Draw(card_layer)
        card_width, card_height = 800, 300
        card_center_x, card_center_y = template.width // 2, template.height // 2
        card_left = card_center_x - card_width // 2
        card_top = card_center_y - card_height // 2
        profile_pic_on_card_x = card_left + 25
        profile_pic_on_card_y = card_top + 60
        qr_img_on_card_x = card_left + card_width - qr_img.width - 25
        card_layer.paste(profile_pic_ticket, (profile_pic_on_card_x, profile_pic_on_card_y))
        card_layer.paste(qr_img, (qr_img_on_card_x, profile_pic_on_card_y))
        text_start_x = profile_pic_on_card_x + profile_pic_ticket.width + 30
        draw.text((text_start_x, profile_pic_on_card_y + 10), student_name, font=font_name, fill='white')
        draw.text((text_start_x, profile_pic_on_card_y + 70), study_year, font=font_details, fill='#cccccc')
        draw.text((text_start_x, profile_pic_on_card_y + 110), f"ID: {generated_student_id}", font=font_details, fill='#cccccc')
        final_image = Image.alpha_composite(template, card_layer).convert("RGB")
        
        # 7. Return the final image as a file
        img_io = io.BytesIO()
        final_image.save(img_io, 'PNG')
        img_io.seek(0)
        
        return send_file(
            img_io,
            mimetype='image/png',
            as_attachment=True,
            download_name=f'{generated_student_id}_ticket.png'
        )

    except Exception as e:
        app.logger.error(f"An error occurred: {e}")
        return jsonify({"error": "An unexpected server error occurred."}), 500

# This function is the entry point for Vercel's serverless environment
def handler(environ, start_response):
    return app(environ, start_response)