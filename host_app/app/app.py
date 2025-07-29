import sys
sys.path.insert(0, '/code')

import streamlit as st
import uuid
import asyncio
from app.services import database, advertis_client, fallback_llm

# --- Page Configuration ---
st.set_page_config(page_title="Advertis Host App", page_icon="🏠")

# --- Database Session Management ---
# Create a single session for the entire Streamlit app lifecycle
db_session = next(database.get_db())

# --- Sidebar for Session Control ---
st.sidebar.title("Session Control")

# --- Get or Create Dummy User ---
# This ensures our default user exists before any sessions are made.
dummy_user = database.get_or_create_dummy_user(db_session)

# Dropdown to select the vertical. For now, only "gaming" is available.
# In the future, the agent_registry would provide these keys.
available_verticals = ["gaming"] # In a real app: agent_registry.agent_registry.keys()
selected_vertical = st.sidebar.selectbox(
    "Select Application Vertical:",
    options=available_verticals
)

# Text area for the system prompt
system_prompt = st.sidebar.text_area(
    "Enter System Prompt:",
    value="You are a sarcastic and world-weary Game Master running a noir detective story in a cyberpunk city.",
    height=150
)

# Button to start a new chat
if st.sidebar.button("Start New Chat"):
    # Create a new session in the database
    new_session = database.create_chat_session(
        db_session=db_session,
        user_id=dummy_user.id,
        system_prompt=system_prompt,
        app_vertical=selected_vertical
    )
    # Store the new session ID and reset messages in Streamlit's state
    st.session_state.session_id = new_session.id
    st.session_state.messages = [{"role": "system", "content": system_prompt}]
    st.rerun() # Rerun the script to reflect the new state

# --- Main Chat Interface ---
st.title("🤖 Advertis Protocol Demo")
st.caption("This application simulates a customer integrating the Advertis monetization service.")

# Initialize chat history in session state if it doesn't exist
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display past messages from session state
for message in st.session_state.messages:
    if message["role"] != "system": # Don't display the system prompt
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

# Define the new async orchestrator function
async def get_final_response(session_id: uuid.UUID, prompt: str) -> str:
    """
    Orchestrates getting the final response by calling the simplified SDK wrapper.
    """
    # Get the full history from the database
    history = database.get_chat_history(db_session, session_id)

    # The implementation is now just a single, declarative line!
    return await advertis_client.get_monetized_response(
        session_id=str(session_id),
        app_vertical=selected_vertical,
        history=history,
        fallback_func=fallback_llm.get_fallback_response
    )

# Handle user input
if prompt := st.chat_input("What do you do?"):
    if "session_id" not in st.session_state:
        st.error("Please start a new chat from the sidebar first!")
    else:
        session_id = st.session_state.session_id

        # Add user message to state and display it
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # Save user message to DB
        database.save_message(db_session, session_id, "user", prompt)

        # --- THIS IS THE REFACTORED ORCHESTRATION LOGIC ---
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                # Call the async orchestrator function just once
                final_response_text = asyncio.run(get_final_response(session_id, prompt))
                st.markdown(final_response_text)

        # Add AI response to state and save to DB
        st.session_state.messages.append({"role": "assistant", "content": final_response_text})
        database.save_message(db_session, session_id, "assistant", final_response_text)