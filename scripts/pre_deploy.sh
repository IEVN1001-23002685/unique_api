#!/bin/sh
# Paso Pre-Deploy de Railway: espera a MySQL y aplica únicamente migraciones.
# Las semillas nunca se ejecutan automáticamente; se lanzan de forma explícita.
set -eu

python scripts/wait_for_db.py
flask db upgrade
