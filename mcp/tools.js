const { z } = require('zod');

// Bump when the tool surface changes (new tools, renamed params, schema changes)
const MCP_VERSION = '1.1.0';

function registerTools(server, namespace, client) {
  server.tool(
    'list_devices',
    'List all virtual display tabs. Returns each device\'s id, name, and current content.',
    {},
    async () => {
      const devices = await client.listDevices(namespace);
      return { content: [{ type: 'text', text: JSON.stringify(devices, null, 2) }] };
    }
  );

  server.tool(
    'create_device',
    'Create a new virtual display tab, optionally with initial content. To create a dropbox (agent-to-agent data handoff), set type to "json", provide the JSON body, and set pickup_mode to "single" (one pickup) or "multi" (unlimited pickups). When you create a dropbox, you MUST tell the user the device ID so they can relay it to the receiving agent.',
    {
      name: z.string().describe('Display name for the tab (e.g. "Overview", "Cheat Sheet")'),
      type: z.enum(['text', 'markdown', 'html', 'url', 'image', 'list', 'dashboard', 'table', 'json']).optional().describe('Content type (optional)'),
      body: z.string().optional().describe('Content body (optional). For url/image: the URL. For list: JSON array of strings or {text, checked?}. For dashboard: JSON array of {title, value, subtitle?}. For table: JSON {columns: [{id, label}], rows: [{colId: value, ...}]}. For json: any valid JSON string.'),
      pickup_mode: z.enum(['single', 'multi']).optional().describe('Set to make this device a dropbox. "single" = one-time pickup, "multi" = unlimited pickups. Requires type "json".'),
    },
    async ({ name, type, body, pickup_mode }) => {
      const content = type && body ? { type, body } : null;
      const device = await client.createDevice(namespace, name, content, pickup_mode);
      if (pickup_mode) {
        return { content: [{ type: 'text', text: `Dropbox created.\n\nDevice ID: ${device.id}\nName: ${device.name}\nMode: ${pickup_mode}\n\nIMPORTANT: Tell the user this device ID (${device.id}). They will relay it to the receiving agent, who can pick it up using the pickup_dropbox tool.` }] };
      }
      return { content: [{ type: 'text', text: JSON.stringify(device, null, 2) }] };
    }
  );

  server.tool(
    'update_device',
    'Update a virtual display tab. Can change the name, push new content, or clear content by setting content_type to "clear". Content types: text, markdown, html, url (renders in iframe), image (renders from URL), list (JSON array of strings or {text, checked?}), dashboard (JSON array of {title, value, subtitle?}), table (JSON object: {columns: [{id, label}], rows: [{col_id: value}]})',
    {
      device: z.string().describe('Device ID (as returned by list_devices or create_device)'),
      name: z.string().optional().describe('New display name for the tab'),
      content_type: z.enum(['text', 'markdown', 'html', 'url', 'image', 'list', 'dashboard', 'table', 'json', 'clear']).optional().describe('Content type, or "clear" to remove content'),
      body: z.string().optional().describe('Content body (required unless content_type is "clear"). For url/image: the URL string. For list: JSON array of strings or {text, checked?}. For dashboard: JSON array of {title, value, subtitle?}. For table: JSON {columns: [{id, label}], rows: [{colId: value, ...}]}.'),
    },
    async ({ device, name, content_type, body }) => {
      const updates = {};
      if (name) updates.name = name;
      if (content_type === 'clear') {
        updates.content = null;
      } else if (content_type && body) {
        updates.content = { type: content_type, body };
      }
      const result = await client.updateDevice(namespace, device, updates);
      const action = content_type === 'clear' ? 'cleared' : content_type ? `updated (${content_type})` : 'renamed';
      return { content: [{ type: 'text', text: `Device "${result.name}" ${action}` }] };
    }
  );

  server.tool(
    'delete_device',
    'Remove a virtual display tab and its content',
    { device: z.string().describe('Device ID (as returned by list_devices or create_device)') },
    async ({ device }) => {
      await client.deleteDevice(namespace, device);
      return { content: [{ type: 'text', text: `Tab "${device}" deleted.` }] };
    }
  );

  server.tool(
    'reset_devices',
    'Delete all virtual display tabs and their content',
    {},
    async () => {
      await client.resetDevices(namespace);
      return { content: [{ type: 'text', text: 'All devices cleared.' }] };
    }
  );

  server.tool(
    'list_dropboxes',
    'List all dropbox devices in the namespace, including their pickup history. Use this to find dropboxes available for pickup.',
    {},
    async () => {
      const dropboxes = await client.listDropboxes(namespace);
      return { content: [{ type: 'text', text: JSON.stringify(dropboxes, null, 2) }] };
    }
  );

  server.tool(
    'pickup_dropbox',
    'Pick up data from a dropbox device. Returns the JSON content. Single-use dropboxes can only be picked up once. You must identify yourself with picked_up_by.',
    {
      device: z.string().describe('Device ID of the dropbox to pick up'),
      picked_up_by: z.string().describe('Identifier for who is picking up (e.g. your agent name or session ID)'),
    },
    async ({ device, picked_up_by }) => {
      const result = await client.pickupDropbox(namespace, device, picked_up_by);
      return { content: [{ type: 'text', text: `Dropbox picked up successfully.\n\nContent:\n${result.content?.body ?? '(empty)'}` }] };
    }
  );
}

module.exports = { registerTools, MCP_VERSION };
