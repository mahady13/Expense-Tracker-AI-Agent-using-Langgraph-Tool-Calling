import streamlit as st
import requests
import uuid
import os

st.title("Expense Tracker AI Assistant v3")


API_URL=os.getenv("API_URL","http://localhost:8000")

if "thread_id" not in st.session_state:
    st.session_state["thread_id"]=str(uuid.uuid4())
if "messages" not in st.session_state:
    st.session_state["messages"]=[]

for message in st.session_state["messages"]:
    with st.chat_message(message["role"]):
        st.write(message["content"])

user_input=st.chat_input("What would you like to do sir?")

if user_input:
    st.session_state.messages.append({
        "role":"user",
        "content":user_input
    })

    response = requests.post(
        f"{API_URL}/chat",
        json={
            "thread_id": st.session_state.thread_id,
            "message": user_input,
            "user_id": "user123"
        }
    )

    print("STATUS:", response.status_code)
    print("RESPONSE:", response.text)

    if response.status_code != 200:
        st.error(f"Backend error {response.status_code}: {response.text}")
        st.stop()

    data=response.json()

    st.session_state.messages.append({
        "role":"assistant",
        "content":data["message"]
    })

    st.rerun()