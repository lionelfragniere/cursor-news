# Security Policy

## Reporting

Please report security issues privately by email:

```text
lionel.fragniere@gmail.com
```

Do not open a public issue for secrets, credential leaks, auth bypasses or
anything that could expose user data.

## Supported Version

This is an early open-source prototype. Security fixes are handled on `main`.

## Secrets

The repository must not contain:

- `.env`
- Google Cloud credentials
- Android keystores
- Google Play service account JSON
- generated databases, audio or local model files
