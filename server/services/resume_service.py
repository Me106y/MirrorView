import os
from langchain_community.document_loaders import PyPDFLoader
from langchain_core.documents import Document
from langchain_community.embeddings import DashScopeEmbeddings
from langchain_chroma import Chroma
from server.config import Config
from utils.logger_handler import logger

class ResumeService:
    def __init__(self):
        self.embedding = DashScopeEmbeddings(
            model="text-embedding-v1",
            dashscope_api_key=Config.DASHSCOPE_API_KEY
        )
        self.chroma_dir = Config.CHROMA_DB_DIR

    def parse_resume(self, file_path):
        """
        Parse PDF resume and return text content
        """
        try:
            loader = PyPDFLoader(file_path)
            pages = loader.load()
            full_text = "\n".join([p.page_content for p in pages])
            return full_text
        except Exception as e:
            logger.error(f"Error parsing resume: {e}")
            return None

    def index_resume(self, user_id, file_path):
        """
        Parse resume, split text, and store embeddings in ChromaDB
        Returns extracted text for immediate analysis
        """
        text = self.parse_resume(file_path)
        if not text:
            return None
            
        try:
            # Create a collection specific to the user or use metadata
            # We'll use a single collection but filter by user_id metadata if needed, 
            # or simpler: just recreate the vector store for the current session context.
            # For simplicity in this demo, we'll store everything in one collection 
            # but ideally we should manage user contexts.
            
            # Let's create a temporary vector store for this user's resume
            # Or persist it with user_id metadata
            
            docs = [Document(page_content=text, metadata={"user_id": user_id, "source": "resume"})]
            
            # Initialize Chroma
            vectorstore = Chroma(
                collection_name=f"resume_{user_id}",
                embedding_function=self.embedding,
                persist_directory=self.chroma_dir
            )
            
            # Clear old resume data for this user if exists (simple way: delete collection? Chroma handles upsert?)
            # For now just add.
            vectorstore.add_documents(docs)
            
            return text
        except Exception as e:
            logger.error(f"Error indexing resume: {e}")
            return text # Return text even if indexing fails, so we can still use it for simple context

    def get_vector_store(self, user_id):
        return Chroma(
            collection_name=f"resume_{user_id}",
            embedding_function=self.embedding,
            persist_directory=self.chroma_dir
        )
