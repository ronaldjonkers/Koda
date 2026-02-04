"""Vector-based memory system for semantic search and persistent memory."""

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from loguru import logger


class VectorMemoryStore:
    """
    Vector-based memory system using ChromaDB for semantic search.
    
    Provides:
    - Semantic search over memories using embeddings
    - Automatic chunking and indexing
    - Persistent storage across sessions
    - Memory categorization (facts, preferences, context, tasks)
    """
    
    COLLECTION_NAME = "koda_memory"
    
    def __init__(self, data_dir: Path, embedding_model: str = "all-MiniLM-L6-v2"):
        self.data_dir = data_dir
        self.db_path = data_dir / "vector_db"
        self.embedding_model = embedding_model
        self._client = None
        self._collection = None
        self._embedder = None
    
    def _ensure_initialized(self) -> None:
        """Lazy initialization of ChromaDB and embeddings."""
        if self._client is not None:
            return
        
        try:
            import chromadb
            from chromadb.config import Settings
            
            self.db_path.mkdir(parents=True, exist_ok=True)
            
            self._client = chromadb.PersistentClient(
                path=str(self.db_path),
                settings=Settings(anonymized_telemetry=False)
            )
            
            self._collection = self._client.get_or_create_collection(
                name=self.COLLECTION_NAME,
                metadata={"description": "Koda persistent memory store"}
            )
            
            logger.info(f"Vector memory initialized at {self.db_path}")
            
        except ImportError:
            logger.warning("ChromaDB not installed. Vector memory disabled.")
            raise
    
    def _get_embedder(self):
        """Get or create the sentence transformer embedder."""
        if self._embedder is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._embedder = SentenceTransformer(self.embedding_model)
                logger.debug(f"Loaded embedding model: {self.embedding_model}")
            except ImportError:
                logger.warning("sentence-transformers not installed.")
                raise
        return self._embedder
    
    def _generate_embedding(self, text: str) -> list[float]:
        """Generate embedding for text."""
        embedder = self._get_embedder()
        embedding = embedder.encode(text, convert_to_numpy=True)
        return embedding.tolist()
    
    def _generate_id(self, content: str, category: str) -> str:
        """Generate a unique ID for a memory entry."""
        hash_input = f"{category}:{content}"
        return hashlib.sha256(hash_input.encode()).hexdigest()[:16]
    
    def add(
        self,
        content: str,
        category: str = "general",
        metadata: dict[str, Any] | None = None,
        source: str | None = None
    ) -> str:
        """
        Add a memory to the vector store.
        
        Args:
            content: The memory content to store.
            category: Category (facts, preferences, context, tasks, general).
            metadata: Additional metadata to store.
            source: Source of the memory (e.g., "user", "agent", "system").
        
        Returns:
            The ID of the stored memory.
        """
        self._ensure_initialized()
        
        memory_id = self._generate_id(content, category)
        embedding = self._generate_embedding(content)
        
        mem_metadata = {
            "category": category,
            "source": source or "unknown",
            "created_at": int(time.time()),
            "updated_at": int(time.time()),
        }
        if metadata:
            mem_metadata.update(metadata)
        
        # Upsert to handle duplicates
        self._collection.upsert(
            ids=[memory_id],
            embeddings=[embedding],
            documents=[content],
            metadatas=[mem_metadata]
        )
        
        logger.debug(f"Added memory [{category}]: {content[:50]}...")
        return memory_id
    
    def search(
        self,
        query: str,
        n_results: int = 5,
        category: str | None = None,
        min_score: float = 0.0
    ) -> list[dict[str, Any]]:
        """
        Search memories by semantic similarity.
        
        Args:
            query: The search query.
            n_results: Maximum number of results.
            category: Filter by category (optional).
            min_score: Minimum similarity score (0-1).
        
        Returns:
            List of matching memories with scores.
        """
        self._ensure_initialized()
        
        query_embedding = self._generate_embedding(query)
        
        where_filter = None
        if category:
            where_filter = {"category": category}
        
        results = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            where=where_filter,
            include=["documents", "metadatas", "distances"]
        )
        
        memories = []
        if results and results["documents"] and results["documents"][0]:
            for i, doc in enumerate(results["documents"][0]):
                # ChromaDB returns L2 distance; convert to similarity score
                distance = results["distances"][0][i] if results["distances"] else 0
                score = 1 / (1 + distance)  # Convert distance to similarity
                
                if score >= min_score:
                    memories.append({
                        "id": results["ids"][0][i],
                        "content": doc,
                        "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                        "score": score
                    })
        
        return memories
    
    def get(self, memory_id: str) -> dict[str, Any] | None:
        """Get a specific memory by ID."""
        self._ensure_initialized()
        
        result = self._collection.get(
            ids=[memory_id],
            include=["documents", "metadatas"]
        )
        
        if result and result["documents"] and result["documents"][0]:
            return {
                "id": memory_id,
                "content": result["documents"][0],
                "metadata": result["metadatas"][0] if result["metadatas"] else {}
            }
        return None
    
    def delete(self, memory_id: str) -> bool:
        """Delete a memory by ID."""
        self._ensure_initialized()
        
        try:
            self._collection.delete(ids=[memory_id])
            logger.debug(f"Deleted memory: {memory_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete memory {memory_id}: {e}")
            return False
    
    def update(
        self,
        memory_id: str,
        content: str | None = None,
        metadata: dict[str, Any] | None = None
    ) -> bool:
        """Update an existing memory."""
        self._ensure_initialized()
        
        existing = self.get(memory_id)
        if not existing:
            return False
        
        new_content = content or existing["content"]
        new_metadata = existing.get("metadata", {})
        if metadata:
            new_metadata.update(metadata)
        new_metadata["updated_at"] = int(time.time())
        
        embedding = self._generate_embedding(new_content)
        
        self._collection.update(
            ids=[memory_id],
            embeddings=[embedding],
            documents=[new_content],
            metadatas=[new_metadata]
        )
        
        return True
    
    def list_by_category(self, category: str, limit: int = 50) -> list[dict[str, Any]]:
        """List all memories in a category."""
        self._ensure_initialized()
        
        results = self._collection.get(
            where={"category": category},
            limit=limit,
            include=["documents", "metadatas"]
        )
        
        memories = []
        if results and results["documents"]:
            for i, doc in enumerate(results["documents"]):
                memories.append({
                    "id": results["ids"][i],
                    "content": doc,
                    "metadata": results["metadatas"][i] if results["metadatas"] else {}
                })
        
        return memories
    
    def get_context_for_query(self, query: str, max_tokens: int = 2000) -> str:
        """
        Get relevant memory context for a query.
        
        Args:
            query: The query to find relevant context for.
            max_tokens: Approximate maximum tokens in response.
        
        Returns:
            Formatted context string.
        """
        memories = self.search(query, n_results=10, min_score=0.3)
        
        if not memories:
            return ""
        
        context_parts = ["## Relevant Memories\n"]
        char_count = 0
        max_chars = max_tokens * 4  # Approximate chars per token
        
        for mem in memories:
            category = mem["metadata"].get("category", "general")
            content = mem["content"]
            entry = f"- [{category}] {content}\n"
            
            if char_count + len(entry) > max_chars:
                break
            
            context_parts.append(entry)
            char_count += len(entry)
        
        return "".join(context_parts)
    
    def count(self, category: str | None = None) -> int:
        """Count memories, optionally filtered by category."""
        self._ensure_initialized()
        
        if category:
            results = self._collection.get(
                where={"category": category},
                include=[]
            )
            return len(results["ids"]) if results else 0
        
        return self._collection.count()
    
    def clear(self, category: str | None = None) -> int:
        """Clear memories, optionally filtered by category."""
        self._ensure_initialized()
        
        if category:
            results = self._collection.get(
                where={"category": category},
                include=[]
            )
            if results and results["ids"]:
                self._collection.delete(ids=results["ids"])
                return len(results["ids"])
            return 0
        
        # Clear all
        count = self._collection.count()
        self._client.delete_collection(self.COLLECTION_NAME)
        self._collection = self._client.create_collection(
            name=self.COLLECTION_NAME,
            metadata={"description": "Koda persistent memory store"}
        )
        return count
    
    def export_to_json(self, filepath: Path) -> int:
        """Export all memories to JSON file."""
        self._ensure_initialized()
        
        results = self._collection.get(include=["documents", "metadatas"])
        
        memories = []
        if results and results["documents"]:
            for i, doc in enumerate(results["documents"]):
                memories.append({
                    "id": results["ids"][i],
                    "content": doc,
                    "metadata": results["metadatas"][i] if results["metadatas"] else {}
                })
        
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(json.dumps(memories, indent=2))
        
        return len(memories)
    
    def import_from_json(self, filepath: Path) -> int:
        """Import memories from JSON file."""
        self._ensure_initialized()
        
        if not filepath.exists():
            return 0
        
        memories = json.loads(filepath.read_text())
        count = 0
        
        for mem in memories:
            self.add(
                content=mem["content"],
                category=mem.get("metadata", {}).get("category", "general"),
                metadata=mem.get("metadata"),
                source=mem.get("metadata", {}).get("source")
            )
            count += 1
        
        return count
    
    def keyword_search(
        self,
        query: str,
        n_results: int = 10,
        category: str | None = None
    ) -> list[dict[str, Any]]:
        """
        Search memories by keyword matching (BM25-style).
        
        Args:
            query: The search query (keywords).
            n_results: Maximum number of results.
            category: Filter by category (optional).
        
        Returns:
            List of matching memories with scores.
        """
        self._ensure_initialized()
        
        # Get all documents (or filtered by category)
        where_filter = {"category": category} if category else None
        results = self._collection.get(
            where=where_filter,
            include=["documents", "metadatas"]
        )
        
        if not results or not results["documents"]:
            return []
        
        # Simple keyword scoring
        query_terms = query.lower().split()
        scored = []
        
        for i, doc in enumerate(results["documents"]):
            doc_lower = doc.lower()
            score = 0
            
            for term in query_terms:
                # Count occurrences
                count = doc_lower.count(term)
                if count > 0:
                    # BM25-inspired scoring
                    score += count / (count + 1.5)
            
            if score > 0:
                scored.append({
                    "id": results["ids"][i],
                    "content": doc,
                    "metadata": results["metadatas"][i] if results["metadatas"] else {},
                    "score": score
                })
        
        # Sort by score and return top N
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:n_results]
    
    def hybrid_search(
        self,
        query: str,
        n_results: int = 5,
        category: str | None = None,
        vector_weight: float = 0.7,
        keyword_weight: float = 0.3
    ) -> list[dict[str, Any]]:
        """
        Hybrid search combining semantic (vector) and keyword search.
        
        This provides better results by combining:
        - Semantic similarity (understands meaning)
        - Keyword matching (exact term matches)
        
        Args:
            query: The search query.
            n_results: Maximum number of results.
            category: Filter by category (optional).
            vector_weight: Weight for vector search results (0-1).
            keyword_weight: Weight for keyword search results (0-1).
        
        Returns:
            List of matching memories with combined scores.
        """
        # Get results from both methods
        vector_results = self.search(query, n_results=n_results * 2, category=category)
        keyword_results = self.keyword_search(query, n_results=n_results * 2, category=category)
        
        # Normalize scores
        if vector_results:
            max_v = max(r["score"] for r in vector_results)
            for r in vector_results:
                r["vector_score"] = r["score"] / max_v if max_v > 0 else 0
        
        if keyword_results:
            max_k = max(r["score"] for r in keyword_results)
            for r in keyword_results:
                r["keyword_score"] = r["score"] / max_k if max_k > 0 else 0
        
        # Merge results
        merged = {}
        
        for r in vector_results:
            merged[r["id"]] = {
                "id": r["id"],
                "content": r["content"],
                "metadata": r["metadata"],
                "vector_score": r.get("vector_score", 0),
                "keyword_score": 0
            }
        
        for r in keyword_results:
            if r["id"] in merged:
                merged[r["id"]]["keyword_score"] = r.get("keyword_score", 0)
            else:
                merged[r["id"]] = {
                    "id": r["id"],
                    "content": r["content"],
                    "metadata": r["metadata"],
                    "vector_score": 0,
                    "keyword_score": r.get("keyword_score", 0)
                }
        
        # Calculate combined scores
        results = []
        for item in merged.values():
            combined_score = (
                item["vector_score"] * vector_weight +
                item["keyword_score"] * keyword_weight
            )
            item["score"] = combined_score
            results.append(item)
        
        # Sort by combined score
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:n_results]
    
    def auto_index_file(self, filepath: Path, chunk_size: int = 500) -> int:
        """
        Auto-index a file into memory with chunking.
        
        Args:
            filepath: Path to the file to index.
            chunk_size: Approximate characters per chunk.
        
        Returns:
            Number of chunks indexed.
        """
        if not filepath.exists():
            return 0
        
        content = filepath.read_text()
        filename = filepath.name
        
        # Split into chunks
        chunks = []
        current_chunk = []
        current_size = 0
        
        for line in content.split('\n'):
            current_chunk.append(line)
            current_size += len(line)
            
            if current_size >= chunk_size:
                chunks.append('\n'.join(current_chunk))
                current_chunk = []
                current_size = 0
        
        if current_chunk:
            chunks.append('\n'.join(current_chunk))
        
        # Index each chunk
        for i, chunk in enumerate(chunks):
            self.add(
                content=chunk,
                category="file",
                metadata={
                    "filename": filename,
                    "filepath": str(filepath),
                    "chunk_index": i,
                    "total_chunks": len(chunks)
                },
                source="file_index"
            )
        
        logger.info(f"Indexed {len(chunks)} chunks from {filename}")
        return len(chunks)
    
    def get_stats(self) -> dict[str, Any]:
        """Get memory store statistics."""
        self._ensure_initialized()
        
        total = self._collection.count()
        
        # Count by category
        categories = {}
        for cat in ["facts", "preferences", "context", "tasks", "general", "file"]:
            categories[cat] = self.count(cat)
        
        return {
            "total_memories": total,
            "by_category": categories,
            "db_path": str(self.db_path),
            "embedding_model": self.embedding_model
        }
