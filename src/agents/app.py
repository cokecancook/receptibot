# app.py

from langchain_core.messages import SystemMessage, HumanMessage, BaseMessage, ToolMessage
from langgraph.graph import StateGraph, END

from agent.state import GraphState
from agent.llm_config import llm_with_tools
from agent.system_prompt import SYSTEM_PROMPT
from agent.helpers import check_ollama_connection
from agent.tools import check_gym_availability, book_gym_slot
from agent.graph_nodes import call_llm, call_tools, add_tool_outputs_to_messages

model = "qwen3:8b"

tools = [check_gym_availability, book_gym_slot]

system_message = SystemMessage(content=SYSTEM_PROMPT.strip())

graph = StateGraph(GraphState)

graph.add_node("llm", call_llm)
graph.add_node("tools", call_tools)
graph.add_node("format_tool_outputs", add_tool_outputs_to_messages)
graph.set_entry_point("llm")

def should_call_tools(state: GraphState):
    last_message = state['messages'][-1]
    if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
        state['tool_calls'] = last_message.tool_calls
        return "tools"
    return END
graph.add_conditional_edges("llm", should_call_tools)
graph.add_edge("tools", "llm")
runnable = graph.compile()

if __name__ == "__main__":
    if not check_ollama_connection(model):
        exit(1)
    print("Hey! I'm a gym booking assistant. How can I help? (Type 'exit' to quit)")
    messages = [system_message]
    while True:
        user = input("You: ")
        if user.lower() == "exit":
            break
        messages.append(HumanMessage(content=user))
        result = runnable.invoke({"messages": messages})
        final_response = result["messages"][-1]
        print("Bot:", final_response.content)
        messages = result["messages"]