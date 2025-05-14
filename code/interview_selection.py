import csv
from pathlib import Path
import streamlit as st
from database import get_transcript_by_student_and_type

MATRIX_FILE = Path(__file__).parent / "interview_matrix.csv"

# Show file load message only once
if "interview_matrix_notice_shown" not in st.session_state:
    if MATRIX_FILE.exists():
        # st.info(f"✅ Found interview matrix file: {MATRIX_FILE}")
        pass
    else:
        st.warning(f"⚠️ interview_matrix.csv not found at {MATRIX_FILE}")
    st.session_state.interview_matrix_notice_shown = True

def load_interview_context_map():
    """Reads the interview context mapping from CSV."""
    mapping = {}
    if MATRIX_FILE.exists():
        with open(MATRIX_FILE, newline="", encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile, delimiter=";")
            for row in reader:
                current = row["current_interview"].strip().lower()
                context = row["context_interview"].strip().lower()
                mapping[current] = context
    return mapping


def get_context_transcript(student_id: str, current_interview_type: str) -> str:
    """
    Given the current interview type and student ID, this returns the summary transcript
    of the associated context interview if defined in the matrix.
    """
    context_map = load_interview_context_map()
    interview_key = current_interview_type.lower()
    
    if interview_key in context_map:
        context_type = context_map[interview_key]
        transcript = get_transcript_by_student_and_type(student_id, context_type)
        return transcript
    return ""