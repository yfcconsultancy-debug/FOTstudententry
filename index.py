# --- DEBUGGING VERSION of index.py ---

from flask import Flask, request, jsonify, send_file, render_template
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
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

# --- DATABASE CONNECTION ---
# We will establish the connection inside the request to see the logs.
mongo_uri = os.environ.get('MONGO_URI')
client = None
students_collection = None

# This block will test the connection right when the server starts
try:
    print("SERVER STARTING: Attempting to connect to MongoDB...")
    if not mongo_uri:
        print("SERVER STARTING ERROR: MONGO_URI environment variable is not set.")
    else:
        # Set a 5-second timeout to prevent the function from hanging
        client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
        # The ismaster command is cheap and does not require auth.
        client.admin.command('ismaster')
        print("SERVER STARTING: MongoDB connection successful.")
        db = client['student_ticket_db']
        students_collection = db['students']
except ConnectionFailure as e:
    print(f"SERVER STARTING ERROR: Could not connect to MongoDB. Error: {e}")
except Exception as e:
    print(f"SERVER STARTING ERROR: An unexpected error occurred during connection. Error: {e}")


# --- FOLDER/FILE CONFIGURATION ---
ASSETS_DIR = 'assets'
FONTS_DIR = os.path.join(ASSETS_DIR, 'fonts')
TEMPLATE_FILE = os.path.join(ASSETS_DIR, 'ticket_template.png')


# --- HELPER FUNCTIONS ---
def generate_unique_student_id():
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
    global students_collection # Use the globally defined collection

    print("--- REQUEST RECEIVED ---")
    if students_collection is None:
        print("ERROR: students_collection is not available. Check server start logs.")
        return jsonify({"error": "Database connection failed at startup."}), 500

    try:
        # 1. Get data from the form
        print("Step 1: Getting form data...")
        student_name = request.form.get('studentName')
        roll_no = request.form.get('rollNo')
        study_year = request.form.get('studyYear')
        profile_image_file = request.files.get('profileImage')
        print("Step 1: Done.")

        if not all([student_name, roll_no, study_year, profile_image_file]):
            print("ERROR: Missing form data.")
            return jsonify({"error": "Missing form data."}), 400

        # 2. Check for duplicate Roll No.
        print(f"Step 2: Checking for duplicate roll_no: {roll_no}...")
        if students_collection.find_one({"roll_no": roll_no}):
            print("ERROR: Duplicate roll_no found.")
            return jsonify({"error": f"Roll Number '{roll_no}' already exists."}), 409
        print("Step 2: Done. No duplicates.")

        # 3. Generate Unique Student ID
        print("Step 3: Generating student ID...")
        generated_student_id = generate_unique_student_id()
        print(f"Step 3: Done. ID: {generated_student_id}")
        
        # 4. Upload Profile Image to Vercel Blob
        print("Step 4: Uploading image to Vercel Blob...")
        filename = f"profile_pics/{generated_student_id}_{profile_image_file.filename}"
        body = profile_image_file.read()
        blob_result = put(blob_name=filename, body=body, access='public')
        profile_pic_url = blob_result['url']
        print("Step 4: Done. Image URL:", profile_pic_url)

        # 5. Save new student data to MongoDB
        print("Step 5: Saving document to MongoDB...")
        new_student_document = {
            "roll_no": roll_no, "student_id": generated_student_id, "name": student_name,
            "year": study_year, "profile_pic_url": profile_pic_url, "status": "Active",
            "registered_at": datetime.utcnow()
        }
        students_collection.insert_one(new_student_document)
        print("Step 5: Done.")

        # 6. Generate the Ticket Image
        print("Step 6: Generating ticket image...")
        template = Image.open(TEMPLATE_FILE).convert("RGBA")
        font_name = ImageFont.truetype(os.path.join(FONTS_DIR, 'Poppins-Bold.ttf'), 48)
        font_details = ImageFont.truetype(os.path.join(FONTS_DIR, 'Poppins-Regular.ttf'), 32)
        response = requests.get(profile_pic_url)
        profile_pic_ticket = Image.open(io.BytesIO(response.content)).resize((180, 180))
        qr_img = qrcode.make(generated_student_id).resize((180, 180))
        
        # Drawing logic... (condensed for brevity)
        card_layer = Image.new('RGBA', template.size, (255, 255, 255, 0))
        draw = ImageDraw.Draw(card_layer)
        card_width, card_height = 800, 300; card_center_x, card_center_y = template.width // 2, template.height // 2
        card_left = card_center_x - card_width // 2; card_top = card_center_y - card_height // 2
        profile_pic_on_card_x = card_left + 25; profile_pic_on_card_y = card_top + 60
        qr_img_on_card_x = card_left + card_width - qr_img.width - 25
        card_layer.paste(profile_pic_ticket, (profile_pic_on_card_x, profile_pic_on_card_y))
        card_layer.paste(qr_img, (qr_img_on_card_x, profile_pic_on_card_y))
        text_start_x = profile_pic_on_card_x + profile_pic_ticket.width + 30
        draw.text((text_start_x, profile_pic_on_card_y + 10), student_name, font=font_name, fill='white')
        draw.text((text_start_x, profile_pic_on_card_y + 70), study_year, font=font_details, fill='#cccccc')
        draw.text((text_start_x, profile_pic_on_card_y + 110), f"ID: {generated_student_id}", font=font_details, fill='#cccccc')
        final_image = Image.alpha_composite(template, card_layer).convert("RGB")
        print("Step 6: Done.")

        # 7. Return the final image
        print("Step 7: Returning image file.")
        img_io = io.BytesIO()
        final_image.save(img_io, 'PNG')
        img_io.seek(0)
        
        return send_file(img_io, mimetype='image/png', as_attachment=True, download_name=f'{generated_student_id}_ticket.png')

    except Exception as e:
        print(f"--- UNEXPECTED ERROR IN REQUEST: {e} ---")
        app.logger.error(f"An error occurred: {e}")
        return jsonify({"error": "An unexpected server error occurred."}), 500

def handler(environ, start_response):
    return app(environ, start_response)