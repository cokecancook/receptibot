# app_hf.py

import os
from dotenv import load_dotenv
from typing import TypedDict, List, Optional

from langgraph.graph import StateGraph, END
from langchain_core.messages import SystemMessage, HumanMessage, BaseMessage, AIMessage, ToolMessage
from huggingface_hub import InferenceClient

from tools import check_gym_availability, book_gym_slot
from system_prompt import SYSTEM_PROMPT

# Load environment variables
load_dotenv()
userdata = os.environ

# Initialize HuggingFace client
client = InferenceClient(
    provider="groq",
    api_key=userdata.get('HF_TOKEN'),
)

model = "Qwen/Qwen3-32B"

# Define tools
tools = [check_gym_availability, book_gym_slot]

# Define state schema
class GraphState(TypedDict):
    messages: List[BaseMessage]
    tool_calls: Optional[List]
    tool_outputs: Optional[List]

# Create SystemMessage with the prompt
system_message = SystemMessage(content=SYSTEM_PROMPT.strip())

def call_llm(state: GraphState) -> GraphState:
    try:
        messages = state["messages"]
        formatted_messages = []
        
        for msg in messages:
            if isinstance(msg, SystemMessage):
                formatted_messages.append({"role": "system", "content": msg.content})
            elif isinstance(msg, HumanMessage):
                formatted_messages.append({"role": "user", "content": msg.content})
            elif isinstance(msg, AIMessage):
                formatted_messages.append({"role": "assistant", "content": msg.content})
            elif isinstance(msg, ToolMessage):
                formatted_messages.append({"role": "function", "content": msg.content})
        
        completion = client.chat.completions.create(
            model=model,
            messages=formatted_messages
        )
        
        response = AIMessage(content=completion.choices[0].message['content'])
        
        return {
            "messages": state["messages"] + [response],
            "tool_calls": [], 
            "tool_outputs": []
        }
    except Exception as e:
        print(f"Error calling LLM: {str(e)}")
        print(f"Error type: {type(e)}")
        error_message = AIMessage(content="I apologize, but I'm having trouble processing your request. Please try again.")
        return {
            "messages": state["messages"] + [error_message],
            "tool_calls": [],
            "tool_outputs": []
        }

def call_tools(state: GraphState) -> GraphState:
    outputs = []
    if not state.get("tool_calls"):
        return {
            "messages": state["messages"],
            "tool_calls": [],
            "tool_outputs": []
        }

    for call in state["tool_calls"]:
        print("DEBUG: Processing tool call:", call)
        tool_map = {t.name: t for t in tools}
        tool = tool_map.get(call["name"])
        
        if tool is None:
            outputs.append(f"Error: Tool '{call['name']}' not found.")
            continue
        
        try:
            output = tool(**call["args"])
            outputs.append(output)
        except Exception as e:
            outputs.append(f"Error calling tool {call['name']}: {e}")

    return {
        "messages": state["messages"],
        "tool_calls": [],
        "tool_outputs": outputs
    }

def add_tool_outputs_to_messages(state: GraphState) -> GraphState:
    tool_outputs = state.get("tool_outputs", [])
    tool_calls = state.get("tool_calls", [])
    
    if not tool_outputs or not tool_calls:
        return state

    tool_messages = []
    for call, output in zip(tool_calls, tool_outputs):
        tool_messages.append(ToolMessage(content=str(output), tool_call_id=call.get('id', 'unknown')))

    return {
        "messages": state["messages"] + tool_messages,
        "tool_outputs": [],
        "tool_calls": []
    }

# Build graph
graph = StateGraph(GraphState)

graph.add_node("llm", call_llm)
graph.add_node("tools", call_tools)
graph.add_node("format_tool_outputs", add_tool_outputs_to_messages)

graph.set_entry_point("llm")

def should_call_tools(state: GraphState):
    last_message = state['messages'][-1]
    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        state['tool_calls'] = last_message.tool_calls
        return "tools"
    return END

graph.add_conditional_edges("llm", should_call_tools)
graph.add_edge("tools", "format_tool_outputs")
graph.add_edge("format_tool_outputs", "llm")

runnable = graph.compile()

if __name__ == "__main__":
    print("Hey! I'm a gym booking assistant. How can I help? (Type 'exit' to quit)")
    messages = [system_message]
    
    while True:
        user = input("\nYou: ")
        if user.lower() == "exit":
            break
            
        messages.append(HumanMessage(content=user))
        result = runnable.invoke({"messages": messages})
        final_response = result["messages"][-1]
        print("\nBot:", final_response.content)
        messages = result["messages"]