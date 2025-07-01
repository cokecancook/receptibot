# Agent Modules

This directory contains the modularized components of the agent system, extracted from the original `agent_full.py` file.

## Structure

### `config.py`
- Environment variables and configuration constants
- `RAG_SERVICE_URL`, `GYM_API_URL`, `OLLAMA_MODEL_NAME`

### `tools.py`
- All tool functions used by the agent
- `external_rag_search_tool`, `check_gym_availability`, `book_gym_slot`
- `ALL_TOOLS_LIST` - List of all available tools

### `state.py`
- `AgentState` class definition
- State management functions
- `get_current_agent_scratchpad`, `update_state_after_llm`, `update_state_after_tool`

### `prompts.py`
- System prompts and prompt templates
- `RAG_SYSTEM_PROMPT` - Main system prompt for the agent

### `agent.py`
- Main `RagAgent` class
- All agent methods and workflow logic
- Graph construction and execution

### `cli.py`
- Command-line interface logic
- Main execution function
- User interaction handling

### `__init__.py`
- Package initialization
- Exports all main components for easy importing

## Usage

The original `agent_full.py` has been simplified to just:

```python
import logging
from modules import main

if __name__ == '__main__':
    main()
```

All functionality is now organized in the modules directory, making the code more maintainable and modular.

## Benefits of Refactoring

1. **Separation of Concerns**: Each module has a specific responsibility
2. **Maintainability**: Easier to find and modify specific functionality
3. **Reusability**: Individual modules can be imported and used separately
4. **Testability**: Each module can be tested independently
5. **Readability**: Smaller, focused files are easier to understand 