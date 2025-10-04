from flask import Flask, request, jsonify, send_file, render_template
import pandas as pd
import qrcode
from PIL import Image, ImageDraw, ImageFont
import os
import hashlib
import io
import uuid 
from datetime import datetime
import requests # <-- ADDED for fetching the uploaded image
from vercel_blob import put # <-- ADDED for uploading to Vercel Blob

app = Flask(__name__, template_folder='.')

# --- CONFIGURATION ---
DATA_FILE = os.path.join('data', 'students.xlsx')
ASSETS_DIR = 'assets'
FONTS_DIR = os.path.join(ASSETS_DIR, 'fonts')
TEMPLATE_FILE = os.path.join(ASSETS_DIR, 'ticket_template.png')
# Note: PROFILE_PICS_DIR is no longer needed as we upload to the cloud
# SECRET_KEY will be set as an Environment Variable in Vercel

# --- HELPER FUNCTIONS ---
def generate_unique_student_id():
    """Generates a truly unique, encrypted-like StudentID."""
    secret_key = os.environ.get('SECRET_KEY', 'default_local_secret_key')
    unique_string = str(uuid.uuid4()) + secret_key + str(datetime.now())
    hashed_id = hashlib.sha256(unique_string.encode('utf-8')).hexdigest()
    return f"STU-{hashed_id[:8].upper()}"

# --- ROUTES ---
@app.route('/', methods=['GET'])
def serve_homepage():
    return render_template('index.html')

@app.route('/api/register-student', methods=['POST'])
def register_student_and_generate_ticket():
    try:
        # 1. Get data from form
        student_name = request.form.get('studentName')
        roll_no = request.form.get('rollNo')
        study_year = request.form.get('studyYear')
        profile_image_file = request.files.get('profileImage')

        if not all([student_name, roll_no, study_year, profile_image_file]):
            return jsonify({"error": "Missing form data."}), 400

        # 2. Generate Unique StudentID
        generated_student_id = generate_unique_student_id()
        
        # 3. CHANGED: Upload Profile Image to Vercel Blob
        filename = f"profile_pics/{generated_student_id}_{profile_image_file.filename}"
        body = profile_image_file.read()
        
        blob_result = put(pathname=filename, body=body, options={'access': 'public'})
        profile_pic_url = blob_result['url'] # Get the public URL of the uploaded image

        # 4. Load/Update students.xlsx (This part will still fail on Vercel for now)
        try:
            df = pd.read_excel(DATA_FILE)
        except FileNotFoundError:
            df = pd.DataFrame(columns=['RollNo', 'StudentID', 'Name', 'Status', 'Year', 'ProfilePic'])

        if roll_no in df['RollNo'].astype(str).values:
            return jsonify({"error": f"Roll Number '{roll_no}' already exists."}), 409

        new_student_data = {
            'RollNo': roll_no,
            'StudentID': generated_student_id,
            'Name': student_name,
            'Status': 'Active',
            'Year': study_year,
            'ProfilePic': profile_pic_url # CHANGED: Save the URL instead of the filename
        }
        df = pd.concat([df, pd.DataFrame([new_student_data])], ignore_index=True)
        df.to_excel(DATA_FILE, index=False)

        # 5. Generate the Ticket
        template = Image.open(TEMPLATE_FILE).convert("RGBA")
        font_name = ImageFont.truetype(os.path.join(FONTS_DIR, 'Poppins-Bold.ttf'), 48)
        font_details = ImageFont.truetype(os.path.join(FONTS_DIR, 'Poppins-Regular.ttf'), 32)
        
        # CHANGED: Fetch the profile pic from the Vercel Blob URL
        response = requests.get(profile_pic_url)
        profile_pic_ticket = Image.open(io.BytesIO(response.content)).resize((180, 180))

        qr_img = qrcode.make(generated_student_id).resize((180, 180))
        unique_ticket_code_on_ticket = generated_student_id

        card_layer = Image.new('RGBA', template.size, (255, 255, 255, 0))
        draw = ImageDraw.Draw(card_layer)
        
        card_width = 800 
        card_height = 300 
        card_center_x = template.width // 2
        card_center_y = template.height // 2
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
        draw.text((text_start_x, profile_pic_on_card_y + 110), f"ID: {unique_ticket_code_on_ticket}", font=font_details, fill='#cccccc')

        final_image = Image.alpha_composite(template, card_layer).convert("RGB")
        
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
        app.logger.error(f"Error: {e}")
        return jsonify({"error": f"An unexpected server error occurred: {str(e)}"}), 500

# This is the main entry point for Vercel
def handler(environ, start_response):
    return app(environ, start_response)