# Default variable values for the DMA Insights Terraform deployment.
# project_id is committed here because this is a single-tenant deployment
# and the project ID is not a secret.
#
# image_sha is intentionally NOT set here — it must be supplied at apply
# time to prevent accidentally deploying a stale image:
#   terraform apply -var "image_sha=$(git rev-parse --short HEAD)"
# Or use the deploy wrapper: apps/dma-insights/infra/deploy.sh

project_id = "digital-maturity-assessor"
