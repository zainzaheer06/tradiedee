# RAG Knowledge Base Setup Guide

## Overview
The RAG (Retrieval-Augmented Generation) feature allows agents to search and retrieve information from uploaded documents during conversations. This enables agents to answer questions based on your custom knowledge base.

## Installation

1. Install RAG dependencies:
```bash
pip install -r requirements_rag.txt
```

2. Run the database migration:
```bash
python migrate_knowledge_base.py
```

## Usage

### 1. Upload Documents to Knowledge Base

1. Go to **Agents** page
2. Click on the **Knowledge Base (RAG)** button for your agent
3. Upload documents (supported formats: TXT, PDF, DOC, DOCX, MD, CSV)
4. Documents are automatically indexed using vector embeddings

### 2. How It Works

- When a user asks a question, the agent can use the `search_knowledge_base` tool
- The system searches the knowledge base using vector similarity
- Relevant information is retrieved and provided to the agent
- The agent uses this information to answer the user's question

### 3. Example Use Cases

- **Product Information**: Upload product manuals, specs, FAQs
- **Company Policies**: Upload employee handbooks, policy documents
- **Technical Documentation**: Upload API docs, troubleshooting guides
- **Customer Support**: Upload support articles, common solutions

## How Agents Use the Knowledge Base

The agent automatically has access to the `search_knowledge_base` function tool. When a user asks about topics that might be in the knowledge base, the agent will:

1. Call `search_knowledge_base(query="user's question")`
2. Receive relevant excerpts from the knowledge base
3. Use this information to formulate an accurate response

## Managing Knowledge Base

### View Documents
- Click "Knowledge Base (RAG)" on any agent card
- See all uploaded documents, their status, and size

### Upload New Documents
- Use the upload form to add multiple documents
- Documents are automatically processed and indexed

### Delete Documents
- Click the trash icon next to any document
- Index is automatically rebuilt

### Rebuild Index
- Click "Rebuild Index" to manually rebuild the vector index
- Useful if you encounter issues or after bulk uploads

## Technical Details

### Vector Index
- Uses OpenAI embeddings (`text-embedding-3-small`)
  - **High Quality**: State-of-the-art semantic understanding
  - **Cost Effective**: Optimized pricing for embeddings
  - **Reliable**: Production-grade API
  - **Fast**: Quick response times
- LlamaIndex for document processing and retrieval
- Stores separate indexes for each agent

### Why OpenAI Embeddings?
- ✅ **Best Quality**: Superior semantic understanding
- ✅ **Easy Setup**: No complex dependencies or model downloads
- ✅ **Reliable**: Production-ready with high uptime
- ✅ **Compatible**: Works seamlessly across all platforms (Windows, Mac, Linux)
- 💰 **Cost**: Small cost per embedding (but very affordable for most use cases)

### Storage Structure
```
knowledge_bases/
  agent_{id}/
    docs/         # Original documents
    index/        # Vector index files
```

### Database Schema
- `knowledge_base` table tracks uploaded documents
- Stores filename, path, type, size, and status
- Links to agent via `agent_id` foreign key

## Supported Document Formats

- **Text**: .txt, .md
- **PDF**: .pdf
- **Microsoft Office**: .doc, .docx
- **Data**: .csv

## Timezone Configuration

The system uses Saudi Arabia timezone (Asia/Riyadh) by default. To change timezone settings:
1. Update `TZ` environment variable in `.env`
2. Or modify timezone handling in `campaign_worker.py` and `app.py`

## Troubleshooting

### Documents Not Indexing
- Check file format is supported
- **Ensure OpenAI API key is set in `.env`** (required for embeddings)
- Check logs for specific errors
- Verify you have sufficient OpenAI API credits

### Search Not Working
- Verify index exists (check `knowledge_bases/agent_{id}/index/` folder)
- Try rebuilding the index
- Check that agent has knowledge base documents uploaded

### Performance Issues
- Large documents may take time to index
- Consider splitting very large documents into smaller files
- Adjust `top_k` parameter in queries for faster searches

## API Reference

### KnowledgeBaseService Methods

```python
# Add document
kb_service.add_document(agent_id, file_path, original_filename)

# Build/rebuild index
kb_service.build_index(agent_id)

# Query knowledge base (async)
result = await kb_service.aquery(agent_id, query_text, top_k=3)

# Delete document
kb_service.delete_document(agent_id, filename)

# Clear all documents
kb_service.clear_knowledge_base(agent_id)
```

## Best Practices

1. **Organize Documents**: Group related information in separate documents
2. **Keep Updated**: Remove outdated documents and add new ones regularly
3. **Test Queries**: Test common questions to ensure RAG is returning relevant results
4. **Monitor Usage**: Check logs to see when and how RAG is being used
5. **Optimize Content**: Format documents clearly with headers and bullet points for better retrieval

## Security Notes

- Knowledge base files are stored locally in the `knowledge_bases/` directory
- Each agent has its own isolated knowledge base
- Users can only access knowledge bases for their own agents
- File uploads are sanitized using `secure_filename`

## Future Enhancements

Potential improvements:
- Background indexing for large files
- Document chunking strategies
- Custom embedding models
- Multi-language support
- Document version control
