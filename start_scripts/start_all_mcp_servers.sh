echo "Starting all MCP servers..."
# nohup ./start_mcp_selectai.sh & >> nohup.out
# nohup ./start_mcp_internet_search.sh & >> nohup.out
nohup ./start_mcp_semantic_search_with_oci_iam.sh & >> nohup.out
nohup ./start_mcp_consumption.sh & >> nohup.out
# nohup ./start_mcp_employee.sh & >> nohup.out
# nohup ./start_mcp_oml_predict.sh & >> nohup.out
nohup ./start_mcp_agenda.sh & >> nohup.out
# nohup ./start_mcp_github.sh & >> nohup.out
# nohup ./start_mcp_local_fs.sh & >> nohup.out

