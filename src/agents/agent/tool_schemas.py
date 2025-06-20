check_gym_availability_schema = {
    "type": "function",
    "function": {
        "name": "check_gym_availability",
        "description": "Check if the gym is available for a given time slot.",
        "parameters": {
            "type": "object",
            "properties": {
                "date": {
                    "type": "string",
                    "description": "Date and time to check availability (YYYY-MM-DDTHH:MM:SS)."
                }
            },
            "required": ["date"]
        }
    }
}

book_gym_slot_schema = {
    "type": "function",
    "function": {
        "name": "book_gym_slot",
        "description": "Book a gym slot for a user at a specified time.",
        "parameters": {
            "type": "object",
            "properties": {
                "date": {
                    "type": "string",
                    "description": "Date and time to book (YYYY-MM-DD:HH:MM:SS)."
                },
                "user": {
                    "type": "string",
                    "description": "User's name."
                }
            },
            "required": ["date", "user"]
        }
    }
}

tools = [check_gym_availability_schema, book_gym_slot_schema]