# Python Requirements

Python dependency files for different use cases.

## Files

### 📦 Main Requirements

**requirements.txt** (in root)
- Main/default requirements file
- Use for standard installation

### 📦 Specialized Requirements

**requirements_complete.txt**
- Complete set of all dependencies
- Includes all optional packages

**requirements_livekit.txt**
- LiveKit-specific dependencies
- Agent framework and plugins

**requirements_production.txt**
- Production-optimized dependencies
- Excludes development tools

**requirements_rag.txt**
- RAG/Knowledge Base dependencies
- Vector database and embeddings

## Installation

### Standard Installation
```bash
pip install -r requirements.txt
```

### Complete Installation
```bash
pip install -r requirements/requirements_complete.txt
```

### Feature-Specific Installation
```bash
# LiveKit only
pip install -r requirements/requirements_livekit.txt

# RAG/Knowledge Base only
pip install -r requirements/requirements_rag.txt

# Production deployment
pip install -r requirements/requirements_production.txt
```

## Updating Requirements

When adding new dependencies:
1. Update the appropriate requirements file
2. Update `requirements_complete.txt` with all deps
3. Test installation in a clean virtual environment

## Virtual Environment

Recommended setup:
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows
pip install -r requirements.txt
```
