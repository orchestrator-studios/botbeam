export interface Pickup {
  pickedUpBy: string;
  pickedUpAt: string;
}

export interface Device {
  id: string;
  name: string;
  createdAt: string;
  content: Content | null;
  pickupMode?: 'single' | 'multi';
  pickupCount?: number;
  pickups?: Pickup[];
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
  | { event: 'devices_reset' }
  | { event: 'device_picked_up'; deviceId: string; pickedUpBy: string };
