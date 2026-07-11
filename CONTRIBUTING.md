# Contributing to Parley

Thanks for your interest in improving Parley! Contributions of all sizes are welcome.

## Getting started

1. Fork and clone the repo.
2. Install deps: `pip install -r requirements.txt`.
3. Launch a browser with CDP: `./scripts/start-browser.sh`.
4. Sanity check: `python3 parley.py list`.

## Ways to contribute

- **Add a new AI site.** Most sites need only a fast-path selector for (a) the input box and (b) the latest response. Look at the `UNIVERSAL_*` JavaScript blocks in `parley.py` and add your selectors alongside the ChatGPT/Gemini/Claude entries.
- **Improve streaming detection.** See `make_mutation_observer_js` in `parley.py`.
- **Bug fixes, docs, examples.** Always appreciated.

## Guidelines

- Keep the **text-only, token-efficient** philosophy — avoid screenshots / vision.
- Avoid adding heavy dependencies. The only runtime dep today is `websocket-client`.
- Test your change against at least one real site and describe what you tested in the PR.
- Run a syntax check before pushing:

  ```bash
  python3 -c "import ast; ast.parse(open('parley.py').read())"
  ```

## Reporting bugs

Open an issue with:

- Browser + version, OS, Python version
- The exact command you ran and the output
- Which AI site/tab you were targeting

## Code of conduct

Be respectful and constructive. We are all here to build something useful.
