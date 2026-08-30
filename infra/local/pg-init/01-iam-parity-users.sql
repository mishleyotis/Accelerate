-- Local stand-ins for the Cloud SQL IAM database users. Cloud SQL names an
-- IAM service-account user "<sa-name>@<project>.iam"; creating the same
-- login roles locally means every migration grant behaves identically in
-- both environments. Passwords are local-only convenience.
CREATE ROLE "dmai-api@digital-maturity-assessor.iam" LOGIN PASSWORD 'local';
CREATE ROLE "dmai-mcp@digital-maturity-assessor.iam" LOGIN PASSWORD 'local';
CREATE ROLE "dmai-worker@digital-maturity-assessor.iam" LOGIN PASSWORD 'local';
CREATE ROLE "dmai-migrate@digital-maturity-assessor.iam" LOGIN PASSWORD 'local';
