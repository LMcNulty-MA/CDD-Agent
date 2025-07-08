# CDD-agent 
AI-powered agent for help find matching CDD fields or add new fields

## Developer Setup
1. Install [Python 3.13.x](https://www.python.org/downloads/).

2. Clone the repository: git clone https://github.com/moodysanalytics/cdd-agent.

3. Make a copy of .env.example in the root of the directory and name it '.env'
   - Contact the lead developer for the values for all fields that have 'XXX'
    - Ex. 'OPENAI_API_KEY'


4. Create a virtual environment using python 3.13:
   - C:\Users\YOUR_USERNAME_HERE\AppData\Local\Programs\Python\Python313\python.exe -m venv C:\venvs\cdd-agent
   - MAKE SURE TO REPLACE YOUR_USERNAME_HERE ^^

5. Activate the virtual environment:
   - On Windows: .\venv\Scripts\activate. 
      - C:\venvs\cdd-agent\Scripts\activate

6. Install dependencies from requirements:
   - pip install -r requirements.txt

7. Launch API Locally 
    - Navigate to the root of the directory in command prompt and run
        - python -m scripts.start_server

    - Open the API documentation: http://localhost:5000/cdd-agent/web

8. For questions or concerns during setup, please reach out to logan.mcnulty@moodys.com.

## To Build and Run Docker Image Locally
1. Make sure docker is running
2. Navigate to root of the project 'cdd-agent' in command prompt
3. docker build -t cdd-agent .
4. docker run --env-file .env -d --name cdd-agent-container -p 5000:5000 cdd-agent
5. Open docker desktop app and see that the image is running in the 'Containers' tab
6. Navigate to http://localhost:5000/cdd-agent/web


## In order to Authenticate for use via CI 
1. Make sure have a valid SSO token from 
   - https://ci-api.sso.moodysanalytics.net/sso-api/docs/swagger-ui/index.html?url=%2Fsso-api%2Fassets%2Fswagger.json#/SSOAuthentication/passwordCredentialsGrant
2. grant_type = client_credentials
3. Fill in these credentials and submit
   - clientID
   - clientSecret

## About

This AI-powered application maps application fields to existing CDD (Common Data Dictionary) fields or creates new field suggestions.

### How It Works

**Bulk Processing:**
1. Upload an Excel file with a "fields_to_map" tab containing: field_name, cdd_confirmed, context_definition, and cdd_best_guess columns
2. The system processes each field by searching existing CDD database for matches
3. Users can accept suggested matches or request new field creation
4. New field suggestions are saved to a "new_suggested_fields" tab for wiki submission
5. Download the updated file with all mappings and suggestions

**Single Field Processing:**
- Manually input a field name and context for individual field mapping

**Feedback System:**
- Provide feedback at any point to improve matching accuracy or new field suggestions
