from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import AzureOpenAI
import os, json, time, uuid, re
from dotenv import load_dotenv
import cosmos_helper

load_dotenv()
client = AzureOpenAI(
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    api_version=os.getenv("AZURE_OPENAI_API_VERSION")
)

deployment_name = os.getenv("AZURE_OPENAI_DEPLOYMENT")
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

user_sessions = {}
class UserInput(BaseModel):
    session_id: str
    answer: str

# ✅ Preserve AI JSON and add metadata
def finalize_result(result_json, session_id):
    result_json["id"] = session_id
    result_json["session_id"] = session_id
    result_json["_rid"] = str(uuid.uuid4())
    result_json["_self"] = f"dbs/{session_id}/colls/{session_id}/docs/{session_id}/"
    result_json["_etag"] = "\"fake-etag-0000\""
    result_json["_attachments"] = "attachments/"
    result_json["_ts"] = int(time.time())
    return result_json

def extract_days(answer: str) -> int:
    text = answer.lower()
    match = re.search(r"(\d+)\s*(day|days|night|nights)", text)
    if match:
        return int(match.group(1))
    return 3

@app.post("/chat")
async def chat(user_input: UserInput):
    session_id = user_input.session_id
    answer = (user_input.answer or "").strip()

    # Step 1: Greeting
    if session_id not in user_sessions:
        user_sessions[session_id] = {
            "mode": None,
            "ready": False,
            "history": [],
            "asked_another": False,
            "result": None,
            "expecting_origin": False,
            "origin": None
        }
        greeting = (
            "Hello!\n"
            "Welcome to Easy Trip. I am Laura your personal travel assistant.\n"
            "How can I help you today?"
        )
        return {
            "next_question": greeting,
            "options": ["Build a Travel Itinerary", "Get help with Destinations", "Contact Support"]
        }

    session = user_sessions[session_id]
    session["history"].append(answer)

    # Step 2: Handle option selection
    if session["mode"] is None:
        if "itinerary" in answer.lower():
            session["mode"] = "itinerary"
            session["expecting_origin"] = True
            return {
                "next_question": "Great! First, tell me — from where are you planning your trip?"
            }
        elif "destination" in answer.lower():
            session["mode"] = "destinations"
            return {"next_question": "Sure! Tell me which destinations you’re interested in and I can share details."}
        elif "support" in answer.lower():
            session["mode"] = "support"
            return {"next_question": "Okay, connecting you to support. Please describe your issue."}
        else:
            return {"next_question": "Please choose 1, 2, or 3 from the options."}

    # ✅ Step 2.1: Capture origin city
    if session.get("expecting_origin"):
        session["origin"] = answer
        session["expecting_origin"] = False
        return {
            "next_question": (
                f"Awesome! You're starting from {answer}. Now tell me more about your travel preferences.\n"
                "For example: 'I am travelling alone to New York for 2 days and I am looking for leisure stay with some good hotels in the neighbourhood, consider a good night life as well.'"
            )
        }

    user_choice = answer.lower()

    # ✅ Generate Persona + Itinerary
    if user_choice in ["1", "generate persona", "generate persona & recommendations", "persona"]:
        session["ready"] = True
        days = extract_days(" ".join(session["history"]))
        plan_prompt = f"""
You are a travel assistant. Based on this user description:
{" ".join(session["history"])}
Origin city: {session.get("origin", "Unknown")}
Generate a travel itinerary in the following exact JSON format:
{{
  "persona": "A short description of the traveler",
  "cities": [
    {{
      "city_name": "City Name",
      "hotel": {{
        "name": "Hotel Name",
        "address": "Full address",
        "latitude": 0.0,
        "longitude": 0.0,
        "check_in": "HH:MM AM/PM",
        "check_out": "HH:MM AM/PM"
      }},
      "recommendations": [
        {{
          "day": "Day X - Title",
          "arrival_time": "HH:MM AM/PM",
          "activities": [
            {{
              "time": "HH:MM AM/PM",
              "action": "Arrival",
              "name": "Arrival at <Airport Name>",
              "address": "Airport full address",
              "latitude": 0.0,
              "longitude": 0.0,
              "travel_distance_from_previous": "0 km",
              "travel_time_from_previous": "0 mins",
              "highlights": "3–4 descriptive sentences about arriving at the airport and first impressions of the city.",
              "rating": 4.5,
              "reviews": [
                "Review 1: Short user-style review.",
                "Review 2: Another short user-style review."
              ]
            }},
            {{
              "time": "HH:MM AM/PM",
              "action": "Transfer",
              "name": "Transfer from <Airport Name> to <Hotel Name>",
              "address": "Airport full address → Hotel full address",
              "latitude": 0.0,
              "longitude": 0.0,
              "travel_distance_from_previous": "X km",
              "travel_time_from_previous": "X mins by taxi/metro",
              "highlights": "3–4 descriptive sentences about the journey from the airport to the hotel, including scenery and local atmosphere.",
              "rating": 4.5,
              "reviews": [
                "Review 1: Short user-style review.",
                "Review 2: Another short user-style review."
              ]
            }},
            {{
              "time": "HH:MM AM/PM",
              "action": "Pre Check-in Activity",
              "name": "Nearby activity or sightseeing spot before hotel check-in",
              "address": "Full address",
              "latitude": 0.0,
              "longitude": 0.0,
              "travel_distance_from_previous": "X km",
              "travel_time_from_previous": "X mins",
              "highlights": "If arrival is before check-in, include meaningful activities (brunch, sightseeing, park, etc.) so there are no long gaps.",
              "carry": "Suggested items to carry (camera, water bottle, sunscreen, etc.)",
              "rating": 4.5,
              "reviews": [
                "Review 1: Short user-style review.",
                "Review 2: Another short user-style review."
              ]
            }},
            {{
              "time": "Hotel official check-in time (e.g. 03:00 PM)",
              "action": "Hotel Check-in",
              "name": "<Hotel Name>",
              "address": "Hotel full address",
              "latitude": 0.0,
              "longitude": 0.0,
              "travel_distance_from_previous": "0 km",
              "travel_time_from_previous": "0 mins",
              "highlights": "3–4 descriptive sentences about the hotel facilities, ambiance, location, and why it’s a good base for the trip.",
              "rating": 4.5,
              "reviews": [
                "Review 1: Short user-style review.",
                "Review 2: Another short user-style review."
              ]
            }},
            {{
              "time": "HH:MM AM/PM",
              "name": "Activity or Sightseeing Spot",
              "address": "Full address",
              "latitude": 0.0,
              "longitude": 0.0,
              "travel_distance_from_previous": "X km",
              "travel_time_from_previous": "X mins",
              "highlights": "3–4 descriptive sentences about what makes this place special, what to do there, and why travelers enjoy it.",
              "carry": "Suggested items to carry (camera, water bottle, comfortable shoes, ID, tickets, etc.)",
              "rating": 4.5,
              "reviews": [
                "Review 1: Short user-style review.",
                "Review 2: Another short user-style review."
              ]
            }},
            {{
              "time": "HH:MM AM/PM",
              "meal": "Breakfast/Lunch/Dinner",
              "name": "Restaurant Name",
              "address": "Full address",
              "latitude": 0.0,
              "longitude": 0.0,
              "travel_distance_from_previous": "X km",
              "travel_time_from_previous": "X mins",
              "highlights": "3–4 descriptive sentences about the restaurant, its cuisine, and why it’s worth visiting.",
              "rating": 4.5,
              "reviews": [
                "Review 1: Short user-style review.",
                "Review 2: Another short user-style review."
              ]
            }},
            {{
              "time": "End of Day",
              "action": "Return to Hotel",
              "name": "<Hotel Name>",
              "address": "Hotel full address",
              "latitude": 0.0,
              "longitude": 0.0,
              "travel_distance_from_previous": "X km",
              "travel_time_from_previous": "X mins",
              "highlights": "Always end the day by returning to the hotel for rest. Describe how this ensures comfort and closure to the day.",
              "rating": 4.5,
              "reviews": [
                "Review 1: Short user-style review.",
                "Review 2: Another short user-style review."
              ]
            }}
          ]
        }}
      ]
    }}
  ],
  "inter_city_travel": [
    {{
      "from_city": "Origin City",
      "to_city": "Destination City",
      "mode": "Flight/Train/Bus",
      "departure_time": "HH:MM AM/PM",
      "arrival_time": "HH:MM AM/PM",
      "travel_duration": "Xh Ym",
      "departure_point": {{
        "name": "Station or Airport Name",
        "address": "Full address",
        "latitude": 0.0,
        "longitude": 0.0
      }},
      "arrival_point": {{
        "name": "Station or Airport Name",
        "address": "Full address",
        "latitude": 0.0,
        "longitude": 0.0
      }}
    }},
    {{
      "from_city": "Destination City",
      "to_city": "Origin City",
      "mode": "Flight/Train/Bus",
      "departure_time": "HH:MM AM/PM",
      "arrival_time": "HH:MM AM/PM",
      "travel_duration": "Xh Ym",
      "departure_point": {{
        "name": "Station or Airport Name",
        "address": "Full address",
        "latitude": 0.0,
        "longitude": 0.0
      }},
      "arrival_point": {{
        "name": "Station or Airport Name",
        "address": "Full address",
        "latitude": 0.0,
        "longitude": 0.0
      }}
    }}
  ]
}}
Rules:
- Output must be valid JSON only.
- Always include latitude and longitude.
- Always include hotel details inside each city.
- Always split airport arrival, airport-to-hotel transfer, and hotel check-in into separate activities.
- Hotel check-in must happen at the official time (usually 3:00 PM or hotel’s stated check-in time).
- If arrival is before check-in, the traveler **must have planned activities between airport transfer and official check-in** (e.g., sightseeing, brunch, local market, park visit). Do not leave gaps in the itinerary.
- After check-in, continue with afternoon/evening activities.
- Each day must end with the traveler **returning to their hotel** or a nightlife spot that is near the hotel, never stranded outside.
- If the user moves to a new city or checks into a new hotel, **include that hotel check-in explicitly** in the new city’s activities (with full address, latitude, longitude, check-in/out time).
- Always make activities chronological with realistic travel times and meal breaks.
- Always include both "travel_distance_from_previous" (in km) and "travel_time_from_previous".
- Meals must only be: Breakfast (7–10 AM), Lunch (12–2 PM), Dinner (7–9 PM).
- Do not mark nightlife or clubs as meals. Nightlife should be its own activity with "action": "Nightlife".
- Avoid repeating the same place (except hotel check-in/check-out).
- Keep travel times consistent with distances (e.g., 1 km ≈ 10 mins walk, 5 km ≈ 15 mins by taxi).
- For each activity, always include a "highlights" field with 3–4 descriptive sentences (travel-guide style).
- For each activity, always include a "carry" field listing practical items (if applicable).
- For each activity, always include a "rating" (decimal between 1.0 and 5.0).
- For each activity, always include a "reviews" field with 2 short user-style reviews.
- Always include a full round trip:
  - One inter_city_travel leg from the origin city (e.g., Bengaluru) to the destination city.
  - One inter_city_travel leg returning from the destination city back to the origin city.
  - The return journey must happen after the last day of the trip.
- Day 1 must always start with airport arrival, then transfer, then **pre-check-in activities**, then official hotel check-in.
- Day N (last day) must always end with **hotel check-out and return to airport/train station**.
- Create a {days}-day plan.
"""

        response = client.chat.completions.create(
            model=deployment_name,
            messages=[
                {"role": "system", "content": "You are a helpful travel assistant."},
                {"role": "user", "content": plan_prompt}
            ],
            response_format={"type": "json_object"}
        )

        raw_content = response.choices[0].message.content
        try:
            result_json = json.loads(raw_content)
        except Exception:
            return {"done": False, "error": "Invalid JSON from AI", "raw": raw_content}

        final_result = finalize_result(result_json, session_id)
        session["result"] = final_result

        try:
            cosmos_helper.save_result(final_result)
        except Exception as e:
            print("Cosmos DB error:", e)

        feedback = []
        text = " ".join(session["history"]).lower()
        if re.search(r"[A-Z][a-z]+", " ".join(session["history"])):
            feedback.append("Awesome! Destination locked ✈️")
        if re.search(r"\b\d+\s*(day|days|night|nights)\b", text):
            feedback.append("Got your duration 🗓️")
        for w in ["work", "leisure", "adventure", "food", "culture", "holiday", "business"]:
            if w in text:
                feedback.append(f"Noted — {w.capitalize()} trip 🎯")
                break
        feedback.append("Here’s your personalized persona and travel plan 🎉")

        return {"done": True, "feedback": feedback, "result": final_result, "options": ["Update Plan", "End Chat"]}

    # ✅ Ask Another Question
    if user_choice in ["2", "ask another", "ask another question"]:
        clarify_prompt = f"""
The user so far said: {" ".join(session["history"])}.
Ask ONE more clarifying question about their trip.
Make it conversational and friendly.
"""
        clarify_resp = client.chat.completions.create(
            model=deployment_name,
            messages=[
                {"role": "system", "content": "You are a helpful travel assistant."},
                {"role": "user", "content": clarify_prompt}
            ]
        )
        next_q = clarify_resp.choices[0].message.content.strip()
        if session["asked_another"]:
            session["asked_another"] = False
            return {"next_question": next_q}
        session["asked_another"] = True
        return {"next_question": next_q, "options": ["Generate Persona & Recommendations", "Ask Another Question"]}

    # ✅ Step 4: Acknowledge itinerary mode before persona
    if session["mode"] == "itinerary" and not session["ready"]:
        ack_prompt = f"""
The user said: "{answer}".
Acknowledge briefly and ask:
"Do you want me to generate your persona and travel plan now, or should I ask you another question to refine your trip?"
"""
        ack_resp = client.chat.completions.create(
            model=deployment_name,
            messages=[
                {"role": "system", "content": "You are a helpful travel assistant."},
                {"role": "user", "content": ack_prompt}
            ]
        )
        next_q = ack_resp.choices[0].message.content.strip()
        return {"next_question": next_q, "options": ["Generate Persona & Recommendations", "Ask Another Question"]}

       # ✅ Step 5: Updates after plan is generated (natural language + enrichment)
    if session.get("result"):
        current_result = session["result"]
        updated = False
        feedback_msgs = []
 
        # --- Make sure we work inside cities[0]["recommendations"] ---
        cities = current_result.get("cities", [])
        if not cities or "recommendations" not in cities[0]:
            return {"next_question": "No recommendations found in your current plan to update."}
        recommendations = cities[0]["recommendations"]

        # --- AI prompt to parse natural language into actions ---
        intent_prompt = f"""
You are an intent parser for a travel itinerary assistant.
The user said: "{answer}".
Return a JSON object with a list of actions. Each action must be one of:
- {{ "action": "remove", "activity": "<name>" }}
- {{ "action": "add", "activity": "<name>", "address": "<address or location hint>"}}
- {{ "action": "regenerate", "day": "<day number or title>" }}
Rules:
- If the user says "replace X with Y", output two actions: remove X, add Y.
- If the user says "instead of X add Y", do the same.
- If no clear action, return {{ "actions": [] }}.
Return valid JSON only.
"""
        try:
            intent_resp = client.chat.completions.create(
                model=deployment_name,
                messages=[
                    {"role": "system", "content": "You are a precise intent-to-JSON parser."},
                    {"role": "user", "content": intent_prompt}
                ],
                response_format={"type": "json_object"}
            )
            actions_json = json.loads(intent_resp.choices[0].message.content)
            actions = actions_json.get("actions", [])
        except Exception as e:
            print("Intent parsing error:", e)
            actions = []

        # --- Apply all actions ---
        for act in actions:
            if act["action"] == "remove":
                target = act["activity"].lower()
                for day in recommendations:
                    before = len(day["activities"])
                    day["activities"] = [a for a in day["activities"] if target not in a.get("name", "").lower()]
                    if len(day["activities"]) < before:
                        updated = True
                        feedback_msgs.append(f"Okay, I’ve removed {act['activity']} from your plan ✂️")
            elif act["action"] == "add":
                name = act["activity"]
                addr_hint = act.get("address", "")
                # 🔹 Ask Azure OpenAI to enrich with full address + lat/lon
                geo_prompt = f"""
You are a travel assistant with knowledge of places worldwide.
Find the full postal address and approximate latitude/longitude for this place:
{name}, {addr_hint}.
Return JSON only in this format:
{{
  "address": "Full address",
  "latitude": 12.34,
  "longitude": 56.78
}}
"""
                try:
                    geo_resp = client.chat.completions.create(
                        model=deployment_name,
                        messages=[
                            {"role": "system", "content": "You are a precise place geocoder."},
                            {"role": "user", "content": geo_prompt}
                        ],
                        response_format={"type": "json_object"}
                    )
                    geo_json = json.loads(geo_resp.choices[0].message.content)
                    address = geo_json.get("address", addr_hint or "Unknown")
                    lat = geo_json.get("latitude", 0.0)
                    lon = geo_json.get("longitude", 0.0)
                except Exception as e:
                    print("Geocoding via AI failed:", e)
                    address, lat, lon = addr_hint or "Unknown", 0.0, 0.0
                new_activity = {
                    "name": name,
                    "address": address,
                    "latitude": lat,
                    "longitude": lon
                }
                if recommendations:
                    recommendations[-1]["activities"].append(new_activity)
                    updated = True
                    feedback_msgs.append(f"Got it! I’ve added {name} to your plan 🗺️")
            elif act["action"] == "regenerate":
                day_str = act["day"]
                regen_prompt = f"Regenerate a new plan for {day_str} for: {' '.join(session['history'])}.\nInclude full address, latitude, longitude, travel distance and travel time for each activity."
                try:
                    regen_resp = client.chat.completions.create(
                        model=deployment_name,
                        messages=[
                            {"role": "system", "content": "You are a helpful travel assistant."},
                            {"role": "user", "content": regen_prompt}
                        ],
                        response_format={"type": "json_object"}
                    )
                    regen_json = json.loads(regen_resp.choices[0].message.content)
                    if regen_json.get("recommendations"):
                        idx = int(re.findall(r'\d+', day_str)[0]) - 1
                        if 0 <= idx < len(recommendations):
                            recommendations[idx] = regen_json["recommendations"][0]
                            updated = True
                            feedback_msgs.append(f"Sure! I’ve refreshed {day_str} with new ideas 🔄")
                except Exception as e:
                    feedback_msgs.append(f"Sorry, I couldn’t regenerate {day_str}: {e}")
        # --- Save updates or fallback ---
        if updated:
            session["result"] = current_result
            try:
                cosmos_helper.save_result(session_id, current_result["persona"], cities)
            except Exception as e:
                print("Cosmos DB save error:", e)
            return {"done": True, "feedback": feedback_msgs, "result": current_result, "options": ["Update Plan", "End Chat"]}
        else:
            return {"next_question": "I couldn’t understand your request. Could you rephrase what to update in your plan?"}