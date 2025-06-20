from typing import TypedDict, List, Optional
from langchain_core.messages import BaseMessage

class GraphState(TypedDict):
    messages: List[BaseMessage]
    tool_calls: Optional[List]
    tool_outputs: Optional[List]
