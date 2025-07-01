import os
import logging
from flask import Flask, request, jsonify
from langchain_core.messages import HumanMessage
from src.agents.modules.agent import RagAgent
from src.agents.modules.tools import ALL_TOOLS_LIST

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Global variable to hold the agent instance
agent_instance = None

def initialize_agent():
    """
    Initializes the RagAgent instance.
    This is called before the first request.
    """
    global agent_instance
    if agent_instance is None:
        try:
            logger.info("🚀 Initializing RagAgent...")
            agent_instance = RagAgent(tools=ALL_TOOLS_LIST)
            logger.info("✅ RagAgent initialized successfully.")
        except Exception as e:
            logger.critical(f"❌ Failed to initialize RagAgent: {e}", exc_info=True)
            # This will cause the app to fail on first request if agent fails,
            # which is desirable to avoid running in a broken state.
            raise RuntimeError("Could not initialize the agent.") from e

@app.before_request
def before_request_func():
    # Initialize agent before the first request
    initialize_agent()

@app.route('/chat', methods=['POST'])
def chat_with_agent():
    """
    Endpoint to handle a chat interaction with the agent.
    """
    if agent_instance is None:
        return jsonify({"error": "Agent not initialized."}), 503

    data = request.get_json()
    if not data or 'message' not in data:
        return jsonify({"error": "The 'message' field is required."}), 400

    message = data['message']
    thread_id = data.get('thread_id', 'default-thread')

    logger.info(f"📬 Received chat request for thread '{thread_id}'")

    # Configuration for the LangGraph agent stream
    config = {"configurable": {"thread_id": thread_id}}
    
    # The input for the graph stream
    input_for_graph = {"messages": [HumanMessage(content=message)]}

    try:
        # Stream the agent's response
        final_event_state = None
        for event in agent_instance.graph.stream(input_for_graph, config=config, stream_mode="values"):
            final_event_state = event

        # Get the final state from the checkpointer
        final_graph_state = agent_instance.graph.get_state(config)
        
        if final_graph_state and final_graph_state.values['messages']:
            final_agent_message = final_graph_state.values['messages'][-1]
            response_content = getattr(final_agent_message, 'content', "No content in final message.")
            
            logger.info(f"💬 Agent response for thread '{thread_id}': {response_content}")
            return jsonify({"response": response_content})
        else:
            logger.error(f"No final state found for thread '{thread_id}'")
            return jsonify({"error": "Could not retrieve agent's final response."}), 500

    except Exception as e:
        logger.error(f"❌ Error during agent interaction: {e}", exc_info=True)
        return jsonify({"error": f"An internal error occurred: {e}"}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """
    Health check endpoint to verify the API is running.
    """
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    # This is for local development, not for production.
    # Production will use Gunicorn.
    app.run(host="0.0.0.0", port=8081, debug=True)