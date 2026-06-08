const mysql = require('mysql2/promise');

let pool;

function getPool() {
  if (!pool) {
    pool = mysql.createPool({
      host: process.env.DB_HOST,
      user: process.env.DB_USER,
      password: process.env.DB_PASSWORD,
      database: process.env.DB_NAME,
      waitForConnections: true,
      connectionLimit: 10,
    });
  }
  return pool;
}

async function initDB() {
  const db = getPool();

  await db.query(`
    CREATE TABLE IF NOT EXISTS namespaces (
      id VARCHAR(12) PRIMARY KEY,
      ip_address VARCHAR(45),
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
  `);

  await db.query(`
    CREATE TABLE IF NOT EXISTS api_log (
      id INT AUTO_INCREMENT PRIMARY KEY,
      namespace VARCHAR(12),
      action VARCHAR(50) NOT NULL,
      device VARCHAR(100),
      content_type VARCHAR(20),
      body LONGTEXT,
      ip_address VARCHAR(45),
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
  `);

  await db.query(`
    CREATE TABLE IF NOT EXISTS devices (
      id VARCHAR(100) NOT NULL,
      namespace VARCHAR(12) NOT NULL,
      name VARCHAR(255) NOT NULL,
      content_type VARCHAR(20),
      content_body LONGTEXT,
      content_updated_at TIMESTAMP NULL,
      pickup_mode VARCHAR(10),
      pickup_count INT NOT NULL DEFAULT 0,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      PRIMARY KEY (namespace, id),
      FOREIGN KEY (namespace) REFERENCES namespaces(id) ON DELETE CASCADE
    )
  `);

  await db.query(`
    CREATE TABLE IF NOT EXISTS pickups (
      id INT AUTO_INCREMENT PRIMARY KEY,
      namespace VARCHAR(12) NOT NULL,
      device_id VARCHAR(100) NOT NULL,
      picked_up_by VARCHAR(255) NOT NULL,
      picked_up_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY (namespace, device_id) REFERENCES devices(namespace, id) ON DELETE CASCADE
    )
  `);

  // ── Auth: organizations + users (matches the kh / table-that house pattern:
  //    bcrypt + JWT bearer + org_id/role; auth is stateless so there is no token table) ──
  await db.query(`
    CREATE TABLE IF NOT EXISTS organizations (
      id VARCHAR(12) PRIMARY KEY,
      name VARCHAR(255) NOT NULL,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
  `);

  await db.query(`
    CREATE TABLE IF NOT EXISTS users (
      id VARCHAR(12) PRIMARY KEY,
      email VARCHAR(255) NOT NULL UNIQUE,
      password_hash VARCHAR(255) NOT NULL,
      full_name VARCHAR(255),
      org_id VARCHAR(12) NOT NULL,
      role VARCHAR(20) NOT NULL DEFAULT 'member',
      namespace_id VARCHAR(12) NOT NULL,
      is_active TINYINT(1) NOT NULL DEFAULT 1,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY (org_id) REFERENCES organizations(id),
      FOREIGN KEY (namespace_id) REFERENCES namespaces(id) ON DELETE CASCADE
    )
  `);

  // Seed the Default Organization (new sign-ups join it; org access control comes later)
  await db.query(
    `INSERT IGNORE INTO organizations (id, name) VALUES ('org_default', 'Default Organization')`
  );

  // Migration: add content columns to devices if missing (for existing databases)
  await db.query(`ALTER TABLE devices ADD COLUMN IF NOT EXISTS content_type VARCHAR(20)`).catch(() => {});
  await db.query(`ALTER TABLE devices ADD COLUMN IF NOT EXISTS content_body LONGTEXT`).catch(() => {});
  await db.query(`ALTER TABLE devices ADD COLUMN IF NOT EXISTS content_updated_at TIMESTAMP NULL`).catch(() => {});
  await db.query(`ALTER TABLE devices ADD COLUMN IF NOT EXISTS pickup_mode VARCHAR(10)`).catch(() => {});
  await db.query(`ALTER TABLE devices ADD COLUMN IF NOT EXISTS pickup_count INT NOT NULL DEFAULT 0`).catch(() => {});

  // Backfill pickup_count from pickups table for existing data
  await db.query(`
    UPDATE devices d
    SET d.pickup_count = (
      SELECT COUNT(*) FROM pickups p WHERE p.namespace = d.namespace AND p.device_id = d.id
    )
    WHERE d.pickup_mode IS NOT NULL
  `).catch(() => {});

  // Migration: move data from content table to devices table if content table exists
  try {
    const [tables] = await db.query(`SHOW TABLES LIKE 'content'`);
    if (tables.length > 0) {
      await db.query(`
        UPDATE devices d
        JOIN content c ON d.namespace = c.namespace AND d.id = c.device_id
        SET d.content_type = c.type,
            d.content_body = c.body,
            d.content_updated_at = c.updated_at
      `);
      await db.query(`DROP TABLE content`);
    }
  } catch (err) {
    // Migration already ran or content table doesn't exist — fine
  }

  // Add ip_address column if missing (safe for existing tables)
  await db.query(`
    ALTER TABLE namespaces ADD COLUMN IF NOT EXISTS ip_address VARCHAR(45) AFTER id
  `).catch(() => {});

  console.log('  Database initialized.');
}

module.exports = { getPool, initDB };
