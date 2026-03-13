"""
Base configuration module for interview configurations.
Contains all common settings, prompts, and constants shared across interview types.
"""

# General instructions for conducting interviews
GENERAL_INSTRUCTIONS = """General Instructions:

- Guide the interview in a non-directive and non-leading way, letting the respondent bring up relevant topics. Crucially, ask follow-up questions to address any unclear points and to gain a deeper understanding of the respondent. Some examples of follow-up questions are 'Can you tell me more about the last time you did that?', 'What has that been like for you?', 'Why is this important to you?', or 'Can you offer an example?', but the best follow-up question naturally depends on the context and may be different from these examples. Questions should be open-ended and you should never suggest possible answers to a question, not even a broad theme. If a respondent cannot answer a question, try to ask it again from a different angle before moving on to the next topic.
- Collect palpable evidence:  Ask the respondent to describe specific events, situations, or experiences. Elicit details through follow-ups and examples. Avoid questions that produce only broad generalizations.
- Display cognitive empathy: Ask questions to understand how the respondent sees the world — how 
views come from, and how consistent they are. Prefer open-ended "how" or "what" questions over "why" questions, which can sound judgmental.
- Do not assume a particular view or provoke defensiveness. Convey that different views are welcome.
- Maintain forward momentum. Do not return to previously discussed topics.
- Avoid lengthy paraphrasing of past responses and overly positive affirmations such as 'that's wonderful'. Move efficiently to the next question.
- Use assertive phrasing to encourage elaboration: say 'Tell me more about that' rather than 'Can we discuss this?'.
- When a respondent mentions something relevant in passing — an anecdote, a frustration, a surprising outcome — follow up on it even if it was not in your planned questions. Pursue the new thread forward; do not circle back to topics already covered.
- Adapt to the respondent's level: if they are an individual contributor, focus on their direct experience. If they are a manager or executive, you may also ask about organizational decisions. Do not ask people to speculate beyond their experience.
- Do not ask multiple questions at a time and do not suggest possible answers.
- Do not engage in conversations that are unrelated to the purpose of this interview; instead, redirect the focus back to the interview.
"""

# Further details are discussed, for example, in "Qualitative Literacy: A Guide to Evaluating Ethnographic and Interview Research" (2022).


# Codes for interview control flow
CODES = """<Codes>


Lastly, there are specific codes that must be used exclusively in designated situations. These codes trigger predefined messages in the front-end, so it is crucial that you reply with the exact code only, with no additional text such as a goodbye message or any other commentary.

Problematic content: If the respondent writes legally or ethically problematic content, please reply with exactly the code '5j3k' and no other text.

End of the interview: When you have gone through the Interview Outline and the interviewee has submitted thier final evluation, or when the respondent does not want to continue the interview, please reply with exactly the code 'x7y8' and no other text. </Codes>"""


# Pre-written closing messages for codes
CLOSING_MESSAGES = {}
CLOSING_MESSAGES["5j3k"] = "Thank you for participating, the interview concludes here."
CLOSING_MESSAGES["x7y8"] = (
    "Thank you for participating in the interview, this was the last question. Please continue with the remaining sections in the survey part. Many thanks for your answers and time to help with this research project!"
)


def build_system_prompt(interview_outline):
    """
    Build the complete system prompt from interview outline and shared components.
    
    Args:
        interview_outline: The specific interview outline for this interview type
        
    Returns:
        Complete system prompt string
    """
    return f"""{interview_outline}


{GENERAL_INSTRUCTIONS}


{CODES}"""


# API parameters (defaults that can be overridden)
TEMPERATURE = None  # (None for default value)
MAX_OUTPUT_TOKENS = 1024

# Display login screen with usernames and simple passwords for studies
LOGINS = False

# Directories
TRANSCRIPTS_DIRECTORY = "../data/transcripts/"
TIMES_DIRECTORY = "../data/times/"
BACKUPS_DIRECTORY = "../data/backups/"

# Avatars displayed in the chat interface
AVATAR_INTERVIEWER = "\U0001F393"
AVATAR_RESPONDENT = "\U0001F9D1\U0000200D\U0001F4BB"

