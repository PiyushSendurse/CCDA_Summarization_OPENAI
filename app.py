
import os
import openai
import xml.etree.ElementTree as ET

from flask import Flask, request, render_template, jsonify
from flask_cors import CORS  # Import the CORS module

app = Flask(__name__)
CORS(app)  # Enable CORS for the app
# Define namespaces
namespaces = {
    'default': 'urn:hl7-org:v3',
    'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
    'sdtc': 'urn:hl7-org:sdtc'
}

from dotenv import load_dotenv
load_dotenv()
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY

uploaded_xml_path = None
def extract_section_names(xml_path):
    # Parse the XML file
    tree = ET.parse(xml_path)
    root = tree.getroot()

    # Extract section names
    section_names = []
    for section in root.findall(".//default:section", namespaces=namespaces):
        title_element = section.find("default:title", namespaces=namespaces)
        if title_element is not None:
            section_names.append(title_element.text)
    return section_names

def extract_section_data(xml_path, section_name):
    # Parse the XML file
    tree = ET.parse(xml_path)
    root = tree.getroot()

    # Search for the section by its title
    for section in root.findall(".//default:section", namespaces=namespaces):
        title_element = section.find("default:title", namespaces=namespaces)
        if title_element is not None and title_element.text == section_name:
            # Convert the section subtree to a formatted XML string
            return ET.tostring(section, encoding="unicode", method="xml")
    return "Section not found"

def xml_to_readable(section_xml):
    section = ET.fromstring(section_xml)

    output = []

    title_element = section.find("default:title", namespaces=namespaces)
    if title_element is not None:
        output.append(title_element.text)
        output.append('-' * len(title_element.text))

    for table in section.findall(".//default:table", namespaces=namespaces):
        headers = [th.text for th in table.findall(".//default:thead/default:tr/default:th", namespaces=namespaces)]
        output.append(' | '.join(headers))
        output.append('-' * (sum([len(header) for header in headers]) + len(headers) * 3 - 2))

        for row in table.findall(".//default:tbody/default:tr", namespaces=namespaces):
            row_data = [td.text if td.text else ' '.join(td.itertext()) for td in
                        row.findall(".//default:td", namespaces=namespaces)]
            output.append(' | '.join(row_data))

        output.append('')

    return '\n'.join(output)


@app.route("/", methods=['GET'])
def hello():
    return jsonify("CCDA Summarization")

@app.route("/upload", methods=["POST"])
def index():
    global uploaded_xml_path  # Access the global variable
    xml_file = request.files.get("xml_file")

    if xml_file is None:
        return jsonify({"error": "No file uploaded."}), 400

    # Check if the uploaded file is in XML format
    if not xml_file.filename.lower().endswith(".xml"):
        return jsonify({"error": "Uploaded file is not in XML format."}), 400

    print("Inside upload method")
    uploaded_xml_path = os.path.join("files", xml_file.filename)
    xml_file.save(uploaded_xml_path)
    print("Inside upload method file saved")

    if uploaded_xml_path:
        sections_with_data = extract_sections_with_data(uploaded_xml_path)
        empty_section_threshold = 10  # Define the threshold for empty sections
        if len(sections_with_data) >= empty_section_threshold:
            message = "Uploaded file does not have much relevant data to work with. Kindly contact our technical team for assistance"
            return jsonify({"message": message})

    return jsonify("XML file uploaded successfully!"), 200


@app.route("/get_sections_with_data", methods=["GET"])
def get_sections_with_data():
    global uploaded_xml_path  # Access the global variable
    if uploaded_xml_path:
        sections_with_data = extract_sections_with_data(uploaded_xml_path)
        return jsonify({"sections_with_data": sections_with_data})
    else:
        return jsonify({"message": "No uploaded XML file found."})


def extract_sections_with_data(xml_path):
    tree = ET.parse(xml_path)
    root = tree.getroot()

    sections_with_data = []
    for section in root.findall(".//default:section", namespaces=namespaces):
        if section_has_data(section):
            title_element = section.find("default:title", namespaces=namespaces)
            if title_element is not None:
                if not section_has_none_recorded_data(section):
                    sections_with_data.append(title_element.text)

    return sections_with_data


def section_has_data(section):
    # Check if the section has a <table> element inside it
    table_element = section.find(".//default:table", namespaces=namespaces)
    return table_element is not None


def section_has_none_recorded_data(section):
    # Check if the section's table contains 'None Recorded' data
    table_element = section.find(".//default:table", namespaces=namespaces)
    if table_element is not None:
        for row in table_element.findall(".//default:tbody/default:tr", namespaces=namespaces):
            for td in row.findall(".//default:td", namespaces=namespaces):
                if td.text == "None Recorded":
                    return True
    return False







def extract_all_table_data(section_name, root):
    data = []

    # Find the section by its title
    for section in root.findall(".//default:section", namespaces=namespaces):
        title_element = section.find("default:title", namespaces=namespaces)
        if title_element is not None and title_element.text == section_name:

            # Iterate over each table in the section
            for table in section.findall(".//default:table", namespaces=namespaces):
                table_data = []

                # Iterate over each row in the table
                for row in table.findall(".//default:tbody/default:tr", namespaces=namespaces):
                    row_data = []

                    # Extract data from each cell, handling nested <content> elements
                    for td in row.findall(".//default:td", namespaces=namespaces):
                        content = td.find(".//default:content", namespaces=namespaces)
                        if content is not None and content.text is not None:
                            row_data.append(content.text.strip())
                        else:
                            row_data.append(td.text.strip() if td.text else ' '.join(td.itertext()))

                    table_data.append(row_data)

                data.append(table_data)

    return data



# Generate a summary using OpenAI API

def generate_summary(data):
    # Process data as needed to create a suitable prompt
    section_prompt = ""

    if "Medical_History" in data:
        medical_history_data = data["Medical_History"]
        yes_responses = [entry for entry in medical_history_data if entry[1].lower() == "y"]
        if yes_responses:
            section_prompt = "The individual has the following medical conditions with 'yes' responses:\n"
            for condition in yes_responses:
                section_prompt += f"- {condition[0]}\n"
        else:
            section_prompt = "The individual has no medical conditions with 'yes' responses."
    else:
        # Use your default prompt for other sections
        #section_prompt = f"Summarize the data in the section:\n{data}"
        section_prompt = f"Set random seed: 42\nSummarize the following data:\n{data}"

    # Create a prompt for summarization
    prompt = f"Summarize the following data:\n{section_prompt}"

    # Use OpenAI API for summarization
    response = openai.Completion.create(
        engine="text-davinci-003",
        prompt=prompt,
        max_tokens=200,
        temperature=0.2
    )

    return response.choices[0].text.strip()


@app.route("/summarize_selected_sections", methods=["POST"])
def summarize_selected_sections():
    global uploaded_xml_path

    if not uploaded_xml_path:
        return jsonify({"message": "No uploaded XML file found."})

    # Get the selected sections from the frontend
    selected_sections = request.json.get("selected_sections")


    # Parse the XML file
    tree = ET.parse(uploaded_xml_path)
    root = tree.getroot()  # Get the root element

    section_summaries = {}
    for section_name in selected_sections:
        section_data = extract_all_table_data(uploaded_xml_path,section_name, root)  # Pass the 'root' element
        section_summary = generate_summary(section_data)
        section_summaries[section_name] = section_summary

    return jsonify({"section_summaries": section_summaries})


def extract_personal_info(xml_path):
    tree = ET.parse(xml_path)
    root = tree.getroot()

    personal_info = {}

    patient_element = root.find(".//default:patient", namespaces=namespaces)
    if patient_element is not None:
        personal_info["Name"] = patient_element.find(".//default:name/default:given",
                                                     namespaces=namespaces).text + " " + patient_element.find(
            ".//default:name/default:family", namespaces=namespaces).text
        personal_info["Gender"] = patient_element.find(".//default:administrativeGenderCode",
                                                       namespaces=namespaces).get("displayName")
        personal_info["Birthdate"] = patient_element.find(".//default:birthTime", namespaces=namespaces).get("value")
        personal_info["Marital Status"] = patient_element.find(".//default:maritalStatusCode",
                                                               namespaces=namespaces).get("displayName")

    patient_role_element = root.find(".//default:patientRole", namespaces=namespaces)
    if patient_role_element is not None:
        id_element = patient_role_element.find(".//default:id", namespaces=namespaces)
        if id_element is not None:
            personal_info["Patient-ID"] = {
                "extension": id_element.get("extension"),
                "root": id_element.get("root")
            }

        hp_address = patient_role_element.find(".//default:addr[@use='HP']", namespaces=namespaces)
        pst_address = patient_role_element.find(".//default:addr[@use='PST']", namespaces=namespaces)

        if hp_address is not None:
            personal_info["Contact Details"] = {
                "HP": {
                    "streetAddressLine": hp_address.find("default:streetAddressLine", namespaces=namespaces).text,
                    "city": hp_address.find("default:city", namespaces=namespaces).text,
                    "state": hp_address.find("default:state", namespaces=namespaces).text,
                    "postalCode": hp_address.find("default:postalCode", namespaces=namespaces).text,
                    "country": hp_address.find("default:country", namespaces=namespaces).text
                }
            }
        if pst_address is not None:
            personal_info["Contact Details"]["PST"] = {
                "streetAddressLine": pst_address.find("default:streetAddressLine", namespaces=namespaces).text,
                "city": pst_address.find("default:city", namespaces=namespaces).text,
                "state": pst_address.find("default:state", namespaces=namespaces).text,
                "postalCode": pst_address.find("default:postalCode", namespaces=namespaces).text,
                "country": pst_address.find("default:country", namespaces=namespaces).text
            }

    return personal_info

@app.route("/extract_personal_details", methods=["GET"])
def extract_personal_details():
    global uploaded_xml_path

    if not uploaded_xml_path:
        return jsonify({"message": "No uploaded XML file found."})

    personal_details = extract_personal_info(uploaded_xml_path)

    formatted_output = {
        "Name": personal_details["Name"],
        "Gender": personal_details["Gender"],
        "Birthdate": personal_details["Birthdate"],
        "Marital_Status": personal_details["Marital Status"],
        "Patient-ID": personal_details.get("Patient-ID", {}),
        "Contact_Details": personal_details.get("Contact Details", {})
    }

    return jsonify({"personal_details": formatted_output})


def extract_all_table_data(xml_path, section_name, root):
    section_data = []

    for section in root.findall(".//default:section", namespaces=namespaces):
        title_element = section.find("default:title", namespaces=namespaces)
        if title_element is not None and title_element.text == section_name:
            table_data = extract_table_data(section)
            section_data.extend(table_data)

    return section_data


def extract_table_data(section):
    table_data = []

    table = section.find(".//default:table", namespaces=namespaces)
    if table is not None:
        for row in table.findall(".//default:tbody/default:tr", namespaces=namespaces):
            row_data = []
            for td in row.findall(".//default:td", namespaces=namespaces):
                content = td.find(".//default:content", namespaces=namespaces)
                if content is not None and content.text is not None:
                    row_data.append(content.text.strip())
                else:
                    row_data.append(td.text.strip() if td.text else ' '.join(td.itertext()))
            table_data.append(row_data)

    return table_data


@app.route("/extract_medical_data", methods=["GET"])
def extract_medical_data():
    global uploaded_xml_path

    if not uploaded_xml_path:
        return jsonify({"message": "No uploaded XML file found."})

    sections_to_extract = ['Notes', 'Problems', 'Allergies', 'Medical History']

    extracted_data = {}

    # Parse the XML file
    tree = ET.parse(uploaded_xml_path)
    root = tree.getroot()

    for section_name in sections_to_extract:
        section_data = extract_all_table_data(uploaded_xml_path, section_name, root)
        if len(section_data) > 0:
            summary = generate_summary(section_data)
            section_key = section_name.replace(" ", "_")
            extracted_data[section_key] = summary
        else:
            section_key = section_name.replace(" ", "_")
            extracted_data[section_key] = "No data available in this section."

    return jsonify(extracted_data)


# ... (other code) ...



import random

def extract_data_from_table_section(section_name, key_header, value_header, root):
    data = []

    # Find the section by its title
    for section in root.findall(".//default:section", namespaces=namespaces):
        title_element = section.find("default:title", namespaces=namespaces)
        if title_element is not None and title_element.text == section_name:

            # Iterate over each table in the section
            for table in section.findall(".//default:table", namespaces=namespaces):
                headers = [th.text for th in table.findall(".//default:thead/default:tr/default:th", namespaces=namespaces)]

                # Check if the table has the desired key and value headers
                if key_header in headers and value_header in headers:
                    key_index = headers.index(key_header)
                    value_index = headers.index(value_header)

                    # Iterate over each row in the table
                    for row in table.findall(".//default:tbody/default:tr", namespaces=namespaces):
                        row_data = []

                        # Extract data from each cell, handling nested <content> elements
                        for td in row.findall(".//default:td", namespaces=namespaces):
                            content = td.find(".//default:content", namespaces=namespaces)
                            if content is not None and content.text is not None:
                                row_data.append(content.text.strip())
                            else:
                                row_data.append(td.text.strip() if td.text else ' '.join(td.itertext()))

                        # Extract the key-value pair based on the header indexes
                        if section_name != "Medications":
                            random_times = random.randint(2, 5)
                            value_list = [row_data[value_index]] * random_times  # Append the first element multiple times
                            key_value = (row_data[key_index], value_list)
                        else:
                            key_value = (row_data[key_index], [row_data[value_index]])  # No duplication for Medications
                        data.append(key_value)

    return data







# ...

@app.route("/extract_key_value_data", methods=["GET"])
def extract_key_value_data():
    global uploaded_xml_path

    if not uploaded_xml_path:
        return jsonify({"message": "No uploaded XML file found."})

    # Parse the XML file
    tree = ET.parse(uploaded_xml_path)
    root = tree.getroot()

    # Execute the extraction functions for the specified sections and headers
    past_encounters_data_table = extract_data_from_table_section('Past Encounters', 'Encounter date',
                                                                 'Diagnosis/Indication', root)
    vitals_data_table = extract_data_from_table_section('Vitals', 'Date Recorded', 'Body mass index (BMI)', root)
    procedures_data_table_1 = extract_data_from_table_section('Procedures', 'Date', 'Name', root)
    procedures_data_table_2 = extract_data_from_table_section('Procedures', 'Imaging Date', 'Name', root)
    assessment_data_table = extract_data_from_table_section('Assessment', 'Assessment Date', 'Assessment', root)

    # Keep Medications as it is
    medication_data_table = extract_data_from_table_section('Medications', 'Name', 'Status', root)

    # Return the extracted data
    return jsonify({
        "Assessment": assessment_data_table,
        "Past_Encounters": past_encounters_data_table,
        "Procedures": procedures_data_table_1,
        "Procedures_(Imaging)": procedures_data_table_2,
        "Vitals": vitals_data_table,
        "Medications": medication_data_table
    })



def extract_data_from_table_section_two(section_name, root):
    data = []

    # Find the section by its title
    for section in root.findall(".//default:section", namespaces=namespaces):
        title_element = section.find("default:title", namespaces=namespaces)
        if title_element is not None and title_element.text == section_name:

            # Iterate over each table in the section
            for table in section.findall(".//default:table", namespaces=namespaces):
                headers = [th.text for th in table.findall(".//default:thead/default:tr/default:th", namespaces=namespaces)]

                table_data = []

                # Iterate over each row in the table
                for row in table.findall(".//default:tbody/default:tr", namespaces=namespaces):
                    row_data = []

                    # Iterate over each cell in the row
                    for td in row.findall(".//default:td", namespaces=namespaces):
                        content = td.find(".//default:content", namespaces=namespaces)
                        if content is not None and content.text is not None:
                            cell_data = content.text.strip()
                        else:
                            cell_data = td.text.strip() if td.text else ""  # Use an empty string for empty cells
                        row_data.append(cell_data)

                    table_data.append(row_data)

                data.append({
                    "headers": headers,
                    "table_data": table_data
                })

    return data


@app.route("/extract_dynamic_data", methods=["GET"])
def extract_dynamic_data():
    global uploaded_xml_path

    if not uploaded_xml_path:
        return jsonify({"message": "No uploaded XML file found."})

    # Parse the XML file
    tree = ET.parse(uploaded_xml_path)
    root = tree.getroot()

    extracted_data = {}

    # Get all section names dynamically
    section_names = [section.find("default:title", namespaces=namespaces).text for section in
                     root.findall(".//default:section", namespaces=namespaces)]

    # Iterate through each section and extract data
    for section_name in section_names:
        section_data = extract_data_from_table_section_two(section_name, root)

        # Generate 'header: table_data' pairs for each section
        section_key_values = {}
        for entry in section_data:
            headers = entry["headers"]
            table_data = entry["table_data"]

            header_table_pairs = []
            for row in table_data:
                header_table_pairs.append({header: value for header, value in zip(headers, row)})

            section_key_values[section_name] = header_table_pairs

        extracted_data[section_name] = section_key_values

    return jsonify(extracted_data)

# Custom error handler for all exceptions
@app.errorhandler(Exception)
@app.errorhandler(400)
@app.errorhandler(404)
@app.errorhandler(500)
def error_handler(error):
    status_code = error.code

    if status_code == 400:
        message = "Bad request. Please check your input."
    elif status_code == 404:
        message = "Resource not found."
    elif status_code == 500:
        message = "Internal server error. Please try again later."
    else:
        message = "An error occurred."

    return jsonify({"error": message}), status_code


if __name__ == "__main__":
    app.run(debug=True)

