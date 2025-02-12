import pymongo
import json
from flask import Flask, request, jsonify
import requests
from werkzeug.security import check_password_hash
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
import secrets
from flask_cors import CORS
from werkzeug.security import generate_password_hash
from bson.objectid import ObjectId
import datetime
import PyPDF2
import docx


app = Flask(__name__)
CORS(app)
secret_key = secrets.token_urlsafe(32)
app.config['JWT_SECRET_KEY'] = "BSOXl7U6DC8BA8M22QLE55d6Y-8S0TSFlRIge5_inuQ"
jwt = JWTManager(app)

states = [
    "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado", "Connecticut",
    "Delaware", "Florida", "Georgia", "Hawaii", "Idaho", "Illinois", "Indiana", "Iowa",
    "Kansas", "Kentucky", "Louisiana", "Maine", "Maryland", "Massachusetts", "Michigan",
    "Minnesota", "Mississippi", "Missouri", "Montana", "Nebraska", "Nevada", "New Hampshire",
    "New Jersey", "New Mexico", "New York", "North Carolina", "North Dakota", "Ohio", "Oklahoma",
    "Oregon", "Pennsylvania", "Rhode Island", "South Carolina", "South Dakota", "Tennessee",
    "Texas", "Utah", "Vermont", "Virginia", "Washington", "West Virginia", "Wisconsin", "Wyoming",
    "Larnaca", "Limassol", "Nicosia", "Paphos", "Famagusta"
]

def jaccard_similarity(set1, set2):
    intersection = len(set1 & set2)
    union = len(set1 | set2)
    return intersection / union

def initialize_connection_users():
    client = pymongo.MongoClient("mongodb://localhost:27018", 
                                username='root',
                                password='password')
    db = client["mongodbUsers"]
    collection = db["users"]
    return collection , client

def initialize_connection_jobs():
    client = pymongo.MongoClient("mongodb://localhost:27017", 
                                username='root',
                                password='password')
    db = client["mongodb"]
    collection = db["jobs"]
    return collection , client


@app.route('/post-data', methods=['POST'])
def post_data():
    data = request.json
    collection, client = initialize_connection_jobs()
    collection.insert_many(data)
    client.close()
    return "Data inserted successfully"

@app.route('/get-results', methods=['POST'])
def get_results():
    data = request.json
    collection, client = initialize_connection_jobs()

    # Specify the desired "Location" value to match
    query_builder = {}
    # Check if the "Location" field in data is not empty
    if data.get("Location"):
        query_builder["Location"] = {"$in": data["Location"]}

    # Check if the "Company" field in data is not empty
    if data.get("Company") != "None":
        query_builder["Company"] = data["Company"]

    # Check if the "Employment Type" field in data is not empty
    if data.get("Employment Type"):
        query_builder["$or"] = [
            {"Employment Type": {"$in": data["Employment Type"]}},
            {"Employment Type": ""}
        ]

    # Check if the "Years of Exp" field in data is not empty
    if data.get("Years of Exp"):
        query_builder["$or"] = [
            {"Years of Exp": {"$lte": data["Years of Exp"]}},
            {"Years of Exp": "not given"}
        ]

    # Check if the "Education Level" field in data is not empty
    if data.get("Education Level"):
        query_builder["$or"] = [
            {"Education Level": {"$in": data["Education Level"]}},
            {"Education Level": ""}
        ]

    # Check if the "Education Type" field in data is not empty
    #if data.get("Education Type"):
    #    query_builder["Hard Skills"] = {"$in": data["Education Type"]}

    matching_entries = collection.find(query_builder)


    similar_documents = []

    for entry in matching_entries:
        document_hard_skills = set(entry.get("Hard Skills", []))  # Extract the "Hard Skills" field from the document
        document_soft_skills = set(entry.get("Soft Skills", []))  # Extract the "Soft Skills" field from the document
        hard_skill_similarity = jaccard_similarity(set(data["Hard Skills"]), document_hard_skills)
        soft_skill_similarity = jaccard_similarity(set(data["Soft Skills"]), document_soft_skills)
        if hard_skill_similarity >= 0.2 and soft_skill_similarity >= 0.2:  # Check if the similarity is at least 50%
            similar_documents.append(entry)
        elif hard_skill_similarity >= 0.2 and document_soft_skills == set([]):
            similar_documents.append(entry)
        elif soft_skill_similarity >= 0.2 and document_hard_skills == set([]):
            similar_documents.append(entry)
        elif document_soft_skills == set([]) and document_hard_skills == set([]):
            similar_documents.append(entry)


    matching_entries_list = list(similar_documents)
    urls = [entry['URL'] for entry in matching_entries_list]
    json_result = json.dumps(urls, default=str, indent=4)
    client.close()

    return json_result

@app.route('/login', methods=['POST'])
def login():
    email = request.json.get('email', None)
    password = request.json.get('password', None)
    collection, client = initialize_connection_users()
    user = collection.find_one({"_id": email})

    if user['_id'] == email and check_password_hash(user['password'], password):
        # Create JWT token
        access_token = create_access_token(identity=user['_id'])
        client.close()
        return jsonify(access_token=access_token), 200
    
    client.close()
    return jsonify({"msg": "Bad username or password"}), 401

@app.route('/register', methods=['POST'])
def register():
    data = request.json
    username = data.get('username')
    email = data.get('email')
    password = data.get('password')
    collection, client = initialize_connection_users()
    user = collection.find_one({"_id": email})

    if user:
        client.close()
        return jsonify({"message": "Email already in use"}), 400

    # Hash password and create new user
    hashed_password = generate_password_hash(password)
    data = {
        "_id": email,
        "username": username,
        "password": hashed_password,
        "results": [],
        "action": "",
        "info_location": [],
        "info_job_type": [],
        "info_company": [],
        "info_years_of_exp": [],
        "info_education_level": [],
        "info_education_type": [],
        "info_soft_skills": [],
        "info_hard_skills": [],
        "cv_hard_skills": [],
        "cv_soft_skills": [],
        "github_hard_skills": [],
        "github_location": "None",
    }
    collection.insert_one(data)

    client.close()
    return jsonify({"message": "Registration successful"}), 201

@app.route('/delete-users', methods=['DELETE'])
def delete_users():
    collection, client = initialize_connection_users()
    collection.delete_many({})
    client.close()
    return "Data deleted successfully"

@app.route('/api/messages', methods=['POST'])
@jwt_required()
def send_to_rasa():
    user_identity = get_jwt_identity()
    message_data = request.json.get('message')

    # Your Rasa endpoint
    rasa_endpoint = 'http://localhost:5005/webhooks/rest/webhook'

    # Forward the message to Rasa
    response = requests.post(rasa_endpoint, json={
        'sender': user_identity,  # Using the JWT identity as the sender
        'message': message_data,
    })

    if response.ok:
        # Return Rasa's response back to the client
        return jsonify(response.json()), 200
    else:
        return jsonify({'message': 'Failed to communicate with Rasa.'}), 500

@app.route('/get-username', methods=['GET'])
@jwt_required()
def get_username():
    user_identity = get_jwt_identity()
    collection, client = initialize_connection_users()
    user = collection.find_one({"_id": user_identity})
    client.close()
    return jsonify(user['username']), 200

@app.route('/save-chat', methods=['POST'])
@jwt_required()
def save_chat():
    user_email = get_jwt_identity()
    data = request.json
    chat = {
        "chatId": str(ObjectId()), # Generates a unique ID for the chat
        "date": datetime.datetime.utcnow().isoformat(),
        "messages": data['messages']
    }

    collection, client = initialize_connection_users()

    # Update the user's document to push the new chat into the results array
    collection.update_one(
        {"_id": user_email},
        {"$push": {"results": chat}}
    )

    client.close()

    return jsonify({"message": "Chat saved successfully"}), 200

@app.route('/api/sessions', methods=['GET'])
@jwt_required()
def get_sessions():
    collection, client = initialize_connection_users()
    current_user = get_jwt_identity()  # Get the identity of the current user
    user_sessions = collection.find_one({"_id": current_user}, {"results": 1, "_id": 0})
    
    if not user_sessions:
        client.close()  # Ensure you close the client connection
        return jsonify({"msg": "No sessions found"}), 404

    client.close()  # Ensure you close the client connection
    return jsonify(user_sessions["results"]), 200

@app.route('/api/chat/<chatId>', methods=['GET'])
@jwt_required()
def get_chat_by_chatId(chatId):
    user_identity = get_jwt_identity()
    collection, client = initialize_connection_users()

    # Find the user document
    user_document = collection.find_one({"_id": user_identity})
    

    if user_document:
        # Iterate through the results to find the matching chatId
        for result in user_document.get('results', []):
            if result.get('chatId') == chatId:
                return jsonify(result.get('messages')), 200
        return jsonify({"msg": "Chat session not found"}), 404
    else:
        return jsonify({"msg": "User not found"}), 404

@app.route('/api/chat/<chatId>', methods=['DELETE'])
@jwt_required()
def delete_chat_by_chatId(chatId):
    user_identity = get_jwt_identity()
    collection, client = initialize_connection_users()

    # Attempt to update the user's document by pulling the chat session from the results array
    update_result = collection.update_one(
        {"_id": user_identity},
        {"$pull": {"results": {"chatId": chatId}}}
    )

    if update_result.modified_count > 0:
        # If the update modified a document, the chat session was successfully deleted
        return jsonify({"msg": "Chat session deleted successfully"}), 200
    else:
        # If no documents were modified, the chat session was not found for the user
        return jsonify({"msg": "Chat session not found"}), 404

@app.route('/api/change-password', methods=['POST'])
@jwt_required()
def change_password():
    user_identity = get_jwt_identity()
    collection, client = initialize_connection_users()
    data = request.json

    # Retrieve the user from the database
    user = collection.find_one({"_id": user_identity})  # Assuming username is unique and provided

    if user:
        # Verify the old password
        if check_password_hash(user["password"], data["oldPassword"]):
            # Hash the new password before storing it
            hashed_password = generate_password_hash(data["newPassword"])

            # Update the user's password in the database
            collection.update_one(
                {"_id": user_identity},
                {"$set": {"password": hashed_password}}
            )

            return jsonify({"message": "Password updated successfully"}), 200
        else:
            return jsonify({"error": "Old password is incorrect"}), 400
    else:
        return jsonify({"error": "User not found"}), 404

@app.route('/api/change-username', methods=['POST'])
@jwt_required()
def change_username():
    user_identity = get_jwt_identity()
    collection, client = initialize_connection_users()
    data = request.json

    # Retrieve the user from the database
    user = collection.find_one({"_id": user_identity})  # Assuming username is unique and provided

    if user:
        # Verify the old username
        if user["username"].lower() == data["oldUsername"].lower():

            # Update the user's username in the database
            collection.update_one(
                {"_id": user_identity},
                {"$set": {"username": data["newUsername"]}}
            )

            return jsonify({"message": "Username updated successfully"}), 200
        else:
            return jsonify({"error": "Old username is incorrect"}), 400
    else:
        return jsonify({"error": "User not found"}), 404
    
@app.route('/action/<user_id>/<action>', methods=['POST'])
def info_action(user_id, action):
    collection, client = initialize_connection_users()
    collection.update_one(
        {"_id": user_id},
        {"$set": {"action": action}}
    )
    client.close()
    return "Action updated successfully", 200

@app.route('/info_location/<user_id>', methods=['POST'])
def info_location(user_id):
    collection, client = initialize_connection_users()
    data = request.json
    collection.update_one(
        {"_id": user_id},
        {"$set": {"info_location": data['location']}}
    )
    client.close()
    return "Info location updated successfully", 200

@app.route('/info_job_type/<user_id>', methods=['POST'])
def info_job_type(user_id):
    collection, client = initialize_connection_users()
    data = request.json
    collection.update_one(
        {"_id": user_id},
        {"$set": {"info_job_type": data["job_type"]}}
    )
    client.close()
    return "Info job type updated successfully", 200

@app.route('/info_company/<user_id>', methods=['POST'])
def info_company(user_id):
    collection, client = initialize_connection_users()
    data = request.json
    collection.update_one(
        {"_id": user_id},
        {"$set": {"info_company": data["company"]}}
    )
    client.close()
    return "Info company updated successfully", 200

@app.route('/info_years_of_exp/<user_id>', methods=['POST'])
def info_years_of_exp(user_id):
    collection, client = initialize_connection_users()
    data = request.json
    collection.update_one(
        {"_id": user_id},
        {"$set": {"info_years_of_exp": data["years_of_exp"]}}
    )
    client.close()
    return "Info years of experience updated successfully", 200

@app.route('/info_education/<user_id>', methods=['POST'])
def info_education(user_id):
    collection, client = initialize_connection_users()
    data = request.json
    collection.update_one(
        {"_id": user_id},
        {"$set": {"info_education_level": data["education_level"], "info_education_type": data["education_type"]}}
    )
    client.close()
    return "Info education updated successfully", 200


@app.route('/info_soft_skills/<user_id>', methods=['POST'])
def info_soft_skills(user_id):
    collection, client = initialize_connection_users()
    data = request.json
    collection.update_one(
        {"_id": user_id},
        {"$set": {"info_soft_skills": data["soft_skills"]}}
    )
    user_doc = collection.find_one({"_id": user_id})
    cv_soft_skills = user_doc.get("cv_soft_skills", [])
    for skill in cv_soft_skills:
        collection.update_one(
            {"_id": user_id},
            {"$addToSet": {"info_soft_skills": skill}}
        )
    client.close()
    return "Info soft skills updated successfully", 200

@app.route('/info_hard_skills/<user_id>', methods=['POST'])
def info_hard_skills(user_id):
    collection, client = initialize_connection_users()
    data = request.json
    collection.update_one(
        {"_id": user_id},
        {"$set": {"info_hard_skills": data["hard_skills"]}}
    )
    user_doc = collection.find_one({"_id": user_id})
    cv_hard_skills = user_doc.get("cv_hard_skills", [])
    for skill in cv_hard_skills:
        collection.update_one(
            {"_id": user_id},
            {"$addToSet": {"info_hard_skills": skill}}
        )
    github_hard_skills = user_doc.get("github_hard_skills", [])
    for skill in github_hard_skills:
        collection.update_one(
            {"_id": user_id},
            {"$addToSet": {"info_hard_skills": skill}}
        )
    client.close()
    return "Info hard skills updated successfully", 200

def get_github_user_languages(username):
        repos_url = f'https://api.github.com/users/{username}/repos'
        languages = set()

        try:
            # Fetch the list of repositories for the given user
            repos_response = requests.get(repos_url)
            repos_response.raise_for_status()  # Raise an exception for HTTP errors
            repos = repos_response.json()
            print(repos)
            for repo in repos:
                # Fetch the languages for each repository
                languages_url = repo['languages_url']
                languages_response = requests.get(languages_url)
                repo_languages = languages_response.json()

                # Add the languages to the set
                languages.update(repo_languages.keys())

            url = f'https://api.github.com/users/{username}'
            headers = {'Accept': 'application/vnd.github.v3+json'}
            try:
                response = requests.get(url, headers=headers)
                response.raise_for_status()  # Raise an exception for 4xx or 5xx status codes
                user_data = response.json()
                location = user_data.get('location')
                split_chars = [',', ' ', '-']
                words = [word.strip() for char in split_chars for word in location.split(char)]
                words = list(filter(None, words))
                location_detected = "None"
                for word in words:
                    if word in states:
                        location_detected = word
            except requests.exceptions.RequestException as e:
                print(f"Error fetching user data: {e}")
                location_detected = "None"

                
        except requests.RequestException as e:
            print(f'Error fetching data from GitHub API: {e}')
            return [], "None"

        return list(languages), location_detected

@app.route('/info_github', methods=['POST'])
@jwt_required()
def info_github():
    user_identity = get_jwt_identity()
    collection, client = initialize_connection_users()
    data = request.json
    github, location = get_github_user_languages(data["username"])
    collection.update_one(
        {"_id": user_identity},
        {"$set": {"github_hard_skills":  github}}
    )
    collection.update_one(
        {"_id": user_identity},
        {"$set": {"github_location":  location}}
    )
    client.close()
    return github, 200

@app.route('/get_github', methods=['GET'])
@jwt_required()
def get_github():
    user_identity = get_jwt_identity()
    collection, client = initialize_connection_users()
    user = collection.find_one({"_id": user_identity})
    client.close()
    return jsonify(user['github_hard_skills']), 200

@app.route('/get_rasa/<user_id>', methods=['GET'])
def get_rasa(user_id):
    collection, client = initialize_connection_users()
    user = collection.find_one({"_id": user_id})
    # Update the user's document to set the info_location field
    
    client.close()
    return jsonify({"info_location": user["info_location"],
                    "info_job_type": user["info_job_type"],
                    "info_company": user["info_company"],
                    "info_years_of_exp": user["info_years_of_exp"],
                    "info_education_level": user["info_education_level"],
                    "info_education_type": user["info_education_type"],
                    "info_soft_skills": user["info_soft_skills"],
                    "info_hard_skills": user["info_hard_skills"]}), 200
    
@app.route('/reset_rasa/<user_id>', methods=['POST'])
def reset_rasa(user_id):
    collection, client = initialize_connection_users()
    collection.update_one(
        {"_id": user_id},
        {"$set": {"action": "", 
                  "info_location": [], 
                  "info_job_type": [], 
                  "info_company": [], 
                  "info_years_of_exp": [], 
                  "info_education_level": [], 
                  "info_education_type": [], 
                  "info_soft_skills": [], 
                  "info_hard_skills": []}}
    )
    client.close()
    return "Rasa reset successfully", 200

@app.route('/reset_rasa', methods=['POST'])
@jwt_required()
def reset():
    user_identity = get_jwt_identity()
    collection, client = initialize_connection_users()
    collection.update_one(
        {"_id": user_identity},
        {"$set": {"action": "", 
                  "info_location": [], 
                  "info_job_type": [], 
                  "info_company": [], 
                  "info_years_of_exp": [], 
                  "info_education_level": [], 
                  "info_education_type": [], 
                  "info_soft_skills": [], 
                  "info_hard_skills": []}}
    )
    client.close()
    return "Rasa reset successfully", 200

@app.route('/get_action/<user_id>', methods=['GET'])
def get_action(user_id):
    collection, client = initialize_connection_users()
    user = collection.find_one({"_id": user_id})
    client.close()
    return jsonify(user['action']), 200

def authentication():
    url = "https://auth.emsicloud.com/connect/token"

    payload = "client_id=qn2hk51fh4z9vzcj&client_secret=8YkRlh2e&grant_type=client_credentials&scope=emsi_open"
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}

    response = requests.request("POST", url, data=payload, headers=headers)

    if response.status_code == 200:
        data = response.json()
        access_token = data['access_token']
        return access_token
    else:
        print("Error:", response.status_code, response.text)

def extract_skills(access_token, text):
    url_emis = "https://emsiservices.com/skills/versions/latest/extract"

    payload = json.dumps({
        "text": f"""{ text }""",
        "confidenceThreshold": 0.6
    })
    headers = {
        'Authorization': f"Bearer {access_token}",
        'Content-Type': "application/json"
        }
    response = requests.request("POST", url_emis, data=payload, headers=headers)

    # Parse the JSON data
    emis_data = json.loads(response.text)

    # Create a dictionary to store skill names and their corresponding type names
    skill_type_mapping = {}

    # Extract skill names and type names
    for item in emis_data["data"]:
        if "skill" in item:
            skill = item["skill"]
            if "name" in skill:
                skill_name = skill["name"]
                if "type" in skill:
                    type_name = skill["type"]["name"]
                    skill_type_mapping[skill_name] = type_name

    hard_skills = []
    soft_skills = []

    for skill_name, type_name in skill_type_mapping.items():
        if type_name == "Common Skill":
            soft_skills.append(skill_name)
        else:
            hard_skills.append(skill_name)
    return hard_skills, soft_skills

def allowed_file(filename):
    ALLOWED_EXTENSIONS = {'pdf', 'docx'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def extract_file_text(file):
    extension = file.filename.rsplit('.', 1)[1].lower()
    if extension == 'pdf':
        return extract_text_from_pdf(file)
    elif extension == 'docx':
        return extract_text_from_docx(file)

def extract_text_from_pdf(file):
    reader = PyPDF2.PdfReader(file)
    text = []
    for page in reader.pages:
        text.append(page.extract_text())
    hard_skills, soft_skills = extract_skills(authentication(), text)
    skills_data = {
        'hard_skills': hard_skills,
        'soft_skills': soft_skills
    }
    return skills_data

def extract_text_from_docx(file):
    doc = docx.Document(file)
    text = [paragraph.text for paragraph in doc.paragraphs]
    hard_skills, soft_skills = extract_skills(authentication(), text)
    skills_data = {
        'hard_skills': hard_skills,
        'soft_skills': soft_skills
    }
    return skills_data

@app.route('/analyse-text', methods=['POST'])
@jwt_required()
def extract_text():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    if file and allowed_file(file.filename):
        try:
            skills_data = extract_file_text(file)
            user_email = get_jwt_identity()
            collection, client = initialize_connection_users()
            collection.update_one(
                {"_id": user_email},
                {"$set": {"cv_hard_skills": skills_data['hard_skills'], "cv_soft_skills": skills_data['soft_skills']}}
            )
            client.close()
            return jsonify(skills_data), 200
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    else:
        return jsonify({'error': 'Unsupported file type'}), 400

@app.route('/get-cv-soft-skills', methods=['GET'])
@jwt_required()
def get_cv_soft_skills():
    user_email = get_jwt_identity()
    collection, client = initialize_connection_users()
    user = collection.find_one({"_id": user_email})
    client.close()
    return jsonify(user['cv_soft_skills']), 200

@app.route('/get-cv-hard-skills', methods=['GET'])
@jwt_required()
def get_cv_hard_skills():
    user_email = get_jwt_identity()
    collection, client = initialize_connection_users()
    user = collection.find_one({"_id": user_email})
    client.close()
    return jsonify(user['cv_hard_skills']), 200

@app.route('/get-github-location/<user_id>', methods=['GET'])
def get_github_location(user_id):
    collection, client = initialize_connection_users()
    user = collection.find_one({"_id": user_id})
    client.close()
    return jsonify(user['github_location']), 200

@app.route('/set_github_location/<user_id>', methods=['POST'])
def set_github_location(user_id):
    collection, client = initialize_connection_users()
    data = request.json
    collection.update_one(
        {"_id": user_id},
        {"$set": {"github_location": data["location"]}}
    )
    client.close()
    return "Github location updated successfully", 200


if __name__ == '__main__':
    app.run(debug=True)
