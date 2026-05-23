# Release Checklist

Use this checklist when cutting a release.

- [ ] Bump `pyproject.toml` version
- [ ] Update `CHANGELOG.md` with release notes
- [ ] Run test suite locally: `pytest -q`
- [ ] Ensure CI is green on PR
- [ ] Create tag `vX.Y.Z` and push it
- [ ] Verify GitHub Release created and assets attached
- [ ] Publish release notes to website
