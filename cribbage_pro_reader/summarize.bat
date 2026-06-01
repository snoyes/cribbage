type "..\data\*.json" 2>NUL | jq -s -f summarize.jq
