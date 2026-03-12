# Code for "Conversations at Scale: Robust AI-led Interviews with a Simple Open-Source Platform"

## What it Does
This project is designed as an AI-led interview platform specifically tailored for the Business Studies Internship program at Leiden University. It facilitates self-reflection for students by guiding them through structured interviews based on their learning objectives, progress, challenges, and future career aspirations. The platform supports the mandatory self-reflection interviews required for the internship report, including the analysis of AI's impact on business operations and industry trends.

## How it Works
The platform is built with Streamlit and uses OpenAI-, DeepInfra-, or Anthropic-compatible models to conduct real-time AI-led interviews. Interview transcripts are saved locally, completion metadata is synced to a remote SQLite database over SSH, and transcripts can optionally be emailed to participants.

### Key Features:
- Structured interview flow aligned with the Business Studies Internship Handbook.
- Real-time AI interaction for open-ended discussions and follow-up questions.
- Automatic saving of interview transcripts and timing data to local files.
- Remote storage of interview summaries and completion progress in SQLite.
- Email notifications to students and additional recipients.
- Compatibility with OpenAI (GPT), Anthropic (Claude), and DeepInfra-hosted models.

## Environment Setup and Configuration
The platform is built using Streamlit and requires the following configuration settings:

### Required Environment Variables:
- `API_PROVIDER`: One of `openai`, `deepinfra`, or `anthropic`.
- `MODEL`: The chat model to use for interviews.
- `API_KEY`: OpenAI API key. Also used for optional voice transcription.
- `ANTHROPIC_API_KEY`: Required when `API_PROVIDER="anthropic"`.
- `DEEPINFRA_API_KEY`: Required when `API_PROVIDER="deepinfra"`.
- `ENV`: Environment setting (`test` or `production`).
- `EMAIL_PASSWORD`: Optional Gmail app password for sending transcripts and verification codes.
- `USE_LIACS_EMAIL`: Optional flag to send mail via the LIACS SMTP path instead of Gmail.
- `LIACS_SSH_USERNAME` and `LIACS_SSH_KEY`: Required for remote SQLite sync and the LIACS SMTP path.

### Email Configuration
- Uses Gmail's SMTP server (`smtp.gmail.com` on port `587`).
- Requires setting up an App Password in Gmail.
- Store the email password in `.streamlit/secrets.toml` under `EMAIL_PASSWORD`.

### Local Development Configuration Setup
For local development, you need to create configuration files from the provided templates:

1. **Navigate to the code directory**: `cd code/.streamlit`
2. **Create secrets.toml**: Copy the template file and configure your credentials:
   - Copy `secrets.toml.example` to `secrets.toml`
   - Replace placeholder values with your actual API keys and credentials
   - **Never commit `secrets.toml` to version control** (it's excluded in `.gitignore`)
3. **Create config.toml** (optional): Copy `config.toml.example` to `config.toml` if you want custom Streamlit settings

**Important for Streamlit Cloud deployments**: 
- Do not use local `secrets.toml` for production deployments
- Configure all secrets through the Streamlit Cloud dashboard's secrets management interface
- The local configuration files are only for local development

## Installation Guide
1. Clone this repository.
2. Navigate to the `code` directory.
3. **Set up configuration files** (see "Local Development Configuration Setup" above).
4. Create and activate an environment using one of the following options:
   - Standard virtual environment:
     - `python3 -m venv ../.venv`
     - `source ../.venv/bin/activate`
     - `pip install -r requirements.txt`
   - Conda:
     - `conda env create -f interviewsenv.yml`
     - `conda activate interviews`
5. Start the platform: `streamlit run interview.py`

## Usage Guide
1. Navigate to the Streamlit URL provided in the terminal.
2. Open the interview with the required query parameters, at minimum `name` and `recipient_email`.
3. Conduct the interview following the structured flow.
4. End the interview to automatically save the transcript and timing data.
5. An email notification will be sent if configured.

# Instructions from the old repo

There are two options to explore the AI-led interviews discussed in the paper.

## Option 1: Online notebook

To try own ideas for interviews within minutes and without the need to install Python, see https://colab.research.google.com/drive/1sYl2BMiZACrOMlyASuT-bghCwS5FxHSZ (requires to obtain an API key)

## Option 2: Full platform

To install Python and set up the full interview platform locally (takes around 1h from scratch), see the following steps.

The interview platform is built using the library `streamlit` and the APIs of OpenAI and Anthropic.

- Download miniconda from https://docs.anaconda.com/miniconda/miniconda-install/ and install it (skip if `conda` is already installed)
- Obtain an API key from https://platform.openai.com/ or https://www.anthropic.com/api. In case of the OpenAI API, choose a "project" key
- Download this repository
- In the repository folder on your computer, set up your configuration files (requires making hidden folders visible):
  - Navigate to `/code/.streamlit/`
  - Copy `secrets.toml.example` to `secrets.toml`
  - Edit `secrets.toml` and paste your API key
- In the config.py, select a language model and adjust the interview outline
- In Terminal (Mac) or Anaconda Prompt (Windows), navigate to the folder `code` with `cd` (if unclear, briefly look up basic Linux command line syntax for navigating to folders)
- Once in the `code` folder, create the environment from the .yml file by writing `conda env create -f interviewsenv.yml` and confirming with enter (this installs Python and all libraries necessary to run the platform; only needs to be done once)
- Activate the environment with `conda activate interviews`
- Start the platform with `streamlit run interview.py`


## Paper and citation

The paper is available at https://ssrn.com/abstract=4974382 and can be cited with the following bibtex entry:

```
@article{geieckejaravel2024,
  title={Conversations at Scale: Robust AI-led Interviews with a Simple Open-Source Platform},
  author={Geiecke, Friedrich and Jaravel, Xavier},
  url={https://ssrn.com/abstract=4974382},
  year={2024}
}
```
