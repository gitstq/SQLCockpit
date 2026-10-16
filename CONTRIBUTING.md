# Contributing to SQLCockpit

Thanks for your interest in improving SQLCockpit! 感谢你想为 SQLCockpit 贡献代码！

## Ground rules

- **Zero dependencies**: SQLCockpit must keep running on a stock Python install (standard library only). Pull requests adding third-party dependencies will be declined.
- **Python >= 3.9**: keep the code compatible with Python 3.9 through 3.13 (no `match` statements, no `X | Y` runtime annotations).
- **No local side effects for CI-only work**: builds, packaging and multi-platform checks run on GitHub Actions runners.

## Development workflow

1. Fork and clone the repository.
2. Create a feature branch: `git checkout -b feat/my-feature`.
3. Make your change with tests. Run everything locally with the standard library only:
   ```bash
   python -m compileall -q sqlcockpit tests
   python -m unittest discover -s tests -v
   ```
4. Follow the Angular commit convention:
   - `feat:` new feature
   - `fix:` bug fix
   - `docs:` documentation only
   - `refactor:` code change that neither fixes a bug nor adds a feature
   - `test:` adding or fixing tests
   - `chore:` tooling / CI changes
5. Open a pull request against `main` and describe the motivation, the change and the testing you performed.

## Reporting issues

- Search existing issues first to avoid duplicates.
- Include your OS, Python version (`python --version`), the exact command you ran and the full error output.
- Never include real database files, tokens or other secrets in issues.

## Code style

- Docstrings for public functions and classes.
- Type hints where practical (`from __future__ import annotations` at the top of each module).
- Prefer standard-library modules over hand-rolled equivalents.
