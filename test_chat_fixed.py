import requests
import uuid
import json
 
# Generate a unique session ID per run
session_id = str(uuid.uuid4())
url = "http://127.0.0.1:8000/chat"
def send(answer):
    try:
        resp = requests.post(url, json={
            "session_id": session_id,
            "answer": answer
        })
        
        # Check if response is empty or has no content
        if not resp.text.strip():
            print(f"\n⚠️ Empty response from server. Status code: {resp.status_code}")
            return {"error": "Empty response from server"}
        
        # Try to parse JSON
        return resp.json()
    except requests.exceptions.JSONDecodeError as e:
        print(f"\n⚠️ JSON decode error: {e}")
        print(f"Response status code: {resp.status_code}")
        print(f"Response text: {resp.text[:500]}...")  # Show first 500 chars
        return {"error": "Invalid JSON response", "raw_response": resp.text}
    except Exception as e:
        print(f"\n⚠️ Request error: {e}")
        return {"error": str(e)}

def handle_options(resp):
    """Handle options display and selection with dict object support"""
    print("\nOptions:")
    for idx, opt in enumerate(resp["options"], start=1):
        if isinstance(opt, dict):
            print(f"{idx}. {opt.get('name', str(opt))}")
        else:
            print(f"{idx}. {opt}")
 
    choice = input("\nChoose an option (or type your own): ").strip()
 
    if choice.isdigit() and 1 <= int(choice) <= len(resp["options"]):
        selected_option = resp["options"][int(choice) - 1]
        if isinstance(selected_option, dict):
            return selected_option.get("name", str(selected_option))
        else:
            return selected_option
    else:
        return choice
 
print(f"\n🚀 Starting new session: {session_id}")
 
# Start conversation with greeting
resp = send("hello")
 
while True:
    # Handle errors
    if resp.get("error"):
        print(f"\n❌ Error: {resp['error']}")
        if resp.get("raw_response"):
            print(f"Raw response: {resp['raw_response'][:200]}...")
        break
    
    # Case 1: Assistant asks next question
    if resp.get("next_question"):
        print("\nLaura:", resp["next_question"])
 
        if "options" in resp:
            user_answer = handle_options(resp)
        else:
            user_answer = input("\nYou: ").strip()
 
        # Special handling for "Update Plan"
        if isinstance(user_answer, str) and user_answer.lower() == "update plan":
            print("\n✍️ Enter your update request:")
            follow_up = input("You: ").strip()
            resp = send(follow_up)
        else:
            resp = send(user_answer)
 
    # Case 2: Final persona & recommendations (chat continues)
    elif resp.get("done"):
        print("\n💬 Laura's Feedback:")
        for f in resp.get("feedback", []):
            print("Laura:", f)
 
        # Always show updated plan after persona or update
        if "result" in resp:
            print("\n✅ Current Persona & Recommendations (stored in Cosmos DB):")
            print(json.dumps(resp["result"], indent=4))
 
        if "options" in resp:
            user_answer = handle_options(resp)
 
            if isinstance(user_answer, str) and user_answer.lower() == "end chat":
                print("\n👋 Chat ended.")
                break
 
            # Special handling for "Update Plan"
            if isinstance(user_answer, str) and user_answer.lower() == "update plan":
                print("\n✍️ Enter your update request (natural language allowed):")
                follow_up = input("You: ").strip()
                resp = send(follow_up)
            else:
                resp = send(user_answer)
        else:
            break
 
    # Case 3: Unexpected response
    else:
        print("\n⚠️ Unexpected response:", resp)
        break
 
print(f"\n📌 Session ID {session_id} stored in Cosmos DB")