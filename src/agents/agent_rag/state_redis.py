import redis
import json
from typing import Optional
from langchain_core.messages.base import messages_to_dict
from langchain_core.messages.utils import messages_from_dict
from .state import AgentState

# Configure Redis connection (adjust as needed)
r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

REDIS_PREFIX = "agent_state:"

def save_state_to_redis(key: str, state: AgentState) -> None:
    """
    Serialize and save AgentState to Redis under the given key.
    The 'messages' field is converted to a list of dicts using messages_to_dict.
    """
    serializable_state = state.copy()
    serializable_state['messages'] = messages_to_dict(state['messages'])
    r.set(f"{REDIS_PREFIX}{key}", json.dumps(serializable_state))

def load_state_from_redis(key: str) -> Optional[AgentState]:
    """
    Load AgentState from Redis by key and deserialize it.
    The 'messages' field is reconstructed using messages_from_dict.
    Returns None if no state is found.
    """
    data = r.get(f"{REDIS_PREFIX}{key}")
    if not data:
        return None
    state = json.loads(data)
    state['messages'] = messages_from_dict(state['messages'])
    return state 