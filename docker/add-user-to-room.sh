#!/usr/bin/env sh

set -e
~/.local/bin/cocat add-user-to-room --email "$1" --room-id "$2" --db-path "$DB_PATH/users.db"
