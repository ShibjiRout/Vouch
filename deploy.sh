#!/bin/bash
REGISTRY="doclenses.azurecr.io"
RG="Doc_Lense"

echo "Logging into ACR..."
az acr login --name doclenses

echo "Building images..."
docker build -t $REGISTRY/doclense-server:latest -f Dockerfile . && \
docker build -t $REGISTRY/doclense-worker:latest -f Dockerfile.worker .

echo "Pushing images..."
docker push $REGISTRY/doclense-server:latest && \
docker push $REGISTRY/doclense-worker:latest

echo "Updating Container Apps..."
az containerapp update --name doclense-server --resource-group $RG --image $REGISTRY/doclense-server:latest && \
az containerapp update --name doclense-worker --resource-group $RG --image $REGISTRY/doclense-worker:latest

echo "Deployment complete."