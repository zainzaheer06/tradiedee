"""
Knowledge Base Service - Handles RAG using LlamaIndex
Uses OpenAI embeddings for reliable processing
"""
import os
import json
import shutil
from pathlib import Path
from typing import Optional

# Try to import LlamaIndex components with helpful error messages
try:
    from llama_index.core import (
        SimpleDirectoryReader,
        StorageContext,
        VectorStoreIndex,
        load_index_from_storage,
        Settings
    )
    from llama_index.embeddings.openai import OpenAIEmbedding
    from llama_index.llms.openai import OpenAI

    LLAMAINDEX_AVAILABLE = True
except ImportError as e:
    print(f"Warning: LlamaIndex not available. Install with: pip install -r requirements_rag.txt")
    print(f"Error: {e}")
    LLAMAINDEX_AVAILABLE = False

# Initialize LlamaIndex settings with OpenAI embeddings
if LLAMAINDEX_AVAILABLE:
    try:
        Settings.llm = OpenAI(model="gpt-4o-mini", temperature=0.1)
        Settings.embed_model = OpenAIEmbedding(
            model="text-embedding-3-small"  # Fast and cost-effective OpenAI embeddings
        )
    except Exception as e:
        print(f"Warning: Error initializing embeddings: {e}")
        LLAMAINDEX_AVAILABLE = False

class KnowledgeBaseService:
    def __init__(self, base_dir: str = "knowledge_bases"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(exist_ok=True)
        self._index_cache = {}  # Cache loaded indices for fast queries

    def get_agent_kb_dir(self, agent_id: int) -> Path:
        """Get knowledge base directory for an agent"""
        kb_dir = self.base_dir / f"agent_{agent_id}"
        kb_dir.mkdir(exist_ok=True)
        return kb_dir

    def get_agent_docs_dir(self, agent_id: int) -> Path:
        """Get documents directory for an agent"""
        docs_dir = self.get_agent_kb_dir(agent_id) / "docs"
        docs_dir.mkdir(exist_ok=True)
        return docs_dir

    def get_agent_index_dir(self, agent_id: int) -> Path:
        """Get index storage directory for an agent"""
        index_dir = self.get_agent_kb_dir(agent_id) / "index"
        index_dir.mkdir(exist_ok=True)
        return index_dir

    def add_document(self, agent_id: int, file_path: str, original_filename: str) -> bool:
        """Add a document to the knowledge base"""
        try:
            docs_dir = self.get_agent_docs_dir(agent_id)

            # Copy file to knowledge base directory
            dest_path = docs_dir / original_filename
            shutil.copy2(file_path, dest_path)

            return True
        except Exception as e:
            print(f"Error adding document: {e}")
            return False

    def build_index(self, agent_id: int) -> bool:
        """Build or rebuild the vector index for an agent's knowledge base"""
        if not LLAMAINDEX_AVAILABLE:
            print("LlamaIndex not available. Please install dependencies: pip install -r requirements_rag.txt")
            return False

        try:
            docs_dir = self.get_agent_docs_dir(agent_id)
            index_dir = self.get_agent_index_dir(agent_id)

            # Check if there are any documents
            if not any(docs_dir.iterdir()):
                print(f"No documents found for agent {agent_id}")
                return False

            # Load documents
            documents = SimpleDirectoryReader(docs_dir).load_data()

            # Create index
            index = VectorStoreIndex.from_documents(documents)

            # Persist index
            index.storage_context.persist(persist_dir=str(index_dir))

            # Clear cache so new index gets loaded on next query
            if agent_id in self._index_cache:
                del self._index_cache[agent_id]
                print(f"Cleared cached index for agent {agent_id}")

            print(f"Index built successfully for agent {agent_id} with {len(documents)} documents")
            return True

        except Exception as e:
            print(f"Error building index: {e}")
            import traceback
            traceback.print_exc()
            return False

    def query(self, agent_id: int, query_text: str, top_k: int = 3) -> Optional[str]:
        """Query the knowledge base for an agent"""
        if not LLAMAINDEX_AVAILABLE:
            print("LlamaIndex not available")
            return None

        try:
            index_dir = self.get_agent_index_dir(agent_id)

            # Check if index exists
            if not (index_dir / "docstore.json").exists():
                print(f"No index found for agent {agent_id}")
                return None

            # Load index
            storage_context = StorageContext.from_defaults(persist_dir=str(index_dir))
            index = load_index_from_storage(storage_context)

            # Create query engine
            query_engine = index.as_query_engine(
                similarity_top_k=top_k,
                response_mode="compact"
            )

            # Query
            response = query_engine.query(query_text)

            return str(response)

        except Exception as e:
            print(f"Error querying knowledge base: {e}")
            import traceback
            traceback.print_exc()
            return None

    async def aquery(self, agent_id: int, query_text: str, top_k: int = 3) -> Optional[str]:
        """Async query the knowledge base for an agent (with caching)"""
        if not LLAMAINDEX_AVAILABLE:
            print("LlamaIndex not available")
            return None

        try:
            index_dir = self.get_agent_index_dir(agent_id)

            # Check if index exists
            if not (index_dir / "docstore.json").exists():
                print(f"No index found for agent {agent_id}")
                return None

            # Load index from cache or disk
            if agent_id not in self._index_cache:
                print(f"Loading index for agent {agent_id} (first time)...")
                storage_context = StorageContext.from_defaults(persist_dir=str(index_dir))
                index = load_index_from_storage(storage_context)
                self._index_cache[agent_id] = index
                print(f"Index cached for agent {agent_id}")
            else:
                index = self._index_cache[agent_id]
                print(f"Using cached index for agent {agent_id}")

            # Create query engine
            query_engine = index.as_query_engine(
                similarity_top_k=top_k,
                response_mode="compact",
                use_async=True
            )

            # Query
            response = await query_engine.aquery(query_text)

            return str(response)

        except Exception as e:
            print(f"Error querying knowledge base: {e}")
            import traceback
            traceback.print_exc()
            return None

    def delete_document(self, agent_id: int, filename: str) -> bool:
        """Delete a document and rebuild index"""
        try:
            docs_dir = self.get_agent_docs_dir(agent_id)
            file_path = docs_dir / filename

            if file_path.exists():
                file_path.unlink()
                # Rebuild index after deletion
                self.build_index(agent_id)
                return True
            return False
        except Exception as e:
            print(f"Error deleting document: {e}")
            return False

    def clear_knowledge_base(self, agent_id: int) -> bool:
        """Clear all documents and index for an agent"""
        try:
            kb_dir = self.get_agent_kb_dir(agent_id)
            if kb_dir.exists():
                shutil.rmtree(kb_dir)

            # Clear cache
            if agent_id in self._index_cache:
                del self._index_cache[agent_id]
                print(f"Cleared cached index for agent {agent_id}")

            return True
        except Exception as e:
            print(f"Error clearing knowledge base: {e}")
            return False

    def _get_all_agent_ids_with_kb(self) -> list:
        """Get list of all agent IDs that have knowledge bases"""
        agent_ids = []

        if not self.base_dir.exists():
            return agent_ids

        for agent_dir in self.base_dir.iterdir():
            if agent_dir.is_dir() and agent_dir.name.startswith("agent_"):
                try:
                    agent_id = int(agent_dir.name.split("_")[1])
                    index_dir = self.get_agent_index_dir(agent_id)
                    # Check if index exists
                    if (index_dir / "docstore.json").exists():
                        agent_ids.append(agent_id)
                except (ValueError, IndexError):
                    continue

        return sorted(agent_ids)

    def preload_all_indices(self):
        """
        Pre-load ALL knowledge base indices at startup.
        This ensures zero delay during calls (follows LiveKit pattern).
        """
        if not LLAMAINDEX_AVAILABLE:
            print("⚠️  LlamaIndex not available - skipping KB preload")
            return

        agent_ids = self._get_all_agent_ids_with_kb()

        if not agent_ids:
            print("ℹ️  No knowledge bases found to preload")
            return

        print("\n" + "=" * 60)
        print(f"[LOADING] Pre-loading {len(agent_ids)} Knowledge Base(s)...")
        print("=" * 60)

        loaded_count = 0
        for agent_id in agent_ids:
            try:
                if agent_id not in self._index_cache:
                    index_dir = self.get_agent_index_dir(agent_id)
                    print(f"[KB] Loading index for agent {agent_id}...", end=" ")

                    storage_context = StorageContext.from_defaults(persist_dir=str(index_dir))
                    index = load_index_from_storage(storage_context)
                    self._index_cache[agent_id] = index

                    print(f"[OK] Loaded")
                    loaded_count += 1
                else:
                    print(f"[OK] Agent {agent_id} already cached")
            except Exception as e:
                print(f"[ERROR] Failed to load agent {agent_id}: {e}")

        print("=" * 60)
        print(f"[OK] Pre-loaded {loaded_count}/{len(agent_ids)} knowledge base(s)")
        print(f"[CACHE] Total indices in cache: {len(self._index_cache)}")
        print("=" * 60 + "\n")

    async def retrieve_context(self, agent_id: int, query: str, top_k: int = 3) -> str:
        """
        Fast retrieval from pre-loaded index.
        Returns formatted context string ready to inject into prompt.

        This method is called automatically for every user message,
        ensuring KB context is always available to the LLM.
        """
        if not LLAMAINDEX_AVAILABLE:
            return ""

        if agent_id not in self._index_cache:
            return ""  # No KB for this agent

        try:
            index = self._index_cache[agent_id]
            retriever = index.as_retriever(similarity_top_k=top_k)
            nodes = await retriever.aretrieve(query)

            if not nodes:
                return ""

            # Build context in Arabic for better integration
            context = "\n\n=== معلومات من قاعدة المعرفة ===\n"
            for i, node in enumerate(nodes, 1):
                # Get content without metadata clutter
                try:
                    from llama_index.core.schema import MetadataMode
                    content = node.get_content(metadata_mode=MetadataMode.LLM)
                except:
                    content = node.get_content()

                context += f"\nمصدر {i}:\n{content}\n"

            context += "=== نهاية المعلومات ===\n\n"
            context += "استخدم المعلومات أعلاه للإجابة على سؤال المستخدم بدقة.\n"

            return context

        except Exception as e:
            print(f"Error retrieving context for agent {agent_id}: {e}")
            import traceback
            traceback.print_exc()
            return ""

# Global instance
kb_service = KnowledgeBaseService()

# Pre-load all indices at module import (like LiveKit example)
# This happens ONCE when worker starts, ensuring zero delay during calls
print("\n[INIT] Initializing Knowledge Base Service...")
kb_service.preload_all_indices()
