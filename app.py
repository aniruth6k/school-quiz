from flask import Flask, request, jsonify
from flask_cors import CORS
import openai
import json
import time
import os

app = Flask(__name__)
CORS(app)

# OpenAI API Configuration
API_KEY = os.getenv('OPENAI_API_KEY')
ASSISTANT_ID = os.getenv('ASSISTANT_ID')

client = openai.OpenAI(api_key=API_KEY)

def wait_for_run_completion(thread_id, run_id, timeout=30):
    start_time = time.time()
    while True:
        if time.time() - start_time > timeout:
            raise Exception("Request timed out")
            
        run = client.beta.threads.runs.retrieve(
            thread_id=thread_id,
            run_id=run_id
        )
        
        if run.status == 'completed':
            return run
        elif run.status in ['failed', 'expired']:
            raise Exception(f"Run {run.status}")
        
        time.sleep(1)

def get_messages(thread_id):
    messages = client.beta.threads.messages.list(thread_id=thread_id)
    if messages and messages.data:
        message = messages.data[0]
        if hasattr(message, 'content') and message.content:
            for content_item in message.content:
                if hasattr(content_item, 'text') and hasattr(content_item.text, 'value'):
                    return content_item.text.value
    return None

def generate_questions(unit_number):
    try:
        thread = client.beta.threads.create()
        
        prompt = f"""Generate exactly 5 multiple choice questions for Math Unit {unit_number}.
        
        Requirements:
        1. Each question must have exactly 4 options (A, B, C, D)
        2. Format as JSON array with 5 question objects
        3. Each question object must have:
           - question: The question text
           - options: Array of 4 answer choices
           - correct_answer: Index of correct answer (0-3)
           - explanation: Explanation of the correct answer
        """
        
        message = client.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content=prompt
        )
        
        run = client.beta.threads.runs.create(
            thread_id=thread.id,
            assistant_id=ASSISTANT_ID
        )
        
        wait_for_run_completion(thread.id, run.id)
        response_content = get_messages(thread.id)
        
        if not response_content:
            raise Exception("No valid response received")
            
        json_str = response_content.strip()
        questions = json.loads(json_str)
        
        return questions
            
    except Exception as e:
        print(f"Error generating questions: {e}")
        raise

@app.route('/')
def health_check():
    return jsonify({"status": "healthy", "timestamp": time.time()})

@app.route('/generate-quiz/<int:unit>', methods=['GET'])
def generate_quiz(unit):
    if not 1 <= unit <= 10:
        return jsonify({"error": "Unit number must be between 1 and 10"}), 400
        
    try:
        questions = generate_questions(unit)
        return jsonify({"questions": questions})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)