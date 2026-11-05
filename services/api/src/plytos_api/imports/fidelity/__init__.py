"""The import's fidelity bench: made-up careers written out in many layouts, read
back by the import, and scored against what was written.

Because each resume is generated from a known career (`truth.py`), the right
answer is known exactly: every employer, title and date, which job each
accomplishment sits under, its workstream, and which section each other item
belongs to. `layouts.py` writes a career as a Word file or a PDF in a given
layout; `score.py` compares an import's reading with the career; running the
package scores every layout:

    python -m plytos_api.imports.fidelity              # the rules reader, no AI
    python -m plytos_api.imports.fidelity --ai --budget 20

Everyone in it is fictional. Nothing here reads a real resume.
"""
