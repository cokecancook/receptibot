# tool_agent.py - Simplified version with modules extracted
from agent_rag import main

import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - AGENT - %(levelname)s - %(message)s'
)

# --- Bloque Principal ---
if __name__ == '__main__':
    main() 