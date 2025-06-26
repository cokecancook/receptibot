import sys
import os

print("--- DIAGNOSTIC START ---")
print(f"Python Executable: {sys.executable}")
print(f"Python Version: {sys.version}")
print(f"This file location: {os.path.abspath(__file__)}")
print("--- DIAGNOSTIC END ---")

from langchain_ollama import ChatOllama

from agent.tools import check_gym_availability, book_gym_slot

model = "qwen3:8b"
tools = [check_gym_availability, book_gym_slot]

llm = ChatOllama(
    model=model, 
    base_url="http://localhost:11434/",
    temperature=0,
    streaming=False
)
llm_with_tools = llm.bind_tools(tools)
