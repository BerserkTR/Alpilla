# templates/
Layouts used by engines - never outputs themselves.
- `reports/*.md.j2` - Jinja2 Markdown report bodies
- `html/report.html.j2` - HTML wrapper/styling for reports
- `docx/datasheet_base.docx` - Word styles, page setup, header/footer for datasheets (edit in Word; keep one paragraph in header and footer). Rebuild the default with `python -m engine.tools.make_docx_template`.

Changing a template changes outputs: bump the engine `version` so existing outputs show as stale.
