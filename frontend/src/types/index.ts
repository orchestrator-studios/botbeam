export interface Device {
  id: string;
  name: string;
  isDefault: boolean;
  archivedAt: string | null;
  createdAt: string;
  content: Content | null;
}

export type ContentType = 'text' | 'markdown' | 'html' | 'url' | 'image' | 'list' | 'dashboard' | 'table' | 'json';

export interface TableColumn {
  id: string;
  label: string;
}

export interface TableData {
  columns: TableColumn[];
  rows: Record<string, unknown>[];
}

export interface Content {
  type: ContentType;
  body: string;
  updatedAt: string;
}

export interface DashboardCard {
  title: string;
  value: string;
  subtitle?: string;
}

export interface ListItem {
  text: string;
  checked?: boolean;
}

export type WSEvent =
  | { event: 'device_created'; device: Device }
  | { event: 'device_updated'; device: Device }
  | { event: 'device_deleted'; deviceId: string }
  | { event: 'device_archived'; deviceId: string }
  | { event: 'device_unarchived'; device: Device }
  | { event: 'devices_reset' };
