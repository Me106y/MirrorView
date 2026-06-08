import os
from langchain_community.document_loaders import PyPDFLoader
from langchain_core.documents import Document
from langchain_chroma import Chroma
from server.config import Config
from utils.logger_handler import logger


class ResumeService:
    def __init__(self):
        self._embedding_model = "sentence-transformers/all-MiniLM-L6-v2"
        self.embedding = None  # lazy-load on first use
        self.chroma_dir = Config.CHROMA_DB_DIR

    def _ensure_embedding(self):
        """Lazy-load the embedding model (avoids blocking server startup)."""
        if self.embedding is not None:
            return True
        try:
            import os as _os
            _os.environ.setdefault("HF_HUB_OFFLINE", "1")  # don't phone home
            from langchain_huggingface import HuggingFaceEmbeddings
            self.embedding = HuggingFaceEmbeddings(
                model_name=self._embedding_model
            )
            logger.info(f"Local embeddings loaded: {self._embedding_model}")
            return True
        except ImportError:
            logger.warning(
                "langchain-huggingface not installed — "
                "RAG resume search will not work."
            )
            return False

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

        if not self._ensure_embedding():
            logger.warning("No embedding model — skipping vector storage")
            return text

        try:
            docs = [Document(page_content=text,
                             metadata={"user_id": user_id, "source": "resume"})]

            vectorstore = Chroma(
                collection_name=f"resume_{user_id}",
                embedding_function=self.embedding,
                persist_directory=self.chroma_dir
            )
            vectorstore.add_documents(docs)

            return text
        except Exception as e:
            logger.error(f"Error indexing resume: {e}")
            return text

    def get_vector_store(self, user_id):
        if not self._ensure_embedding():
            return None
        return Chroma(
            collection_name=f"resume_{user_id}",
            embedding_function=self.embedding,
            persist_directory=self.chroma_dir
        )
