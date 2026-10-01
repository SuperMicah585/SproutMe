from supabase import create_client
from twilio.rest import Client as TwilioClient
import json
import asyncio
import os
from datetime import datetime, timezone

from services.public_api import clean_event_url, sanitize_event
class DatabaseHandler:
    """
    A class to handle database operations with Supabase for the Events table.
    """
    
    def __init__(self, supabase_url, supabase_key, table_name):
        """
        Initialize the DatabaseHandler with Supabase credentials and table information.
        
        Args:
            supabase_url (str): The URL for the Supabase instance
            supabase_key (str): The API key for Supabase
            table_name (str): The name of the table to interact with
        """
        self.supabase_url = supabase_url
        self.supabase_key = supabase_key
        self.table_name = table_name
        self.client = create_client(self.supabase_url, self.supabase_key)
        self.account_sid = os.environ.get("TWILIO_ACCOUNT_SID") or ""
        self.auth_token = os.environ.get("TWILIO_AUTH_TOKEN") or ""
        self.twilio_client = TwilioClient(self.account_sid, self.auth_token) if self.account_sid and self.auth_token else None
        self.twilio_phone_number = os.environ.get("TWILIO_FROM_NUMBER") or ""


    
    def clear_table(self):
        """
        Delete all rows from the specified table.
        
        Returns:
            dict: Response from the Supabase API
        """
        try:
            response = self.client.table(self.table_name).delete().neq("id", 10000000).execute()
            return {
                "success": True,
                "message": f"All rows deleted from {self.table_name}",
                "response": response
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Error clearing table: {str(e)}"
            }

    def get_name_by_phone_number(self, phone_number):
        # Query to retrieve the name based on phone number
        result = self.client.table(self.table_name).select('name').eq('phone_number', phone_number).execute()
        if result.data:
            return result.data[0]['name']
        return None


    def update_user_name(self, phone_number, name):
        if not phone_number or not name:
            return {
                "success": False,
                "message": "phone_number and name are required"
            }, 400

        try:
            # Update the user's name in the database
            response = self.client.table(self.table_name).update({"name": name}).eq('phone_number', phone_number).execute()
            print(response)
            if response.data:
                return {
                    "success": True,
                    "message": "Name updated successfully"
                }
            else:
                return {
                    "success": False,
                    "message": "User not found"
                }, 404

        except Exception as e:
            return {
                "success": False,
                "message": f"Error updating name: {str(e)}"
            }, 500
    

    def get_genres(self, genre_list):
        """
        Get all rows where the genre column contains any of the genres in the provided list.
        
        Args:
            genre_list (list): List of genre strings to match against.
            
        Returns:
            dict: Response from the Supabase API
        """
        try:
            # Construct the query using .or() to match any of the genres in the list
            genre_conditions = ",".join([f"genre.ilike.%{genre}%" for genre in genre_list])
            print(genre_conditions)
            # Query to get all rows where the genre contains any of the genres in the list
            response = self.client.table('Events_table').select('*').or_(genre_conditions).execute()
            #print(response.data)
            pretty_data = json.dumps(response.data, indent=4)
            print(pretty_data)
   
            return {
                "success": True,
                "message": f"Rows with specified genres retrieved successfully",
                "response": response
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Error fetching rows: {str(e)}"
            }

    def get_event_by_id(self, event_id):
        """
        Get a row from the Events_table based on the provided event ID.
        
        Args:
            event_id (int): The ID of the event to retrieve.
            
        Returns:
            dict: The event row data or error message.
        """
        try:
            # Query the database where the event's ID matches the input
            response = self.client.table('Events_table').select('*').eq('id', event_id).execute()
   
            # Check if data is returned
            if response.data:
                return {
                    "success": True,
                    "message": "Event retrieved successfully",
                    "data": response.data[0]  # We return the first event since we expect a single result
                }
            else:
                return {
                    "success": False,
                    "message": f"No event found with ID {event_id}",
                    "data": None
                }
        except Exception as e:
            return {
                "success": False,
                "message": f"Error fetching event: {str(e)}",
                "data": None
            }

    def get_all_users(self):

        try:
            # Query to get all rows from the user_table
            response = self.client.table('user_table').select('*').execute()
            
            return {
                "success": True,
                "message": "All users retrieved successfully",
                "data": response.data
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Error fetching users: {str(e)}",
                "data": None
            }

    def get_all_phone_numbers(self):
        try:
            # Fetch all users
            users_response = self.get_all_users()
            
            # Check if the request was successful
            if not users_response["success"]:
                return {
                    "success": False,
                    "message": f"Error fetching users: {users_response['message']}",
                    "data": None
                }
            
            # Extract users from the response
            users = users_response["data"]
            
            # Extract phone numbers from each user
            phone_numbers = [user['phone_number'] for user in users]
            
            return {
                "success": True,
                "message": "Phone numbers fetched successfully",
                "data": phone_numbers
            }
        
        except Exception as e:
            return {
                "success": False,
                "message": f"Error fetching phone numbers: {str(e)}",
                "data": None
            }



    def match_events_for_user(self, phone_number):
        try:
            # First, get all users
            users_response = self.get_all_users()

            if not users_response["success"]:
                return {
                    "success": False,
                    "message": f"Error fetching users: {users_response['message']}",
                    "data": None
                }

            users = users_response["data"]
            user = next((u for u in users if u['phone_number'] == phone_number), None)

            if not user:
                return {
                    "success": False,
                    "message": "User not found",
                    "data": None
                }

            genre_list = user['genre_list']
            city_list = user['city_list']

            # Get all events
            events_response = self.client.table('Events_table').select('*').execute()
            events = events_response.data

            # List to store all matching events
            matching_events = []

            # Loop through all events to find matches
            for event in events:
                # Find all genres that match
                matching_genres = [genre for genre in genre_list if genre.lower() in event['genre'].lower()]

                # Find all cities that match
                matching_cities = [city for city in city_list if city.lower() in event['city'].lower()]

                # If there are matches in both genre and city, add the event to the list
                if matching_genres and matching_cities:
                    matching_events.append(event)

            return {
                "success": True,
                "message": "User-event matching completed successfully",
                "data": matching_events
            }

        except Exception as e:
            return {
                "success": False,
                "message": f"Error matching events for user: {str(e)}",
                "data": None
            }

    def _fetch_all_rows(self, table_name=None, columns="*"):
        table_name = table_name or self.table_name
        rows = []
        start = 0
        page = 1000
        while True:
            response = (
                self.client.table(table_name)
                .select(columns)
                .range(start, start + page - 1)
                .execute()
            )
            chunk = response.data or []
            rows.extend(chunk)
            if len(chunk) < page:
                break
            start += page
        return rows

    def get_all_events(self, columns="*"):
        """
        Get all events from the Events_table.
        
        Returns:
            dict: Response containing all events
        """
        try:
            response_data = self._fetch_all_rows("Events_table", columns=columns)
            
            return {
                "success": True,
                "message": "All events retrieved successfully",
                "data": [sanitize_event(event) for event in response_data]
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Error fetching events: {str(e)}",
                "data": None
            }

    def get_events_with_favorite_status(self, phone_number):
        """
        Get all events from the Events_table and mark which ones are favorites for the user.
        
        Args:
            phone_number (str): The phone number of the user
            
        Returns:
            dict: Response containing all events with is_favorite flag
        """
        try:
            # Get all events
            events_data = self._fetch_all_rows("Events_table")
            
            # Get the user's favorite events
            favorites_response = self.client.table('favorite_events').select('*').eq('phone_number', phone_number).execute()
            
            if not events_data:
                return {
                    "success": True,
                    "message": "No events found",
                    "data": []
                }
                
            # Create a list of favorite event identifiers for easy lookup
            favorite_events = []
            for fav in favorites_response.data:
                favorite_events.append({
                    'event_name': fav.get('event_name'),
                    'venue': fav.get('venue'),
                    'date': fav.get('date'),
                    'organizer': fav.get('organizer'),
                    'raw_date': fav.get('raw_date', ''),
                    'ticket_info': fav.get('ticket_info', ''),
                    'genre': fav.get('genre', ''),
                    'event_url': fav.get('event_url', '')
                })
                
            # Mark events as favorites if they appear in the user's favorites
            events_with_status = []
            for event in events_data:
                is_favorite = False
                
                # Ensure event has all properties we need for comparison
                if 'raw_date' not in event and event.get('date'):
                    event['raw_date'] = event.get('date')
                    
                # Check if this event is in the user's favorites
                for fav in favorite_events:
                    # Primary matching criteria - event name, venue, date, and organizer
                    if (event.get('event_name') == fav.get('event_name') and
                        event.get('venue') == fav.get('venue') and
                        event.get('date') == fav.get('date') and
                        event.get('organizer') == fav.get('organizer')):
                        is_favorite = True
                        break
                    
                    # Secondary matching with raw_date when primary fails
                    if not is_favorite and fav.get('raw_date') and event.get('raw_date'):
                        if (event.get('event_name') == fav.get('event_name') and
                            event.get('venue') == fav.get('venue') and
                            event.get('raw_date') == fav.get('raw_date') and
                            event.get('organizer') == fav.get('organizer')):
                            is_favorite = True
                            break
                    
                    # Additional matching with extended fields if available 
                    if not is_favorite and event.get('ticket_info') and fav.get('ticket_info'):
                        if (event.get('event_name') == fav.get('event_name') and
                            event.get('venue') == fav.get('venue') and
                            event.get('ticket_info') == fav.get('ticket_info')):
                            is_favorite = True
                            break
                    
                # Add is_favorite flag to the event
                event_with_status = sanitize_event(event.copy())
                event_with_status['is_favorite'] = is_favorite
                events_with_status.append(event_with_status)
                
            return {
                "success": True,
                "message": "All events retrieved with favorite status",
                "data": events_with_status
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Error fetching events with favorite status: {str(e)}",
                "data": None
            }

    def create_user(self, phone_number, send_welcome=True):
        """
        Create a new user in the user_table with empty genre_list and city_list arrays
        if the phone number doesn't already exist.
        """
        try:
            # First check if user already exists
            check_response = self.client.table('user_table').select('*').eq('phone_number', phone_number).execute()
            
            is_new_user = False
            if check_response.data:
                user_data = check_response.data[0]
                result = {
                    "success": True,
                    "message": f"User with phone number {phone_number} already exists",
                    "data": user_data
                }
            else:
                # Create new user with empty arrays
                new_user = {
                    "phone_number": phone_number,
                    "genre_list": [],
                    "city_list": []
                }
                
                response = self.client.table('user_table').insert(new_user).execute()
                is_new_user = True
                result = {
                    "success": True,
                    "message": f"User with phone number {phone_number} created successfully",
                    "data": response.data[0] if response.data else None
                }
                
                if send_welcome:
                    result["sms"] = self.send_welcome_sms(phone_number, is_new_user)
                
            return result
        except Exception as e:
            return {
                "success": False,
                "message": f"Error creating user: {str(e)}",
                "data": None
            }

    def send_welcome_sms(self, phone_number, is_new_user=False):

        """
        Send a welcome SMS to a user with helpful commands.
        Only sends the message if the user was newly created.
        
        Args:
            phone_number (str): The phone number to send the SMS to
            is_new_user (bool): Flag indicating if this is a newly created user
            
        Returns:
            dict: Response indicating success or failure of the SMS send operation
        """
        try:
            # Only send welcome message to newly created users
            if not is_new_user:
                return {
                    "success": True,
                    "message": f"No SMS sent - user already existed",
                    "data": None
                }
                
            # Compose welcome message with helpful commands
            welcome_message = (
                "Welcome to our service! Every Sunday, you'll receive an SMS with a link to your upcoming events. Here's how you can manage your experience:\n\n"
                "📅 Text EVENTS to get your events link.\n"
                "🚫 Text REMOVE to unsubscribe from the service.\n\n"
                "Reply anytime to get started!"
            )
            
            # Send the message using Twilio
            message = self.twilio_client.messages.create(
                body=welcome_message,
                from_=self.twilio_phone_number,
                to=phone_number
            )
            
            return {
                "success": True,
                "message": f"Welcome SMS sent successfully to {phone_number}",
                "data": {
                    "twilio_sid": message.sid,
                    "status": message.status
                }
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Error sending welcome SMS: {str(e)}",
                "data": None
            }

    def get_user(self, phone_number):
        """
        Retrieve a user from the user_table based on the given phone number.

        Args:
            phone_number (str): The phone number of the user to retrieve.

        Returns:
            dict: Response indicating success or failure along with user data if found.
        """
        try:
            # Query the user_table for the given phone number
            response = self.client.table('user_table').select('*').eq('phone_number', phone_number).execute()
            print(response)
            if response.data:
                return {
                    "success": True,
                    "message": f"User with phone number {phone_number} found",
                    "data": response.data[0]  # Return the first user found
                }
            else:
                return {
                    "success": False,
                    "message": f"No user found with phone number {phone_number}",
                    "data": None
                }

        except Exception as e:
            return {
                "success": False,
                "message": f"Error retrieving user: {str(e)}",
                "data": None
            }


    def check_user_name(self, phone_number):
        """
        Retrieve a user from the user_table based on the given phone number,
        and check if the name column is null or not.

        Args:
            phone_number (str): The phone number of the user to retrieve.

        Returns:
            dict: Response indicating success or failure along with user data if found.
        """
        try:
            # Query the user_table for the given phone number
            response = self.client.table('user_table').select('*').eq('phone_number', phone_number).execute()
            
            if response.data:
                user = response.data[0]  # Assume only one user per phone number
                if user.get("name"):
                    return {
                        "success": True,
                        "status": "user_with_name",
                        "message": f"User with phone number {phone_number} found and name is not null",
                        "data": user
                    }
                else:
                    return {
                        "success": True,
                        "status": "user_without_name",
                        "message": f"User with phone number {phone_number} found but name is null",
                        "data": user
                    }
            else:
                return {
                    "success": False,
                    "status": "user_not_found",
                    "message": f"No user found with phone number {phone_number}",
                    "data": None
                }
        
        except Exception as e:
            return {
                "success": False,
                "status": "error",
                "message": f"Error retrieving user: {str(e)}",
                "data": None
            }

    def update_user_genres(self, phone_number, genre_list):
        """
        Update the genre_list array for a user with the provided phone number.
        
        Args:
            phone_number (str): The phone number of the user to update
            genre_list (list): List of genres to set for the user
            
        Returns:
            dict: Response indicating success or failure
        """
        try:
            # Check if user exists
            check_response = self.client.table('user_table').select('*').eq('phone_number', phone_number).execute()
            
            if not check_response.data:
                return {
                    "success": False,
                    "message": f"No user found with phone number {phone_number}",
                    "data": None
                }
            
            # Update the user's genre_list
            response = self.client.table('user_table').update(
                {"genre_list": genre_list}
            ).eq('phone_number', phone_number).execute()
            
            return {
                "success": True,
                "message": f"Genre list updated for user with phone number {phone_number}",
                "data": response.data[0] if response.data else None
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Error updating genre list: {str(e)}",
                "data": None
            }

    def update_user_cities(self, phone_number, city_list):
        """
        Update the city_list array for a user with the provided phone number.
        
        Args:
            phone_number (str): The phone number of the user to update
            city_list (list): List of cities to set for the user
            
        Returns:
            dict: Response indicating success or failure
        """
        try:
            # Check if user exists
            check_response = self.client.table('user_table').select('*').eq('phone_number', phone_number).execute()
            
            if not check_response.data:
                return {
                    "success": False,
                    "message": f"No user found with phone number {phone_number}",
                    "data": None
                }
            
            # Update the user's city_list
            response = self.client.table('user_table').update(
                {"city_list": city_list}
            ).eq('phone_number', phone_number).execute()
            
            return {
                "success": True,
                "message": f"City list updated for user with phone number {phone_number}",
                "data": response.data[0] if response.data else None
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Error updating city list: {str(e)}",
                "data": None
            }

    def delete_user(self, phone_number):
        """
        Delete a user based on the provided phone number.
        
        Args:
            phone_number (str): The phone number of the user to delete
            
        Returns:
            dict: Response indicating success or failure
        """
        try:
            # Check if user exists
            check_response = self.client.table('user_table').select('*').eq('phone_number', phone_number).execute()
            
            if not check_response.data:
                return {
                    "success": False,
                    "message": f"No user found with phone number {phone_number}",
                    "data": None
                }
            
            # Delete the user
            response = self.client.table('user_table').delete().eq('phone_number', phone_number).execute()
            
            return {
                "success": True,
                "message": f"User with phone number {phone_number} deleted successfully",
                "data": response.data[0] if response.data else None
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Error deleting user: {str(e)}",
                "data": None
            }

    def star_event(self, phone_number, event):
        """
        Add an event to a user's favorites in the favorite_events table.
        
        Args:
            phone_number (str): The phone number of the user
            event (dict): The event data to add to favorites
            
        Returns:
            dict: Response indicating success or failure
        """
        try:
            # Print the incoming event for debugging
            print(f"DEBUG - Event received: {event}")
            
            # Create a record in the favorite_events table with only the fields that exist in the table
            favorite_record = {
                "phone_number": phone_number,
                "event_name": event.get("event_name"),
                "venue": event.get("venue"),
                "date": event.get("date"),
                "organizer": event.get("organizer", ""),  # Default to empty string if not provided
                "raw_date": event.get("raw_date", ""),  # Add raw_date field with default empty string
                "ticket_info": event.get("ticket_info", ""),  # Add ticket_info field
                "genre": event.get("genre", ""),  # Add genre field
                "event_url": clean_event_url(event.get("event_url", "")),
            }
            
            print(f"DEBUG - Record to insert: {favorite_record}")
            
            # Insert the record directly without checking (we'll handle duplicates on the database side)
            response = self.client.table('favorite_events').insert(favorite_record).execute()
            
            return {
                "success": True,
                "message": "Event added to favorites successfully",
                "data": response.data[0] if response.data else None
            }
        except Exception as e:
            print(f"ERROR - Failed to star event: {str(e)}")
            return {
                "success": False,
                "message": f"Error adding event to favorites: {str(e)}",
                "data": None
            }
    
    def unstar_event(self, phone_number, event_metadata):
        """
        Remove an event from a user's favorites in the favorite_events table.
        
        Args:
            phone_number (str): The phone number of the user
            event_metadata (dict): Metadata to identify the event
            
        Returns:
            dict: Response indicating success or failure
        """
        try:
            # Print debugging info
            print(f"DEBUG - Unstar request: phone_number={phone_number}, event_metadata={event_metadata}")
            
            # Find and delete the record in the favorite_events table
            # Start with the basic query with required fields
            response = self.client.table('favorite_events').delete() \
                .eq('phone_number', phone_number) \
                .eq('event_name', event_metadata.get("event_name")) \
                .eq('venue', event_metadata.get("venue")) \
                .eq('date', event_metadata.get("date")) \
                .eq('organizer', event_metadata.get("organizer", ""))
                
            # Add additional filters for optional fields if they exist in event_metadata
            if event_metadata.get("raw_date"):
                response = response.eq('raw_date', event_metadata.get("raw_date"))
                
            # Add ticket_info filter if provided
            if event_metadata.get("ticket_info"):
                response = response.eq('ticket_info', event_metadata.get("ticket_info"))
                
            # Add genre filter if provided
            if event_metadata.get("genre"):
                response = response.eq('genre', event_metadata.get("genre"))
                
            # Add event_url filter if provided
            if event_metadata.get("event_url"):
                response = response.eq('event_url', event_metadata.get("event_url"))
                
            # Execute the query
            response = response.execute()
            
            print(f"DEBUG - Unstar response: {response.data}")
            
            if response.data:
                return {
                    "success": True,
                    "message": "Event removed from favorites successfully",
                    "data": response.data[0]
                }
            else:
                return {
                    "success": False,
                    "message": "Event not found in favorites",
                    "data": None
                }
        except Exception as e:
            print(f"ERROR - Failed to unstar event: {str(e)}")
            return {
                "success": False,
                "message": f"Error removing event from favorites: {str(e)}",
                "data": None
            }
            
    def get_favorite_events(self, phone_number):
        """
        Get all favorite events for a user.
        
        Args:
            phone_number (str): The phone number of the user
            
        Returns:
            dict: Response containing the user's favorite events
        """
        try:
            # Query to get all favorite events for this user
            response = self.client.table('favorite_events').select('*').eq('phone_number', phone_number).execute()
            
            return {
                "success": True,
                "message": "Favorite events retrieved successfully",
                "data": [sanitize_event(event) for event in (response.data or [])]
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Error fetching favorite events: {str(e)}",
                "data": None
            }

    def get_user_submitted_events(self):
        """
        Get events added by users. These live outside Events_table so the daily scrape cannot wipe them.
        """
        try:
            response = self.client.table('user_submitted_events').select('*').order('created_at', desc=True).execute()
            return {
                "success": True,
                "message": "User submitted events retrieved successfully",
                "data": [sanitize_event(event) for event in (response.data or [])]
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Error fetching user submitted events: {str(e)}",
                "data": []
            }

    def add_user_submitted_event(self, event):
        """
        Insert a user-submitted event into user_submitted_events.
        """
        try:
            payload = dict(event or {})
            if payload.get("event_url"):
                payload["event_url"] = clean_event_url(payload["event_url"])
            if payload.get("event_link_url"):
                payload["event_link_url"] = clean_event_url(payload["event_link_url"])
            response = self.client.table('user_submitted_events').insert(payload).execute()
            return {
                "success": True,
                "message": "Event added successfully",
                "data": sanitize_event(response.data[0]) if response.data else payload
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Error adding user submitted event: {str(e)}",
                "data": None
            }

    def get_sms_conversation(self, phone_number):
        try:
            response = self.client.table("sms_conversations").select("*").eq("phone_number", phone_number).execute()
            if response.data:
                return {
                    "success": True,
                    "message": "Conversation found",
                    "data": response.data[0],
                }
            return {
                "success": True,
                "message": "No conversation yet",
                "data": {
                    "phone_number": phone_number,
                    "messages": [],
                    "started_at": None,
                    "global_rules": "",
                    "rules_updated_at": None,
                },
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Error fetching conversation: {str(e)}",
                "data": None,
            }

    def list_sms_conversations(self):
        try:
            rows = self._fetch_all_rows("sms_conversations", columns="*")
            return {
                "success": True,
                "message": "Conversations listed",
                "data": rows or [],
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Error listing conversations: {str(e)}",
                "data": [],
            }

    def save_sms_conversation(
        self,
        phone_number,
        messages,
        started_at=None,
        global_rules=None,
        update_rules=False,
    ):
        try:
            now = datetime.now(timezone.utc).isoformat()
            existing = {}
            try:
                prior = (
                    self.client.table("sms_conversations")
                    .select("global_rules,rules_updated_at,started_at")
                    .eq("phone_number", phone_number)
                    .limit(1)
                    .execute()
                )
                if prior.data:
                    existing = prior.data[0] or {}
            except Exception:
                existing = {}

            payload = {
                "phone_number": phone_number,
                "messages": messages or [],
                "started_at": started_at or existing.get("started_at") or now,
                "updated_at": now,
            }
            if hasattr(payload["started_at"], "isoformat"):
                payload["started_at"] = payload["started_at"].isoformat()

            if update_rules:
                payload["global_rules"] = global_rules or ""
                payload["rules_updated_at"] = now
            else:
                payload["global_rules"] = existing.get("global_rules") or ""
                if existing.get("rules_updated_at"):
                    payload["rules_updated_at"] = existing["rules_updated_at"]

            response = self.client.table("sms_conversations").upsert(payload).execute()
            return {
                "success": True,
                "message": "Conversation saved",
                "data": response.data[0] if response.data else payload,
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Error saving conversation: {str(e)}",
                "data": None,
            }

    def delete_sms_conversation(self, phone_number):
        try:
            self.client.table("sms_conversations").delete().eq("phone_number", phone_number).execute()
            return {
                "success": True,
                "message": "Conversation deleted",
                "data": None,
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Error deleting conversation: {str(e)}",
                "data": None,
            }

'''
if __name__ == "__main__":
    db_handler = DatabaseHandler(
            supabase_url=os.environ.get("SUPABASE_URL") or "",
            supabase_key=os.environ.get("SUPABASE_KEY") or "",
            table_name="Events_table"
        )
    db_handler.match_users_with_events()
'''
