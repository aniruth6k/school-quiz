from flask import Flask, request, jsonify
from flask_cors import CORS
from google.generativeai import GenerativeModel
import google.generativeai as genai
from dotenv import load_dotenv
from pydantic import BaseModel
from typing import List, Optional, Set, Dict
import os
import random
import json
from urllib.parse import unquote
from threading import Thread
import re
import asyncio
from functools import wraps

app = Flask(__name__)
CORS(app)
load_dotenv()

# Configuration
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
genai.configure(api_key=GEMINI_API_KEY)
model = GenerativeModel('gemini-2.0-flash-exp')

# Constants
TEST_MODE_QUESTIONS = 25
PRACTICE_MODE_QUESTIONS_PER_SET = 5
HARD_QUESTION_PERCENTAGE = 70

class QuizQuestion(BaseModel):
    question: str
    options: List[str]
    answer: str
    explanation: str

# Global variables
question_cache: List[QuizQuestion] = []
used_questions: Set[str] = set()
current_topic: str = ""
file_content_cache: Dict[str, str] = {}
concept_cache: Dict[str, str] = {}
processed_files: Set[str] = set()

def async_to_sync(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        return asyncio.run(f(*args, **kwargs))
    return wrapper

def extract_key_concepts(text_content: str) -> str:
    print("\nExtracting key concepts from text content...")
    prompt = """Extract and summarize the key concepts and important points from this text. 
    Include only the most essential information needed for generating questions later.
    Keep it concise but comprehensive."""
    
    response = model.generate_content(f"{prompt}\n\nText: {text_content}")
    concepts = response.text.strip()
    print("Successfully extracted key concepts")
    return concepts

def print_question(q: QuizQuestion, index: int):
    print(f"\nQuestion {index}:")
    print("=" * 50)
    print(f"Q: {q.question}")
    print("\nOptions:")
    for i, opt in enumerate(q.options):
        print(f"{chr(65+i)}) {opt}")
    print(f"\nCorrect Answer: {q.answer}")
    print(f"Explanation: {q.explanation}")
    print("-" * 50)

def read_and_process_content(file_path: str) -> Optional[str]:
    try:
        print(f"\nReading and processing file: {file_path}")
        with open(file_path, 'r', encoding='utf-8') as file:
            content = file.read()
            key_concepts = extract_key_concepts(content)
            concept_cache[file_path] = key_concepts
            file_content_cache[file_path] = content
            print("Successfully processed file and extracted concepts")
            return content
    except Exception as e:
        print(f"Error processing file {file_path}: {str(e)}")
        return None

def calculate_accuracy(text_content: str, questions: List[QuizQuestion]) -> float:
    try:
        total_words = len(text_content.split())
        relevant_count = 0
        for q in questions:
            question_words = q.question.lower().split()
            for word in question_words:
                if len(word) > 3 and word in text_content.lower():
                    relevant_count += 1
        accuracy = min((relevant_count / (len(questions) * 2)) * 100, 100)
        return round(accuracy, 2)
    except Exception as e:
        print(f"Error calculating accuracy: {str(e)}")
        return 0.0

async def generate_quiz_questions(text_content: str = None, topic: str = None, concepts: str = None, is_practice_mode: bool = True) -> Optional[List[QuizQuestion]]:
    print("\nGenerating Questions...")
    print("=" * 50)
    print(f"Mode: {'Practice' if is_practice_mode else 'Test'}")
    print(f"Source: {'Text File' if text_content else 'Concepts' if concepts else 'Topic only'}")

    try:
        num_questions = TEST_MODE_QUESTIONS if not is_practice_mode else PRACTICE_MODE_QUESTIONS_PER_SET

        if not is_practice_mode:
            enhanced_prompt = """Generate extremely challenging multiple choice questions that test advanced cognitive abilities. Questions should be:

            Question Distribution:
            1. Complex logical reasoning (40%)
               - Multi-step deductive reasoning
               - Advanced pattern recognition
               - Abstract concept application
            
            2. Advanced critical thinking (60%)
               - Deep analysis requirements
               - Complex problem evaluation
               - Multi-perspective consideration
            
            3. Multi-step problem solving (60%)
               - Sophisticated computational thinking
               - Strategic solution planning
               - Advanced concept integration

            Requirements:
            - All questions must be at the highest difficulty level
            - Questions should challenge even advanced learners
            - Clear and unambiguous despite complexity
            - Each question should require deep understanding
            - Include detailed explanations for learning

            Format Requirements:
            - 4 distinct options per question
            - One definitively correct answer
            - Comprehensive explanation (40 words)
            - Crystal clear question structure

            Response Format (JSON):
            {
                "questions": [
                    {
                        "question": "Question text",
                        "options": ["Option 1", "Option 2", "Option 3", "Option 4"],
                        "answer": "Correct option text",
                        "explanation": "Detailed explanation"
                    }
                ]
            }"""
        else:
            enhanced_prompt = """Generate a balanced mix of multiple choice questions with varying difficulty levels:

            Question Distribution:
            1. Hard questions (100%)
               - Complex reasoning
               - Advanced problem-solving
               - Deep conceptual understanding
            
            2. Intermediate questions (100%)
               - Applied knowledge
               - Basic analysis
               - Concept integration
            
            3. Basic questions (1000%)
               - Fundamental concepts
               - Direct application
               - Core understanding

            Requirements:
            - Progressive difficulty level
            - Clear learning progression
            - Balanced concept coverage
            - Appropriate challenge level
            - Helpful explanations for learning

            Format Requirements:
            - 4 distinct options per question
            - One definitively correct answer
            - Clear explanation (40 words)
            - Well-structured questions

            Response Format (JSON):
            {
                "questions": [
                    {
                        "question": "Question text",
                        "options": ["Option 1", "Option 2", "Option 3", "Option 4"],
                        "answer": "Correct option text",
                        "explanation": "Detailed explanation"
                    }
                ]
            }"""

        if text_content:
            content_prompt = f"Using this content:\n{text_content}\n\nGenerate {num_questions} questions that follow the guidelines above."
            print("Using full text content for generation")
        elif concepts:
            content_prompt = f"""Generate {num_questions} questions about {topic} using these key concepts:
            {concepts}
            
            Ensure questions are based on these concepts while maintaining variety and appropriate difficulty."""
            print("Using extracted concepts for generation")
        else:
            content_prompt = f"Generate {num_questions} questions about {topic} that follow the guidelines above."
            print("Using topic only for generation")

        full_prompt = f"{enhanced_prompt}\n\n{content_prompt}"

        response = model.generate_content(full_prompt)
        response_text = response.text.strip()
        
        json_text = re.search(r'({[\s\S]*})', response_text)
        if not json_text:
            raise ValueError("No valid JSON found in response")
            
        cleaned_json = re.sub(r'[\x00-\x1F\x7F-\x9F]', '', json_text.group(1))
        cleaned_json = re.sub(r',(\s*[}\]])', r'\1', cleaned_json)
        
        try:
            response_data = json.loads(cleaned_json)
        except json.JSONDecodeError as e:
            print(f"JSON Parse Error: {str(e)}")
            print(f"Problematic JSON: {cleaned_json}")
            raise
        
        processed_questions = []
        for q in response_data.get("questions", []):
            if not all(k in q for k in ["question", "options", "answer", "explanation"]):
                continue
                
            if len(q["options"]) != 4:
                continue
                
            if q["question"] in used_questions:
                continue

            cleaned_question = {
                "question": q["question"].strip(),
                "options": [opt.strip() for opt in q["options"]],
                "answer": q["answer"].strip(),
                "explanation": q["explanation"].strip()
            }

            try:
                question = QuizQuestion(**cleaned_question)

                if question.answer not in question.options:
                    continue

                random.shuffle(question.options)
                used_questions.add(question.question)
                processed_questions.append(question)
                print_question(question, len(processed_questions))
            except Exception as e:
                print(f"Error creating question object: {str(e)}")
                continue

        print(f"\nSuccessfully processed {len(processed_questions)} questions")
        return processed_questions

    except Exception as e:
        print(f"Error in generate_quiz_questions: {str(e)}")
        return None

@app.route('/quiz/next', methods=['GET'])
@async_to_sync
async def get_next_questions():
    try:
        topic = unquote(request.args.get('topic', ''))
        current_index = int(request.args.get('current_index', 0))
        standard = request.args.get('standard', '')
        subject = request.args.get('subject', '')
        chapter = request.args.get('chapter', '')
        is_practice_mode = request.args.get('is_practice_mode', 'true').lower() == 'true'
        
        if not topic:
            return jsonify({"error": "Missing topic parameter"}), 400

        topic = topic.strip()
        
        if not is_practice_mode and current_index >= TEST_MODE_QUESTIONS:
            return jsonify({
                "questions": [],
                "should_fetch": False,
                "total_questions": TEST_MODE_QUESTIONS
            })

        questions_per_set = PRACTICE_MODE_QUESTIONS_PER_SET if is_practice_mode else TEST_MODE_QUESTIONS

        if len(question_cache) < questions_per_set:
            file_path = rf"/home/ubuntu/schoolbookstxt/{standard}/{subject}/{topic}.txt"
            
            if os.path.exists(file_path):
                if file_path not in processed_files:
                    print("\nProcessing new file content...")
                    chapter_content = read_and_process_content(file_path)
                    processed_files.add(file_path)
                    questions = await generate_quiz_questions(
                        text_content=chapter_content,
                        is_practice_mode=is_practice_mode
                    )
                else:
                    print("\nUsing cached concepts...")
                    concepts = concept_cache.get(file_path)
                    questions = await generate_quiz_questions(
                        topic=topic,
                        concepts=concepts,
                        is_practice_mode=is_practice_mode
                    )
            else:
                print("\nGenerating questions from topic only...")
                questions = await generate_quiz_questions(
                    topic=topic,
                    is_practice_mode=is_practice_mode
                )
                
            if questions is None or len(questions) == 0:
                return jsonify({"error": "Failed to generate questions"}), 500
                
            question_cache.extend(questions)

        questions_to_send = question_cache[:questions_per_set]
        del question_cache[:questions_per_set]

        if not questions_to_send:
            return jsonify({"error": "No questions available"}), 500

        return jsonify({
            "questions": [q.model_dump() for q in questions_to_send],
            "should_fetch": True if is_practice_mode else current_index + len(questions_to_send) < TEST_MODE_QUESTIONS,
            "total_questions": TEST_MODE_QUESTIONS if not is_practice_mode else -1
        })

    except Exception as e:
        print(f"Error in get_next_questions: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy"}), 200

@app.route('/quiz/clear-cache', methods=['GET'])
def clear_cache():
    global question_cache, used_questions, file_content_cache, concept_cache, processed_files
    question_cache.clear()
    used_questions.clear()
    file_content_cache.clear()
    concept_cache.clear()
    processed_files.clear()
    print("\nAll caches cleared")
    return jsonify({"status": "Caches cleared"}), 200

@app.route('/quiz/status', methods=['GET'])
def get_status():
    return jsonify({
        "cache_size": len(question_cache),
        "used_questions": len(used_questions),
        "file_cache_size": len(file_content_cache),
        "concept_cache_size": len(concept_cache),
        "processed_files": len(processed_files),
        "current_topic": current_topic
    }), 200

if __name__ == '__main__':
    print("\nStarting Quiz Generator Server...")
    print(f"Test Mode Questions: {TEST_MODE_QUESTIONS}")
    print(f"Practice Mode Questions Per Set: {PRACTICE_MODE_QUESTIONS_PER_SET}")
    print(f"Hard Question Percentage: {HARD_QUESTION_PERCENTAGE}%")
    print("=" * 50)
    
    CORS(app, resources={r"/": {"origins": ""}})
    app.run(debug=True, port=5000, host='0.0.0.0')
