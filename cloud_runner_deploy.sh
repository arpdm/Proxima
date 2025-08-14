#!/bin/bash

# Build and deploy from main directory
cd /Users/alexwright/Projects/Proxima

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
  --set-env-vars EXPERIMENT_ID=exp_001 \
  --set-secrets MONGODB_URI=mongodb-uri:latest

echo "Proxima UI Deployment complete!"