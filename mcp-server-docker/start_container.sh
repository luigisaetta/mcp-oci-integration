docker run --rm -it \
  -e TRANSPORT=streamable-http \
  -e HOST=0.0.0.0 \
  -e PORT=8080 \
  -e ENABLE_JWT_TOKEN=false \
  -e IAM_BASE_URL="https://idcs-EXAMPLE.identity.oraclecloud.com" \
  -e ISSUER="https://idcs-EXAMPLE.identity.oraclecloud.com/" \
  -e AUDIENCE="your-audience" \
  -p 8080:8080 \
  --name mcp-http \
  mcp-fastmcp-oracle:latest
