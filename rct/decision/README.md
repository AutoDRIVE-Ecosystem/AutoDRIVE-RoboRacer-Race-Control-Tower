# Backend Decision Packages

Decision packages are server-side analysis modules. Each package has:

- a stable id in `PACKAGES` in `engine.py`
- Python analysis logic that returns an opinion, metrics, and plot series
- a Jinja2 HTML template fragment under `templates/`
- a Matplotlib SVG plot rendered through the decision plot REST API

Frontend code should call the REST APIs and render returned HTML. It should not own penalty analysis logic.
