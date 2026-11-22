# music-releases-alert

This program checks a list of artists for new music releases. It posts each new release to a Discord channel. It uses the free Deezer API, so you do not need a Deezer or Spotify account.

Each post shows the artist, title, type (album, single, EP or compilation), release date, cover art, and a Deezer link.

## How it works

The program runs all day as a Docker container. It checks for new releases at 00:15, 06:00, 12:00, and 18:00 in the server time zone. It waits at least 200 ms between Deezer requests.

The program matches each artist name to a Deezer artist ID. It saves the ID in a local SQLite database, so it searches for a name only once. It also saves every release that it has seen, so no release is posted twice.

On the first check of an artist, the program posts only releases from the current year. It records older releases as seen without posting them.

The program sends a warning to Discord in these cases:
- A name matches more than one Deezer artist, or has no exact match. The warning names the artist that the program chose and lists other candidates.
- A name finds no artist on Deezer.
- A request to Deezer fails. The warning includes the error text.

Each ambiguous or missing name is reported once. The program tries a failed Deezer request again at the next scheduled check.

## Set up

You need Docker and Docker Compose on the Raspberry Pi.

1. In Discord, open the channel settings. Go to Integrations, then Webhooks, and create a webhook. Copy the webhook URL.
2. Copy the example files:
   ```
   cp .env.example .env
   cp data/artists.txt.example data/artists.txt
   ```
3. Open `.env` and set `DISCORD_WEBHOOK_URL`.
4. Open `data/artists.txt` and list your artists, one per line.
5. Start the container:
   ```
   docker compose up -d --build
   ```
6. Read the log to make sure that the next run time is correct:
   ```
   docker compose logs -f
   ```

## Artist file format

```
Daft Punk            # plain name
Justice | 1234       # name with a pinned Deezer ID
deezer:27            # Deezer ID only
```

To find an ID, open the artist page on deezer.com. The ID is the number at the end of the URL. A pinned ID skips the search, so the match is never ambiguous.

If you receive an ambiguous match warning, add the correct ID to the line. The new line is looked up again at the next check.

## Test commands

Run these commands from the project folder. Each one reads the same `.env` file and `data/` folder.

```
docker compose run --rm music-alert python -m music_alert --resolve-only
docker compose run --rm music-alert python -m music_alert --dry-run
docker compose run --rm music-alert python -m music_alert --once
```

- `--resolve-only` matches the artist file to Deezer IDs and prints the result. It sends nothing to Discord.
- `--dry-run` finds new releases and prints them. It does not post and does not save anything.
- `--once` does one real check and then exits.

## Configuration

You set these values in `.env`.

| Variable | Default | Meaning |
| --- | --- | --- |
| `DISCORD_WEBHOOK_URL` | none | The webhook URL. Required. |
| `SCHEDULE` | `00:15,06:00,12:00,18:00` | Check times in HH:MM, server time. |
| `REQUEST_DELAY_MS` | `200` | Minimum gap between Deezer requests. |
| `RUN_ON_START` | `false` | If `true`, run one check at container start. |
| `LOG_LEVEL` | `INFO` | Log detail. |

## Development

```
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt pytest
pytest
```
