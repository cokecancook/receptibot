import unittest
import json
from datetime import datetime, timedelta
import requests

#import @tools from tools.py
from tools import check_gym_availability

today = datetime.now().isoformat()
today_day = today.split("T")[0]
tomorrow = (datetime.now() + timedelta(days=1)).isoformat()
tomorrow_day = tomorrow.split("T")[0]

class APITestCase(unittest.TestCase):
    def test_availability_missing_start_time(self):
        # Missing start_time should return error 400
        payload = {"service_name": "gimnasio"}
        print("test_availability_missing_start_time - Sending request:", payload)
        response = requests.post("http://localhost:8000/availability", json=payload)
        print("test_availability_missing_start_time - Received response:", response.status_code, response.text)
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("error", data)
        
        # test_availability_missing_start_time - Sending request:
        #   {'service_name': 'gimnasio'}
        # test_availability_missing_start_time - Received response:
        #   400 {"error": "El campo 'start_time' es obligatorio."}

    def test_availability_invalid_service(self):
        # Use invalid service name
        payload = {"service_name": "pool", "start_time": f'{tomorrow_day}T00:00:00'}
        print("test_availability_invalid_service - Sending request:", payload)
        response = requests.post("http://localhost:8000/availability", json=payload)
        print("test_availability_invalid_service - Received response:", response.status_code, response.text)
        self.assertEqual(response.status_code, 404)
        data = response.json()
        self.assertIn("error", data)
        
        # test_availability_invalid_service - Sending request: 
        #   {'service_name': 'pool', 'start_time': '2025-06-19T00:00:00'}
        # test_availability_invalid_service - Received response: 
        #   404 {"error": "Servicio no encontrado. Use 'gimnasio' o 'sauna'."}

    def test_availability_with_date(self):
        # Valid availability using only a date (returns up to 3 slots)
        payload = {"service_name": "gimnasio", "start_time": tomorrow_day}
        print("test_availability_with_date - Sending request:", payload)
        response = requests.post("http://localhost:8000/availability", json=payload)
        print("test_availability_with_date - Received response:", response.status_code, response.text)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)
        
        # test_availability_with_date - Sending request:
        #   {'service_name': 'gimnasio', 'start_time': '2025-06-19T00:00:00'}
        # test_availability_with_date - Received response:
        #   200 [
        #   {
        #     "available_slots": 5,
        #     "current_bookings": 5,
        #     "slot_id": 35,
        #     "start_time": "2025-06-19T08:00:00",
        #     "total_capacity": 10
        #   },
        #   {
        #     "available_slots": 9,
        #     "current_bookings": 1,
        #     "slot_id": 36,
        #     "start_time": "2025-06-19T09:00:00",
        #     "total_capacity": 10
        #   },
        #   {
        #     "available_slots": 10,
        #     "current_bookings": 0,
        #     "slot_id": 37,
        #     "start_time": "2025-06-19T10:00:00",
        #     "total_capacity": 10
        #   }
        #   ]

    def test_availability_with_full_datetime(self):
        # Valid availability with full datetime format
        payload = {"service_name": "gimnasio", "start_time": f"{tomorrow_day}T08:00:00"}
        print("test_availability_with_full_datetime - Sending request:", payload)
        response = requests.post("http://localhost:8000/availability", json=payload)
        print("test_availability_with_full_datetime - Received response:", response.status_code, response.text)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)
    
        # test_availability_with_full_datetime - Sending request:
        #   {'service_name': 'gimnasio', 'start_time': '2025-06-19T08:00:00'}
        # test_availability_with_full_datetime - Received response: 200 [
        #   {
        #     "available_slots": 5,
        #     "current_bookings": 5,
        #     "slot_id": 35,
        #     "start_time": "2025-06-19T08:00:00",
        #     "total_capacity": 10
        #   }
        #   ]
    

    def test_create_booking(self):
        # First, get an available slot
        avail_payload = {"service_name": "gimnasio", "start_time": f"{tomorrow_day}T08:00:00"}
        print("test_create_booking - Sending availability request:", avail_payload)
        avail_response = requests.post("http://localhost:8000/availability", json=avail_payload)
        print("test_create_booking - Availability response:", avail_response.status_code, avail_response.text)
        self.assertEqual(avail_response.status_code, 200)
        slots = avail_response.json()

        if not slots:
            self.skipTest("No available slots found to test booking.")
        slot_id = slots[0]["slot_id"]

        # Attempt booking the available slot
        booking_payload = {"slot_id": slot_id, "guest_name": "Test User"}
        print("test_create_booking - Sending booking request:", booking_payload)
        book_response = requests.post("http://localhost:8000/booking", json=booking_payload)
        print("test_create_booking - Booking response:", book_response.status_code, book_response.text)
        self.assertIn(book_response.status_code, [201, 409])
        if book_response.status_code == 201:
            booking_data = book_response.json()
            self.assertEqual(booking_data["slot_id"], slot_id)
            self.assertEqual(booking_data["guest_name"], "Test User")
            
        # test_create_booking - Sending availability request:
        #     5-06-19T08:00:00'}
        # test_create_booking - Availability response: 200 [
        #     {
        #         "available_slots": 5,
        #         "current_bookings": 5,
        #         "slot_id": 35,
        #         "start_time": "2025-06-19T08:00:00",
        #         "total_capacity": 10
        #     }
        #     ]

        #     test_create_booking - Sending booking request: {'slot_id': 35, 'guest_name': 'Test User'}
        #     test_create_booking - Booking response: 201 {
        #     "guest_name": "Test User",
        #     "id": 223,
        #     "slot_id": 35
        #     }

if __name__ == "__main__":
    unittest.main()