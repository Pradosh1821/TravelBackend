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
            "expecting_travel_style": False,
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
                "next_question": "Great! Let's start planning your journey. From which city will you be starting your trip?"
            }
        elif "destination" in answer.lower():
            session["mode"] = "destinations"
            return {"next_question": "Sure! Tell me which destinations you're interested in and I can share details."}
        elif "support" in answer.lower():
            session["mode"] = "support"
            return {"next_question": "Okay, connecting you to support. Please describe your issue."}
        else:
            return {"next_question": "Please choose 1, 2, or 3 from the options."}

    # ✅ Step 2.1: Capture origin city
    if session.get("expecting_origin"):
        session["origin"] = answer
        session["expecting_origin"] = False
        session["expecting_travel_style"] = True
        return {
            "next_question": f"Awesome! You're starting from {answer}. Let me understand your travel style better - Choose one Below",
            "options": [
                "Solo Traveler - no specific requirements",
                "Family Vacation - with fun, food at the beach", 
                "Perfect girls trip - to any beach destination",
                "None of these. I'll describe my trip myself"
            ]
        }
    
    # ✅ Step 2.2: Handle travel style selection
    if session.get("expecting_travel_style"):
        session["expecting_travel_style"] = False
        if "solo" in answer.lower():
            return {"next_question": "Got it! You're travelling solo - sounds exciting! Where are you planning to go?"}
        elif "family" in answer.lower():
            return {"next_question": "Perfect! A family vacation with fun and food at the beach sounds amazing! Where are you planning to go?"}
        elif "girls trip" in answer.lower():
            return {"next_question": "Awesome! A perfect girls trip to a beach destination - that's going to be so much fun! Where are you planning to go?"}
        elif "none" in answer.lower() or "describe" in answer.lower():
            return {"next_question": "No problem! Please describe your trip in your own words - tell me about your travel preferences, destination, duration, and what you're looking for."}
        else:
            # Handle numbered choices
            if answer.strip() == "1":
                return {"next_question": "Got it! You're travelling solo - sounds exciting! Where are you planning to go?"}
            elif answer.strip() == "2":
                return {"next_question": "Perfect! A family vacation with fun and food at the beach sounds amazing! Where are you planning to go?"}
            elif answer.strip() == "3":
                return {"next_question": "Awesome! A perfect girls trip to a beach destination - that's going to be so much fun! Where are you planning to go?"}
            elif answer.strip() == "4":
                return {"next_question": "No problem! Please describe your trip in your own words - tell me about your travel preferences, destination, duration, and what you're looking for."}
            else:
                return {"next_question": "Please choose one of the options (1, 2, 3, or 4)."}

    user_choice = answer.lower()

    # ✅ Generate Persona + Itinerary
    if user_choice in ["1", "generate persona", "generate persona & recommendations", "persona", "generate an itinerary", "itinerary"]:
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
        "check_out": "HH:MM AM/PM",
        "why_recommended": "1-2 sentences explaining why this hotel is recommended"
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
              "reviews": {{
                "Review 1": "Short user-style review.",
                "Review 2": "Another short user-style review."
              }}
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
              "reviews": {{
                "Review 1": "Short user-style review.",
                "Review 2": "Another short user-style review."
              }}
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
              "why_recommended": "1-2 sentences explaining why this pre check-in activity is recommended",
              "rating": 4.5,
              "reviews": {{
                "Review 1": "Short user-style review.",
                "Review 2": "Another short user-style review."
              }}
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
              "highlights": "3–4 descriptive sentences about the hotel facilities, ambiance, location, and why it's a good base for the trip.",
              "rating": 4.5,
              "reviews": {{
                "Review 1": "Short user-style review.",
                "Review 2": "Another short user-style review."
              }}
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
              "why_recommended": "1-2 sentences explaining why this place is recommended to visit",
              "rating": 4.5,
              "reviews": {{
                "Review 1": "Short user-style review.",
                "Review 2": "Another short user-style review."
              }}
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
              "highlights": "3–4 descriptive sentences about the restaurant, its cuisine, and why it's worth visiting.",
              "why_recommended": "1-2 sentences explaining why this restaurant is recommended",
              "rating": 4.5,
              "reviews": {{
                "Review 1": "Short user-style review.",
                "Review 2": "Another short user-style review."
              }}
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
              "reviews": {{
                "Review 1": "Short user-style review.",
                "Review 2": "Another short user-style review."
              }}
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
- Hotel check-in must happen at the official time (usually 3:00 PM or hotel's stated check-in time).
- If arrival is before check-in, the traveler **must have planned activities between airport transfer and official check-in** (e.g., sightseeing, brunch, local market, park visit). Do not leave gaps in the itinerary.
- After check-in, continue with afternoon/evening activities.
- Each day must end with the traveler **returning to their hotel** or a nightlife spot that is near the hotel, never stranded outside.
- If the user moves to a new city or checks into a new hotel, **include that hotel check-in explicitly** in the new city's activities (with full address, latitude, longitude, check-in/out time).
- Always make activities chronological with realistic travel times and meal breaks.
- Always include both "travel_distance_from_previous" (in km) and "travel_time_from_previous".
- Meals must only be: Breakfast (7–10 AM), Lunch (12–2 PM), Dinner (7–9 PM).
- Do not mark nightlife or clubs as meals. Nightlife should be its own activity with "action": "Nightlife".
- Avoid repeating the same place (except hotel check-in/check-out).
- Keep travel times consistent with distances (e.g., 1 km ≈ 10 mins walk, 5 km ≈ 15 mins by taxi).
- For each activity, always include a "highlights" field with 3–4 descriptive sentences (travel-guide style).
- For each activity, always include a "carry" field listing practical items (if applicable).
- For each activity, always include a "why_recommended" field with 1-2 sentences explaining why it's recommended (except for Arrival, Transfer, Return to Hotel, Hotel Check-out, Departure).
- For each activity, always include a "rating" (decimal between 1.0 and 5.0).
- For each activity, always include a "reviews" field as an object with "Review 1" and "Review 2" as keys with short reviews.
- For hotels, always include a "why_recommended" field explaining why the hotel is chosen.
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

        # Add summary section with counts only
        summary = {
            "counts": {
                "flights": 0,
                "transfers": 0,
                "hotels": 0,
                "activities": 0,
                "meals": 0
            }
        }
        
        # Count inter-city travel (flights)
        if "inter_city_travel" in result_json:
            summary["counts"]["flights"] = len(result_json["inter_city_travel"])
        
        # Count hotels, activities, meals, transfers from cities
        if "cities" in result_json:
            for city in result_json["cities"]:
                # Count hotels
                if "hotel" in city:
                    summary["counts"]["hotels"] += 1
                
                # Count activities, meals, transfers from recommendations
                if "recommendations" in city:
                    for day in city["recommendations"]:
                        if "activities" in day:
                            for activity in day["activities"]:
                                action = activity.get("action", "")
                                name = activity.get("name", "")
                                
                                if action == "Transfer" or "transfer" in name.lower():
                                    summary["counts"]["transfers"] += 1
                                elif "meal" in activity:
                                    summary["counts"]["meals"] += 1
                                elif action not in ["Arrival", "Hotel Check-in", "Return to Hotel", "Hotel Check-out", "Departure"]:
                                    summary["counts"]["activities"] += 1
        
        result_json["summary"] = summary
        final_result = finalize_result(result_json, session_id)
        session["result"] = final_result

        try:
            cosmos_helper.save_result(final_result)
        except Exception as e:
            print("Cosmos DB error:", e)

        # Generate single dynamic feedback using AI
        feedback_prompt = f"""
Based on this travel conversation history: {" ".join(session["history"])}
Origin: {session.get("origin", "Unknown")}

Generate ONE single enthusiastic sentence as Laura the travel assistant that:
- Acknowledges specific details from the user's input (destination, duration, travel style, etc.)
- Uses appropriate emojis
- Is conversational and excited
- Ends with "Here's your personalized itinerary 🎉"

Return just the sentence, no JSON format needed.
"""
        
        try:
            feedback_resp = client.chat.completions.create(
                model=deployment_name,
                messages=[
                    {"role": "system", "content": "You are Laura, an enthusiastic travel assistant. Generate one personalized feedback sentence."},
                    {"role": "user", "content": feedback_prompt}
                ]
            )
            feedback = [feedback_resp.choices[0].message.content.strip()]
        except:
            feedback = ["Perfect! I've got all your travel details and this is going to be an amazing trip - here's your personalized itinerary 🎉"]

        return {"done": True, "feedback": feedback, "result": final_result, "options": ["Update Plan", "End Chat"]}

    # ✅ Ask Another Question
    if user_choice in ["2", "ask another", "ask another question", "add more preferences", "preferences", "more preferences"]:
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
        return {"next_question": next_q, "options": ["Generate an itinerary", "Add more preferences"]}

    # ✅ Step 4: Acknowledge itinerary mode before persona
    if session["mode"] == "itinerary" and not session["ready"]:
        # Extract destination from the answer
        destination = answer.strip()
        return {
            "next_question": f"Got it, {destination}! Shall I go ahead and create your itinerary or you want to add more preferences to refine your trip?",
            "options": ["Generate an itinerary", "Add more preferences"]
        }

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

        # --- Track removed positions and activities for replacements ---
        removed_positions = []
        removed_activities = []
        
        # --- Apply all actions ---
        for act in actions:
            if act["action"] == "remove":
                target = act["activity"].lower()
                for day_idx, day in enumerate(recommendations):
                    for act_idx, activity in enumerate(day["activities"]):
                        if target in activity.get("name", "").lower():
                            removed_positions.append((day_idx, act_idx))
                            removed_activities.append(activity.copy())
                            day["activities"].pop(act_idx)
                            updated = True
                            feedback_msgs.append(f"Okay, I've removed {act['activity']} from your plan ✂️")
                            break
            elif act["action"] == "add":
                name = act["activity"]
                addr_hint = act.get("address", "")
                # Extract destination from user's travel history
                destination = "Unknown"
                for msg in session['history']:
                    if any(place in msg.lower() for place in ['hawaii', 'new york', 'paris', 'london', 'tokyo', 'dubai', 'singapore', 'bangkok', 'mumbai', 'delhi', 'goa', 'kerala', 'rajasthan', 'agra', 'jaipur', 'udaipur']):
                        # Extract likely destination
                        words = msg.split()
                        for i, word in enumerate(words):
                            if word.lower() in ['to', 'in', 'visiting', 'going']:
                                if i + 1 < len(words):
                                    destination = words[i + 1].title()
                                    break
                        if destination == "Unknown":
                            for word in words:
                                if word.lower() in ['hawaii', 'newyork', 'paris', 'london', 'tokyo', 'dubai', 'singapore', 'bangkok', 'mumbai', 'delhi', 'goa', 'kerala', 'rajasthan', 'agra', 'jaipur', 'udaipur']:
                                    destination = word.title()
                                    break
                        break
                
                # 🔹 Ask Azure OpenAI to find real place in destination city
                geo_prompt = f"""
You are a travel assistant with knowledge of places worldwide.
Find a real, specific, highly-rated {name} in {destination}. 
Do not create generic names - find an actual establishment that exists.
Return JSON only in this format:
{{
  "name": "Actual restaurant/place name",
  "address": "Full address in {destination}",
  "latitude": 12.34,
  "longitude": 56.78
}}
Example: If user asks for "Mexican restaurant" in Hawaii, find a real Mexican restaurant like "Frida's Mexican Beach House" with its actual address.
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
                    name = geo_json.get("name", name)  # Use real place name if found
                    address = geo_json.get("address", addr_hint or "Unknown")
                    lat = geo_json.get("latitude", 0.0)
                    lon = geo_json.get("longitude", 0.0)
                except Exception as e:
                    print("Geocoding via AI failed:", e)
                    address, lat, lon = addr_hint or "Unknown", 0.0, 0.0
                
                # Insert at removed position if available, otherwise append
                if removed_positions:
                    day_idx, act_idx = removed_positions.pop(0)
                    removed_activity = removed_activities.pop(0)
                    
                    # Get previous activity for distance calculation
                    prev_activity = recommendations[day_idx]["activities"][act_idx-1] if act_idx > 0 else None
                    
                    # Calculate distance and time from previous location
                    if prev_activity and prev_activity.get("latitude") and prev_activity.get("longitude"):
                        distance_calc_prompt = f"""
Calculate travel distance and time between:
From: {prev_activity.get('name', 'Previous location')} at {prev_activity.get('latitude')}, {prev_activity.get('longitude')}
To: {name} at {lat}, {lon}
Return JSON: {{"distance": "X km", "time": "X mins by taxi"}}
"""
                        try:
                            calc_resp = client.chat.completions.create(
                                model=deployment_name,
                                messages=[
                                    {"role": "system", "content": "You are a travel distance calculator."},
                                    {"role": "user", "content": distance_calc_prompt}
                                ],
                                response_format={"type": "json_object"}
                            )
                            calc_json = json.loads(calc_resp.choices[0].message.content)
                            travel_distance = calc_json.get("distance", "2 km")
                            travel_time = calc_json.get("time", "10 mins by taxi")
                        except:
                            travel_distance = "2 km"
                            travel_time = "10 mins by taxi"
                    else:
                        travel_distance = removed_activity.get("travel_distance_from_previous", "2 km")
                        travel_time = removed_activity.get("travel_time_from_previous", "10 mins by taxi")
                    
                    # Create new activity with exact same field order as removed one
                    new_activity = {}
                    for key in removed_activity.keys():
                        if key == "name":
                            new_activity[key] = name
                        elif key == "address":
                            new_activity[key] = address
                        elif key == "latitude":
                            new_activity[key] = lat
                        elif key == "longitude":
                            new_activity[key] = lon
                        elif key == "travel_distance_from_previous":
                            new_activity[key] = travel_distance
                        elif key == "travel_time_from_previous":
                            new_activity[key] = travel_time
                        elif key == "highlights":
                            highlight_prompt = f"Write exactly 2-3 sentences about {name} describing what makes it special and what visitors can do there. Keep it concise and similar to this style: 'Waimea Bay is famous for its breathtaking beauty and excellent swimming and surfing spots. The crystal-clear waters and scenic surroundings provide an exhilarating backdrop for sunbathing or enjoying water activities.'"
                            try:
                                highlight_resp = client.chat.completions.create(
                                    model=deployment_name,
                                    messages=[
                                        {"role": "system", "content": "You are a concise travel writer."},
                                        {"role": "user", "content": highlight_prompt}
                                    ]
                                )
                                new_activity[key] = highlight_resp.choices[0].message.content.strip()
                            except:
                                new_activity[key] = f"{name} offers unique attractions and scenic views for visitors to enjoy."
                        elif key == "carry":
                            carry_prompt = f"List 2-4 essential items to carry when visiting {name}. Keep it short like 'Swimsuit, towel, refreshments.' or 'Camera, comfortable shoes, water bottle.'"
                            try:
                                carry_resp = client.chat.completions.create(
                                    model=deployment_name,
                                    messages=[
                                        {"role": "system", "content": "You are a concise travel advisor."},
                                        {"role": "user", "content": carry_prompt}
                                    ]
                                )
                                new_activity[key] = carry_resp.choices[0].message.content.strip()
                            except:
                                new_activity[key] = "Camera, comfortable shoes, water bottle."
                        elif key == "why_recommended":
                            why_prompt = f"Write 1-2 short sentences explaining why {name} is recommended. Keep it concise like 'A must-visit for authentic Hawaiian food. It's budget-friendly and loved by locals.'"
                            try:
                                why_resp = client.chat.completions.create(
                                    model=deployment_name,
                                    messages=[
                                        {"role": "system", "content": "You are a travel recommendation expert."},
                                        {"role": "user", "content": why_prompt}
                                    ]
                                )
                                new_activity[key] = why_resp.choices[0].message.content.strip()
                            except:
                                new_activity[key] = "A popular destination loved by travelers."
                        elif key == "reviews":
                            review_prompt = f"Write 2 realistic, natural human reviews for {name}. Make them sound like real travelers wrote them - include specific details, emotions, and varied writing styles. Format as: Review 1: [text] | Review 2: [text]"
                            try:
                                review_resp = client.chat.completions.create(
                                    model=deployment_name,
                                    messages=[
                                        {"role": "system", "content": "You are a travel review generator. Write authentic, varied reviews that sound like real people."},
                                        {"role": "user", "content": review_prompt}
                                    ]
                                )
                                review_text = review_resp.choices[0].message.content.strip()
                                reviews = review_text.split(" | ")
                                if len(reviews) >= 2:
                                    new_activity[key] = {
                                        "Review 1": reviews[0].replace("Review 1: ", ""),
                                        "Review 2": reviews[1].replace("Review 2: ", "")
                                    }
                                else:
                                    new_activity[key] = {
                                        "Review 1": f"Had an amazing time at {name}! The experience exceeded my expectations.",
                                        "Review 2": "Definitely worth visiting. Great atmosphere and friendly staff."
                                    }
                            except:
                                new_activity[key] = {
                                    "Review 1": f"Had an amazing time at {name}! The experience exceeded my expectations.",
                                    "Review 2": "Definitely worth visiting. Great atmosphere and friendly staff."
                                }
                        else:
                            new_activity[key] = removed_activity[key]
                    
                    recommendations[day_idx]["activities"].insert(act_idx, new_activity)
                    feedback_msgs.append(f"Perfect! I've replaced the removed activity with {name} 🔄")
                else:
                    # For new additions, use similar structure to existing activities
                    prev_activity = recommendations[-1]["activities"][-1] if recommendations and recommendations[-1]["activities"] else None
                    
                    new_activity = {
                        "time": "2:00 PM",
                        "name": name,
                        "address": address,
                        "latitude": lat,
                        "longitude": lon,
                        "travel_distance_from_previous": "3 km",
                        "travel_time_from_previous": "15 mins by taxi",
                        "highlights": f"Explore {name} and enjoy its unique attractions and scenic views.",
                        "carry": "Camera, comfortable shoes, water bottle",
                        "why_recommended": "A popular destination loved by travelers.",
                        "rating": 4.5,
                        "reviews": {
                            "Review 1": f"Had an amazing time at {name}! The experience exceeded my expectations.",
                            "Review 2": "Definitely worth visiting. Great atmosphere and friendly staff."
                        }
                    }
                    
                    if recommendations:
                        recommendations[-1]["activities"].append(new_activity)
                        feedback_msgs.append(f"Got it! I've added {name} to your plan 🗺️")
                updated = True
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
                            feedback_msgs.append(f"Sure! I've refreshed {day_str} with new ideas 🔄")
                except Exception as e:
                    feedback_msgs.append(f"Sorry, I couldn't regenerate {day_str}: {e}")
        
        # --- Save updates or fallback ---
        if updated:
            # Regenerate summary after updates
            summary = {
                "counts": {
                    "flights": 0,
                    "transfers": 0,
                    "hotels": 0,
                    "activities": 0,
                    "meals": 0
                }
            }
            
            # Count inter-city travel (flights)
            if "inter_city_travel" in current_result:
                summary["counts"]["flights"] = len(current_result["inter_city_travel"])
            
            # Count hotels, activities, meals, transfers from cities
            if "cities" in current_result:
                for city in current_result["cities"]:
                    # Count hotels
                    if "hotel" in city:
                        summary["counts"]["hotels"] += 1
                    
                    # Count activities, meals, transfers from recommendations
                    if "recommendations" in city:
                        for day in city["recommendations"]:
                            if "activities" in day:
                                for activity in day["activities"]:
                                    action = activity.get("action", "")
                                    name = activity.get("name", "")
                                    
                                    if action == "Transfer" or "transfer" in name.lower():
                                        summary["counts"]["transfers"] += 1
                                    elif "meal" in activity:
                                        summary["counts"]["meals"] += 1
                                    elif action not in ["Arrival", "Hotel Check-in", "Return to Hotel", "Hotel Check-out", "Departure"]:
                                        summary["counts"]["activities"] += 1
            
            current_result["summary"] = summary
            session["result"] = current_result
            try:
                cosmos_helper.save_result(current_result)
            except Exception as e:
                print("Cosmos DB save error:", e)
            return {"done": True, "feedback": feedback_msgs, "result": current_result, "options": ["Update Plan", "End Chat"]}
        else:
            return {"next_question": "I couldn't understand your request. Could you rephrase what to update in your plan?"}