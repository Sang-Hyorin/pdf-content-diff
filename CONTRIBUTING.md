# Contributing

Use Python 3.9 or newer with `pip install -r requirements.txt`.

Run `python -m unittest discover -s tests -v` and `node --check extension.js`
before submitting a pull request. Tests must use synthetic or freely reusable
PDFs. Do not upload private manuscripts, credentials, user paths or logs.

Useful contributions include reading-order cases, multilingual text extraction,
hyphenation handling and compact review layouts. When reporting a false positive
or missed edit, describe the intended change and provide a minimal synthetic
reproduction. Figure-only comparison and OCR are outside the current scope.
