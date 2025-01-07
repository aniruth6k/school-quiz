from flask import Flask, jsonify, request
from openai import OpenAI
import os
import time
from flask_cors import CORS
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)
CORS(app)

# Initialize OpenAI client - corrected initialization
client = OpenAI(
    api_key=os.getenv('OPENAI_API_KEY')
)

# Get or create assistant ID
ASSISTANT_ID = os.getenv('OPENAI_ASSISTANT_ID')

def create_assistant():
    assistant = client.beta.assistants.create(
        name="School Quiz Generator",
        instructions="""You are a school quiz generator. When given notes or study material, generate 5 
        multiple choice questions that test understanding of the material. Each question must have:
        1. A clear question statement
        2. Four options (labeled A, B, C, D)
        3. The correct answer (0 for A, 1 for B, 2 for C, 3 for D)
        4. A brief explanation of why the answer is correct
        
        Format each question as a dictionary with these exact keys:
        - 'question': the question text
        - 'options': list of 4 options
        - 'correct_answer': integer 0-3
        - 'explanation': explanation text""",
        model="gpt-4-1106-preview"
    )
    print(f"Created assistant with ID: {assistant.id}")
    return assistant.id

# Create assistant if ID not found
if not ASSISTANT_ID:
    ASSISTANT_ID = create_assistant()

def parse_assistant_response(response_text):
    try:
        # Implement your parsing logic here
        questions = [
            {
                "question": "Sample question 1?",
                "options": ["Option A", "Option B", "Option C", "Option D"],
                "correct_answer": 0,
                "explanation": "Explanation for the correct answer"
            }
        ]
        return questions
    except Exception as e:
        print(f"Error parsing response: {e}")
        return None

@app.route('/generate-quiz/<int:unit>', methods=['GET'])
def generate_quiz(unit):
    try:
        # Get notes content from environment variable instead of file
        unit_notes = os.getenv(f'UNIT_{unit}_NOTES', '')
        if not unit_notes:
            return jsonify({'error': f'Notes for Unit {unit} not found'}), 404

        thread = client.beta.threads.create()

        message = client.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content=f"""Generate 5 multiple choice questions based on these study materials:
            
            {unit_notes}"""
        )

        run = client.beta.threads.runs.create(
            thread_id=thread.id,
            assistant_id=ASSISTANT_ID
        )

        start_time = time.time()
        timeout = 30
        
        while True:
            if time.time() - start_time > timeout:
                return jsonify({'error': 'Request timed out'}), 504
                
            run_status = client.beta.threads.runs.retrieve(
                thread_id=thread.id,
                run_id=run.id
            )
            
            if run_status.status == 'completed':
                break
            elif run_status.status == 'failed':
                return jsonify({'error': 'Failed to generate questions'}), 500
                
            time.sleep(1)

        messages = client.beta.threads.messages.list(
            thread_id=thread.id
        )

        assistant_response = messages.data[0].content[0].text.value
        
        questions = parse_assistant_response(assistant_response)
        
        if questions is None:
            return jsonify({'error': 'Failed to parse questions'}), 500

        return jsonify({
            'questions': questions
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'healthy'}), 200

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
