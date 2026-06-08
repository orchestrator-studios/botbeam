import type { Content, ContentType, TableData } from '../types';

export const TYPE_META: Record<ContentType, { label: string; color: string }> = {
  text:      { label: 'Text',      color: '#888' },
  markdown:  { label: 'Markdown',  color: '#4fc3f7' },
  html:      { label: 'HTML',      color: '#ce93d8' },
  url:       { label: 'Web',       color: '#ffb74d' },
  image:     { label: 'Image',     color: '#81c784' },
  list:      { label: 'List',      color: '#90caf9' },
  dashboard: { label: 'Dashboard', color: '#fff176' },
  table:     { label: 'Table',     color: '#a5d6a7' },
  json:      { label: 'JSON',      color: '#ffcc80' },
};

export function contentDetail(content: Content): string | null {
  switch (content.type) {
    case 'url':
    case 'image': {
      try { return new URL(content.body).hostname; } catch { return content.body; }
    }
    case 'list': {
      try {
        const items = JSON.parse(content.body);
        return `${items.length} item${items.length === 1 ? '' : 's'}`;
      } catch { return null; }
    }
    case 'dashboard': {
      try {
        const cards = JSON.parse(content.body);
        return `${cards.length} card${cards.length === 1 ? '' : 's'}`;
      } catch { return null; }
    }
    case 'table': {
      try {
        const data: TableData = JSON.parse(content.body);
        return `${data.rows.length} row${data.rows.length === 1 ? '' : 's'}, ${data.columns.length} col${data.columns.length === 1 ? '' : 's'}`;
      } catch { return null; }
    }
    case 'json': {
      try {
        const data = JSON.parse(content.body);
        if (Array.isArray(data)) return `${data.length} item${data.length === 1 ? '' : 's'}`;
        if (typeof data === 'object' && data !== null) return `${Object.keys(data).length} key${Object.keys(data).length === 1 ? '' : 's'}`;
        return null;
      } catch { return null; }
    }
    case 'html':
      return `${Math.round(content.body.length / 1024)}KB`;
    default:
      return null;
  }
}
