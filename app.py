import os
import requests
from flask import Flask, render_template, request
from datetime import datetime
from elasticsearch import Elasticsearch

app = Flask(__name__)

# Set paths and configurations
UPLOAD_FOLDER = os.path.abspath('/home/vboxuser/mini-project/flask')
LOGSTASH_CONFIG_PATH = os.path.abspath('/home/vboxuser/mini-project/logstash_config.conf')
ALLOWED_EXTENSIONS = {'txt', 'csv', 'log'}
ELASTICSEARCH_HOST = 'http://localhost:9200'
KIBANA_HOST = 'http://localhost:5601'

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Initialize Elasticsearch client
es = Elasticsearch(hosts=[ELASTICSEARCH_HOST])




def fetch_dashboards():
    try:
        dashboards = []
        page = 1
        per_page = 100  # Adjust based on the number of dashboards you have
        
        while True:
            # Query Kibana saved objects for dashboards with pagination
            url = f"{KIBANA_HOST}/api/saved_objects/_find?type=dashboard&page={page}&per_page={per_page}"
            headers = {"kbn-xsrf": "true"}
            response = requests.get(url, headers=headers)
            response.raise_for_status()  # Raise an exception for bad responses
            data = response.json()

            # Append the current page of dashboards to the list
            dashboards.extend(data.get("saved_objects", []))

            # Check if we've reached the last page
            if len(data.get("saved_objects", [])) < per_page:
                break

            # Increment the page number for the next request
            page += 1
        
        return dashboards

    except Exception as e:
        print(f"Error fetching dashboards: {e}")
        return []


        



@app.route('/upload')
def upload():
    return render_template('upload.html')
    
    
            
        
# Function to check allowed file extensions
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Function to fetch all dashboards from Kibana

# Function to append dynamically to Logstash config
def append_to_logstash(filepath):
    try:
        logstash_block = f"""
    file {{
        path => "{filepath}"
        start_position => "beginning"
        sincedb_path => "/dev/null"
    }}
        """
        with open(LOGSTASH_CONFIG_PATH, 'r+') as logstash_file:
            content = logstash_file.read()
            placeholder = "# Placeholder for dynamically added inputs"
            if placeholder not in content:
                raise ValueError(f"Placeholder '{placeholder}' not found in Logstash configuration")
            content = content.replace(placeholder, logstash_block + "\n  " + placeholder)
            logstash_file.seek(0)
            logstash_file.write(content)
            logstash_file.truncate()
    except Exception as e:
        raise RuntimeError(f"Failed to update Logstash configuration: {str(e)}")

# Function to add file to Elasticsearch and create Kibana index pattern
def add_file_to_elasticsearch(index_name, file_path):
    try:
        # Prepare file metadata
        file_metadata = {
            "filename": os.path.basename(file_path),
            "path": file_path,
            "uploaded_at": datetime.now().isoformat()
        }
        
        # Index metadata in Elasticsearch
        es.index(index=index_name, document=file_metadata)

        # Create a Kibana index pattern
        create_kibana_index_pattern(index_name)
    except Exception as e:
        raise RuntimeError(f"Failed to index file metadata in Elasticsearch: {str(e)}")

# Function to create Kibana index pattern
def create_kibana_index_pattern(index_name):
    try:
        # Prepare the Kibana index pattern payload
        payload = {
            "attributes": {
                "title": index_name,
                "timeFieldName": "uploaded_at"
            }
        }
        
        # Send a POST request to Kibana's Saved Objects API
        headers = {"kbn-xsrf": "true"}  # Required header for Kibana API
        response = requests.post(
            f"{KIBANA_HOST}/api/saved_objects/index-pattern",
            json=payload,
            headers=headers
        )
        
        if response.status_code == 200 or response.status_code == 201:
            print(f"Index pattern '{index_name}' created successfully in Kibana.")
        else:
            print(f"Failed to create index pattern in Kibana: {response.text}")
    except Exception as e:
        raise RuntimeError(f"Failed to create Kibana index pattern: {str(e)}")

# Route to render the upload form
@app.route('/')
def index():
    # Fetch all dashboards
    dashboards = fetch_dashboards()
    return render_template('dashboards.html', dashboards=dashboards)

# Route to handle file upload
@app.route('/upload', methods=['POST'])
def upload_file():
    try:
        if 'file' not in request.files:
            return "No file part in the request", 400
        
        file = request.files['file']
        if file.filename == '':
            return "No file selected", 400

        if file and allowed_file(file.filename):
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)

            # Check if the file already exists in the directory
            if os.path.exists(filepath):
                return "File already exists, please choose a different file", 400

            file.save(filepath)

            # Dynamically set the index name as the file name (without extension)
            index_name = os.path.splitext(file.filename)[0]

            # Update Logstash configuration
            append_to_logstash(filepath)

            # Index metadata in Elasticsearch and create Kibana index pattern
            add_file_to_elasticsearch(index_name, filepath)

            return f"File uploaded and indexed successfully: {filepath}", 200
        else:
            return "File type not allowed", 400
    except Exception as e:
        return f"An error occurred: {str(e)}", 500

# Route to display a specific Kibana dashboard
@app.route('/dashboard/<dashboard_id>')
def dashboard(dashboard_id):
    try:
        # Fetch details of a specific dashboard using its ID
        url = f"{KIBANA_HOST}/api/saved_objects/dashboard/{dashboard_id}"
        headers = {"kbn-xsrf": "true"}
        response = requests.get(url, headers=headers)
        response.raise_for_status()  # Raise an exception for bad responses
        
        # Get the dashboard data (already parsed from JSON)
        dashboard_data = response.json()

        # Construct the URL for embedding the dashboard
        dashboard_url = f"{KIBANA_HOST}/app/kibana#/dashboard/{dashboard_id}"
        
        # Pass the dashboard data and URL to the template
        return render_template('dashboard_detail.html', dashboard=dashboard_data, dashboard_url=dashboard_url)

    except requests.exceptions.HTTPError as http_err:
        print(f"HTTP error occurred: {http_err}")
        return f"HTTP error occurred: {http_err}", 500
    except Exception as e:
        print(f"Error fetching dashboard details: {e}")
        return f"Error fetching dashboard details: {str(e)}", 500






if __name__ == '__main__':
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    app.run(debug=True)

