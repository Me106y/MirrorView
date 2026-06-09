import os
import json
from langchain_community.chat_models.tongyi import ChatTongyi
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser, JsonOutputParser
from server.config import Config
from server.services.resume_service import ResumeService
from utils.logger_handler import logger

from server.factories.llm_factory import ModelFactory

class AIService:
    def __init__(self):
        self.llm = ModelFactory.get_model("deepseek", "deepseek-chat", temperature=0.7)
        self.resume_service = ResumeService()

    def analyze_resume_and_update_job(self, user_id, resume_text, current_job_intention):
        """
        Analyze resume to extract job intention and key projects.
        Returns updated job intention and project summary.
        """
        prompt = ChatPromptTemplate.from_template(
            """
            You are an expert HR and Technical Interviewer.
            Analyze the following resume content and the user's stated job intention.
            
            User's stated intention: {current_job}
            
            Resume Content:
            {resume_text}
            
            Task:
            1. Determine the most suitable job position based on the resume and stated intention. 
               If the resume strongly suggests a different specific role, suggest that, otherwise stick to the stated intention but refine it.
            2. Extract 2-3 key projects or experiences that are most relevant to this role.
            
            Output JSON format:
            {{
                "suggested_position": "string",
                "projects_summary": "string (concise summary of key projects)"
            }}
            """
        )
        
        chain = prompt | self.llm | JsonOutputParser()
        
        try:
            result = chain.invoke({"current_job": current_job_intention, "resume_text": resume_text[:10000]}) # Truncate if too long
            return result
        except Exception as e:
            logger.error(f"Error analyzing resume: {e}")
            return {"suggested_position": current_job_intention, "projects_summary": ""}

    def generate_interview_questions(self, job_position, resume_text=None, projects_summary=None):
        """
        Generate 10 interview questions.
        If resume/projects provided, include 2 project-specific questions.
        """
        if resume_text and projects_summary:
            template = """
            You are an expert Interviewer. Generate 10 interview questions for a {job_position} role.
            
            Candidate's Key Projects/Experience:
            {projects_summary}
            
            Requirements:
            1. Questions 1-8: General technical and behavioral questions relevant to {job_position}.
            2. Questions 9-10: Specific questions probing the candidate's projects/experience mentioned above.
            3. Questions should be challenging but fair.
            4. Output ONLY a JSON array of strings.
            
            Example:
            ["Question 1", "Question 2", ...]
            """
            input_vars = {"job_position": job_position, "projects_summary": projects_summary}
        else:
            template = """
            You are an expert Interviewer. Generate 10 interview questions for a {job_position} role.
            
            Requirements:
            1. Mix of technical and behavioral questions.
            2. Output ONLY a JSON array of strings.
            
            Example:
            ["Question 1", "Question 2", ...]
            """
            input_vars = {"job_position": job_position}
            
        prompt = ChatPromptTemplate.from_template(template)
        chain = prompt | self.llm | JsonOutputParser()
        
        try:
            questions = chain.invoke(input_vars)
            # Ensure we strictly have strings
            return [str(q) for q in questions]
        except Exception as e:
            logger.error(f"Error generating questions: {e}")
            # Fallback
            return [
                f"Tell me about yourself and why you want to be a {job_position}.",
                "What are your greatest strengths and weaknesses?",
                "Describe a challenging technical problem you solved.",
                "Where do you see yourself in 5 years?",
                "Why should we hire you?",
                "How do you handle conflict in a team?",
                "What is your preferred working style?",
                "Tell me about a time you failed.",
                "What technologies are you most proficient in?",
                "Do you have any questions for us?"
            ]

    def evaluate_answer(self, question, answer, user_id=None):
        """
        Evaluate user's answer. Use RAG if user_id is provided (to access resume context).
        """
        context = ""
        if user_id:
            try:
                vectorstore = self.resume_service.get_vector_store(user_id)
                # Find relevant resume parts to see if answer matches experience
                docs = vectorstore.similarity_search(question + " " + answer, k=2)
                context = "\n".join([d.page_content for d in docs])
            except Exception as e:
                logger.warning(f"RAG lookup failed: {e}")

        prompt = ChatPromptTemplate.from_template(
            """
            You are an expert Interviewer evaluating a candidate's answer.
            
            Question: {question}
            Candidate's Answer: {answer}
            
            Context from Resume (if any):
            {context}
            
            Task:
            Evaluate the answer. Consider if it matches their resume context (if provided).
            Provide a dynamic score (0-10) based on the quality, depth, and relevance of the answer.
            - 9-10: Excellent, deep understanding, relevant examples.
            - 7-8: Good, covers basics, some examples.
            - 5-6: Average, correct but shallow.
            - 3-4: Below average, missed key points.
            - 0-2: Poor or irrelevant.
            
            Give a brief constructive feedback and a score.
            
            Output JSON:
            {{
                "score": float,
                "feedback": "string",
                "improved_answer_suggestion": "string"
            }}
            """
        )
        
        chain = prompt | self.llm | JsonOutputParser()
        
        try:
            return chain.invoke({"question": question, "answer": answer, "context": context})
        except Exception as e:
            logger.error(f"Error evaluating answer: {e}")
            # Try to recover or just return default
            return {"score": 5.0, "feedback": "Could not evaluate answer due to error.", "improved_answer_suggestion": ""}

    def generate_feedback(self, interview):
        """
        Generate overall feedback for the interview.
        """
        # Fetch all messages
        from server.models import Message
        messages = Message.query.filter_by(interview_id=interview.id).order_by(Message.created_at).all()
        
        # Prepare context
        conversation = "\n".join([f"{m.role}: {m.content}" for m in messages])
        
        prompt = ChatPromptTemplate.from_template(
            """
            You are an expert Interview Coach.
            Review the following interview transcript for a {job_position} role.
            
            Transcript:
            {conversation}
            
            Task:
            Provide a comprehensive summary and feedback in a single, well-structured paragraph or a few paragraphs.
            Include an overall score (0-100), key strengths, areas for improvement, and a final verdict (Hire/No Hire).
            Do NOT return JSON. Return plain text only.
            
            Format:
            Start with the score and verdict, then provide the detailed feedback.
            """
        )
        
        chain = prompt | self.llm | StrOutputParser()
        
        try:
            return chain.invoke({"job_position": interview.job_position, "conversation": conversation})
        except Exception as e:
            logger.error(f"Error generating feedback: {e}")
            return "Could not generate feedback due to an error."

    def chat_response_stream(self, messages_list, user_input, job_position="General"):
        """
        Streaming chat response using structured message history.
        messages_list: list of dicts [{'role': 'user'/'agent', 'content': '...'}]
        """
        from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

        system_template = "You are the AI Interviewer for a {job_position} role. Reply naturally. Keep responses concise."
        chat_template = ChatPromptTemplate.from_messages([
            ("system", system_template),
            ("placeholder", "{chat_history}"),
            ("human", "{input}")
        ])
        
        # Convert history for placeholder
        history_msgs = []
        for msg in messages_list:
            if msg['role'] == 'user':
                history_msgs.append(HumanMessage(content=msg['content']))
            elif msg['role'] == 'agent':
                history_msgs.append(AIMessage(content=msg['content']))
        
        chain = chat_template | self.llm | StrOutputParser()
        
        try:
            for chunk in chain.stream({
                "job_position": job_position, 
                "chat_history": history_msgs, 
                "input": user_input
            }):
                yield chunk
        except Exception as e:
            logger.error(f"Error generating chat response stream: {e}")
            yield "I apologize, but I encountered an error processing your request."
