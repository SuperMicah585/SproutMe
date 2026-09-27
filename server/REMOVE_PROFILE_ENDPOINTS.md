# Removed profile city/genre write paths

Applied on PythonAnywhere; mirror on Railway API.

## SMS (`services/sms_agent.py`)
- Removed tools: `get_profile`, `update_profile`
- No longer falls back to `user_table.city_list[0]` for “my city”
- Prompt: ask which city if they say “my city” / “near me” without naming one
- Soft `genre_list` boost in ranking still reads DB if present (Micah still has `bass`)

## HTTP (`sproutMe.py`)
- Removed `PUT /user/cities`
- Removed `PUT /user/genres`
- Kept `GET/POST /user` for login/name

## Frontend
- Removed orphaned `/dashboard` page (only consumer of those PUT routes)
