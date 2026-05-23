# Mintlify Docs

This directory is a Mintlify documentation site for Open Arbitrage Tool.

## Preview locally

With Docker Compose from the project root:

```bash
cd /Users/liuhongyang/Desktop/content/arbitrage_tool
docker compose up -d --build
```

Open:

```text
http://127.0.0.1:3000
```

Or run Mintlify directly:

```bash
cd /Users/liuhongyang/Desktop/content/arbitrage_tool/mintlify-docs
npx mintlify@latest dev
```

If your local Mintlify CLI exposes the newer `mint` command, this also works:

```bash
npx mint@latest dev
```

## Validate

```bash
npx mintlify@latest broken-links
```

## Content map

- `index.mdx`: landing page
- `get-started/quickstart.mdx`: install and first paper-trading ticks
- `get-started/onboarding.mdx`: operator onboarding checklist
- `core-concepts/strategy.mdx`: tranche strategy
- `core-concepts/profit-model.mdx`: net profit calculation
- `core-concepts/risk-controls.mdx`: paper/live risk gates
- `guides/`: local run, VPS deployment, operation, config
- `reference/`: API overview, logs, FAQ
- `openapi.json`: generated from the FastAPI app
