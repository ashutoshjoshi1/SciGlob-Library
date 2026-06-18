# Publishing SciGlob to PyPI - Complete Guide

**Version:** 0.1.5  
**Status:** ✅ Ready for Publishing  
**Date:** December 17, 2025

---

## 📦 Current Status

✅ Package built successfully  
✅ Both distributions created:
- `dist/sciglob-0.1.5-py3-none-any.whl` (wheel)
- `dist/sciglob-0.1.5.tar.gz` (source)

✅ Packages validated with `twine check`  
✅ All PyPI compliance checks passed  

---

## 🚀 Step-by-Step Publishing Instructions

### Step 1: Create PyPI Accounts

You'll need accounts on both Test PyPI (for testing) and Production PyPI.

#### A. Create Test PyPI Account (Test First!)

1. Go to: https://test.pypi.org/account/register/
2. Fill in:
   - Username: (choose a username)
   - Email: ajoshi@sciglob.com
   - Password: (create strong password)
3. **Verify your email** (check inbox)
4. **Enable 2FA** (Two-Factor Authentication):
   - Go to Account Settings
   - Security → Add 2FA method
   - Use authenticator app (Google Authenticator, Authy, etc.)

#### B. Create Production PyPI Account

1. Go to: https://pypi.org/account/register/
2. Fill in **same details as Test PyPI**
3. Verify email
4. Enable 2FA (required)

---

### Step 2: Create API Tokens

**Why tokens?** More secure than passwords, and required for automation.

#### A. Test PyPI Token

1. Log in to https://test.pypi.org/
2. Go to: Account Settings → API tokens
3. Click "Add API token"
4. **Token name:** `sciglob-test-upload`
5. **Scope:** "Entire account" (first time) or "Project: sciglob" (after first upload)
6. Click "Add token"
7. **⚠️ IMPORTANT:** Copy the token immediately! Format: `pypi-AgEIc...`
8. **Save it somewhere safe** (you won't see it again)

#### B. Production PyPI Token

1. Log in to https://pypi.org/
2. Go to: Account Settings → API tokens
3. Click "Add API token"
4. **Token name:** `sciglob-production-upload`
5. **Scope:** "Entire account" (first time)
6. Click "Add token"
7. **Copy and save the token**

---

### Step 3: Configure Twine with Tokens

Create a file `~/.pypirc` (in your home directory) with your tokens:

```bash
# Create/edit the file
nano ~/.pypirc
```

Add this content (replace YOUR_TEST_TOKEN and YOUR_PROD_TOKEN with actual tokens):

```ini
[distutils]
index-servers =
    pypi
    testpypi

[testpypi]
repository = https://test.pypi.org/legacy/
username = __token__
password = pypi-AgEI...YOUR_TEST_TOKEN_HERE...

[pypi]
repository = https://pypi.org/legacy/
username = __token__
password = pypi-AgEI...YOUR_PROD_TOKEN_HERE...
```

**Set secure permissions:**
```bash
chmod 600 ~/.pypirc
```

---

### Step 4: Upload to Test PyPI (TESTING FIRST!)

Always test on Test PyPI before uploading to production!

```bash
# Navigate to your project
cd "/Users/ashu/Desktop/Github/SciGlob-Library"

# Upload to Test PyPI
python -m twine upload --repository testpypi dist/*
```

**Expected output:**
```
Uploading distributions to https://test.pypi.org/legacy/
Uploading sciglob-0.1.5-py3-none-any.whl
100% ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 
Uploading sciglob-0.1.5.tar.gz
100% ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 

View at:
https://test.pypi.org/project/sciglob/0.1.5/
```

---

### Step 5: Test Installation from Test PyPI

Test that the package can be installed:

```bash
# Create a test environment
python -m venv test_env
source test_env/bin/activate  # On Windows: test_env\Scripts\activate

# Install from Test PyPI
pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ sciglob

# Test import
python -c "import sciglob; print(sciglob.__version__)"
# Should print: 0.1.5

# Test basic functionality
python -c "from sciglob import HeadSensor; print('Import successful!')"

# Deactivate and cleanup
deactivate
rm -rf test_env
```

**Note:** We use `--extra-index-url https://pypi.org/simple/` because dependencies (pyserial, pyyaml) are on production PyPI, not Test PyPI.

---

### Step 6: Upload to Production PyPI

✅ If Test PyPI worked perfectly, upload to production:

```bash
# Upload to Production PyPI
python -m twine upload dist/*
```

**Expected output:**
```
Uploading distributions to https://upload.pypi.org/legacy/
Uploading sciglob-0.1.5-py3-none-any.whl
100% ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 
Uploading sciglob-0.1.5.tar.gz
100% ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 

View at:
https://pypi.org/project/sciglob/0.1.5/
```

---

### Step 7: Verify Production Installation

Wait 1-2 minutes for PyPI to process, then test:

```bash
# Create fresh environment
python -m venv verify_env
source verify_env/bin/activate

# Install from PyPI (no special flags needed!)
pip install sciglob

# Verify
python -c "import sciglob; print(f'SciGlob v{sciglob.__version__} installed successfully!')"

# Cleanup
deactivate
rm -rf verify_env
```

---

### Step 8: Update Project Scopes (After First Upload)

After first successful upload, create project-specific tokens:

#### Test PyPI:
1. Go to https://test.pypi.org/manage/account/
2. Delete the old token
3. Create new token with **Scope: "Project: sciglob"**

#### Production PyPI:
1. Go to https://pypi.org/manage/account/
2. Delete the old token
3. Create new token with **Scope: "Project: sciglob"**

Update your `~/.pypirc` with the new tokens.

---

## 🎉 Success! Your Library is Now Published

Anyone can now install your library with:

```bash
pip install sciglob
```

Your package is available at:
- **Production:** https://pypi.org/project/sciglob/
- **Documentation:** https://github.com/ashutoshjoshi1/SciGlob-Library

---

## 📝 Publishing Future Versions

When you want to release a new version:

### 1. Update Version Number

Edit `pyproject.toml`:
```toml
version = "0.1.6"  # Increment version
```

And `sciglob/__init__.py`:
```python
__version__ = "0.1.6"
```

### 2. Update CHANGELOG.md

Document what's new:
```markdown
## [0.1.6] - 2025-12-XX
### Added
- New feature X
### Fixed
- Bug Y
```

### 3. Commit Changes

```bash
git add .
git commit -m "Release v0.1.6"
git tag v0.1.6
git push origin main --tags
```

### 4. Rebuild and Upload

```bash
# Clean old builds
rm -rf dist/ build/ *.egg-info

# Build new version
python -m build

# Check packages
python -m twine check dist/*

# Upload to Test PyPI first
python -m twine upload --repository testpypi dist/*

# Test installation
pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ sciglob==0.1.6

# If good, upload to production
python -m twine upload dist/*
```

---

## 🔒 Security Best Practices

1. **Never commit** `.pypirc` or API tokens to git
2. **Use project-scoped tokens** after first upload
3. **Rotate tokens** periodically
4. **Enable 2FA** on both PyPI accounts
5. **Keep tokens secure** - treat them like passwords

---

## ⚠️ Troubleshooting

### Error: "The user 'YOUR_USERNAME' isn't allowed to upload to project 'sciglob'"

**Solution:** Use `__token__` as username with your API token as password.

### Error: "File already exists"

**Solution:** You can't re-upload the same version. Increment version number.

### Error: "Invalid or non-existent authentication information"

**Solution:** Check your token is correct in `~/.pypirc`. Regenerate if needed.

### Error: "Package name already taken"

**Solution:** The name 'sciglob' is already yours if you uploaded. Use project-scoped token.

### Installation fails with "No matching distribution found"

**Solution:** Wait 1-2 minutes after upload. PyPI needs time to process.

---

## 📊 Package Statistics

After publishing, you can view statistics at:
- https://pypi.org/project/sciglob/
- https://pypistats.org/packages/sciglob

Track:
- Download counts
- Version distribution
- Geographic distribution

---

## 🔄 Automated Publishing with GitHub Actions (Optional)

For future automation, you can set up GitHub Actions to publish automatically on new releases.

Create `.github/workflows/publish.yml`:

```yaml
name: Publish to PyPI

on:
  release:
    types: [published]

jobs:
  publish:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install build twine
      
      - name: Build package
        run: python -m build
      
      - name: Publish to PyPI
        env:
          TWINE_USERNAME: __token__
          TWINE_PASSWORD: ${{ secrets.PYPI_API_TOKEN }}
        run: python -m twine upload dist/*
```

Add your PyPI token to GitHub Secrets:
1. Go to repository → Settings → Secrets and variables → Actions
2. Add secret: `PYPI_API_TOKEN` with your token value

---

## ✅ Checklist Before Publishing

- [ ] Version number updated in `pyproject.toml`
- [ ] Version number updated in `sciglob/__init__.py`
- [ ] CHANGELOG.md updated
- [ ] All tests passing
- [ ] Documentation up to date
- [ ] README.md current
- [ ] No sensitive information in code
- [ ] Git commits pushed
- [ ] Git tag created
- [ ] Package built successfully
- [ ] `twine check` passed
- [ ] Tested on Test PyPI
- [ ] Ready for production!

---

## 📞 Support

If you encounter issues:
- PyPI Help: https://pypi.org/help/
- Packaging Guide: https://packaging.python.org/
- Twine Docs: https://twine.readthedocs.io/

---

**Good luck with your publication! 🚀**

After publishing, update your README.md to include:
```markdown
## Installation

Install from PyPI:
```bash
pip install sciglob
```

Or install from source:
```bash
git clone https://github.com/ashutoshjoshi1/SciGlob-Library.git
cd SciGlob-Library
pip install -e .
```
