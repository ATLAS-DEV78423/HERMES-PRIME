# Release Checklist

## Pre-Release
- [ ] All tests passing (CI green)
- [ ] No security vulnerabilities (`pip-audit`)
- [ ] `ruff check .` passes with no errors
- [ ] `mypy hermes_prime/ infrastructure/` passes
- [ ] Version bumped in `pyproject.toml` (semantic versioning)
- [ ] CHANGELOG updated with release notes
- [ ] README is current and accurate
- [ ] SECURITY.md is up to date
- [ ] SBOM generated (`pip-audit --requirement requirements.txt --format json > sbom.json`)
- [ ] Dependencies reviewed for CVEs

## Release Process
- [ ] Tag created on GitHub (`git tag v0.x.x && git push origin v0.x.x`)
- [ ] Release notes drafted on GitHub
- [ ] PyPI package published (`python -m build && twine check dist/* && twine upload dist/*`)
- [ ] Docker image built and pushed (`docker build -t hermes-prime:v0.x.x . && docker push ...`)
- [ ] GitHub Release published

## Post-Release
- [ ] Verify PyPI package installs cleanly (`pip install hermes-prime==0.x.x`)
- [ ] Verify Docker image runs (`docker run --rm hermes-prime:v0.x.x --help`)
- [ ] Close milestone on GitHub
- [ ] Update any downstream dependents
