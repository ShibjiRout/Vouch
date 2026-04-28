$REGISTRY = "doclesnses.azurecr.io"
$RG = "Doc_Lense"

Write-Host "Logging into ACR..."
az acr login --name DocLesnses

Write-Host "Building images..."
docker build -t "$REGISTRY/doclense-server:latest" -f Dockerfile .
docker build -t "$REGISTRY/doclense-worker:latest" -f Dockerfile.worker .

Write-Host "Pushing images..."
docker push "$REGISTRY/doclense-server:latest"
docker push "$REGISTRY/doclense-worker:latest"

Write-Host "Updating Container Apps..."
az containerapp update --name doclense-server --resource-group $RG --image "$REGISTRY/doclense-server:latest"
az containerapp update --name doclense-worker --resource-group $RG --image "$REGISTRY/doclense-worker:latest"

Write-Host "Deployment complete."