#!/bin/bash
set -euo pipefail

# Build and deploy from main directory
cd /Users/alexwright/Projects/Proxima

if ! command -v gcloud &> /dev/null; then
  echo "Error: 'gcloud' command not found." >&2
  echo "Install the Google Cloud CLI first, e.g.: brew install --cask google-cloud-sdk" >&2
  echo "Then run 'gcloud init' / 'gcloud auth login' before retrying this script." >&2
  exit 1
fi

# Create secret for MongoDB URI (run once)
# echo -n "your-mongodb-connection-string" | gcloud secrets create mongodb-uri --data-file=-

gcloud run deploy proxima \
  --source . \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --memory 1Gi \
  --cpu 1 \
  --min-instances 0 \
  --max-instances 10 \
  --timeout 300 \
  --env-vars-file cloud_runner_env.yaml \
  --set-secrets MONGODB_URI=mongodb-uri:latest

echo "Proxima UI Deployment complete!"