# Contributing

## Development Setup

### Prerequisites

* Python 3.12 or later
* [Poetry](https://python-poetry.org/docs/#installation) 2.0 or later

### Install Dependencies

```bash
# Install all dependencies including dev tools (ruff, mypy, pytest, etc.)
$ poetry install --no-root
```

### Activate the Virtual Environment

Either activate the environment:

```bash
$ poetry env activate
```

Or prefix commands with `poetry run` (shown in the examples below).

## Project Structure

```
src/            # Application source code
  main.py       # Entry point
tests/          # Test suite
examples/       # Sample configuration files
```

## Running the Gateway Locally

```bash
$ poetry run python src/main.py -u <saic-user> -p <saic-pwd> -m tcp://localhost:1883
```

You can also create a `.env` file in the project root with your configuration:

```
SAIC_USER=your-user
SAIC_PASSWORD=your-password
MQTT_URI=tcp://localhost:1883
```

Then simply run:

```bash
$ poetry run python src/main.py
```

## Code Quality

The CI pipeline runs the following checks on every push and pull request. Run them locally before submitting a PR:

```bash
# Type checking
$ poetry run mypy

# Linting
$ poetry run ruff check .

# Tests with coverage
$ poetry run pytest tests --cov
```

## Pull Requests

* PRs should target the `develop` branch
* Ensure all CI checks pass (mypy, ruff, pytest)
