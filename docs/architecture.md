# BotBeam — Architecture & Deployment

## What BotBeam Does

BotBeam gives AI chatbots (ChatGPT, Claude, Claude Code) a set of browser tabs they can push content to in real time. A user opens their BotBeam URL in a browser, connects their AI via MCP, and then tells the AI what to show. The AI creates tabs and pushes content — markdown, images, webpages, dashboards, lists — and the browser updates instantly via WebSocket.

## Three Actors

```
Person (browser)  ──►  BotBeam Server  ◄──  Chatbot (MCP client)
                         ├─ store.js (MySQL)
                         ├─ websocket.js (real-time push)
                         └─ routes.js / mcp.js (two entry points)
```

- **Person** — opens `https://botbeam.ironcliff.ai/s/{namespace}` in a browser. Sees tabs, receives content via WebSocket.
- **Chatbot** — connects to `https://botbeam.ironcliff.ai/s/{namespace}/mcp` via MCP protocol. Calls tools like `push_content`, `list_devices`, `create_device`, `delete_device`.
- **Server** — one Node.js process running Express + WebSocket. Stores everything in MySQL. Two paths reach the same core logic (`store.js`):
  - **Browser path**: `routes.js` — REST API at `/s/{namespace}/api/...`
  - **Chatbot path**: `mcp.js` — MCP JSON-RPC at `/s/{namespace}/mcp`

## Server File Structure

```
server/
  index.js        — Wiring: creates Express app, mounts both routers, starts server
  store.js        — All MySQL queries. Validation (type whitelist, size cap, name checks)
  routes.js       — REST API router (browser-facing). Also has the URL proxy endpoint
  mcp.js          — MCP router (chatbot-facing). DirectClient calls store.js directly
  websocket.js    — WebSocket connection tracking + broadcast/broadcastGlobal
  namespace.js    — Middleware: validates namespace exists, touches last_active
  log.js          — API logging to api_log table
  db.js           — MySQL connection pool + table creation

mcp/
  tools.js        — MCP tool definitions (used by server/mcp.js)

frontend/
  src/            — React app (Vite + TypeScript)
  dist/           — Built assets (served by Express at /app/)
```

## How Mounting Works

Both sides are mounted identically in `index.js`:

```js
app.use('/s/:namespace/mcp', namespaceMiddleware, createMCPRouter(broadcast, broadcastGlobal));
app.use('/s/:namespace/api', namespaceMiddleware, createAPIRouter(broadcast, broadcastGlobal));
```

Both routers:
- Export `createRouter(broadcast, broadcastGlobal)` returning an Express Router
- Use `req.namespace` set by the shared `namespaceMiddleware`
- `require('./store')` internally (store is a singleton module)
- Only `broadcast` and `broadcastGlobal` are injected (they're created at runtime from the WebSocket server)

## Content Types

| Type | Body | Rendering |
|------|------|-----------|
| `markdown` | Markdown string | Rendered via marked.js |
| `url` | URL string | Proxied through server to bypass CSP/X-Frame-Options |
| `image` | Image URL | `<img>` tag |
| `dashboard` | JSON array of `{title, value, subtitle?}` | Card grid |
| `list` | JSON array of strings or `{text, checked}` | Checklist |
| `text` | Plain string | Literal text |
| `html` | HTML string | Sandboxed iframe |

Validated in `store.js`. Max body size: 500KB.

## Database (MySQL on RDS)

Instance: `chatter.c0guz2wkpcod.us-east-2.rds.amazonaws.com`
Database name: `signal`

Tables (created automatically by `db.js` on startup):

- **namespaces** — `id` (nanoid 8), `ip_address`, `created_at`, `last_active`
- **devices** — `id` (nanoid 8), `namespace` (FK), `name`, `content_type`, `content_body` (LONGTEXT), `content_updated_at`, `created_at`
- **api_log** — `namespace`, `action`, `device`, `content_type`, `body` (LONGTEXT), `ip_address`, `created_at`

---

# Deployment

## Infrastructure Overview

```
                   HTTPS                          MySQL
Browser/Chatbot ──────►  ALB ──► ECS Fargate ──────────► RDS
                         │        (1 task)                (chatter)
                         │
                    ACM cert
                 (botbeam.ironcliff.ai)
```

| Component | What it is | How to find it |
|-----------|-----------|----------------|
| **ECR** | Docker image registry | AWS Console → ECR → `botbeam/web` |
| **ECS Cluster** | Container orchestration | `botbeam-prod-Cluster-RF1huELGViqb` |
| **ECS Service** | Keeps 1 task running | Service `botbeam-prod-web` in that cluster |
| **ALB** | Load balancer, terminates HTTPS | `botbea-Publi-0ZimuF1UCfov-125301842.us-east-2.elb.amazonaws.com` |
| **ACM** | SSL certificate | Cert for `botbeam.ironcliff.ai` |
| **Route 53** | DNS | `botbeam.ironcliff.ai` CNAME → ALB |
| **RDS** | MySQL database | `chatter.c0guz2wkpcod.us-east-2.rds.amazonaws.com` |
| **SSM Parameter Store** | DB password (encrypted) | `/copilot/botbeam/prod/secrets/db_password` |

## AWS Copilot Structure

```
copilot/
  .workspace              — app: botbeam
  environments/prod/
    manifest.yml           — env: prod
  web/
    manifest.yml           — service: web (Load Balanced Web Service)
```

The service manifest (`copilot/web/manifest.yml`) defines:
- Image: built from `Dockerfile`, port 4888
- Resources: 256 CPU, 512 MB memory, 1 instance
- Health check: `GET /health` every 30s
- Stickiness: enabled (for WebSocket affinity)
- Environment variables: `PORT`, `DB_HOST`, `DB_USER`, `DB_NAME`
- Secrets: `DB_PASSWORD` from SSM Parameter Store
- Network: public VPC placement

## How to Deploy

```bash
AWS_PROFILE=copilot copilot svc deploy --name web --env prod
```

This command:
1. Builds the Docker image locally
2. Pushes it to ECR (`botbeam/web:latest`)
3. Updates the ECS task definition
4. ECS rolls out the new task (starts new, waits for health check, drains old)

Typical deploy time: ~4 minutes.

### Post-Deploy: Update RDS Security Group

**Important:** RDS and ECS are in different VPCs. The ECS task connects to RDS via its public IP, which changes on every deploy. After deploying, update the RDS security group:

```bash
# Get the new ECS task's public IP
TASK_ARN=$(AWS_PROFILE=copilot aws ecs list-tasks \
  --cluster botbeam-prod-Cluster-RF1huELGViqb \
  --region us-east-2 --query "taskArns[0]" --output text)

ENI=$(AWS_PROFILE=copilot aws ecs describe-tasks \
  --cluster botbeam-prod-Cluster-RF1huELGViqb \
  --tasks "$TASK_ARN" --region us-east-2 \
  --query "tasks[0].attachments[0].details[?name=='networkInterfaceId'].value" --output text)

NEW_IP=$(AWS_PROFILE=copilot aws ec2 describe-network-interfaces \
  --network-interface-ids "$ENI" --region us-east-2 \
  --query "NetworkInterfaces[0].Association.PublicIp" --output text)

echo "New ECS IP: $NEW_IP"

# Remove old ECS IP rule (replace OLD_IP with the previous one)
AWS_PROFILE=copilot aws ec2 revoke-security-group-ingress \
  --group-id sg-0b539947e6ed29cf0 --protocol tcp --port 3306 \
  --cidr OLD_IP/32 --region us-east-2

# Add new ECS IP rule
AWS_PROFILE=copilot aws ec2 authorize-security-group-ingress \
  --group-id sg-0b539947e6ed29cf0 --protocol tcp --port 3306 \
  --cidr $NEW_IP/32 --region us-east-2
```

### Why the IP Dance?

RDS is in the default VPC (`vpc-0af0e03541cfd6520`). ECS is in Copilot's VPC (`vpc-0029a0ba06398b0c2`). Since they're different VPCs, security group references don't work — we can only whitelist IPs. ECS tasks in public subnets get a new public IP on every deploy.

**Future fix options:**
- **NAT Gateway** — gives ECS a fixed egress IP (~$30/mo)
- **Move RDS into Copilot VPC** — then use security group references
- **VPC Peering** — connect the two VPCs

## Viewing Logs

```bash
# Last hour of logs
AWS_PROFILE=copilot copilot svc logs --name web --env prod --since 1h

# Tail in real time
AWS_PROFILE=copilot copilot svc logs --name web --env prod --follow

# Logs from a crashed task
AWS_PROFILE=copilot copilot svc logs --name web --env prod --previous
```

## Security

| Concern | Status |
|---------|--------|
| DB password | Stored in SSM Parameter Store (SecureString, KMS encrypted). Referenced via `secrets:` in manifest |
| RDS access | Security group allows port 3306 from ECS task IP + developer IP only |
| HTTPS | ACM certificate on ALB, HTTP redirects to HTTPS |
| Namespace isolation | Each namespace gets a random 8-char ID (nanoid). No auth — URL is the access key |
| Content validation | Type whitelist, 500KB body size cap, device name validation |
| URL proxy | SSRF protection blocks internal/private IPs. Scripts stripped from proxied HTML |
| `.env` | Gitignored. Never committed |

### RDS Security Group

Group ID: `sg-0b539947e6ed29cf0`

Current rules (port 3306):
- Developer IP (update when your IP changes)
- Current ECS task IP (update after each deploy)

## Local Development

```bash
cp .env.example .env   # Fill in your DB credentials
npm install
npm start              # Server on http://localhost:4888
```

The `.env` file is gitignored. Required variables:

```
DB_HOST=chatter.c0guz2wkpcod.us-east-2.rds.amazonaws.com
DB_USER=admin
DB_PASSWORD=<from SSM or ask team>
DB_NAME=signal
PORT=4888
```

## IAM

Deployments use the `copilot` AWS CLI profile, which corresponds to IAM user `copilot-deploy` with admin permissions.

The ECS execution role (`botbeam-prod-web-ExecutionRole-R6C5ek2ytN7N`) has:
- ECR pull access (managed by Copilot)
- `ssm:GetParameters` on `/copilot/botbeam/prod/secrets/db_password`
- `kms:Decrypt` on the SSM default KMS key
