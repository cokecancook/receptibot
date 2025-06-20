import requests
from langchain_core.tools import tool
from datetime import datetime, date, timedelta

        
# ==============================================================================
# TOOL 1: CHECK GYM AVAILABILITY
# ==============================================================================
@tool
def check_gym_availability(target_date: str) -> str:
    """
    Checks gym slot availability for a given date. Use this as the FIRST step for any user query about the gym.
    
    Parameter:
    - target_date: A string in ISO 8601 format (YYYY-MM-DDTHH:MM:SS) representing the date and time to check availability.
    
    Implementation:
    - If no time is defined, booking_date will include T00:00:00, as YYYY-MM-DDT00:00:00. (Pending! Now time defined is represented as YYYY-MM-DD)
        - API RESPONSE will be the first 3 available slots from YYYY-MM-DDT08:00:00 to YYYY-MM-DDT21:00:00. (Fix Pending! Now next slots are return even if at full capacity and technically unavailable)
    - If time is defined, booking_date will be as: from YYYY-MM-DDT08:00:00 to YYYY-MM-DDT21:00:00.
        - If time is defined, and slot is available, answer from the API will be the available slot. (Fix Pending! Now target_slot is return even if at full capacity and technically unavailable)
        - If time is defined, and slot is not available, answer from the API will be a message of unavailability and the next 3 available slots from YYYY-MM-DDT08:00:00 to YYYY-MM-DDT21:00:00.)
    
    This tool is read-only and does not make a booking.
    """
    url = "http://localhost:8000/availability"
        
    # Prepare payload; API expects 'service_name':'gimnasio' and 'start_time'
    payload = {
        "service_name": "gimnasio",
        "start_time": target_date
    }
    
    headers = {"Content-Type": "application/json"}
    response = requests.post(url, json=payload, headers=headers)
    
    if response.status_code == 200:
        start_times = [slot["start_time"] for slot in response.json()]
        return str(start_times)
    else:
        return f"Slot not available ({response.status_code}).\n\nNext slots available:\n{response.text}"    


# ==============================================================================
# TOOL 2: BOOK GYM SLOT
# ==============================================================================
@tool
def book_gym_slot(booking_date: str, user_name: str) -> str:
    """
    Books a specific time slot at the gym for a user after availability has been confirmed.
    WARNING: This action creates a reservation and has side effects.
    ONLY use this tool after confirming the exact date and time (together as booking_date) and the guest's name.
    
    Parameters:
    - booking_date: A string in ISO 8601 format (YYYY-MM-DDTHH:MM:SS) representing the date and time to book.
    - user_name: The full name of the person making the booking. This must be provided by the user before calling this tool.
    
    Implementation:
    - booking_date holds both date and time (e.g. "2025-06-16T08:00:00")
    - Checks availability for this exact slot.
    - If available, attempts the booking by sending booking_date and guest name and retuns a success message along with the slot ID and the guest name.
    - If not available, answer from the API will be a message of unavailability and the next 3 available slots from YYYY-MM-DDT08:00:00 to YYYY-MM-DDT21:00:00. (Pending implementation for next 3 available slots)

    """
    print(f"DEBUG: Attempting booking for {user_name} on {booking_date}.")

    # Check availability for the specified slot.
    avail_url = "http://localhost:8000/availability"
    avail_payload = {"service_name": "gimnasio", "start_time": booking_date}
    headers = {"Content-Type": "application/json"}
    
    avail_response = requests.post(avail_url, json=avail_payload, headers=headers)
    if avail_response.status_code != 200:
        return f"Unable to check availability (status code: {avail_response.status_code})."
    
    slots = avail_response.json()
    slot_id = None
    for slot in slots:
        if slot.get("start_time") == booking_date:
            slot_id = slot.get("slot_id")
            break
    
    if not slot_id:
        # Return the first 3 available slots.
        available_slots = [slot.get("start_time") for slot in slots][:3]
        return (f"Desired slot {booking_date} is not available.\n"
                f"Next available slots: {', '.join(available_slots)}")
    
    # Attempt booking now that the slot is confirmed available.
    book_url = "http://localhost:8000/booking"
    booking_payload = {
        "slot_id": slot_id,
        "guest_name": user_name
    }
    book_response = requests.post(book_url, json=booking_payload, headers=headers)
    
    if book_response.status_code == 201:
        booking_data = book_response.json()
        return (f"Booking successful: Slot ID {booking_data.get('slot_id')}, "
                f"Guest: {booking_data.get('guest_name')}.")
    elif book_response.status_code == 409:
        return f"Booking conflict: The slot {booking_date} is already booked or full."
    else:
        return f"Booking failed (status {book_response.status_code}): {book_response.text}"

# ==============================================================================
# BASIC TESTING FOR BOTH TOOLS
# ==============================================================================
if __name__ == "__main__":
    today = datetime.now().isoformat()
    today_day = today.split("T")[0]
    tomorrow = (datetime.now() + timedelta(days=1)).isoformat()
    tomorrow_day = tomorrow.split("T")[0]
    test_time = "12:00:00"  # Example time for testing
    
    # Testing Tool 1: check_gym_availability
    print("===== Test Check Gym Availability =====")
    test_date = f"{tomorrow_day}T{test_time}"

    avail_result = check_gym_availability.run({"target_date": test_date})
    print("Availability result:", avail_result)
    
    print("\n===== Test Book Gym Slot =====")
    # Sample test parameters (ensure that the API has an available slot for this test)
    booking_date = f"{today_day}T{test_time}"
    user_name = "Test User"
    book_result = book_gym_slot.run({"booking_date": booking_date, "user_name": user_name})
    print("Booking result:", book_result)