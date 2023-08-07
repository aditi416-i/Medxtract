from distutils.command.config import config
from html import entities
from flask import Flask, render_template, request,jsonify, session
import boto3
import os
app = Flask(__name__)
from werkzeug.utils import secure_filename
from collections import OrderedDict

s3 = boto3.client('s3',
                    aws_access_key_id='Enter your access key here',
                    aws_secret_access_key= 'Enter your access key here',
                    region_name='Enter region name'
                    #aws_session_token=keys.AWS_SESSION_TOKEN
                     )

textract = boto3.client('textract',
                        aws_access_key_id='Enter your access key here',
                        aws_secret_access_key = 'Enter your access key here', region_name='Enter region name')

comprehend = boto3.client('comprehendmedical', aws_access_key_id='Enter your acces key here', 
                        aws_secret_access_key = 'Enter your access key here', region_name='Enter the region name here')

dynamodb = boto3.resource('dynamodb', 
                    aws_access_key_id='Enter your access key here',
                    aws_secret_access_key= 'Enter your access key here',
                    region_name='Enter your region name')

from boto3.dynamodb.conditions import Key, Attr #Filtering conditions while querying the data from Amazon dynamodb

BUCKET_NAME='PrescriptionRecognitionbucket'

app.secret_key = 'This is your secret key to utilize session in Flask'

entities_to_store = [] #Initializing an empty list

@app.route('/')  
def home():
    return render_template("first.html")

@app.route('/upload',methods=['post'])
def upload():
    if request.method == 'POST':
        img = request.files['file']
        UPLOAD_FOLDER = os.path.join('static', 'uploads')
        app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
        img_filename = secure_filename(img.filename)
        #img.save(os.path.join(app.config['UPLOAD_FOLDER'], img_filename))
        session['uploaded_img_file_path'] = os.path.join(app.config['UPLOAD_FOLDER'], img_filename)
        msg = 'Please upload a file'
        if img:
                filename = secure_filename(img.filename)
                img.save(filename)
                s3.upload_file(
                    Bucket = BUCKET_NAME,
                    Filename=filename,
                    Key = filename
                )
                msg = "Upload Done!"

    return render_template("second.html", msg = msg)

@app.route('/extract', methods=['post'])
def extract():
    if request.method == 'POST':
      
        objs = s3.list_objects_v2(Bucket=BUCKET_NAME, Delimiter='/') ['Contents']
        #print(objs)
        objs.sort(key=lambda e: e['LastModified'], reverse=True)
        #print("******")
        #print(objs[0])
        first_item = list(objs[0].items())[0]
        #print(first_item[1])
        documentName = str(first_item[1])
        
        # Call Amazon Textract
        with open(documentName, "rb") as document:
            response = textract.analyze_document(
                Document={
                    
                    'Bytes': document.read(),
                },
                FeatureTypes=["FORMS"])
        
        #print(response)
        extractedText = ""

        for block in response['Blocks']:
            if block["BlockType"] == "LINE":
                # print('\033[94m' + item["Text"] + '\033[0m')
                extractedText = extractedText+block["Text"]+" "

        file1 = open("temp.txt", 'w')
        file1.write(extractedText)
        file1.close()

        responseJson = {

            "text": extractedText
        }
        #print(responseJson)

    return render_template("third.html",text = [extractedText])

@app.route('/image', methods=['post'])
def imshow():
    if request.method == 'POST':

        temp_file = open("temp.txt", 'r')
        extractedText = temp_file.read()
        temp_file.close()
        
        img = request.files['file']
        UPLOAD_FOLDER = os.path.join('static', 'uploads')
        app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
        img_filename = secure_filename(img.filename)
        img.save(os.path.join(app.config['UPLOAD_FOLDER'], img_filename))
        session['uploaded_img_file_path'] = os.path.join(app.config['UPLOAD_FOLDER'], img_filename)
        img_file_path = session.get('uploaded_img_file_path', None)

    return render_template('fourth.html', user_image = img_file_path, text = [extractedText])

@app.route('/classifier', methods=['post'])
def ner():
    if request.method == 'POST':
      
        temp_file = open("temp.txt", 'r')
        extractedText = temp_file.read()
        temp_file.close()

        # Call AWS Comprehend Medical
        result = comprehend.detect_entities(Text= extractedText)
        entities = result['Entities']
        global entities_to_store
        entities_to_store = entities
        print('Extracted Medical Entities:\n')

        array = []
        for entity in entities:
            print(f"{'Entity Text: '  + str(entity['Text']) : <40}{'Entity Type: ' + str(entity['Type']) : <40}{'Category: ' + str(entity['Category']) : <40}")
            array.append(f"{'Entity Text: '  + str(entity['Text']) + '  |  ' : <40}{'Entity Type: ' + str(entity['Type']) +'  |  ' : <40}{'Category: ' + str(entity['Category']) : <40}")
            if 'Attributes' in entity.keys():
                print()
                for element in entity['Attributes']:
                    print(f"{'      --> ' : <5}{'Attribute Text: ' + str(element['Text']) : <40}{'Relationship: ' + str(element['RelationshipType']) : <40}{'Category: ' + str(element['Category']) : <40}")
                    array.append(f"{'      --> ' : <5}{'Attribute Text: ' + str(element['Text']) +'  |  ': <40}{'Relationship: ' + str(element['RelationshipType'])+'  |  ' : <40}{'Category: ' + str(element['Category']) : <40}")
            print('-'*130)
            array.append('-'*130)
        print()

        print(entities)

    return render_template("store_button.html",text = array)

@app.route('/store', methods=['POST'])
def database_storage():
    if request.method == 'POST':

        global entities_to_store
        entities = entities_to_store
        dictn = {}
        for entity in entities:
            '''
            print('Entity Text: ' + str(entity['Text']) + '|    Entity Type: ' + str(entity['Type']) + '|    
            Category: ' + str(entity['Category']))
            '''
            generic_name_cnt = 0
            if str(entity['Type']) == "GENERIC_NAME":
                generic_name_cnt = generic_name_cnt + 1
                dictn["MEDICINE_"+str(generic_name_cnt)] = str(entity['Text'])
            else:
                dictn[str(entity['Type'])] = str(entity['Text'])
            if 'Attributes' in entity.keys():
                # print('----->  ')
                dictelem = {}
                dictelem["NAME"] = dictn["MEDICINE_"+str(generic_name_cnt)]
                for element in entity['Attributes']:
                    dictelem[str(element['RelationshipType'])] = {str(element['Text'])}
                    # print('                       Attribute Text: ' + str(element['Text']) +
                    #  '|    Relationship: ' + str(element['RelationshipType']) + '|    Category: ' + str(element['Category']))
                dictn['MEDICINE_'+str(generic_name_cnt)+'_Attributes'] = dictelem
                # print()
        dictn["Name-Date"] = dictn["NAME"] + " " + dictn["DATE"]
        print(dictn)
        table = dynamodb.Table('Prescriptions')
        # table.put_item(Item=dictn)
        with table.batch_writer() as writer:
            writer.put_item(Item=dictn)

    entities_to_store = []

    return render_template("final.html", msg1 = 'Your data has been successfully stored in the database!', msg2 = 'Thank you!')

@app.route('/return', methods=['POST'])
def go_back():
    return render_template("first.html")



if __name__ == "__main__":
    
    app.run(debug=True)