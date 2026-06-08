import { useState, useCallback, useMemo } from 'react';
import { marked } from 'marked';
import type { Content, DashboardCard, ListItem, TableData } from '../types';
import { useBotBeam } from '../context/BotBeamContext';

interface Props {
  content: Content;
}

function UrlEmbed({ url }: { url: string }) {
  const { proxyUrl } = useBotBeam();
  const [failed, setFailed] = useState(false);

  const onLoad = useCallback((e: React.SyntheticEvent<HTMLIFrameElement>) => {
    try {
      // If the proxy returned an error JSON body, the iframe will load but show garbage.
      // We can detect this by checking if the iframe document is accessible and tiny.
      const doc = e.currentTarget.contentDocument;
      if (doc) {
        const text = doc.body?.innerText ?? '';
        if (text.startsWith('{"error"')) {
          setFailed(true);
        }
      }
    } catch {
      // Cross-origin — means the page actually loaded (good)
    }
  }, []);

  if (failed) {
    return (
      <div className="content-url-failed">
        <p>This site couldn't be loaded in the viewer. Some sites block embedding or aren't available through our proxy.</p>
        <a href={url} target="_blank" rel="noopener noreferrer">{url}</a>
      </div>
    );
  }

  return (
    <>
      <div className="content-url-bar">
        <a href={url} target="_blank" rel="noopener noreferrer" title={url}>{url}</a>
      </div>
      <iframe
        className="content-url"
        src={proxyUrl(url)}
        allowFullScreen
        onError={() => setFailed(true)}
        onLoad={onLoad}
      />
    </>
  );
}

function ImageEmbed({ url }: { url: string }) {
  const [failed, setFailed] = useState(false);

  if (failed) {
    return (
      <div className="content-url-failed">
        <p>This image couldn't be loaded. The source may be unavailable or blocking external access.</p>
        <a href={url} target="_blank" rel="noopener noreferrer">{url}</a>
      </div>
    );
  }

  return <img className="content-image" src={url} alt="Display" onError={() => setFailed(true)} />;
}

function JsonViewer({ body }: { body: string }) {
  let formatted: string;
  try {
    formatted = JSON.stringify(JSON.parse(body), null, 2);
  } catch {
    formatted = body;
  }
  return (
    <pre className="content-json">
      <code>{formatted}</code>
    </pre>
  );
}

type SortDir = 'asc' | 'desc' | null;

function TableView({ data }: { data: TableData }) {
  const [sortCol, setSortCol] = useState<string | null>(null);
  const [sortDir, setSortDir] = useState<SortDir>(null);
  const [filter, setFilter] = useState('');

  const toggleSort = (colId: string) => {
    if (sortCol !== colId) { setSortCol(colId); setSortDir('asc'); }
    else if (sortDir === 'asc') setSortDir('desc');
    else { setSortCol(null); setSortDir(null); }
  };

  const rows = useMemo(() => {
    let result = data.rows;

    if (filter) {
      const q = filter.toLowerCase();
      result = result.filter(row =>
        data.columns.some(col => String(row[col.id] ?? '').toLowerCase().includes(q))
      );
    }

    if (sortCol && sortDir) {
      result = [...result].sort((a, b) => {
        const av = a[sortCol] ?? '';
        const bv = b[sortCol] ?? '';
        const an = Number(av), bn = Number(bv);
        let cmp: number;
        if (!isNaN(an) && !isNaN(bn) && av !== '' && bv !== '') {
          cmp = an - bn;
        } else {
          cmp = String(av).localeCompare(String(bv));
        }
        return sortDir === 'desc' ? -cmp : cmp;
      });
    }

    return result;
  }, [data.rows, data.columns, filter, sortCol, sortDir]);

  return (
    <div className="content-table-wrap">
      <div className="content-table-toolbar">
        <input
          className="content-table-search"
          type="text"
          placeholder="Filter rows..."
          value={filter}
          onChange={e => setFilter(e.target.value)}
        />
        <span className="content-table-count">
          {rows.length}{filter ? ` / ${data.rows.length}` : ''} row{rows.length !== 1 ? 's' : ''}
        </span>
      </div>
      <div className="content-table-scroll">
        <table className="content-table">
          <thead>
            <tr>
              {data.columns.map(col => (
                <th key={col.id} onClick={() => toggleSort(col.id)}>
                  <span>{col.label}</span>
                  <span className="sort-indicator">
                    {sortCol === col.id ? (sortDir === 'asc' ? ' \u25B2' : ' \u25BC') : ''}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i}>
                {data.columns.map(col => (
                  <td key={col.id}>{String(row[col.id] ?? '')}</td>
                ))}
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={data.columns.length} className="content-table-empty">
                  {filter ? 'No matching rows' : 'No data'}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function ContentRenderer({ content }: Props) {
  switch (content.type) {
    case 'text':
      return <div className="content content-text">{content.body}</div>;

    case 'markdown':
      return (
        <div
          className="content content-markdown"
          dangerouslySetInnerHTML={{ __html: marked.parse(content.body) as string }}
        />
      );

    case 'html':
      return (
        <div className="content">
          <iframe
            className="content-html"
            sandbox="allow-scripts"
            srcDoc={content.body}
          />
        </div>
      );

    case 'url':
      return (
        <div className="content">
          <UrlEmbed url={content.body} />
        </div>
      );

    case 'image':
      return (
        <div className="content content-image-wrap">
          <ImageEmbed url={content.body} />
        </div>
      );

    case 'list': {
      const items: (string | ListItem)[] = JSON.parse(content.body);
      return (
        <div className="content">
          <ul className="content-list">
            {items.map((item, i) => {
              const isObj = typeof item === 'object';
              const text = isObj ? item.text : item;
              const checked = isObj && item.checked;
              return (
                <li key={i} className={checked ? 'checked' : ''}>
                  <div className="check" />
                  <span>{text}</span>
                </li>
              );
            })}
          </ul>
        </div>
      );
    }

    case 'dashboard': {
      const cards: DashboardCard[] = JSON.parse(content.body);
      return (
        <div className="content">
          <div className="content-dashboard">
            {cards.map((card, i) => (
              <div key={i} className="dash-card">
                <div className="title">{card.title}</div>
                <div className="value">{card.value}</div>
                {card.subtitle && <div className="subtitle">{card.subtitle}</div>}
              </div>
            ))}
          </div>
        </div>
      );
    }

    case 'json':
      return (
        <div className="content content-json-wrap">
          <JsonViewer body={content.body} />
        </div>
      );

    case 'table': {
      let tableData: TableData | null = null;
      try { tableData = JSON.parse(content.body); } catch { /* invalid JSON */ }
      if (!tableData?.columns || !tableData?.rows) return <div className="content content-text">Invalid table data</div>;
      return (
        <div className="content content-table">
          <TableView data={tableData} />
        </div>
      );
    }

    default:
      return <div className="content content-text">{content.body}</div>;
  }
}
