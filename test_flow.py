#!/usr/bin/env python3
"""
Test script to verify the new chatbot flow
"""

import requests
import json

# Test the new flow
def test_new_flow():
    base_url = "http://localhost:8000"
    session_id = "test_session_123"
    
    # Step 1: Initial greeting
    response = requests.post(f"{base_url}/chat", json={
        "session_id": session_id,
        "answer": ""
    })
    print("Step 1 - Initial Greeting:")
    print(json.dumps(response.json(), indent=2))
    print("\n" + "="*50 + "\n")
    
    # Step 2: Select "Plan a Trip"
    response = requests.post(f"{base_url}/chat", json={
        "session_id": session_id,
        "answer": "Plan a Trip"
    })
    print("Step 2 - Plan a Trip:")
    print(json.dumps(response.json(), indent=2))
    print("\n" + "="*50 + "\n")
    
    # Step 3: Select travel vibe
    response = requests.post(f"{base_url}/chat", json={
        "session_id": session_id,
        "answer": "Bro-cation"
    })
    print("Step 3 - Travel Vibe:")
    print(json.dumps(response.json(), indent=2))
    print("\n" + "="*50 + "\n")
    
    # Step 4: Destination choice
    response = requests.post(f"{base_url}/chat", json={
        "session_id": session_id,
        "answer": "Yes, I have one in mind"
    })
    print("Step 4 - Destination Choice:")
    print(json.dumps(response.json(), indent=2))
    print("\n" + "="*50 + "\n")
    
    # Step 5: Manual destination input
    response = requests.post(f"{base_url}/chat", json={
        "session_id": session_id,
        "answer": "Bengaluru to Hawaii"
    })
    print("Step 5 - Manual Destination:")
    print(json.dumps(response.json(), indent=2))
    print("\n" + "="*50 + "\n")

if __name__ == "__main__":
    test_new_flow()