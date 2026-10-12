import type { StreamEvent } from './types';

let token = '';
export function setToken(value: string) {
  token = value;
}

async function responseError(res: Response) {
  const body = await res.json().catch(() => ({}));
  if (res.status === 404 && body.detail === 'Not Found')
    return '接口不存在，请重启新版后端并检查连接地址';
  return typeof body.detail === 'string'
    ? body.detail
    : res.status === 422
      ? '请检查填写的内容'
      : `请求失败（${res.status}）`;
}

export async function api<T>(
  path: string,
  method = 'GET',
  body?: unknown,
): Promise<T> {
  const res = await fetch(`/api${path}`, {
    method,
    headers: {
      ...(body ? { 'Content-Type': 'application/json' } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    ...(body ? { body: JSON.stringify(body) } : {}),
  });
  if (!res.ok) throw new Error(await responseError(res));
  return res.json();
}

export async function streamChat(
  message: string,
  conversationId: string | null,
  onEvent: (event: StreamEvent) => void,
  signal: AbortSignal,
) {
  const res = await fetch('/api/chat/stream', {
    method: 'POST',
    signal,
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ message, conversation_id: conversationId }),
  });
  if (!res.ok) throw new Error(await responseError(res));
  if (!res.body) throw new Error('浏览器不支持流式响应');
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '',
    complete = false;
  try {
    while (true) {
      const { value, done } = await reader.read();
      buffer += done
        ? decoder.decode()
        : decoder.decode(value, { stream: true });
      buffer = buffer.replace(/\r\n/g, '\n');
      let boundary;
      while ((boundary = buffer.indexOf('\n\n')) >= 0) {
        const frame = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        const data = frame
          .split('\n')
          .filter((l) => l.startsWith('data:'))
          .map((l) => l.slice(5).trimStart())
          .join('\n');
        if (data) {
          const event = JSON.parse(data) as StreamEvent;
          onEvent(event);
          if (event.event === 'done') complete = true;
        }
      }
      if (done) break;
    }
    if (!complete) throw new Error('连接中断，回答可能不完整，请重试');
  } finally {
    reader.releaseLock();
  }
}
