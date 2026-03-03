# Batch Scripts

Windows batch scripts for common operations.

## Scripts

### 🔧 Installation Scripts

**install_rag.bat**
- Installs RAG (Knowledge Base) dependencies
- Runs: `pip install -r requirements/requirements_rag.txt`

**install_recording.bat**
- Installs call recording dependencies
- Sets up recording service requirements

### ▶️ Run Scripts

**run_agent.bat**
- Starts the LiveKit agent
- Runs: `python agent.py`

**run_dashboard.bat**
- Starts the Flask web dashboard
- Runs: `python app.py`

## Usage

### First Time Setup
```batch
# Install all dependencies
install_rag.bat
install_recording.bat

# Or install complete requirements
pip install -r requirements.txt
```

### Running the Application
```batch
# Terminal 1: Start the agent
run_agent.bat

# Terminal 2: Start the web dashboard
run_dashboard.bat
```

## Notes

- Run from the project root directory
- Ensure Python and pip are in your PATH
- For Linux/Mac, create equivalent .sh scripts
