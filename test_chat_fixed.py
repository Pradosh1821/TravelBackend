import requests
import uuid
import json
 
# Generate a unique session ID per run
session_id = str(uuid.uuid4())
url = "http://127.0.0.1:8000/chat"
def send(answer):
    resp = requests.post(url, json={
        "session_id": session_id,
        "answer": answer
    })
    return resp.json()

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