# BotBeam

AI-powered virtual display platform. One Node.js process (Express + WebSocket) backed by MySQL on RDS, deployed to AWS ECS Fargate via Copilot.

Live at: https://botbeam.ironcliff.ai

## Deploying

**Always use the deploy script:**

```bash
./deploy.sh
```

This is required because RDS and ECS are in different VPCs. ECS tasks get a new public IP on every deploy, and RDS's security group must allow that IP. The script handles the full sequence: opens the security group, deploys, finds the new IP, locks it back down.

**Do not** run `copilot svc deploy` directly — the new task will fail to connect to the database.

## Key Files

- `server/index.js` — Wiring. Mounts both routers identically
- `server/store.js` — All MySQL queries + validation
- `server/routes.js` — REST API (browser-facing)
- `server/mcp.js` — MCP router (chatbot-facing)
- `mcp/tools.js` — MCP tool definitions
- `docs/architecture.md` — Full architecture and infrastructure docs

## AWS Resources

- **ECS Cluster**: `botbeam-prod-Cluster-RF1huELGViqb`
- **RDS Security Group**: `sg-0b539947e6ed29cf0`
- **SSM Secret**: `/copilot/botbeam/prod/secrets/db_password`
- **AWS Profile**: `copilot`
- **Region**: `us-east-2`
