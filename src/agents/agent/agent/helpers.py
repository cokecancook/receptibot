def check_ollama_connection(model: str) -> bool:
    import requests
    try:
        version_response = requests.get("http://localhost:11434/api/version")
        if version_response.status_code != 200:
            return False
        list_response = requests.get("http://localhost:11434/api/tags")
        if list_response.status_code != 200:
            return False
        available_models = list_response.json()["models"]
        model_found = any(m['name'].startswith(model) for m in available_models)
        if not model_found:
            print(f"Model '{model}' not found. Please check if the container is running and the model exists. {model}")
            return False
        return True
    except Exception:
        return False
