import asyncio
from datetime import datetime, timedelta
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from llm import llm_complete
import os
import pickle

SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]


# ─── Auth ─────────────────────────────────────────────────────────────────────

def get_credentials() -> Credentials:
    creds = None
    if os.path.exists("token.pickle"):
        with open("token.pickle", "rb") as f:
            creds = pickle.load(f)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                "credentials.json", SCOPES
            )
            creds = flow.run_local_server(port=0)
        with open("token.pickle", "wb") as f:
            pickle.dump(creds, f)

    return creds


def get_calendar_service():
    return build("calendar", "v3", credentials=get_credentials())


def get_gmail_service():
    return build("gmail", "v1", credentials=get_credentials())


# ─── Calendar ─────────────────────────────────────────────────────────────────

async def add_event_to_calendar(title: str, date_description: str, time_str: str = "10:00 AM") -> dict:
    """Add an event to Google Calendar based on natural language date description."""
    try:
        # Use LLM to parse the natural language date
        messages = [{
            "role": "user",
            "content": f"Convert this date description to ISO format (YYYY-MM-DD). Today is {datetime.now().strftime('%Y-%m-%d')}. Parse: {date_description}\n\nRespond with ONLY the date in YYYY-MM-DD format, nothing else."
        }]
        
        date_str = await llm_complete(
            messages=messages,
            system="You are a date parser. Convert natural language dates to ISO format (YYYY-MM-DD). Always respond with ONLY the date.",
            mode="persona",
            max_tokens=16,
        )
        
        event_date = datetime.fromisoformat(date_str.strip())
        
        # Parse the time
        time_obj = datetime.strptime(time_str, "%I:%M %p").time()
        event_datetime = datetime.combine(event_date.date(), time_obj)
        
        service = get_calendar_service()
        loop = asyncio.get_event_loop()
        
        event = {
            "summary": title,
            "start": {
                "dateTime": event_datetime.isoformat(),
                "timeZone": "UTC",
            },
            "end": {
                "dateTime": (event_datetime + timedelta(hours=1)).isoformat(),
                "timeZone": "UTC",
            },
        }
        
        result = await loop.run_in_executor(
            None,
            lambda: service.events().insert(
                calendarId="primary",
                body=event,
            ).execute()
        )
        
        return {
            "success": True,
            "event_id": result.get("id"),
            "title": title,
            "start": event_datetime.isoformat(),
            "message": f"Added '{title}' to your calendar for {event_datetime.strftime('%B %d at %I:%M %p')}"
        }
    except Exception as e:
        print(f"[executive] calendar creation error: {e}")
        return {"success": False, "error": str(e), "message": f"couldn't add that event~ {str(e)}"}


async def plan_schedule(query: str, date_str: str = None, time_str: str = None) -> str:
    """Handle scheduling requests from the user."""
    print(f"[executive] scheduling: {query}")
    
    # Extract event title and date from query using LLM
    messages = [{
        "role": "user",
        "content": f"Extract the event title and date from this request: '{query}'. Respond in format: TITLE|DATE\nExample: Team meeting|next Tuesday"
    }]
    
    extraction = await llm_complete(
        messages=messages,
        system="You extract event details from user requests. Respond in format: TITLE|DATE (nothing else)",
        mode="persona",
        max_tokens=32,
    )
    
    try:
        parts = extraction.strip().split("|")
        event_title = parts[0].strip() if len(parts) > 0 else "Event"
        event_date = parts[1].strip() if len(parts) > 1 else date_str or "tomorrow"
        event_time = time_str or "10:00 AM"
    except:
        return "hmm, i didn't quite catch that~ try something like 'add a meeting next Tuesday at 2pm'"
    
    result = await add_event_to_calendar(event_title, event_date, event_time)
    return result["message"]


async def get_todays_events() -> list[dict]:
    try:
        service = get_calendar_service()
        now = datetime.utcnow()
        end = now + timedelta(hours=24)

        loop = asyncio.get_event_loop()
        events_result = await loop.run_in_executor(
            None,
            lambda: service.events().list(
                calendarId="primary",
                timeMin=now.isoformat() + "Z",
                timeMax=end.isoformat() + "Z",
                singleEvents=True,
                orderBy="startTime",
            ).execute()
        )

        events = []
        for e in events_result.get("items", []):
            start = e["start"].get("dateTime", e["start"].get("date"))
            events.append({
                "title": e.get("summary", "Untitled"),
                "start": start,
                "location": e.get("location", ""),
            })
        return events
    except Exception as ex:
        print(f"[executive] calendar error: {ex}")
        return []


async def get_upcoming_event() -> dict | None:
    events = await get_todays_events()
    if not events:
        return None
    now = datetime.utcnow()
    for event in events:
        try:
            start = datetime.fromisoformat(
                event["start"].replace("Z", "+00:00")
            ).replace(tzinfo=None)
            minutes_until = (start - now).total_seconds() / 60
            if 0 < minutes_until <= 15:
                return { **event, "minutes_until": int(minutes_until) }
        except Exception:
            continue
    return None


# ─── Gmail ────────────────────────────────────────────────────────────────────

async def get_unread_emails(max_results: int = 5) -> list[dict]:
    try:
        service = get_gmail_service()
        loop = asyncio.get_event_loop()

        result = await loop.run_in_executor(
            None,
            lambda: service.users().messages().list(
                userId="me",
                q="is:unread",
                maxResults=max_results,
            ).execute()
        )

        emails = []
        for msg in result.get("messages", []):
            detail = await loop.run_in_executor(
                None,
                lambda m=msg: service.users().messages().get(
                    userId="me",
                    id=m["id"],
                    format="metadata",
                    metadataHeaders=["From", "Subject"],
                ).execute()
            )
            headers = { h["name"]: h["value"] for h in detail["payload"]["headers"] }
            emails.append({
                "from": headers.get("From", ""),
                "subject": headers.get("Subject", ""),
            })
        return emails
    except Exception as e:
        print(f"[executive] gmail error: {e}")
        return []


# ─── Summarizer ───────────────────────────────────────────────────────────────

EXECUTIVE_SYSTEM = """You are a personal assistant. Handle three types of requests:
1. Calendar/event summaries: Summarize calendar or email data into 1-2 spoken sentences.
2. Scheduling requests: Help add events to the calendar.
3. Email summaries: Summarize unread emails concisely.

Be concise, natural, and helpful. No markdown."""


async def executive_respond(query: str) -> str:
    print(f"[executive] handling: {query}")

    is_scheduling = any(w in query.lower() for w in [
        "add", "schedule", "book", "set up", "create event", "add event"
    ])
    
    if is_scheduling:
        return await plan_schedule(query)
    
    is_calendar = any(w in query.lower() for w in [
        "calendar", "meeting", "schedule", "event", "today", "remind"
    ])

    if is_calendar:
        events = await get_todays_events()
        if not events:
            return "your calendar is clear today~"
        event_text = "\n".join([
            f"{e['title']} at {e['start']}" for e in events
        ])
        messages = [{
            "role": "user",
            "content": f"Summarize today's events:\n{event_text}"
        }]
    else:
        emails = await get_unread_emails()
        if not emails:
            return "no unread emails~ you're all caught up!"
        email_text = "\n".join([
            f"From: {e['from']} | Subject: {e['subject']}" for e in emails
        ])
        messages = [{
            "role": "user",
            "content": f"Summarize these unread emails:\n{email_text}"
        }]

    return await llm_complete(
        messages=messages,
        system=EXECUTIVE_SYSTEM,
        mode="persona",
        max_tokens=128,
    )


# ─── Proactive calendar watcher ───────────────────────────────────────────────

async def watch_calendar(on_alert):
    print("[executive] calendar watcher started")
    notified = set()

    while True:
        try:
            event = await get_upcoming_event()
            if event:
                key = event["title"] + event["start"]
                if key not in notified:
                    notified.add(key)
                    mins = event["minutes_until"]
                    text = f"heads up~ {event['title']} starts in {mins} minutes!"
                    await on_alert(text)
        except Exception as e:
            print(f"[executive] watcher error: {e}")
        await asyncio.sleep(300)  # check every 5 minutes