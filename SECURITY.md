# Security

## Credentials

Keep inverter, Wattpilot, and Polestar credentials only in a local `.env` file.
The repository ignores `.env`; never copy real credentials into
`.env.example`, screenshots, issues, logs, or commits.

If credentials are committed accidentally, remove them from the repository
history and rotate the affected password immediately. Removing only the latest
file revision is not sufficient.

## Unofficial integrations

The Wattpilot and Polestar integrations use unofficial interfaces. Keep their
dependencies updated, use read-only access where possible, and review upstream
changes before upgrading. Do not expose this dashboard directly to the public
internet without authentication and TLS termination.

## Reporting issues

Do not open a public issue containing credentials, VINs, IP addresses, access
tokens, or other personal data. Contact the repository owner privately for
security-sensitive reports.
