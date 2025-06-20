from langchain_core.messages import ToolMessage, AIMessage
from langchain_core.tools import ToolException

from agent.state import GraphState
from agent.llm_config import llm_with_tools
from agent.tools import check_gym_availability, book_gym_slot

tools = [check_gym_availability, book_gym_slot]

def call_llm(state: GraphState) -> GraphState:
    try:
        print("DEBUG: Sending request to LLM...")
        response = llm_with_tools.invoke(state["messages"])
        print("DEBUG: Received response:", response)
        return {
            "messages": state["messages"] + [response],
            "tool_calls": response.tool_calls if hasattr(response, "tool_calls") else [],
            "tool_outputs": [],
        }
    except Exception as e:
        print(f"Error calling LLM: {str(e)}")
        print(f"Error type: {type(e)}")
        error_message = AIMessage(content="I apologize, but I'm having trouble processing your request. Please try again.")
        return {
            "messages": state["messages"] + [error_message],
            "tool_calls": [],
            "tool_outputs": [],
        }

def call_tools(state: GraphState) -> GraphState:
    outputs = []
    if not state.get("tool_calls"):
        return {
            "messages": state["messages"],
            "tool_calls": [],
            "tool_outputs": [],
        }
    for call in state["tool_calls"]:
        print("DEBUG: Processing tool call:", call)
        tool_map = {t.name: t for t in tools}
        tool = tool_map.get(call["name"])
        if tool is None:
            print(f"DEBUG: Tool {call['name']} not found!")
            outputs.append(
                ToolException(f"Error: Tool '{call['name']}' not found.")
            )
            continue
        try:
            output = tool.invoke(call["args"])
            print(f"DEBUG: Tool {call['name']} returned: {output}")
            outputs.append(output)
        except Exception as e:
            outputs.append(ToolException(f"Error calling tool {call['name']}: {e}"))
    return {
        "messages": state["messages"],
        "tool_calls": [],
        "tool_outputs": outputs,
    }

def add_tool_outputs_to_messages(state: GraphState) -> GraphState:
    tool_outputs = state.get("tool_outputs", [])
    tool_calls = state.get("tool_calls", [])
    if not tool_outputs or not tool_calls:
        return state
    tool_messages = []
    for call, output in zip(tool_calls, tool_outputs):
        tool_messages.append(ToolMessage(content=str(output), tool_call_id=call['id']))
    return {
        "messages": state["messages"] + tool_messages,
        "tool_outputs": [],
        "tool_calls": []
    }
