# Security policy

Please report vulnerabilities privately through GitHub: **Security > Report a vulnerability** on this repository. Do not open a public issue for a security problem.

Include the version or commit, what you did and what you saw. We aim to answer within a week.

Deployments handle biological sample records and shipment documents: keep `config.env`, databases and uploaded files out of version control, use a long administrator password and serve the application over HTTPS when other people can reach it.
