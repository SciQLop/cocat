#!/usr/bin/env sh

set -e
~/.local/bin/cocat remove-user-from-room --email "$1" --room-id "$2" --db-path "$DB_PATH/users.db"