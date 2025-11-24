#!/usr/bin/env sh

set -e
~/.local/bin/cocat create-user --email "$1" --password "$2" --db-path "$DB_PATH/users.db"
