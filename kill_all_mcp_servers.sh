#!/bin/bash
# Kill all Python processes containing the word 'port'
# Safe version with confirmation prompt.

# Find process IDs (excluding the grep itself)
PIDS=$(ps -ef | grep python | grep port | grep -v grep | awk '{print $2}')

if [ -z "$PIDS" ]; then
  echo "No matching python processes found."
  exit 0
fi

echo "Found the following processes:"
ps -ef | grep python | grep port | grep -v grep

# Ask for confirmation
read -p "Do you want to kill these processes? (y/N): " CONFIRM
if [[ "$CONFIRM" =~ ^[Yy]$ ]]; then
  echo "Killing processes: $PIDS"
  kill -9 $PIDS
  echo "Done."
else
  echo "Aborted."
fi

