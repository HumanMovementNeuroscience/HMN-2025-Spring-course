# Enhanced system prompts
CLEANUP_TRANSCRIPT_SYSTEM_PROMPT = """    
    Please clean up the spoken text in the following transcript into a more grammatically correct form.
    Remove filler words likes um, ah, etc and make the output use correct punctuation and capitalization.

    YOU MUST MAINTAIN THE ORIGINAL MEANING AND INTENTION AND INCLUDE ALL CONTENT!
    DO NOT MAKE THINGS UP! DO NOT ATTEMPT TO ADD ADDITIONAL MEANING TO THE SPOKEN TEXT!

    The goal is to produce a version of the spoken lecture that makes sense when written down, but which 
    matches the meaning of the original text as closely as possible.
"""

OUTLINE_SYSTEM_PROMPT = """
    You are working on generating a comprehensive outline of the content of a transcribed lecture the title of the lecture is: 

    {LECTURE_TITLE}

    You are being given the lecture transcript piece by piece and generating a running outline based on the present chunk 
    along with the outline from previous iterations.

    You are currently on chunk number {CHUNK_NUMBER} of {TOTAL_CHUNK_COUNT}

    The outline from the previous iterations is: 

    ___

    {PREVIOUS_OUTLINE}

    ___

    The current chunk of text you are integrating into the outline is: 

    ___

    {CURRENT_CHUNK}

    ___

    Your response should be in the form of a markdown formatted outline with a #H1 title, ##H2 headings for the major topics, 
    ###H3 headings for the minor topics, and bulleted outline sentences for the content itself.

    Focus on the CONTENT of the lecture, not information that is incidental to the record (i.e. Greeting the students, 
    acknowledging forgotten equipment, etc).

    De-emphasize course related admin stuff about assignments and due dates, and focus on the scientific and philosophical 
    core content of the lecture.

    Focus on declarative statements rather than vague referential ones. Here are some examples of what I mean, 
    based on some bad examples from a less helpful, insightful, and clever AI than you:

    ___
    ## Introduction to the Lecture
       - Overview of the course structure and expectations.  <- this is too vague, what is the course structure and what are the expectations? Be specific!
       - Emphasis on student engagement and personal interests in the subject matter. <- this is too vague, say WHAT was emphasized! Be specific!

    ## The Role of AI in Education
       - AI's ability to adapt to student interests compared to traditional curricula. <- this is too vague, what was said about AI's ability to adapt? Be specific!
       - Encouragement for students to explore their unique paths in human perceptual motor neuroscience. <- this is too vague, what was said about exploring unique paths? Be specific!

    ## Empirical Data Collection
    - Acknowledgment of the limitations of understanding past actions and the reliance on empirical data for insights. <- THIS IS TOO VAGUE! What are the limitations? What were past actions? what is the empirical data? Be specific!
    ___

    Instead, include the actual CONTENT of what was said on those topics! A person reading this outline should walk away 
    with the same main points as someone who watched the lecture.

    Do not respond with ANY OTHER TEXT besides the running outline, which integrates the current text chunk with the outline 
    from previous iterations.
"""

THEME_SYNTHESIS_SYSTEM_PROMPT = """
    You will be provided with the outlines from a series of lectures from a professor teaching a class on human perceptual motor neuroscience.

    Your job is to use the provided outlines to generate a comprehensive outline on one of the major themes running through 
    the lectures. In this run, your job is to generate a comprehensive outline on the following theme:

    Theme: "{theme}"

    Here is a list of the other themes that you will be generating an outline for at a DIFFERENT TIME: {all_themes}

    It is ok (and often unavoidable!) for there to be some overlap between the outlines you generate for the different themes,
    but you should try to make each outline as distinct as possible so be sure to focus on the theme you are given.

    The outline should be based on the provided lecture outlines and should be structured in a way that is easy to understand 
    and follow while incorporating as much of the content from the original outlines as possible.

    The outline should be detailed and cover all the major points and subpoints related to the theme.

    The title of the outline (with an #H1 header) should be: `HMN25: {theme}` and should begin with a high-level summary 
    of the theme in abstract form with a few bulleted highlights.

    Following that, you should provide a comprehensive and detailed outline of this theme based ENTIRELY on the material 
    provided in the lecture outlines.

    DO NOT MAKE THINGS UP! USE THE ORIGINAL TEXT AS MUCH AS POSSIBLE AND DO NOT INVENT CONTENT OR INJECT MEANING THAT 
    WAS NOT IN THE ORIGINAL TEXT. DO NOT MAKE THINGS UP!

    Here are the outlines from the lectures in this course:

    >>>>>LECTURE_OUTLINES_BEGIN<<<<<

    {lecture_outlines}

    >>>>>LECTURE_OUTLINES_END<<<<<

    REMEMBER! Your task is to generate a comprehensive outline on the theme: {theme}
"""
