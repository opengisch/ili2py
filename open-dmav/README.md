# open-dmav

Standalone Django project generated from the INTERLIS model `KGK_Alles_V1_0`.

This folder is intentionally independent so it can be moved to its own repository later.

## What is inside

- `open_dmav/`: Django project settings and entry points.
- `apps/`: Generated Django app packages from `KGK_Alles_V1_0.imd`.
- Runtime dependencies (`ili2django`, `ili2py`) are installed via `requirements.txt`.

## Quick start

1. Create a virtual environment and install dependencies.
2. Ensure GDAL/GeoDjango prerequisites are installed in your target environment.
3. Run migrations and start the server.

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

## Notes

Generated apps use `django.contrib.gis.db.models` fields (`PointField`, `PolygonField`, etc.) with `srid=2056`.

## Docker quick start

This repository includes a Docker setup with GeoDjango system dependencies and a PostGIS database.

```bash
docker compose up --build
```

The web app will be available on `http://localhost:8000/`.

On startup, the `web` container entrypoint automatically runs:
- `python manage.py migrate --noinput --run-syncdb`
- `python manage.py sync_enum_values --prune`

This ensures schema migrations and enum value-list seed data are applied before `runserver` starts.

## OGC API Features

The project exposes a single global OAPIF service at `/oapif/`.

Collection registration is automatic for generated `odmav_*` models:
- Feature collections: models with at least one geometry field.
- Lookup collections: enum value-list tables (generated models carrying `__ili2django_values__`).

Enum lookup collections are published so consuming clients can discover allowed values.

Feature collections are writable (`POST`, `PUT`, `PATCH`, `DELETE`) for users with the corresponding Django model permissions (`add`, `change`, `delete`).
Anonymous users keep read-only access (`GET`).
Lookup collections remain read-only.

### Reverse proxy host handling

`django-oapif` generates absolute links from the incoming Django request host.
When deploying behind Traefik, make sure forwarded headers are passed and trusted,
otherwise links may show `localhost`.

This project enables the required Django settings:
- `USE_X_FORWARDED_HOST = True`
- `USE_X_FORWARDED_PORT = True`
- `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")`

For Traefik, ensure the request preserves/provides:
- `Host: <public-domain>`
- `X-Forwarded-Host: <public-domain>`
- `X-Forwarded-Proto: https`

Useful commands:

```bash
# run Django checks in the container
docker compose run --rm web python manage.py check

# create migrations for local custom apps (if you add any)
docker compose run --rm web python manage.py makemigrations

# apply migrations
docker compose run --rm web python manage.py migrate

# synchronize generated enum value-list rows
docker compose run --rm web python manage.py sync_enum_values

# import an XTF transfer into generated models
docker compose run --rm web python manage.py import_xtf /app/data/input.xtf

# import with optional IMD preload and translation IMD
docker compose run --rm web python manage.py import_xtf /app/data/input.xtf \
	--imd /app/models/KGK_Alles_V1_0.imd \
	--translation-imd /app/models/KGK_Alles_fr.imd
```

## Import XTF

You can import transfer data with the Django management command:

```bash
python manage.py import_xtf /path/to/input.xtf
```

Optional flags:

- `--imd /path/to/model.imd`: preload IMD metadata before import.
- `--translation-imd /path/to/translation.imd`: add translation IMDs (repeatable).

The same workflow is available from Django admin at:

- `/admin/import-xtf/`

## Regenerate apps

Regenerate the Django apps from the source IMD using the updated `ili2django` generator:

```bash
cd ..
./.venv313/bin/python -m ili2django.cli generate-models \
	-i ili2django/tests/local_data/models/KGK_V1_0/KGK_Alles_V1_0.imd \
	-o open-dmav/apps \
	-l interface \
	-a odmav \
	--srid 2056
```

After migrations, populate enum tables:

```bash
cd open-dmav
../.venv313/bin/python manage.py sync_enum_values
```
