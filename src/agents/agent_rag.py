# tool_agent.py - Simplified version with modules extracted
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - AGENT - %(levelname)s - %(message)s'
)

# Import everything from the modules package
from agent_rag import main

# --- Bloque Principal ---
if __name__ == '__main__':
    main() 