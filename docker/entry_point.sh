#!/usr/bin/env sh

set -e

echo  "Starting cocat server..."
~/.local/bin/cocat serve --host "0.0.0.0" --port "$PORT" --update_dir "$STORAGE_PATH" --db-path "$DB_PATH/users.db"
echo "Cocat server stopped."