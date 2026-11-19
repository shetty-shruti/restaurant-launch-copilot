"""Streamlit front end. Run with: make ui"""

import httpx
import streamlit as st

API_URL = "http://localhost:8000"

st.title("Restaurant Launch Copilot")
question = st.text_input("Ask about opening or running a restaurant in New York City")
if st.button("Ask") and question:
    resp = httpx.post(f"{API_URL}/ask", json={"question": question}, timeout=120)
    if resp.status_code == 200:
        data = resp.json()
        st.write(data["answer"])
        for c in data["citations"]:
            label = f"{c['source']} {c['section']} ({c['jurisdiction']})"
            st.markdown(f"[{c['id']}] [{label}]({c['url']})")
    else:
        st.error(f"{resp.status_code}: {resp.text}")
