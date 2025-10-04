from flask import Flask, request, jsonify, send_file, render_template
import pandas as pd
import qrcode
from PIL import Image, ImageDraw, ImageFont
import os
import hashlib
import io
import uuid # For generating unique IDs
from datetime import datetime # MOVED: Import moved to the top

app = Flask(__name__, template_folder='.')

# --- CONFIGURATION ---
DATA_FILE = os.path.join('data', 'students.xlsx')
ASSETS_DIR = 'assets'
PROFILE_PICS_DIR = os.path.join(ASSETS_DIR, 'profile_pics') # Where uploaded images will be stored
FONTS_DIR = os.path.join(ASSETS_DIR, 'fonts')
TEMPLATE_FILE = os.path.join(ASSETS_DIR, 'ticket_template.png')
SECRET_KEY = "YourSuperSecretKeyHere123!" # IMPORTANT: Keep this secret and change for production

# --- HELPER FUNCTIONS ---

def generate_unique_student_id():
    """Generates a truly unique, encrypted-like StudentID."""
    # Using uuid4 for uniqueness, then hashing it to make it look "encrypted" and fixed length
    unique_string = str(uuid.uuid4()) + SECRET_KEY + str(datetime.now())
    hashed_id = hashlib.sha256(unique_string.encode('utf-8')).hexdigest()
    return f"STU-{hashed_id[:8].upper()}" # e.g., STU-A1B2C3D4

# --- ROUTES ---

# Route to serve the main homepage (index.html)
@app.route('/', methods=['GET'])
def serve_homepage():
    return render_template('index.html')

# API Endpoint to register a new student and generate their ticket
@app.route('/api/register-student', methods=['POST'])
def register_student_and_generate_ticket():
    try:
        # 1. Get data from form
        student_name = request.form.get('studentName')
        roll_no = request.form.get('rollNo')
        study_year = request.form.get('studyYear')
        profile_image_file = request.files.get('profileImage')

        if not all([student_name, roll_no, study_year, profile_image_file]):
            return jsonify({"error": "Missing form data (Name, Roll No, Year, or Profile Image)."}), 400

        # 2. Generate Unique StudentID (this will be the QR code content)
        generated_student_id = generate_unique_student_id()
        
        # 3. Save Profile Image
        profile_pic_filename = f"{generated_student_id}_{profile_image_file.filename}"
        profile_pic_path = os.path.join(PROFILE_PICS_DIR, profile_pic_filename)
        os.makedirs(PROFILE_PICS_DIR, exist_ok=True) # Ensure directory exists
        profile_image_file.save(profile_pic_path)

        # 4. Load/Update students.xlsx
        try:
            df = pd.read_excel(DATA_FILE)
        except FileNotFoundError:
            # Create new dataframe if file doesn't exist
            df = pd.DataFrame(columns=['RollNo', 'StudentID', 'Name', 'Status', 'Year', 'ProfilePic'])

        # Check if RollNo already exists (to prevent duplicates)
        if roll_no in df['RollNo'].astype(str).values:
            return jsonify({"error": f"Roll Number '{roll_no}' already exists. Please use a unique Roll Number."}), 409 # 409 Conflict

        new_student_data = {
            'RollNo': roll_no,
            'StudentID': generated_student_id, # This is the generated, encrypted-like ID
            'Name': student_name,
            'Status': 'Active', # Default status for new students
            'Year': study_year,
            'ProfilePic': profile_pic_filename
        }
        df = pd.concat([df, pd.DataFrame([new_student_data])], ignore_index=True)
        
        # Ensure 'StudentID' column is string type for QR generation consistency
        df['StudentID'] = df['StudentID'].astype(str)
        df['RollNo'] = df['RollNo'].astype(str) # Also ensure RollNo is string
        
        df.to_excel(DATA_FILE, index=False) # Save changes

        # 5. Generate the Ticket (using the logic from previous steps)
        template = Image.open(TEMPLATE_FILE).convert("RGBA")
        font_name = ImageFont.truetype(os.path.join(FONTS_DIR, 'Poppins-Bold.ttf'), 48)
        font_details = ImageFont.truetype(os.path.join(FONTS_DIR, 'Poppins-Regular.ttf'), 32)
        
        # Profile pic for the ticket will be the one just uploaded
        profile_pic_ticket = Image.open(profile_pic_path).resize((180, 180))

        qr_img = qrcode.make(generated_student_id) # QR code contains the generated StudentID
        qr_img = qr_img.resize((180, 180))

        unique_ticket_code_on_ticket = generated_student_id # The StudentID IS the unique code

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
        # FIXED! Changed student_year to study_year
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
        app.logger.error(f"Error during student registration and ticket generation: {e}")
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500

# This is the main entry point for Vercel
def handler(environ, start_response):
    return app(environ, start_response)

if __name__ == '__main__':
    # This block is not used by Vercel, but is good for local testing
    # To run locally, use the command: flask --app index.py run
    pass