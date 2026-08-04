"""Cloud Run Job entrypoint: migrate, load catalogues, verify, report.

Runs as dmai-migrate with IAM DB auth over Direct VPC egress. Alembic
first (deploy proceeds only on success); catalogue loads are driven by
LOAD_CATALOGUES (comma list, ':current' suffix marks the pin target,
e.g. "v7.0:current,v5.0") — idempotent per version, so re-running is
safe. Ends by printing the verification counts: the database is
private-IP only, so these log lines ARE the production verification.
"""
import os
import subprocess
import sys
import tempfile

BUCKET = os.environ.get("CATALOGUE_BUCKET", "digital-maturity-assessor-catalogue-staging")


def sh(*cmd):
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True)


def bootstrap(password: str) -> None:
    """One-shot instance bootstrap as the postgres superuser: extensions
    (cloudsqlsuperuser-only), database ownership to the migrate identity,
    and CREATEROLE so revision 0001 can create the service roles. The
    password exists only for this execution and is rotated to a discarded
    random value immediately after (no DB password survives)."""
    from google.cloud.sql.connector import Connector, IPTypes
    connector = Connector(ip_type=IPTypes.PRIVATE)
    conn = connector.connect(
        os.environ["DB_INSTANCE_CONNECTION_NAME"], "pg8000",
        user="postgres", password=password, db=os.environ.get("DB_NAME", "dma_insights"),
    )
    conn.autocommit = True
    cur = conn.cursor()
    for ext in ("vector", "citext", "pg_trgm", "pgcrypto"):
        cur.execute(f'CREATE EXTENSION IF NOT EXISTS "{ext}"')
    migrate_user = os.environ.get("DB_USER", "dmai-migrate@digital-maturity-assessor.iam")
    db = os.environ.get("DB_NAME", "dma_insights")
    # Cloud SQL: postgres is cloudsqlsuperuser, not superuser — it must be a
    # member of a role before making it a database owner.
    cur.execute(f'GRANT "{migrate_user}" TO postgres')
    cur.execute(f'ALTER DATABASE {db} OWNER TO "{migrate_user}"')
    try:
        cur.execute(f'ALTER ROLE "{migrate_user}" CREATEROLE')
        print("bootstrap: migrate identity granted CREATEROLE", flush=True)
    except Exception as e:  # PG16 CREATEROLE/ADMIN rules can forbid this on
        # API-created users; pre-create the service roles instead, with
        # ADMIN for the migrate identity so 0001's grants still work.
        print(f"bootstrap: CREATEROLE unavailable ({e}); pre-creating service roles", flush=True)
        for role in ("svc_api", "svc_mcp", "svc_worker", "svc_migrate"):
            cur.execute(
                f"""DO $$ BEGIN
                     IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{role}') THEN
                       CREATE ROLE {role} NOLOGIN ADMIN "{migrate_user}";
                     END IF;
                   END $$"""
            )
    conn.close()
    print("bootstrap complete: extensions, db ownership, role authority", flush=True)


def main() -> int:
    pw = os.environ.get("BOOTSTRAP_PG_PASSWORD")
    if pw:
        bootstrap(pw)
    sh("alembic", "upgrade", "head")

    for spec in filter(None, os.environ.get("LOAD_CATALOGUES", "").split(",")):
        version, _, flag = spec.partition(":")
        from google.cloud import storage
        client = storage.Client()
        with tempfile.TemporaryDirectory() as tmp:
            n = 0
            for blob in client.list_blobs(BUCKET, prefix=f"{version}/"):
                if blob.name.endswith(".xlsx") and "_" in blob.name.split("/")[-1]:
                    dest = os.path.join(tmp, blob.name.split("/")[-1])
                    blob.download_to_filename(dest)
                    n += 1
            print(f"downloaded {n} workbooks for {version}", flush=True)
            args = ["python", "-m", "ccg_loader", "--version", version, "--dir", tmp]
            if flag == "current":
                args.append("--make-current")
            sh(*args)

    # Verification — printed, because the logs are the only reachable proof.
    from ccg_loader.db import connect
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM pg_tables WHERE schemaname='public' AND tablename <> 'alembic_version'")
    print(f"VERIFY tables={cur.fetchone()[0]}", flush=True)
    cur.execute("SELECT version, cell_count, category_count, is_current FROM ccg_versions ORDER BY version")
    for row in cur.fetchall():
        print(f"VERIFY catalogue version={row[0]} cells={row[1]} categories={row[2]} current={row[3]}", flush=True)
    cur.execute("SELECT rolname FROM pg_roles WHERE rolname LIKE 'svc_%' ORDER BY 1")
    print(f"VERIFY roles={[r[0] for r in cur.fetchall()]}", flush=True)
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
