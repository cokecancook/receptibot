from langchain_ollama import ChatOllama

from agent.tools import check_gym_availability, book_gym_slot

model = "qwen3:1.7b"
tools = [check_gym_availability, book_gym_slot]

llm = ChatOllama(
    model=model, 
    base_url="http://localhost:11434/",
    temperature=0,
    streaming=False
)
llm_with_tools = llm.bind_tools(tools)
