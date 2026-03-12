# CLAUDE.md

This file provides guidance for Claude Code and other coding agents when working with this repository.

---

# 1. Project Summary

This repository is a **local manga translation assistant**.

Its purpose is to help users translate manga images using a locally deployed vision-language model. The tool supports both a web UI workflow and a command-line workflow.

The project is intended to remain:

- lightweight
- easy to run on Windows
- compatible with WSL-hosted model services
- simple to maintain
- focused on practical manga translation workflows

This is **not** a cloud SaaS application.
This is **not** a distributed system.
This is a **local desktop-oriented tool** with a Python backend and a simple browser frontend.

---

# 2. Primary Goals

When making changes, prioritize the following goals:

1. Keep the tool usable for non-technical end users
2. Preserve the existing Windows + WSL workflow
3. Keep dependencies minimal
4. Avoid unnecessary architectural rewrites
5. Improve reliability for batch image translation
6. Preserve export compatibility (Markdown / CSV / JSON)
7. Keep the frontend simple and responsive

---

# 3. Tech Stack

## Backend

- Python 3
- Flask
- Pillow

Backend entry point:

- `manga_hub.py`

## Frontend

- HTML
- CSS
- JavaScript
- Vanilla JS only

Main frontend script:

- `static/app.js`

## Model Serving

- Qwen-VL
- deployed with vLLM
- running inside WSL

Ports:

- `8001` = 7B model
- `8000` = 30B model

Claude should assume the model service is local and already deployed separately.

---

# 4. Supported Workflows

## Web UI mode

Users start the web UI with:

- `start_manga_hub.cmd`
- or `launch_manga_hub.ps1`

The web UI supports:

- drag-and-drop upload
- clipboard paste upload
- image processing from browser
- fixed region selection
- export of structured results

## CLI mode

Users run:

- `translate_manga.ps1`

CLI mode is mainly for:

- batch translation
- folder processing
- repeated translation tasks
- automation-oriented workflows

---

# 5. Expected Project Structure

Typical important files and directories:

- `manga_hub.py` — Flask backend
- `translate_manga.ps1` — CLI entry
- `start_manga_hub.cmd` — Windows launcher
- `launch_manga_hub.ps1` — PowerShell launcher
- `static/app.js` — main frontend logic
- `static/` — frontend assets
- image input/output folders — may vary by implementation

When editing, inspect the actual repository structure first before assuming filenames beyond those already known.

---

# 6. Functional Scope

Core functionality includes:

- translating a single image
- translating folders in batch
- uploading images through web UI
- pasting images from clipboard
- selecting and reusing fixed regions
- exporting translation results in:
  - Markdown
  - CSV
  - JSON

Changes should preserve these capabilities unless the user explicitly requests otherwise.

---

# 7. Architectural Understanding

The project generally has three layers:

## A. UI Layer

Handles:

- drag/drop events
- paste events
- region selection
- result rendering
- export triggers

Main file:

- `static/app.js`

## B. Web Backend Layer

Handles:

- file upload
- request routing
- image processing orchestration
- calling translation/model pipeline
- returning structured results

Main file:

- `manga_hub.py`

## C. Model Inference Layer

External local dependency:

- Qwen-VL served through vLLM in WSL

The app likely communicates with the model over HTTP on localhost.

Claude should treat model serving as an external dependency, not as code to redesign unless explicitly requested.

---

# 8. Non-Goals

Unless explicitly requested, do NOT:

- rewrite Flask into FastAPI
- replace vanilla JS with React/Vue
- replace Pillow with OpenCV-heavy rewrites
- redesign the project into microservices
- add databases, queues, or cloud infrastructure
- change the model serving stack
- introduce large dependency trees for minor tasks

This project values simplicity and maintainability over abstraction.

---

# 9. Coding Principles

## General

- Read relevant files before editing
- Make minimal, targeted changes
- Preserve existing behavior unless a bug requires changing it
- Prefer clarity over cleverness
- Avoid broad refactors without clear user request
- Keep function boundaries understandable
- Preserve current user workflow

## Dependency Policy

Prefer existing dependencies.

Before adding a new dependency, ask:

- Can this be done with Python stdlib?
- Can this be done with Flask/Pillow/current JS?
- Is the dependency lightweight and justified?

Avoid introducing heavy frameworks or tools unless clearly necessary.

## Compatibility

Preserve compatibility with:

- Windows launch flow
- PowerShell scripts
- WSL-hosted model service
- existing export formats

---

# 10. Python Backend Guidelines

When working on Python backend code:

- keep Flask routes simple and explicit
- separate request handling from processing logic when practical
- validate file inputs carefully
- avoid loading unnecessary images into memory
- handle batch processing robustly
- keep error messages actionable for local users
- preserve filesystem-based workflow

If refactoring, prefer extracting helper functions over introducing complex class hierarchies.

---

# 11. Frontend Guidelines

The frontend is intentionally lightweight.

Rules:

- use vanilla JavaScript
- avoid adding frameworks
- prefer direct DOM logic when the UI is small
- keep interactions responsive
- keep code understandable for future maintenance

When editing UI behavior:

- preserve drag-and-drop
- preserve paste-upload behavior
- preserve region-selection usability
- avoid making the UI visually complex unless requested

---

# 12. Image Processing Guidelines

Image processing is a core part of the product.

Rules:

- prefer Pillow
- avoid destructive image modifications unless intended
- maintain predictable output
- preserve batch-processing safety
- do not assume all images have identical dimensions
- be careful with memory usage for large folders

If changing image processing logic:

- verify behavior on single-image and folder workflows
- preserve compatibility with downstream export/output logic

---

# 13. Model Interaction Guidelines

The project depends on a local VLM endpoint.

Assume the model service is reachable at localhost, typically:

- `http://127.0.0.1:8001`
- `http://127.0.0.1:8000`

Possible usage pattern:

- send image-related input
- receive OCR/translation/structured results
- transform that into app output

When working on model integration:

- do not hardcode unnecessary assumptions about only one port unless repository logic already does so
- preserve support for both model sizes if already present
- add timeout/error handling where useful
- surface connection failures clearly to users

If the app fails, one common cause is that the WSL model service is not running.

---

# 14. Output and Export Rules

The tool supports export formats:

- Markdown
- CSV
- JSON

Changes must preserve schema stability as much as possible.

When modifying export logic:

- do not silently rename fields unless required
- avoid breaking downstream scripts/users
- preserve encoding correctness
- preserve readable text formatting
- keep JSON structured and machine-friendly
- keep CSV predictable and tabular
- keep Markdown human-readable

If changing output format is necessary, explain the impact clearly.

---

# 15. Performance Expectations

Users may process many manga pages at once.

Priorities:

- avoid reading all images into memory at once
- prefer sequential or controlled-batch processing
- avoid blocking UI unnecessarily
- avoid expensive repeated conversions
- avoid duplicate inference calls when possible

Performance improvements are welcome if they do not significantly increase complexity.

---

# 16. Error Handling Policy

When errors occur, prefer actionable messages.

Good error messages help users answer:

- Was the file invalid?
- Did upload fail?
- Is the model service offline?
- Is the port incorrect?
- Did image parsing fail?
- Did export fail?

Avoid vague messages like:

- "Something went wrong"
- "Unknown error"

Prefer messages that suggest the next debugging step.

---

# 17. Debugging Priorities

When debugging issues, check in this order:

## For web UI issues

1. Flask server started successfully
2. Browser can access the local page
3. static assets loaded correctly
4. upload/paste event handlers are firing
5. backend route is returning expected data
6. model service is reachable

## For translation failures

1. input image is valid
2. request reaches backend
3. backend successfully calls model endpoint
4. model endpoint is running on expected port
5. response format matches parser expectations
6. export/output logic handles returned content correctly

## For CLI failures

1. PowerShell script arguments/path handling
2. Python environment correctness
3. file/folder enumeration
4. image read success
5. model connectivity
6. output writing permissions

---

# 18. File Editing Strategy

Before changing code, Claude should:

1. Identify the smallest set of files relevant to the request
2. Read those files first
3. Explain the intended change briefly
4. Implement minimal edits
5. Summarize which files changed and why
6. Provide verification steps

Do not edit many files if one or two targeted changes are enough.

---

# 19. Testing Strategy

Formal automated tests may or may not exist.

If tests exist:

- run the smallest relevant tests first
- avoid changing unrelated tests
- add tests only where they provide clear value

If tests do not exist:

- provide manual verification steps
- prefer reproducible checks for:
  - single image translation
  - folder batch translation
  - drag/drop upload
  - paste upload
  - export generation

Useful manual checks include:

- launch web UI
- upload one image
- upload a folder/batch
- test region selection
- confirm Markdown/CSV/JSON output
- confirm model service connection works

---

# 20. Recommended Workflow For Claude

For feature work:

1. understand the user request
2. inspect the relevant files
3. identify the current implementation path
4. propose a minimal solution
5. implement carefully
6. verify behavior
7. summarize changes

For bug fixes:

1. locate the failing layer
2. reproduce mentally from code path
3. patch the smallest reliable point
4. avoid broad speculative rewrites
5. provide verification steps

For refactors:

1. preserve behavior
2. improve clarity incrementally
3. avoid changing public behavior without need
4. keep launch scripts and model integration intact

---

# 21. Repository-Specific Agent Hints

Claude should be especially helpful with:

- improving translation pipeline robustness
- improving local UX for manga processing
- debugging Flask route or upload issues
- making region selection more reliable
- improving batch folder processing
- improving structured export generation
- improving error messages
- reducing friction in Windows + WSL workflows

Claude should be cautious with:

- changing model prompt contracts
- changing output schemas
- changing launcher scripts
- changing local path assumptions
- changing frontend behavior that non-technical users rely on

---

# 22. Preferred Change Style

Preferred:

- small patches
- explicit logic
- clear helper functions
- stable behavior
- practical local-tool ergonomics

Avoid:

- speculative abstractions
- framework migrations
- overengineering
- introducing hidden magic
- turning simple scripts into large architectures

---

# 23. Common Task Reference

## Start web UI

Use:

- `start_manga_hub.cmd`
- or `launch_manga_hub.ps1`

## Run CLI translation

Use:

- `translate_manga.ps1`

## Check model service

Verify whether local model endpoints are reachable on:

- port `8001`
- port `8000`

---

# 24. When Uncertain

If implementation details are unclear:

- inspect the actual file structure
- trace existing code paths
- follow current conventions
- prefer compatibility over idealized redesign

If multiple solutions are possible, prefer the one that:

- requires fewer changes
- is easier to debug
- preserves current workflow
- keeps the project lightweight

---

# 25. Response Style For Claude

When assisting in this repo, Claude should:

- be concise but practical
- explain the plan before significant edits
- mention which files are relevant
- note risks when changing pipeline/output behavior
- provide clear validation steps
- avoid unnecessary theory

A good response structure is:

1. what is happening
2. what will be changed
3. the patch
4. how to verify it

---

# 26. Final Reminder

This repository is a practical, local manga translation tool.

The most important engineering values are:

- reliability
- simplicity
- low friction
- Windows usability
- WSL model compatibility
- maintainable code
- preserving current workflows