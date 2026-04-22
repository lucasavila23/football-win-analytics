import sys
import os
import importlib.util

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st

st.set_page_config(
    page_title="Football Analytics Platform",
    page_icon="⚽",
    layout="wide",
)


def _load_page(filename: str):
    path = os.path.join(os.path.dirname(__file__), "pages", filename)
    spec = importlib.util.spec_from_file_location(filename, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


PAGES = {
    "Project Overview":      "00_overview.py",
    "Architecture":          "01_architecture.py",
    "Pipeline Walkthrough":  "02_pipeline.py",
    "Tech Stack":            "03_stack.py",
    "Key Findings":          "04_findings.py",
    "Dashboard":             "05_findings2.py",
}

tab_presentation, tab_dashboard = st.tabs(["📊 Presentation", "🗺️ Dashboard"])

with tab_presentation:
    with st.sidebar:
        st.markdown("## 📊 Presentation")
        selected = st.radio("Navigate to", list(PAGES.keys()), label_visibility="collapsed")

    _load_page(PAGES[selected]).render()

with tab_dashboard:
    st.markdown("## Dashboard coming soon")
