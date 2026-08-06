# MirrorView

MirrorView is an AI career training workspace for job seekers. It brings role analysis, resume preparation, application writing, and interview practice into one continuous workflow.

The goal is not to produce generic career advice. MirrorView helps you turn a target role and your own experience into clearer evidence, stronger application materials, and more deliberate interview practice.

[中文](README_CN.md) | English

## What We Want To Build

MirrorView is designed around a practical job-search loop:

```text
Understand the role -> improve or create a resume -> write the application message -> practice the interview
```

Each tool can be used on its own, or as part of the same preparation process. The long-term direction is a focused career workspace that helps users move from a job description to a more confident application without repeating the same information at every step.

## Use MirrorView

1. Open the [MirrorView website](https://mirrorview.dpdns.org/) and select **Model Settings**.
2. Choose the supported model provider, enter your API key, base URL, and model name, then test and save the connection.
3. Choose a workflow from the home page.
4. Provide the resume, job description, or experience details requested by that workflow.
5. Review the result, revise the input when needed, and export supported resume or report outputs as HTML or PDF.

The model API key is stored in the browser and used for your requests. Use a temporary or usage-limited key and revoke it when you no longer need it. Do not include real credentials in screenshots, issue reports, or shared files.

## Product Tour

The home page is the starting point for every workflow:

![MirrorView home page](docs/images/readme-home.jpg)

### Resume Match

Upload a PDF resume, enter the target role, and paste the job description. MirrorView uses the role requirements to produce a match assessment, identify strengths and gaps, and suggest concrete resume improvements.

![Resume match input](docs/images/readme-resume-match.jpg)

The result can be reviewed in the site and exported as HTML or PDF when the report is available.

### AI Resume Craft

Resume Craft is a guided resume-building flow:

- Step 1 sets the target role, JD summary, template, language, and optional photo;
- Step 2 collects personal information and education;
- Step 3 uses a conversational flow to organize work, project, skills, and certificate information;
- the final step generates a resume preview that can be revised and exported.

It currently supports Chinese, English, and bilingual output, multiple templates, optional profile photos, HTML preview, and PDF export.

![Resume Craft setup and guided flow](docs/images/readme-resume-craft.jpg)

### Cover Letter

Enter the company name, target job description, and resume text. Select an email or recruitment-chat scenario to generate a tailored application message that connects your experience with the role.

### Text Mock Interview

Start with a target role or your first answer. The AI interviewer keeps the conversation context and continues with follow-up questions. It is intended for practice in:

- introductions and motivation;
- project and behavioral questions;
- technical, business, and situational questions;
- answer structure and interview communication.

### Job Search

The Job Search entry is visible in the product navigation, but the current version is still a placeholder. Real job data sources, asynchronous search, and result tracking are planned for a later phase.

## Current Status

| Capability | Current state | What it does today |
|---|---|---|
| Resume Match | Available | Analyzes a PDF resume against a target role and JD. |
| AI Resume Craft | Available | Guides resume creation and supports HTML/PDF output. |
| Cover Letter | Planned | Generates email or recruitment-chat application copy. |
| Text Mock Interview | Planned | Runs a context-aware interview practice conversation. |
| Job Search | Planned | Navigation placeholder; live job sources are not connected yet. |

## Important Notes

- AI output is a draft for preparation. Check facts, dates, claims, and formatting before using any material in an application.
- MirrorView currently relies on the model connection configured by the user. Availability and cost depend on the selected provider and key.
- A successful resume or report export depends on the relevant workflow completing successfully; exported content remains the user's responsibility to review.

## License

MIT License. See [LICENSE](LICENSE) for details.
