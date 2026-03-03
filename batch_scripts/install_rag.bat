@echo off
echo ========================================
echo RAG Knowledge Base - Dependency Install
echo ========================================
echo.
echo This will install:
echo - LlamaIndex (RAG framework)
echo - HuggingFace Transformers
echo - Sentence Transformers (embeddings)
echo - PyTorch (deep learning)
echo.
echo Installation may take 5-10 minutes...
echo.
pause

pip install -r requirements_rag.txt

echo.
echo ========================================
echo Installation Complete!
echo ========================================
echo.
echo RAG Knowledge Base is now ready!
echo.
echo Next steps:
echo 1. Restart your Flask app
echo 2. Go to Agents page
echo 3. Click "Knowledge Base (RAG)" on any agent
echo 4. Upload your documents
echo.
pause
