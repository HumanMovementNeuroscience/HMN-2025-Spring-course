import asyncio
import logging
import os
from pathlib import Path

import yaml
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.DEBUG)
# Suppress some external loggers that are too verbose for our context/taste
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)
LECTURE_TRANSCRIPTS_DIR = "lecture_transcripts"
LECTURE_DATA_FILE = "lecture_transcripts/lecture_outlines_prev-utf8.md"
if not Path(LECTURE_DATA_FILE).exists():
    logging.error(f"File not found: {LECTURE_DATA_FILE}, run `ai_outline_lecture_data.py` first")
    exit()

API_KEY = os.getenv('OPENAI_API_KEY')
DEFAULT_LLM = "gpt-4o"
BASE_AI_URL = None
# API_KEY = os.getenv('DEEPSEEK_API_KEY')
# DEFAULT_LLM = "deepseek-reasoner"
# BASE_AI_URL = "https://https://api.deepseek.com"
if not API_KEY:
    raise ValueError("API key not found. Please set the *_API_KEY environment variable.")

AI_CLIENT = AsyncOpenAI(api_key=API_KEY,
                        base_url=BASE_AI_URL)


async def make_openai_text_generation_ai_request(client: AsyncOpenAI,
                                                 system_prompt: str,
                                                 llm_model: str):
    messages = [{"role": "system", "content": system_prompt}]
    response = await client.beta.chat.completions.parse(
        model=llm_model,
        messages=messages,
        temperature=0.0,
    )
    output = response.choices[0].message.content
    return output


def load_lecture_data():
    logger.debug(f"Loading lecture data from {LECTURE_DATA_FILE}")
    try:
        with open(LECTURE_DATA_FILE, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        logger.error(f"File not found: {LECTURE_DATA_FILE}")
        return None
    except yaml.YAMLError as e:
        logger.error(f"Error parsing YAML file: {e}")
        return None


async def ai_extract_lecture_themes(lecture_outlines: str, theme:str, all_themes:str) -> str:

    IDENTITY_PROMPT = "You will be provided with the outlines from a series of lectures from a professor teaching a class on human perceptual motor neuroscience."
    MAIN_TASK_PROMPT = """
    Your job is to  use the provided outlines generate a comprehensive outline on one of the major themes running through the lectures. In this run, your job is to generate a comprehensive outline on the following theme- 
    
    Theme: "{theme}".
    
    Here is a list of the other themes that you will be generating an outline for at a DIFFERENT TIME: {all_themes}
    
    
    It is ok (and often unavoidable!) for there to be some overlap between the outlines you generate for the different themes , but you should try to make each outline as distinct as possible so be sure to focus on the theme you are given.
         
    The outline should be based on the provided lecture outlines and should be structured in a way that is easy to understand and follow while incorporating as much of the content from the original outlines as possible.
    The outline should be detailed and cover all the major points and subpoints related to the theme.
     
     The title of the outline (with an #H1 header) should be: `HMN25: {theme}` and should begin with a high-level summary of the theme in abstract form with a few bulleted highlights.
     Following that, you should provide a comprehensive and detailed outline of these theme based ENTIRELY on the material provided in the lecture outlines.
    DO NOT MAKE THINGS UP! USE THE ORIGINAL TEXT AS MUCH AS POSSIBLE AND DO NOT INVENT CONTENT OR INJECT MEANING THAT WAS NOT IN THE ORIGINAL TEXT. DO NOT MAKE THINGS UP!
    """
    CONTENT_PROMPT = """
     Here are the outlines from the lectures in this course
         
     >>>>>LECTURE_OUTLINES_BEGIN<<<<<
    
    {LECTURE_OUTLINES}
    
     >>>>>LECTURE_OUTLINES_END<<<<<
    """
    SYSTEM_PROMPT_TEMPLATE = """
         {IDENTITY_PROMPT}
        {MAIN_TASK_PROMPT}
        {CONTENT_PROMPT}
        REMEMBER! Your task is:             
        
            {MAIN_TASK_REPEAT}
         """

    formatted_system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        IDENTITY_PROMPT=IDENTITY_PROMPT,
        MAIN_TASK_PROMPT=MAIN_TASK_PROMPT.format(theme=theme, all_themes=all_themes),
        CONTENT_PROMPT=CONTENT_PROMPT.format(LECTURE_OUTLINES=lecture_outlines),
        MAIN_TASK_REPEAT=MAIN_TASK_PROMPT
    )
    try:
        logger.debug(f"Generating AI outline with for the theme: {theme}")
        response = await make_openai_text_generation_ai_request(
            client=AI_CLIENT,
            system_prompt=formatted_system_prompt,
            llm_model=DEFAULT_LLM
        )
        logger.debug(f"AI outline response: {response} \n\n ({len(response.split(' '))} words, {len(response.split('\n'))} lines)")
        return response

    except Exception as e:
        logger.error(f"Error adding AI outline : {e}")
        raise e


KEY_THEMES = [
    "Human Perceptual Motor Neuroscience",
    "Philosophy of science, empiricism, and the scientific method",
    "AI",
    "Research Methodology",
    "Motion Capture",
    "Vision and eye movements",
    "Biomechanics, posture, and balance",
    "Teaching/personal philosophy",
    "Poster assignment"
]

async def main():
    lecture_outlines = load_lecture_data()
    tasks = []
    for theme in KEY_THEMES:
        all_themes = ", ".join(KEY_THEMES)
        all_themes.replace(theme, "")
        tasks.append(asyncio.create_task(ai_extract_lecture_themes(lecture_outlines=lecture_outlines, theme=theme, all_themes=KEY_THEMES)))

    results = await asyncio.gather(*tasks)
    theme_results = {theme: result for theme, result in zip(KEY_THEMES, results)}

    theme_out_folder = "lecture_transcripts/theme_outlines"
    Path(theme_out_folder).mkdir(parents=True, exist_ok=True)
    for theme, result in theme_results.items():
        clean_theme_name = theme.replace(" ", "_").replace(",", "").replace(":", "").replace("/", "_")
        with open(f"{theme_out_folder}/HMN25_{clean_theme_name}.md", 'w') as f:
            f.write(result)


    logger.info("Done!")


if __name__ == "__main__":
    asyncio.run(main())
